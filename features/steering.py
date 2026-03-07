"""
Interactive Steering System
============================

File-based signaling for human-in-the-loop communication with the running agent.
The agent subprocess reads steering messages via a PreToolUse hook.

Supports three steering types:
- instruction: General guidance (agent acknowledges and incorporates)
- reflect: Deep reflection (agent re-evaluates and modifies task list)
- abort: Immediate stop request

Uses {project_dir}/steering_input.json as the communication channel.
"""

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.paths import get_paths


@dataclass
class SteeringMessage:
    """A steering message from the human operator."""
    message: str
    steering_type: str = "instruction"  # instruction | reflect | abort
    timestamp: str = ""
    processed: bool = False


def _expand_file_mentions(project_dir: Path, message: str) -> str:
    """Expand @file mentions into inline file content.

    Patterns like @src/main.py are detected. If the file exists inside
    the project directory, its content (up to 500 lines) is appended
    to the message so the agent can see it.
    """
    import re
    pattern = r"@([\w\-./\\]+\.[\w]+)"
    mentions = re.findall(pattern, message)
    if not mentions:
        return message

    appended: list[str] = []
    for mention in mentions:
        filepath = Path(project_dir) / mention
        # Security: only allow files inside the project directory
        try:
            filepath.resolve().relative_to(Path(project_dir).resolve())
        except ValueError:
            continue
        if filepath.is_file():
            try:
                content = filepath.read_text(encoding="utf-8", errors="replace")
                lines = content.split("\n")[:500]
                appended.append(f"\n\n[FILE: {mention}]\n```\n" + "\n".join(lines) + "\n```")
            except OSError:
                pass

    return message + "".join(appended) if appended else message


def write_steering_message(
    project_dir: Path,
    message: str,
    steering_type: str = "instruction",
) -> None:
    """Write a steering message for the agent to pick up.

    Supports @file mentions — e.g. "Fix the bug in @src/main.py"
    will expand to include the file's content inline.

    Args:
        project_dir: Project directory path
        message: The steering message content (may contain @file mentions)
        steering_type: One of "instruction", "reflect", "abort"
    """
    steering_file = get_paths(project_dir).steering_input
    steering_file.parent.mkdir(parents=True, exist_ok=True)
    expanded = _expand_file_mentions(project_dir, message)
    msg = SteeringMessage(
        message=expanded,
        steering_type=steering_type,
        timestamp=datetime.now().isoformat(),
        processed=False,
    )
    steering_file.write_text(
        json.dumps(asdict(msg), indent=2),
        encoding="utf-8",
    )


def read_steering_message(project_dir: Path) -> Optional[SteeringMessage]:
    """Read a pending steering message.

    Returns None if no unprocessed message exists.
    """
    steering_file = get_paths(project_dir).resolve_read("steering_input.json")
    if not steering_file.exists():
        return None
    try:
        data = json.loads(steering_file.read_text(encoding="utf-8"))
        if data.get("processed", False):
            return None
        return SteeringMessage(
            message=data.get("message", ""),
            steering_type=data.get("steering_type", "instruction"),
            timestamp=data.get("timestamp", ""),
            processed=data.get("processed", False),
        )
    except (json.JSONDecodeError, OSError):
        return None


def mark_steering_processed(project_dir: Path) -> None:
    """Mark the current steering message as processed."""
    steering_file = get_paths(project_dir).resolve_read("steering_input.json")
    if not steering_file.exists():
        return
    try:
        data = json.loads(steering_file.read_text(encoding="utf-8"))
        data["processed"] = True
        steering_file.write_text(
            json.dumps(data, indent=2),
            encoding="utf-8",
        )
    except (json.JSONDecodeError, OSError):
        pass


def has_pending_steering(project_dir: Path) -> bool:
    """Check if there's an unprocessed steering message."""
    steering_file = get_paths(project_dir).resolve_read("steering_input.json")
    if not steering_file.exists():
        return False
    try:
        data = json.loads(steering_file.read_text(encoding="utf-8"))
        return not data.get("processed", True)
    except (json.JSONDecodeError, OSError):
        return False
