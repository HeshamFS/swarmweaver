"""LSP REST API endpoints for code intelligence and diagnostics."""

from fastapi import APIRouter, Query, Body
from pathlib import Path
from typing import Optional

router = APIRouter()


@router.get("/api/lsp/status")
async def lsp_status(
    path: str = Query(..., description="Project directory"),
):
    """Get status of all LSP servers. Auto-initializes + detects + installs if needed."""
    from api.state import get_lsp_manager, set_lsp_manager
    manager = get_lsp_manager(path)
    if not manager:
        try:
            from services.lsp_manager import LSPManager, LSPConfig
            lsp_config = LSPConfig.load(Path(path))
            if lsp_config.enabled:
                manager = LSPManager(path, lsp_config)
                set_lsp_manager(path, manager)
                manager.start_health_loop()
                try:
                    started = await manager.auto_detect_and_start()
                    if started:
                        print(f"[LSP] Auto-started: {', '.join(started)}", flush=True)
                except Exception as e:
                    print(f"[LSP] Auto-detect failed: {e}", flush=True)
        except Exception as e:
            print(f"[LSP] Initialization failed: {e}", flush=True)
    if not manager:
        return {"servers": [], "message": "LSP not available"}

    instances = manager.get_all_instances()
    return {
        "servers": [
            {
                "language_id": inst.spec.language_id,
                "server_name": inst.spec.server_name,
                "status": inst.status.value,
                "root_uri": inst.root_uri,
                "pid": inst.pid,
                "started_at": inst.started_at,
                "restart_count": inst.restart_count,
                "open_files": len(inst.open_files),
                "diagnostic_count": sum(len(d) for d in inst.diagnostics.values()),
                "worker_id": inst.worker_id,
            }
            for inst in instances
        ],
    }


@router.get("/api/lsp/diagnostics")
async def lsp_diagnostics(
    path: str = Query(..., description="Project directory"),
    severity: Optional[int] = Query(None, description="Filter by severity (1=Error, 2=Warning, 3=Info, 4=Hint)"),
    file_pattern: Optional[str] = Query(None, description="Filter by file pattern (glob)"),
    worker_id: Optional[int] = Query(None, description="Filter by worker ID"),
    limit: int = Query(100, description="Max diagnostics to return"),
):
    """Get aggregated diagnostics across all LSP servers."""
    from api.state import get_lsp_manager
    manager = get_lsp_manager(path)
    if not manager:
        return {"diagnostics": [], "total": 0}

    wid = str(worker_id) if worker_id is not None else None
    diags = manager.get_diagnostics(
        file_path=None,
        severity=severity,
        worker_id=wid,
    )

    # Apply file pattern filter
    if file_pattern:
        import fnmatch
        diags = [d for d in diags if fnmatch.fnmatch(d.get("uri", ""), f"*{file_pattern}*")]

    # Severity label helper
    _sev_labels = {1: "Error", 2: "Warning", 3: "Info", 4: "Hint"}

    # Sort by severity then file
    diags.sort(key=lambda d: (d.get("severity", 9), d.get("uri", ""), d.get("start_line", d.get("range_start_line", 0))))

    total = len(diags)
    diags = diags[:limit]

    all_diags = manager.get_all_diagnostics()

    return {
        "diagnostics": [
            {
                "uri": d.get("uri", ""),
                "line": d.get("start_line", d.get("range_start_line", 0)) + 1,
                "character": d.get("start_character", d.get("range_start_char", 0)),
                "end_line": d.get("end_line", d.get("range_end_line", 0)) + 1,
                "end_character": d.get("end_character", d.get("range_end_char", 0)),
                "severity": d.get("severity", 4),
                "severity_label": d.get("severity_label", _sev_labels.get(d.get("severity", 4), "Hint")),
                "message": d.get("message", ""),
                "source": d.get("source"),
                "code": d.get("code"),
            }
            for d in diags
        ],
        "total": total,
        "error_count": sum(1 for d in all_diags if d.get("severity") == 1),
        "warning_count": sum(1 for d in all_diags if d.get("severity") == 2),
    }


@router.get("/api/lsp/diagnostics/{file_path:path}")
async def lsp_file_diagnostics(
    file_path: str,
    path: str = Query(..., description="Project directory"),
):
    """Get diagnostics for a specific file."""
    from api.state import get_lsp_manager
    manager = get_lsp_manager(path)
    if not manager:
        return {"diagnostics": [], "file": file_path}

    _sev_labels = {1: "Error", 2: "Warning", 3: "Info", 4: "Hint"}
    diags = manager.get_diagnostics(file_path=file_path)
    return {
        "file": file_path,
        "diagnostics": [
            {
                "line": d.get("start_line", d.get("range_start_line", 0)) + 1,
                "character": d.get("start_character", d.get("range_start_char", 0)),
                "severity": d.get("severity", 4),
                "severity_label": d.get("severity_label", _sev_labels.get(d.get("severity", 4), "Hint")),
                "message": d.get("message", ""),
                "source": d.get("source"),
                "code": d.get("code"),
            }
            for d in diags
        ],
    }


