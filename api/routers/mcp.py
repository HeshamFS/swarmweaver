"""MCP Server management API endpoints."""

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from services.mcp_manager import MCPConfigStore, MCPServerConfig

router = APIRouter(tags=["mcp"])


class MCPServerBody(BaseModel):
    name: str
    command: str
    args: list[str] = []
    env: dict[str, str] = {}
    enabled: bool = True
    transport: str = "stdio"
    timeout: int = 30
    description: str = ""


class MCPServerUpdateBody(BaseModel):
    command: Optional[str] = None
    args: Optional[list[str]] = None
    env: Optional[dict[str, str]] = None
    enabled: Optional[bool] = None
    transport: Optional[str] = None
    timeout: Optional[int] = None
    description: Optional[str] = None


class MCPImportBody(BaseModel):
    configs: list[dict]


class MCPRawConfigBody(BaseModel):
    content: str


# ── List ──────────────────────────────────────────────────────────

@router.get("/api/mcp/servers")
async def list_mcp_servers(
    path: str = Query("", description="Project directory path (empty for global only)"),
):
    """List all configured MCP servers (built-in + global + project)."""
    project_dir = Path(path) if path else None
    store = MCPConfigStore(project_dir)
    servers = store.list_servers()
    return {
        "servers": [s.to_dict() for s in servers],
        "total": len(servers),
        "enabled": sum(1 for s in servers if s.enabled),
    }


# ── Get single server ────────────────────────────────────────────

@router.get("/api/mcp/servers/{name}")
async def get_mcp_server(
    name: str,
    path: str = Query("", description="Project directory path"),
):
    """Get a single MCP server config by name."""
    project_dir = Path(path) if path else None
    store = MCPConfigStore(project_dir)
    server = store.get_server(name)
    if not server:
        return {"error": f"Server '{name}' not found", "status": "error"}
    return {"server": server.to_dict(), "status": "ok"}


# ── Add / Update ──────────────────────────────────────────────────

@router.post("/api/mcp/servers")
async def add_mcp_server(
    body: MCPServerBody,
    path: str = Query("", description="Project directory path"),
    scope: str = Query("project", description="Config scope: 'project' or 'global'"),
):
    """Add a new MCP server configuration."""
    project_dir = Path(path) if path else None
    store = MCPConfigStore(project_dir)

    config = MCPServerConfig(
        name=body.name,
        command=body.command,
        args=body.args,
        env=body.env,
        enabled=body.enabled,
        transport=body.transport,
        timeout=body.timeout,
        description=body.description,
    )

    # Validate first
    validation = store.validate_server(config)
    if not validation["valid"]:
        return {"status": "error", "errors": validation["errors"]}

    stored = store.add_server(config, scope=scope if project_dir else "global")
    return {
        "status": "ok",
        "server": stored.to_dict(),
        "warnings": validation.get("warnings", []),
    }


@router.put("/api/mcp/servers/{name}")
async def update_mcp_server(
    name: str,
    body: MCPServerUpdateBody,
    path: str = Query("", description="Project directory path"),
    scope: str = Query("project", description="Config scope"),
):
    """Update an existing MCP server configuration."""
    project_dir = Path(path) if path else None
    store = MCPConfigStore(project_dir)

    existing = store.get_server(name)
    if not existing:
        return {"status": "error", "error": f"Server '{name}' not found"}

    # Apply updates
    updates = body.model_dump(exclude_none=True)
    for key, val in updates.items():
        if hasattr(existing, key):
            setattr(existing, key, val)

    validation = store.validate_server(existing)
    if not validation["valid"]:
        return {"status": "error", "errors": validation["errors"]}

    stored = store.add_server(existing, scope=scope if project_dir else "global")
    return {
        "status": "ok",
        "server": stored.to_dict(),
        "warnings": validation.get("warnings", []),
    }


# ── Delete ────────────────────────────────────────────────────────

@router.delete("/api/mcp/servers/{name}")
async def delete_mcp_server(
    name: str,
    path: str = Query("", description="Project directory path"),
    scope: str = Query("project", description="Config scope"),
):
    """Remove an MCP server configuration."""
    project_dir = Path(path) if path else None
    store = MCPConfigStore(project_dir)

    # Prevent deleting built-in servers (they can only be disabled)
    server = store.get_server(name)
    if server and server.builtin:
        return {"status": "error", "error": "Cannot delete built-in servers. Disable them instead."}

    removed = store.remove_server(name, scope=scope if project_dir else "global")
    if not removed:
        return {"status": "error", "error": f"Server '{name}' not found in {scope} config"}
    return {"status": "ok", "removed": name}


# ── Enable / Disable ─────────────────────────────────────────────

@router.post("/api/mcp/servers/{name}/enable")
async def enable_mcp_server(
    name: str,
    path: str = Query("", description="Project directory path"),
):
    """Enable an MCP server."""
    project_dir = Path(path) if path else None
    store = MCPConfigStore(project_dir)
    result = store.enable_server(name)
    if not result:
        return {"status": "error", "error": f"Server '{name}' not found"}
    return {"status": "ok", "server": result.to_dict()}


