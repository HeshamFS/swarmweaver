"""
Test Task Tracker Integration (features/task_tracker.py)
=========================================================

Tests TaskTracker interface, GitHubIssueTracker, SyncManager,
and sync operations.
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from features.task_tracker import (
    ExternalTask,
    SyncStatus,
    GitHubIssueTracker,
    SyncManager,
)


# ---------------------------------------------------------------------------
# ExternalTask
# ---------------------------------------------------------------------------

def test_external_task_creation():
    """ExternalTask stores all fields."""
    task = ExternalTask(
        external_id="42",
        title="Fix login bug",
        description="Login fails for emails with +",
        status="open",
        labels=["bug"],
        url="https://github.com/org/repo/issues/42",
        source="github",
    )
    assert task.external_id == "42"
    assert task.title == "Fix login bug"
    assert task.source == "github"


def test_external_task_to_dict():
    """ExternalTask serializes to dict."""
    task = ExternalTask(external_id="1", title="Test")
    d = task.to_dict()
    assert d["external_id"] == "1"
    assert d["title"] == "Test"


def test_external_task_from_dict():
    """ExternalTask deserializes from dict."""
    d = {"external_id": "5", "title": "Feature", "status": "closed"}
    task = ExternalTask.from_dict(d)
    assert task.external_id == "5"
    assert task.status == "closed"


# ---------------------------------------------------------------------------
# SyncStatus
# ---------------------------------------------------------------------------

def test_sync_status_defaults():
    """SyncStatus has sensible defaults."""
    status = SyncStatus()
    assert status.last_synced == ""
    assert status.tasks_pulled == 0
    assert status.tasks_pushed == 0
    assert status.in_progress is False


def test_sync_status_to_dict():
    """SyncStatus serializes correctly."""
    status = SyncStatus(
        direction="pull",
        tasks_pulled=5,
        last_synced="2026-01-01T00:00:00Z",
    )
    d = status.to_dict()
    assert d["direction"] == "pull"
    assert d["tasks_pulled"] == 5


# ---------------------------------------------------------------------------
# GitHubIssueTracker
# ---------------------------------------------------------------------------

def test_github_tracker_not_available_without_gh(tmp_path):
    """GitHubIssueTracker reports unavailable when gh CLI missing."""
    tracker = GitHubIssueTracker(tmp_path)
    with patch("subprocess.run", side_effect=FileNotFoundError):
        assert tracker.is_available() is False


def test_github_tracker_sync_from_external_no_gh(tmp_path):
    """sync_from_external returns empty when gh fails."""
    tracker = GitHubIssueTracker(tmp_path)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=1, stderr="not logged in", stdout=""
        )
        tasks, errors = tracker.sync_from_external(tmp_path)
        assert tasks == []
        assert len(errors) > 0


def test_github_tracker_sync_from_external_success(tmp_path):
    """sync_from_external parses gh issue list output."""
    tracker = GitHubIssueTracker(tmp_path)
    issues_json = json.dumps([
        {
            "number": 1,
            "title": "Fix bug",
            "body": "Details here",
            "state": "OPEN",
            "labels": [{"name": "bug"}],
            "url": "https://github.com/org/repo/issues/1",
            "assignees": [{"login": "user1"}],
        },
        {
            "number": 2,
            "title": "Add feature",
            "body": "",
            "state": "OPEN",
            "labels": [],
            "url": "https://github.com/org/repo/issues/2",
            "assignees": [],
        },
    ])
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout=issues_json, stderr=""
        )
        tasks, errors = tracker.sync_from_external(tmp_path)
        assert len(tasks) == 2
        assert tasks[0].external_id == "1"
        assert tasks[0].title == "Fix bug"
        assert "bug" in tasks[0].labels
        assert tasks[1].external_id == "2"


def test_github_tracker_update_status(tmp_path):
    """update_status calls gh issue close."""
    tracker = GitHubIssueTracker(tmp_path)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = tracker.update_status("42", "closed", "Done by SwarmWeaver")
        assert result is True
        # Should have called gh issue comment and gh issue close
        assert mock_run.call_count >= 1


# ---------------------------------------------------------------------------
# SyncManager
# ---------------------------------------------------------------------------

def test_sync_manager_get_status_default(tmp_path):
    """Default sync status is empty."""
    manager = SyncManager(tmp_path)
    status = manager.get_status()
    assert status.last_synced == ""
    assert status.in_progress is False


def test_sync_manager_pull_creates_tasks(tmp_path):
    """sync_pull adds external tasks to task_list.json."""
    # Create empty task list under .swarmweaver/
    swarmweaver_dir = tmp_path / ".swarmweaver"
    swarmweaver_dir.mkdir(parents=True, exist_ok=True)
    task_data = {"metadata": {"mode": "feature"}, "tasks": []}
    (swarmweaver_dir / "task_list.json").write_text(json.dumps(task_data))

    manager = SyncManager(tmp_path)

    issues_json = json.dumps([
        {
            "number": 10,
            "title": "New issue",
            "body": "Issue body",
            "state": "OPEN",
            "labels": [],
            "url": "https://github.com/org/repo/issues/10",
            "assignees": [],
        },
    ])

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=issues_json, stderr="")
        status = manager.sync_pull()

    assert status.tasks_pulled == 1
    assert status.in_progress is False

    # Verify task was added (written to .swarmweaver/)
    updated = json.loads((tmp_path / ".swarmweaver" / "task_list.json").read_text())
    assert len(updated["tasks"]) == 1
    assert updated["tasks"][0]["external_id"] == "10"
    assert updated["tasks"][0]["title"] == "New issue"


def test_sync_manager_pull_no_duplicates(tmp_path):
    """sync_pull doesn't add tasks that already exist."""
    swarmweaver_dir = tmp_path / ".swarmweaver"
    swarmweaver_dir.mkdir(parents=True, exist_ok=True)
    task_data = {
        "metadata": {"mode": "feature"},
        "tasks": [{"id": "gh-10", "title": "Existing", "external_id": "10", "status": "pending"}],
    }
    (swarmweaver_dir / "task_list.json").write_text(json.dumps(task_data))

    manager = SyncManager(tmp_path)

    issues_json = json.dumps([
        {"number": 10, "title": "Existing", "body": "", "state": "OPEN", "labels": [], "url": "", "assignees": []},
    ])

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=issues_json, stderr="")
        status = manager.sync_pull()

    assert status.tasks_pulled == 0


def test_sync_manager_push(tmp_path):
    """sync_push sends completed tasks to GitHub."""
    swarmweaver_dir = tmp_path / ".swarmweaver"
    swarmweaver_dir.mkdir(parents=True, exist_ok=True)
    task_data = {
        "metadata": {},
        "tasks": [
            {"id": "gh-5", "title": "Done task", "status": "done", "external_id": "5"},
            {"id": "local-1", "title": "Local only", "status": "done"},
        ],
    }
    (swarmweaver_dir / "task_list.json").write_text(json.dumps(task_data))

    manager = SyncManager(tmp_path)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        status = manager.sync_push()

    assert status.tasks_pushed == 1  # Only the one with external_id


def test_sync_manager_status_persistence(tmp_path):
    """Sync status is saved and loaded correctly."""
    manager = SyncManager(tmp_path)

    # Create a status file
    status = SyncStatus(
        direction="pull",
        tasks_pulled=3,
        last_synced="2026-01-01T00:00:00Z",
    )
    manager._save_status(status)

    loaded = manager.get_status()
    assert loaded.direction == "pull"
    assert loaded.tasks_pulled == 3
    assert loaded.last_synced == "2026-01-01T00:00:00Z"
