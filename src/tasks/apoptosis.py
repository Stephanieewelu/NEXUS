"""
apoptosis.py — Programmed self-destruction of bad or stale task paths.

Just as biological apoptosis removes damaged cells without triggering
inflammation, the ApoptosisEngine silently prunes failing or resource-
wasting tasks before they drag down the rest of the ecosystem.
"""

import time
from typing import Dict, List

from tasks.mitosis_engine import MitosisEngine, Task


class ApoptosisEngine:
    """Evaluates and prunes failing / stale tasks from the task ecosystem."""

    def __init__(
        self,
        stale_age_seconds: float = 3600.0,
        min_energy_threshold: float = 0.05,
    ):
        self.stale_age = stale_age_seconds
        self.min_energy = min_energy_threshold
        self.prune_log: List[dict] = []

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def should_prune(self, task: Task) -> bool:
        """Return True if a task should be destroyed."""
        if task.status in ("completed", "pruned"):
            return False

        # Stale — has been sitting untouched for too long
        age = time.time() - task.created_at
        if age > self.stale_age and task.status == "pending":
            return True

        # Energy-depleted — no resources left to execute
        if task.energy < self.min_energy and task.status != "in_progress":
            return True

        # Failed tasks with no children
        if task.status == "failed" and not task.children:
            return True

        return False

    def run(self, engine: MitosisEngine) -> List[str]:
        """
        Scan all tasks in the engine and prune those that qualify.

        Returns a list of pruned task IDs.
        """
        pruned_ids: List[str] = []

        for tid, task in list(engine.tasks.items()):
            if self.should_prune(task):
                reason = self._determine_reason(task)
                task.status = "pruned"
                pruned_ids.append(tid)
                engine.pruned.append(tid)
                self.prune_log.append({
                    "task_id": tid,
                    "description": task.description[:80],
                    "reason": reason,
                    "pruned_at": time.time(),
                })
                print(f"  💀 Task pruned [{reason}]: {task.description[:60]}")

        return pruned_ids

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _determine_reason(self, task: Task) -> str:
        age = time.time() - task.created_at
        if task.status == "failed":
            return "failed"
        if age > self.stale_age:
            return "stale"
        if task.energy < self.min_energy:
            return "energy_depleted"
        return "unknown"

    def stats(self) -> dict:
        reasons: dict = {}
        for entry in self.prune_log:
            r = entry["reason"]
            reasons[r] = reasons.get(r, 0) + 1
        return {"total_pruned": len(self.prune_log), "by_reason": reasons}
