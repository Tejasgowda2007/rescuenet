"""
TCP Network Transport for Local Wi-Fi / Hotspot Mesh Synchronization.

Design Decisions:
1. Pure Local Networking (No Internet Needed):
   - Volunteers connect their laptops/phones to a portable battery-powered Wi-Fi router
     or mobile phone hotspot with cellular data turned OFF.
   - Point-to-point IP communication via standard TCP sockets.
2. Stream Framing:
   - TCP is a streaming byte protocol. Message boundaries are enforced using a 4-byte
     big-endian length prefix: [4-byte unsigned int Length][Canonical JSON Payload].
3. Fault-Tolerant & Non-Blocking:
   - If a peer's laptop goes out of range or sleeps, connection attempts timeout
     gracefully (returning None), simulating a real-world transient link cut.
4. Exact Wire Byte Accounting:
   - Measures every byte transmitted over the wire (including the 4-byte framing header).
"""

from __future__ import annotations
import socket
import struct
import threading
import time
from typing import Dict, Tuple, Callable, Optional
from .base import Transport, TransportMessage


DEFAULT_MAX_FRAME_SIZE = 10 * 1024 * 1024  # 10 MB maximum allowed frame size


class FrameTooLargeError(ConnectionError):
    """Raised when an incoming TCP frame exceeds the maximum allowed size limit."""
    pass


def recv_exact(sock: socket.socket, num_bytes: int) -> bytes:
    """
    Read exactly num_bytes from a TCP stream.
    Raises ConnectionError if the connection drops before receiving full frame.
    """
    chunks = []
    received = 0
    while received < num_bytes:
        chunk = sock.recv(min(num_bytes - received, 65536))
        if not chunk:
            raise ConnectionError(f"Connection closed prematurely (got {received}/{num_bytes} bytes)")
        chunks.append(chunk)
        received += len(chunk)
    return b"".join(chunks)


