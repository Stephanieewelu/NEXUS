"""
meme_pool.py — A shared marketplace of ideas (memes) that compete for
cognitive real-estate inside NEXUS.

Memes enter the pool from conversations and dream insights, compete via
fitness, and the fittest ones influence the agent's system prompt.
"""

import random
import time
from typing import Dict, List, Optional

from contagion.idea_virus import IdeaVirus


class MemePool:
    """Ecosystem of competing ideas that influence agent cognition."""

    def __init__(self, capacity: int = 50):
        self.capacity = capacity
        self.pool: Dict[str, IdeaVirus] = {}
        self.graveyard: List[dict] = []
        self.tick_count = 0

    # ------------------------------------------------------------------
    # Pool management
    # ------------------------------------------------------------------

    def introduce(
        self,
        idea: str,
        fitness: float = 0.5,
        spread_rate: float = 0.3,
    ) -> IdeaVirus:
        """Introduce a new idea virus into the pool."""
        vid = f"virus_{int(time.time()*1000)}_{random.randint(0,999)}"
        virus = IdeaVirus(
            id=vid,
            core_idea=idea,
            fitness=fitness,
            spread_rate=spread_rate,
        )
        self.pool[vid] = virus
        return virus

    def tick(self):
        """
        Run one ecological cycle:
        1. Encounter phase — ideas compete for exposure
        2. Mutation — successful ideas may spawn variants
        3. Extinction — failed ideas die
        4. Capacity control
        """
        self.tick_count += 1

        extinct_ids: List[str] = []
        new_viruses: List[IdeaVirus] = []

        for vid, virus in list(self.pool.items()):
            # Encounter
            if virus.encounter():
                virus.fitness = min(1.0, virus.fitness + 0.02)
                # Probabilistic mutation
                if random.random() < virus.mutation_rate:
                    child = virus.mutate()
                    new_viruses.append(child)
            else:
                virus.fitness = max(0.0, virus.fitness - 0.01)

            if virus.is_extinct():
                extinct_ids.append(vid)

        # Remove extinct
        for vid in extinct_ids:
            virus = self.pool.pop(vid)
            self.graveyard.append(virus.to_dict())

        # Add mutants
        for virus in new_viruses:
            self.pool[virus.id] = virus

        # Capacity control — remove lowest fitness
        if len(self.pool) > self.capacity:
            sorted_pool = sorted(
                self.pool.items(), key=lambda x: x[1].fitness
            )
            to_remove = len(self.pool) - self.capacity
            for vid, virus in sorted_pool[:to_remove]:
                self.pool.pop(vid)
                self.graveyard.append(virus.to_dict())

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def most_fit(self, top_k: int = 5) -> List[IdeaVirus]:
        """Return the fittest ideas currently in the pool."""
        return sorted(
            self.pool.values(), key=lambda v: v.fitness, reverse=True
        )[:top_k]

    def get_cognitive_influence(self) -> str:
        """
        Summarise the top ideas as a prompt injection for the system prompt.
        """
        top = self.most_fit(top_k=3)
        if not top:
            return ""
        lines = ["Active memes influencing cognition:"]
        for v in top:
            lines.append(
                f"  [{v.fitness:.2f}] {v.core_idea[:100]}"
            )
        return "\n".join(lines)

    def stats(self) -> dict:
        vitalities = [v.fitness for v in self.pool.values()]
        return {
            "active": len(self.pool),
            "extinct": len(self.graveyard),
            "avg_fitness": sum(vitalities) / max(len(vitalities), 1),
            "tick": self.tick_count,
        }
