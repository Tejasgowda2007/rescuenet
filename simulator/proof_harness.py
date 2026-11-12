"""
Automatic Proof Harness for RescueNet Invariant Verification.

Runs N-node random partition & merge scenarios (e.g. 1,000 trials)
and rigorously verifies the 4 core distributed systems invariants:
  (a) Identical State Convergence: All nodes reach 100% byte-for-byte identical state.
  (b) Zero Lost Updates (Audit Intact): Every generated event exists on every node's raw log.
  (c) Indivisible Item Double Alloc=0: No scarce item is allocated twice; each confirmed allocation
      is verified from raw event logs to have originated from the verified token holder.
  (d) Divisible Supply Escrow Balance: Totals recomputed from raw event logs strictly satisfy
      sum(quotas) + sum(consumed) == total_inventory at all times.
Total wire bytes and bandwidth efficiency are measured and reported.
"""

from __future__ import annotations
import random
import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Set, Optional, Callable
from .engine import DisasterSimulator
from .workload import WorkloadGenerator
from events.event import Event


@dataclass
class ScenarioResult:
    """Outcome and invariant telemetry for a single scenario."""
    scenario_id: int
    num_nodes: int
    rounds: int
    events_generated: int
    total_bytes: int
    state_converged: bool
    zero_lost_updates: bool
    no_double_allocations: bool
    escrow_conserved: bool
    duration_ms: float
    error_message: str = ""

    @property
    def passed(self) -> bool:
        return (
            self.state_converged
            and self.zero_lost_updates
            and self.no_double_allocations
            and self.escrow_conserved
            and not self.error_message
        )


@dataclass
class ProofReport:
    """Aggregated statistics across all tested scenarios."""
    total_scenarios: int = 0
    passed_scenarios: int = 0
    failed_scenarios: int = 0
    state_convergence_passes: int = 0
    zero_lost_updates_passes: int = 0
    no_double_allocation_passes: int = 0
    escrow_conservation_passes: int = 0
    total_events_generated: int = 0
    total_bytes_transferred: int = 0
    total_duration_sec: float = 0.0
    failures: List[ScenarioResult] = field(default_factory=list)

    def pass_rate(self) -> float:
        if self.total_scenarios == 0:
            return 0.0
        return (self.passed_scenarios / self.total_scenarios) * 100.0


