"""
Centralized Hook Definitions for Autonomous Coding Agent
========================================================

Implements Claude Agent SDK hooks for:
- PreToolUse: Security validation (bash_security_hook from security.py)
- PostToolUse: Audit logging + background process tracking
- Stop: Graceful shutdown, state saving, and process cleanup
- PreCompact: Transcript archival before summarization
- SubagentStop: Tracking parallel task completion

All hooks follow the SDK callback signature:
    async def hook(input_data: dict, tool_use_id: str | None, context: Any) -> dict
"""

import contextvars
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Awaitable, Optional

# Re-export the existing security hook for backward compatibility
from hooks.security import bash_security_hook
from core.paths import get_paths

# ---------------------------------------------------------------------------
# Per-asyncio-task context variables
# ---------------------------------------------------------------------------
# When multiple workers run in parallel (each as its own asyncio.Task), they
# must NOT share these paths — otherwise all workers write to the last-set
# global, making only the last worker's audit log visible.
#
# ContextVar values are isolated per asyncio Task: setting a ContextVar inside
# a task only affects that task (and any child tasks created from it).  All
# existing non-swarm code keeps working because ContextVar.get() falls back to
# the module-level global when no per-task value has been set.
# ---------------------------------------------------------------------------
_audit_log_ctx: contextvars.ContextVar[Optional[Path]] = contextvars.ContextVar(
    "swarmweaver_audit_log_path", default=None
)
_transcript_archive_ctx: contextvars.ContextVar[Optional[Path]] = contextvars.ContextVar(
    "swarmweaver_transcript_archive_path", default=None
)
_project_dir_ctx: contextvars.ContextVar[Optional[Path]] = contextvars.ContextVar(
    "swarmweaver_project_dir", default=None
)

# Module-level fallback globals (used when no per-task value is set)
_audit_log_path: Optional[Path] = None
_transcript_archive_path: Optional[Path] = None
_stop_callback: Optional[Callable[[], Awaitable[None]]] = None
_project_dir: Optional[Path] = None
_cleanup_processes_on_stop: bool = True
_notification_callback: Optional[Callable[[str, str, str], None]] = None


def _get_audit_log_path() -> Optional[Path]:
    """Return the audit log path for the current async task (or the global fallback)."""
    return _audit_log_ctx.get(_audit_log_path)


def _get_transcript_archive_path() -> Optional[Path]:
    """Return the transcript archive path for the current async task (or the global fallback)."""
    return _transcript_archive_ctx.get(_transcript_archive_path)


def _get_project_dir() -> Optional[Path]:
    """Return the project directory for the current async task (or the global fallback)."""
    return _project_dir_ctx.get(_project_dir)


def set_audit_log_path(path: Path) -> None:
    """Configure the audit log file path (per-task and global fallback)."""
    global _audit_log_path
    _audit_log_path = path        # fallback for tasks that haven't set their own value
    _audit_log_ctx.set(path)      # isolated value for the current asyncio task


def set_transcript_archive_path(path: Path) -> None:
    """Configure the transcript archive file path (per-task and global fallback)."""
    global _transcript_archive_path
    _transcript_archive_path = path
    _transcript_archive_ctx.set(path)


def set_stop_callback(callback: Callable[[], Awaitable[None]]) -> None:
    """Set the callback to invoke when the agent stops."""
    global _stop_callback
    _stop_callback = callback


def set_project_dir(path: Path) -> None:
    """Configure the project directory for process registry (per-task and global fallback)."""
    global _project_dir
    _project_dir = path
    _project_dir_ctx.set(path)


def set_cleanup_on_stop(enabled: bool) -> None:
    """Configure whether to cleanup background processes on stop."""
    global _cleanup_processes_on_stop
    _cleanup_processes_on_stop = enabled


def set_notification_callback(callback: Optional[Callable[[str, str, str], None]]) -> None:
    """Set a callback for sending notifications (event_type, title, body)."""
    global _notification_callback
    _notification_callback = callback


# --- Steering Hook ---

