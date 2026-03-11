"""Tests for state/snapshots.py — SnapshotManager."""

import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from state.snapshots import SnapshotManager, SnapshotRecord


@pytest.fixture
def tmp_project(tmp_path):
    """Create a temporary project directory."""
    project = tmp_path / "test_project"
    project.mkdir()
    # Create some files
    (project / "main.py").write_text("print('hello')\n")
    (project / "readme.txt").write_text("Test project\n")
    return project


@pytest.fixture
def manager(tmp_project):
    mgr = SnapshotManager(tmp_project)
    return mgr


class TestSnapshotManager:
    def test_init_shadow_repo(self, manager):
        available = manager.is_available()
        assert available
        shadow = manager._shadow_dir()
        assert (shadow / ".git").exists()

    def test_capture_returns_hash(self, manager):
        h = manager.capture("test-snap", session_id="s1", phase="code", iteration=1)
        assert h is not None
        assert len(h) == 40  # git tree hash is 40 hex chars

    def test_capture_unchanged_same_hash(self, manager):
        h1 = manager.capture("snap1", session_id="s1")
        h2 = manager.capture("snap2", session_id="s1")
        # Same content should produce same tree hash
        assert h1 == h2

    def test_diff_shows_changes(self, manager, tmp_project):
        h1 = manager.capture("before", session_id="s1")
        # Make a change
        (tmp_project / "main.py").write_text("print('world')\n")
        h2 = manager.capture("after", session_id="s1")
        assert h1 != h2

        diff = manager.diff(h1, h2)
        assert diff["summary"]["files_changed"] >= 1
        assert any(f["path"] == "main.py" for f in diff["files"])

    def test_diff_file_single(self, manager, tmp_project):
        h1 = manager.capture("before", session_id="s1")
        (tmp_project / "main.py").write_text("print('changed')\n")
        h2 = manager.capture("after", session_id="s1")

        diff_text = manager.diff_file(h1, h2, "main.py")
        assert "changed" in diff_text or "hello" in diff_text

    def test_changed_files(self, manager, tmp_project):
        h1 = manager.capture("before", session_id="s1")
        (tmp_project / "new_file.py").write_text("new content\n")
        h2 = manager.capture("after", session_id="s1")

        files = manager.changed_files(h1, h2)
        assert "new_file.py" in files

    def test_restore_full(self, manager, tmp_project):
        h1 = manager.capture("original", session_id="s1")
        original_content = (tmp_project / "main.py").read_text()

        # Modify
        (tmp_project / "main.py").write_text("modified content\n")
        assert (tmp_project / "main.py").read_text() != original_content

        # Restore
        success = manager.restore(h1)
        assert success
        assert (tmp_project / "main.py").read_text() == original_content

    def test_revert_files_selective(self, manager, tmp_project):
        h1 = manager.capture("before", session_id="s1")
        original_main = (tmp_project / "main.py").read_text()
        original_readme = (tmp_project / "readme.txt").read_text()

        # Modify both files
        (tmp_project / "main.py").write_text("changed main\n")
        (tmp_project / "readme.txt").write_text("changed readme\n")

        # Revert only main.py
        result = manager.revert_files(h1, ["main.py"])
        assert "main.py" in result["reverted"]
        assert (tmp_project / "main.py").read_text() == original_main
        # readme.txt should still be modified
        assert (tmp_project / "readme.txt").read_text() == "changed readme\n"

    def test_list_snapshots(self, manager):
        manager.capture("snap-1", session_id="s1", phase="code", iteration=1)
        manager.capture("snap-2", session_id="s1", phase="code", iteration=2)
        manager.capture("snap-3", session_id="s2", phase="test", iteration=1)

        all_snaps = manager.list_snapshots()
        assert len(all_snaps) == 3

        s1_snaps = manager.list_snapshots(session_id="s1")
        assert len(s1_snaps) == 2

    def test_cleanup(self, manager):
        manager.capture("old-snap", session_id="s1")
        manager.cleanup(max_age_days=0)
        # After cleanup with 0 days, all should be removed
        snaps = manager.list_snapshots()
        assert len(snaps) == 0


class TestSnapshotGraceful:
    def test_no_git_returns_none(self, tmp_project):
        """If git is somehow unavailable, capture returns None gracefully."""
        mgr = SnapshotManager(tmp_project, enabled=False)
        assert not mgr.is_available()
        assert mgr.capture("test") is None

    def test_capture_failure_continues(self, tmp_project):
        mgr = SnapshotManager(tmp_project)
        # Force availability but use a bad hash for diff
        if mgr.is_available():
            diff = mgr.diff("0000000000000000000000000000000000000000")
            # Should return empty result, not crash
            assert diff["summary"]["files_changed"] == 0

    def test_corrupt_repo_reinitializes(self, tmp_project):
        mgr = SnapshotManager(tmp_project)
        assert mgr.is_available()
        shadow = mgr._shadow_dir()

        # Corrupt the repo
        git_dir = shadow / ".git"
        if git_dir.exists():
            head_file = git_dir / "HEAD"
            if head_file.exists():
                head_file.write_text("garbage")

        # Create new manager — should detect corruption and reinit
        mgr2 = SnapshotManager(tmp_project)
        assert mgr2.is_available()

    def test_revert_partial_failure(self, tmp_project):
        mgr = SnapshotManager(tmp_project)
        h = mgr.capture("test", session_id="s1")

        result = mgr.revert_files(h, ["main.py", "nonexistent_file.xyz"])
        # main.py should succeed, nonexistent should fail
        assert "main.py" in result["reverted"]
        assert "nonexistent_file.xyz" in result["failed"]


class TestSnapshotWSL2:
    def test_gitignore_sync(self, tmp_project):
        # Create project .gitignore
        (tmp_project / ".gitignore").write_text("*.log\nbuild/\n")
        mgr = SnapshotManager(tmp_project)
        mgr.is_available()

        shadow_gitignore = mgr._shadow_dir() / ".gitignore"
        content = shadow_gitignore.read_text()
        # Should contain both shadow exclusions and project exclusions
        assert "node_modules/" in content
        assert "*.log" in content
        assert "build/" in content

    def test_config_settings(self, tmp_project):
        mgr = SnapshotManager(tmp_project)
        mgr.is_available()

        # Verify git configs are set
        ok, val = mgr._run_git("config", "core.autocrlf")
        assert ok
        assert val == "false"

        ok, val = mgr._run_git("config", "gc.auto")
        assert ok
        assert val == "0"

    def test_status(self, tmp_project):
        mgr = SnapshotManager(tmp_project)
        mgr.capture("test-snap")
        status = mgr.get_status()
        assert status["available"] is True
        assert status["snapshot_count"] >= 1
        assert status["repo_size_mb"] >= 0
