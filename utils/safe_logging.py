"""
Safe Fire-and-Forget Logging
===============================

Appends structured log entries to NDJSON files without blocking
or raising exceptions. Designed for use inside agent hot paths
where a logging failure must never crash the agent.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional


def fire_and_forget_log(
    event: dict,
    log_dir: Optional[Path] = None,
) -> None:
    """
    Write a log entry without blocking or raising.

    Appends to a daily NDJSON file at ``log_dir/YYYY-MM-DD.ndjson``.
    If ``log_dir`` is None, defaults to ``.swarmweaver/logs``.

    Args:
        event: Arbitrary dict to log. A ``timestamp`` key is added
               automatically if not already present.
        log_dir: Directory for log files. Created if missing.
    """
    try:
        if log_dir is None:
            log_dir = Path(".swarmweaver/logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{datetime.now().strftime('%Y-%m-%d')}.ndjson"
        if "timestamp" not in event:
            event["timestamp"] = datetime.now().isoformat()
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, default=str) + "\n")
    except Exception:
        pass  # Never crash the agent
