"""Settings, notifications, plugins, and templates endpoints."""

import json
import os
import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query

from api.models import NotificationConfigModel, ProjectSettingsBody, GlobalSettingsBody, ApiKeysBody
from api.state import DEFAULT_PROJECT_SETTINGS, DEFAULT_GLOBAL_SETTINGS, GLOBAL_SETTINGS_PATH
from services.templates import list_templates as _list_templates, get_template as _get_template
from features.notifications import NotificationManager, NotificationConfig

router = APIRouter()


# --- Global Settings ---

@router.get("/api/settings")
async def get_global_settings():
    """Read global user settings from ~/.swarmweaver/settings.json."""
    try:
        if GLOBAL_SETTINGS_PATH.exists():
            data = json.loads(GLOBAL_SETTINGS_PATH.read_text(encoding="utf-8"))
            merged = {**DEFAULT_GLOBAL_SETTINGS, **data}
            return {"status": "ok", "settings": merged}
        return {"status": "ok", "settings": DEFAULT_GLOBAL_SETTINGS.copy()}
    except Exception as e:
        return {"status": "ok", "settings": DEFAULT_GLOBAL_SETTINGS.copy(), "warning": str(e)}


@router.post("/api/settings")
async def save_global_settings(body: GlobalSettingsBody):
    """Write global user settings to ~/.swarmweaver/settings.json."""
    try:
        GLOBAL_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if GLOBAL_SETTINGS_PATH.exists():
            existing = json.loads(GLOBAL_SETTINGS_PATH.read_text(encoding="utf-8"))
        update = {k: v for k, v in body.model_dump().items() if v is not None}
        merged = {**existing, **update}
        GLOBAL_SETTINGS_PATH.write_text(
            json.dumps(merged, indent=2), encoding="utf-8"
        )
        return {"status": "ok", "settings": {**DEFAULT_GLOBAL_SETTINGS, **merged}}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# --- Project Settings ---

@router.get("/api/default-model")
async def get_default_model():
    """Return the server's default model."""
    return {"default_model": DEFAULT_PROJECT_SETTINGS["default_model"]}


@router.get("/api/projects/settings")
async def get_project_settings(
    path: str = Query(..., description="Project directory path"),
):
    """Read project_settings.json from a project directory."""
    try:
        settings_file = Path(path) / "project_settings.json"
        if settings_file.exists():
            data = json.loads(settings_file.read_text(encoding="utf-8"))
            return {"settings": data, "found": True}
        return {"settings": DEFAULT_PROJECT_SETTINGS.copy(), "found": False}
    except Exception as e:
        return {"settings": DEFAULT_PROJECT_SETTINGS.copy(), "found": False, "error": str(e)}


@router.post("/api/projects/settings")
async def save_project_settings(
    body: ProjectSettingsBody,
    path: str = Query(..., description="Project directory path"),
):
    """Write/update project_settings.json in a project directory."""
    try:
        project_path = Path(path)
        project_path.mkdir(parents=True, exist_ok=True)
        settings_file = project_path / "project_settings.json"
        settings_file.write_text(
            json.dumps(body.model_dump(), indent=2),
            encoding="utf-8",
        )
        return {"status": "ok", "settings": body.model_dump()}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.delete("/api/projects/settings")
async def delete_project_settings(
    path: str = Query(..., description="Project directory path"),
):
    """Reset project settings to defaults by removing project_settings.json."""
    try:
        settings_file = Path(path) / "project_settings.json"
        if settings_file.exists():
            settings_file.unlink()
        return {"status": "ok", "settings": DEFAULT_PROJECT_SETTINGS.copy()}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# --- API Keys ---

def _mask_key(key: str) -> str:
    """Mask an API key for safe display, e.g. 'sk-ant-****5F2A'."""
    if not key or len(key) < 8:
        return ""
    return key[:6] + "****" + key[-4:]


def _env_file_path() -> Path:
    """Return the .env file path at the project root."""
    return Path(__file__).resolve().parent.parent.parent / ".env"


@router.get("/api/settings/api-keys")
async def get_api_keys():
    """Return which API keys are configured (masked for security)."""
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    oauth_token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "")

    return {
        "anthropic_api_key": {
            "configured": bool(anthropic_key),
            "masked": _mask_key(anthropic_key) if anthropic_key else "",
        },
        "claude_code_oauth_token": {
            "configured": bool(oauth_token),
            "masked": _mask_key(oauth_token) if oauth_token else "",
        },
    }