@router.post("/api/mcp/servers/{name}/disable")
async def disable_mcp_server(
    name: str,
    path: str = Query("", description="Project directory path"),
):
    """Disable an MCP server."""
    project_dir = Path(path) if path else None
    store = MCPConfigStore(project_dir)
    result = store.disable_server(name)
    if not result:
        return {"status": "error", "error": f"Server '{name}' not found"}
    return {"status": "ok", "server": result.to_dict()}


# ── Test ──────────────────────────────────────────────────────────

@router.post("/api/mcp/servers/{name}/test")
async def test_mcp_server(
    name: str,
    path: str = Query("", description="Project directory path"),
):
    """Test if an MCP server can start successfully."""
    project_dir = Path(path) if path else None
    store = MCPConfigStore(project_dir)
    result = store.test_server(name)
    return result


# ── Validate (pre-save) ──────────────────────────────────────────

@router.post("/api/mcp/servers/validate")
async def validate_mcp_server(body: MCPServerBody):
    """Validate a server config without saving it."""
    config = MCPServerConfig(
        name=body.name,
        command=body.command,
        args=body.args,
        env=body.env,
        timeout=body.timeout,
    )
    store = MCPConfigStore()
    return store.validate_server(config)


# ── Import / Export ───────────────────────────────────────────────

@router.get("/api/mcp/export")
async def export_mcp_config(
    path: str = Query("", description="Project directory path"),
    scope: str = Query("project", description="Scope to export"),
):
    """Export MCP server configs as JSON."""
    project_dir = Path(path) if path else None
    store = MCPConfigStore(project_dir)
    return {"configs": store.export_config(scope=scope if project_dir else "global")}


@router.post("/api/mcp/import")
async def import_mcp_config(
    body: MCPImportBody,
    path: str = Query("", description="Project directory path"),
    scope: str = Query("project", description="Scope to import into"),
):
    """Import MCP server configs from JSON."""
    project_dir = Path(path) if path else None
    store = MCPConfigStore(project_dir)
    count = store.import_config(body.configs, scope=scope if project_dir else "global")
    return {"status": "ok", "imported": count}


# ── Raw Config File Editor ───────────────────────────────────────

@router.get("/api/mcp/config")
async def get_raw_mcp_config(
    path: str = Query("", description="Project directory path"),
    scope: str = Query("project", description="Config scope: 'project' or 'global'"),
):
    """Get the raw JSON content of an MCP config file for direct editing."""
    project_dir = Path(path) if path else None
    store = MCPConfigStore(project_dir)
    target = store._target_file(scope if project_dir else "global")
    file_path = str(target.resolve())
    if target.exists():
        try:
            content = target.read_text(encoding="utf-8")
            # Validate it's parseable JSON
            json.loads(content)
        except (json.JSONDecodeError, OSError):
            content = "[]"
    else:
        content = "[]"
    return {
        "path": file_path,
        "scope": scope if project_dir else "global",
        "content": content,
        "exists": target.exists(),
    }


@router.put("/api/mcp/config")
async def save_raw_mcp_config(
    body: MCPRawConfigBody,
    path: str = Query("", description="Project directory path"),
    scope: str = Query("project", description="Config scope: 'project' or 'global'"),
):
    """Save raw JSON content directly to an MCP config file.

    Accepts two formats:
    1. SwarmWeaver array format: [{"name": "x", "command": "y", ...}, ...]
    2. Claude Desktop format: {"mcpServers": {"name": {"command": "y", ...}}}
       (auto-converted to array format on save)
    """
    # Validate JSON before saving
    try:
        parsed = json.loads(body.content)
    except json.JSONDecodeError as e:
        return {"status": "error", "error": f"Invalid JSON: {e}"}

    warnings = []

    # Auto-convert Claude Desktop format → SwarmWeaver array format
    if isinstance(parsed, dict):
        servers_dict = parsed.get("mcpServers") or parsed.get("mcp_servers") or parsed
        if isinstance(servers_dict, dict) and all(isinstance(v, dict) for v in servers_dict.values()):
            converted = []
            for name, cfg in servers_dict.items():
                entry = {"name": name, **cfg}
                converted.append(entry)
            parsed = converted
            warnings.append("Converted from object format to SwarmWeaver array format")
        else:
            return {"status": "error", "error": "Config must be a JSON array or an object with server entries (e.g. {\"mcpServers\": {\"name\": {...}}})"}

    if not isinstance(parsed, list):
        return {"status": "error", "error": "Config must be a JSON array of server objects or a Claude Desktop-style object"}

    # Validate each entry has at least name + command
    for i, entry in enumerate(parsed):
        if not isinstance(entry, dict):
            return {"status": "error", "error": f"Entry {i} is not an object"}
        if not entry.get("name"):
            return {"status": "error", "error": f"Entry {i} is missing 'name'"}
        if not entry.get("command"):
            return {"status": "error", "error": f"Entry {i} is missing 'command'"}

    project_dir = Path(path) if path else None
    store = MCPConfigStore(project_dir)
    target = store._target_file(scope if project_dir else "global")
    target.parent.mkdir(parents=True, exist_ok=True)

    # Pretty-print for readability
    formatted = json.dumps(parsed, indent=2) + "\n"
    target.write_text(formatted, encoding="utf-8")

    return {
        "status": "ok",
        "path": str(target.resolve()),
        "entries": len(parsed),
        "warnings": warnings,
    }
