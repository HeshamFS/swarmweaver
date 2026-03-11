"""Tests for state/sessions.py — SessionStore + GlobalSessionIndex."""

import json
import os
import sqlite3
import tempfile
import time
from pathlib import Path

import pytest

# Ensure the project root is on sys.path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from state.sessions import SessionStore, GlobalSessionIndex


@pytest.fixture
def tmp_project(tmp_path):
    """Create a temporary project directory with .swarmweaver/ and a git repo."""
    project = tmp_path / "test_project"
    project.mkdir()
    sw = project / ".swarmweaver"
    sw.mkdir()
    # Initialize git repo for compute_change_summary
    os.system(f"cd {project} && git init && git commit --allow-empty -m init")
    return project


@pytest.fixture
def store(tmp_project):
    s = SessionStore(tmp_project)
    s.initialize()
    return s


class TestSessionStore:
    def test_create_session(self, store):
        sid = store.create_session(mode="feature", model="sonnet", task_input="Add auth")
        assert sid
        session = store.get_session(sid)
        assert session is not None
        assert session["mode"] == "feature"
        assert session["model"] == "sonnet"
        assert session["status"] == "running"
        assert "auth" in session["title"].lower() or "auth" in session["task_input"].lower()

    def test_update_status(self, store):
        sid = store.create_session(mode="fix", model="opus")
        store.update_session(sid, status="stopped", tasks_completed=3, tasks_total=5)
        session = store.get_session(sid)
        assert session["status"] == "stopped"
        assert session["tasks_completed"] == 3

    def test_complete_session(self, store):
        sid = store.create_session(mode="evolve", model="haiku")
        store.complete_session(sid, status="completed")
        session = store.get_session(sid)
        assert session["status"] == "completed"
        assert session["completed_at"] is not None

    def test_complete_session_with_error(self, store):
        sid = store.create_session(mode="fix", model="opus")
        store.complete_session(sid, status="error", error_message="Auth failed")
        session = store.get_session(sid)
        assert session["status"] == "error"
        assert session["error_message"] == "Auth failed"

    def test_archive_session(self, store):
        sid = store.create_session(mode="feature", model="sonnet")
        store.archive_session(sid)
        session = store.get_session(sid)
        assert session["status"] == "archived"

    def test_record_message(self, store):
        sid = store.create_session(mode="feature", model="sonnet")
        mid = store.record_message(
            session_id=sid,
            agent_name="main",
            phase="implement",
            role="assistant",
            content_summary="Implemented auth module",
            input_tokens=5000,
            output_tokens=2000,
            cost_usd=0.05,
            model="sonnet",
            turn_number=1,
            duration_ms=30000,
        )
        assert mid
        msgs = store.get_messages(sid)
        assert len(msgs) == 1
        assert msgs[0]["input_tokens"] == 5000
        # Verify cumulative totals updated
        session = store.get_session(sid)
        assert session["total_input_tokens"] == 5000
        assert session["total_cost_usd"] == pytest.approx(0.05, abs=0.001)

    def test_record_file_changes(self, store):
        sid = store.create_session(mode="feature", model="sonnet")
        store.record_file_changes(sid, [
            {"file_path": "src/auth.py", "change_type": "added", "additions": 100, "deletions": 0},
            {"file_path": "src/main.py", "change_type": "modified", "additions": 10, "deletions": 5},
        ])
        changes = store.get_file_changes(sid)
        assert len(changes) == 2
        assert changes[0]["file_path"] == "src/auth.py"

    def test_list_sessions_with_filters(self, store):
        store.create_session(mode="feature", model="sonnet")
        store.create_session(mode="fix", model="opus")
        store.create_session(mode="feature", model="haiku")

        all_sessions = store.list_sessions()
        assert len(all_sessions) == 3

        features = store.list_sessions(mode="feature")
        assert len(features) == 2

        # Test limit
        limited = store.list_sessions(limit=1)
        assert len(limited) == 1

    def test_get_detail(self, store):
        sid = store.create_session(mode="feature", model="sonnet")
        store.record_message(session_id=sid, phase="analyze", role="assistant")
        store.record_file_changes(sid, [
            {"file_path": "test.py", "change_type": "added"},
        ])
        detail = store.get_detail(sid)
        assert detail is not None
        assert "messages" in detail
        assert "file_changes" in detail
        assert len(detail["messages"]) == 1
        assert len(detail["file_changes"]) == 1

    def test_compute_change_summary(self, tmp_project):
        """compute_change_summary uses git diff to populate file_changes + session stats."""
        store = SessionStore(tmp_project)
        store.initialize()
        sid = store.create_session(mode="feature", model="sonnet")

        # Create a file and commit it so git diff has something
        new_file = tmp_project / "new_feature.py"
        new_file.write_text("def hello():\n    return 'world'\n")
        os.system(f"cd {tmp_project} && git add -A && git commit -m 'add feature'")

        summary = store.compute_change_summary(sid)
        # The diff from initial empty commit to HEAD should show the new file
        assert summary["lines_added"] >= 2
        assert "new_feature.py" in summary["changed_files"]

        # Verify file_changes table was populated
        changes = store.get_file_changes(sid)
        assert len(changes) >= 1
        assert any(c["file_path"] == "new_feature.py" for c in changes)

        # Verify session summary fields updated
        session = store.get_session(sid)
        assert session["lines_added"] >= 2

    def test_analytics(self, store):
        sid1 = store.create_session(mode="feature", model="sonnet")
        store.record_message(session_id=sid1, cost_usd=0.10, input_tokens=1000, output_tokens=500)
        store.complete_session(sid1)

        sid2 = store.create_session(mode="fix", model="opus")
        store.record_message(session_id=sid2, cost_usd=0.20, input_tokens=2000, output_tokens=1000)
        store.complete_session(sid2)

        analytics = store.get_analytics()
        assert analytics["total_sessions"] == 2
        assert analytics["by_mode"]["feature"] == 1
        assert analytics["by_mode"]["fix"] == 1
        assert analytics["total_cost_usd"] == pytest.approx(0.30, abs=0.01)

    def test_delete_session(self, store):
        sid = store.create_session(mode="feature", model="sonnet")
        store.record_message(session_id=sid, phase="test")
        store.record_file_changes(sid, [{"file_path": "x.py", "change_type": "added"}])
        assert store.delete_session(sid)
        assert store.get_session(sid) is None
        assert store.get_messages(sid) == []
        assert store.get_file_changes(sid) == []

    def test_purge(self, store):
        sid = store.create_session(mode="feature", model="sonnet")
        store.complete_session(sid)
        # Manually backdate
        conn = store._get_connection()
        conn.execute(
            "UPDATE sessions SET created_at = '2020-01-01T00:00:00Z' WHERE id = ?",
            (sid,),
        )
        conn.commit()
        count = store.purge(older_than_days=1)
        assert count == 1
        assert store.get_session(sid) is None