async def steering_hook(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
    """PreToolUse hook that checks for pending steering messages.

    Runs on ALL tools. When a steering message is found, blocks the current
    tool call and injects the steering message as the block reason, which
    the agent sees and must respond to.
    """
    project_dir = _get_project_dir()
    if project_dir is None:
        return {}

    try:
        from features.steering import has_pending_steering, read_steering_message, mark_steering_processed

        if not has_pending_steering(project_dir):
            return {}

        msg = read_steering_message(project_dir)
        if msg is None:
            return {}

        mark_steering_processed(project_dir)

        if msg.steering_type == "abort":
            return {
                "decision": "block",
                "reason": (
                    "[STEERING] ABORT requested by operator. "
                    "Stop all work immediately and save progress."
                ),
            }
        elif msg.steering_type == "reflect":
            return {
                "decision": "block",
                "reason": (
                    f"[STEERING] REFLECTION REQUESTED by operator:\n\n"
                    f"{msg.message}\n\n"
                    f"You MUST now:\n"
                    f"1. Read the current task_list.json\n"
                    f"2. Re-evaluate ALL tasks in light of this feedback\n"
                    f"3. You may: modify titles, add new tasks, skip tasks, "
                    f"change priorities, reorder dependencies\n"
                    f"4. Write the modified task_list.json\n"
                    f"5. Explain what you changed and why\n\n"
                    f"Then continue working on the next task."
                ),
            }
        else:
            # Regular instruction (directive from orchestrator/operator)
            return {
                "decision": "block",
                "reason": (
                    "[DIRECTIVE FROM ORCHESTRATOR — follow this instruction]\n\n"
                    f"{msg.message}\n\n"
                    "You MUST:\n"
                    "1. Acknowledge: call report_to_orchestrator(progress, \"Directive received\", "
                    "\"Acknowledged: <brief summary of what you will do>\")\n"
                    "2. Adjust your work according to the directive above\n"
                    "3. Continue with your tasks"
                ),
            }
    except Exception:
        return {}


def _worker_scope_block_reason() -> dict:
    return {
        "decision": "block",
        "reason": (
            "Direct access to .swarmweaver/task_list.json is disabled for swarm workers. "
            "Use mcp__worker_tools__get_my_tasks to read your tasks, "
            "mcp__worker_tools__start_task before implementing, and "
            "mcp__worker_tools__complete_task when done."
        ),
    }


async def worker_scope_hook(
    input_data: dict[str, Any],
    tool_use_id: Optional[str],
    context: Any,
) -> dict[str, Any]:
    """
    PreToolUse hook that blocks direct Read/Edit/Write of .swarmweaver/task_list.json
    and Bash commands that cat/grep it, when the agent is a swarm worker.

    Swarm workers MUST use get_my_tasks, start_task, complete_task MCP tools instead.
    """
    project_dir = _get_project_dir()
    if project_dir is None:
        return {}

    swarm_marker = project_dir / ".swarmweaver" / "swarm_worker"
    if not swarm_marker.exists():
        return {}

    tool_name = input_data.get("tool_name")
    tool_input = input_data.get("tool_input", {})

    if tool_name in ("Read", "Edit", "Write"):
        file_path = str(tool_input.get("file_path", ""))
        if file_path:
            path_lower = file_path.replace("\\", "/").lower()
            if "task_list.json" in path_lower and ".swarmweaver" in path_lower:
                return _worker_scope_block_reason()
        return {}

    if tool_name == "Bash":
        command = str(tool_input.get("command", ""))
        if not command:
            return {}
        cmd_lower = command.lower()
        # Block cat/head/tail/grep of task_list.json
        if "task_list.json" in cmd_lower and any(
            x in cmd_lower for x in ("cat ", "head ", "tail ", "grep ", "python", "python3")
        ):
            return _worker_scope_block_reason()
        return {}

    return {}


def _get_process_registry():
    """Get the process registry, initializing if needed."""
    project_dir = _get_project_dir()
    if project_dir is None:
        return None
    try:
        from state.process_registry import get_registry
        return get_registry(project_dir)
    except Exception:
        return None


def _extract_background_process_info(tool_input: dict, tool_result: Any) -> Optional[dict]:
    """
    Extract background process information from Bash tool results.
    
    Returns dict with pid, port, command, process_type if a background process was started.
    """
    command = tool_input.get("command", "")
    
    # Check if this is a background command
    is_background = (
        tool_input.get("run_in_background", False) or
        tool_input.get("background", False) or
        command.rstrip().endswith("&")
    )
    
    if not is_background:
        return None
    
    # Try to extract PID from result
    pid = None
    result_str = str(tool_result) if tool_result else ""
    
    # Look for PID patterns in output
    pid_match = re.search(r'\[(\d+)\]|\bPID[:\s]+(\d+)|started.*?(\d{4,})', result_str, re.IGNORECASE)
    if pid_match:
        pid = int(next(g for g in pid_match.groups() if g))
    
    # Look for task_id pattern (from SDK Task tool)
    task_match = re.search(r'task_id[\'"]?\s*[:=]\s*[\'"]?([a-f0-9]+)', result_str, re.IGNORECASE)
    
    if not pid and not task_match:
        return None
    
    # Detect port from command
    port = None
    port_match = re.search(r'--port[=\s]+(\d+)|-p\s+(\d+)|:\s*(\d{4,5})\b', command)
    if port_match:
        port = int(next(g for g in port_match.groups() if g))
    
    # Detect process type
    cmd_lower = command.lower()
    if any(x in cmd_lower for x in ['uvicorn', 'gunicorn', 'flask', 'django', 'fastapi']):
        process_type = 'backend'
    elif any(x in cmd_lower for x in ['next', 'vite', 'react', 'npm run dev', 'pnpm dev']):
        process_type = 'frontend'
    elif any(x in cmd_lower for x in ['pytest', 'jest', 'test']):
        process_type = 'test'
    else:
        process_type = 'dev-tool'
    
    return {
        "pid": pid,
        "port": port,
        "command": command[:200],  # Truncate long commands
        "process_type": process_type,
        "task_id": task_match.group(1) if task_match else None
    }


async def audit_log_hook(
    input_data: dict[str, Any],
    tool_use_id: Optional[str],
    context: Any
) -> dict[str, Any]:
    """
    PostToolUse hook that logs all tool executions for auditing.

    Creates an append-only JSON lines log file with tool execution details.
    Also tracks background processes in the process registry.
    Never crashes - logging failures are silently ignored.
    """
    tool_name = input_data.get("tool_name", "unknown")
    tool_input = input_data.get("tool_input", {})
    tool_result = input_data.get("tool_result", None)
    is_error = input_data.get("is_error", False)
    
    # Track background processes from Bash commands
    if tool_name == "Bash" and not is_error:
        try:
            process_info = _extract_background_process_info(tool_input, tool_result)
            if process_info and process_info.get("pid"):
                registry = _get_process_registry()
                if registry:
                    registry.register(
                        pid=process_info["pid"],
                        port=process_info["port"],
                        command=process_info["command"],
                        process_type=process_info["process_type"]
                    )
                    print(f"[HOOK] Registered background process: PID {process_info['pid']} "
                          f"({process_info['process_type']}) on port {process_info['port'] or 'N/A'}")
        except Exception as e:
            print(f"[HOOK] Warning: Failed to track background process: {e}")
    
    # Send notifications on errors
    if is_error and _notification_callback:
        try:
            error_preview = str(tool_result)[:200] if tool_result else "Unknown error"
            _notification_callback(
                "error",
                f"SwarmWeaver Error: {tool_name}",
                error_preview,
            )
        except Exception:
            pass

    # Audit logging (with sanitization to prevent secret leakage to disk)
    audit_log_path = _get_audit_log_path()
    if audit_log_path:
        try:
            from utils.sanitizer import sanitize
            entry = {
                "timestamp": datetime.now().isoformat(),
                "tool_use_id": tool_use_id,
                "tool_name": tool_name,
                "tool_input_preview": sanitize(str(tool_input)[:200]),
                "is_error": is_error,
            }

            with open(audit_log_path, "a") as f:
                f.write(json.dumps(entry) + "\n")

        except Exception:
            # Never crash on logging failures
            pass

    return {}


async def stop_hook(
    input_data: dict[str, Any],
    tool_use_id: Optional[str],
    context: Any
) -> dict[str, Any]:
    """
    Stop hook for graceful shutdown and state saving.

    Invokes the configured stop callback to persist state before exit.
    Also cleans up background processes if configured.
    """
    print("[HOOK] Stop event received - saving state...")

    if _stop_callback:
        try:
            await _stop_callback()
            print("[HOOK] State saved successfully")
        except Exception as e:
            print(f"[HOOK] Stop callback error: {e}")
    
    # Cleanup background processes
    if _cleanup_processes_on_stop:
        try:
            registry = _get_process_registry()
            if registry:
                status = registry.get_status()
                if status["total"] > 0:
                    print(f"[HOOK] Cleaning up {status['total']} background processes...")
                    terminated = registry.terminate_all()
                    print(f"[HOOK] Terminated {terminated} processes")
        except Exception as e:
            print(f"[HOOK] Process cleanup error: {e}")

    return {}


async def pre_compact_hook(
    input_data: dict[str, Any],
    tool_use_id: Optional[str],
    context: Any
) -> dict[str, Any]:
    """
    PreCompact hook for transcript archival before summarization.

    Archives transcript metadata before the conversation is compacted.
    Useful for maintaining full history for debugging.
    """
    print("[HOOK] PreCompact - archiving transcript metadata...")

    transcript_archive_path = _get_transcript_archive_path()
    if not transcript_archive_path:
        return {}

    try:
        trigger = input_data.get("trigger", "unknown")  # 'manual' or 'auto'
        transcript_path = input_data.get("transcript_path", "")

        archive_entry = {
            "timestamp": datetime.now().isoformat(),
            "trigger": trigger,
            "transcript_path": transcript_path,
            "event": "pre_compact",
        }

        with open(transcript_archive_path, "a") as f:
            f.write(json.dumps(archive_entry) + "\n")

    except Exception as e:
        print(f"[HOOK] PreCompact archive error: {e}")

    # Save task state for context recovery after compaction
    try:
        project_dir = _get_project_dir()
        if project_dir:
            from state.task_list import TaskList
            tl = TaskList(project_dir)
            if tl.load():
                in_progress = [
                    {"id": t.id, "title": t.title[:50]}
                    for t in tl.get_tasks_by_status("in_progress")
                ]
                snapshot = {
                    "timestamp": datetime.now().isoformat(),
                    "total": tl.total,
                    "done": tl.done_count,
                    "pending": tl.pending_count,
                    "in_progress": in_progress,
                }
                snapshot_path = Path(project_dir) / ".swarmweaver" / "context_snapshot.json"
                snapshot_path.write_text(json.dumps(snapshot, indent=2))

                # Write steering message for context recovery
                from features.steering import write_steering_message
                in_prog_str = ", ".join(f"{t['id']}" for t in in_progress[:5]) if in_progress else "none"
                write_steering_message(
                    Path(project_dir),
                    f"[CONTEXT RECOVERY] Your context was compacted. "
                    f"State: {snapshot['done']}/{snapshot['total']} tasks done. "
                    f"In-progress: {in_prog_str}. "
                    f"Re-read your task list with get_my_tasks or check .swarmweaver/task_list.json.",
                    "instruction",
                )
    except Exception as e:
        print(f"[HOOK] Context snapshot error: {e}")

    return {}


async def subagent_stop_hook(
    input_data: dict[str, Any],
    tool_use_id: Optional[str],
    context: Any
) -> dict[str, Any]:
    """
    SubagentStop hook for tracking parallel task completion.

    Logs when subagents complete their work for monitoring and debugging.
    """
    stop_hook_active = input_data.get("stop_hook_active", False)

    print(f"[HOOK] Subagent completed (tool_use_id: {tool_use_id})")
    if stop_hook_active:
        print("[HOOK]   Stop hook was active during completion")

    return {}


async def log_consolidation_hook(
    input_data: dict[str, Any],
    tool_use_id: Optional[str],
    context: Any
) -> dict[str, Any]:
    """
    PreToolUse hook that consolidates log file creation.
    
    When agent tries to create a new log file, redirect to standard names:
    - backend*.log -> logs/backend.log
    - frontend*.log -> logs/frontend.log
    """
    tool_name = input_data.get("tool_name")
    if tool_name not in ("Write", "Bash"):
        return {}
    
    tool_input = input_data.get("tool_input", {})
    
    try:
        if tool_name == "Write":
            file_path = str(tool_input.get("file_path", "")).lower()
            if "backend" in file_path and ".log" in file_path:
                # Redirect to standard backend.log
                _pd = _get_project_dir()
                if _pd:
                    new_path = _pd / "logs" / "backend.log"
                    print(f"[HOOK] ⚡ LOG CONSOLIDATION: Redirecting to logs/backend.log")
                    return {"modify_input": {"file_path": str(new_path)}}
            elif "frontend" in file_path and ".log" in file_path:
                _pd = _get_project_dir()
                if _pd:
                    new_path = _pd / "logs" / "frontend.log"
                    print(f"[HOOK] ⚡ LOG CONSOLIDATION: Redirecting to logs/frontend.log")
                    return {"modify_input": {"file_path": str(new_path)}}
        
        elif tool_name == "Bash":
            command = tool_input.get("command", "")
            # Check for log file redirects in bash commands
            if "> " in command or ">> " in command:
                # Look for non-standard log files
                import re
                log_match = re.search(r'>\s*[\'"]?([^\s\'"]+\.log)', command)
                if log_match:
                    log_file = log_match.group(1)
                    if "backend" in log_file.lower() and log_file != "logs/backend.log":
                        new_cmd = command.replace(log_file, "logs/backend.log")
                        print(f"[HOOK] ⚡ LOG CONSOLIDATION: Redirecting output to logs/backend.log")
                        return {"modify_input": {"command": new_cmd}}
                    elif "frontend" in log_file.lower() and log_file != "logs/frontend.log":
                        new_cmd = command.replace(log_file, "logs/frontend.log")
                        print(f"[HOOK] ⚡ LOG CONSOLIDATION: Redirecting output to logs/frontend.log")
                        return {"modify_input": {"command": new_cmd}}
                        
    except Exception as e:
        print(f"[HOOK] Log consolidation error: {e}")
    
    return {}


async def shell_script_lf_hook(
    input_data: dict[str, Any],
    tool_use_id: Optional[str],
    context: Any
) -> dict[str, Any]:
    """
    PostToolUse hook that normalizes .sh files to LF line endings.
    
    When the agent writes a shell script via the Write tool, Windows/CRLF
    line endings can corrupt the shebang and cause 'invalid option' or
    'command not found' errors in WSL/Linux bash. This hook rewrites
    the file with LF-only line endings after each Write to *.sh.
    """
    if input_data.get("tool_name") != "Write":
        return {}
    
    tool_input = input_data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")
    if not file_path or not str(file_path).lower().endswith(".sh"):
        return {}
    
    try:
        project_dir = _get_project_dir()
        if project_dir is None:
            return {}
        
        path = Path(file_path)
        if not path.is_absolute():
            path = project_dir / path
        if not path.exists():
            return {}
        
        content = path.read_text(encoding="utf-8", errors="replace")
        normalized = content.replace("\r\n", "\n").replace("\r", "\n")
        if content != normalized:
            path.write_text(normalized, encoding="utf-8", newline="\n")
            print(f"[HOOK] ✓ Normalized {path.name} to LF line endings (CRLF removed)")
    except Exception as e:
        print(f"[HOOK] Shell script LF normalization error: {e}")
    
    return {}


async def progress_file_management_hook(
    input_data: dict[str, Any],
    tool_use_id: Optional[str],
    context: Any
) -> dict[str, Any]:
    """
    PostToolUse hook that manages progress file size.
    
    When progress file gets too large (>2000 lines), auto-archive old content
    and keep only recent sessions.
    """
    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})
    
    # Only check after edits to progress file
    if tool_name != "Edit":
        return {}
    
    file_path = str(tool_input.get("file_path", ""))
    if "progress" not in file_path.lower():
        return {}
    
    try:
        _pd = _get_project_dir()
        if _pd is None:
            return {}

        progress_file = get_paths(_pd).resolve_read("claude-progress.txt")
        if not progress_file.exists():
            return {}
        
        content = progress_file.read_text()
        lines = content.split('\n')
        
        # If file is too large, warn and suggest archiving
        if len(lines) > 2000:
            print(f"[HOOK] ⚠️  PROGRESS FILE TOO LARGE: {len(lines)} lines")
            print(f"[HOOK]    Consider archiving old sessions to docs/archived_progress.txt")
            print(f"[HOOK]    Keep only last 500 lines in claude-progress.txt")
            
    except Exception as e:
        print(f"[HOOK] Progress management error: {e}")
    
    return {}


