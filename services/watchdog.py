"""
Swarm Watchdog Health Monitor
================================

Provides continuous background monitoring of swarm worker processes, detecting:

  - Dead processes (PID no longer exists)
  - Stalled workers (no output for configurable timeout)
  - Budget exhaustion (optional token/cost limits)

Escalation levels:
  Level 0: Log warning (internal only)
  Level 1: Notify user via WebSocket
  Level 2: Attempt to restart the worker
  Level 3: Terminate and report failure

Runs as an asyncio background task inside FastAPI's lifespan,
not as a separate daemon.
"""

import asyncio
import json
import logging
import os
import subprocess as _sp
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import IntEnum
from pathlib import Path
from typing import Optional, Callable, Any

logger = logging.getLogger(__name__)


class EscalationLevel(IntEnum):
    """Watchdog escalation levels."""
    LOG = 0
    NOTIFY = 1
    RESTART = 2
    TERMINATE = 3


class WorkerHealthStatus(str):
    """Health status labels for workers."""
    HEALTHY = "healthy"
    WARNING = "warning"
    STALLED = "stalled"
    DEAD = "dead"
    TERMINATED = "terminated"


@dataclass
class WorkerHealth:
    """Health state for a single worker."""
    worker_id: int
    pid: Optional[int] = None
    status: str = WorkerHealthStatus.HEALTHY
    last_output_time: float = 0.0  # timestamp of last output
    escalation_level: int = 0
    warnings: list[str] = field(default_factory=list)
    check_count: int = 0
    worktree_path: str = ""  # For steering-based nudging
    recorded_status: str = ""  # ZFC: last known recorded status for reconciliation

    def to_dict(self) -> dict:
        d = asdict(self)
        d["last_output_ago_seconds"] = (
            int(time.time() - self.last_output_time)
            if self.last_output_time > 0
            else -1
        )
        return d


@dataclass
class WatchdogEvent:
    """An event emitted by the watchdog."""
    event_type: str  # "warning" | "stalled" | "dead" | "terminated" | "restarted"
    worker_id: int
    message: str
    escalation_level: int
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return asdict(self)


