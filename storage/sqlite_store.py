"""
SQLite-backed Append-Only Event Store.

Key Invariants:
1. Append-Only: No UPDATE or DELETE operations exist on the events table.
2. Idempotency: Appending the same event twice succeeds without duplicating data.
3. Anti-Equivocation: A node cannot issue two distinct events with the same counter.
4. Version Vectors: Can compute current (node_id -> max_counter) vector instantly via index.
"""

from __future__ import annotations
import sqlite3
import json
from typing import Dict, List, Optional, Iterable
from events.event import Event


class StorageError(Exception):
    """Base exception for storage errors."""
    pass


class EquivocationError(StorageError):
    """Raised when a node produces conflicting events with the same sequence counter."""
    pass


class SQLiteEventStore:
    """
    Append-only storage engine for a single disaster coordination node.
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        """
        Initialize the SQLite store.
        :param db_path: Path to SQLite file, or ':memory:' for transient/simulated nodes.
        """
        self.db_path = db_path
        # Design Decision: check_same_thread=False allows sharing across simulator tasks or UI threads
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        """
        Create tables and indices if they do not exist.
        Design Decision:
        - Primary Key is event_id (content hash), ensuring automatic deduplication.
        - UNIQUE(node_id, counter) constraint physically enforces that a single device's
          logical clock cannot fork into two different realities.
        - Composite index (timestamp, node_id, counter) provides canonical, deterministic sorting.
        """
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    node_id TEXT NOT NULL,
                    counter INTEGER NOT NULL,
                    timestamp REAL NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    signature TEXT NOT NULL DEFAULT '',
                    UNIQUE(node_id, counter)
                );
            """)
            self.conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_node_counter ON events(node_id, counter);
            """)
            self.conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_entity ON events(entity_type, entity_id);
            """)
            self.conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_canonical_order ON events(timestamp, node_id, counter);
            """)

    def append(self, event: Event) -> bool:
        """
        Append a single event to the local log.
        :return: True if the event was newly added, False if it was already present (idempotent).
        :raises EquivocationError: If the node already logged a DIFFERENT event with the same counter.
        """
        # Step 1: Check if the exact event already exists (deduplication)
        cur = self.conn.cursor()
        cur.execute("SELECT event_id FROM events WHERE event_id = ?", (event.event_id,))
        if cur.fetchone() is not None:
            return False  # Already have this exact event; safe no-op

        # Step 2: Check if this node has already issued a DIFFERENT event with this counter
        cur.execute(
            "SELECT event_id FROM events WHERE node_id = ? AND counter = ?",
            (event.node_id, event.counter)
        )
        row = cur.fetchone()
        if row is not None and row["event_id"] != event.event_id:
            raise EquivocationError(
                f"Equivocation detected for node '{event.node_id}' at counter {event.counter}: "
                f"existing event {row['event_id']} != new event {event.event_id}"
            )

        # Step 3: Insert new event
        try:
            with self.conn:
                self.conn.execute("""
                    INSERT INTO events (
                        event_id, node_id, counter, timestamp,
                        entity_type, entity_id, operation,
                        payload_json, signature
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    event.event_id,
                    event.node_id,
                    event.counter,
                    event.timestamp,
                    event.entity_type,
                    event.entity_id,
                    event.operation,
                    json.dumps(event.payload, sort_keys=True),
                    event.signature,
                ))
            return True
        except sqlite3.IntegrityError as e:
            # Race condition safeguard in case another thread inserted concurrently
            cur.execute("SELECT event_id FROM events WHERE event_id = ?", (event.event_id,))
            if cur.fetchone() is not None:
                return False
            raise StorageError(f"Database integrity error: {e}") from e

    def append_many(self, events: Iterable[Event]) -> int:
        """
        Append multiple events within a single transaction.
        Returns count of newly inserted events.
        """
        added_count = 0
        with self.conn:
            for ev in events:
                if self.append(ev):
                    added_count += 1
        return added_count

    def get_event(self, event_id: str) -> Optional[Event]:
        """Fetch a specific event by its ID."""
        cur = self.conn.cursor()
        cur.execute("""
            SELECT event_id, node_id, counter, timestamp, entity_type, entity_id,
                   operation, payload_json, signature
            FROM events WHERE event_id = ?
        """, (event_id,))
        row = cur.fetchone()
        if not row:
            return None
        return self._row_to_event(row)

    def get_all_events(self) -> List[Event]:
        """
        Retrieve all events ordered deterministically.
        Design Decision:
        Ordering by (timestamp, node_id, counter) ensures that any node replaying
        this log in batch produces the exact same sequence of state transitions.
        """
        cur = self.conn.cursor()
        cur.execute("""
            SELECT event_id, node_id, counter, timestamp, entity_type, entity_id,
                   operation, payload_json, signature
            FROM events
            ORDER BY timestamp ASC, node_id ASC, counter ASC
        """)
        return [self._row_to_event(row) for row in cur.fetchall()]

    def get_events_for_entity(self, entity_type: str, entity_id: str) -> List[Event]:
        """Retrieve full audit history for a single entity."""
        cur = self.conn.cursor()
        cur.execute("""
            SELECT event_id, node_id, counter, timestamp, entity_type, entity_id,
                   operation, payload_json, signature
            FROM events
            WHERE entity_type = ? AND entity_id = ?
            ORDER BY timestamp ASC, node_id ASC, counter ASC
        """, (entity_type, entity_id))
        return [self._row_to_event(row) for row in cur.fetchall()]

    def get_version_vector(self) -> Dict[str, int]:
        """
        Compute the local version vector: {node_id: max_counter_seen}.
        Design Decision:
        Version vectors summarize what this node knows about every peer in O(N_peers) time.
        Used directly in anti-entropy sync (Stage 2).
        """
        cur = self.conn.cursor()
        cur.execute("""
            SELECT node_id, MAX(counter) as max_counter
            FROM events
            GROUP BY node_id
        """)
        return {row["node_id"]: int(row["max_counter"]) for row in cur.fetchall()}

    def get_events_since(self, peer_version_vector: Dict[str, int]) -> List[Event]:
        """
        Returns all events that the peer has NOT yet seen.
        Design Decision:
        For every node_id in our database, we return events where counter > peer's vector.
        If the peer has never seen node_id (counter 0), we return all events from node_id.
        This guarantees small sync payloads (Requirement 4).
        """
        all_events = self.get_all_events()
        missing = []
        for ev in all_events:
            peer_counter = peer_version_vector.get(ev.node_id, 0)
            if ev.counter > peer_counter:
                missing.append(ev)
        return missing

    def count(self) -> int:
        """Total number of events logged."""
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM events")
        return cur.fetchone()[0]

    def close(self) -> None:
        """Close SQLite database connection."""
        self.conn.close()

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> Event:
        """Helper to convert a database row back into an immutable Event object."""
        return Event(
            event_id=row["event_id"],
            node_id=row["node_id"],
            counter=row["counter"],
            timestamp=row["timestamp"],
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            operation=row["operation"],
            payload=json.loads(row["payload_json"]),
            signature=row["signature"],
        )