async def knowledge_injection_hook(
    input_data: dict[str, Any],
    tool_use_id: Optional[str],
    context: Any
) -> dict[str, Any]:
    """
    PostToolUse hook that AUTONOMOUSLY injects relevant documentation.
    
    When the agent reads certain files or runs certain commands,
    this hook automatically suggests or injects relevant documentation.
    
    Triggers:
    1. Agent encounters errors -> Suggest web search
    2. Agent works on classification -> Inject Annex III reference
    3. Agent works on A2A/AG-UI -> Inject protocol docs
    """
    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})
    tool_result = input_data.get("tool_result", "")
    is_error = input_data.get("is_error", False)
    
    result_str = str(tool_result).lower() if tool_result else ""
    
    suggestions = []
    
    try:
        # TRIGGER 1: Error encountered -> Suggest web search
        if is_error and tool_result:
            error_text = str(tool_result)[:200]
            suggestions.append(
                f"[HOOK] 💡 ERROR DETECTED - Consider using web search:\n"
                f"       mcp__web_search__search(query=\"{error_text[:50]}...\")"
            )
        
        
        # TRIGGER 3: Working on classification
        if tool_name in ("Read", "Edit", "Write"):
            file_path = str(tool_input.get("file_path", "")).lower()
            if "classif" in file_path or "risk" in file_path:
                suggestions.append(
                    "[HOOK] 💡 CLASSIFICATION CODE - Reference Annex III categories:\n"
                    "       Grep(pattern=\"Annex III\", path=\"docs/\")"
                )
        
        # TRIGGER 4: Working on A2A protocol
        if tool_name in ("Read", "Edit", "Write"):
            file_path = str(tool_input.get("file_path", "")).lower()
            if "a2a" in file_path or "agent" in file_path:
                suggestions.append(
                    "[HOOK] 💡 A2A PROTOCOL CODE - Read the protocol docs:\n"
                    "       Read(file_path=\"docs/A2A.md\")"
                )
        
        # TRIGGER 5: Working on AG-UI
        if tool_name in ("Read", "Edit", "Write"):
            file_path = str(tool_input.get("file_path", "")).lower()
            if "agui" in file_path or "ag-ui" in file_path or "copilot" in file_path:
                suggestions.append(
                    "[HOOK] 💡 AG-UI PROTOCOL CODE - Read the protocol docs:\n"
                    "       Read(file_path=\"docs/ag-ui.md\")"
                )
        
        # TRIGGER 6: Import errors or module not found
        if is_error and any(x in result_str for x in ["import", "modulenotfound", "no module"]):
            suggestions.append(
                "[HOOK] 💡 IMPORT ERROR - Search for correct import:\n"
                "       mcp__web_search__search(query=\"python <module> import example\")"
            )
        
        # TRIGGER 7: API or HTTP errors
        if is_error and any(x in result_str for x in ["http", "api", "request", "connection", "timeout"]):
            suggestions.append(
                "[HOOK] 💡 API ERROR - Check API documentation:\n"
                "       mcp__web_search__search(query=\"<service> API documentation\")"
            )
        
        # Print suggestions
        for suggestion in suggestions:
            print(suggestion)
        
    except Exception as e:
        print(f"[HOOK] Knowledge injection error: {e}")
    
    return {}