@router.post("/api/settings/api-keys")
async def save_api_keys(body: ApiKeysBody):
    """Validate key format and write to .env file."""
    errors = []

    # Validate formats
    if body.anthropic_api_key is not None and body.anthropic_api_key.strip():
        key = body.anthropic_api_key.strip()
        if not re.match(r"^sk-ant-[a-zA-Z0-9_-]{20,}$", key):
            errors.append("ANTHROPIC_API_KEY: expected format sk-ant-...")

    if body.claude_code_oauth_token is not None and body.claude_code_oauth_token.strip():
        token = body.claude_code_oauth_token.strip()
        if len(token) < 10:
            errors.append("CLAUDE_CODE_OAUTH_TOKEN: token too short")

    if errors:
        return {"status": "error", "errors": errors}

    # Read existing .env
    env_path = _env_file_path()
    existing_lines: list[str] = []
    if env_path.exists():
        existing_lines = env_path.read_text(encoding="utf-8").splitlines()

    # Update or append keys
    updates: dict[str, str] = {}
    if body.anthropic_api_key is not None:
        val = body.anthropic_api_key.strip()
        updates["ANTHROPIC_API_KEY"] = val
        if val:
            os.environ["ANTHROPIC_API_KEY"] = val
        else:
            os.environ.pop("ANTHROPIC_API_KEY", None)

    if body.claude_code_oauth_token is not None:
        val = body.claude_code_oauth_token.strip()
        updates["CLAUDE_CODE_OAUTH_TOKEN"] = val
        if val:
            os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = val
        else:
            os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN", None)

    # Merge into existing lines
    new_lines: list[str] = []
    seen_keys: set[str] = set()
    for line in existing_lines:
        stripped = line.strip()
        matched = False
        for key_name, value in updates.items():
            if stripped.startswith(f"{key_name}=") or stripped.startswith(f"#{key_name}="):
                if value:
                    new_lines.append(f"{key_name}={value}")
                else:
                    new_lines.append(f"#{key_name}=")
                seen_keys.add(key_name)
                matched = True
                break
        if not matched:
            new_lines.append(line)

    # Append any new keys not found in existing file
    for key_name, value in updates.items():
        if key_name not in seen_keys and value:
            new_lines.append(f"{key_name}={value}")

    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    return {"status": "ok"}




# --- Output Styles ---

AVAILABLE_OUTPUT_STYLES = [
    {
        "id": "verbose",
        "name": "Verbose",
        "description": "Full detail with all context and explanations",
    },
    {
        "id": "concise",
        "name": "Concise",
        "description": "Key information only, minimal explanations",
    },
    {
        "id": "structured",
        "name": "Structured",
        "description": "Organized with headers, bullets, and clear sections",
    },
    {
        "id": "minimal",
        "name": "Minimal",
        "description": "Bare essentials — just code and critical notes",
    },
]


@router.get("/api/output-styles")
async def list_output_styles():
    """List available output styles."""
    return {"styles": AVAILABLE_OUTPUT_STYLES}


@router.get("/api/notifications/config")
async def get_notification_config(
    path: str = Query(..., description="Project directory path"),
):
    """Get notification config for a project."""
    mgr = NotificationManager(Path(path))
    return mgr.config.to_dict()


@router.post("/api/notifications/config")
async def update_notification_config(
    config: NotificationConfigModel,
    path: str = Query(..., description="Project directory path"),
):
    """Update notification config for a project."""
    mgr = NotificationManager(Path(path))
    mgr.save_config(NotificationConfig(
        enabled=config.enabled,
        webhook_url=config.webhook_url,
        slack_webhook=config.slack_webhook,
        discord_webhook=config.discord_webhook,
        notify_on=config.notify_on,
    ))
    return {"status": "saved"}


@router.post("/api/notifications/test")
async def test_notification(
    path: str = Query(..., description="Project directory path"),
):
    """Send a test notification to all configured channels."""
    mgr = NotificationManager(Path(path))
    results = mgr.test_notification()
    return {"results": results}


# --- Plugins ---

@router.get("/api/plugins")
async def list_plugins():
    """List loaded plugins."""
    try:
        from features.plugins import PluginLoader
        loader = PluginLoader()
        defs = loader.load_config()
        return {"plugins": [d.__dict__ for d in defs]}
    except Exception as e:
        return {"plugins": [], "error": str(e)}


@router.post("/api/plugins/{name}/toggle")
async def toggle_plugin(name: str):
    """Toggle a plugin on/off."""
    try:
        from features.plugins import PluginLoader
        loader = PluginLoader()
        toggled = loader.toggle_plugin(name)
        return {"status": "ok", "enabled": toggled}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# --- Templates ---

@router.get("/api/templates")
async def api_list_templates(
    category: Optional[str] = Query(None, description="Filter by category"),
):
    """List available project templates."""
    templates = _list_templates(category)
    return {"templates": [t.to_dict() for t in templates]}


@router.get("/api/templates/{template_id}")
async def api_get_template(template_id: str):
    """Get a specific template with its spec content."""
    template = _get_template(template_id)
    if not template:
        return {"error": f"Template '{template_id}' not found"}
    result = template.to_dict()
    result["spec_content"] = template.load_spec()
    return result
