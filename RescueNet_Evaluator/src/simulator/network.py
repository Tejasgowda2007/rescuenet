"""
Simulator Network Partition Manager.

Allows programmatic and random topological partitioning of N nodes
to simulate mountain blockages, power failures, and radio dead zones.
"""

from __future__ import annotations
import random
from typing import List, Dict, Set, Tuple
from transport.in_memory import InMemoryTransport


class PartitionManager:
    """
    Controls dynamic link cuts and heals across an InMemoryTransport.
    """

    def __init__(self, transport: InMemoryTransport, node_ids: List[str]) -> None:
        self.transport = transport
        self.node_ids = list(node_ids)

    def set_partitions(self, groups: List[List[str]]) -> None:
        """
        Partition nodes into mutually exclusive connected islands.
        Nodes within the same group can communicate; across groups, links are cut.
        """
        # Step 1: Clear previous cuts
        self.transport.heal_all()

        # Step 2: Build lookup of node -> group_index
        group_map = {}
        for idx, grp in enumerate(groups):
            for nid in grp:
                group_map[nid] = idx

        # Step 3: Cut links between nodes in different groups
        for i, n1 in enumerate(self.node_ids):
            for j in range(i + 1, len(self.node_ids)):
                n2 = self.node_ids[j]
                g1 = group_map.get(n1, -1)
                g2 = group_map.get(n2, -2)
                if g1 != g2:
                    self.transport.cut_link(n1, n2)

    def random_partition(self, rng: random.Random, min_groups: int = 2, max_groups: int = 3) -> List[List[str]]:
        """
        Randomly partition the nodes into 2 or more isolated components.
        """
        shuffled = list(self.node_ids)
        rng.shuffle(shuffled)

        k = rng.randint(min_groups, min(max_groups, len(shuffled)))
        groups: List[List[str]] = [[] for _ in range(k)]

        # Ensure each group has at least one node
        for i in range(k):
            groups[i].append(shuffled[i])

        # Distribute remaining nodes
        for nid in shuffled[k:]:
            g_idx = rng.randint(0, k - 1)
            groups[g_idx].append(nid)

        self.set_partitions(groups)
        return groups

    def heal_all(self) -> None:
        """Restore all network links so every node can reach every other node."""
        self.transport.heal_all()

    def get_connected_components(self) -> List[List[str]]:
        """
        Compute current connected components via simple BFS.
        """
        visited: Set[str] = set()
        components: List[List[str]] = []

        for nid in self.node_ids:
            if nid not in visited:
                comp = []
                queue = [nid]
                visited.add(nid)
                while queue:
                    curr = queue.pop(0)
                    comp.append(curr)
                    for other in self.node_ids:
                        if other not in visited and self.transport.is_connected(curr, other):
                            visited.add(other)
                            queue.append(other)
                components.append(sorted(comp))

        return components
