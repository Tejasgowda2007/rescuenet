"""
FieldMesh Packet, Frame, and Fragmentation Engine.

Handles:
- Constrained radio packet headers, prioritization, and wire size calculation.
- LoRa MTU fragmentation and reassembly of large event deltas.
- Duplicate message suppression and Time-To-Live (TTL) loop prevention.
"""

from __future__ import annotations
import uuid
import time
import json
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict


# Priority classes
PRIORITY_SOS = 0         # High-priority emergency SOS broadcast
PRIORITY_SYNC = 1        # Anti-entropy state delta sync
PRIORITY_TELEMETRY = 2   # Heartbeats, routing probes, battery updates

# Maximum Transmission Units (MTU)
LORA_DEFAULT_MTU = 180   # Safe payload boundary under SF9-SF11
P2P_DEFAULT_MTU = 1400   # Directional microwave link MTU


@dataclass
class Packet:
    packet_id: str
    source_id: str
    destination_id: str        # Specific node_id or "BROADCAST"
    prev_hop: str
    next_hop: str
    msg_type: str              # "SOS", "SYNC_REQ", "SYNC_RESP", "EVENT_DELTA", "ACK", "PROBE"
    priority: int              # PRIORITY_SOS, PRIORITY_SYNC, PRIORITY_TELEMETRY
    payload: Dict[str, Any]
    ttl: int = 8
    hop_count: int = 0
    route_history: List[str] = field(default_factory=list)
    fragment_index: int = 0
    total_fragments: int = 1
    original_msg_id: str = ""
    timestamp: float = field(default_factory=time.time)
    retry_count: int = 0

    def __post_init__(self):
        if not self.packet_id:
            self.packet_id = f"pkt-{uuid.uuid4().hex[:10]}"
        if not self.original_msg_id:
            self.original_msg_id = self.packet_id
        if not self.route_history and self.source_id:
            self.route_history = [self.source_id]

    def wire_byte_size(self) -> int:
        """Calculate approximate physical wire size in bytes (headers + JSON payload)."""
        # 16-byte fixed radio header: [2B sync, 1B type, 1B priority, 4B msg_id, 1B src, 1B dst, 1B ttl, 1B hop, 2B frag_info, 2B crc]
        header_bytes = 16
        payload_bytes = len(json.dumps(self.payload, separators=(",", ":")).encode("utf-8"))
        return header_bytes + payload_bytes

    def create_forward_copy(self, current_node: str, next_hop: str) -> Optional[Packet]:
        """Produce next-hop packet decrementing TTL and recording route history."""
        if self.ttl <= 1 or current_node in self.route_history:
            # Expired or loop detected!
            return None

        new_history = list(self.route_history)
        new_history.append(current_node)

        return Packet(
            packet_id=self.packet_id,
            source_id=self.source_id,
            destination_id=self.destination_id,
            prev_hop=current_node,
            next_hop=next_hop,
            msg_type=self.msg_type,
            priority=self.priority,
            payload=self.payload,
            ttl=self.ttl - 1,
            hop_count=self.hop_count + 1,
            route_history=new_history,
            fragment_index=self.fragment_index,
            total_fragments=self.total_fragments,
            original_msg_id=self.original_msg_id,
            timestamp=self.timestamp,
            retry_count=self.retry_count,
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PacketFragmentationManager:
    """
    Splits large payload objects into multiple MTU-sized packets and reassembles them.
    Prevents overflowing constrained LoRa channel bandwidths.
    """

    def __init__(self, mtu_bytes: int = LORA_DEFAULT_MTU) -> None:
        self.mtu_bytes = mtu_bytes
        # Incomplete reassembly buffers: {original_msg_id: {frag_idx: payload_dict, '_total': N, '_created': ts}}
        self._buffers: Dict[str, Dict[str, Any]] = {}

    def fragment_message(
        self,
        source_id: str,
        destination_id: str,
        msg_type: str,
        full_payload: Dict[str, Any],
        priority: int = PRIORITY_SYNC,
    ) -> List[Packet]:
        """
        Serialize payload to JSON and fragment into packets if size > MTU.
        """
        raw_json = json.dumps(full_payload, separators=(",", ":"))
        total_len = len(raw_json.encode("utf-8"))

        # Overhead budget for framing
        effective_chunk_size = max(40, self.mtu_bytes - 32)

        if total_len <= effective_chunk_size:
            # Single packet suffices
            pkt = Packet(
                packet_id=f"pkt-{uuid.uuid4().hex[:10]}",
                source_id=source_id,
                destination_id=destination_id,
                prev_hop=source_id,
                next_hop="",
                msg_type=msg_type,
                priority=priority,
                payload=full_payload,
                fragment_index=0,
                total_fragments=1,
            )
            return [pkt]

        # Multi-fragment split
        chunks = []
        raw_bytes = raw_json.encode("utf-8")
        for i in range(0, len(raw_bytes), effective_chunk_size):
            chunks.append(raw_bytes[i:i + effective_chunk_size].decode("utf-8", errors="ignore"))

        total_frags = len(chunks)
        orig_id = f"msg-{uuid.uuid4().hex[:10]}"
        packets = []

        for idx, chunk_str in enumerate(chunks):
            pkt = Packet(
                packet_id=f"{orig_id}-f{idx}",
                source_id=source_id,
                destination_id=destination_id,
                prev_hop=source_id,
                next_hop="",
                msg_type=msg_type,
                priority=priority,
                payload={"_frag_data": chunk_str},
                fragment_index=idx,
                total_fragments=total_frags,
                original_msg_id=orig_id,
            )
            packets.append(pkt)

        return packets

    def receive_fragment(self, packet: Packet) -> Optional[Dict[str, Any]]:
        """
        Ingest a packet fragment.
        Returns the reassembled full payload if all fragments have arrived, else None.
        """
        if packet.total_fragments <= 1:
            return packet.payload

        orig_id = packet.original_msg_id
        if orig_id not in self._buffers:
            self._buffers[orig_id] = {
                "_total": packet.total_fragments,
                "_created": time.time(),
                "fragments": {},
            }

        buf = self._buffers[orig_id]
        buf["fragments"][packet.fragment_index] = packet.payload.get("_frag_data", "")

        # Check completeness
        if len(buf["fragments"]) == buf["_total"]:
            # Combine in order
            ordered_parts = [buf["fragments"][i] for i in range(buf["_total"])]
            assembled_json = "".join(ordered_parts)
            del self._buffers[orig_id]
            try:
                return json.loads(assembled_json)
            except Exception:
                return {"_raw": assembled_json}

        return None

    def prune_stale_buffers(self, timeout_sec: float = 60.0) -> int:
        """Remove incomplete fragment sets older than timeout_sec."""
        now = time.time()
        stale_keys = [
            k for k, v in self._buffers.items()
            if now - v["_created"] > timeout_sec
        ]
        for k in stale_keys:
            del self._buffers[k]
        return len(stale_keys)
