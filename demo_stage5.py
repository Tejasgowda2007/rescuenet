"""
RescueNet Stage 5 Demonstration:
Automatic Proof Harness Running 1,000 Randomized Partition & Merge Scenarios.

Checks after every scenario:
(a) All nodes have 100% identical state,
(b) Every original update still exists (zero lost updates),
(c) No scarce item is allocated twice & escrow conservation holds,
(d) Total bytes transferred and network telemetry.
Prints the final pass/fail scorecard table.
"""

import os
import sys
import time

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from simulator.proof_harness import ProofHarness, ScenarioResult


def progress_indicator(current: int, total: int, res: ScenarioResult):
    """Print clean terminal progress updates every 100 scenarios."""
    if current == 1 or current % 100 == 0 or current == total:
        pct = (current / total) * 100
        status_symbol = "[OK]" if res.passed else "[FAIL]"
        print(f"  [{current:>4}/{total}] ({pct:>5.1f}%) | "
              f"Nodes: {res.num_nodes} | "
              f"Events: {res.events_generated:>3} | "
              f"Wire: {res.total_bytes:>6} B | "
              f"Last Trial: {status_symbol} ({res.duration_ms:.1f}ms)")


def main():
    print("\n" + "=" * 76)
    print(" RescueNet Stage 5: 1,000-Scenario Automatic Convergence & Invariant Proof")
    print("=" * 76)
    print("Running 1,000 stochastic disaster coordination scenarios across:")
    print("  * Node Counts: 3 to 5 nodes per trial")
    print("  * Network Cuts: Random dynamic multi-cluster partitions")
    print("  * Field Workloads: Shelters, supplies, scarce items, conflicting sightings")
    print("  * Convergence: Epidemic gossip reconciliation across healed mesh\n")

    num_scenarios = 1000
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        num_scenarios = int(sys.argv[1])

    harness = ProofHarness(base_seed=2026)
    t0 = time.time()
    report = harness.run_proof_suite(
        num_scenarios=num_scenarios,
        progress_callback=progress_indicator,
    )
    total_elapsed = time.time() - t0

    print("\n" + harness.format_scorecard_table(report))

    if report.failed_scenarios > 0:
        print("\n[!] Failures encountered:")
        for f in report.failures[:5]:
            print(f"  - Scenario #{f.scenario_id}: {f.error_message}")
        sys.exit(1)
    else:
        print("\n[OK] Stage 5 proof harness verified: 100% mathematical consistency across all trials!\n")


if __name__ == "__main__":
    main()
