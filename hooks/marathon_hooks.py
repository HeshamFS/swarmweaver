"""
Marathon Session Hooks
======================

Hooks designed for long-running autonomous coding sessions:
- Auto-commit: Periodic git commits to save progress
- Health monitoring: Check if servers are still running
- Loop detection: Detect when agent is stuck
- Resource monitoring: Track disk/memory usage
"""

import asyncio
import json
import os
import subprocess
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

# Global state for marathon tracking
_marathon_state = {
    "project_dir": None,
    "last_commit_time": None,
    "commit_interval_minutes": 15,
    "tool_history": [],  # Last N tool calls for loop detection
    "error_count": 0,
    "consecutive_errors": 0,
    "session_start": None,
    "total_tool_calls": 0,
}

# Constants
MAX_TOOL_HISTORY = 50
LOOP_DETECTION_WINDOW = 10
MAX_CONSECUTIVE_ERRORS = 5
_MAX_LOOP_DETECTIONS = 3  # Stop after 3 consecutive loop detections

# Persistent counters for forced-stop escalation
_loop_detections: int = 0
_consecutive_error_warnings: int = 0


def configure_marathon(
    project_dir: Path,
    commit_interval_minutes: int = 15,
) -> None:
    """Configure marathon hooks with project settings."""
    _marathon_state["project_dir"] = project_dir
    _marathon_state["commit_interval_minutes"] = commit_interval_minutes
    _marathon_state["session_start"] = datetime.now()
    _marathon_state["last_commit_time"] = datetime.now()
    print(f"[MARATHON] Configured for long-running session")
    print(f"[MARATHON]   Auto-commit interval: {commit_interval_minutes} minutes")


