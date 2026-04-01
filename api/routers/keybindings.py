"""Keybinding configuration endpoints."""

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter

router = APIRouter()

KEYBINDINGS_PATH = Path.home() / ".swarmweaver" / "keybindings.json"

DEFAULT_BINDINGS = [
    {"id": "command-palette", "label": "Toggle Command Palette", "keys": ["ctrl+k"], "category": "navigation"},
    {"id": "new-tab", "label": "New Session Tab", "keys": ["ctrl+t"], "category": "navigation"},
    {"id": "toggle-drawer", "label": "Toggle Command Panel", "keys": ["ctrl+."], "category": "navigation"},
    {"id": "stop-agent", "label": "Stop Agent", "keys": ["ctrl+shift+c"], "category": "actions"},
    {"id": "focus-steering", "label": "Focus Steering Input", "keys": ["ctrl+shift+s"], "category": "actions"},
    {"id": "show-plan", "label": "Show Execution Plan", "keys": ["ctrl+shift+p"], "category": "panels"},
    {"id": "show-costs", "label": "Show Cost Analysis", "keys": ["ctrl+shift+$"], "category": "panels"},
    {"id": "show-tasks", "label": "Show Tasks", "keys": ["ctrl+shift+t"], "category": "panels"},
]

RESERVED_KEYS = [
    "ctrl+c", "ctrl+v", "ctrl+x", "ctrl+a", "ctrl+z", "ctrl+y",
    "ctrl+f", "ctrl+g", "ctrl+p", "ctrl+s", "ctrl+w", "ctrl+n",
    "ctrl+tab", "ctrl+shift+tab", "alt+tab", "alt+f4",
    "f5", "f11", "f12",
]


@router.get("/api/keybindings")
async def get_keybindings():
    """Return merged keybindings (defaults + user overrides)."""
    user_overrides = {}
    if KEYBINDINGS_PATH.exists():
        try:
            data = json.loads(KEYBINDINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "bindings" in data:
                for b in data["bindings"]:
                    if "id" in b and "keys" in b:
                        user_overrides[b["id"]] = b["keys"]
        except (json.JSONDecodeError, OSError):
            pass

    merged = []
    for default in DEFAULT_BINDINGS:
        entry = {**default, "isDefault": default["id"] not in user_overrides}
        if default["id"] in user_overrides:
            entry["keys"] = user_overrides[default["id"]]
        merged.append(entry)

    return {"bindings": merged, "reserved": RESERVED_KEYS}


@router.post("/api/keybindings")
async def save_keybindings(body: dict):
    """Save user keybinding overrides."""
    try:
        KEYBINDINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        KEYBINDINGS_PATH.write_text(
            json.dumps(body, indent=2), encoding="utf-8"
        )
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/api/keybindings/reset")
async def reset_keybindings():
    """Reset to default keybindings."""
    try:
        if KEYBINDINGS_PATH.exists():
            KEYBINDINGS_PATH.unlink()
        return {"status": "ok", "bindings": DEFAULT_BINDINGS}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/api/keybindings/validate")
async def validate_keybinding(body: dict):
    """Validate a proposed keybinding for conflicts."""
    keys = body.get("keys", [])
    binding_id = body.get("id", "")

    errors = []
    for key in keys:
        normalized = key.lower().strip()
        if normalized in RESERVED_KEYS:
            errors.append(f"'{key}' is a reserved browser shortcut")

    # Check conflicts with other bindings
    conflicts = []
    if KEYBINDINGS_PATH.exists():
        try:
            data = json.loads(KEYBINDINGS_PATH.read_text(encoding="utf-8"))
            for b in data.get("bindings", []):
                if b.get("id") != binding_id:
                    for k in b.get("keys", []):
                        if k.lower() in [x.lower() for x in keys]:
                            conflicts.append({"id": b["id"], "key": k})
        except (json.JSONDecodeError, OSError):
            pass

    # Also check defaults
    for d in DEFAULT_BINDINGS:
        if d["id"] != binding_id:
            for k in d["keys"]:
                if k.lower() in [x.lower() for x in keys]:
                    conflicts.append({"id": d["id"], "key": k})

    return {
        "valid": len(errors) == 0 and len(conflicts) == 0,
        "errors": errors,
        "conflicts": conflicts,
    }
