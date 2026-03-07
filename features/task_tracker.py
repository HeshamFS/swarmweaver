"""Task tracker integration - sync tasks with external systems like GitHub Issues."""
import json
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class ExternalTask:
    """Represents a task from an external tracker."""
    external_id: str  # e.g., GitHub issue number
    title: str
    description: str = ""
    status: str = "open"  # open, closed, in_progress
    labels: list[str] = field(default_factory=list)
    url: str = ""
    assignee: str = ""
    source: str = ""  # "github", "jira", etc.

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ExternalTask":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class SyncStatus:
    """Status of a sync operation."""
    last_synced: str = ""
    direction: str = ""  # "pull", "push", "bidirectional"
    tasks_pulled: int = 0
    tasks_pushed: int = 0
    conflicts: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    in_progress: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class TaskTracker(ABC):
    """Abstract interface for external task trackers."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the tracker is configured and accessible."""
        ...

    @abstractmethod
    def sync_from_external(self, project_dir: Path) -> tuple[list[ExternalTask], list[str]]:
        """Pull tasks from external tracker.

        Returns:
            Tuple of (tasks, errors)
        """
        ...

    @abstractmethod
    def sync_to_external(self, project_dir: Path, tasks: list[dict]) -> tuple[int, list[str]]:
        """Push task statuses to external tracker.

        Args:
            project_dir: Project directory containing task_list.json
            tasks: List of internal task dicts to sync

        Returns:
            Tuple of (count_pushed, errors)
        """
        ...

    @abstractmethod
    def update_status(self, external_id: str, status: str, comment: str = "") -> bool:
        """Update a single external task's status."""
        ...


