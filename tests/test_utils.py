"""
Test Verification Utilities for Autonomous Coding Agent
========================================================

Provides utilities for inspecting task_list.json and verifying/marking tasks.
"""

from pathlib import Path
from typing import Optional

from state.task_list import TaskList, TaskStatus


def load_task_list(project_dir: Path) -> TaskList:
    """Load TaskList from project directory."""
    tl = TaskList(project_dir)
    tl.load()
    return tl


def get_task_status(project_dir: Path) -> dict:
    """Return summary of task status from task_list.json."""
    tl = load_task_list(project_dir)
    return {
        "total": tl.total,
        "done": tl.done_count,
        "pending": tl.pending_count,
        "in_progress": tl.in_progress_count,
        "blocked": tl.blocked_count,
        "percentage": tl.percentage_done,
        "by_category": tl.count_by_category(),
    }


def print_task_summary(project_dir: Path) -> None:
    """Print a summary of task status to stdout."""
    tl = load_task_list(project_dir)
    print(tl.summary())


def verify_file_exists(project_dir: Path, relative_path: str) -> bool:
    """Check if a file exists in the project directory."""
    return (project_dir / relative_path).exists()


def verify_server_responds(url: str, timeout: float = 5.0) -> bool:
    """Check if a server responds to HTTP requests."""
    try:
        import urllib.request
        with urllib.request.urlopen(urllib.request.Request(url), timeout=timeout) as response:
            return response.status == 200
    except Exception:
        return False


def verify_command_succeeds(command: str, cwd: Optional[Path] = None) -> bool:
    """Check if a shell command succeeds (returns 0)."""
    import subprocess
    try:
        result = subprocess.run(command, shell=True, cwd=cwd, capture_output=True, timeout=60)
        return result.returncode == 0
    except Exception:
        return False


if __name__ == "__main__":
    import sys
    project_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("generations/my_project")
    print_task_summary(project_path)
