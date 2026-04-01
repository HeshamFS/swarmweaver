"""Run management and agent control endpoints."""

from fastapi import APIRouter, Query

from api.state import _running_engines

router = APIRouter()


@router.get("/api/status")
async def get_running_status():
    """Check if an agent is currently running."""
    active = {key: {"running": True} for key in _running_engines}
    return {"running": len(active) > 0, "processes": active}


@router.post("/api/stop")
async def stop_agent():
    """Stop the currently running agent."""
    stopped = []
    for key, engine in list(_running_engines.items()):
        try:
            await engine.stop()
            stopped.append(key)
        except Exception:
            pass
    return {"stopped": stopped}


@router.get("/api/runtimes")
async def list_available_runtimes():
    """List available agent runtimes."""
    return {"runtimes": [{"name": "sdk", "description": "Claude Agent SDK (in-process)"}]}


@router.post("/api/steer")
async def steer_agent(
    path: str,
    message: str,
    steering_type: str = "instruction",
):
    """Send a steering message to the running agent."""
    from pathlib import Path
    try:
        from features.steering import write_steering_message
        write_steering_message(Path(path), message, steering_type)
        return {"status": "ok", "steering_type": steering_type}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/api/plan")
async def get_plan(
    path: str = Query(..., description="Project directory path"),
    mode: str = Query("feature", description="Operation mode"),
    task_input: str = Query("", description="Task description"),
    model: str = Query("claude-sonnet-4-6", description="Model to use"),
):
    """Return the full execution plan: spec, tasks, phases, profile from disk."""
    import json
    from pathlib import Path as P
    from core.paths import get_paths

    project_dir = P(path)
    paths = get_paths(project_dir)

    # Determine phases for this mode
    phase_map = {
        "greenfield": ["initialize", "code"],
        "feature": ["analyze", "plan", "implement"],
        "refactor": ["analyze", "plan", "migrate"],
        "fix": ["investigate", "fix"],
        "evolve": ["audit", "improve"],
        "security": ["scan", "remediate"],
    }
    phases = phase_map.get(mode, ["analyze", "plan", "implement"])

    # Read spec (app_spec.txt)
    spec = ""
    if paths.app_spec.exists():
        try:
            spec = paths.app_spec.read_text(encoding="utf-8")
        except OSError:
            pass

    # Read task input
    saved_task_input = task_input
    if not saved_task_input and paths.task_input.exists():
        try:
            saved_task_input = paths.task_input.read_text(encoding="utf-8").strip()
        except OSError:
            pass

    # Read task list
    tasks = []
    if paths.task_list.exists():
        try:
            data = json.loads(paths.task_list.read_text(encoding="utf-8"))
            if isinstance(data, list):
                tasks = data
            elif isinstance(data, dict):
                tasks = data.get("tasks", data.get("features", []))
        except (json.JSONDecodeError, OSError):
            pass

    # Read codebase profile
    codebase_profile = None
    profile_path = paths.swarmweaver_dir / "codebase_profile.json"
    if profile_path.exists():
        try:
            codebase_profile = json.loads(profile_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    # Read iteration from session state
    iteration = 0
    session_path = paths.swarmweaver_dir / "session_state.json"
    if session_path.exists():
        try:
            session_data = json.loads(session_path.read_text(encoding="utf-8"))
            iteration = session_data.get("iteration", 0)
        except (json.JSONDecodeError, OSError):
            pass

    return {
        "status": "ok",
        "plan": {
            "mode": mode,
            "model": model,
            "task_input": saved_task_input,
            "spec": spec,
            "phases": phases,
            "tasks": tasks,
            "codebase_profile": codebase_profile,
            "iteration": iteration,
        },
    }


@router.post("/api/plan/modify")
async def modify_plan(
    path: str = Query(..., description="Project directory path"),
    spec: str = Query(None, description="Modified spec text"),
    tasks: str = Query(None, description="Modified tasks JSON"),
):
    """Write modified spec or tasks back to disk for the agent to pick up."""
    import json
    from pathlib import Path as P
    from core.paths import get_paths

    project_dir = P(path)
    paths = get_paths(project_dir)
    paths.ensure_dir()

    modified = []
    if spec is not None:
        paths.app_spec.write_text(spec, encoding="utf-8")
        modified.append("spec")
    if tasks is not None:
        try:
            parsed = json.loads(tasks)
            paths.task_list.write_text(json.dumps(parsed, indent=2), encoding="utf-8")
            modified.append("tasks")
        except json.JSONDecodeError:
            return {"status": "error", "message": "Invalid tasks JSON"}

    return {"status": "ok", "modified": modified}
