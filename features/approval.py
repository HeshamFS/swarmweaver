"""
Task Approval Gates
====================

Pause the agent at configurable checkpoints for human review.
Supports 4 decisions: Approve, Reject, Reflect, Skip.

Uses file-based signaling:
- approval_pending.json: Written by agent when gate is triggered
- approval_resolved.json: Written by frontend/API when user decides

The agent polls for approval_resolved.json until timeout.
"""

import json
import asyncio
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.paths import get_paths


@dataclass
class ApprovalRequest:
    """A request for human approval."""
    request_id: str
    gate_type: str           # "phase_complete" | "task_complete" | "pre_commit"
    summary: str
    tasks_completed: list[str]
    tasks_remaining: list[str]
    git_diff_summary: str
    timestamp: str


def request_approval(
    project_dir: Path,
    gate_type: str,
    summary: str,
    tasks_completed: Optional[list[str]] = None,
    tasks_remaining: Optional[list[str]] = None,
    git_diff_summary: str = "",
) -> str:
    """Create an approval request and write it to disk.

    Returns the request_id.
    """
    project_dir = Path(project_dir)
    request_id = str(uuid.uuid4())[:8]

    # Get git diff summary if not provided
    if not git_diff_summary:
        git_diff_summary = _get_git_diff_summary(project_dir)

    req = ApprovalRequest(
        request_id=request_id,
        gate_type=gate_type,
        summary=summary,
        tasks_completed=tasks_completed or [],
        tasks_remaining=tasks_remaining or [],
        git_diff_summary=git_diff_summary,
        timestamp=datetime.now().isoformat(),
    )

    paths = get_paths(project_dir)
    pending_file = paths.approval_pending
    pending_file.parent.mkdir(parents=True, exist_ok=True)
    pending_file.write_text(
        json.dumps(asdict(req), indent=2),
        encoding="utf-8",
    )

    # Remove any previous resolved file
    resolved_file = paths.approval_resolved
    if resolved_file.exists():
        resolved_file.unlink()

    return request_id


def get_pending_approval(project_dir: Path) -> Optional[ApprovalRequest]:
    """Get the pending approval request, if any."""
    pending_file = get_paths(project_dir).resolve_read("approval_pending.json")
    if not pending_file.exists():
        return None
    try:
        data = json.loads(pending_file.read_text(encoding="utf-8"))
        return ApprovalRequest(**data)
    except (json.JSONDecodeError, OSError, TypeError):
        return None


def resolve_approval(
    project_dir: Path,
    decision: str,
    feedback: str = "",
) -> None:
    """Resolve a pending approval request.

    Args:
        project_dir: Project directory path
        decision: One of "approved", "rejected", "reflect", "skipped"
        feedback: Optional feedback text from the user
    """
    project_dir = Path(project_dir)
    paths = get_paths(project_dir)
    resolved_file = paths.approval_resolved
    resolved_file.parent.mkdir(parents=True, exist_ok=True)
    resolved_file.write_text(
        json.dumps({
            "decision": decision,
            "feedback": feedback,
            "timestamp": datetime.now().isoformat(),
        }, indent=2),
        encoding="utf-8",
    )

    # Clean up pending file
    pending_file = paths.approval_pending
    if pending_file.exists():
        pending_file.unlink()


async def wait_for_approval(
    project_dir: Path,
    timeout: int = 3600,
    poll_interval: float = 2.0,
) -> tuple[str, str]:
    """Wait for the user to resolve an approval request.

    Polls for approval_resolved.json every poll_interval seconds.

    Returns:
        (decision, feedback) tuple
    """
    project_dir = Path(project_dir)
    resolved_file = get_paths(project_dir).resolve_read("approval_resolved.json")
    elapsed = 0.0

    while elapsed < timeout:
        if resolved_file.exists():
            try:
                data = json.loads(resolved_file.read_text(encoding="utf-8"))
                decision = data.get("decision", "approved")
                feedback = data.get("feedback", "")
                # Clean up
                resolved_file.unlink()
                return decision, feedback
            except (json.JSONDecodeError, OSError):
                pass

        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

    # Timeout — auto-approve
    return "approved", "Auto-approved after timeout"


def _get_git_diff_summary(project_dir: Path) -> str:
    """Get a brief git diff summary."""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "diff", "--stat", "HEAD"],
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return "No changes detected"
