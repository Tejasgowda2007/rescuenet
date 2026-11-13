"""
RescueNet Autonomous Anti-Entropy Gossip Synchronization Daemon.

Runs in the background of each node to periodically sync with registered peers,
detect network partitions and link reconnections, recover missing gaps,
and propagate events transitively across multi-hop offline mesh networks.
"""

from __future__ import annotations
import threading
import time
from typing import Dict, Any, List, Optional, Callable
from sync.node import Node
from sync.messages import SyncStats


class PeerHealthStatus:
    """Tracks connection health and telemetry for an individual peer."""

    def __init__(self, peer_id: str) -> None:
        self.peer_id = peer_id
        self.status: str = "INITIALIZING"  # INITIALIZING, ONLINE, UNREACHABLE
        self.last_sync_time: float = 0.0
        self.last_attempt_time: float = 0.0
        self.last_error: Optional[str] = None
        self.consecutive_failures: int = 0
        self.total_events_sent: int = 0
        self.total_events_received: int = 0
        self.total_bytes_transferred: int = 0
        self.last_latency_ms: float = 0.0

    def record_success(self, stats: SyncStats, latency_ms: float) -> None:
        was_offline = (self.status == "UNREACHABLE")
        self.status = "ONLINE"
        self.last_sync_time = time.time()
        self.last_attempt_time = self.last_sync_time
        self.last_error = None
        self.consecutive_failures = 0
        self.total_events_sent += stats.events_sent
        self.total_events_received += stats.events_received
        self.total_bytes_transferred += stats.total_bytes
        self.last_latency_ms = latency_ms

    def record_failure(self, error: str) -> None:
        self.status = "UNREACHABLE"
        self.last_attempt_time = time.time()
        self.last_error = error
        self.consecutive_failures += 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "peer_id": self.peer_id,
            "status": self.status,
            "last_sync_time": self.last_sync_time,
            "last_attempt_time": self.last_attempt_time,
            "last_error": self.last_error,
            "consecutive_failures": self.consecutive_failures,
            "total_events_sent": self.total_events_sent,
            "total_events_received": self.total_events_received,
            "total_bytes_transferred": self.total_bytes_transferred,
            "last_latency_ms": round(self.last_latency_ms, 2),
        }


class GossipSyncDaemon:
    """
    Autonomous anti-entropy background synchronization daemon.
    """

    def __init__(
        self,
        node: Node,
        interval_sec: float = 3.0,
        peers: Optional[List[str]] = None,
        on_sync_callback: Optional[Callable[[str, SyncStats], None]] = None,
    ) -> None:
        self.node = node
        self.interval_sec = interval_sec
        self.configured_peers: List[str] = list(peers) if peers else []
        self.on_sync_callback = on_sync_callback

        self._peer_health: Dict[str, PeerHealthStatus] = {}
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._is_running = False

        # Initialize health tracker for configured peers
        for p in self.configured_peers:
            self._peer_health[p] = PeerHealthStatus(p)

    def add_peer(self, peer_id: str) -> None:
        """Register a new peer to be gossiped with."""
        with self._lock:
            if peer_id not in self.configured_peers:
                self.configured_peers.append(peer_id)
            if peer_id not in self._peer_health:
                self._peer_health[peer_id] = PeerHealthStatus(peer_id)

    def remove_peer(self, peer_id: str) -> None:
        """Unregister a peer from gossip."""
        with self._lock:
            if peer_id in self.configured_peers:
                self.configured_peers.remove(peer_id)

    def start(self) -> None:
        """Start the background gossip worker thread."""
        with self._lock:
            if self._is_running:
                return
            self._is_running = True
            self._stop_event.clear()
            self._wake_event.clear()
            self._thread = threading.Thread(
                target=self._gossip_loop,
                name=f"GossipDaemon-{self.node.node_id}",
                daemon=True,
            )
            self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        """Stop the background gossip worker cleanly."""
        with self._lock:
            if not self._is_running:
                return
            self._is_running = False
            self._stop_event.set()
            self._wake_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def trigger_now(self, target_peer_id: Optional[str] = None) -> List[SyncStats]:
        """
        Immediately perform an anti-entropy sync cycle without waiting for timer.
        """
        return self._sync_cycle(target_peer_id)

    def wake_up(self) -> None:
        """
        Wake up the gossip worker thread immediately to push new local updates or
        react to newly discovered peers with zero latency.
        """
        self._wake_event.set()

    def get_peer_health(self) -> Dict[str, Dict[str, Any]]:
        """Return the health dictionary for all monitored peers."""
        with self._lock:
            return {pid: ph.to_dict() for pid, ph in self._peer_health.items()}

    def _get_active_peers(self) -> List[str]:
        """Collect all peers from configured list and attached transport directory."""
        with self._lock:
            peers_set = set(self.configured_peers)
            if self.node.transport is not None and hasattr(self.node.transport, "peers"):
                for p in self.node.transport.peers.keys():
                    peers_set.add(p)
            for p in peers_set:
                if p not in self._peer_health:
                    self._peer_health[p] = PeerHealthStatus(p)
            return [p for p in peers_set if p != self.node.node_id]

    def _sync_cycle(self, target_peer_id: Optional[str] = None) -> List[SyncStats]:
        """Run one round of anti-entropy sync against peers."""
        targets = [target_peer_id] if target_peer_id else self._get_active_peers()
        results: List[SyncStats] = []

        for peer_id in targets:
            if peer_id == self.node.node_id:
                continue

            with self._lock:
                if peer_id not in self._peer_health:
                    self._peer_health[peer_id] = PeerHealthStatus(peer_id)
                health = self._peer_health[peer_id]

            t_start = time.time()
            try:
                stats = self.node.sync_with(peer_id)
                latency_ms = (time.time() - t_start) * 1000.0

                if stats.success:
                    with self._lock:
                        health.record_success(stats, latency_ms)
                else:
                    err = stats.error or "Sync failed"
                    with self._lock:
                        health.record_failure(err)

                results.append(stats)

                if self.on_sync_callback:
                    try:
                        self.on_sync_callback(peer_id, stats)
                    except Exception:
                        pass

            except Exception as e:
                with self._lock:
                    health.record_failure(str(e))

        return results

    def _gossip_loop(self) -> None:
        """Main loop executed by background worker thread."""
        while not self._stop_event.is_set():
            # Run one sync cycle
            self._sync_cycle()

            # Wait for next interval or explicit wakeup
            self._wake_event.wait(timeout=self.interval_sec)
            self._wake_event.clear()
