"""
fitness_evaluator.py — Natural selection for cognitive approaches.

Computes per-chromosome fitness signals from run-time metrics so that
CognitiveDNA.evolve() can reward successful strategies and prune failures.
"""

from typing import Dict, Optional


class FitnessEvaluator:
    """
    Translates run-time performance metrics into fitness signals
    consumed by CognitiveDNA.evolve().
    """

    def __init__(self):
        # Rolling history of raw metric samples (capped to avoid memory bloat)
        self._history: Dict[str, list] = {
            "task_success_rate": [],
            "response_quality": [],
            "memory_vitality": [],
            "mood_valence": [],
            "exploration_score": [],
            "creativity_score": [],
        }
        self._cap = 50  # Max samples retained per metric

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record(self, metric: str, value: float):
        """Record a single metric observation (value in [0, 1])."""
        if metric not in self._history:
            self._history[metric] = []
        buf = self._history[metric]
        buf.append(max(0.0, min(1.0, value)))
        if len(buf) > self._cap:
            buf.pop(0)

    def evaluate(
        self,
        *,
        task_success_rate: Optional[float] = None,
        response_quality: Optional[float] = None,
        memory_vitality: Optional[float] = None,
        mood_valence: Optional[float] = None,
        exploration_score: Optional[float] = None,
        creativity_score: Optional[float] = None,
        max_abstraction_level: int = 0,
        avg_connections: float = 0.0,
        mood: Optional[dict] = None,
    ) -> Dict[str, float]:
        """
        Compute fitness signals for each chromosome.

        Returns a dict keyed by chromosome name → fitness ∈ [0, 1].
        """
        # Convenience: unpack mood dict if provided
        if mood:
            mood_valence = mood_valence or mood.get("valence", 0.5)
            exploration_score = exploration_score or mood.get("curiosity", 0.5)

        # Helper — use provided value, fall back to rolling average
        def resolve(key: str, direct: Optional[float]) -> float:
            if direct is not None:
                self.record(key, direct)
                return direct
            buf = self._history.get(key, [])
            return sum(buf) / len(buf) if buf else 0.5

        r_quality = resolve("response_quality", response_quality)
        t_success = resolve("task_success_rate", task_success_rate)
        m_vitality = resolve("memory_vitality", memory_vitality)
        m_valence = resolve("mood_valence", mood_valence)
        e_score = resolve("exploration_score", exploration_score)
        c_score = resolve("creativity_score", creativity_score)

        # Per-chromosome fitness formulae
        fitness: Dict[str, float] = {
            # Good reasoning → high task success + response quality
            "reasoning": _clamp(0.6 * t_success + 0.4 * r_quality),

            # Good communication → response quality + positive mood
            "communication": _clamp(0.7 * r_quality + 0.3 * _norm_valence(m_valence)),

            # Exploration is driven by curiosity
            "exploration": _clamp(e_score),

            # Memory strategy → how alive the memory ecology is
            "memory_strategy": _clamp(
                0.5 * m_vitality
                + 0.3 * min(1.0, avg_connections / 3.0)
                + 0.2 * min(1.0, max_abstraction_level / 5.0)
            ),

            # Risk tolerance correlates with arousal/confidence
            "risk_tolerance": _clamp(t_success * 0.8 + 0.2 * r_quality),

            # Creativity → abstraction depth + creativity score
            "creativity": _clamp(
                0.5 * c_score
                + 0.3 * min(1.0, max_abstraction_level / 5.0)
                + 0.2 * t_success
            ),
        }

        return fitness

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def summary(self) -> Dict[str, float]:
        """Return rolling averages for all tracked metrics."""
        return {
            key: (sum(buf) / len(buf) if buf else 0.5)
            for key, buf in self._history.items()
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _norm_valence(v: float) -> float:
    """Normalise valence from [-1, 1] to [0, 1]."""
    return (v + 1.0) / 2.0