async def file_management_hook(
    input_data: dict[str, Any],
    tool_use_id: Optional[str],
    context: Any
) -> dict[str, Any]:
    """
    PreToolUse hook that AUTONOMOUSLY manages file organization.
    
    This hook makes automatic decisions:
    1. If creating a test/check/debug script in project root -> AUTO-REDIRECT to scripts/ dir
    2. If creating a file that already exists -> BLOCK and notify
    3. If creating session notes in root -> AUTO-REDIRECT to docs/ dir
    4. If creating screenshots in root -> AUTO-REDIRECT to screenshots/ dir
    
    Keeps the project root clean automatically.
    """
    tool_name = input_data.get("tool_name")
    if tool_name not in ("Write", "Edit"):
        return {}
    
    tool_input = input_data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")
    if not file_path:
        return {}
    
    try:
        from pathlib import Path
        
        path = Path(file_path)
        filename = path.name
        parent = path.parent

        # Get project directory from per-task context
        project_dir = _get_project_dir()
        if project_dir is None:
            return {}

        # Only apply to files in project root
        if parent != project_dir and str(parent) != str(project_dir):
            return {}
        
        # DECISION 1: Auto-redirect test/check/debug scripts to scripts/ directory
        temp_script_patterns = [
            'test_', 'check_', 'debug_', 'verify_', 'quick_', 
            'kill_', 'restart_', 'start_', 'mark_test', 'show_', 
            'find_', 'create_sample', 'update_', 'fix_', 'unmark_',
            'wait_', 'force_', 'aggressive_', 'diagnose_', 'add_'
        ]
        
        if any(filename.startswith(p) for p in temp_script_patterns) and filename.endswith('.py'):
            scripts_dir = project_dir / "scripts"
            scripts_dir.mkdir(exist_ok=True)
            new_path = scripts_dir / filename
            
            print(f"[HOOK] ⚡ AUTO-REDIRECTING script to scripts/: {filename}")
            return {
                "modify_input": {
                    "file_path": str(new_path)
                }
            }
        
        # DECISION 2: Auto-redirect session notes to docs/ directory
        session_patterns = ['session', 'SESSION', 'URGENT', 'NEXT_SESSION', 'KNOWN_ISSUES']
        if any(p in filename for p in session_patterns) and filename.endswith('.md'):
            docs_dir = project_dir / "docs"
            docs_dir.mkdir(exist_ok=True)
            new_path = docs_dir / filename
            
            print(f"[HOOK] ⚡ AUTO-REDIRECTING notes to docs/: {filename}")
            return {
                "modify_input": {
                    "file_path": str(new_path)
                }
            }
        
        # DECISION 3: Auto-redirect screenshots to screenshots/ directory
        if filename.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
            screenshots_dir = project_dir / "screenshots"
            screenshots_dir.mkdir(exist_ok=True)
            new_path = screenshots_dir / filename
            
            print(f"[HOOK] ⚡ AUTO-REDIRECTING screenshot to screenshots/: {filename}")
            return {
                "modify_input": {
                    "file_path": str(new_path)
                }
            }
        
    except Exception as e:
        print(f"[HOOK] File management error: {e}")
    
    return {}


