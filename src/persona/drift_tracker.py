"""
drift_tracker.py — Track and report personality / cognitive evolution over time.
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional


class DriftTracker:
    """Records snapshots of cognitive & personality state across generations."""

    def __init__(self):
        self.snapshots: List[dict] = []
        self.milestone_log: List[dict] = []

    # ------------------------------------------------------------------
    # Snapshot recording
    # ------------------------------------------------------------------

    def record_snapshot(
        self,
        generation: int,
        genome_hash: str,
        mood: dict,
        personality: dict,
        ecology_stats: dict,
        interaction_count: int,
    ):
        """Store a full state snapshot."""
        snapshot = {
            "timestamp": datetime.now().isoformat(),
            "generation": generation,
            "genome_hash": genome_hash,
            "mood": mood,
            "personality": personality,
            "ecology": ecology_stats,
            "interaction_count": interaction_count,
        }
        self.snapshots.append(snapshot)

        # Keep the last 200 snapshots to avoid unbounded growth
        if len(self.snapshots) > 200:
            self.snapshots = self.snapshots[-200:]

    def log_milestone(self, description: str, metadata: Optional[dict] = None):
        """Record a significant evolutionary event."""
        self.milestone_log.append({
            "timestamp": datetime.now().isoformat(),
            "description": description,
            "metadata": metadata or {},
        })

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def personality_drift(self, window: int = 10) -> Dict[str, float]:
        """
        Compute the average change in personality trait values over the
        last `window` snapshots vs the previous `window` snapshots.
        """
        if len(self.snapshots) < 2 * window:
            return {}

        recent = self.snapshots[-window:]
        earlier = self.snapshots[-(2 * window) : -window]

        def avg_trait(snaps: list, trait: str) -> float:
            vals = [s["personality"].get(trait, 0.5) for s in snaps]
            return sum(vals) / max(len(vals), 1)

        all_traits = set(self.snapshots[-1]["personality"].keys())
        return {
            trait: avg_trait(recent, trait) - avg_trait(earlier, trait)
            for trait in all_traits
        }

    def mood_trend(self, window: int = 5) -> Dict[str, float]:
        """Return average mood over the last `window` snapshots."""
        recent = self.snapshots[-window:] if self.snapshots else []
        if not recent:
            return {}

        dims = ["valence", "arousal", "curiosity", "confidence"]
        return {
            dim: sum(s["mood"].get(dim, 0.0) for s in recent) / len(recent)
            for dim in dims
        }

    def genome_evolution_rate(self, window: int = 10) -> float:
        """
        Fraction of snapshots in the last `window` where the genome hash
        changed (proxy for evolution speed).
        """
        snaps = self.snapshots[-window:]
        if len(snaps) < 2:
            return 0.0
        changes = sum(
            1 for i in range(1, len(snaps))
            if snaps[i]["genome_hash"] != snaps[i - 1]["genome_hash"]
        )
        return changes / (len(snaps) - 1)

    def summary_report(self) -> str:
        """Return a human-readable drift summary."""
        drift = self.personality_drift()
        trend = self.mood_trend()
        evo_rate = self.genome_evolution_rate()

        lines = ["=== Drift Tracker Report ==="]

        lines.append(f"\nSnapshots recorded: {len(self.snapshots)}")
        lines.append(f"Milestones logged:  {len(self.milestone_log)}")
        lines.append(f"Genome evolution rate: {evo_rate:.1%}")

        if trend:
            lines.append("\nRecent mood trend:")
            for dim, val in trend.items():
                lines.append(f"  {dim:12s}: {val:+.3f}")

        if drift:
            significant = {k: v for k, v in drift.items() if abs(v) > 0.01}
            if significant:
                lines.append("\nPersonality drift (recent vs earlier):")
                for trait, delta in sorted(
                    significant.items(), key=lambda x: abs(x[1]), reverse=True
                ):
                    direction = "▲" if delta > 0 else "▼"
                    lines.append(f"  {direction} {trait:20s}: {delta:+.3f}")

        if self.milestone_log:
            lines.append("\nRecent milestones:")
            for m in self.milestone_log[-5:]:
                lines.append(f"  [{m['timestamp'][:16]}] {m['description']}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def serialize(self) -> dict:
        return {
            "snapshots": self.snapshots,
            "milestones": self.milestone_log,
        }

    @classmethod
    def deserialize(cls, data: dict) -> "DriftTracker":
        dt = cls()
        dt.snapshots = data.get("snapshots", [])
        dt.milestone_log = data.get("milestones", [])
        return dt
