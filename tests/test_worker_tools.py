"""
Worker MCP Tools Tests
======================

Tests for worker_tools: create_worker_tool_server, task_list_dir, mail_project_dir,
report_to_orchestrator in WORKER_TOOL_NAMES, and server config structure.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.worker_tools import (
    create_worker_tool_server,
    WORKER_TOOL_NAMES,
)
from state.task_list import TaskList


def test_worker_tool_names_include_report_to_orchestrator():
    """report_to_orchestrator should be in WORKER_TOOL_NAMES."""
    assert "mcp__worker_tools__report_to_orchestrator" in WORKER_TOOL_NAMES


def test_worker_tool_names_include_all_tools():
    """All worker tools should be in WORKER_TOOL_NAMES."""
    expected = [
        "mcp__worker_tools__get_my_tasks",
        "mcp__worker_tools__start_task",
        "mcp__worker_tools__complete_task",
        "mcp__worker_tools__report_blocker",
        "mcp__worker_tools__report_to_orchestrator",
        "mcp__worker_tools__get_my_ports",
        "mcp__worker_tools__close_my_ports",
    ]
    for name in expected:
        assert name in WORKER_TOOL_NAMES


def test_create_worker_tool_server_with_task_list_and_mail_dirs(tmp_path):
    """Server can be created with task_list_dir (worktree) and mail_project_dir (main)."""
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    swarm_dir = worktree / ".swarmweaver"
    swarm_dir.mkdir()
    (swarm_dir / "task_list.json").write_text(json.dumps({
        "tasks": [
            {"id": "TASK-001", "title": "Test", "status": "pending"},
            {"id": "TASK-002", "title": "Test 2", "status": "pending"},
        ],
    }, indent=2))

    main_dir = tmp_path / "main"
    main_dir.mkdir()
    (main_dir / ".swarmweaver").mkdir()

    server = create_worker_tool_server(
        worker_id=1,
        task_ids=["TASK-001", "TASK-002"],
        task_list_dir=worktree,
        mail_project_dir=main_dir,
    )
    assert server is not None
    assert server.get("name") == "worker_tools"
    assert server.get("type") == "sdk"
    assert "instance" in server


def test_create_worker_tool_server_task_list_dir_only(tmp_path):
    """Server can be created with only task_list_dir (no mail)."""
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / ".swarmweaver").mkdir()
    (worktree / ".swarmweaver" / "task_list.json").write_text(json.dumps({"tasks": []}))

    server = create_worker_tool_server(
        worker_id=1,
        task_ids=[],
        task_list_dir=worktree,
    )
    assert server is not None
    assert server.get("name") == "worker_tools"