async def test_script_port_hook(
    input_data: dict[str, Any],
    tool_use_id: Optional[str],
    context: Any
) -> dict[str, Any]:
    """
    PreToolUse hook that fixes hardcoded ports in test scripts being written.
    
    When agent writes a test_*.py script, automatically replaces hardcoded
    backend ports with the actual running port.
    """
    tool_name = input_data.get("tool_name")
    if tool_name != "Write":
        return {}
    
    tool_input = input_data.get("tool_input", {})
    file_path = str(tool_input.get("file_path", ""))
    content = tool_input.get("content", "")
    
    # Only apply to test scripts
    if not (file_path.endswith('.py') and ('test_' in file_path or 'check_' in file_path or 'verify_' in file_path)):
        return {}
    
    # Check if content has hardcoded localhost ports
    if 'localhost:80' not in content:
        return {}
    
    try:
        # Swarm worker: use allocated backend port; else configured/running port
        worker_ports = _get_worker_ports()
        actual_port = worker_ports[0] if worker_ports else _get_configured_backend_port()
        
        # Replace any hardcoded backend port with the actual one
        new_content = content
        ports_to_replace = [8000, 8001, 8002, 8003, 8004, 8005, 8006]
        
        for port in ports_to_replace:
            if port == actual_port:
                continue
            if f'localhost:{port}' in content:
                new_content = new_content.replace(f'localhost:{port}', f'localhost:{actual_port}')
                print(f"[HOOK] ⚡ AUTO-FIXING test script: port {port} → {actual_port}")
        
        if new_content != content:
            return {
                "modify_input": {
                    "content": new_content
                }
            }
        
    except Exception as e:
        print(f"[HOOK] Test script port fix error: {e}")
    
    return {}


def _detect_running_backend_port() -> Optional[int]:
    """Detect which port the backend is actually running on."""
    import socket
    
    # Check ports in order of preference
    ports_to_check = [8000, 8003, 8001, 8004, 8005, 8006]
    
    for port in ports_to_check:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            result = sock.connect_ex(('localhost', port))
            sock.close()
            if result == 0:
                return port
        except:
            pass
    return None


def _get_configured_backend_port() -> int:
    """Get the configured backend port from .env or detect running server."""
    _pd = _get_project_dir()
    if _pd is None:
        return 8000

    # First check .env.local for configured port
    env_file = _pd / "frontend" / ".env.local"
    if env_file.exists():
        content = env_file.read_text()
        match = re.search(r'NEXT_PUBLIC_API_URL.*?:(\d+)', content)
        if match:
            return int(match.group(1))
    
    # Otherwise detect running server
    detected = _detect_running_backend_port()
    if detected:
        return detected
    
    return 8000  # Default


def _get_worker_ports():
    """
    If running in swarm worker mode, return (backend_port, frontend_port) for this worker.
    Otherwise return None.
    """
    _pd = _get_project_dir()
    if _pd is None:
        return None
    swarm_marker = _pd / ".swarmweaver" / "swarm_worker"
    if not swarm_marker.exists():
        return None
    try:
        content = swarm_marker.read_text(encoding="utf-8").strip()
        # Format: "worker-N"
        if content.startswith("worker-"):
            worker_id = int(content.split("-", 1)[1])
        else:
            return None
    except (ValueError, OSError):
        return None
    # Worktree is at main/.swarmweaver/swarm/worker-N -> main = parent.parent
    main_project = _pd.parent.parent
    try:
        from state.port_allocations import allocate_ports_for_worker
        ports = allocate_ports_for_worker(main_project, worker_id)
        return (ports["backend"], ports["frontend"])
    except Exception:
        return None


