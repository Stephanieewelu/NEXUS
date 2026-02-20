"""
cultural_evolution.py — Group learning dynamics across idea generations.

Tracks how meme fitness distributions evolve over time, detecting
accelerating innovation vs. stagnation.
"""

from typing import Dict, List

from contagion.meme_pool import MemePool


class CulturalEvolution:
    """
    Observes the MemePool over time and derives cultural-level trends:
    - Idea diversity (Shannon entropy)
    - Innovation rate (new mutations per tick)
    - Dominant paradigms (top recurring themes)
    """

    def __init__(self, pool: MemePool):
        self.pool = pool
        self.history: List[dict] = []

    # ------------------------------------------------------------------
    # Observation
    # ------------------------------------------------------------------

    def observe(self):
        """Record a cultural snapshot of the current meme pool state."""
        stats = self.pool.stats()
        top = self.pool.most_fit(top_k=5)
        snapshot = {
            "tick": stats["tick"],
            "active": stats["active"],
            "avg_fitness": stats["avg_fitness"],
            "dominant_ideas": [v.core_idea[:60] for v in top],
            "diversity": self._diversity_index(),
        }
        self.history.append(snapshot)
        if len(self.history) > 500:
            self.history = self.history[-500:]

    def _diversity_index(self) -> float:
        """Shannon entropy of idea generations as a diversity proxy."""
        import math
        gen_counts: Dict[int, int] = {}
        for v in self.pool.pool.values():
            gen_counts[v.generation] = gen_counts.get(v.generation, 0) + 1

        total = sum(gen_counts.values())
        if total == 0:
            return 0.0

        entropy = 0.0
        for count in gen_counts.values():
            p = count / total
            if p > 0:
                entropy -= p * math.log2(p)

        return round(entropy, 4)

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def innovation_trend(self, window: int = 10) -> str:
        """Return 'accelerating', 'stable', or 'stagnating'."""
        if len(self.history) < 2 * window:
            return "insufficient_data"

        recent_diversity = sum(
            s["diversity"] for s in self.history[-window:]
        ) / window
        earlier_diversity = sum(
            s["diversity"] for s in self.history[-(2 * window) : -window]
        ) / window

        delta = recent_diversity - earlier_diversity
        if delta > 0.05:
            return "accelerating"
        if delta < -0.05:
            return "stagnating"
        return "stable"

    def report(self) -> str:
        if not self.history:
            return "No cultural history recorded yet."

        latest = self.history[-1]
        trend = self.innovation_trend()
        lines = [
            "=== Cultural Evolution Report ===",
            f"Tick:             {latest['tick']}",
            f"Active memes:     {latest['active']}",
            f"Avg fitness:      {latest['avg_fitness']:.3f}",
            f"Diversity index:  {latest['diversity']:.4f}",
            f"Innovation trend: {trend}",
        ]
        if latest["dominant_ideas"]:
            lines.append("Dominant ideas:")
            for idea in latest["dominant_ideas"][:3]:
                lines.append(f"  • {idea}")
        return "\n".join(lines)
