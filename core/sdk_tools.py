"""
Custom In-Process MCP Tools
=============================

Defines custom tools that the agent can invoke during native SDK execution.
These tools run in-process (not as subprocesses) and give the agent direct
access to SwarmWeaver internals:

- update_task_status: Mark tasks done/in_progress/failed from within the agent
- emit_progress: Push progress updates to the dashboard in real-time

These are assembled into an ``McpSdkServerConfig`` and injected into the
``create_client()`` call when running in native mode.
"""

import json
from pathlib import Path
from typing import Optional

from state.task_list import TaskList, TaskStatus


def update_task_status(
    project_dir: Path,
    task_id: str,
    status: str,
    notes: str = "",
) -> dict:
    """
    Update a task's status in the SwarmWeaver task list.

    Args:
        project_dir: Project root directory.
        task_id: ID of the task (e.g. "TASK-001").
        status: New status — one of "done", "in_progress", "pending",
                "failed", "blocked", "skipped".
        notes: Optional notes to append.

    Returns:
        Dict with success/error info.
    """
    try:
        tl = TaskList(project_dir)
        if not tl.load():
            return {"success": False, "error": "No task list found"}

        task = tl.get_task(task_id)
        if not task:
            return {"success": False, "error": f"Task {task_id} not found"}

        status_lower = status.lower().strip()
        if status_lower == "done":
            task.mark_done(notes)
        elif status_lower == "in_progress":
            task.mark_in_progress()
        elif status_lower == "failed":
            task.mark_failed(notes)
        elif status_lower == "blocked":
            task.mark_blocked(notes)
        elif status_lower == "skipped":
            task.mark_skipped(notes)
        elif status_lower == "pending":
            task.status = TaskStatus.PENDING.value
        else:
            return {"success": False, "error": f"Unknown status: {status}"}

        if notes and status_lower not in ("done", "failed", "blocked", "skipped"):
            task.notes = f"{task.notes}\n{notes}".strip()

        tl.save()
        return {
            "success": True,
            "task_id": task_id,
            "new_status": task.status,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def emit_progress(
    project_dir: Path,
    message: str,
    percent: Optional[int] = None,
    phase: Optional[str] = None,
) -> dict:
    """
    Write a progress update to the progress file for dashboard display.

    Args:
        project_dir: Project root directory.
        message: Human-readable progress message.
        percent: Optional completion percentage (0-100).
        phase: Optional current phase name.

    Returns:
        Dict confirming the update.
    """
    from core.paths import get_paths
    from datetime import datetime

    try:
        paths = get_paths(project_dir)
        progress_file = paths.progress_notes

        entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "message": message,
        }
        if percent is not None:
            entry["percent"] = max(0, min(100, percent))
        if phase:
            entry["phase"] = phase

        # Append to progress file
        lines = []
        if progress_file.exists():
            lines = progress_file.read_text(encoding="utf-8").splitlines()

        lines.append(json.dumps(entry))

        # Cap at 500 lines to prevent unbounded growth
        if len(lines) > 500:
            lines = lines[-500:]

        progress_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        return {"success": True, "message": message}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_task_summary(project_dir: Path) -> dict:
    """
    Return a summary of the current task list for the agent.

    Returns:
        Dict with task counts and next actionable task info.
    """
    try:
        tl = TaskList(project_dir)
        if not tl.load():
            return {"success": False, "error": "No task list found"}

        total = len(tl.tasks)
        done = len([t for t in tl.tasks if t.status == "done"])
        pending = len([t for t in tl.tasks if t.status == "pending"])
        in_progress = len([t for t in tl.tasks if t.status == "in_progress"])
        failed = len([t for t in tl.tasks if t.status == "failed"])

        next_task = tl.get_next_actionable()

        result = {
            "success": True,
            "total": total,
            "done": done,
            "pending": pending,
            "in_progress": in_progress,
            "failed": failed,
            "percent_complete": round(done / total * 100, 1) if total > 0 else 0,
        }

        if next_task:
            result["next_task"] = {
                "id": next_task.id,
                "title": next_task.title,
                "category": next_task.category,
                "priority": next_task.priority,
            }

        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Tool definitions for SDK registration ──

SDK_TOOL_DEFINITIONS = [
    {
        "name": "update_task_status",
        "description": (
            "Update a task's status in the SwarmWeaver task list. "
            "Use this to mark tasks as done, in_progress, failed, blocked, or skipped."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task ID (e.g. 'TASK-001')",
                },
                "status": {
                    "type": "string",
                    "enum": ["done", "in_progress", "pending", "failed", "blocked", "skipped"],
                    "description": "New status for the task",
                },
                "notes": {
                    "type": "string",
                    "description": "Optional notes to append to the task",
                    "default": "",
                },
            },
            "required": ["task_id", "status"],
        },
    },
    {
        "name": "emit_progress",
        "description": (
            "Send a progress update to the SwarmWeaver dashboard. "
            "Use this to report what you're working on and how far along you are."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Human-readable progress message",
                },
                "percent": {
                    "type": "integer",
                    "description": "Completion percentage (0-100)",
                    "minimum": 0,
                    "maximum": 100,
                },
                "phase": {
                    "type": "string",
                    "description": "Current phase name (e.g. 'implement', 'test')",
                },
            },
            "required": ["message"],
        },
    },
    {
        "name": "get_task_summary",
        "description": (
            "Get a summary of the current task list including counts by status "
            "and the next actionable task. Use this to decide what to work on next."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]


def handle_sdk_tool_call(
    project_dir: Path,
    tool_name: str,
    tool_input: dict,
) -> str:
    """
    Dispatch an SDK custom tool call to the appropriate handler.

    Args:
        project_dir: Project root directory.
        tool_name: Name of the tool being called.
        tool_input: Parsed JSON input from the agent.

    Returns:
        JSON string result.
    """
    handlers = {
        "update_task_status": lambda inp: update_task_status(
            project_dir,
            task_id=inp.get("task_id", ""),
            status=inp.get("status", ""),
            notes=inp.get("notes", ""),
        ),
        "emit_progress": lambda inp: emit_progress(
            project_dir,
            message=inp.get("message", ""),
            percent=inp.get("percent"),
            phase=inp.get("phase"),
        ),
        "get_task_summary": lambda _: get_task_summary(project_dir),
    }

    handler = handlers.get(tool_name)
    if not handler:
        return json.dumps({"success": False, "error": f"Unknown tool: {tool_name}"})

    result = handler(tool_input)
    return json.dumps(result)
