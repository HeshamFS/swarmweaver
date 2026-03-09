"""
Universal Task List System
===========================

Replaces the rigid feature_list.json with a flexible task system
that supports multiple operation modes: greenfield, feature, refactor, fix, evolve.

Tasks can represent features, refactoring steps, bug fixes, migrations, tests,
or any other unit of work. Each task has rich metadata including status,
priority, dependencies, and agent notes.
"""

import json
import os
import shutil
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from core.paths import get_paths


class TaskStatus(str, Enum):
    """Status of a task in the task list."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    BLOCKED = "blocked"
    FAILED = "failed"
    SKIPPED = "skipped"


class TaskCategory(str, Enum):
    """Category types for tasks."""
    FEATURE = "feature"
    REFACTOR = "refactor"
    FIX = "fix"
    TEST = "test"
    MIGRATION = "migration"
    STYLE = "style"
    DOCS = "docs"
    INFRA = "infra"
    PERFORMANCE = "performance"
    SECURITY = "security"
    CLEANUP = "cleanup"


@dataclass
class Task:
    """A single unit of work in the task list."""
    id: str
    title: str
    description: str = ""
    category: str = ""
    acceptance_criteria: list[str] = field(default_factory=list)
    status: str = TaskStatus.PENDING.value
    priority: int = 3  # 1 (highest) to 5 (lowest)
    depends_on: list[str] = field(default_factory=list)
    files_affected: list[str] = field(default_factory=list)
    notes: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    # Verification fields (Self-Healing Verification Loop)
    verification_status: str = "unverified"  # unverified | verified | retrying | failed_verification
    verification_attempts: int = 0
    max_verification_attempts: int = 3
    last_verification_error: str = ""

    def mark_in_progress(self):
        """Mark task as in progress."""
        self.status = TaskStatus.IN_PROGRESS.value
        self.started_at = datetime.now().isoformat()

    def mark_done(self, notes: str = ""):
        """Mark task as completed."""
        self.status = TaskStatus.DONE.value
        self.completed_at = datetime.now().isoformat()
        if notes:
            self.notes = f"{self.notes}\n{notes}".strip()

    def mark_failed(self, reason: str = ""):
        """Mark task as failed."""
        self.status = TaskStatus.FAILED.value
        if reason:
            self.notes = f"{self.notes}\nFailed: {reason}".strip()

    def mark_blocked(self, blocker: str = ""):
        """Mark task as blocked."""
        self.status = TaskStatus.BLOCKED.value
        if blocker:
            self.notes = f"{self.notes}\nBlocked: {blocker}".strip()

    def mark_skipped(self, reason: str = ""):
        """Mark task as skipped."""
        self.status = TaskStatus.SKIPPED.value
        if reason:
            self.notes = f"{self.notes}\nSkipped: {reason}".strip()

    def is_actionable(self) -> bool:
        """Check if task can be worked on (pending and no unmet dependencies)."""
        return self.status == TaskStatus.PENDING.value

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        d = asdict(self)
        # Remove None values
        return {k: v for k, v in d.items() if v is not None}


class TaskList:
    """Manages a list of tasks with persistence to disk."""

    TASK_LIST_FILE = "task_list.json"

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self._paths = get_paths(project_dir)
        self.tasks: list[Task] = []
        self.metadata: dict = {
            "version": "2.0",
            "mode": "greenfield",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "description": "",
        }

    @property
    def task_file(self) -> Path:
        return self._paths.task_list

    def load(self) -> bool:
        """Load tasks from disk. Returns True if tasks were loaded."""
        task_path = self._paths.task_list
        if task_path.exists():
            if self._load_task_list_from(task_path):
                return True
        # Fallback to backup
        bak = task_path.with_suffix(".json.bak")
        if bak.exists():
            print(f"Warning: Loading from backup {bak}")
            return self._load_task_list_from(bak)
        return False

    @staticmethod
    def _make_task(t: dict) -> Task:
        """Create a Task from a dict, ignoring unknown fields."""
        valid = {f for f in Task.__dataclass_fields__}
        return Task(**{k: v for k, v in t.items() if k in valid})

    def _load_task_list_from(self, path: Path) -> bool:
        """Load from the new task_list.json format."""
        try:
            with open(path, "r") as f:
                data = json.load(f)

            if isinstance(data, dict) and "tasks" in data:
                self.metadata = data.get("metadata", self.metadata)
                self.tasks = [self._make_task(t) for t in data["tasks"]]
            elif isinstance(data, list):
                self.tasks = [self._make_task(t) for t in data]
            return True
        except (json.JSONDecodeError, IOError, TypeError) as e:
            print(f"Warning: Could not load {path}: {e}")
            return False

    def to_dict(self) -> dict:
        """Convert task list to a dict suitable for JSON serialization and WebSocket events."""
        return {
            "metadata": self.metadata,
            "tasks": [t.to_dict() for t in self.tasks],
        }

    def save(self):
        """Save tasks to disk in the new format."""
        self.metadata["updated_at"] = datetime.now().isoformat()
        data = {
            "metadata": self.metadata,
            "tasks": [t.to_dict() for t in self.tasks],
        }
        self.task_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.task_file.with_suffix(".json.tmp")
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        # Backup current before replacing
        if self.task_file.exists():
            bak = self.task_file.with_suffix(".json.bak")
            try:
                shutil.copy2(self.task_file, bak)
            except OSError:
                pass
        os.replace(tmp, self.task_file)  # atomic on all platforms

    def add_task(self, task: Task):
        """Add a task to the list."""
        self.tasks.append(task)

    def add_tasks(self, tasks: list[Task]):
        """Add multiple tasks."""
        self.tasks.extend(tasks)

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID."""
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None

    def get_next_actionable(self) -> Optional[Task]:
        """Get the next actionable task (pending, highest priority, dependencies met)."""
        done_ids = {t.id for t in self.tasks if t.status == TaskStatus.DONE.value}
        for task in sorted(self.tasks, key=lambda t: t.priority):
            if task.status != TaskStatus.PENDING.value:
                continue
            # Check dependencies
            if task.depends_on and not all(dep in done_ids for dep in task.depends_on):
                continue
            return task
        return None

    def reopen_task(self, task_id: str, error: str = "") -> bool:
        """Reopen a completed task for re-work (used by verification loop)."""
        task = self.get_task(task_id)
        if task is None:
            return False
        task.status = TaskStatus.PENDING.value
        task.verification_status = "retrying"
        task.verification_attempts += 1
        if error:
            task.last_verification_error = error
            task.notes = f"{task.notes}\n[VERIFY] Reopened: {error[:200]}".strip()
        self.save()
        return True

    def get_tasks_by_status(self, status: str) -> list[Task]:
        """Get all tasks with a given status."""
        return [t for t in self.tasks if t.status == status]

    def get_tasks_by_category(self, category: str) -> list[Task]:
        """Get all tasks in a given category."""
        return [t for t in self.tasks if t.category == category]

    # --- Statistics ---

    def count_by_status(self) -> dict[str, int]:
        """Count tasks by status."""
        counts: dict[str, int] = {}
        for task in self.tasks:
            counts[task.status] = counts.get(task.status, 0) + 1
        return counts

    def count_by_category(self) -> dict[str, dict[str, int]]:
        """Count tasks by category and status."""
        result: dict[str, dict[str, int]] = {}
        for task in self.tasks:
            cat = task.category
            if cat not in result:
                result[cat] = {"total": 0, "done": 0, "pending": 0, "other": 0}
            result[cat]["total"] += 1
            if task.status == TaskStatus.DONE.value:
                result[cat]["done"] += 1
            elif task.status == TaskStatus.PENDING.value:
                result[cat]["pending"] += 1
            else:
                result[cat]["other"] += 1
        return result

    @property
    def total(self) -> int:
        return len(self.tasks)

    @property
    def done_count(self) -> int:
        return sum(1 for t in self.tasks if t.status == TaskStatus.DONE.value)

    @property
    def pending_count(self) -> int:
        return sum(1 for t in self.tasks if t.status == TaskStatus.PENDING.value)

    @property
    def in_progress_count(self) -> int:
        return sum(1 for t in self.tasks if t.status == TaskStatus.IN_PROGRESS.value)

    @property
    def blocked_count(self) -> int:
        return sum(1 for t in self.tasks if t.status == TaskStatus.BLOCKED.value)

    @property
    def percentage_done(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.done_count / self.total) * 100

    def has_pending_tasks(self) -> bool:
        """Check if there are any remaining tasks to work on."""
        return any(
            t.status in (TaskStatus.PENDING.value, TaskStatus.IN_PROGRESS.value, TaskStatus.BLOCKED.value)
            for t in self.tasks
        )

    def summary(self) -> str:
        """Generate a text summary of task progress."""
        lines = []
        status_counts = self.count_by_status()
        lines.append(f"Total: {self.total} tasks")
        for status, count in sorted(status_counts.items()):
            lines.append(f"  {status}: {count}")
        lines.append(f"Progress: {self.percentage_done:.1f}%")
        return "\n".join(lines)


def get_blocking_tasks(worker_task_ids: list[str], all_tasks: list) -> list[str]:
    """Return task IDs that depend on the given worker's incomplete tasks.

    If worker A has task T1 and worker B's task T2 depends_on T1,
    then T1 is a "blocking task" — stalling worker A blocks worker B.
    """
    worker_set = set(worker_task_ids)
    blocked_by = []
    for task in all_tasks:
        deps = getattr(task, "depends_on", []) or []
        for dep_id in deps:
            if dep_id in worker_set and task.id not in worker_set:
                if dep_id not in blocked_by:
                    blocked_by.append(dep_id)
    return blocked_by


def generate_task_id() -> str:
    """Generate a unique task ID."""
    return f"TASK-{uuid.uuid4().hex[:6].upper()}"


def create_task(
    title: str,
    description: str = "",
    category: str = "feature",
    acceptance_criteria: list[str] = None,
    priority: int = 3,
    depends_on: list[str] = None,
) -> Task:
    """Convenience function to create a new task."""
    return Task(
        id=generate_task_id(),
        title=title,
        description=description or title,
        category=category,
        acceptance_criteria=acceptance_criteria or [],
        priority=priority,
        depends_on=depends_on or [],
    )