class TCPTransport(Transport):
    """
    Real-world TCP implementation of the RescueNet Transport interface.
    """

    def __init__(
        self,
        node_id: str,
        host: str = "127.0.0.1",
        port: int = 0,  # Port 0 binds to any available ephemeral port
        timeout: float = 3.0,
        max_frame_size: int = DEFAULT_MAX_FRAME_SIZE,
    ) -> None:
        self.node_id = node_id
        self.host = host
        self.timeout = timeout
        self.max_frame_size = max_frame_size
        self.handler: Optional[Callable[[TransportMessage], Optional[TransportMessage]]] = None

        # Peer directory: {peer_node_id: (ip_address, port)}
        self.peers: Dict[str, Tuple[str, int]] = {}

        # Wire statistics
        self._total_bytes_transferred: int = 0
        self._total_messages_sent: int = 0
        self._lock = threading.Lock()

        # Initialize listening TCP server socket
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind((self.host, port))
        # Retrieve actual bound port (useful if port=0 was passed)
        self.port = self._server_sock.getsockname()[1]
        self._server_sock.listen(128)

        # Background server listener thread
        self._is_running = True
        self._server_thread = threading.Thread(
            target=self._server_listen_loop,
            name=f"TCPTransport-{self.node_id}-{self.port}",
            daemon=True,
        )
        self._server_thread.start()

    def register_node(
        self,
        node_id: str,
        handler: Callable[[TransportMessage], Optional[TransportMessage]]
    ) -> None:
        """Register the incoming message handler."""
        self.node_id = node_id
        self.handler = handler

    def unregister_node(self, node_id: str) -> None:
        """Unregister the message handler."""
        self.handler = None

    def add_peer(self, peer_id: str, host: str, port: int) -> None:
        """Register a peer device's IP address and TCP port."""
        self.peers[peer_id] = (host, port)

    def _server_listen_loop(self) -> None:
        """Background thread accepting incoming connections from peer nodes."""
        self._server_sock.settimeout(0.5)
        while self._is_running:
            try:
                conn, _ = self._server_sock.accept()
            except socket.timeout:
                continue
            except Exception:
                break

            # Handle client connection in a separate worker thread
            client_thread = threading.Thread(
                target=self._handle_client_connection,
                args=(conn,),
                daemon=True,
            )
            client_thread.start()

    def _handle_client_connection(self, conn: socket.socket) -> None:
        """Handle a single incoming TCP sync connection."""
        conn.settimeout(self.timeout)
        try:
            # Step 1: Read 4-byte length prefix
            header_bytes = recv_exact(conn, 4)
            msg_length = struct.unpack("!I", header_bytes)[0]
            if msg_length > self.max_frame_size:
                raise FrameTooLargeError(
                    f"Frame size {msg_length} bytes exceeds maximum allowed limit {self.max_frame_size} bytes"
                )

            # Step 2: Read message payload
            payload_bytes = recv_exact(conn, msg_length)

            with self._lock:
                self._total_bytes_transferred += 4 + msg_length
                self._total_messages_sent += 1

            in_msg = TransportMessage.from_bytes(payload_bytes)

            # Step 3: Invoke node protocol handler
            response_msg: Optional[TransportMessage] = None
            if self.handler is not None:
                response_msg = self.handler(in_msg)

            # Step 4: Write framed response back to client if provided
            if response_msg is not None:
                out_bytes = response_msg.to_bytes()
                out_header = struct.pack("!I", len(out_bytes))
                conn.sendall(out_header + out_bytes)

                with self._lock:
                    self._total_bytes_transferred += 4 + len(out_bytes)
                    self._total_messages_sent += 1
            else:
                # Send 0-length frame indicating no response
                conn.sendall(struct.pack("!I", 0))

        except Exception:
            # Client disconnected or timed out
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def send(self, message: TransportMessage) -> Optional[TransportMessage]:
        """
        Send a framed TransportMessage to target peer over real TCP socket.
        Returns the parsed response or None if peer is unreachable / times out.
        """
        recipient_id = message.recipient_id
        if recipient_id not in self.peers:
            return None

        peer_host, peer_port = self.peers[recipient_id]

        client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_sock.settimeout(self.timeout)

        try:
            # Connect to peer's TCP server
            client_sock.connect((peer_host, peer_port))

            # Send 4-byte length prefix + payload
            out_bytes = message.to_bytes()
            header = struct.pack("!I", len(out_bytes))
            client_sock.sendall(header + out_bytes)

            with self._lock:
                self._total_bytes_transferred += 4 + len(out_bytes)
                self._total_messages_sent += 1

            # Read response
            resp_header = recv_exact(client_sock, 4)
            resp_len = struct.unpack("!I", resp_header)[0]
            if resp_len > self.max_frame_size:
                raise FrameTooLargeError(
                    f"Response frame size {resp_len} bytes exceeds maximum allowed limit {self.max_frame_size} bytes"
                )

            if resp_len == 0:
                return None

            resp_bytes = recv_exact(client_sock, resp_len)

            with self._lock:
                self._total_bytes_transferred += 4 + resp_len
                self._total_messages_sent += 1

            return TransportMessage.from_bytes(resp_bytes)

        except (socket.timeout, ConnectionRefusedError, ConnectionError, OSError):
            # Peer laptop is offline, sleeping, or out of Wi-Fi range
            return None
        finally:
            try:
                client_sock.close()
            except Exception:
                pass

    def get_stats(self) -> Dict[str, int]:
        """Return total bytes and messages moved across this TCP socket."""
        with self._lock:
            return {
                "total_bytes": self._total_bytes_transferred,
                "total_messages": self._total_messages_sent,
            }

    def reset_stats(self) -> None:
        """Reset byte statistics."""
        with self._lock:
            self._total_bytes_transferred = 0
            self._total_messages_sent = 0

    def close(self) -> None:
        """Shutdown the TCP server and release port."""
        self._is_running = False
        try:
            self._server_sock.close()
        except Exception:
            pass
        if self._server_thread.is_alive():
            self._server_thread.join(timeout=1.0)