class TestGlobalSessionIndex:
    def test_upsert_and_list(self, tmp_path):
        # Override home for test
        idx = GlobalSessionIndex()
        idx.db_path = tmp_path / "global_sessions.db"
        idx.initialize()

        idx.upsert({
            "id": "s1",
            "project_dir": "/proj/a",
            "mode": "feature",
            "model": "sonnet",
            "title": "Test",
            "status": "completed",
            "is_team": 0,
            "agent_count": 1,
            "tasks_total": 5,
            "tasks_completed": 5,
            "total_cost_usd": 0.15,
            "created_at": "2025-01-01T00:00:00Z",
            "completed_at": "2025-01-01T01:00:00Z",
            "task_input": "Add auth",
        })

        sessions = idx.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["id"] == "s1"

    def test_list_by_project(self, tmp_path):
        idx = GlobalSessionIndex()
        idx.db_path = tmp_path / "global_sessions.db"
        idx.initialize()

        for i, proj in enumerate(["/proj/a", "/proj/a", "/proj/b"]):
            idx.upsert({
                "id": f"s{i}",
                "project_dir": proj,
                "mode": "feature",
                "model": "sonnet",
                "title": f"Session {i}",
                "status": "completed",
                "is_team": 0,
                "agent_count": 1,
                "tasks_total": 0,
                "tasks_completed": 0,
                "total_cost_usd": 0.0,
                "created_at": f"2025-01-0{i+1}T00:00:00Z",
                "task_input": "",
            })

        proj_a = idx.list_sessions(project_dir="/proj/a")
        assert len(proj_a) == 2

    def test_analytics(self, tmp_path):
        idx = GlobalSessionIndex()
        idx.db_path = tmp_path / "global_sessions.db"
        idx.initialize()

        idx.upsert({
            "id": "s1", "project_dir": "/proj/a", "mode": "feature",
            "model": "sonnet", "title": "", "status": "completed",
            "is_team": 0, "agent_count": 1, "tasks_total": 0,
            "tasks_completed": 0, "total_cost_usd": 1.0,
            "created_at": "2025-01-01", "task_input": "",
        })
        idx.upsert({
            "id": "s2", "project_dir": "/proj/b", "mode": "fix",
            "model": "opus", "title": "", "status": "completed",
            "is_team": 0, "agent_count": 1, "tasks_total": 0,
            "tasks_completed": 0, "total_cost_usd": 2.0,
            "created_at": "2025-01-02", "task_input": "",
        })

        analytics = idx.get_analytics()
        assert analytics["total_sessions"] == 2
        assert analytics["total_cost_usd"] == pytest.approx(3.0, abs=0.01)
        assert len(analytics["by_project"]) == 2


