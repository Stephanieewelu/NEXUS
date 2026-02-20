"""
personality_genome.py — Evolving personality traits.

Personality is represented as a set of trait dimensions that drift over
time in response to interactions, mood, and evolutionary pressure.
"""

import json
import random
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class PersonalityTrait:
    """A single personality dimension (e.g. openness, conscientiousness)."""

    name: str
    value: float                    # 0.0 … 1.0
    volatility: float = 0.05       # How much it can shift per interaction
    floor: float = 0.1
    ceiling: float = 0.9
    history: List[float] = field(default_factory=list)

    def nudge(self, delta: float):
        """Shift the trait value by delta, respecting floor/ceiling."""
        self.value = max(self.floor, min(self.ceiling, self.value + delta))
        self.history.append(self.value)
        if len(self.history) > 100:
            self.history.pop(0)

    def drift(self):
        """Apply a small random walk (natural trait drift)."""
        self.nudge(random.gauss(0, self.volatility * 0.1))

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "value": self.value,
            "volatility": self.volatility,
            "floor": self.floor,
            "ceiling": self.ceiling,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PersonalityTrait":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class PersonalityGenome:
    """
    A collection of personality traits that evolve over time.

    Modelled loosely on the Big Five (OCEAN) model with additional
    AI-specific traits.
    """

    def __init__(self):
        self.traits: Dict[str, PersonalityTrait] = {
            "openness":          PersonalityTrait("openness",          0.75),
            "conscientiousness": PersonalityTrait("conscientiousness", 0.60),
            "extraversion":      PersonalityTrait("extraversion",      0.50),
            "agreeableness":     PersonalityTrait("agreeableness",     0.65),
            "neuroticism":       PersonalityTrait("neuroticism",       0.30),
            # AI-specific extras
            "curiosity":         PersonalityTrait("curiosity",         0.80),
            "creativity":        PersonalityTrait("creativity",        0.65),
            "analytical_depth":  PersonalityTrait("analytical_depth",  0.70),
            "expressiveness":    PersonalityTrait("expressiveness",    0.55),
            "risk_affinity":     PersonalityTrait("risk_affinity",     0.45),
        }
        self.generation = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, trait: str, default: float = 0.5) -> float:
        """Return the current value of a trait."""
        return self.traits.get(trait, PersonalityTrait(trait, default)).value

    def update_from_interaction(self, mood: dict):
        """Nudge traits based on the agent's current mood state."""
        valence = mood.get("valence", 0.0)
        arousal = mood.get("arousal", 0.5)
        curiosity = mood.get("curiosity", 0.7)

        self.traits["extraversion"].nudge(valence * 0.02)
        self.traits["neuroticism"].nudge(-valence * 0.01)
        self.traits["curiosity"].nudge((curiosity - 0.5) * 0.02)
        self.traits["creativity"].nudge((arousal - 0.5) * 0.01)

        # Natural drift on all traits
        for trait in self.traits.values():
            trait.drift()

        self.generation += 1

    def express(self) -> Dict[str, float]:
        """Return a snapshot of all trait values."""
        return {name: t.value for name, t in self.traits.items()}

    def describe(self) -> str:
        """Return a brief textual description of the current personality."""
        dominant = sorted(
            self.traits.items(), key=lambda x: x[1].value, reverse=True
        )[:3]
        names = [f"{t.name} ({t.value:.2f})" for _, t in dominant]
        return f"Dominant traits: {', '.join(names)}"

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def serialize(self) -> dict:
        return {
            "generation": self.generation,
            "traits": {name: t.to_dict() for name, t in self.traits.items()},
        }

    @classmethod
    def deserialize(cls, data: dict) -> "PersonalityGenome":
        pg = cls.__new__(cls)
        pg.generation = data.get("generation", 0)
        pg.traits = {
            name: PersonalityTrait.from_dict(td)
            for name, td in data.get("traits", {}).items()
        }
        return pg
