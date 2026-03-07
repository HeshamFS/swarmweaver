"""
Structured Event System for Agent Observability
=================================================

Parses raw agent stdout into structured events for the observability
dashboard. Tracks tool calls, file touches, errors, phase changes,
verification results, and session statistics.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class EventType(str, Enum):
    """Types of structured events emitted during agent execution."""
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TASK_UPDATE = "task_update"
    PHASE_CHANGE = "phase_change"
    ERROR = "error"
    FILE_TOUCH = "file_touch"
    VERIFICATION = "verification"
    SESSION_STAT = "session_stat"
    RAW_OUTPUT = "raw_output"
    MARATHON = "marathon"
    BLOCKED = "blocked"


@dataclass
class AgentEvent:
    """A single structured event from agent execution."""
    type: str
    timestamp: str
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "timestamp": self.timestamp,
            "data": self.data,
        }


class EventParser:
    """
    Parses raw agent output lines into structured events.

    Maintains running statistics for the observability dashboard:
    - Tool call counts by tool name
    - Error count
    - File touch heatmap (file → touch count)
    - Phase tracking
    """

    # Regex patterns for detecting structured output
    TOOL_CALL_RE = re.compile(r"^\[Tool:\s*(\w+)\]")
    TOOL_INPUT_RE = re.compile(r"^\s+Input:\s*(.+)")
    TOOL_DONE_RE = re.compile(r"^\s+\[Done\]")
    TOOL_ERROR_RE = re.compile(r"^\s+\[Error\]\s*(.*)")
    TOOL_BLOCKED_RE = re.compile(r"^\s+\[BLOCKED\]\s*(.*)")
    SESSION_RE = re.compile(r"^\s*SESSION\s+(\d+):\s*(.+)")
    VERIFY_RE = re.compile(r"^\[VERIFY\]\s*(.+)")
    MARATHON_RE = re.compile(r"^\[MARATHON\]\s*(.+)")
    HOOK_RE = re.compile(r"^\[HOOK\]\s*(.+)")
    FILE_PATH_RE = re.compile(
        r'(?:file_path|path)["\']?\s*[:=]\s*["\']?([^\s"\'}{,]+\.\w+)'
    )
    CHECKPOINT_RE = re.compile(r"^\[Captured\s+(\d+)\s+checkpoints")
    PROGRESS_RE = re.compile(r"^Progress:\s*([\d.]+)%")

    def __init__(self):
        self.tool_call_count: int = 0
        self.tool_counts: dict[str, int] = {}
        self.error_count: int = 0
        self.file_touches: dict[str, int] = {}
        self.current_phase: str = ""
        self.current_tool: Optional[str] = None
        self.session_number: int = 0
        self._start_time = datetime.now(timezone.utc).isoformat()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def parse_line(self, line: str) -> list[AgentEvent]:
        """Parse a single line of agent output into zero or more events."""
        events: list[AgentEvent] = []
        stripped = line.strip()

        if not stripped:
            return events

        # Tool call: [Tool: Bash]
        m = self.TOOL_CALL_RE.match(stripped)
        if m:
            tool_name = m.group(1)
            self.tool_call_count += 1
            self.tool_counts[tool_name] = self.tool_counts.get(tool_name, 0) + 1
            self.current_tool = tool_name
            events.append(AgentEvent(
                type=EventType.TOOL_CALL,
                timestamp=self._now(),
                data={"tool": tool_name, "count": self.tool_call_count},
            ))
            return events

        # Tool input — check for file paths
        m = self.TOOL_INPUT_RE.match(stripped)
        if m:
            input_str = m.group(1)
            fm = self.FILE_PATH_RE.search(input_str)
            if fm:
                fp = fm.group(1)
                self.file_touches[fp] = self.file_touches.get(fp, 0) + 1
                events.append(AgentEvent(
                    type=EventType.FILE_TOUCH,
                    timestamp=self._now(),
                    data={"file": fp, "count": self.file_touches[fp], "tool": self.current_tool},
                ))
            return events

        # Tool done
        if self.TOOL_DONE_RE.match(stripped):
            events.append(AgentEvent(
                type=EventType.TOOL_RESULT,
                timestamp=self._now(),
                data={"status": "done", "tool": self.current_tool},
            ))
            return events

        # Tool error
        m = self.TOOL_ERROR_RE.match(stripped)
        if m:
            self.error_count += 1
            events.append(AgentEvent(
                type=EventType.ERROR,
                timestamp=self._now(),
                data={
                    "message": m.group(1)[:300],
                    "tool": self.current_tool,
                    "error_count": self.error_count,
                },
            ))
            return events

        # Blocked
        m = self.TOOL_BLOCKED_RE.match(stripped)
        if m:
            events.append(AgentEvent(
                type=EventType.BLOCKED,
                timestamp=self._now(),
                data={"reason": m.group(1)[:300], "tool": self.current_tool},
            ))
            return events

        # Session header: SESSION 3: FEATURE / IMPLEMENT
        m = self.SESSION_RE.match(stripped)
        if m:
            self.session_number = int(m.group(1))
            self.current_phase = m.group(2).strip()
            events.append(AgentEvent(
                type=EventType.PHASE_CHANGE,
                timestamp=self._now(),
                data={
                    "session": self.session_number,
                    "phase": self.current_phase,
                },
            ))
            return events

        # Verification: [VERIFY] ...
        m = self.VERIFY_RE.match(stripped)
        if m:
            events.append(AgentEvent(
                type=EventType.VERIFICATION,
                timestamp=self._now(),
                data={"message": m.group(1)[:300]},
            ))
            return events

        # Marathon hooks: [MARATHON] ...
        m = self.MARATHON_RE.match(stripped)
        if m:
            events.append(AgentEvent(
                type=EventType.MARATHON,
                timestamp=self._now(),
                data={"message": m.group(1)[:300]},
            ))
            return events

        # Progress percentage
        m = self.PROGRESS_RE.match(stripped)
        if m:
            events.append(AgentEvent(
                type=EventType.SESSION_STAT,
                timestamp=self._now(),
                data={"progress_pct": float(m.group(1))},
            ))
            return events

        # Everything else → raw output (only emit if non-trivial)
        if len(stripped) > 2 and not stripped.startswith("=") and not stripped.startswith("-"):
            events.append(AgentEvent(
                type=EventType.RAW_OUTPUT,
                timestamp=self._now(),
                data={"text": stripped[:500]},
            ))

        return events

    def get_stats(self) -> dict:
        """Return aggregate statistics for the session."""
        return {
            "tool_call_count": self.tool_call_count,
            "tool_counts": dict(self.tool_counts),
            "error_count": self.error_count,
            "file_touches": dict(sorted(
                self.file_touches.items(),
                key=lambda x: x[1],
                reverse=True,
            )[:50]),  # Top 50 files
            "current_phase": self.current_phase,
            "session_number": self.session_number,
            "start_time": self._start_time,
        }