# Ports reserved for SwarmWeaver; agent must not kill processes on these ports
SWARMWEAVER_BACKEND_PORT = 8000
SWARMWEAVER_FRONTEND_PORT = 3000


async def protect_swarmweaver_backend_hook(
    input_data: dict[str, Any],
    tool_use_id: Optional[str],
    context: Any
) -> dict[str, Any]:
    """
    PreToolUse hook that prevents the agent from killing the SwarmWeaver backend or frontend.

    When the agent runs commands like `lsof -i :8000 | xargs kill -9` or
    `lsof -i :3000 | xargs kill -9` to free a port before starting a project's
    server, it would kill the SwarmWeaver control plane (backend on 8000,
    frontend on 3000). This hook MODIFIES such commands to use alternate
    ports (8001 for backend, 3001 for frontend) so the project's servers
    run on those ports and SwarmWeaver stays alive.
    """
    if input_data.get("tool_name") != "Bash":
        return {}

    tool_input = input_data.get("tool_input", {})
    command = tool_input.get("command", "")
    if not command:
        return {}

    has_kill = "kill" in command or "xargs" in command
    if not ("lsof" in command and has_kill):
        return {}

    # Protected ports and their project alternates: (port, alt_port, name)
    protected = [
        (SWARMWEAVER_BACKEND_PORT, 8001, "backend"),
        (SWARMWEAVER_FRONTEND_PORT, 3001, "frontend"),
    ]

    new_command = command
    messages = []

    for port, alt_port, name in protected:
        has_lsof_on_port = (
            f":{port}" in command or
            f": {port}" in command or
            f"-i:{port}" in command
        )
        if not has_lsof_on_port:
            continue

        replacements = [
            (f":{port}", f":{alt_port}"),
            (f": {port}", f": {alt_port}"),
            (f"-i:{port}", f"-i:{alt_port}"),
            (f"--port {port}", f"--port {alt_port}"),
            (f"--port={port}", f"--port={alt_port}"),
            (f"-p {port}", f"-p {alt_port}"),
        ]
        for old, new in replacements:
            if old in new_command and old.strip() != "":
                new_command = new_command.replace(old, new)
        messages.append(f"{port} ({name}) → {alt_port}")

    if new_command != command:
        print(f"[HOOK] Ports 8000 (backend) and 3000 (frontend) are reserved for SwarmWeaver.")
        print(f"[HOOK]   Redirecting: {', '.join(messages)}")
        return {"modify_input": {"command": new_command}}

    return {}


async def port_config_hook(
    input_data: dict[str, Any],
    tool_use_id: Optional[str],
    context: Any
) -> dict[str, Any]:
    """
    PreToolUse hook that injects standard port configuration.
    
    Automatically replaces hardcoded ports with the ACTUAL running backend port:
    - Detects which port backend is running on
    - Replaces ALL hardcoded backend ports in commands
    
    This prevents port mismatch errors in test scripts.
    """
    if input_data.get("tool_name") != "Bash":
        return {}
    
    tool_input = input_data.get("tool_input", {})
    command = tool_input.get("command", "")
    if not command:
        return {}
    
    try:
        # Only apply to commands that reference localhost ports
        if 'localhost:80' not in command:
            return {}
        
        if _get_project_dir() is None:
            return {}

        # Swarm worker: use allocated backend port; else configured/running port
        worker_ports = _get_worker_ports()
        actual_port = worker_ports[0] if worker_ports else _get_configured_backend_port()
        
        # Replace any hardcoded backend port with the actual one
        new_command = command
        ports_to_replace = [8000, 8001, 8002, 8003, 8004, 8005, 8006]
        
        for port in ports_to_replace:
            if port == actual_port:
                continue  # Don't replace if it's already correct
            if f'localhost:{port}' in command:
                new_command = new_command.replace(f'localhost:{port}', f'localhost:{actual_port}')
                print(f"[HOOK] ⚡ AUTO-REPLACING port {port} with actual running port {actual_port}")
        
        if new_command != command:
            return {
                "modify_input": {
                    "command": new_command
                }
            }
        
    except Exception as e:
        print(f"[HOOK] Port config error: {e}")
    
    return {}