@router.post("/api/lsp/hover")
async def lsp_hover(
    path: str = Query(..., description="Project directory"),
    file_path: str = Body(..., embed=True),
    line: int = Body(..., embed=True),
    character: int = Body(..., embed=True),
):
    """Get hover information at a position."""
    from api.state import get_lsp_manager
    manager = get_lsp_manager(path)
    if not manager:
        return {"error": "LSP not initialized"}

    instance = manager.get_instance_for_file(Path(path) / file_path)
    if not instance or not instance.client:
        return {"error": f"No LSP server for {file_path}"}

    uri = (Path(path) / file_path).as_uri()
    result = await instance.client.hover(uri, line, character)
    if not result:
        return {"hover": None}

    return {
        "hover": {
            "contents": result.contents,
            "line": result.range_start_line,
        },
    }


@router.post("/api/lsp/definition")
async def lsp_definition(
    path: str = Query(..., description="Project directory"),
    file_path: str = Body(..., embed=True),
    line: int = Body(..., embed=True),
    character: int = Body(..., embed=True),
):
    """Go to definition."""
    from api.state import get_lsp_manager
    manager = get_lsp_manager(path)
    if not manager:
        return {"error": "LSP not initialized"}

    instance = manager.get_instance_for_file(Path(path) / file_path)
    if not instance or not instance.client:
        return {"error": f"No LSP server for {file_path}"}

    uri = (Path(path) / file_path).as_uri()
    locations = await instance.client.go_to_definition(uri, line, character)
    return {
        "locations": [
            {
                "uri": loc.uri,
                "line": loc.range_start_line + 1,
                "character": loc.range_start_char,
            }
            for loc in locations
        ],
    }


@router.post("/api/lsp/references")
async def lsp_references(
    path: str = Query(..., description="Project directory"),
    file_path: str = Body(..., embed=True),
    line: int = Body(..., embed=True),
    character: int = Body(..., embed=True),
):
    """Find all references."""
    from api.state import get_lsp_manager
    manager = get_lsp_manager(path)
    if not manager:
        return {"error": "LSP not initialized"}

    instance = manager.get_instance_for_file(Path(path) / file_path)
    if not instance or not instance.client:
        return {"error": f"No LSP server for {file_path}"}

    uri = (Path(path) / file_path).as_uri()
    refs = await instance.client.find_references(uri, line, character)
    return {
        "references": [
            {
                "uri": r.uri,
                "line": r.range_start_line + 1,
                "character": r.range_start_char,
            }
            for r in refs
        ],
        "total": len(refs),
    }


@router.post("/api/lsp/symbols")
async def lsp_symbols(
    path: str = Query(..., description="Project directory"),
    file_path: Optional[str] = Body(None, embed=True),
    query: Optional[str] = Body("", embed=True),
):
    """Get document or workspace symbols."""
    from api.state import get_lsp_manager
    manager = get_lsp_manager(path)
    if not manager:
        return {"error": "LSP not initialized"}

    if file_path:
        instance = manager.get_instance_for_file(Path(path) / file_path)
        if not instance or not instance.client:
            return {"error": f"No LSP server for {file_path}"}
        uri = (Path(path) / file_path).as_uri()
        symbols = await instance.client.document_symbols(uri)
        return {
            "type": "document",
            "symbols": [
                {
                    "name": s.name,
                    "kind": s.kind,
                    "line": s.range_start_line + 1,
                    "end_line": s.range_end_line + 1,
                    "detail": s.detail,
                    "children": len(s.children),
                }
                for s in symbols
            ],
        }
    else:
        # Workspace symbols from all servers
        all_symbols = []
        for inst in manager.get_all_instances():
            if inst.client and inst.status.value == "ready":
                try:
                    ws = await inst.client.workspace_symbols(query or "")
                    all_symbols.extend(ws)
                except Exception:
                    pass
        return {"type": "workspace", "symbols": all_symbols[:200]}


