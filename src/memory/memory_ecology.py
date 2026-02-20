"""
memory_ecology.py — Living, decaying, growing memory as an ecosystem.

Memories are MemoryOrganisms that are born, age, compete for resources,
reproduce, and die — mirroring biological population dynamics.
"""

import time
import random
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from memory.memory_organisms import MemoryOrganism


class MemoryEcology:
    """An ecosystem where memories live, compete, cooperate, and evolve."""

    def __init__(self, carrying_capacity: int = 1000):
        self.organisms: Dict[str, MemoryOrganism] = {}
        self.carrying_capacity = carrying_capacity
        self.graveyard: List[dict] = []   # Dead memories (archaeological record)
        self.epoch = 0
        self.ecological_history: List[dict] = []

    # ------------------------------------------------------------------
    # Birth
    # ------------------------------------------------------------------

    def birth(
        self,
        content: str,
        memory_type: str = "episodic",
        tags: Optional[List[str]] = None,
        emotional_charge: float = 0.0,
        context: Optional[dict] = None,
    ) -> MemoryOrganism:
        """Create and register a new memory in the ecology."""
        organism = MemoryOrganism(
            id=f"mem_{int(time.time() * 1000)}_{random.randint(0, 9999)}",
            content=content,
            memory_type=memory_type,
            tags=tags or [],
            emotional_charge=emotional_charge,
            context=context or {},
        )
        self._establish_connections(organism)
        self.organisms[organism.id] = organism
        return organism

    # ------------------------------------------------------------------
    # Connections
    # ------------------------------------------------------------------

    def _establish_connections(self, new_mem: MemoryOrganism):
        """Find and establish connections with existing memories via tags."""
        for mid, existing in self.organisms.items():
            shared_tags = set(new_mem.tags) & set(existing.tags)
            if not shared_tags:
                continue

            connection_strength = len(shared_tags) / max(
                len(new_mem.tags), len(existing.tags), 1
            )
            if connection_strength > 0.2:
                new_mem.connections.append(mid)
                existing.connections.append(new_mem.id)

                # High overlap → symbiosis
                if connection_strength > 0.6:
                    new_mem.symbiotes.append(mid)
                    existing.symbiotes.append(new_mem.id)

    # ------------------------------------------------------------------
    # Recall
    # ------------------------------------------------------------------

    def recall(
        self,
        query_tags: Optional[List[str]] = None,
        query_type: Optional[str] = None,
        emotional_range: Optional[Tuple[float, float]] = None,
        top_k: int = 5,
    ) -> List[MemoryOrganism]:
        """
        Retrieve memories ranked by ecological fitness + query relevance.
        Accessing a memory recharges it.
        """
        scored = []
        for mem in self.organisms.values():
            score = mem.vitality

            if query_tags:
                tag_overlap = len(set(query_tags) & set(mem.tags))
                score += tag_overlap * 0.3

            if query_type and mem.memory_type == query_type:
                score += 0.2

            if emotional_range is not None:
                if emotional_range[0] <= mem.emotional_charge <= emotional_range[1]:
                    score += 0.15

            scored.append((mem, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        results = []
        for mem, _ in scored[:top_k]:
            mem.access()
            results.append(mem)

        return results

    # ------------------------------------------------------------------
    # Ecological tick
    # ------------------------------------------------------------------

    def tick(self):
        """Run one ecological cycle: metabolise → die → reproduce → cap."""
        self.epoch += 1

        dead_ids: List[str] = []
        reproduction_queue: List[Tuple[str, str]] = []

        # Phase 1: Metabolism
        for mid, mem in self.organisms.items():
            mem.metabolize()

            if mem.energy <= 0.01 and mem.vitality < 0.1:
                dead_ids.append(mid)
                continue

            if mem.can_reproduce() and mem.symbiotes:
                partner_id = random.choice(mem.symbiotes)
                if partner_id in self.organisms:
                    reproduction_queue.append((mid, partner_id))

        # Phase 2: Apoptosis
        for mid in dead_ids:
            mem = self.organisms.pop(mid)
            self.graveyard.append({
                "id": mid,
                "content": mem.content,
                "lived_epochs": self.epoch,
                "final_vitality": mem.vitality,
                "cause_of_death": "energy_depletion",
            })
            print(
                f"  💀 Memory died: '{mem.content[:40]}...' "
                f"(lived {mem.access_count} accesses)"
            )

        # Phase 3: Reproduction (max 3 births per tick)
        for parent1_id, parent2_id in reproduction_queue[:3]:
            if parent1_id in self.organisms and parent2_id in self.organisms:
                child = self.organisms[parent1_id].reproduce_with(
                    self.organisms[parent2_id]
                )
                if child:
                    self.organisms[child.id] = child
                    print(
                        f"  🌱 Memory born: '{child.content[:40]}...' "
                        f"(abstraction level {child.abstraction_level})"
                    )

        # Phase 4: Population control
        if len(self.organisms) > self.carrying_capacity:
            self._ecological_collapse()

        # Record history
        self.ecological_history.append({
            "epoch": self.epoch,
            "population": len(self.organisms),
            "births": len(reproduction_queue),
            "deaths": len(dead_ids),
            "avg_vitality": (
                sum(m.vitality for m in self.organisms.values())
                / max(len(self.organisms), 1)
            ),
        })

    def _ecological_collapse(self):
        """Remove weakest memories when over carrying capacity."""
        sorted_mems = sorted(
            self.organisms.items(), key=lambda x: x[1].vitality
        )
        to_remove = len(self.organisms) - self.carrying_capacity
        for mid, mem in sorted_mems[:to_remove]:
            self.organisms.pop(mid)
            self.graveyard.append({
                "id": mid,
                "content": mem.content,
                "cause_of_death": "ecological_collapse",
            })

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def get_ecology_stats(self) -> dict:
        if not self.organisms:
            return {
                "epoch": self.epoch,
                "population": 0,
                "carrying_capacity": self.carrying_capacity,
                "graveyard_size": len(self.graveyard),
            }

        type_counts: dict = defaultdict(int)
        for mem in self.organisms.values():
            type_counts[mem.memory_type] += 1

        vitalities = [m.vitality for m in self.organisms.values()]
        connections_counts = [len(m.connections) for m in self.organisms.values()]

        return {
            "epoch": self.epoch,
            "population": len(self.organisms),
            "carrying_capacity": self.carrying_capacity,
            "type_distribution": dict(type_counts),
            "avg_vitality": sum(vitalities) / len(vitalities),
            "avg_connections": sum(connections_counts) / len(connections_counts),
            "max_abstraction": max(
                (m.abstraction_level for m in self.organisms.values()), default=0
            ),
            "graveyard_size": len(self.graveyard),
            "total_accesses": sum(m.access_count for m in self.organisms.values()),
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def serialize(self) -> dict:
        return {
            "epoch": self.epoch,
            "carrying_capacity": self.carrying_capacity,
            "organisms": {mid: m.to_dict() for mid, m in self.organisms.items()},
            "graveyard": self.graveyard[-100:],  # Keep last 100
        }

    @classmethod
    def deserialize(cls, data: dict) -> "MemoryEcology":
        ecology = cls(carrying_capacity=data.get("carrying_capacity", 1000))
        ecology.epoch = data.get("epoch", 0)
        ecology.graveyard = data.get("graveyard", [])
        for mid, mdata in data.get("organisms", {}).items():
            try:
                ecology.organisms[mid] = MemoryOrganism.from_dict(mdata)
            except Exception:
                pass  # Skip corrupt entries
        return ecology
