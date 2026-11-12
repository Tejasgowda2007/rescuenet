# RescueNet: Offline-First Disaster Coordination System

An offline-first, peer-to-peer event-sourced disaster coordination system built in Python for 36-hour hackathons. Rescue volunteers record needs, supplies, shelters, and missing/found persons with zero internet connectivity.

---

## Invariants & Design Principles

1. **State as a Fold over History:** Each device maintains an append-only event log in its own SQLite database. Current state is never mutated in place; it is computed by replaying events deterministically.
2. **Deterministic Convergence:** Devices with the same set of events always compute identical state, regardless of the order in which events were received across network partitions.
3. **Zero Lost Updates:** Conflicting updates (e.g. concurrent reports on missing persons) are flagged in a conflict ledger for human review rather than silently overwriting.
4. **Anti-Entropy Delta Sync:** Version vectors `(node_id -> max_counter)` ensure peers only transmit events the other side is missing, keeping sync payloads minimal.
5. **No Double-Allocation of Scarce Items:**
   - **Pre-allocated escrow quotas** for divisible supplies: $\sum \text{quotas} + \text{consumed} \equiv \text{total}$.
   - **Single-owner possession tokens** for indivisible items (e.g., rescue boats): offline non-token holders can only emit `REQUESTED` claims.

---

## Project Structure

```
rescuenet/
├── events/
│   ├── __init__.py
│   └── event.py             # Immutable Event model with content-addressed SHA-256 IDs
├── storage/
│   ├── __init__.py
│   ├── sqlite_store.py      # Append-only SQLite engine with anti-equivocation enforcement
│   └── projector.py         # Deterministic reducer / materialized state projector
├── transport/               # Transport abstraction layer
│   ├── __init__.py
│   ├── base.py              # Abstract Transport & TransportMessage wire serialization
│   └── in_memory.py         # InMemoryTransport with partition cuts & wire byte counters
├── sync/                    # Anti-entropy sync protocol
│   ├── __init__.py
│   ├── messages.py          # Message constants and SyncStats telemetry
│   └── node.py              # Node coordinator (Store + Projector + Sync engine)
├── allocation/              # Stage 3: Merge rules & scarce-resource allocation
│   ├── __init__.py
│   ├── escrow.py            # Bounded counter escrow quotas (divisible supplies)
│   ├── tokens.py            # Single-owner possession tokens (indivisible assets)
│   └── conflict_resolver.py # Human-in-the-loop triage for person tracking
├── simulator/               # Stage 4: Multi-node dynamic partition simulator
│   ├── __init__.py
│   ├── network.py           # PartitionManager for graph cut & heal topology
│   ├── workload.py          # Stochastic disaster field actions & conflict injector
│   └── engine.py            # DisasterSimulator & SimulationReport
├── crypto/                  # Stage 6: Field-level AES-GCM encryption & Ed25519 signatures
├── ui/                      # Stage 8: Streamlit 3-node interactive partition demo
├── tests/
│   ├── __init__.py
│   ├── test_stage1.py       # Event log, idempotency & projection tests
│   ├── test_stage2.py       # Version vector sync, byte counting & partition tests
│   ├── test_stage3.py       # Escrow, token ownership, & conflict resolution tests
│   └── test_stage4.py       # Multi-node partitions, transitive sync & chaos tests
├── demo_stage1.py           # Standalone terminal demonstration of Stage 1
├── demo_stage2.py           # Interactive terminal demonstration of Stage 2 (sync + bytes)
├── demo_stage3.py           # Demonstration of Stage 3 (escrow, boat token, conflicts)
├── demo_stage4.py           # Demonstration of Stage 4 (4-node hurricane scenario & mesh)
├── requirements.txt
└── README.md
```

---

## How to Run and Test

Make sure your shell is inside the project directory:
```powershell
cd C:\Users\gowda\.gemini\antigravity\scratch\rescuenet
```

### Stage 1: Event Log & State Projection
```powershell
python demo_stage1.py
```

### Stage 2: Anti-Entropy Sync & Byte Counting
```powershell
python demo_stage2.py
```

### Stage 3: Merge Rules & Scarce Resource Allocation
```powershell
python demo_stage3.py
```

### Stage 4: Multi-Node Partition Simulator
```powershell
python demo_stage4.py
```

### Run All Unit & Integration Tests (Pytest)
```powershell
python -m pytest tests -v
```
