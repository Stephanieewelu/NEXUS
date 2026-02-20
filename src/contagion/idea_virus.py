"""
idea_virus.py — Ideas that spread and mutate through the agent's cognition.

An IdeaVirus is a self-replicating concept: each time it is "encountered"
it has a chance of infecting (entering) the meme pool, mutating, or dying.
"""

import random
import time
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class IdeaVirus:
    """A self-replicating idea that can spread and mutate."""

    id: str
    core_idea: str
    fitness: float = 0.5          # How "sticky" this idea is
    mutation_rate: float = 0.1
    spread_rate: float = 0.3
    virulence: float = 0.5        # How strongly it influences cognition
    generation: int = 0
    lineage: List[str] = field(default_factory=list)
    born_at: float = field(default_factory=time.time)
    encounter_count: int = 0

    # ------------------------------------------------------------------
    # Spread mechanics
    # ------------------------------------------------------------------

    def encounter(self) -> bool:
        """Simulate one exposure event. Returns True if the idea 'infects'."""
        self.encounter_count += 1
        return random.random() < self.spread_rate * self.fitness

    def mutate(self) -> "IdeaVirus":
        """Spawn a mutated child idea."""
        modifiers = [
            "inverted", "scaled", "applied to", "merged with",
            "filtered through", "abstracted from",
        ]
        child_idea = f"[{random.choice(modifiers)}] {self.core_idea}"
        child = IdeaVirus(
            id=f"{self.id}_m{self.generation + 1}",
            core_idea=child_idea,
            fitness=max(0.0, min(1.0, self.fitness + random.gauss(0, 0.1))),
            mutation_rate=self.mutation_rate,
            spread_rate=max(0.0, min(1.0, self.spread_rate + random.gauss(0, 0.05))),
            virulence=max(0.0, min(1.0, self.virulence + random.gauss(0, 0.05))),
            generation=self.generation + 1,
            lineage=self.lineage + [self.id],
        )
        return child

    def is_extinct(self) -> bool:
        """Return True if the virus has too low fitness to survive."""
        return self.fitness < 0.1 and self.encounter_count > 10

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "core_idea": self.core_idea,
            "fitness": self.fitness,
            "generation": self.generation,
            "encounter_count": self.encounter_count,
            "lineage": self.lineage,
        }
