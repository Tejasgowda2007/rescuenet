"""
Unit and Integration Tests for Stage 5:
Automatic Proof Harness Invariant Verification.
"""

import pytest
from simulator.proof_harness import ProofHarness, ProofReport


def test_proof_harness_single_scenario_all_invariants():
    """Verify that a single randomized trial strictly satisfies all 4 invariants."""
    harness = ProofHarness(base_seed=42)
    res = harness.run_scenario(scenario_id=1, num_nodes=4, num_rounds=3)

    assert res.passed is True
    assert res.state_converged is True
    assert res.zero_lost_updates is True
    assert res.no_double_allocations is True
    assert res.escrow_conserved is True
    assert res.total_bytes > 0
    assert res.events_generated > 0


def test_proof_harness_batch_50_scenarios():
    """
    Run 50 randomized trials across variable node counts (3 to 5 nodes)
    and verify 100% pass rate.
    """
    harness = ProofHarness(base_seed=999)
    report = harness.run_proof_suite(num_scenarios=50)

    assert report.total_scenarios == 50
    assert report.passed_scenarios == 50
    assert report.failed_scenarios == 0
    assert report.pass_rate() == 100.0
    assert report.state_convergence_passes == 50
    assert report.zero_lost_updates_passes == 50
    assert report.no_double_allocation_passes == 50
    assert report.escrow_conservation_passes == 50


def test_scorecard_formatting():
    """Verify ASCII scorecard generator produces human-readable tables."""
    harness = ProofHarness(base_seed=123)
    report = harness.run_proof_suite(num_scenarios=5)
    scorecard = harness.format_scorecard_table(report)

    assert "SCORECARD" in scorecard
    assert "Identical State Convergence" in scorecard
    assert "Zero Lost Updates" in scorecard
    assert "Indivisible Item Double Alloc=0" in scorecard
    assert "Divisible Supply Escrow Balance" in scorecard
    assert "PASS" in scorecard
