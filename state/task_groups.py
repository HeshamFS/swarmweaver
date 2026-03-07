"""
Task Groups (Batch Coordination)
====================================

Groups related tasks into batches that auto-close when all members complete.
Enables coordinated tracking of work distributed across multiple workers.
"""

import json
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class TaskGroup:
    """A batch of related tasks."""
    id: str
    name: str
    task_ids: list[str]
    status: str = "active"  # active, completed
    created_at: str = ""
    completed_at: str = ""
    worker_id: Optional[int] = None  # Which worker owns this group

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TaskGroupProgress:
    """Progress snapshot for a task group."""
    group_id: str
    group_name: str
    total: int
    completed: int
    in_progress: int
    pending: int
    failed: int
    percentage: float

    def to_dict(self) -> dict:
        return asdict(self)


class TaskGroupStore:
    """
    Manages task groups with JSON file persistence.

    Storage: <project>/.swarmweaver/task_groups.json
    """

    GROUPS_FILE = ".swarmweaver/task_groups.json"

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.groups_file = project_dir / self.GROUPS_FILE
        self.groups: list[TaskGroup] = self._load()

    def _load(self) -> list[TaskGroup]:
        if not self.groups_file.exists():
            return []
        try:
            data = json.loads(self.groups_file.read_text(encoding="utf-8"))
            return [TaskGroup(**g) for g in data]
        except (json.JSONDecodeError, TypeError):
            return []

    def _save(self) -> None:
        self.groups_file.parent.mkdir(parents=True, exist_ok=True)
        self.groups_file.write_text(
            json.dumps([g.to_dict() for g in self.groups], indent=2),
            encoding="utf-8",
        )

    def create_group(
        self,
        name: str,
        task_ids: list[str],
        worker_id: Optional[int] = None,
    ) -> TaskGroup:
        group = TaskGroup(
            id=f"group-{uuid.uuid4().hex[:8]}",
            name=name,
            task_ids=task_ids,
            worker_id=worker_id,
        )
        self.groups.append(group)
        self._save()
        return group

    def get_group(self, group_id: str) -> Optional[TaskGroup]:
        for g in self.groups:
            if g.id == group_id:
                return g
        return None

    def add_tasks(self, group_id: str, task_ids: list[str]) -> bool:
        group = self.get_group(group_id)
        if not group:
            return False
        for tid in task_ids:
            if tid not in group.task_ids:
                group.task_ids.append(tid)
        self._save()
        return True

    def remove_tasks(self, group_id: str, task_ids: list[str]) -> bool:
        group = self.get_group(group_id)
        if not group:
            return False
        group.task_ids = [t for t in group.task_ids if t not in task_ids]
        self._save()
        return True

    def get_progress(
        self,
        group_id: str,
        task_statuses: dict[str, str],
    ) -> Optional[TaskGroupProgress]:
        group = self.get_group(group_id)
        if not group:
            return None
        total = len(group.task_ids)
        completed = sum(1 for t in group.task_ids if task_statuses.get(t) in ("done", "completed"))
        in_progress = sum(1 for t in group.task_ids if task_statuses.get(t) == "in_progress")
        failed = sum(1 for t in group.task_ids if task_statuses.get(t) == "failed")
        pending = total - completed - in_progress - failed
        return TaskGroupProgress(
            group_id=group.id,
            group_name=group.name,
            total=total,
            completed=completed,
            in_progress=in_progress,
            pending=pending,
            failed=failed,
            percentage=round((completed / total) * 100, 1) if total > 0 else 0.0,
        )

    def check_auto_complete(self, task_statuses: dict[str, str]) -> list[str]:
        """Check all active groups and auto-complete those where all tasks are done."""
        completed_groups = []
        for group in self.groups:
            if group.status != "active":
                continue
            all_done = all(
                task_statuses.get(tid) in ("done", "completed")
                for tid in group.task_ids
            )
            if all_done and group.task_ids:
                group.status = "completed"
                group.completed_at = datetime.now().isoformat()
                completed_groups.append(group.id)
        if completed_groups:
            self._save()
        return completed_groups

    def list_groups(self, status: Optional[str] = None) -> list[TaskGroup]:
        if status:
            return [g for g in self.groups if g.status == status]
        return list(self.groups)
