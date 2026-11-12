"""
Disaster Network Simulator Engine.

Orchestrates N nodes (N >= 3) undergoing random topological network splits,
offline workloads, conflicting edits, and transitive anti-entropy convergence.
"""

from __future__ import annotations
import random
from typing import List, Dict, Any, Optional
from transport.in_memory import InMemoryTransport
from sync.node import Node
from allocation.escrow import EscrowManager
from allocation.tokens import TokenManager
from .network import PartitionManager
from .workload import WorkloadGenerator


class SimulationReport:
    """Telemetry report produced by a simulation run."""

    def __init__(self) -> None:
        self.rounds_executed: int = 0
        self.events_created: int = 0
        self.sync_attempts: int = 0
        self.successful_syncs: int = 0
        self.blocked_syncs: int = 0
        self.total_bytes_transferred: int = 0
        self.converged: bool = False
        self.final_event_count: int = 0
        self.log_entries: List[str] = []

    def summary(self) -> str:
        return (
            f"Simulation Results: {'CONVERGED' if self.converged else 'DIVERGED'}\n"
            f"  * Rounds:            {self.rounds_executed}\n"
            f"  * Events Created:    {self.events_created}\n"
            f"  * Sync Attempts:     {self.sync_attempts} ({self.successful_syncs} ok, {self.blocked_syncs} blocked)\n"
            f"  * Total Wire Bytes:  {self.total_bytes_transferred} bytes\n"
            f"  * Final Event Count: {self.final_event_count} on each node"
        )


class DisasterSimulator:
    """
    Simulates a multi-node disaster coordination environment.
    """

    def __init__(
        self,
        node_ids: List[str],
        seed: Optional[int] = 42,
    ) -> None:
        if len(node_ids) < 3:
            raise ValueError("DisasterSimulator requires N >= 3 nodes")

        self.rng = random.Random(seed)
        self.transport = InMemoryTransport()
        self.node_ids = list(node_ids)
        self.nodes: Dict[str, Node] = {
            nid: Node(nid, ":memory:", self.transport)
            for nid in self.node_ids
        }
        self.partition_manager = PartitionManager(self.transport, self.node_ids)

        # Active entity registries for workload generator
        self.active_people: List[str] = []
        self.active_supplies: List[str] = []
        self.active_scarce_items: List[str] = []

        self.report = SimulationReport()

    def bootstrap_default_scenario(self) -> None:
        """
        Bootstrap baseline shared supplies and scarce items (e.g. boats, medical escrow).
        """
        # Node 0 creates a shared escrow pool of 120 antibiotics
        first_node = self.nodes[self.node_ids[0]]
        initial_quotas = {nid: 120 // len(self.node_ids) for nid in self.node_ids}

        EscrowManager.create_pool(
            node=first_node,
            supply_id="supply-antibiotics",
            item_name="Amoxicillin 500mg",
            total_quantity=120,
            initial_quotas=initial_quotas,
            unit="courses",
        )
        self.active_supplies.append("supply-antibiotics")

        # Node 0 registers the scarce rescue boat
        TokenManager.register_item(
            node=first_node,
            item_id="boat-titan",
            item_name="Titan Flood Rescue Boat #1",
            initial_holder_id=self.node_ids[0],
            location="Harbor Base",
        )
        self.active_scarce_items.append("boat-titan")

        # Sync bootstrap state to all nodes initially
        for nid in self.node_ids[1:]:
            first_node.sync_with(nid)

        self.transport.reset_stats()

    def step(self, partition_groups: Optional[List[List[str]]] = None) -> List[str]:
        """
        Execute one simulation step:
        1. Set network partition topology.
        2. Perform local operations on partitioned nodes.
        3. Attempt sync within connected clusters.
        """
        round_logs: List[str] = []
        self.report.rounds_executed += 1

        # Step 1: Partition
        if partition_groups is None:
            partition_groups = self.partition_manager.random_partition(self.rng)
        else:
            self.partition_manager.set_partitions(partition_groups)

        round_logs.append(f"Round {self.report.rounds_executed} Partition Topology: {partition_groups}")

        # Step 2: Random offline actions in each partition
        for nid in self.node_ids:
            node = self.nodes[nid]
            action_log = WorkloadGenerator.generate_random_action(
                node, self.rng, self.active_people, self.active_supplies, self.active_scarce_items
            )
            round_logs.append(f"  [Action] {action_log}")
            self.report.events_created += 1

        # Step 3: Attempt syncs between randomly chosen pairs
        pairs = []
        for i in range(len(self.node_ids)):
            for j in range(i + 1, len(self.node_ids)):
                pairs.append((self.node_ids[i], self.node_ids[j]))
        self.rng.shuffle(pairs)

        for n1, n2 in pairs[:len(self.node_ids)]:
            self.report.sync_attempts += 1
            stats = self.nodes[n1].sync_with(n2)
            if stats.success:
                self.report.successful_syncs += 1
                round_logs.append(f"  [Sync OK] {n1} <-> {n2} ({stats.total_bytes} B, sent {stats.events_sent}, recv {stats.events_received})")
            else:
                self.report.blocked_syncs += 1
                round_logs.append(f"  [Sync BLOCKED] {n1} <-> {n2} (partition cut)")

        self.report.log_entries.extend(round_logs)
        return round_logs

    def heal_and_converge(self, max_gossip_passes: int = 5) -> bool:
        """
        Heals the entire network and executes epidemic gossip passes until
        all nodes reach identical version vectors and verified identical state.
        """
        self.partition_manager.heal_all()

        for pass_num in range(max_gossip_passes):
            changed = False
            for i in range(len(self.node_ids)):
                for j in range(i + 1, len(self.node_ids)):
                    n1 = self.node_ids[i]
                    n2 = self.node_ids[j]
                    stats = self.nodes[n1].sync_with(n2)
                    if stats.events_sent > 0 or stats.events_received > 0:
                        changed = True

            # If an entire round across all pairs exchanged 0 events, network is fully converged!
            if not changed:
                break

        # Verification of state equivalence across all nodes
        first_state = self.nodes[self.node_ids[0]].get_state()
        first_vv = self.nodes[self.node_ids[0]].get_version_vector()
        first_count = self.nodes[self.node_ids[0]].store.count()

        is_converged = True
        for nid in self.node_ids[1:]:
            node = self.nodes[nid]
            if node.get_version_vector() != first_vv:
                is_converged = False
                break
            if node.get_state() != first_state:
                is_converged = False
                break

        self.report.converged = is_converged
        self.report.final_event_count = first_count
        self.report.total_bytes_transferred = self.transport.get_stats()["total_bytes"]
        return is_converged

    def close(self) -> None:
        """Clean up all nodes."""
        for node in self.nodes.values():
            node.close()
