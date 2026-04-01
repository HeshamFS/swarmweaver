"""
Dream Daemon — Background Consolidation Service
=================================================

Periodically checks if any project needs memory consolidation.
Started/stopped with the FastAPI app lifecycle.
"""

import asyncio
from pathlib import Path
from typing import Optional

from services.dream_consolidator import DreamConfig, DreamGatekeeper, DreamPipeline, DreamResult
import logging

logger = logging.getLogger(__name__)

# Module-level singleton for notifications
_daemon_instance: Optional["DreamDaemon"] = None


class DreamDaemon:
    """Background asyncio task for periodic memory consolidation."""

    def __init__(self, check_interval_seconds: int = 300):
        self._interval = check_interval_seconds
        self._task: Optional[asyncio.Task] = None
        self._stopped = False
        self._gatekeepers: dict[str, DreamGatekeeper] = {}
        self._config = DreamConfig()

    def start(self) -> None:
        """Start the background check loop."""
        self._stopped = False
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Dream daemon started (check every %ds)", self._interval)

    def stop(self) -> None:
        """Stop the daemon."""
        self._stopped = True
        if self._task:
            self._task.cancel()
        logger.info("Dream daemon stopped")

    def _get_gatekeeper(self, project_dir: Path) -> DreamGatekeeper:
        key = str(project_dir.resolve())
        if key not in self._gatekeepers:
            self._gatekeepers[key] = DreamGatekeeper(self._config, project_dir)
        return self._gatekeepers[key]

    async def _run_loop(self) -> None:
        """Main loop: sleep, then check known projects."""
        while not self._stopped:
            try:
                await asyncio.sleep(self._interval)
            except asyncio.CancelledError:
                break
            try:
                await self._check_all_projects()
            except Exception as e:
                logger.warning(f"Dream daemon check error: {e}")

    async def _check_all_projects(self) -> None:
        """Check each known project for consolidation eligibility."""
        for key, gatekeeper in list(self._gatekeepers.items()):
            try:
                should_run, reason = await gatekeeper.check_gates()
                if should_run:
                    logger.info(f"Dream triggered for {key}: {reason}")
                    await self._run_consolidation(gatekeeper)
            except Exception as e:
                logger.warning(f"Dream check failed for {key}: {e}")

    async def _run_consolidation(self, gatekeeper: DreamGatekeeper) -> DreamResult:
        """Execute consolidation for a project."""
        async with gatekeeper._lock:
            pipeline = DreamPipeline(gatekeeper.project_dir, self._config)
            result = await pipeline.run()

            # Update state
            state = gatekeeper._load_state()
            state["last_run_timestamp"] = result.timestamp
            history = state.get("history", [])
            history.append(result.to_dict())
            state["history"] = history[-20:]  # Keep last 20 runs
            gatekeeper._save_state(state)

            logger.info(
                f"Dream completed: {result.consolidated} consolidated, "
                f"{result.pruned} pruned, {result.duration_seconds}s"
            )
            return result

    async def trigger_manual(self, project_dir: Path) -> DreamResult:
        """Manually trigger consolidation for a specific project."""
        gatekeeper = self._get_gatekeeper(project_dir)
        return await self._run_consolidation(gatekeeper)

    def register_project(self, project_dir: Path) -> None:
        """Register a project for periodic checking."""
        self._get_gatekeeper(project_dir)

    def get_status(self, project_dir: Path) -> dict:
        """Get gate status for a project."""
        gatekeeper = self._get_gatekeeper(project_dir)
        return gatekeeper.get_gate_status()

    def get_config(self) -> dict:
        """Get daemon configuration."""
        return {
            "enabled": self._config.enabled,
            "time_gate_hours": self._config.time_gate_hours,
            "scan_throttle_minutes": self._config.scan_throttle_minutes,
            "session_gate_count": self._config.session_gate_count,
            "max_turns": self._config.max_turns,
            "check_interval_seconds": self._interval,
        }


def get_daemon() -> Optional[DreamDaemon]:
    """Get the singleton daemon instance."""
    return _daemon_instance


def set_daemon(daemon: DreamDaemon) -> None:
    """Set the singleton daemon instance."""
    global _daemon_instance
    _daemon_instance = daemon
