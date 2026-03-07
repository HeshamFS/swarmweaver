"""System health, processes, agents, checkpoints, and insights endpoints."""

import json
import os
import re as _re
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query

from core.paths import get_paths
from api.models import CheckpointRestoreRequest

router = APIRouter()


@router.get("/api/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@router.get("/api/doctor")
async def run_doctor(
    path: Optional[str] = Query(None, description="Project directory path"),
    category: Optional[str] = Query(None, description="Check category"),
):
    """Run system health checks."""
    try:
        from services.doctor import Doctor
        doc = Doctor(Path(path) if path else None)
        if category:
            results = doc.run_category(category)
        else:
            results = doc.run_all()

        passed = sum(1 for r in results if r.status == "pass")
        warned = sum(1 for r in results if r.status == "warn")
        failed = sum(1 for r in results if r.status == "fail")
        overall = "pass" if failed == 0 else ("warn" if warned > 0 and failed == 0 else "fail")

        return {
            "overall": overall,
            "passed": passed,
            "warned": warned,
            "failed": failed,
            "checks": [r.to_dict() for r in results],
        }
    except Exception as e:
        return {"overall": "fail", "checks": [], "error": str(e)}


@router.get("/api/processes")
async def get_processes(
    path: str = Query(..., description="Project directory path"),
):
    """Get all relevant processes: registered + system dev processes for this project."""
    import subprocess as _subprocess

    project_path = str(Path(path).resolve())
    seen_pids: set[int] = set()
    processes: list[dict] = []
    ports_in_use: list[int] = []

    # 1. Process registry (agent-started processes)
    registry_file = get_paths(Path(path)).resolve_read("process_registry.json")
    if registry_file.exists():
        try:
            data = json.loads(registry_file.read_text(encoding="utf-8"))
            for pid_str, entry in data.get("processes", {}).items():
                try:
                    pid = int(pid_str)
                except ValueError:
                    continue
                alive = False
                try:
                    _subprocess.run(["kill", "-0", str(pid)], capture_output=True, check=True)
                    alive = True
                except Exception:
                    pass
                seen_pids.add(pid)
                proc = {
                    "pid": pid,
                    "port": entry.get("port"),
                    "type": entry.get("process_type", "agent"),
                    "alive": alive,
                    "command_preview": entry.get("command", "")[:100],
                    "source": "agent",
                }
                processes.append(proc)
                if entry.get("port"):
                    ports_in_use.append(entry["port"])
        except (json.JSONDecodeError, OSError):
            pass

    # 2. System scan
    dev_keywords = [
        "node ", "npm ", "npx ", "next", "vite", "uvicorn", "fastapi",
        "python ", "tsx ", "ts-node", "deno ", "bun ", "cargo ",
    ]
    try:
        result = _subprocess.run(
            ["ps", "aux"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines()[1:]:
                parts = line.split(None, 10)
                if len(parts) < 11:
                    continue
                pid_str, cpu, mem, cmd = parts[1], parts[2], parts[3], parts[10]
                try:
                    pid = int(pid_str)
                except ValueError:
                    continue
                if pid in seen_pids:
                    continue
                cmd_lower = cmd.lower()
                is_project_related = project_path.lower() in cmd_lower
                is_dev_server = any(kw in cmd_lower for kw in dev_keywords) and "grep" not in cmd_lower
                if not (is_project_related or is_dev_server):
                    continue
                port = None
                port_match = _re.search(r'(?:--port|-p)\s+(\d+)|:(\d{4,5})\b', cmd)
                if port_match:
                    port = int(port_match.group(1) or port_match.group(2))
                ptype = "dev"
                if "next" in cmd_lower or "node" in cmd_lower:
                    ptype = "node"
                elif "python" in cmd_lower or "uvicorn" in cmd_lower:
                    ptype = "python"
                elif "npm" in cmd_lower or "npx" in cmd_lower:
                    ptype = "npm"
                seen_pids.add(pid)
                processes.append({
                    "pid": pid,
                    "port": port,
                    "type": ptype,
                    "alive": True,
                    "command_preview": cmd[:100],
                    "source": "system",
                })
                if port:
                    ports_in_use.append(port)
    except Exception:
        pass

    # 3. Port scan
    common_ports = [3000, 3001, 4000, 5000, 5173, 8000, 8080, 8001, 9000, 4321]
    try:
        port_result = _subprocess.run(
            ["ss", "-tlnp"],
            capture_output=True, text=True, timeout=5
        )
        if port_result.returncode == 0:
            for line in port_result.stdout.splitlines():
                for p in common_ports:
                    if f":{p} " in line and p not in ports_in_use:
                        pid_match = _re.search(r'pid=(\d+)', line)
                        pid = int(pid_match.group(1)) if pid_match else None
                        if pid and pid in seen_pids:
                            continue
                        ports_in_use.append(p)
                        if pid:
                            seen_pids.add(pid)
                            processes.append({
                                "pid": pid,
                                "port": p,
                                "type": "server",
                                "alive": True,
                                "command_preview": f"listening on :{p}",
                                "source": "port-scan",
                            })
    except Exception:
        pass

    return {"total": len(processes), "processes": processes, "ports_in_use": sorted(set(ports_in_use))}


@router.get("/api/checkpoints")
async def get_checkpoints(
    path: str = Query(..., description="Project directory path"),
):
    """Get all checkpoints for a project."""
    try:
        from state.checkpoints import CheckpointManager
        mgr = CheckpointManager(Path(path))
        mgr.load()
        checkpoints = [
            {
                "id": c.id,
                "description": c.description,
                "timestamp": c.timestamp.isoformat(),
                "session_id": c.session_id,
                "iteration": c.iteration,
            }
            for c in mgr.checkpoints
        ]
        return {"checkpoints": checkpoints, "total": len(checkpoints)}
    except Exception as e:
        return {"checkpoints": [], "total": 0, "error": str(e)}


@router.post("/api/checkpoints/restore")
async def restore_checkpoint(req: CheckpointRestoreRequest):
    """Restore a checkpoint by ID."""
    try:
        from state.checkpoints import CheckpointManager
        mgr = CheckpointManager(Path(req.path))
        mgr.load()
        checkpoint = mgr.get_by_id(req.checkpoint_id)
        if not checkpoint:
            return {"status": "error", "message": f"Checkpoint '{req.checkpoint_id}' not found"}
        return {
            "status": "ok",
            "checkpoint": {
                "id": checkpoint.id,
                "description": checkpoint.description,
                "timestamp": checkpoint.timestamp.isoformat(),
                "session_id": checkpoint.session_id,
                "iteration": checkpoint.iteration,
            },
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/api/insights")
async def get_insights(
    path: str = Query(..., description="Project directory path"),
):
    """Get session insights (tool usage, hot files, error patterns)."""
    try:
        from services.insights import SessionInsightAnalyzer
        analyzer = SessionInsightAnalyzer(Path(path))
        analysis = analyzer.analyze_audit_log()
        return {
            "top_tools": analysis.top_tools,
            "hot_files": analysis.hot_files,
            "error_frequency": analysis.error_frequency,
            "total_tool_calls": analysis.total_tool_calls,
            "insights": [i.to_dict() for i in analysis.insights],
        }
    except Exception as e:
        return {"top_tools": [], "hot_files": [], "error_frequency": 0, "total_tool_calls": 0, "insights": [], "error": str(e)}


@router.get("/api/subagents")
async def get_subagents():
    """Get subagent definitions."""
    try:
        from services.subagents import SUBAGENT_DEFINITIONS
        subagents = []
        for name, agent_def in SUBAGENT_DEFINITIONS.items():
            subagents.append({
                "name": name,
                "description": agent_def.description,
                "model": agent_def.model,
            })
        return {"subagents": subagents}
    except Exception as e:
        return {"subagents": [], "error": str(e)}


@router.get("/api/agents")
async def list_agents(
    path: str = Query(..., description="Project directory path"),
):
    """List all persistent agent identities."""
    try:
        from state.agent_identity import AgentIdentityStore
        store = AgentIdentityStore(Path(path))
        agents = store.list_agents()
        return {"agents": [a.to_dict() for a in agents]}
    except Exception as e:
        return {"agents": [], "error": str(e)}


@router.get("/api/agents/{name}")
async def get_agent(
    name: str,
    path: str = Query(..., description="Project directory path"),
):
    """Get a specific agent identity by name."""
    try:
        from state.agent_identity import AgentIdentityStore
        store = AgentIdentityStore(Path(path))
        agent = store.load(name)
        if not agent:
            return {"error": f"Agent '{name}' not found", "status": 404}
        return agent.to_dict()
    except Exception as e:
        return {"error": str(e)}


@router.get("/api/fleet/health")
async def get_fleet_health(
    path: str = Query(..., description="Project directory path"),
):
    """Get comprehensive fleet health analysis with recommended actions."""
    try:
        from services.monitor import FleetMonitor
        monitor = FleetMonitor()
        health = monitor.analyze_fleet_health(Path(path))
        issues = monitor.check_mail_for_issues(Path(path))
        actions = monitor.recommend_actions(health, issues)
        return {
            "health": health,
            "mail_issues": issues,
            "recommended_actions": actions,
        }
    except Exception as e:
        return {"health": {}, "mail_issues": [], "recommended_actions": [], "error": str(e)}


@router.get("/api/projects/expertise")
async def get_project_expertise(
    path: str = Query(..., description="Project directory path"),
    domain: Optional[str] = Query(None, description="Filter by domain"),
    q: Optional[str] = Query(None, description="Search query"),
):
    """Get project-scoped expertise entries."""
    try:
        from features.project_expertise import ProjectExpertise
        store = ProjectExpertise(Path(path))
        if q:
            entries = store.search(q)
        elif domain:
            entries = store.get_by_domain(domain)
        else:
            entries = store.get_all()
        return {
            "entries": [e.to_dict() for e in entries],
            "domains": store.get_domains(),
            "total": len(entries),
        }
    except Exception as e:
        return {"entries": [], "domains": [], "total": 0, "error": str(e)}


@router.post("/api/projects/expertise")
async def add_project_expertise(
    path: str = Query(..., description="Project directory path"),
    content: str = Query(..., description="Expertise content"),
    category: str = Query("pattern", description="Category"),
    domain: str = Query("", description="Domain"),
    tags: str = Query("", description="Comma-separated tags"),
    source_file: str = Query("", description="Source file path"),
):
    """Add a project expertise entry."""
    try:
        from features.project_expertise import ProjectExpertise
        store = ProjectExpertise(Path(path))
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
        entry_id = store.add(
            content=content,
            category=category,
            domain=domain,
            tags=tag_list,
            source_file=source_file,
        )
        return {"status": "ok", "id": entry_id}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.delete("/api/projects/expertise/{entry_id}")
async def delete_project_expertise(
    entry_id: str,
    path: str = Query(..., description="Project directory path"),
):
    """Delete a project expertise entry."""
    try:
        from features.project_expertise import ProjectExpertise
        store = ProjectExpertise(Path(path))
        deleted = store.delete(entry_id)
        return {"status": "ok" if deleted else "not_found", "deleted": deleted}
    except Exception as e:
        return {"status": "error", "message": str(e)}
