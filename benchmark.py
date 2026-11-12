"""Performance benchmark for RescueNet sync throughput and latency."""
from __future__ import annotations
import time
from simulator.engine import DisasterSimulator
from sync.mesh_router import MeshRouter


def main():
    n = 5
    sim = DisasterSimulator([f"node-{i}" for i in range(n)], seed=1)
    router = MeshRouter()
    for i in range(n):
        for j in range(i + 1, n):
            router.add_link(f"node-{i}", f"node-{j}")

    for i in range(100):
        sim.nodes["node-0"].record_event("need", f"need-{i}", "CREATE", {"item": "water", "urgency": "HIGH"})

    t0 = time.perf_counter()
    rounds = router.broadcast_sync(sim.nodes)
    elapsed = time.perf_counter() - t0
    total_events = sum(nd.store.count() for nd in sim.nodes.values())
    print(f"Nodes: {n} | Events generated: 100 | Sync rounds: {rounds}")
    print(f"Elapsed: {elapsed:.4f}s | Total stored events: {total_events}")
    print(f"Throughput: {total_events / elapsed:.0f} events/s")
    vvs = [nd.get_version_vector() for nd in sim.nodes.values()]
    print("Converged:", all(v == vvs[0] for v in vvs))


if __name__ == "__main__":
    main()