async def environment_management_hook(
    input_data: dict[str, Any],
    tool_use_id: Optional[str],
    context: Any
) -> dict[str, Any]:
    """
    PreToolUse hook that AUTONOMOUSLY manages Python and Node environments.
    
    This hook makes automatic decisions:
    1. If activating venv that doesn't exist -> AUTO-CREATE it first
    2. If running pip install but venv exists -> AUTO-PREPEND venv activation
    3. If running npm/pnpm but node_modules exists -> SKIP npm install
    4. If trying to create venv that already exists -> SKIP and notify
    
    The agent does NOT need to check environments - this hook handles everything.
    """
    if input_data.get("tool_name") != "Bash":
        return {}
    
    tool_input = input_data.get("tool_input", {})
    command = tool_input.get("command", "")
    if not command:
        return {}
    
    cmd_lower = command.lower()
    
    try:
        import os
        from pathlib import Path
        
        # Get project directory from per-task context
        project_dir = _get_project_dir()
        if project_dir is None:
            return {}

        # DECISION 1: Skip venv creation if it already exists
        if 'python -m venv' in cmd_lower or 'python3 -m venv' in cmd_lower:
            # Extract venv path from command
            venv_match = re.search(r'venv\s+(\S+)', command)
            venv_name = venv_match.group(1) if venv_match else 'venv'
            venv_path = project_dir / venv_name
            
            if venv_path.exists() and (venv_path / 'Scripts').exists():
                print(f"[HOOK] ✓ Python venv '{venv_name}' already exists - SKIPPING creation")
                return {
                    "decision": "block",
                    "reason": f"Virtual environment '{venv_name}' already exists. No need to create it again."
                }
        
        # DECISION 2: Skip plain npm install if node_modules exists and is populated.
        # Allow npm install -D pkg, npm install pkg, etc. (adding packages).
        if ('npm install' in cmd_lower or 'pnpm install' in cmd_lower or 'yarn install' in cmd_lower) and '--' not in cmd_lower:
            # Allow when adding packages: -D, --save-dev, -g, --global, or package names (@, /)
            if any(x in cmd_lower for x in [' -d ', ' -d', '--save-dev', ' -g ', ' -g', '--global']) or '@' in command or ' /' in command:
                pass  # Allow - adding packages
            else:
                for subdir in ['', 'frontend', 'client']:
                    check_path = project_dir / subdir / 'node_modules' if subdir else project_dir / 'node_modules'
                    if check_path.exists() and any(check_path.iterdir()):
                        # Check if command has package args (e.g. "npm install tailwindcss")
                        rest = command.split('install', 1)[-1].strip() if 'install' in cmd_lower else ''
                        # Block only if rest is empty or just shell redirects (2>&1, |, etc.)
                        if not rest or re.match(r'^[\|\>\&\d\s]+$', rest):
                            print(f"[HOOK] ✓ node_modules already populated in {subdir or 'root'} - SKIPPING install")
                            return {
                                "decision": "block",
                                "reason": f"node_modules already exists and is populated. No need to run npm install again."
                            }
                        break  # Has package args, allow
        
        # DECISION 3: Auto-use venv Python for pip commands
        if 'pip install' in cmd_lower and 'venv' not in cmd_lower:
            # Check if venv exists in backend or root
            for venv_loc in ['backend/venv', 'venv']:
                venv_path = project_dir / venv_loc
                if venv_path.exists():
                    # Windows path
                    venv_python = venv_path / 'Scripts' / 'python.exe'
                    if not venv_python.exists():
                        # Unix path
                        venv_python = venv_path / 'bin' / 'python'
                    
                    if venv_python.exists():
                        # Modify command to use venv python
                        new_command = command.replace('pip install', f'"{venv_python}" -m pip install')
                        print(f"[HOOK] ⚡ AUTO-USING venv Python for pip: {venv_loc}")
                        return {
                            "modify_input": {
                                "command": new_command
                            }
                        }
        
    except Exception as e:
        print(f"[HOOK] Environment management error: {e}")
    
    return {}


async def server_management_hook(
    input_data: dict[str, Any],
    tool_use_id: Optional[str],
    context: Any
) -> dict[str, Any]:
    """
    PreToolUse hook that AUTONOMOUSLY manages server processes.
    
    This hook makes automatic decisions:
    1. If a server of the same type is already running -> BLOCK and notify (reuse existing)
    2. If port is taken by different process type -> AUTO-KILL old process and allow
    3. If port is taken by untracked process -> AUTO-MODIFY command to use available port
    
    The agent does NOT need to make decisions - this hook handles everything.
    """
    if input_data.get("tool_name") != "Bash":
        return {}
    
    tool_input = input_data.get("tool_input", {})
    command = tool_input.get("command", "")
    if not command:
        return {}
    
    # Detect if this is a server-starting command
    cmd_lower = command.lower()
    server_patterns = {
        'backend': ['uvicorn', 'gunicorn', 'flask run', 'django', 'fastapi'],
        'frontend': ['next dev', 'vite', 'npm run dev', 'pnpm dev', 'npx next', 'yarn dev'],
    }
    
    detected_type = None
    for stype, patterns in server_patterns.items():
        if any(p in cmd_lower for p in patterns):
            detected_type = stype
            break
    
    if not detected_type:
        return {}
    
    # Check if this is a background command
    is_background = (
        tool_input.get("run_in_background", False) or
        tool_input.get("background", False) or
        command.rstrip().endswith("&")
    )
    
    # Swarm worker: use allocated ports (each worker gets dedicated backend/frontend)
    worker_ports = _get_worker_ports()
    
    try:
        registry = _get_process_registry()
        if not registry:
            return {}
        
        # DECISION 1: Check if same type of server is already running
        existing_same_type = registry.get_processes_by_type(detected_type)
        alive_same_type = [p for p in existing_same_type if p.is_alive()]
        
        if alive_same_type:
            existing = alive_same_type[0]
            print(f"[HOOK] ✓ {detected_type.upper()} server already running: PID {existing.pid} on port {existing.port}")
            print(f"[HOOK]   BLOCKING duplicate server start - reuse existing server")
            return {
                "decision": "block",
                "reason": f"{detected_type} server already running on port {existing.port} (PID {existing.pid}). No need to start another one."
            }
        
        # Extract port from command
        port = None
        port_match = re.search(r'--port[=\s]+(\d+)|-p\s+(\d+)|:(\d{4,5})\b', command)
        if port_match:
            port = int(next(g for g in port_match.groups() if g))
        
        # Get target port: worker-allocated or standard
        if worker_ports:
            target_backend, target_frontend = worker_ports
            target_port = target_backend if detected_type == 'backend' else target_frontend
            if port != target_port:
                new_command = command
                if port_match:
                    new_command = re.sub(r'--port[=\s]+\d+', f'--port {target_port}', new_command)
                    new_command = re.sub(r'-p\s+\d+', f'-p {target_port}', new_command)
                    new_command = re.sub(r':(\d{4,5})\b', f':{target_port}', new_command)
                else:
                    if 'uvicorn' in command.lower() or 'fastapi' in command.lower():
                        new_command = f"{command} --port {target_port}"
                    else:
                        new_command = f"{command} -p {target_port}"
                print(f"[HOOK] ⚡ WORKER: forcing {detected_type} to port {target_port}")
                return {"modify_input": {"command": new_command}}
            port = target_port
        else:
            standard_backend = 8000
            standard_frontend = 3000
            _pd = _get_project_dir()
            if _pd:
                env_file = _pd / "frontend" / ".env.local"
                if env_file.exists():
                    try:
                        content = env_file.read_text()
                        match = re.search(r'NEXT_PUBLIC_API_URL.*?:(\d+)', content)
                        if match:
                            standard_backend = int(match.group(1))
                    except Exception:
                        pass
            if not port:
                port = standard_backend if detected_type == 'backend' else standard_frontend
            # DECISION 0: Standardize ports - correct non-standard ports to configured ones
            if detected_type == 'frontend' and port != standard_frontend:
                # Check if standard port is available
                if not registry._check_port_bound(standard_frontend):
                    print(f"[HOOK] ⚡ STANDARDIZING frontend port: {port} → {standard_frontend}")
                    new_command = re.sub(r'-p\s+\d+', f'-p {standard_frontend}', command)
                    new_command = re.sub(r'--port[=\s]+\d+', f'--port {standard_frontend}', new_command)
                    if new_command != command:
                        return {"modify_input": {"command": new_command}}
                    port = standard_frontend
        
        # DECISION 2: Check if port is taken by a different process type
        existing_on_port = registry.get_process_on_port(port)
        if existing_on_port and existing_on_port.is_alive():
            if existing_on_port.process_type != detected_type:
                # Different type - auto-kill it
                print(f"[HOOK] ⚡ Port {port} used by {existing_on_port.process_type} (PID {existing_on_port.pid})")
                print(f"[HOOK]   AUTO-KILLING to make room for {detected_type}")
                registry.terminate_process(existing_on_port.pid, force=True)
            else:
                # Same type but we already checked above, shouldn't reach here
                pass
        
        # DECISION 3: Check if port is bound by untracked process
        if registry._check_port_bound(port):
            try:
                new_port = registry.find_available_port(port)
                print(f"[HOOK] ⚡ Port {port} is bound by untracked process")
                print(f"[HOOK]   AUTO-MODIFYING command to use port {new_port}")
                
                # Modify the command to use the new port
                if port_match:
                    # Replace the port in the command
                    new_command = re.sub(
                        r'(--port[=\s]+)\d+|(-p\s+)\d+|(:\s*)\d{4,5}\b',
                        lambda m: f"{m.group(1) or m.group(2) or m.group(3)}{new_port}",
                        command,
                        count=1
                    )
                else:
                    # Add port to command
                    new_command = f"{command} --port {new_port}"
                
                # Return modified input
                return {
                    "modify_input": {
                        "command": new_command
                    }
                }
            except RuntimeError:
                print(f"[HOOK] ✗ Port {port} bound, no alternatives in range")
                return {
                    "decision": "block",
                    "reason": f"Port {port} is in use and no alternative ports available"
                }
        
        # Port is free, allow command
        print(f"[HOOK] ✓ Starting {detected_type} server on port {port}")
        return {}
                
    except Exception as e:
        print(f"[HOOK] Server management error: {e}")
        return {}


