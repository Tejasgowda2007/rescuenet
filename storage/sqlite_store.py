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
import threading
import zlib
from typing import Dict, List, Optional, Iterable
from events.event import Event
try:
    from validation.schema import validate_event as _validate_event
except Exception:  # pragma: no cover
    _validate_event = None


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
        try:
            self.conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30.0)
        except sqlite3.OperationalError:
            # Fallback to in-memory store if path is unwritable
            self.db_path = ":memory:"
            self.conn = sqlite3.connect(":memory:", check_same_thread=False, timeout=30.0)
        self.conn.row_factory = sqlite3.Row
        # Durability + concurrency hardening
        self._lock = threading.RLock()
        try:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=NORMAL")
            self.conn.execute("PRAGMA busy_timeout=30000")
            self.conn.execute("PRAGMA foreign_keys=ON")
            self.conn.execute("PRAGMA temp_store=MEMORY")
            self.conn.commit()
        except sqlite3.Error:
            pass
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
        with self._lock:
            return self._append_impl(event)

    def append_many(self, events: Iterable[Event]) -> int:
        with self._lock:
            return self._append_many_impl(events)

    def _append_impl(self, event: Event) -> bool:
        """
        Append a single event to the local log.
        :return: True if the event was newly added, False if it was already present (idempotent).
        :raises EquivocationError: If the node already logged a DIFFERENT event with the same counter.
        """
        # Schema validation (offline, no network)
        if _validate_event is not None:
            try:
                _validate_event(event)
            except Exception as e:
                raise StorageError(f"validation failed: {e}") from e
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

    def _append_many_impl(self, events: Iterable[Event]) -> int:
        """
        Append multiple events within a single transaction.
        Returns count of newly inserted events.
        """
        added_count = 0
        with self.conn:
            for ev in events:
                if self._append_impl(ev):
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

    def get_contiguous_high_water_mark(self, node_id: str) -> int:
        """
        Compute the Contiguous High-Water Mark (CHWM) for a given node_id.
        Starting from counter 1, returns the highest consecutive counter logged with zero missing gaps.
        Returns 0 if counter 1 is missing or no events exist for this node.
        """
        cur = self.conn.cursor()
        cur.execute(
            "SELECT counter FROM events WHERE node_id = ? ORDER BY counter ASC",
            (node_id,)
        )
        rows = cur.fetchall()
        if not rows:
            return 0
        expected = 1
        for row in rows:
            c = row["counter"]
            if c == expected:
                expected += 1
            elif c > expected:
                break
        return expected - 1

    def get_max_counter(self, node_id: str) -> int:
        """Return the highest counter seen for this node (may exceed CHWM if gaps exist)."""
        cur = self.conn.cursor()
        cur.execute("SELECT MAX(counter) as max_c FROM events WHERE node_id = ?", (node_id,))
        row = cur.fetchone()
        return int(row["max_c"]) if row and row["max_c"] is not None else 0

    def get_max_version_vector(self) -> Dict[str, int]:
        """Compute the raw maximum counter version vector {node_id: max_counter}."""
        cur = self.conn.cursor()
        cur.execute("""
            SELECT node_id, MAX(counter) as max_counter
            FROM events
            GROUP BY node_id
        """)
        return {row["node_id"]: int(row["max_counter"]) for row in cur.fetchall()}

    def get_version_vector(self) -> Dict[str, int]:
        """
        Compute the local version vector using Contiguous High-Water Marks (CHWM).
        Design Decision:
        Using CHWM guarantees that if intermediate events were dropped or received
        out-of-order, peer nodes will know to re-send the missing gap events rather
        than assuming the local node has all preceding events.
        """
        cur = self.conn.cursor()
        cur.execute("SELECT DISTINCT node_id FROM events")
        node_ids = [row["node_id"] for row in cur.fetchall()]
        return {nid: self.get_contiguous_high_water_mark(nid) for nid in node_ids}

    def get_missing_counter_ranges(self, node_id: str) -> List[tuple[int, int]]:
        """
        Find all missing counter intervals for a given node_id between 1 and MAX(counter).
        Returns list of (start_counter, end_counter) inclusive tuples.
        """
        cur = self.conn.cursor()
        cur.execute(
            "SELECT counter FROM events WHERE node_id = ? ORDER BY counter ASC",
            (node_id,)
        )
        rows = cur.fetchall()
        if not rows:
            return []

        gaps: List[tuple[int, int]] = []
        expected = 1
        for row in rows:
            c = row["counter"]
            if c > expected:
                gaps.append((expected, c - 1))
                expected = c + 1
            elif c == expected:
                expected += 1
        return gaps

    def get_all_gaps(self) -> Dict[str, List[tuple[int, int]]]:
        """Return missing counter ranges across all known origin nodes."""
        cur = self.conn.cursor()
        cur.execute("SELECT DISTINCT node_id FROM events")
        node_ids = [row["node_id"] for row in cur.fetchall()]
        all_gaps: Dict[str, List[tuple[int, int]]] = {}
        for nid in node_ids:
            g = self.get_missing_counter_ranges(nid)
            if g:
                all_gaps[nid] = g
        return all_gaps

    def get_events_for_counter_ranges(
        self,
        ranges: Dict[str, List[tuple[int, int]]],
    ) -> List[Event]:
        """
        Retrieve events matching explicit missing counter ranges for specific origin nodes.
        :param ranges: {node_id: [(start, end), ...]}
        """
        if not ranges:
            return []

        matched_events: List[Event] = []
        for nid, intervals in ranges.items():
            for start_c, end_c in intervals:
                cur = self.conn.cursor()
                cur.execute("""
                    SELECT event_id, node_id, counter, timestamp, entity_type, entity_id,
                           operation, payload_json, signature
                    FROM events
                    WHERE node_id = ? AND counter >= ? AND counter <= ?
                    ORDER BY counter ASC
                """, (nid, start_c, end_c))
                for row in cur.fetchall():
                    matched_events.append(self._row_to_event(row))
        return matched_events

    def get_events_since(
        self,
        peer_version_vector: Dict[str, int],
        peer_gaps: Optional[Dict[str, List[tuple[int, int]]]] = None,
    ) -> List[Event]:
        """
        Returns all events that the peer has NOT yet seen.
        Design Decision:
        1. For every node_id in our database, we return events where counter > peer's CHWM.
        2. If the peer explicitly reported gap ranges, we include those missing events too.
        Deduplicated by event_id and canonically sorted.
        """
        seen_ids = set()
        missing = []

        all_events = self.get_all_events()
        for ev in all_events:
            peer_counter = peer_version_vector.get(ev.node_id, 0)
            if ev.counter > peer_counter:
                if ev.event_id not in seen_ids:
                    seen_ids.add(ev.event_id)
                    missing.append(ev)

        if peer_gaps:
            gap_events = self.get_events_for_counter_ranges(peer_gaps)
            for ev in gap_events:
                if ev.event_id not in seen_ids:
                    seen_ids.add(ev.event_id)
                    missing.append(ev)

        return sorted(missing, key=lambda e: (e.timestamp, e.node_id, e.counter))

    def query_events(
        self,
        entity_type: Optional[str] = None,
        node_id: Optional[str] = None,
        since_timestamp: Optional[float] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[List[Event], int]:
        """
        Paginated query for events with optional filtering.
        Returns (events_page, total_matching_count).
        """
        where_clauses = []
        params: List[Any] = []

        if entity_type:
            where_clauses.append("entity_type = ?")
            params.append(entity_type)
        if node_id:
            where_clauses.append("node_id = ?")
            params.append(node_id)
        if since_timestamp is not None:
            where_clauses.append("timestamp >= ?")
            params.append(since_timestamp)

        where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        cur = self.conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM events{where_sql}", params)
        total_count = cur.fetchone()[0]

        sql = f"""
            SELECT event_id, node_id, counter, timestamp, entity_type, entity_id,
                   operation, payload_json, signature
            FROM events{where_sql}
            ORDER BY timestamp DESC, node_id ASC, counter DESC
            LIMIT ? OFFSET ?
        """
        cur.execute(sql, params + [limit, offset])
        events = [self._row_to_event(row) for row in cur.fetchall()]
        return events, total_count

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


# Thread-safety: wrap read/close methods with the store lock (WAL-friendly).
_THREAD_SAFE_METHODS = (
    "get_event", "get_all_events", "get_events_for_entity",
    "get_version_vector", "get_contiguous_high_water_mark", "get_max_counter",
    "get_max_version_vector", "get_missing_counter_ranges", "get_all_gaps",
    "get_events_for_counter_ranges", "get_events_since", "query_events",
    "count", "close",
)
for _name in _THREAD_SAFE_METHODS:
    _orig = getattr(SQLiteEventStore, _name)

    def _make(orig):
        def _wrapped(self, *args, **kwargs):
            with self._lock:
                return orig(self, *args, **kwargs)
        _wrapped.__name__ = orig.__name__
        _wrapped.__doc__ = orig.__doc__
        return _wrapped

    setattr(SQLiteEventStore, _name, _make(_orig))