@router.post("/api/lsp/call-hierarchy")
async def lsp_call_hierarchy(
    path: str = Query(..., description="Project directory"),
    file_path: str = Body(..., embed=True),
    line: int = Body(..., embed=True),
    character: int = Body(..., embed=True),
    direction: str = Body("incoming", embed=True),
):
    """Get call hierarchy (incoming or outgoing calls)."""
    from api.state import get_lsp_manager
    manager = get_lsp_manager(path)
    if not manager:
        return {"error": "LSP not initialized"}

    instance = manager.get_instance_for_file(Path(path) / file_path)
    if not instance or not instance.client:
        return {"error": f"No LSP server for {file_path}"}

    uri = (Path(path) / file_path).as_uri()
    items = await instance.client.prepare_call_hierarchy(uri, line, character)
    if not items:
        return {"calls": [], "item": None}

    item = items[0]
    if direction == "outgoing":
        calls = await instance.client.outgoing_calls(item)
    else:
        calls = await instance.client.incoming_calls(item)

    return {
        "item": {"name": item.name, "kind": item.kind, "uri": item.uri},
        "direction": direction,
        "calls": calls,
    }


@router.get("/api/lsp/servers")
async def lsp_servers(
    path: str = Query(..., description="Project directory"),
):
    """List all configured/available LSP servers."""
    from services.lsp_manager import BUILTIN_SERVER_SPECS
    return {
        "servers": [
            {
                "language_id": s.language_id,
                "server_name": s.server_name,
                "command": s.command,
                "extensions": s.extensions,
                "install_command": s.install_command,
                "priority": s.priority,
            }
            for s in BUILTIN_SERVER_SPECS
        ],
    }


@router.post("/api/lsp/servers/{server_id}/restart")
async def lsp_restart_server(
    server_id: str,
    path: str = Query(..., description="Project directory"),
):
    """Restart a specific LSP server."""
    from api.state import get_lsp_manager
    manager = get_lsp_manager(path)
    if not manager:
        return {"error": "LSP not initialized"}

    try:
        instance = await manager.restart_server(server_id, Path(path))
        return {
            "success": True,
            "server": server_id,
            "status": instance.status.value if instance else "unknown",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/api/lsp/config")
async def lsp_config_get(
    path: str = Query(..., description="Project directory"),
):
    """Get current LSP configuration."""
    from services.lsp_manager import LSPConfig
    config = LSPConfig.load(Path(path))
    return {
        "enabled": config.enabled,
        "auto_install": config.auto_install,
        "auto_detect": config.auto_detect,
        "max_servers_per_worktree": config.max_servers_per_worktree,
        "health_check_interval_s": config.health_check_interval_s,
        "request_timeout_s": config.request_timeout_s,
        "diagnostics_debounce_ms": config.diagnostics_debounce_ms,
        "diagnostics_timeout_s": config.diagnostics_timeout_s,
        "max_diagnostics_per_file": config.max_diagnostics_per_file,
        "disabled_servers": config.disabled_servers,
        "custom_servers": config.custom_servers,
    }


@router.put("/api/lsp/config")
async def lsp_config_update(
    path: str = Query(..., description="Project directory"),
    config: dict = Body(...),
):
    """Update LSP configuration."""
    import json
    config_path = Path(path) / ".swarmweaver" / "lsp.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2))
    return {"success": True, "message": "LSP config updated"}


@router.get("/api/lsp/impact-analysis")
async def lsp_impact_analysis(
    path: str = Query(..., description="Project directory"),
    file_path: str = Query(..., description="File path (relative)"),
    line: int = Query(..., description="Line number (0-based)"),
    character: int = Query(0, description="Character offset (0-based)"),
):
    """Cross-file impact analysis for a symbol."""
    from api.state import get_lsp_manager
    manager = get_lsp_manager(path)
    if not manager:
        return {"error": "LSP not initialized"}

    from services.lsp_intelligence import CodeIntelligence
    intel = CodeIntelligence(manager)
    abs_path = str(Path(path) / file_path)
    return await intel.impact_analysis(abs_path, line, character)


@router.get("/api/lsp/stats")
async def lsp_stats(
    path: str = Query(..., description="Project directory"),
):
    """Get diagnostic statistics — found, resolved, per-worker breakdown, recent events."""
    from api.state import get_lsp_manager
    manager = get_lsp_manager(path)
    if not manager:
        return {
            "total_found": 0,
            "total_resolved": 0,
            "active_count": 0,
            "active_errors": 0,
            "active_warnings": 0,
            "by_worker": {},
            "by_severity": {},
            "recent_events": [],
        }
    return manager.get_stats()


@router.get("/api/lsp/code-health")
async def lsp_code_health(
    path: str = Query(..., description="Project directory"),
):
    """Get project-wide code health score."""
    from api.state import get_lsp_manager
    manager = get_lsp_manager(path)
    if not manager:
        return {"score": 100, "error_count": 0, "warning_count": 0, "by_language": {}}

    from services.lsp_intelligence import CodeIntelligence
    intel = CodeIntelligence(manager)
    return await intel.code_health_score()
