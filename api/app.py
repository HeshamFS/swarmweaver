"""Application factory for SwarmWeaver API."""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import runs, tasks, swarm, worktree, budget, github
from api.routers import projects, sessions, settings, system, wizard
from api.routers import mcp, lsp, expertise
from api.routers import session_history, snapshots, keybindings
from api.routers import skills
from api.routers import dream
from api.routers import memory
from api.websocket import run as ws_run, wizard as ws_wizard


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    app = FastAPI(title="SwarmWeaver API", version="1.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.environ.get(
            "SWARMWEAVER_CORS_ORIGINS", "http://localhost:3000"
        ).split(","),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # REST routers
    app.include_router(runs.router)
    app.include_router(tasks.router)
    app.include_router(swarm.router)
    app.include_router(worktree.router)
    app.include_router(budget.router)
    app.include_router(github.router)
    app.include_router(projects.router)
    app.include_router(sessions.router)
    app.include_router(settings.router)
    app.include_router(system.router)
    app.include_router(wizard.router)
    app.include_router(mcp.router)
    app.include_router(lsp.router)
    app.include_router(expertise.router)
    app.include_router(session_history.router)
    app.include_router(snapshots.router)
    app.include_router(keybindings.router)
    app.include_router(skills.router)
    app.include_router(dream.router)
    app.include_router(memory.router)

    # WebSocket routers
    app.include_router(ws_run.router)
    app.include_router(ws_wizard.router)

    @app.on_event("startup")
    async def _init_global_memory():
        """Ensure global memory structure exists at ~/.swarmweaver/."""
        try:
            from core.paths import _ensure_global_memory
            _ensure_global_memory()
        except Exception:
            pass

    @app.on_event("startup")
    async def _start_dream_daemon():
        from services.dream_daemon import DreamDaemon, set_daemon
        daemon = DreamDaemon(check_interval_seconds=300)
        daemon.start()
        set_daemon(daemon)

    @app.on_event("shutdown")
    async def _stop_dream_daemon():
        from services.dream_daemon import get_daemon
        daemon = get_daemon()
        if daemon:
            daemon.stop()

    return app


# Module-level app instance for backward compatibility (uvicorn server:app)
app = create_app()
