"""
memory_organisms.py — Individual memory units that live, compete, and merge.

A MemoryOrganism is the atomic unit of the memory ecology: it has vital signs,
connections to peers, and a lifecycle governed by energy, access, and age.
"""

import time
import math
import random
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class MemoryOrganism:
    """A memory that lives, grows, decays, and can reproduce."""

    id: str
    content: str
    memory_type: str   # "episodic" | "semantic" | "procedural" | "emotional"

    # ---- Vital signs ------------------------------------------------
    energy: float = 1.0           # Depletes over time; recharged on access
    strength: float = 0.5         # Reliability / consolidation level
    emotional_charge: float = 0.0  # −1 (negative) … +1 (positive)

    # ---- Ecological properties --------------------------------------
    connections: List[str] = field(default_factory=list)   # Linked memory IDs
    nutrients: dict = field(default_factory=dict)          # What it "feeds" on
    symbiotes: List[str] = field(default_factory=list)     # Mutually beneficial
    parasites: List[str] = field(default_factory=list)     # Contradicting mems

    # ---- Lifecycle --------------------------------------------------
    birth_time: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    access_count: int = 0
    reproduction_count: int = 0

    # ---- Genetics ---------------------------------------------------
    tags: List[str] = field(default_factory=list)
    abstraction_level: int = 0    # 0=raw; higher=more abstracted

    # ---- Metadata ---------------------------------------------------
    context: dict = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Derived properties
    # ------------------------------------------------------------------

    @property
    def age(self) -> float:
        return time.time() - self.birth_time

    @property
    def vitality(self) -> float:
        """Overall health of this memory (0–1)."""
        recency_bonus = math.exp(-0.001 * (time.time() - self.last_accessed))
        access_bonus = min(1.0, self.access_count / 10.0)
        connection_bonus = min(1.0, len(self.connections) / 5.0)

        return (
            0.30 * self.energy
            + 0.25 * self.strength
            + 0.20 * recency_bonus
            + 0.15 * access_bonus
            + 0.10 * connection_bonus
        )

    # ------------------------------------------------------------------
    # Lifecycle methods
    # ------------------------------------------------------------------

    def metabolize(self, delta_time: float = 1.0):
        """Consume energy over time (natural memory decay)."""
        base_decay = 0.001 * delta_time
        # Emotional memories decay slower
        emotional_factor = 1.0 - (abs(self.emotional_charge) * 0.5)
        # Well-connected memories decay slower
        connection_factor = 1.0 / (1.0 + len(self.connections) * 0.2)
        self.energy -= base_decay * emotional_factor * connection_factor
        self.energy = max(0.0, self.energy)

    def access(self):
        """Recharge energy when this memory is accessed."""
        self.last_accessed = time.time()
        self.access_count += 1
        self.energy = min(1.0, self.energy + 0.2)
        self.strength = min(1.0, self.strength + 0.05)

    def can_reproduce(self) -> bool:
        """Check whether this memory has enough energy to spawn offspring."""
        return (
            self.energy > 0.7
            and self.access_count > 3
            and self.reproduction_count < 5
        )

    def reproduce_with(
        self, other: "MemoryOrganism"
    ) -> Optional["MemoryOrganism"]:
        """
        'Sexual' reproduction — combine two memories into an abstracted child.

        Returns a new MemoryOrganism or None if this memory can't reproduce.
        """
        if not self.can_reproduce():
            return None

        self.reproduction_count += 1
        self.energy -= 0.3

        child = MemoryOrganism(
            id=f"mem_{int(time.time() * 1000)}_{random.randint(0, 999)}",
            content=(
                f"[SYNTHESIS] Combining: '{self.content[:50]}' "
                f"+ '{other.content[:50]}'"
            ),
            memory_type="semantic",
            energy=0.6,
            strength=(self.strength + other.strength) / 2.0,
            emotional_charge=(self.emotional_charge + other.emotional_charge) / 2.0,
            connections=[self.id, other.id],
            tags=list(set(self.tags + other.tags)),
            abstraction_level=max(self.abstraction_level, other.abstraction_level) + 1,
            context={
                "parents": [self.id, other.id],
                "synthesis_type": "reproduction",
            },
        )

        # Register the child in each parent's connections
        self.connections.append(child.id)
        other.connections.append(child.id)

        return child

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "memory_type": self.memory_type,
            "energy": self.energy,
            "strength": self.strength,
            "emotional_charge": self.emotional_charge,
            "connections": self.connections,
            "symbiotes": self.symbiotes,
            "parasites": self.parasites,
            "birth_time": self.birth_time,
            "last_accessed": self.last_accessed,
            "access_count": self.access_count,
            "reproduction_count": self.reproduction_count,
            "tags": self.tags,
            "abstraction_level": self.abstraction_level,
            "context": self.context,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryOrganism":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