def _run_git_command(project_dir: Path, *args) -> tuple[bool, str]:
    """Run a git command and return success status and output."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.returncode == 0, result.stdout + result.stderr
    except Exception as e:
        return False, str(e)


def _gitignore_safe_for_add_all(project_dir: Path) -> bool:
    """Return True if .gitignore exists and excludes node_modules (and similar)."""
    gitignore = project_dir / ".gitignore"
    if not gitignore.exists():
        return False
    try:
        content = gitignore.read_text(encoding="utf-8")
    except OSError:
        return False
    # Must have node_modules when node_modules dir exists
    if (project_dir / "node_modules").exists() and "node_modules" not in content:
        return False
    return True


def _auto_commit(project_dir: Path, message: str = None) -> bool:
    """Perform an automatic git commit if there are changes."""
    # Check if there are changes
    success, output = _run_git_command(project_dir, "status", "--porcelain")
    if not success or not output.strip():
        return False  # No changes or error

    # Only use git add -A when .gitignore protects node_modules (avoids committing node_modules)
    if not _gitignore_safe_for_add_all(project_dir):
        return False  # Skip auto-commit to avoid staging node_modules

    # Stage all changes
    success, _ = _run_git_command(project_dir, "add", "-A")
    if not success:
        return False
    
    # Commit with auto-generated message
    if not message:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        message = f"chore: Auto-save progress at {timestamp}"
    
    success, output = _run_git_command(project_dir, "commit", "-m", message)
    if success:
        print(f"[MARATHON] ✅ Auto-committed: {message[:50]}...")
        return True
    return False


async def auto_commit_hook(
    input_data: dict[str, Any],
    tool_use_id: Optional[str],
    context: Any
) -> dict[str, Any]:
    """
    PostToolUse hook that automatically commits progress periodically.
    
    Triggers:
    1. After every N minutes of work
    2. After successful test completions
    3. Before session end
    """
    project_dir = _marathon_state.get("project_dir")
    if not project_dir:
        return {}
    
    try:
        now = datetime.now()
        last_commit = _marathon_state.get("last_commit_time")
        interval = _marathon_state.get("commit_interval_minutes", 15)
        
        # Check if enough time has passed
        if last_commit and (now - last_commit) > timedelta(minutes=interval):
            if _auto_commit(project_dir):
                _marathon_state["last_commit_time"] = now
        
        # Also commit after task_list.json updates (task completions)
        tool_name = input_data.get("tool_name", "")
        tool_input = input_data.get("tool_input", {})

        if tool_name == "Edit":
            file_path = str(tool_input.get("file_path", ""))
            if file_path.endswith("task_list.json"):
                # Task was completed - commit immediately
                _auto_commit(project_dir, "feat: Mark task as done")
                _marathon_state["last_commit_time"] = now
                
    except Exception as e:
        print(f"[MARATHON] Auto-commit error: {e}")
    
    return {}


async def health_monitor_hook(
    input_data: dict[str, Any],
    tool_use_id: Optional[str],
    context: Any
) -> dict[str, Any]:
    """
    PostToolUse hook that monitors server health periodically.
    
    Checks:
    1. Backend server responding
    2. Frontend server responding
    3. Suggests restart if dead
    """
    project_dir = _marathon_state.get("project_dir")
    if not project_dir:
        return {}
    
    # Only check every 20 tool calls to avoid overhead
    _marathon_state["total_tool_calls"] = _marathon_state.get("total_tool_calls", 0) + 1
    if _marathon_state["total_tool_calls"] % 20 != 0:
        return {}
    
    try:
        import socket
        
        dead_servers = []
        
        # Check common ports
        ports_to_check = [
            (8003, "Backend"),
            (8000, "Backend"),
            (3000, "Frontend"),
            (3001, "Frontend"),
        ]
        
        for port, name in ports_to_check:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('localhost', port))
            sock.close()
            
            if result == 0:
                # Port is open, server likely running
                break
        else:
            # No servers found on any port
            print(f"[MARATHON] ⚠️ HEALTH CHECK: No servers detected on common ports")
            print(f"[MARATHON]    Consider restarting backend/frontend")
                
    except Exception as e:
        pass  # Silently fail health checks
    
    return {}


async def loop_detection_hook(
    input_data: dict[str, Any],
    tool_use_id: Optional[str],
    context: Any
) -> dict[str, Any]:
    """
    PostToolUse hook that detects when agent is stuck in a loop.
    
    Detects:
    1. Same tool called repeatedly with same input
    2. Alternating between same 2-3 tools
    3. Repeated errors
    """
    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})
    is_error = input_data.get("is_error", False)
    
    # Track error count
    if is_error:
        _marathon_state["consecutive_errors"] = _marathon_state.get("consecutive_errors", 0) + 1
        _marathon_state["error_count"] = _marathon_state.get("error_count", 0) + 1
        
        if _marathon_state["consecutive_errors"] >= MAX_CONSECUTIVE_ERRORS:
            global _consecutive_error_warnings
            _consecutive_error_warnings += 1
            print(f"\n[MARATHON] 🔴 STUCK DETECTION: {MAX_CONSECUTIVE_ERRORS} consecutive errors! (warning #{_consecutive_error_warnings})")
            print(f"[MARATHON]    Agent may be stuck. Consider:")
            print(f"[MARATHON]    1. Reading error messages carefully")
            print(f"[MARATHON]    2. Using web search for the error")
            print(f"[MARATHON]    3. Trying a different approach")
            print(f"[MARATHON]    4. Skipping this test and moving on\n")
            if _consecutive_error_warnings >= 2:
                project_dir = _marathon_state.get("project_dir")
                if project_dir:
                    try:
                        from features.steering import write_steering_message
                        write_steering_message(
                            project_dir,
                            "[FORCED STOP] 10+ consecutive errors detected. "
                            "You are stuck repeating failing operations. "
                            "STOP what you are doing. Mark the current task as blocked. "
                            "Move to the next task or call signal_complete.",
                            "abort",
                        )
                        print(f"[MARATHON] FORCED STOP: wrote abort steering after {_consecutive_error_warnings} error warnings", flush=True)
                    except Exception as e:
                        print(f"[MARATHON] Failed to write abort steering: {e}", flush=True)
                _consecutive_error_warnings = 0
    else:
        _marathon_state["consecutive_errors"] = 0
        _consecutive_error_warnings = 0
    
    # Track tool history for loop detection
    history = _marathon_state.get("tool_history", [])
    
    # Create a signature for this tool call
    sig = f"{tool_name}:{hash(json.dumps(tool_input, sort_keys=True, default=str)) % 10000}"
    history.append(sig)
    
    # Keep only last N entries
    if len(history) > MAX_TOOL_HISTORY:
        history = history[-MAX_TOOL_HISTORY:]
    _marathon_state["tool_history"] = history
    
    # Check for loops in recent history
    if len(history) >= LOOP_DETECTION_WINDOW:
        recent = history[-LOOP_DETECTION_WINDOW:]
        unique = set(recent)
        
        # If only 1-2 unique calls in last N, likely stuck
        if len(unique) <= 2 and len(recent) >= LOOP_DETECTION_WINDOW:
            global _loop_detections
            _loop_detections += 1
            print(f"\n[MARATHON] 🔴 LOOP DETECTION: Repeating same {len(unique)} operation(s) (detection #{_loop_detections})")
            print(f"[MARATHON]    Breaking out of loop - try a different approach\n")
            # Clear history to reset detection
            _marathon_state["tool_history"] = []

            if _loop_detections >= _MAX_LOOP_DETECTIONS:
                print(f"[MARATHON] FORCED STOP: {_loop_detections} consecutive loop detections", flush=True)
                project_dir = _marathon_state.get("project_dir")
                if project_dir:
                    try:
                        from features.steering import write_steering_message
                        write_steering_message(
                            project_dir,
                            "[FORCED STOP] Loop detected 3 times consecutively. "
                            "You are stuck repeating the same operations. "
                            "STOP what you are doing. Mark the current task as blocked. "
                            "Move to the next task or call signal_complete.",
                            "abort",
                        )
                    except Exception as e:
                        print(f"[MARATHON] Failed to write abort steering: {e}", flush=True)
                _loop_detections = 0  # Reset after abort
        else:
            _loop_detections = 0  # Reset on healthy activity

    return {}


async def resource_monitor_hook(
    input_data: dict[str, Any],
    tool_use_id: Optional[str],
    context: Any
) -> dict[str, Any]:
    """
    PostToolUse hook that monitors system resources.
    
    Checks:
    1. Disk space
    2. Memory usage (if available)
    """
    project_dir = _marathon_state.get("project_dir")
    if not project_dir:
        return {}
    
    # Only check every 50 tool calls
    total_calls = _marathon_state.get("total_tool_calls", 0)
    if total_calls % 50 != 0:
        return {}
    
    try:
        import shutil
        
        # Check disk space
        total, used, free = shutil.disk_usage(project_dir)
        free_gb = free / (1024 ** 3)
        
        if free_gb < 1.0:
            print(f"\n[MARATHON] ⚠️ LOW DISK SPACE: {free_gb:.1f} GB remaining")
            print(f"[MARATHON]    Consider cleaning up old files\n")
        elif free_gb < 5.0:
            print(f"[MARATHON] 💾 Disk space: {free_gb:.1f} GB free")
            
    except Exception:
        pass
    
    return {}


async def session_stats_hook(
    input_data: dict[str, Any],
    tool_use_id: Optional[str],
    context: Any
) -> dict[str, Any]:
    """
    PostToolUse hook that tracks and reports session statistics.
    """
    # Increment tool call counter
    _marathon_state["total_tool_calls"] = _marathon_state.get("total_tool_calls", 0) + 1
    total = _marathon_state["total_tool_calls"]
    
    # Report every 100 tool calls
    if total % 100 == 0:
        start = _marathon_state.get("session_start")
        if start:
            duration = datetime.now() - start
            hours = duration.total_seconds() / 3600
            print(f"\n[MARATHON] 📊 SESSION STATS:")
            print(f"[MARATHON]    Tool calls: {total}")
            print(f"[MARATHON]    Duration: {hours:.1f} hours")
            print(f"[MARATHON]    Errors: {_marathon_state.get('error_count', 0)}")
            print()
    
    return {}


def force_commit() -> bool:
    """Force an immediate git commit (call from stop hook)."""
    project_dir = _marathon_state.get("project_dir")
    if project_dir:
        return _auto_commit(project_dir, "chore: Session end auto-save")
    return False


# Heartbeat hook state
_heartbeat_state = {
    "last_heartbeat_time": None,
    "tool_call_count": 0,
}

HEARTBEAT_INTERVAL_S = 60  # Send heartbeat every 60 seconds


async def heartbeat_hook(
    input_data: dict[str, Any],
    tool_use_id: Optional[str],
    context: Any
) -> dict[str, Any]:
    """
    PostToolUse hook that sends heartbeat messages every 60s via mail.

    Keeps the watchdog informed that the worker is alive even when
    no stdout is being produced (e.g., during long LLM thinking phases).
    """
    _heartbeat_state["tool_call_count"] = _heartbeat_state.get("tool_call_count", 0) + 1
    tool_count = _heartbeat_state["tool_call_count"]

    now = datetime.now()
    last_hb = _heartbeat_state.get("last_heartbeat_time")

    # Only send heartbeat every HEARTBEAT_INTERVAL_S seconds
    if last_hb and (now - last_hb).total_seconds() < HEARTBEAT_INTERVAL_S:
        return {}

    project_dir = _marathon_state.get("project_dir")
    if not project_dir:
        return {}

    try:
        from state.mail import MailStore

        # Derive worker_id from environment or project context
        worker_id = os.environ.get("SWARMWEAVER_WORKER_ID", "0")

        tool_name = input_data.get("tool_name", "")

        store = MailStore(project_dir)
        if store.db_path.exists():
            store.initialize()
            store.send(
                sender=f"worker-{worker_id}",
                recipient="watchdog",
                msg_type="health_check",
                subject=f"Heartbeat from worker-{worker_id}",
                body=f"Tool #{tool_count}: {tool_name}",
                metadata={
                    "type": "heartbeat",
                    "worker_id": int(worker_id) if worker_id.isdigit() else 0,
                    "tool_call_count": tool_count,
                    "last_tool_name": tool_name,
                },
            )
            store.close()
            _heartbeat_state["last_heartbeat_time"] = now
    except Exception:
        pass  # Never crash the worker for heartbeat failures

    return {}


# Export all hooks
__all__ = [
    "configure_marathon",
    "auto_commit_hook",
    "health_monitor_hook",
    "loop_detection_hook",
    "resource_monitor_hook",
    "session_stats_hook",
    "heartbeat_hook",
    "force_commit",
]
