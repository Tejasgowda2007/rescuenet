"""
RescueNet Local Network Peer Discovery via UDP Broadcast Beacons.

Enables zero-configuration peer discovery for laptops connecting to the same
Wi-Fi router, mobile hotspot, or ad-hoc wireless network with NO internet access.

Protocol:
- Periodic UDP beacon broadcast on port 8002 (default).
- Beacon payload: Canonical JSON with cluster name, sender node ID, TCP sync port, and web port.
- Receiver validates that sender is in the trusted peer manifest before adding to route table.
- Gracefully falls back to manual peer IP configuration if UDP broadcast is disabled by router AP isolation.
"""

from __future__ import annotations
import json
import socket
import threading
import time
from typing import Dict, Any, Optional, Callable, List, Tuple


DEFAULT_DISCOVERY_PORT = 8002
DEFAULT_BEACON_INTERVAL = 2.5
DEFAULT_PEER_TIMEOUT = 12.0
CLUSTER_ID = "RESCUENET-OFFLINE-MESH"


class PeerDiscoveryBeacon:
    """
    Broadcasts and listens for local subnet peer discovery beacons.
    """

    def __init__(
        self,
        node_id: str,
        tcp_port: int,
        web_port: int = 8000,
        broadcast_port: int = DEFAULT_DISCOVERY_PORT,
        beacon_interval: float = DEFAULT_BEACON_INTERVAL,
        peer_timeout: float = DEFAULT_PEER_TIMEOUT,
        on_peer_discovered: Optional[Callable[[str, str, int, int], None]] = None,
        on_peer_lost: Optional[Callable[[str], None]] = None,
        trusted_peer_ids: Optional[List[str]] = None,
    ) -> None:
        self.node_id = node_id
        self.tcp_port = tcp_port
        self.web_port = web_port
        self.broadcast_port = broadcast_port
        self.beacon_interval = beacon_interval
        self.peer_timeout = peer_timeout
        self.on_peer_discovered = on_peer_discovered
        self.on_peer_lost = on_peer_lost
        self.trusted_peer_ids = set(trusted_peer_ids) if trusted_peer_ids else None

        # Discovered peers: {peer_id: {"host": ip, "tcp_port": port, "web_port": port, "last_seen": ts}}
        self.discovered_peers: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._is_running = False
        self._threads: List[threading.Thread] = []

        # Sockets
        self._broadcast_sock: Optional[socket.socket] = None
        self._listen_sock: Optional[socket.socket] = None

    def start(self) -> None:
        """Start beacon broadcasting and listening daemon threads."""
        if self._is_running:
            return
        self._is_running = True

        # 1. Setup UDP broadcast socket
        try:
            self._broadcast_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._broadcast_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self._broadcast_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except Exception:
            self._broadcast_sock = None

        # 2. Setup UDP listener socket
        try:
            self._listen_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._listen_sock.bind(("0.0.0.0", self.broadcast_port))
            self._listen_sock.settimeout(1.0)
        except Exception:
            self._listen_sock = None

        # 3. Launch worker threads
        if self._broadcast_sock:
            t_send = threading.Thread(
                target=self._broadcast_loop,
                name=f"PeerDiscovery-Sender-{self.node_id}",
                daemon=True,
            )
            t_send.start()
            self._threads.append(t_send)

        if self._listen_sock:
            t_recv = threading.Thread(
                target=self._listen_loop,
                name=f"PeerDiscovery-Listener-{self.node_id}",
                daemon=True,
            )
            t_recv.start()
            self._threads.append(t_recv)

        t_mon = threading.Thread(
            target=self._monitor_loop,
            name=f"PeerDiscovery-Monitor-{self.node_id}",
            daemon=True,
        )
        t_mon.start()
        self._threads.append(t_mon)

    def stop(self) -> None:
        """Stop discovery threads and close sockets."""
        self._is_running = False
        if self._broadcast_sock:
            try:
                self._broadcast_sock.close()
            except Exception:
                pass
        if self._listen_sock:
            try:
                self._listen_sock.close()
            except Exception:
                pass

    def _broadcast_loop(self) -> None:
        """Periodically broadcast discovery beacon to local subnet."""
        while self._is_running:
            try:
                payload = {
                    "cluster": CLUSTER_ID,
                    "node_id": self.node_id,
                    "tcp_port": self.tcp_port,
                    "web_port": self.web_port,
                    "ts": time.time(),
                }
                raw = json.dumps(payload, sort_keys=True).encode("utf-8")
                # Send to standard broadcast 255.255.255.255
                if self._broadcast_sock:
                    try:
                        self._broadcast_sock.sendto(raw, ("<broadcast>", self.broadcast_port))
                    except Exception:
                        try:
                            self._broadcast_sock.sendto(raw, ("255.255.255.255", self.broadcast_port))
                        except Exception:
                            pass
            except Exception:
                pass
            time.sleep(self.beacon_interval)

    def _listen_loop(self) -> None:
        """Listen for incoming peer discovery beacons from other laptops."""
        while self._is_running:
            if not self._listen_sock:
                break
            try:
                data, addr = self._listen_sock.recvfrom(2048)
                sender_ip = addr[0]
                beacon = json.loads(data.decode("utf-8"))

                # Validate cluster ID
                if beacon.get("cluster") != CLUSTER_ID:
                    continue

                peer_id = beacon.get("node_id")
                tcp_port = int(beacon.get("tcp_port", 0))
                web_port = int(beacon.get("web_port", 0))

                # Ignore our own beacon
                if not peer_id or peer_id == self.node_id:
                    continue

                # Filter by trusted manifest if configured
                if self.trusted_peer_ids is not None and peer_id not in self.trusted_peer_ids:
                    continue

                # Record or update peer
                is_new = False
                with self._lock:
                    if peer_id not in self.discovered_peers:
                        is_new = True
                    self.discovered_peers[peer_id] = {
                        "host": sender_ip,
                        "tcp_port": tcp_port,
                        "web_port": web_port,
                        "last_seen": time.time(),
                    }

                # Callback on new peer discovery
                if is_new and self.on_peer_discovered:
                    try:
                        self.on_peer_discovered(peer_id, sender_ip, tcp_port, web_port)
                    except Exception:
                        pass

            except socket.timeout:
                continue
            except Exception:
                pass

    def _monitor_loop(self) -> None:
        """Monitor peer freshness and fire callbacks when a peer drops offline."""
        while self._is_running:
            now = time.time()
            lost_peers = []
            with self._lock:
                for peer_id, info in list(self.discovered_peers.items()):
                    if now - info["last_seen"] > self.peer_timeout:
                        lost_peers.append(peer_id)
                        del self.discovered_peers[peer_id]

            for peer_id in lost_peers:
                if self.on_peer_lost:
                    try:
                        self.on_peer_lost(peer_id)
                    except Exception:
                        pass

            time.sleep(2.0)

    def get_discovered_peers(self) -> Dict[str, Dict[str, Any]]:
        """Return snapshot of active discovered peers."""
        with self._lock:
            return dict(self.discovered_peers)
