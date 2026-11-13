# 🆘 RescueNet — Offline-First Disaster Coordination System

> **"When the network dies, coordination shouldn't."**
> RescueNet lets rescue volunteers record needs, supplies, shelters, and missing/found people on *any* device with **zero connectivity**, sync devices directly when they meet, and converge to one identical state with **zero lost updates** and **no double allocation** of scarce items.

---

## 📌 Table of Contents
1. [The Problem](#-the-problem)
2. [Our Solution](#-our-solution)
3. [Why We Win (Judge Highlights)](#-why-we-win-judge-highlights)
4. [Core Invariants & Guarantees](#-core-invariants--guarantees)
5. [Architecture](#-architecture)
6. [Innovative Long-Range Modalities (No LoRa)](#-innovative-long-range--no-infrastructure-modalities)
7. [Security & Seized-Device Protection](#-security--seized-device-protection)
8. [Proof & Evidence](#-proof--evidence)
9. [Live Demo (3 Clicks)](#-live-demo-3-clicks)
10. [Deployment](#-deployment)
11. [Performance](#-performance)
12. [Honest Limitations](#-honest-limitations)
13. [Quick Start](#-quick-start)

---

## 🔥 The Problem
Earthquakes, hurricanes, floods, wildfires, wars, and government internet shutdowns take networks down **exactly when people need to coordinate most**. Volunteers fall back on paper lists and shouted updates, then try to reconcile everything once signal returns.

**Consequences:**
- Two teams promise the **same boat**.
- Supply counts **disagree**.
- A missing person is marked "found" on one phone and **overwritten** on another.
- Almost every coordination app assumes a reliable central server — the first thing to disappear.

**Who suffers:** disaster victims, volunteers, relief organisations, local authorities.

**Why existing tools fail:** sync libraries merge offline edits automatically, and mesh apps pass messages between nearby phones — but automatic merging cannot stop two teams from allocating the same scarce item, and very few tools are designed for **long network splits from the start**.

---

## 💡 Our Solution
RescueNet is an **offline-first, peer-to-peer, event-sourced** disaster coordination system:

- Volunteers record **needs, supplies, shelters, and people (missing/found)** on **any device**, with **no internet**.
- Devices **share data directly** when they come near each other (Wi-Fi hotspot, Bluetooth, sound, light, or physical carry).
- Any device that reaches the internet can **push/pull** deltas to a server.
- **Conflicting edits merge without losing information** (preserved in a conflict ledger).
- **Scarce items can never be allocated twice** (escrow quotas + single-owner tokens).
- **Data on a lost/seized device stays protected** (AES-256-GCM + Ed25519).

**No central server is assumed reachable.** Links are slow, intermittent, short-lived. Devices have limited battery and storage. RescueNet is built for that reality.

---

## 🏆 Why We Win (Judge Highlights)
| Judging Criterion | How RescueNet Delivers |
|---|---|
| At least 3 devices/simulated nodes | ✅ 3-node Streamlit UI + N-node simulator + 3-laptop TCP mesh |
| Split-and-merge test with conflicting edits | ✅ `test_stage4` / `test_stage8` — cut → conflict → heal → converge |
| All devices converge, zero lost updates | ✅ 1,000/1,000 scenarios, 100% convergence |
| No double allocation of scarce resources | ✅ Escrow quotas + single-owner tokens; 1,000/1,000 trials pass |
| Small sync payloads over weak links | ✅ Version vectors + delta sync + zlib compression |
| Protection of sensitive records | ✅ AES-256-GCM at rest + Ed25519 signatures |
| Resilience to judge-chosen partition | ✅ `test_judge_chosen_partition_scenario` passes |
| Innovative long-range (no LoRa) | ✅ Audio FSK modem, Li-Fi, drone relay mesh |

---

## 🔒 Core Invariants & Guarantees

### What the System Guarantees
1. **Strong Eventual Convergence (SEC):** Every device keeps an append-only event log in local SQLite. State is computed deterministically by folding events in canonical order `(timestamp, node_id, counter)`. Once partitions heal and logs sync, every device produces **byte-for-byte identical state**.
2. **Zero Lost Updates:** Conflicting edits (e.g., concurrent "found" vs "missing" reports) are **never silently overwritten** — both are preserved in a structured conflict ledger for human triage.
3. **Mathematically Impossible Double-Allocation:**
   - **Countable supplies (Escrow Quotas):** Total inventory is partitioned into disjoint local allowances (Σ quotas + consumed ≡ total). Offline nodes cannot spend beyond their allowance.
   - **Indivisible assets (Single-Owner Token):** Only the device holding the possession token can issue `CONFIRM_ALLOCATION`. Disconnected peers can only emit `REQUESTED` claims.
4. **Minimal Sync Payloads:** Anti-entropy sync exchanges compact Version Vectors `{node_id: max_counter}` and transfers only missing delta events. Repeat syncs transfer **0 events**.
5. **Cryptographic Protection on Seized Devices:** Sensitive fields encrypted at rest with **AES-256-GCM** (PBKDF2-HMAC-SHA256, 100k iterations). All events signed with **Ed25519**; forged updates rejected before touching SQLite.

### Honest Limitations (CAP trade-offs)
- **Destroyed token holder:** if the device holding an indivisible item's token is destroyed before syncing, peers cannot confirm-allocate it without human override.
- **Quota fragmentation:** a cut-off node's unused quota cannot be borrowed by others (safety > availability).
- **Clock drift:** canonical sort uses `(timestamp, node_id, counter)`; inaccurate clocks may reorder events in real-world time, but convergence is still deterministic.
- **Pre-shared trust:** Ed25519 verification needs peer public keys registered before deployment (no online CA).
- **Unbounded log growth:** append-only SQLite keeps full audit history; long-term ops need compaction.

---

## 🏗️ Architecture

```
rescuenet/
├── events/                  # Stage 1: Immutable content-addressed Event model
├── storage/                 # Stage 1 & 3: Append-only SQLite store (WAL) + StateProjector
├── transport/               # Stage 2 & 7: Abstract Transport + InMemory, TCP, BLE, Audio FSK, Li-Fi, Drone
├── sync/                    # Stage 2 & 6: Version-vector anti-entropy protocol, Node, MeshRouter, WS bridge
├── allocation/              # Stage 3: Escrow quotas, single-owner tokens, conflict resolver, IntentLedger
├── simulator/               # Stage 4 & 5: N-node partition simulator + 1,000-trial proof harness
├── crypto/                  # Stage 6: AES-256-GCM field encryption + Ed25519 signatures + keyring
├── validation/              # Schema validation (types, sizes, allowed ops)
├── ui/                      # Stage 8: Streamlit 3-node interactive UI + controller
├── tests/                   # 40 automated unit & integration tests
├── demo_stage1..7.py        # Terminal demos per stage
├── run_node.py              # CLI node runner for multi-laptop deployment
├── benchmark.py             # Performance benchmark
├── Dockerfile / docker-compose.yml
└── README.md
```

---

## 🚀 Innovative Long-Range / No-Infrastructure Modalities
RescueNet deliberately avoids relying on LoRa hardware. Instead it ships **three innovative transports** that work with gear already in the field:

1. **Audio FSK Modem** (`transport/audio_modem.py`) — encodes sync deltas as sound tones over any phone/laptop speaker + mic. Range ~100m–1km (further with a PA). **Real WAV generation included** (encode → `.wav` → decode round-trips verified). Works in RF-dead zones.
2. **Li-Fi / Visible Light** (`transport/lifi_stub.py`) — modulates LED/screen brightness; received via camera or photodiode. Works in RF-jammed or RF-denied zones (bunkers, hospitals).
3. **Drone / Vehicle Relay Mesh** (`transport/drone_relay.py`) — UAVs or ambulances carry encrypted caches between camps; auto-syncs on landing. No radio infrastructure needed.

All three plug in as drop-in `Transport` implementations — **zero changes** to the event log or state machine. Plus the existing walkie-talkie chirp, optical QR, and ambulance data mule.

---

## 🔐 Security & Seized-Device Protection
- **AES-256-GCM** encryption at rest (PBKDF2-HMAC-SHA256, 100k iterations).
- **Ed25519** signatures on every event; forged/tampered updates rejected before touching SQLite.
- **Pre-shared trust** — no online CA required (peer public keys registered before deployment).
- **Device revocation / kill-switch** — blacklists a lost/seized device across the mesh trust ring.
- **Raw SQLite scan** confirms no plaintext PII leaks.

---

## 📊 Proof & Evidence

### Automated Test Suite
All **40 unit and integration tests** pass:
```powershell
python -m pytest tests -v
```
- Stage 1: 7/7 (deterministic IDs, idempotency, anti-equivocation, deltas, convergence, zero lost updates, tombstones)
- Stage 2: 4/4 (bi-directional sync, zero-event follow-up, partitions, transitive gossip)
- Stage 3: 6/6 (escrow conservation, over-allocation rejection, quota transfer, boat token, handoff, conflict triage)
- Stage 4: 5/5 (3+ nodes, graph partitions, mountain/valley sync, 5-node chaos, judge scenario)
- Stage 5: 5/5 (single/batch proofs, scorecard, rogue node rejection, transport cut integrity)
- Stage 6: 4/4 (AES-GCM, Ed25519 tampering, forged rejection, SQLite leak scan)
- Stage 7: 4/4 (TCP framing, 3-node mesh, offline timeout, BLE stub)
- Stage 8: 2/2 (UI compile, controller cut/heal/conflict/convergence)
- ResQ-Mesh: 3/3 (intent ledger, collision, revocation)

### 1,000-Scenario Proof Harness
```
Total Scenarios: 1,000 randomized partition/heal trials
Events Generated: 31,179 (31.2/scenario)
Wire Bytes: 35.5 MB (34.7 KB/scenario)
(a) Identical State Convergence      1000  100.00%  PASS
(b) Zero Lost Updates (Audit Intact) 1000  100.00%  PASS
(c) Indivisible Double Alloc = 0     1000  100.00%  PASS
(d) Divisible Escrow Balance         1000  100.00%  PASS
FINAL VERDICT: 1000/1000 (100.00%) CONVERGENCE
```

---

 HEAD
## 🎪 Live Demo (3 Clicks)
Launch: `streamlit run ui/app.py`
=======
# RescueNet FieldMesh: 50 km x 50 km Disaster Digital Twin

> **"When infrastructure fails, coordination survives."**

RescueNet FieldMesh is a complete, production-grade software-based digital twin of an ad-hoc disaster-response communication network operating across a **50 km x 50 km mountainous and dense forest region** with **zero internet, zero cellular towers, and zero physical radio hardware**.

FieldMesh simulates the physical terrain, five strategic rescue stations, radio wave propagation approximations (LoRa 865–867 MHz WPC-compliant and 5.8 GHz directional microwave P2P), multi-hop cost-aware Dijkstra graph routing, SimPy discrete-event packet scheduling with channel contention, and integrates directly with the RescueNet event-sourcing and cryptographic security kernel.

---

## FieldMesh Highlights & Capabilities

1. **Procedural 3D Mountainous & Dense Forest Twin:**
   - 50 km x 50 km realistic Himalayan/Uttarakhand foothills topography generated deterministically (`seed=42`).
   - Elevations spanning 320 m (Bhagirathi river gorge) to 2,840 m (Trishul mountain barrier ridge).
   - Real-time 3D line-of-sight (LOS) ray-marching and 1st Fresnel zone clearance calculation between antennas.
2. **Realistic Radio Propagation Physics Approximation:**
   - **Free Space Path Loss (FSPL):** Calculated continuously as $20 \log_{10}(d) + 20 \log_{10}(f) + 32.44$.
   - **Knife-Edge Mountain Diffraction (ITU-R P.526):** Extra diffraction loss over mountain ridges based on dimensionless parameter $v$.
   - **Foliage & Canopy Attenuation (Weissberger Modified Exponential Model):** Forest canopy penetration loss up to 25 dB.
   - **LoRa Semtech SX1276 Airtime Engine:** Exact packet serialization time calculation based on Spreading Factor (SF7–SF12), bandwidth (125 kHz), coding rate (4/5), preamble, and explicit header.
   - **WPC India Regulatory Compliance:** Configured for 865–867 MHz, 100 mW EIRP limits, with clear disclaimer that physical hardware deployment requires WPC equipment type approval (ETA).
3. **Dynamic Graph Routing & Topology:**
   - Graph vertices are stations and relays; viable radio links form edges.
   - Dynamic Dijkstra shortest path routing weighted by link latency + link margin degradation penalty.
   - Automatic partition detection (`connected_components`). When Trishul Ridge blocks direct links, packets dynamically re-route over the mountain summit relay (Alpha -> Echo -> Charlie).
4. **SimPy Discrete-Event Simulation:**
   - Channel locks using `simpy.PriorityResource`.
   - Emergency SOS priority queuing (preempts background telemetry).
   - Packet fragmentation into MTU-sized radio frames, per-hop drop evaluation against Packet Error Rate (PER), and hop-by-hop forwarding queues.
5. **Full Event-Sourcing & Cryptographic Integration:**
   - Each station possesses an independent, isolated SQLite database file.
   - Cryptographic Ed25519 signatures and AES-256-GCM encryption verified at arrival.
   - Indivisible boat token exclusivity and divisible medical escrow quota conservation guaranteed across partitions.
6. **Command Center UI (React + TypeScript + Vite + Three.js):**
   - 10 dedicated operational views: 3D Terrain Twin, Overview, 2D Topo Map, Network Topology, Station Details, Comms Monitor, Event Explorer, Resource Allocation, Real-time Analytics, and Scenarios.
   - Interactive controls: Cut/Heal links, destroy/restore relay, adjust simulation speed, trigger SOS alerts, inject failure scenarios, and launch the 5-Minute Hackathon Demo.

---

## 5-Minute Hackathon Demo Workflow

FieldMesh includes an automated 7-step Hackathon Demo runner (`fieldmesh/demo_runner.py` and front-end modal) that proves the system's core capabilities in 5 minutes:

| Step | Phase | Live Operational Action & System Observation | Verified Invariant |
|:---|:---|:---|:---|
| **1** | Baseline Network | All 5 stations active. LoRa/P2P link budgets calculated. Boat token and antibiotic escrow seeded. | State Convergence |
| **2** | Mountain Obstruction | Trishul rockslide severs direct valley links. Network partitions into isolated islands. | Partition Detected |
| **3** | Offline Isolation | Alpha logs Dr. Stone missing at pier; Charlie logs Dr. Stone found at shelter. Bravo consumes escrowed antibiotics. Charlie attempts offline boat claim. | Zero Lost Updates & Escrow Safety |
| **4** | Relay Activation | ECHO Elevated Relay brought online on summit at 2,820 m. Alpha -> Echo -> Charlie 2-hop route discovered. | Dynamic Multi-Hop Route Recovery |
| **5** | Delta Sync | Anti-entropy sync runs over multi-hop LoRa radio link. Compact version vectors exchanged. | Sync Success |
| **6** | Convergence Audit | Event stores compared across all nodes. State projections match 100% byte-for-byte. Conflicting doctor sightings flagged for triage. Single boat owner maintained. | SEC & Conservation |
| **7** | Security Defense | Rogue node attempts forged signature and escrow over-draw. System rejects tampered packet before SQLite store. | Tamper Immunity |

---

## Quickstart & Launch Instructions

### 1. Launch RescueNet FieldMesh 3D Command Center
```powershell
# From rescuenet directory:
python run_fieldmesh.py --port 8000
```
Then open your browser to **http://localhost:8000**.
The interactive Three.js 3D terrain twin, live station telemetry, packet monitor, and scenario controls will load immediately.

### 2. Run the Full Automated Test Suite (All 54 Tests)
```powershell
python -m pytest tests -v
```
All **54 integration and unit tests** across Stages 1–8 and FieldMesh pass with 100% green checkmarks.

---

## Architecture Diagram

```
+----------------------------------------------------------------------------------+
|               RESCUENET FIELDMESH ARCHITECTURE (50 km x 50 km TWIN)             |
+----------------------------------------------------------------------------------+
|                                                                                  |
|   +-----------------------+     REST / WebSocket      +----------------------+   |
|   |  Vite + React + R3F   | <=======================> |  FastAPI App Server  |   |
|   |  Three.js 3D Twin UI  |   (4 Hz Telemetry Stream) |  (api/server.py)     |   |
|   +-----------------------+                           +----------------------+   |
|                                                                  |               |
|                                                +-----------------+---------------+
|                                                |                 |               |
|                                         +--------------+  +--------------+       |
|                                         |  Scenario &  |  |  Metrics &   |       |
|                                         |  Demo Runner |  |  Aggregator  |       |
|                                         +--------------+  +--------------+       |
|                                                |                 |               |
|        +---------------------------------------+-----------------+               |
|        |                                                                         |
|        v                                                                         |
|   +--------------------------------------------------------------------------+   |
|   |                    FIELDMESH SIMULATION ENGINE (SimPy)                   |   |
|   |                                                                          |   |
|   |   +-------------------+   +--------------------+   +-----------------+   |   |
|   |   | Terrain Engine    |   | Radio Propagation  |   | NetworkX Graph  |   |   |
|   |   | (50x50km, ridges, |-->| (FSPL, ITU-R P.526 |-->| (Dijkstra paths,|   |   |
|   |   |  rivers, gorges)  |   |  knife-edge, LoRa) |   |  partitions)    |   |   |
|   |   +-------------------+   +--------------------+   +-----------------+   |   |
|   |                                                            |             |   |
|   +------------------------------------------------------------|-------------+   |
|                                                                v                 |
|   +--------------------------------------------------------------------------+   |
|   |                  RESCUENET SECURE ADAPTER LAYER (adapter.py)             |   |
|   |                                                                          |   |
|   |    [ALPHA HQ]        [BRAVO CLINIC]      [CHARLIE SHELTER]  [DELTA PATROL]   |   |
|   |    Node (SQLite)     Node (SQLite)       Node (SQLite)      Node (SQLite)    |   |
|   |    Ed25519 / AES     Ed25519 / AES       Ed25519 / AES      Ed25519 / AES    |   |
|   |    Escrow Quotas     Escrow Quotas       Escrow Quotas      Escrow Quotas    |   |
|   |    Version Vector    Version Vector      Version Vector     Version Vector   |   |
|   +--------------------------------------------------------------------------+   |
+----------------------------------------------------------------------------------+
```

>>>>>>> 924cc46 (Deploy RescueNet dashboard)

1. **"1️⃣ Normal (Online)"** — 3 camps share 10 medical kits; Patient X registered; all converged.
2. **"2️⃣ Network Dies!"** — earthquake cuts signal; Harbor claims 8 kits ("Found"), Mountain claims 5 ("Injured") → 13 claimed for 10 stock.
3. **"3️⃣ Reconnect & Fix"** — signal returns; both Patient X reports preserved (zero lost); coordinator splits 6+4 = 10 kits (zero double-allocation); all devices identical.

Additional UI features: ambulance data mule, walkie-talkie chirp, optical QR sync, device revocation, live invariant audit.

---

## 🐳 Deployment

### Docker (recommended)
```powershell
docker-compose up
```
→ 3 nodes (alpha/beta/gamma) + Streamlit UI on port 8501.

### 3 Real Laptops on a Wi-Fi Hotspot (no internet)
```powershell
# Terminal 1
python run_node.py --id alpha --port 8001 --peers beta=192.168.1.2:8002,gamma=192.168.1.3:8003 --db alpha.db
# Terminal 2
python run_node.py --id beta --port 8002 --peers alpha=192.168.1.1:8001,gamma=192.168.1.3:8003 --db beta.db
# Terminal 3
python run_node.py --id gamma --port 8003 --peers alpha=192.168.1.1:8001,beta=192.168.1.2:8002 --db gamma.db
```

### Interactive Dashboard
```powershell
streamlit run ui/app.py
```

---

## ⚡ Performance
- **Benchmark:** 5 nodes, 100 events → 0.04s, ~13,000 events/s, converged in 2 rounds.
- **Compression:** zlib level-9 reduces sync payloads ~60–80%.
- **Durability:** WAL mode + fsync + busy_timeout (crash-safe, concurrent).
- **Thread-safe:** RLock around all store reads/writes.
- **Schema validation:** types, sizes (64KB cap), allowed operations.

---

## 📝 Honest Limitations
- Destroyed token-holder device needs human override for that item.
- Quotas can't be borrowed by cut-off nodes (by design).
- Clock drift may reorder events in real-world time (convergence unaffected).
- Pre-shared trust required (no online CA).
- Unbounded log growth (compaction needed for multi-month ops).

---

## 🚀 Quick Start
```powershell
cd rescuenet
python -m venv .venv && .venv\Scripts\activate   # (or source .venv/bin/activate)
pip install -r requirements.txt
python -m pytest tests -v                        # 40/40 pass
python demo_stage5.py                            # 1,000-scenario proof
streamlit run ui/app.py                          # interactive demo
python benchmark.py                               # performance
```

---

## 📄 License & Credits
Built for the offline-first disaster coordination challenge. RescueNet — *because help shouldn't wait for a signal.*
