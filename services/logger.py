"""
Multi-Format Logging System
===============================

Logs to multiple parallel formats simultaneously:
  - session.log  — Human-readable with timestamps
  - events.ndjson — Machine-parseable NDJSON
  - errors.log   — Errors only with context

Fire-and-forget writes — never crashes the host process.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional


class MultiLogger:
    """
    Parallel multi-format logger.

    Usage:
        logger = MultiLogger(project_dir, session_id="sess-001")
        logger.log("tool_call", tool="Read", file="main.py")
        logger.error("ImportError", details="No module named 'foo'")
    """

    def __init__(self, project_dir: Path, session_id: str = "default"):
        self.log_dir = project_dir / ".swarmweaver" / "logs" / session_id
        self._session_log: Optional[Path] = None
        self._events_log: Optional[Path] = None
        self._errors_log: Optional[Path] = None
        self._initialized = False

    def _ensure_dirs(self) -> None:
        if self._initialized:
            return
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            self._session_log = self.log_dir / "session.log"
            self._events_log = self.log_dir / "events.ndjson"
            self._errors_log = self.log_dir / "errors.log"
            self._initialized = True
        except OSError:
            pass

    def log(
        self,
        event_type: str,
        level: str = "info",
        **kwargs: str,
    ) -> None:
        """Log an event to all applicable formats."""
        self._ensure_dirs()
        timestamp = datetime.now().isoformat()

        # Human-readable session.log
        self._write_session(timestamp, level, event_type, kwargs)

        # Machine-parseable events.ndjson
        self._write_ndjson(timestamp, level, event_type, kwargs)

        # Errors-only
        if level == "error":
            self._write_error(timestamp, event_type, kwargs)

    def error(self, event_type: str, **kwargs: str) -> None:
        """Convenience: log an error-level event."""
        self.log(event_type, level="error", **kwargs)

    def tool_start(self, tool_name: str, **kwargs: str) -> None:
        """Log a tool invocation start."""
        self.log("tool_start", tool=tool_name, **kwargs)

    def tool_end(self, tool_name: str, duration_ms: int = 0, is_error: bool = False, **kwargs: str) -> None:
        """Log a tool invocation end."""
        level = "error" if is_error else "info"
        self.log("tool_end", level=level, tool=tool_name, duration_ms=str(duration_ms), **kwargs)

    def _write_session(self, timestamp: str, level: str, event_type: str, data: dict) -> None:
        """Write to human-readable session.log."""
        if not self._session_log:
            return
        try:
            # Format: [2024-01-15T10:30:00] INFO tool_call tool=Read file=main.py
            kv_pairs = " ".join(f"{k}={v}" for k, v in data.items() if v)
            line = f"[{timestamp}] {level.upper():5s} {event_type} {kv_pairs}\n"
            with open(self._session_log, "a", encoding="utf-8") as f:
                f.write(line)
        except OSError:
            pass

    def _write_ndjson(self, timestamp: str, level: str, event_type: str, data: dict) -> None:
        """Write to machine-parseable events.ndjson."""
        if not self._events_log:
            return
        try:
            entry = {
                "timestamp": timestamp,
                "level": level,
                "type": event_type,
                **data,
            }
            with open(self._events_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            pass

    def _write_error(self, timestamp: str, event_type: str, data: dict) -> None:
        """Write to errors-only log."""
        if not self._errors_log:
            return
        try:
            details = data.get("details", data.get("error", data.get("message", "")))
            line = f"[{timestamp}] {event_type}: {details}\n"
            if data.get("stack_trace"):
                line += f"  Stack: {data['stack_trace']}\n"
            with open(self._errors_log, "a", encoding="utf-8") as f:
                f.write(line)
        except OSError:
            pass

    def get_log_paths(self) -> dict[str, str]:
        """Get paths to all log files."""
        self._ensure_dirs()
        return {
            "session": str(self._session_log) if self._session_log else "",
            "events": str(self._events_log) if self._events_log else "",
            "errors": str(self._errors_log) if self._errors_log else "",
        }
