"""
Worker MCP Tools
================

In-process MCP tools that enforce strict task scope for swarm workers.

Each worker receives a scoped view of the task list — it can only see,
start, and complete its own assigned tasks.  Attempting to touch a task
outside the assigned set returns an explicit error, making scope violations
immediately visible and self-correcting.

The create_worker_tool_server() function returns an McpSdkServerConfig
passed to ClaudeAgentOptions.mcp_servers when creating a worker's Engine.
"""

import json
import subprocess
from pathlib import Path
from typing import Any, Optional

from claude_agent_sdk import tool, create_sdk_mcp_server

from state.mail import MailStore, MessageType
from state.task_list import TaskList
from state.port_allocations import allocate_ports_for_worker, get_worker_ports, release_ports_for_worker
from state.process_registry import ProcessRegistry


def create_worker_tool_server(
    worker_id: int,
    task_ids: list[str],
    task_list_dir: Path,
    mail_project_dir: Optional[Path] = None,
):
    """
    Create an in-process MCP server with task-scoped tools for a worker.

    The server exposes five tools:
        get_my_tasks           — scoped read: only the worker's assigned tasks
        start_task            — mark a task in_progress (scope-checked)
        complete_task         — mark a task done (scope-checked)
        report_blocker        — mark a task blocked (scope-checked)
        report_to_orchestrator — send status/question/blocker/progress to orchestrator

    Any attempt to reference a task ID outside the assigned set is rejected
    with an explicit error listing the allowed IDs.

    Args:
        worker_id:        Integer ID of this worker (for error messages)
        task_ids:         Exact task IDs assigned to this worker
        task_list_dir:    Worktree directory where task_list.json lives (worker writes here)
        mail_project_dir: Main project directory where mail.db lives (for report_to_orchestrator)
    """
    assigned: set[str] = set(task_ids)
    _dir = Path(task_list_dir)
    _mail_dir = Path(mail_project_dir) if mail_project_dir else None

    # ── helpers ─────────────────────────────────────────────────────

    def _load_my_tasks() -> list[dict]:
        tl = TaskList(_dir)
        tl.load()
        result = []
        for t in tl.tasks:
            if t.id in assigned:
                d = t.__dict__.copy() if hasattr(t, "__dict__") else dict(t)
                result.append(d)
        return result

    def _set_status(task_id: str, status: str, notes: str = "") -> dict:
        if task_id not in assigned:
            return {
                "error": (
                    f"Task {task_id!r} is NOT assigned to worker-{worker_id}. "
                    f"Your assigned tasks: {sorted(assigned)}. "
                    "You MUST NOT work on tasks outside your assignment."
                )
            }
        tl = TaskList(_dir)
        tl.load()
        for task in tl.tasks:
            if task.id == task_id:
                task.status = status
                if notes:
                    task.notes = notes
                tl.save()
                return {"ok": True, "task_id": task_id, "new_status": status}
        return {"error": f"Task {task_id!r} not found in task_list.json"}

    # ── tools ────────────────────────────────────────────────────────

    @tool(
        "get_my_tasks",
        (
            "Get YOUR assigned tasks — the ONLY tasks you are responsible for. "
            "ALWAYS call this first, before touching any files. "
            "DO NOT read .swarmweaver/task_list.json directly — it contains ALL "
            "tasks for all workers and will mislead you into working outside scope. "
            "This tool returns only YOUR subset with full details (description, "
            "acceptance criteria, files_affected, current status). "
            "When all tasks show status 'done', stop and call complete_task."
        ),
        {"type": "object", "properties": {}, "required": []},
    )
    async def get_my_tasks(args: dict[str, Any]) -> dict[str, Any]:
        tasks = _load_my_tasks()
        pending = [t for t in tasks if t.get("status") in ("pending", "in_progress")]
        done = [t for t in tasks if t.get("status") in ("done", "completed", "passed")]
        result = {
            "worker_id": worker_id,
            "assigned_task_ids": sorted(assigned),
            "tasks": tasks,
            "summary": {
                "total": len(tasks),
                "pending_or_in_progress": len(pending),
                "done": len(done),
            },
            "next_action": (
                "All your tasks are complete. Stop and await orchestrator instructions."
                if not pending
                else f"Start working on: {pending[0].get('id')}. Call start_task first."
            ),
            "scope_warning": (
                "You are ONLY allowed to work on the task IDs in assigned_task_ids. "
                "Do not implement, modify, or reference any other task."
            ),
        }
        return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}

    @tool(
        "start_task",
        (
            "Mark a task as in_progress immediately before you begin working on it. "
            "ALWAYS call this before editing any files for a task — it is your "
            "commitment to the orchestrator that you are working on this task. "
            "Returns an error (with your allowed task list) if the task ID is "
            "not in your assigned scope — do NOT proceed in that case."
        ),
        {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task ID to start — must be in your assigned_task_ids list",
                },
            },
            "required": ["task_id"],
        },
    )
    async def start_task(args: dict[str, Any]) -> dict[str, Any]:
        result = _set_status(args.get("task_id", ""), "in_progress")
        return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}

    @tool(
        "complete_task",
        (
            "Mark a task as done after you have fully implemented it. "
            "Call this BEFORE moving on to the next task — one task at a time. "
            "If all your tasks are done, stop working and wait for the orchestrator. "
            "Returns an error if the task is not in your assigned scope."
        ),
        {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task ID to mark done — must be in your assigned_task_ids list",
                },
                "notes": {
                    "type": "string",
                    "description": "Brief summary of what you implemented (optional)",
                },
            },
            "required": ["task_id"],
        },
    )
    async def complete_task(args: dict[str, Any]) -> dict[str, Any]:
        task_id = args.get("task_id", "")
        # Enforce one task at a time: fail if completing B while A is still in_progress
        tasks = _load_my_tasks()
        in_progress = [t for t in tasks if t.get("status") == "in_progress"]
        if in_progress and in_progress[0].get("id") != task_id:
            result = {
                "error": (
                    f"Complete {in_progress[0].get('id')} first (still in_progress) before "
                    f"completing {task_id}. Work on ONE task at a time."
                ),
                "in_progress": in_progress[0].get("id"),
            }
            return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}
        result = _set_status(task_id, "done", args.get("notes", ""))
        if result.get("ok"):
            # Commit task_list.json so task progress is persisted for long runs
            try:
                sp = subprocess.run(
                    ["git", "add", ".swarmweaver/task_list.json"],
                    cwd=str(_dir),
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if sp.returncode == 0:
                    subprocess.run(
                        ["git", "commit", "-m", f"task: complete {task_id}"],
                        cwd=str(_dir),
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
            except Exception as e:
                result["commit_note"] = f"task_list committed; git commit skipped: {e}"

            remaining = [
                t for t in _load_my_tasks()
                if t.get("status") in ("pending", "in_progress")
            ]
            result["tasks_remaining"] = len(remaining)
            result["next_action"] = (
                "All your tasks are complete. STOP working now and wait for the orchestrator."
                if not remaining
                else (
                    f"{len(remaining)} task(s) remaining. "
                    f"Call start_task('{remaining[0].get('id')}') to begin the next one."
                )
            )
        return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}

    @tool(
        "report_blocker",
        (
            "Report that a task cannot be completed due to a dependency or unresolvable issue. "
            "Use this when a task requires work from another worker's scope, or when you "
            "hit an error you cannot fix. The orchestrator will be notified. "
            "After reporting, move to your next pending task."
        ),
        {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task ID that is blocked",
                },
                "reason": {
                    "type": "string",
                    "description": "Why the task is blocked — be specific",
                },
            },
            "required": ["task_id", "reason"],
        },
    )
    async def report_blocker(args: dict[str, Any]) -> dict[str, Any]:
        task_id = args.get("task_id", "")
        reason = args.get("reason", "")
        if task_id not in assigned:
            result = {
                "error": f"Task {task_id!r} is not in your scope.",
                "your_tasks": sorted(assigned),
            }
            return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}

        tl = TaskList(_dir)
        tl.load()
        for task in tl.tasks:
            if task.id == task_id:
                task.status = "blocked"
                if hasattr(task, "blocker_reason"):
                    task.blocker_reason = reason
                else:
                    task.notes = f"BLOCKED: {reason}"
                tl.save()
                break

        result = {
            "ok": True,
            "task_id": task_id,
            "status": "blocked",
            "reason": reason,
            "next_action": "Move to your next pending task, or call get_my_tasks.",
        }
        return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}

    @tool(
        "report_to_orchestrator",
        (
            "Send status, question, blocker, or progress to the orchestrator. "
            "Use when blocked, when you need guidance, or to report completion immediately. "
            "The orchestrator reads these via get_worker_updates and can respond with send_directive."
        ),
        {
            "type": "object",
            "properties": {
                "msg_type": {
                    "type": "string",
                    "enum": ["status", "question", "blocker", "progress", "request_directive"],
                    "description": "Type: status (general update), question (need guidance), blocker (stuck), progress (task done), request_directive (need orchestrator input)",
                },
                "subject": {
                    "type": "string",
                    "description": "Short subject line",
                },
                "body": {
                    "type": "string",
                    "description": "Message body — be specific",
                },
            },
            "required": ["msg_type", "subject", "body"],
        },
    )
    async def report_to_orchestrator(args: dict[str, Any]) -> dict[str, Any]:
        if not _mail_dir:
            result = {
                "error": "report_to_orchestrator is not available — no mail_project_dir configured.",
            }
            return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}

        msg_type = args.get("msg_type", "status")
        subject = args.get("subject", "")
        body = args.get("body", "")
        sender = f"worker-{worker_id}"

        # Map msg_type to MailStore MessageType
        type_map = {
            "status": MessageType.WORKER_PROGRESS.value,
            "question": MessageType.QUESTION.value,
            "blocker": MessageType.ERROR.value,  # blocker is an error condition
            "progress": MessageType.WORKER_PROGRESS.value,
            "request_directive": MessageType.QUESTION.value,
        }
        store_type = type_map.get(msg_type, MessageType.WORKER_PROGRESS.value)

        try:
            store = MailStore(_mail_dir)
            store.initialize()
            store.send(
                sender=sender,
                recipient="orchestrator",
                msg_type=store_type,
                subject=subject,
                body=body,
            )
            result = {
                "ok": True,
                "message": "Report sent to orchestrator.",
                "msg_type": msg_type,
            }
        except Exception as e:
            result = {"error": f"Failed to send report: {e}"}
        return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}

    @tool(
        "get_my_ports",
        (
            "Get YOUR dedicated backend and frontend ports for servers and tests. "
            "ALWAYS call this BEFORE starting any server (uvicorn, npm run dev, etc.). "
            "Use these ports for ALL servers and test config. Set NEXT_PUBLIC_API_URL "
            "and .env vars to localhost:{backend}. Never use another worker's ports. "
            "Returns backend (e.g. 8010) and frontend (e.g. 3010) — stable for your session."
        ),
        {"type": "object", "properties": {}, "required": []},
    )
    async def get_my_ports(args: dict[str, Any]) -> dict[str, Any]:
        if not _mail_dir:
            result = {
                "error": "get_my_ports requires main project (mail_project_dir). Not available in this context.",
            }
            return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}
        try:
            ports = get_worker_ports(_mail_dir, worker_id) or allocate_ports_for_worker(_mail_dir, worker_id)
            result = {
                "worker_id": worker_id,
                "backend": ports["backend"],
                "frontend": ports["frontend"],
                "instructions": (
                    f"Use backend port {ports['backend']} for uvicorn/FastAPI/Flask. "
                    f"Use frontend port {ports['frontend']} for npm run dev. "
                    f"Set NEXT_PUBLIC_API_URL=http://localhost:{ports['backend']} in .env.local. "
                    "Never use ports 8000 or 3000 (reserved for SwarmWeaver). "
                    "Never touch another worker's ports."
                ),
            }
        except Exception as e:
            result = {"error": str(e)}
        return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}

    @tool(
        "close_my_ports",
        (
            "Terminate YOUR background server processes (backend, frontend) only. "
            "Call this when you finish testing, before completing your last task. "
            "Do NOT kill processes on other ports — only your own servers. "
            "This ensures clean shutdown without affecting other workers."
        ),
        {"type": "object", "properties": {}, "required": []},
    )
    async def close_my_ports(args: dict[str, Any]) -> dict[str, Any]:
        try:
            registry = ProcessRegistry(_dir)
            registry.load()
            status = registry.get_status()
            if status["total"] == 0:
                result = {"ok": True, "message": "No background processes to terminate.", "terminated": 0}
                return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}
            terminated = registry.terminate_all()
            if _mail_dir:
                release_ports_for_worker(_mail_dir, worker_id)
            result = {"ok": True, "message": f"Terminated {terminated} process(es).", "terminated": terminated}
        except RuntimeError as e:
            result = {"error": f"Registry not initialized: {e}"}
        except Exception as e:
            result = {"error": str(e)}
        return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}

    return create_sdk_mcp_server(
        "worker_tools",
        version="1.0.0",
        tools=[
            get_my_tasks,
            start_task,
            complete_task,
            report_blocker,
            report_to_orchestrator,
            get_my_ports,
            close_my_ports,
        ],
    )


# Tool names for allowed_tools lists
WORKER_TOOL_NAMES = [
    "mcp__worker_tools__get_my_tasks",
    "mcp__worker_tools__start_task",
    "mcp__worker_tools__complete_task",
    "mcp__worker_tools__report_blocker",
    "mcp__worker_tools__report_to_orchestrator",
    "mcp__worker_tools__get_my_ports",
    "mcp__worker_tools__close_my_ports",
]
