"""Module-level shared state used across API routers."""

import os
from pathlib import Path

from core.engine import Engine
from core.models import DEFAULT_MODEL


# Track active native engines for stop support
_running_engines: dict[str, Engine] = {}

# Directories to scan for projects (configurable via SWARMWEAVER_PROJECT_DIRS env var)
# Defaults to: generations/ dir + the parent dir of this script
_default_scan_dirs = [
    str(Path("generations").resolve()),
    str(Path(__file__).parent.parent.resolve()),
]
PROJECT_SCAN_DIRS = [
    d.strip()
    for d in os.environ.get("SWARMWEAVER_PROJECT_DIRS", ",".join(_default_scan_dirs)).split(",")
    if d.strip()
]

# Default project settings template
DEFAULT_PROJECT_SETTINGS = {
    "default_model": DEFAULT_MODEL,
    "default_parallel": 1,
    "use_worktree": False,
    "approval_gates": False,
    "budget_limit": None,
}

# Global settings path and defaults
GLOBAL_SETTINGS_PATH = Path.home() / ".swarmweaver" / "settings.json"

DEFAULT_GLOBAL_SETTINGS = {
    "defaultModel": DEFAULT_MODEL,
    "phaseModels": {"architect": "", "plan": "", "code": ""},
    "useWorktree": True,
    "approvalGates": False,
    "autoPr": False,
    "budgetLimit": None,
    "maxHours": None,
    "defaultParallel": 1,
    "skipQA": False,
    "theme": "ember",
    "defaultBrowsePath": None,
}
