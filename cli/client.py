"""REST/WebSocket client for connecting to a remote SwarmWeaver server."""

import asyncio
import json
from pathlib import Path
from typing import AsyncIterator, Optional
from urllib.parse import urlencode, urljoin


class SwarmWeaverClient:
    """HTTP/WebSocket client that talks to the SwarmWeaver API server.

    Used when SWARMWEAVER_URL is set or --server is passed, routing CLI
    commands through the server instead of running the engine in-process.
    """

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    # ── HTTP helpers ────────────────────────────────────────────────

    async def _get(self, path: str, params: Optional[dict] = None) -> dict:
        """Send an async GET request and return parsed JSON."""
        import aiohttp
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urlencode(params)}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def _post(self, path: str, params: Optional[dict] = None, body: Optional[dict] = None) -> dict:
        """Send an async POST request and return parsed JSON."""
        import aiohttp
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urlencode(params)}"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=body) as resp:
                resp.raise_for_status()
                return await resp.json()

    # ── Run management ──────────────────────────────────────────────

    async def stream_run(self, config: dict) -> AsyncIterator[dict]:
        """Connect to /ws/run, send config, and yield events.

        Args:
            config: Run configuration dict (mode, project_dir, task_input, model, etc.)

        Yields:
            Event dicts streamed from the server.
        """
        import aiohttp
        ws_url = self.base_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ws_url}/ws/run"

        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(ws_url) as ws:
                # Send run config
                await ws.send_str(json.dumps(config))

                # Yield events
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        try:
                            yield json.loads(msg.data)
                        except json.JSONDecodeError:
                            yield {"type": "output", "data": msg.data}
                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        break

    # ── Status ──────────────────────────────────────────────────────

    async def get_status(self) -> dict:
        """GET /api/status - check if agent is running."""
        return await self._get("/api/status")

    async def get_tasks(self, project_dir: str) -> dict:
        """GET /api/tasks - get task list."""
        return await self._get("/api/tasks", {"path": project_dir})

    # ── Steering ────────────────────────────────────────────────────

    async def steer(self, project_dir: str, message: str, steering_type: str = "instruction") -> dict:
        """POST /api/steer - send steering message."""
        return await self._post("/api/steer", {
            "path": project_dir,
            "message": message,
            "steering_type": steering_type,
        })

    # ── Worktree ────────────────────────────────────────────────────

    async def merge_worktree(self, project_dir: str, run_id: str) -> dict:
        """POST /api/worktree/merge."""
        return await self._post("/api/worktree/merge", {
            "path": project_dir,
            "run_id": run_id,
        })

    async def discard_worktree(self, project_dir: str, run_id: str) -> dict:
        """POST /api/worktree/discard."""
        return await self._post("/api/worktree/discard", {
            "path": project_dir,
            "run_id": run_id,
        })

    async def get_worktree_diff(self, project_dir: str, run_id: str) -> dict:
        """GET /api/worktree/diff."""
        return await self._get("/api/worktree/diff", {
            "path": project_dir,
            "run_id": run_id,
        })

    # ── Budget ──────────────────────────────────────────────────────

    async def get_budget(self, project_dir: str) -> dict:
        """GET /api/budget."""
        return await self._get("/api/budget", {"path": project_dir})

    # ── Checkpoints ─────────────────────────────────────────────────

    async def get_checkpoints(self, project_dir: str) -> dict:
        """GET /api/checkpoints."""
        return await self._get("/api/checkpoints", {"path": project_dir})


def get_server_url() -> Optional[str]:
    """Return the server URL from environment, or None for standalone mode."""
    import os
    return os.environ.get("SWARMWEAVER_URL")