class SwarmWatchdog:
    """
    Background health monitor for swarm workers.

    Usage:
        watchdog = SwarmWatchdog(
            stale_timeout=300,  # 5 minutes without output = stalled
            check_interval=30,  # Check every 30 seconds
        )

        # Register workers
        watchdog.register_worker(worker_id=1, pid=12345)

        # Report activity (called from output stream handler)
        watchdog.report_activity(worker_id=1)

        # Start monitoring
        task = asyncio.create_task(watchdog.run(on_event=my_callback))

        # Stop monitoring
        watchdog.stop()
    """

    def __init__(
        self,
        stale_timeout: float = 300.0,  # seconds before declaring stalled
        check_interval: float = 30.0,  # seconds between health checks
        max_escalation: int = EscalationLevel.TERMINATE,
        mail_store: Optional[Any] = None,
    ):
        self.stale_timeout = stale_timeout
        self.check_interval = check_interval
        self.max_escalation = min(max_escalation, EscalationLevel.TERMINATE)
        self.mail_store = mail_store
        self.workers: dict[int, WorkerHealth] = {}
        self.output_buffers: dict[int, list[str]] = {}  # last 20 lines per worker
        self.nudge_history: dict[int, list[dict]] = {}  # worker_id -> [{timestamp, method, message, success}]
        self._running = False
        self._events: list[WatchdogEvent] = []
        self._on_event: Optional[Callable] = None
        self._triage_results: dict[int, dict] = {}  # last triage result per worker

    def register_worker(self, worker_id: int, pid: Optional[int] = None) -> None:
        """Register a worker for health monitoring."""
        self.workers[worker_id] = WorkerHealth(
            worker_id=worker_id,
            pid=pid,
            last_output_time=time.time(),
        )

    def unregister_worker(self, worker_id: int) -> None:
        """Remove a worker from monitoring."""
        self.workers.pop(worker_id, None)
        self.output_buffers.pop(worker_id, None)

    def report_activity(self, worker_id: int) -> None:
        """
        Report that a worker produced output (is still active).
        Should be called from the worker's output stream handler.
        """
        if worker_id in self.workers:
            health = self.workers[worker_id]
            health.last_output_time = time.time()
            # Reset escalation if worker recovered
            if health.escalation_level > 0 and health.status != WorkerHealthStatus.DEAD:
                health.status = WorkerHealthStatus.HEALTHY
                health.escalation_level = 0
                health.warnings = []

    def report_output(self, worker_id: int, line: str) -> None:
        """Record output line from a worker for triage context."""
        if worker_id not in self.output_buffers:
            self.output_buffers[worker_id] = []
        self.output_buffers[worker_id].append(line)
        # Keep only last 20 lines
        if len(self.output_buffers[worker_id]) > 20:
            self.output_buffers[worker_id] = self.output_buffers[worker_id][-20:]

    def update_pid(self, worker_id: int, pid: int) -> None:
        """Update a worker's PID (e.g., after restart)."""
        if worker_id in self.workers:
            self.workers[worker_id].pid = pid

    async def run(
        self,
        on_event: Optional[Callable[[WatchdogEvent], Any]] = None,
    ) -> None:
        """
        Main monitoring loop. Runs until stop() is called.

        Args:
            on_event: Callback for watchdog events (e.g., push to WebSocket)
        """
        self._running = True
        self._on_event = on_event

        while self._running:
            await asyncio.sleep(self.check_interval)

            if not self._running:
                break

            for worker_id, health in list(self.workers.items()):
                health.check_count += 1
                event = self._check_worker(health)

                if event:
                    self._events.append(event)
                    if on_event:
                        try:
                            result = on_event(event)
                            if asyncio.iscoroutine(result):
                                await result
                        except Exception:
                            pass  # Don't crash the watchdog on callback errors

    def stop(self) -> None:
        """Stop the monitoring loop."""
        self._running = False

    def _check_worker(self, health: WorkerHealth) -> Optional[WatchdogEvent]:
        """
        Check a single worker's health using ZeroFlow Consistency (ZFC):
        Observable state (PID alive, output freshness) is the source of truth.
        Reconcile when recorded state conflicts with observable state.
        """
        # ZFC: Check observable PID state
        if health.pid is not None and not self._is_pid_alive(health.pid):
            # ZFC reconciliation: recorded says alive, observable says dead
            if health.recorded_status in ("working", "running") and health.status != WorkerHealthStatus.DEAD:
                health.warnings.append(
                    f"ZFC: Recorded status '{health.recorded_status}' but PID {health.pid} is dead. Observable state wins."
                )
            if health.status != WorkerHealthStatus.DEAD:
                health.status = WorkerHealthStatus.DEAD
                health.escalation_level = EscalationLevel.NOTIFY
                return WatchdogEvent(
                    event_type="dead",
                    worker_id=health.worker_id,
                    message=f"Worker {health.worker_id} (PID {health.pid}) is no longer running",
                    escalation_level=health.escalation_level,
                )
            return None

        # Check for stale output
        if health.last_output_time > 0:
            elapsed = time.time() - health.last_output_time

            if elapsed > self.stale_timeout:
                return self._escalate_stall(health, elapsed)
            elif elapsed > self.stale_timeout * 0.7:
                # Pre-warning at 70% of timeout
                if health.status == WorkerHealthStatus.HEALTHY:
                    health.status = WorkerHealthStatus.WARNING
                    msg = (
                        f"Worker {health.worker_id} has not produced output "
                        f"for {int(elapsed)}s (threshold: {int(self.stale_timeout)}s)"
                    )
                    health.warnings.append(msg)
                    return WatchdogEvent(
                        event_type="warning",
                        worker_id=health.worker_id,
                        message=msg,
                        escalation_level=EscalationLevel.LOG,
                    )

        return None

    def _escalate_stall(self, health: WorkerHealth, elapsed: float) -> WatchdogEvent:
        """
        Escalate a stalled worker through 4 progressive levels:
          Level 0 (LOG): Log warning only
          Level 1 (NUDGE): Inject steering message to worker
          Level 2 (AI_TRIAGE): Ask Claude to classify situation
          Level 3 (TERMINATE): Kill the process
        """
        health.status = WorkerHealthStatus.STALLED

        # Progressive escalation
        if health.escalation_level < self.max_escalation:
            health.escalation_level += 1

        level = health.escalation_level
        msg = (
            f"Worker {health.worker_id} stalled: no output for {int(elapsed)}s "
            f"(escalation level {level})"
        )
        health.warnings.append(msg)

        event_type = "stalled"

        # Level 1: Nudge via tmux or steering file
        if level == EscalationLevel.NOTIFY:
            nudge_result = self._nudge_worker(health)
            msg += f" — nudge sent via {nudge_result['method']}"

        # Level 2: AI triage (ask Claude to classify)
        elif level == EscalationLevel.RESTART:
            triage_result = self._ai_triage(health)
            verdict_str = triage_result["verdict"]
            # Store triage result for health endpoint access
            self._triage_results[health.worker_id] = triage_result
            # Push triage result via WS event
            if self._on_event:
                try:
                    result = self._on_event(WatchdogEvent(
                        event_type="triage_result",
                        worker_id=health.worker_id,
                        message=json.dumps(triage_result),
                        escalation_level=health.escalation_level,
                    ))
                    if asyncio.iscoroutine(result):
                        import asyncio as _aio
                        # Schedule but don't block
                        try:
                            loop = _aio.get_running_loop()
                            loop.create_task(result)
                        except RuntimeError:
                            pass
                except Exception:
                    pass
            if verdict_str == "terminate":
                health.escalation_level = EscalationLevel.TERMINATE
                level = EscalationLevel.TERMINATE
            elif verdict_str == "escalate":
                msg += f" — AI triage verdict: escalate ({triage_result['reasoning']})"
            elif verdict_str == "retry":
                self._nudge_worker(health, "You appear stuck. Please re-evaluate your current approach.")
                msg += f" — AI triage verdict: {verdict_str}"
            else:  # "extend"
                msg += f" — AI triage verdict: extend (continuing to monitor)"

        # Level 3: Terminate
        if level >= EscalationLevel.TERMINATE:
            event_type = "terminated"
            if health.pid:
                self._kill_pid(health.pid)
                health.status = WorkerHealthStatus.TERMINATED

        # Send escalation mail if mail store is available
        if self.mail_store:
            try:
                from state.mail import MessageType, MessagePriority
                self.mail_store.send(
                    sender="watchdog",
                    recipient="orchestrator",
                    msg_type=MessageType.ESCALATION.value,
                    subject=f"Worker {health.worker_id} stalled",
                    body=f"Worker stalled for {elapsed:.0f}s, escalation level {health.escalation_level}",
                    priority=MessagePriority.URGENT.value,
                    metadata={
                        "worker_id": health.worker_id,
                        "elapsed_seconds": elapsed,
                        "escalation_level": health.escalation_level,
                    },
                )
            except Exception:
                pass  # Don't crash the watchdog on mail errors

        return WatchdogEvent(
            event_type=event_type,
            worker_id=health.worker_id,
            message=msg,
            escalation_level=level,
        )

    def _tmux_nudge(self, health: WorkerHealth, message: str = "") -> bool:
        """Try to nudge a worker via tmux keystroke injection.

        Args:
            health: Worker health state
            message: Optional message to type into the pane

        Returns:
            True if tmux nudge succeeded
        """
        if not health.pid:
            return False

        try:
            # Find tmux pane by PID
            result = _sp.run(
                ["tmux", "list-panes", "-a", "-F", "#{pane_pid} #{pane_id}"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0:
                return False

            target_pane = None
            for line in result.stdout.strip().splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[0] == str(health.pid):
                    target_pane = parts[1]
                    break

            if not target_pane:
                # Try to find by child PID
                for line in result.stdout.strip().splitlines():
                    parts = line.split()
                    if len(parts) >= 2:
                        try:
                            pane_pid = int(parts[0])
                            children = _sp.run(
                                ["pgrep", "-P", str(pane_pid)],
                                capture_output=True, text=True, timeout=5,
                            )
                            if str(health.pid) in children.stdout:
                                target_pane = parts[1]
                                break
                        except (ValueError, _sp.TimeoutExpired):
                            continue

            if not target_pane:
                return False

            if message:
                _sp.run(
                    ["tmux", "send-keys", "-t", target_pane, message, "Enter"],
                    capture_output=True, timeout=5,
                )
            else:
                _sp.run(
                    ["tmux", "send-keys", "-t", target_pane, "", "Enter"],
                    capture_output=True, timeout=5,
                )

            logger.info(f"Tmux nudge sent to worker {health.worker_id} via pane {target_pane}")
            return True

        except (FileNotFoundError, _sp.TimeoutExpired) as e:
            logger.debug(f"Tmux nudge failed for worker {health.worker_id}: {e}")
            return False

    def _nudge_worker(self, health: WorkerHealth, message: str = "") -> dict:
        """Nudge a stalled worker. Returns method used and success status."""
        result = {"method": "none", "success": False, "worker_id": health.worker_id}

        # Try tmux first
        if self._tmux_nudge(health, message):
            result["method"] = "tmux"
            result["success"] = True
            self._record_nudge(health.worker_id, result, message)
            return result

        # Fall back to steering file
        if health.worktree_path:
            steering_path = Path(health.worktree_path) / ".claude" / "steering.md"
            try:
                steering_path.parent.mkdir(parents=True, exist_ok=True)
                nudge_msg = message or (
                    f"Watchdog: You have been silent for {int(time.time() - health.last_output_time)}s. "
                    "Please report progress or indicate if you are blocked."
                )
                steering_path.write_text(f"# Nudge\n\n{nudge_msg}\n")
                result["method"] = "steering_file"
                result["success"] = True
            except Exception as e:
                logger.warning(f"Steering file nudge failed for worker {health.worker_id}: {e}")

        self._record_nudge(health.worker_id, result, message)
        return result

    def _record_nudge(self, worker_id: int, result: dict, message: str) -> None:
        """Record a nudge attempt in the history."""
        if worker_id not in self.nudge_history:
            self.nudge_history[worker_id] = []
        self.nudge_history[worker_id].append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "method": result["method"],
            "message": message,
            "success": result["success"],
        })

    def get_nudge_history(self, worker_id: int) -> list[dict]:
        """Get nudge history for a specific worker."""
        return self.nudge_history.get(worker_id, [])

    def _ai_triage(self, health: WorkerHealth) -> dict:
        """AI-powered triage returning structured verdict.

        Returns:
            dict with keys: verdict, reasoning, recommended_action
            verdict is one of: "retry", "terminate", "extend", "escalate"
        """
        recent_output = self.output_buffers.get(health.worker_id, [])
        output_context = "\n".join(recent_output[-20:]) if recent_output else "No recent output"

        # Build triage context
        context = {
            "worker_id": health.worker_id,
            "status": health.status,
            "warnings": health.warnings,
            "escalation_level": health.escalation_level,
            "recent_output": output_context,
            "stall_duration_seconds": time.time() - health.last_output_time if health.last_output_time else 0,
        }

        # Heuristic-based triage
        stall_duration = context["stall_duration_seconds"]
        has_errors = any("error" in w.lower() for w in health.warnings)
        has_loop = any("loop" in w.lower() or "repeated" in w.lower() for w in health.warnings)
        output_has_progress = any(
            "commit" in l.lower() or "test" in l.lower() or "done" in l.lower()
            for l in recent_output[-5:]
        ) if recent_output else False

        if has_loop and stall_duration > 600:
            verdict = {
                "verdict": "terminate",
                "reasoning": "Worker stuck in detected loop for >10min",
                "recommended_action": "Terminate and reassign tasks to new worker",
            }
        elif has_errors and health.escalation_level >= 2:
            verdict = {
                "verdict": "escalate",
                "reasoning": f"Persistent errors after {health.escalation_level} escalations",
                "recommended_action": "Escalate to orchestrator for manual intervention",
            }
        elif output_has_progress and stall_duration < 600:
            verdict = {
                "verdict": "extend",
                "reasoning": "Recent output shows progress, may need more time",
                "recommended_action": "Extend timeout and continue monitoring",
            }
        elif stall_duration < 300:
            verdict = {
                "verdict": "retry",
                "reasoning": f"Stalled for {stall_duration:.0f}s, within retry window",
                "recommended_action": "Send nudge and wait for response",
            }
        else:
            verdict = {
                "verdict": "terminate",
                "reasoning": f"No progress for {stall_duration:.0f}s with no signs of recovery",
                "recommended_action": "Terminate worker and reassign remaining tasks",
            }

        return verdict

    @staticmethod
    def _is_pid_alive(pid: int) -> bool:
        """Check if a process with the given PID is still running."""
        try:
            if sys.platform == "win32":
                import subprocess
                result = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}"],
                    capture_output=True, text=True, timeout=5,
                )
                return str(pid) in result.stdout
            else:
                os.kill(pid, 0)
                return True
        except (OSError, FileNotFoundError):
            return False

    @staticmethod
    def _kill_pid(pid: int) -> bool:
        """Attempt to kill a process."""
        try:
            if sys.platform == "win32":
                import subprocess
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/F"],
                    capture_output=True, timeout=5,
                )
            else:
                import signal
                os.kill(pid, signal.SIGTERM)
            return True
        except Exception:
            return False

    def get_status(self) -> dict:
        """Get current health status of all workers."""
        return {
            "running": self._running,
            "workers": {
                wid: health.to_dict()
                for wid, health in self.workers.items()
            },
            "triage_results": dict(self._triage_results),
            "total_events": len(self._events),
            "recent_events": [
                e.to_dict() for e in self._events[-10:]
            ],
        }

    def get_events(self, limit: int = 50) -> list[dict]:
        """Get recent watchdog events."""
        return [e.to_dict() for e in self._events[-limit:]]