class TestSessionStoreTeam:
    def test_team_session(self, store):
        sid = store.create_session(
            mode="feature", model="sonnet", is_team=True, agent_count=3
        )
        session = store.get_session(sid)
        assert session["is_team"] == 1
        assert session["agent_count"] == 3

    def test_multi_agent_messages(self, store):
        sid = store.create_session(mode="feature", model="sonnet", is_team=True)
        store.record_message(session_id=sid, agent_name="worker-1", phase="implement")
        store.record_message(session_id=sid, agent_name="worker-2", phase="implement")
        store.record_message(session_id=sid, agent_name="worker-1", phase="implement")

        all_msgs = store.get_messages(sid)
        assert len(all_msgs) == 3

        w1_msgs = store.get_messages(sid, agent_name="worker-1")
        assert len(w1_msgs) == 2

    def test_concurrent_writes(self, store):
        """Multiple rapid writes should not fail with WAL mode."""
        sid = store.create_session(mode="feature", model="sonnet")
        for i in range(20):
            store.record_message(
                session_id=sid,
                agent_name=f"worker-{i % 3}",
                phase="implement",
                turn_number=i,
            )
        msgs = store.get_messages(sid)
        assert len(msgs) == 20


class TestMigration:
    def test_migrate_from_chains(self, tmp_project):
        # Create chain data
        chains_dir = tmp_project / ".swarmweaver" / "chains"
        chains_dir.mkdir(parents=True, exist_ok=True)
        (chains_dir / "_active_chain.txt").write_text("abc123")
        (chains_dir / "abc123.json").write_text(json.dumps([
            {
                "session_id": "sess-1",
                "chain_id": "abc123",
                "sequence_number": 1,
                "checkpoint_summary": "First session",
                "start_time": "2025-01-01T00:00:00Z",
                "end_time": "2025-01-01T01:00:00Z",
                "phase": "implement",
                "tasks_completed": 3,
                "tasks_total": 5,
                "cost": 0.5,
            },
            {
                "session_id": "sess-2",
                "chain_id": "abc123",
                "sequence_number": 2,
                "checkpoint_summary": "Second session",
                "start_time": "2025-01-01T01:00:00Z",
                "end_time": "2025-01-01T02:00:00Z",
                "phase": "implement",
                "tasks_completed": 5,
                "tasks_total": 5,
                "cost": 0.3,
            },
        ]))

        store = SessionStore(tmp_project)
        store.initialize()
        count = store.migrate_from_chains()
        assert count == 2

        sessions = store.list_sessions()
        assert len(sessions) == 2

    def test_idempotent_migration(self, tmp_project):
        chains_dir = tmp_project / ".swarmweaver" / "chains"
        chains_dir.mkdir(parents=True, exist_ok=True)
        (chains_dir / "xyz.json").write_text(json.dumps([
            {"session_id": "s1", "chain_id": "xyz", "sequence_number": 1, "phase": "code"},
        ]))

        store = SessionStore(tmp_project)
        store.initialize()
        count1 = store.migrate_from_chains()
        assert count1 == 1

        # Second migration should skip (sessions already exist)
        count2 = store.migrate_from_chains()
        assert count2 == 0
