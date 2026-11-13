"""
Store-and-forward mesh router for multi-hop offline sync.

Allows events to traverse intermediate nodes (data mules, relays) when
source and destination are not directly connected. Each hop exchanges
deltas; intermediate nodes persist and re-forward.
"""
from __future__ import annotations
from typing import Dict, List, Any, Optional


class MeshRouter:
    def __init__(self) -> None:
        self.adjacency: Dict[str, List[str]] = {}

    def add_link(self, a: str, b: str) -> None:
        self.adjacency.setdefault(a, [])
        self.adjacency.setdefault(b, [])
        if b not in self.adjacency[a]:
            self.adjacency[a].append(b)
        if a not in self.adjacency[b]:
            self.adjacency[b].append(a)

    def remove_link(self, a: str, b: str) -> None:
        if a in self.adjacency and b in self.adjacency[a]:
            self.adjacency[a].remove(b)
        if b in self.adjacency and a in self.adjacency[b]:
            self.adjacency[b].remove(a)

    def neighbors(self, node_id: str) -> List[str]:
        return list(self.adjacency.get(node_id, []))

    def shortest_path(self, src: str, dst: str) -> Optional[List[str]]:
        if src == dst:
            return [src]
        visited = {src}
        queue = [(src, [src])]
        while queue:
            cur, path = queue.pop(0)
            for nb in self.neighbors(cur):
                if nb in visited:
                    continue
                if nb == dst:
                    return path + [nb]
                visited.add(nb)
                queue.append((nb, path + [nb]))
        return None

    def broadcast_sync(self, nodes: Dict[str, Any], max_hops: int = 8) -> int:
        rounds = 0
        changed = True
        while changed and rounds < max_hops:
            changed = False
            rounds += 1
            for nid, node in nodes.items():
                for peer in self.neighbors(nid):
                    if peer not in nodes:
                        continue
                    stats = node.sync_with(peer)
                    if stats.success and (stats.events_sent + stats.events_received) > 0:
                        changed = True
        return rounds