# ---------------------------------------------------------------------------
# Write-before-read prevention hook
# ---------------------------------------------------------------------------

_read_files: set[str] = set()


async def write_before_read_hook(
    input_data: dict, tool_use_id: str | None = None, context: Any = None,
) -> dict:
    """Warn and block when Write/Edit is called on an existing file not yet Read."""
    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    if tool_name == "Read":
        path = tool_input.get("file_path", "")
        if path:
            _read_files.add(path)
        return {}

    if tool_name in ("Write", "Edit"):
        path = tool_input.get("file_path", "")
        if path and path not in _read_files:
            from pathlib import Path as _Path
            if _Path(path).exists():
                _log_error("WRITE_BEFORE_READ", f"Writing {_Path(path).name} without reading first")
                return {
                    "decision": "block",
                    "message": f"Please Read {_Path(path).name} before modifying it to avoid data loss.",
                }
    return {}


# ---------------------------------------------------------------------------
# Mail injection hook (M1-2) — delivers unread mail to swarm workers
# ---------------------------------------------------------------------------

# Per-task mail store context (set by the engine for each worker)
_mail_store_ctx: contextvars.ContextVar[Optional[Any]] = contextvars.ContextVar(
    "swarmweaver_mail_store", default=None
)
_agent_name_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "swarmweaver_agent_name", default=None
)
# Module-level fallbacks
_mail_store: Optional[Any] = None
_agent_name: Optional[str] = None

def set_mail_store(store, agent_name: str = "") -> None:
    """Set the MailStore and agent name for the current async task.

    Called by the engine/orchestrator before starting a worker so that
    the mail_injection_hook can deliver messages.
    """
    global _mail_store, _agent_name
    _mail_store = store
    _agent_name = agent_name
    _mail_store_ctx.set(store)
    _agent_name_ctx.set(agent_name)


def _get_mail_store():
    return _mail_store_ctx.get(_mail_store)

def _get_agent_name():
    return _agent_name_ctx.get(_agent_name)


# Throttle: inject at most once every N tool calls
_mail_inject_counter: contextvars.ContextVar[int] = contextvars.ContextVar(
    "swarmweaver_mail_inject_counter", default=0
)
MAIL_INJECT_EVERY_N = 5  # check for mail every 5 tool calls


async def mail_injection_hook(
    input_data: dict[str, Any],
    tool_use_id: Optional[str],
    context: Any,
) -> dict[str, Any]:
    """PostToolUse hook that injects unread mail into the agent's context.

    Checks for unread messages for the current agent every N tool calls.
    When mail is found, returns it as a hook message that the agent sees.
    """
    store = _get_mail_store()
    name = _get_agent_name()
    if not store or not name:
        return {}

    # Throttle: only check every N tool calls to avoid DB overhead
    counter = _mail_inject_counter.get(0)
    counter += 1
    _mail_inject_counter.set(counter)
    if counter % MAIL_INJECT_EVERY_N != 0:
        return {}

    try:
        formatted = store.format_for_injection(name, max_messages=5)
        if not formatted:
            return {}
        return {
            "message": formatted,
        }
    except Exception:
        return {}


# Export all hooks for easy import
__all__ = [
    # Security hook (re-exported)
    "bash_security_hook",
    "protect_swarmweaver_backend_hook",
    # Autonomous management hooks
    "server_management_hook",
    "environment_management_hook",
    "file_management_hook",
    "port_config_hook",
    "test_script_port_hook",
    "knowledge_injection_hook",
    "log_consolidation_hook",
    "progress_file_management_hook",
    # Write safety
    "write_before_read_hook",
    # Other hooks
    "audit_log_hook",
    "stop_hook",
    "pre_compact_hook",
    "subagent_stop_hook",
    # Mail injection
    "mail_injection_hook",
    # Configuration functions
    "set_audit_log_path",
    "set_transcript_archive_path",
    "set_stop_callback",
    "set_project_dir",
    "set_cleanup_on_stop",
    "set_notification_callback",
    "set_mail_store",
]
