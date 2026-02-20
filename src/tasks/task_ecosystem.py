"""
task_ecosystem.py — Tasks compete for resources and are managed as an ecosystem.

Integrates MitosisEngine (creation & division) with ApoptosisEngine
(pruning) to form a self-regulating task population.
"""

from tasks.apoptosis import ApoptosisEngine
from tasks.mitosis_engine import MitosisEngine, Task
from typing import List, Optional


class TaskEcosystem:
    """Self-regulating task ecosystem: tasks are born, split, and pruned."""

    def __init__(
        self,
        max_tasks: int = 100,
        auto_divide_threshold: float = 0.7,
    ):
        self.engine = MitosisEngine()
        self.apoptosis = ApoptosisEngine()
        self.max_tasks = max_tasks
        self.auto_divide_threshold = auto_divide_threshold
        self.tick_count = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(
        self,
        description: str,
        priority: float = 0.5,
        complexity: float = 0.5,
        tags: Optional[List[str]] = None,
    ) -> Task:
        """Add a new task to the ecosystem."""
        task = self.engine.create(
            description=description,
            priority=priority,
            complexity=complexity,
            tags=tags,
        )
        # Auto-divide very complex tasks immediately
        if complexity >= self.auto_divide_threshold:
            self.engine.divide(task.id, num_children=2)
        return task

    def complete(self, task_id: str, result: Optional[str] = None):
        self.engine.complete(task_id, result=result)

    def fail(self, task_id: str):
        self.engine.fail(task_id)

    def get_next(self, top_k: int = 3) -> List[Task]:
        """Return the next highest-priority pending tasks."""
        return self.engine.get_pending(top_k=top_k)

    # ------------------------------------------------------------------
    # Ecosystem tick
    # ------------------------------------------------------------------

    def tick(self):
        """One regulation cycle: prune dead tasks, enforce population cap."""
        self.tick_count += 1

        # Prune failing / stale tasks
        pruned = self.apoptosis.run(self.engine)

        # Population cap — prune lowest-priority pending tasks
        all_tasks = list(self.engine.tasks.values())
        alive = [t for t in all_tasks if t.status not in ("pruned", "completed")]
        if len(alive) > self.max_tasks:
            overflow = sorted(alive, key=lambda t: t.priority)
            for task in overflow[: len(alive) - self.max_tasks]:
                task.status = "pruned"
                self.engine.pruned.append(task.id)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        eco = self.engine.stats()
        apo = self.apoptosis.stats()
        return {
            "tick": self.tick_count,
            "tasks": eco,
            "apoptosis": apo,
        }
