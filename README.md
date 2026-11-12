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
6. **Zero-Trust Security & Seized Device Protection:**
   - **Field-level encryption at rest (AES-256-GCM):** PII, patient conditions, and victim identities are encrypted using passphrase-derived keys (PBKDF2-HMAC-SHA256, 100k rounds). A seized laptop exposes zero plain text.
   - **Ed25519 digital signatures:** Every event is signed with the volunteer's private key. Forged or tampered events are rejected before entering SQLite.

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
│   └── node.py              # Node coordinator (Store + Projector + Keyring + Sync engine)
├── allocation/              # Stage 3: Merge rules & scarce-resource allocation
│   ├── __init__.py
│   ├── escrow.py            # Bounded counter escrow quotas (divisible supplies)
│   ├── tokens.py            # Single-owner possession tokens (indivisible assets)
│   └── conflict_resolver.py # Human-in-the-loop triage for person tracking
├── simulator/               # Stage 4 & 5: Simulation & Formal Proof Harness
│   ├── __init__.py
│   ├── network.py           # PartitionManager for graph cut & heal topology
│   ├── workload.py          # Stochastic disaster field actions & conflict injector
│   ├── engine.py            # DisasterSimulator & SimulationReport
│   └── proof_harness.py     # 1,000-scenario automated fuzzing & invariant proof harness
├── crypto/                  # Stage 6: Field-level AES-GCM encryption & Ed25519 signatures
│   ├── __init__.py
│   ├── ciphers.py           # PBKDF2-HMAC-SHA256 & AES-256-GCM field encryptor
│   ├── signatures.py        # Ed25519 digital signature signing & verification
│   └── keyring.py           # NodeKeyring managing local secrets & trusted peers
├── ui/                      # Stage 8: Streamlit 3-node interactive partition demo
├── tests/
│   ├── __init__.py
│   ├── test_stage1.py       # Event log, idempotency & projection tests
│   ├── test_stage2.py       # Version vector sync, byte counting & partition tests
│   ├── test_stage3.py       # Escrow, token ownership, & conflict resolution tests
│   ├── test_stage4.py       # Multi-node partitions, transitive sync & chaos tests
│   ├── test_stage5.py       # Invariant proof harness & misbehaving node tests
│   └── test_stage6.py       # AES-GCM encryption, Ed25519 signatures & seized device tests
├── demo_stage1.py           # Standalone terminal demonstration of Stage 1
├── demo_stage2.py           # Interactive terminal demonstration of Stage 2 (sync + bytes)
├── demo_stage3.py           # Demonstration of Stage 3 (escrow, boat token, conflicts)
├── demo_stage4.py           # Demonstration of Stage 4 (4-node hurricane scenario & mesh)
├── demo_stage5.py           # Stage 5 1,000-scenario automated proof harness
├── demo_stage6.py           # Stage 6 seized device forensic demonstration
├── requirements.txt
└── README.md
```

---

## Automated Proof Harness (Stage 5 Scorecard)

Running `python demo_stage5.py` executes 1,000 distinct randomized partition & heal trials (auditing raw event logs):

```
============================================================================
         RESCUENET AUTOMATIC INVARIANT PROOF HARNESS SCORECARD
============================================================================
  Total Scenarios Executed:     1,000 randomized partition/heal trials
  Total Elapsed Test Time:      31.66 seconds (31.66 ms/scenario)
  Total Events Generated:       31,179 events (31.2 ev/scenario)
  Total Wire Bytes Transferred: 35,529,142 bytes (34.70 KB/scenario)
----------------------------------------------------------------------------
  INVARIANT TESTED                       | PASSED       | PASS RATE  | VERDICT
----------------------------------------------------------------------------
  (a) Identical State Convergence      | 1000         |  100.00%   | PASS
  (b) Zero Lost Updates (Audit Intact) | 1000         |  100.00%   | PASS
  (c) Indivisible Item Double Alloc=0  | 1000         |  100.00%   | PASS
  (d) Divisible Supply Escrow Balance  | 1000         |  100.00%   | PASS
============================================================================
  FINAL VERDICT: 1000/1000 SCENARIOS PASSED (100.00%) -> 100.00% CONVERGENCE
============================================================================
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

### Stage 5: 1,000-Scenario Formal Proof Harness
```powershell
python demo_stage5.py
```

### Stage 6: Seized Device & Event Signing Forensic Demo
```powershell
python demo_stage6.py
```

### Run All Unit & Integration Tests (Pytest)
```powershell
python -m pytest tests -v
```