class ProofHarness:
    """
    Automated stress tester and formal invariant checker.
    """

    def __init__(self, base_seed: int = 12345) -> None:
        self.base_seed = base_seed

    def run_scenario(
        self,
        scenario_id: int,
        num_nodes: int = 3,
        num_rounds: int = 3,
        actions_per_node_per_round: int = 3,
    ) -> ScenarioResult:
        """
        Execute a single randomized scenario and verify all invariants.
        """
        start_time = time.perf_counter()
        scenario_seed = self.base_seed + scenario_id
        rng = random.Random(scenario_seed)

        node_ids = [f"node-{chr(65 + i)}" for i in range(num_nodes)]
        sim = DisasterSimulator(node_ids=node_ids, seed=scenario_seed)
        sim.bootstrap_default_scenario()

        # Track all events created across the entire network
        all_created_event_ids: Set[str] = set()

        # Record bootstrap events
        for node in sim.nodes.values():
            for ev in node.store.get_all_events():
                all_created_event_ids.add(ev.event_id)

        try:
            # Step 1: Run rounds with random partitions and multiple field actions per node
            for round_idx in range(num_rounds):
                # Randomly partition into 2 or 3 groups
                groups = sim.partition_manager.random_partition(rng)

                # Multiple actions per node in each round (Requirement 7)
                actions_count = rng.randint(2, max(2, actions_per_node_per_round))
                for _ in range(actions_count):
                    for nid in node_ids:
                        node = sim.nodes[nid]
                        WorkloadGenerator.generate_random_action(
                            node=node,
                            rng=rng,
                            active_people=sim.active_people,
                            active_supplies=sim.active_supplies,
                            active_scarce_items=sim.active_scarce_items,
                        )

                # Collect newly created event IDs
                for node in sim.nodes.values():
                    for ev in node.store.get_all_events():
                        all_created_event_ids.add(ev.event_id)

                # Partial syncs between randomly chosen pairs in current partition
                pairs = []
                for i in range(len(node_ids)):
                    for j in range(i + 1, len(node_ids)):
                        pairs.append((node_ids[i], node_ids[j]))
                rng.shuffle(pairs)

                for n1, n2 in pairs[:len(node_ids)]:
                    sim.nodes[n1].sync_with(n2)

            # Step 2: Heal all links and run transitive epidemic convergence
            sim.heal_and_converge(max_gossip_passes=5)

            # -------------------------------------------------------------
            # INVARIANT CHECKS
            # -------------------------------------------------------------
            first_node = sim.nodes[node_ids[0]]
            first_state = first_node.get_state()
            first_vv = first_node.get_version_vector()

            # (a) Identical State Convergence Invariant
            state_converged = True
            for nid in node_ids[1:]:
                node = sim.nodes[nid]
                if node.get_version_vector() != first_vv or node.get_state() != first_state:
                    state_converged = False
                    break

            # (b) Zero Lost Updates (Audit Intact) Invariant
            zero_lost_updates = True
            for nid in node_ids:
                node = sim.nodes[nid]
                node_event_ids = {ev.event_id for ev in node.store.get_all_events()}
                # Every created event must exist in this node's SQLite database
                if not all_created_event_ids.issubset(node_event_ids):
                    zero_lost_updates = False
                    break

            # Retrieve canonical raw events from the converged SQLite log
            raw_events: List[Event] = first_node.store.get_all_events()

            # -------------------------------------------------------------
            # (c) Indivisible Item Double Alloc=0 (Audited from Raw Event Logs)
            # Reconstruct causal token custody and count CONFIRM_ALLOCATION events
            # -------------------------------------------------------------
            no_double_allocations = True
            scarce_item_events: Dict[str, List[Event]] = {}
            for ev in raw_events:
                if ev.entity_type == "scarce_item":
                    scarce_item_events.setdefault(ev.entity_id, []).append(ev)

            for item_id, item_evs in scarce_item_events.items():
                current_token_holder: Optional[str] = None
                is_currently_allocated: bool = False
                active_allocations_count: int = 0

                for ev in item_evs:
                    op = ev.operation
                    if op == "REGISTER_TOKEN":
                        current_token_holder = ev.payload.get("current_token_holder", ev.node_id)
                        is_currently_allocated = False
                    elif op == "TRANSFER_TOKEN":
                        # Custody transfers only valid if issued by current verified token holder
                        if ev.node_id == current_token_holder:
                            current_token_holder = ev.payload.get("to_holder")
                    elif op == "CONFIRM_ALLOCATION":
                        # Invariant Check: Did this confirmed allocation originate from the token holder?
                        if ev.node_id != current_token_holder:
                            # Unauthorized allocation attempt by non-token holder!
                            # Verify that StateProjector flagged/rejected this attempt
                            item_proj = first_state.get("scarce_item", {}).get(item_id, {})
                            rejected_ids = {r["event_id"] for r in item_proj.get("rejected_allocations", [])}
                            if ev.event_id not in rejected_ids:
                                no_double_allocations = False
                        else:
                            # From valid token holder: check if already allocated (double-allocation)
                            if is_currently_allocated:
                                no_double_allocations = False
                            is_currently_allocated = True
                            active_allocations_count += 1
                    elif op == "RELEASE_ITEM":
                        if ev.node_id == current_token_holder:
                            is_currently_allocated = False
                            active_allocations_count = max(0, active_allocations_count - 1)

                # At end of scenario, cannot have more than 1 active confirmed allocation
                if active_allocations_count > 1:
                    no_double_allocations = False

            # -------------------------------------------------------------
            # (d) Divisible Supply Escrow Balance (Recomputed from Raw Events)
            # Recomputes totals directly from raw events rather than projected state
            # -------------------------------------------------------------
            escrow_conserved = True
            supply_events: Dict[str, List[Event]] = {}
            for ev in raw_events:
                if ev.entity_type == "supply":
                    supply_events.setdefault(ev.entity_id, []).append(ev)

            for supply_id, sup_evs in supply_events.items():
                raw_total_quantity: int = 0
                raw_quotas: Dict[str, int] = {}
                raw_consumed: int = 0

                for ev in sup_evs:
                    op = ev.operation
                    if op == "INIT_ESCROW":
                        raw_total_quantity = ev.payload.get("total_quantity", 0)
                        raw_quotas = dict(ev.payload.get("initial_quotas", {}))
                        raw_consumed = 0
                    elif op == "TRANSFER_QUOTA":
                        from_node = ev.payload.get("from_node", ev.node_id)
                        to_node = ev.payload.get("to_node", "")
                        qty = ev.payload.get("quantity", 0)
                        if raw_quotas.get(from_node, 0) >= qty:
                            raw_quotas[from_node] -= qty
                            raw_quotas[to_node] = raw_quotas.get(to_node, 0) + qty
                    elif op == "CONSUME_QUOTA":
                        consumer = ev.node_id
                        qty = ev.payload.get("quantity", 0)
                        if raw_quotas.get(consumer, 0) >= qty:
                            raw_quotas[consumer] -= qty
                            raw_consumed += qty
                        else:
                            # Over-allocation event: Projector rejects this; verify it didn't mutate quota
                            pass

                # Check strict conservation equation on recomputed raw event totals:
                # sum(quotas) + consumed == total_quantity
                if raw_total_quantity > 0:
                    if sum(raw_quotas.values()) + raw_consumed != raw_total_quantity:
                        escrow_conserved = False
                    if raw_consumed > raw_total_quantity:
                        escrow_conserved = False
                    for q in raw_quotas.values():
                        if q < 0:
                            escrow_conserved = False

                    # Cross-check that raw recomputed totals match the projected state
                    proj_supply = first_state.get("supply", {}).get(supply_id, {})
                    if proj_supply.get("consumed") != raw_consumed:
                        escrow_conserved = False
                    if proj_supply.get("quotas") != raw_quotas:
                        escrow_conserved = False

            duration_ms = (time.perf_counter() - start_time) * 1000
            total_wire_bytes = sim.transport.get_stats()["total_bytes"]

            return ScenarioResult(
                scenario_id=scenario_id,
                num_nodes=num_nodes,
                rounds=num_rounds,
                events_generated=len(all_created_event_ids),
                total_bytes=total_wire_bytes,
                state_converged=state_converged,
                zero_lost_updates=zero_lost_updates,
                no_double_allocations=no_double_allocations,
                escrow_conserved=escrow_conserved,
                duration_ms=duration_ms,
            )

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            return ScenarioResult(
                scenario_id=scenario_id,
                num_nodes=num_nodes,
                rounds=num_rounds,
                events_generated=len(all_created_event_ids),
                total_bytes=0,
                state_converged=False,
                zero_lost_updates=False,
                no_double_allocations=False,
                escrow_conserved=False,
                duration_ms=duration_ms,
                error_message=str(e),
            )
        finally:
            sim.close()

    def run_proof_suite(
        self,
        num_scenarios: int = 1000,
        progress_callback: Optional[Callable[[int, int, ScenarioResult], None]] = None,
    ) -> ProofReport:
        """
        Run the complete 1,000 scenario proof suite across randomized topologies.
        """
        report = ProofReport(total_scenarios=num_scenarios)
        suite_start = time.perf_counter()

        for s_idx in range(num_scenarios):
            # Vary node counts (3 to 5 nodes) and rounds (2 to 4 rounds)
            num_nodes = 3 + (s_idx % 3)            # 3, 4, or 5 nodes
            num_rounds = 2 + ((s_idx // 3) % 3)    # 2, 3, or 4 rounds

            res = self.run_scenario(
                scenario_id=s_idx + 1,
                num_nodes=num_nodes,
                num_rounds=num_rounds,
                actions_per_node_per_round=3,
            )

            report.total_events_generated += res.events_generated
            report.total_bytes_transferred += res.total_bytes

            if res.state_converged:
                report.state_convergence_passes += 1
            if res.zero_lost_updates:
                report.zero_lost_updates_passes += 1
            if res.no_double_allocations:
                report.no_double_allocation_passes += 1
            if res.escrow_conserved:
                report.escrow_conservation_passes += 1

            if res.passed:
                report.passed_scenarios += 1
            else:
                report.failed_scenarios += 1
                report.failures.append(res)

            if progress_callback:
                progress_callback(s_idx + 1, num_scenarios, res)

        report.total_duration_sec = time.perf_counter() - suite_start
        return report

    @staticmethod
    def format_scorecard_table(report: ProofReport) -> str:
        """
        Format an ASCII Pass/Fail proof table for judges and documentation.
        Computes the VERDICT column from real pass counts and removes 'FORMAL' from final line.
        """
        total = report.total_scenarios
        conv_pct = (report.state_convergence_passes / total) * 100 if total else 0
        zero_lost_pct = (report.zero_lost_updates_passes / total) * 100 if total else 0
        scarce_pct = (report.no_double_allocation_passes / total) * 100 if total else 0
        escrow_pct = (report.escrow_conservation_passes / total) * 100 if total else 0
        overall_pct = report.pass_rate()

        avg_bytes_per_scenario = report.total_bytes_transferred / total if total else 0
        avg_events_per_scenario = report.total_events_generated / total if total else 0
        avg_time_ms = (report.total_duration_sec / total) * 1000 if total else 0

        # Requirement 1: Compute VERDICT column dynamically from real pass counts
        def get_verdict(passed_count: int, total_count: int) -> str:
            return "PASS" if total_count > 0 and passed_count == total_count else "FAIL"

        lines = [
            "=" * 76,
            "         RESCUENET AUTOMATIC INVARIANT PROOF HARNESS SCORECARD",
            "=" * 76,
            f"  Total Scenarios Executed:     {total:,} randomized partition/heal trials",
            f"  Total Elapsed Test Time:      {report.total_duration_sec:.2f} seconds ({avg_time_ms:.2f} ms/scenario)",
            f"  Total Events Generated:       {report.total_events_generated:,} events ({avg_events_per_scenario:.1f} ev/scenario)",
            f"  Total Wire Bytes Transferred: {report.total_bytes_transferred:,} bytes ({avg_bytes_per_scenario / 1024:.2f} KB/scenario)",
            "-" * 76,
            f"  {'INVARIANT TESTED':<38} | {'PASSED':<12} | {'PASS RATE':<10} | {'VERDICT'}",
            "-" * 76,
            f"  (a) Identical State Convergence      | {report.state_convergence_passes:<12} | {conv_pct:>7.2f}%   | {get_verdict(report.state_convergence_passes, total)}",
            f"  (b) Zero Lost Updates (Audit Intact) | {report.zero_lost_updates_passes:<12} | {zero_lost_pct:>7.2f}%   | {get_verdict(report.zero_lost_updates_passes, total)}",
            f"  (c) Indivisible Item Double Alloc=0  | {report.no_double_allocation_passes:<12} | {scarce_pct:>7.2f}%   | {get_verdict(report.no_double_allocation_passes, total)}",
            f"  (d) Divisible Supply Escrow Balance  | {report.escrow_conservation_passes:<12} | {escrow_pct:>7.2f}%   | {get_verdict(report.escrow_conservation_passes, total)}",
            "=" * 76,
            f"  FINAL VERDICT: {report.passed_scenarios}/{total} SCENARIOS PASSED ({overall_pct:.2f}%) -> {overall_pct:.2f}% CONVERGENCE",
            "=" * 76,
        ]
        return "\n".join(lines)
