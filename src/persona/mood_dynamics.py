"""
mood_dynamics.py — Emotional state machine for the agent.

Mood is a four-dimensional vector that shifts in response to inputs,
interaction quality, and internal state.
"""

import math
import random
from typing import Dict


class MoodState:
    """
    Four-dimensional emotional state:
        valence   — negative (−1) to positive (+1)
        arousal   — calm (0) to excited (1)
        curiosity — bored (0) to fascinated (1)
        confidence— uncertain (0) to confident (1)
    """

    def __init__(self):
        self.valence: float = 0.0
        self.arousal: float = 0.5
        self.curiosity: float = 0.7
        self.confidence: float = 0.5

    # ------------------------------------------------------------------
    # Update dynamics
    # ------------------------------------------------------------------

    def update(
        self,
        user_input: str,
        response_text: str,
        interaction_count: int,
    ):
        """Shift mood dimensions based on a completed interaction."""
        input_charge = _sentiment(user_input)
        has_question = "?" in user_input
        input_length = len(user_input)

        # Valence drifts toward the input's emotional tone
        self.valence = _smooth(self.valence, input_charge, alpha=0.3)
        self.valence = _clamp(self.valence, -1.0, 1.0)

        # Arousal increases with long/novel inputs
        novelty = min(1.0, input_length / 500.0)
        self.arousal = _smooth(self.arousal, novelty, alpha=0.2)

        # Curiosity increases with questions, slowly decays otherwise
        if has_question:
            self.curiosity = min(1.0, self.curiosity + 0.1)
        else:
            self.curiosity = max(0.2, self.curiosity - 0.02)

        # Confidence grows slowly with experience
        self.confidence = min(1.0, self.confidence + 0.01)

        # Occasional random micro-fluctuations (emotional noise)
        self.valence += random.gauss(0, 0.01)
        self.arousal += random.gauss(0, 0.01)

    def to_dict(self) -> Dict[str, float]:
        return {
            "valence": round(self.valence, 4),
            "arousal": round(self.arousal, 4),
            "curiosity": round(self.curiosity, 4),
            "confidence": round(self.confidence, 4),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MoodState":
        ms = cls()
        ms.valence = data.get("valence", 0.0)
        ms.arousal = data.get("arousal", 0.5)
        ms.curiosity = data.get("curiosity", 0.7)
        ms.confidence = data.get("confidence", 0.5)
        return ms

    def describe(self) -> str:
        v = "positive" if self.valence > 0.2 else ("negative" if self.valence < -0.2 else "neutral")
        a = "excited" if self.arousal > 0.7 else ("calm" if self.arousal < 0.3 else "engaged")
        return (
            f"mood={v} | arousal={a} | "
            f"curiosity={self.curiosity:.2f} | confidence={self.confidence:.2f}"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_POSITIVE_WORDS = {
    "good", "great", "love", "awesome", "amazing", "wonderful",
    "happy", "excited", "beautiful", "brilliant", "fantastic",
    "thank", "please", "help", "interesting", "cool", "nice",
}
_NEGATIVE_WORDS = {
    "bad", "hate", "terrible", "awful", "horrible", "sad",
    "angry", "wrong", "fail", "stupid", "boring", "ugly",
    "never", "worst", "problem", "error", "broken",
}


def _sentiment(text: str) -> float:
    """Naïve sentiment score in [−1, +1]."""
    words = text.lower().split()
    pos = sum(1 for w in words if w.strip(".,!?;:'\"") in _POSITIVE_WORDS)
    neg = sum(1 for w in words if w.strip(".,!?;:'\"") in _NEGATIVE_WORDS)
    total = pos + neg
    if total == 0:
        return 0.0
    return (pos - neg) / total


def _smooth(current: float, target: float, alpha: float = 0.3) -> float:
    return current * (1.0 - alpha) + target * alpha


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))
