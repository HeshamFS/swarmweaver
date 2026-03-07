"""Run management and agent control endpoints."""

from fastapi import APIRouter

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
