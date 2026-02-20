"""
mitosis_engine.py — Tasks that split into subtasks (cell division).

A complex task can undergo "mitosis" — dividing into smaller, more
manageable child tasks that can be processed independently.
"""

import random
import time
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Task:
    """An atomic unit of work within the NEXUS task ecosystem."""

    id: str
    description: str
    priority: float = 0.5         # 0 (lowest) … 1 (highest)
    complexity: float = 0.5       # 0 (trivial) … 1 (very complex)
    energy: float = 1.0           # Available resource; depletes on partial work
    status: str = "pending"       # pending | in_progress | completed | failed | pruned
    parent_id: Optional[str] = None
    children: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    tags: List[str] = field(default_factory=list)
    result: Optional[str] = None

    @property
    def can_divide(self) -> bool:
        """A task can undergo mitosis if it is complex enough."""
        return self.complexity > 0.6 and self.status == "pending" and not self.children

    def divide(self, num_children: int = 2) -> List["Task"]:
        """
        Split this task into `num_children` subtasks (mitosis).
        The parent task's energy is distributed among children.
        """
        if not self.can_divide:
            return []

        child_energy = self.energy / num_children
        child_complexity = max(0.1, self.complexity - 0.2)

        children: List[Task] = []
        for i in range(num_children):
            child = Task(
                id=f"{self.id}_child{i+1}",
                description=f"[Sub-task {i+1}] {self.description}",
                priority=self.priority,
                complexity=child_complexity,
                energy=child_energy,
                parent_id=self.id,
                tags=self.tags,
            )
            children.append(child)
            self.children.append(child.id)

        self.energy = 0.0
        self.status = "in_progress"
        return children

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "priority": self.priority,
            "complexity": self.complexity,
            "energy": self.energy,
            "status": self.status,
            "parent_id": self.parent_id,
            "children": self.children,
            "tags": self.tags,
            "result": self.result,
        }


class MitosisEngine:
    """Manages the task lifecycle including creation, division, and completion."""

    def __init__(self):
        self.tasks: dict = {}          # id → Task
        self.completed: List[str] = []
        self.pruned: List[str] = []
        self._id_counter = 0

    # ------------------------------------------------------------------
    # Task management
    # ------------------------------------------------------------------

    def create(
        self,
        description: str,
        priority: float = 0.5,
        complexity: float = 0.5,
        tags: Optional[List[str]] = None,
    ) -> Task:
        self._id_counter += 1
        task = Task(
            id=f"task_{self._id_counter}_{int(time.time())}",
            description=description,
            priority=priority,
            complexity=complexity,
            tags=tags or [],
        )
        self.tasks[task.id] = task
        return task

    def divide(self, task_id: str, num_children: int = 2) -> List[Task]:
        """Trigger mitosis on a task."""
        task = self.tasks.get(task_id)
        if not task or not task.can_divide:
            return []
        children = task.divide(num_children=num_children)
        for child in children:
            self.tasks[child.id] = child
        return children

    def complete(self, task_id: str, result: Optional[str] = None):
        """Mark a task as completed."""
        task = self.tasks.get(task_id)
        if task:
            task.status = "completed"
            task.result = result
            task.completed_at = time.time()
            self.completed.append(task_id)

    def fail(self, task_id: str):
        """Mark a task as failed."""
        task = self.tasks.get(task_id)
        if task:
            task.status = "failed"

    def get_pending(self, top_k: int = 5) -> List[Task]:
        """Return the highest-priority pending tasks."""
        pending = [t for t in self.tasks.values() if t.status == "pending"]
        return sorted(pending, key=lambda t: t.priority, reverse=True)[:top_k]

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        counts: dict = {}
        for t in self.tasks.values():
            counts[t.status] = counts.get(t.status, 0) + 1
        return {
            "total": len(self.tasks),
            "by_status": counts,
            "completed": len(self.completed),
            "pruned": len(self.pruned),
        }