class GitHubIssueTracker(TaskTracker):
    """GitHub Issues integration using gh CLI."""

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir

    def is_available(self) -> bool:
        """Check if gh CLI is installed and authenticated."""
        try:
            result = subprocess.run(
                ["gh", "auth", "status"],
                capture_output=True, text=True, timeout=10,
                cwd=str(self.project_dir),
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _get_repo(self) -> Optional[str]:
        """Get the repo name (owner/repo) from git remote."""
        try:
            result = subprocess.run(
                ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
                capture_output=True, text=True, timeout=10,
                cwd=str(self.project_dir),
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return None

    def sync_from_external(self, project_dir: Path) -> tuple[list[ExternalTask], list[str]]:
        """Pull open issues from GitHub."""
        errors = []
        tasks = []

        try:
            result = subprocess.run(
                ["gh", "issue", "list", "--json", "number,title,body,state,labels,url,assignees", "--limit", "50"],
                capture_output=True, text=True, timeout=30,
                cwd=str(project_dir),
            )

            if result.returncode != 0:
                errors.append(f"gh issue list failed: {result.stderr}")
                return tasks, errors

            issues = json.loads(result.stdout)
            for issue in issues:
                labels = [la.get("name", "") for la in issue.get("labels", [])]
                assignees = [a.get("login", "") for a in issue.get("assignees", [])]

                task = ExternalTask(
                    external_id=str(issue["number"]),
                    title=issue.get("title", ""),
                    description=issue.get("body", "") or "",
                    status="open" if issue.get("state") == "OPEN" else "closed",
                    labels=labels,
                    url=issue.get("url", ""),
                    assignee=assignees[0] if assignees else "",
                    source="github",
                )
                tasks.append(task)

        except Exception as e:
            errors.append(f"Error syncing from GitHub: {e}")

        return tasks, errors

    def sync_to_external(self, project_dir: Path, tasks: list[dict]) -> tuple[int, list[str]]:
        """Push task statuses to GitHub issues."""
        errors = []
        pushed = 0

        for task in tasks:
            external_id = task.get("external_id") or task.get("github_issue")
            if not external_id:
                continue

            status = task.get("status", "")
            if status in ("done", "completed", "verified"):
                success = self.update_status(external_id, "closed", "Completed by SwarmWeaver agent")
            elif status in ("in_progress", "working"):
                success = self.update_status(external_id, "open", "In progress via SwarmWeaver")
            else:
                continue

            if success:
                pushed += 1
            else:
                errors.append(f"Failed to update issue #{external_id}")

        return pushed, errors

    def update_status(self, external_id: str, status: str, comment: str = "") -> bool:
        """Update a GitHub issue's state."""
        try:
            if comment:
                subprocess.run(
                    ["gh", "issue", "comment", external_id, "--body", comment],
                    capture_output=True, text=True, timeout=15,
                    cwd=str(self.project_dir),
                )

            if status == "closed":
                result = subprocess.run(
                    ["gh", "issue", "close", external_id],
                    capture_output=True, text=True, timeout=15,
                    cwd=str(self.project_dir),
                )
                return result.returncode == 0

            return True

        except Exception as e:
            logger.warning(f"Failed to update issue #{external_id}: {e}")
            return False

    def create_issue(self, title: str, body: str = "", labels: list[str] | None = None) -> Optional[str]:
        """Create a new GitHub issue."""
        try:
            cmd = ["gh", "issue", "create", "--title", title, "--body", body or ""]
            if labels:
                for label in labels:
                    cmd.extend(["--label", label])

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=15,
                cwd=str(self.project_dir),
            )

            if result.returncode == 0:
                return result.stdout.strip()
            return None

        except Exception as e:
            logger.warning(f"Failed to create issue: {e}")
            return None


class SyncManager:
    """Manages sync state and operations."""

    SYNC_STATE_FILE = ".swarmweaver/sync_status.json"

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.state_path = project_dir / self.SYNC_STATE_FILE
        self.tracker = GitHubIssueTracker(project_dir)

    def get_status(self) -> SyncStatus:
        if self.state_path.exists():
            data = json.loads(self.state_path.read_text())
            return SyncStatus(**{k: v for k, v in data.items() if k in SyncStatus.__dataclass_fields__})
        return SyncStatus()

    def _save_status(self, status: SyncStatus) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(status.to_dict(), indent=2))

    def sync_pull(self) -> SyncStatus:
        """Pull tasks from external tracker into task_list.json."""
        status = SyncStatus(direction="pull", in_progress=True)
        self._save_status(status)

        external_tasks, errors = self.tracker.sync_from_external(self.project_dir)

        from core.paths import get_paths
        paths = get_paths(self.project_dir)
        task_file = paths.resolve_read("task_list.json")
        if task_file.exists():
            task_data = json.loads(task_file.read_text())
        else:
            task_data = {"metadata": {"mode": "feature"}, "tasks": []}

        existing_external_ids = {
            t.get("external_id") or t.get("github_issue")
            for t in task_data["tasks"]
            if t.get("external_id") or t.get("github_issue")
        }

        pulled = 0
        for ext_task in external_tasks:
            if ext_task.external_id not in existing_external_ids:
                new_task = {
                    "id": f"gh-{ext_task.external_id}",
                    "title": ext_task.title,
                    "description": ext_task.description,
                    "status": "pending",
                    "external_id": ext_task.external_id,
                    "external_url": ext_task.url,
                    "external_source": "github",
                    "labels": ext_task.labels,
                }
                task_data["tasks"].append(new_task)
                pulled += 1

        if pulled > 0:
            write_path = paths.task_list
            write_path.parent.mkdir(parents=True, exist_ok=True)
            write_path.write_text(json.dumps(task_data, indent=2))

        status.in_progress = False
        status.tasks_pulled = pulled
        status.errors = errors
        status.last_synced = datetime.now(timezone.utc).isoformat()
        self._save_status(status)

        return status

    def sync_push(self) -> SyncStatus:
        """Push task statuses to external tracker."""
        from core.paths import get_paths
        status = SyncStatus(direction="push", in_progress=True)
        self._save_status(status)

        paths = get_paths(self.project_dir)
        task_file = paths.resolve_read("task_list.json")
        if not task_file.exists():
            status.in_progress = False
            status.errors = ["No task_list.json found"]
            self._save_status(status)
            return status

        task_data = json.loads(task_file.read_text())
        tasks_with_external = [t for t in task_data.get("tasks", []) if t.get("external_id")]

        pushed, errors = self.tracker.sync_to_external(self.project_dir, tasks_with_external)

        status.in_progress = False
        status.tasks_pushed = pushed
        status.errors = errors
        status.last_synced = datetime.now(timezone.utc).isoformat()
        self._save_status(status)

        return status
