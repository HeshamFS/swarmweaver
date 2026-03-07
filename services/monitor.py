"""
Fleet Monitor
===============

Provides high-level health analysis of the swarm fleet by combining
data from the swarm state file, watchdog health checks, and the
inter-agent mail system.

Generates recommended actions based on detected issues.

Also includes the MonitorDaemon — a background asyncio task for
continuous fleet health monitoring with WebSocket event push.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Callable, Any

logger = logging.getLogger(__name__)


class FleetMonitor:
    """
    Analyzes swarm fleet health and recommends corrective actions.

    Usage:
        monitor = FleetMonitor()
        health = monitor.analyze_fleet_health(project_dir)
        issues = monitor.check_mail_for_issues(project_dir)
        actions = monitor.recommend_actions(health, issues)
    """

    def analyze_fleet_health(self, project_dir: Path) -> dict:
        """
        Analyze all workers' health.

        Reads .swarm/state.json for worker status and .swarm/watchdog_state.json
        for health monitoring data. Combines into a unified health report.

        Args:
            project_dir: Path to the project directory

        Returns:
            Dict with keys: workers (list of worker health dicts),
            summary (aggregate stats)
        """
        workers: list[dict] = []
        summary = {
            "total": 0,
            "healthy": 0,
            "warning": 0,
            "stalled": 0,
            "dead": 0,
            "completed": 0,
            "overall_status": "unknown",
        }

        # Read swarm state
        state_file = project_dir / ".swarm" / "state.json"
        swarm_state: dict = {}
        if state_file.exists():
            try:
                swarm_state = json.loads(state_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass

        # Read watchdog state
        watchdog_file = project_dir / ".swarm" / "watchdog_state.json"
        watchdog_data: dict = {}
        if watchdog_file.exists():
            try:
                watchdog_data = json.loads(watchdog_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass

        watchdog_workers = watchdog_data.get("workers", {})

        # Process each worker from swarm state
        for worker in swarm_state.get("workers", []):
            worker_id = worker.get("worker_id", worker.get("id", 0))
            status = worker.get("status", "unknown")
            pid = worker.get("pid")

            # Merge watchdog health data if available
            wd_health = watchdog_workers.get(str(worker_id), {})
            health_status = wd_health.get("status", "healthy")
            last_output_ago = wd_health.get("last_output_ago_seconds", -1)
            escalation_level = wd_health.get("escalation_level", 0)
            warnings = wd_health.get("warnings", [])

            # Determine effective status
            if status in ("done", "completed"):
                effective_status = "completed"
            elif health_status in ("dead", "terminated"):
                effective_status = "dead"
            elif health_status == "stalled":
                effective_status = "stalled"
            elif health_status == "warning":
                effective_status = "warning"
            else:
                effective_status = "healthy"

            worker_entry = {
                "worker_id": worker_id,
                "pid": pid,
                "task_status": status,
                "health_status": effective_status,
                "last_output_ago_seconds": last_output_ago,
                "escalation_level": escalation_level,
                "warnings": warnings[-3:],  # Last 3 warnings
                "task_id": worker.get("task_id", ""),
                "worktree": worker.get("worktree_path", ""),
            }
            workers.append(worker_entry)

            # Update summary counters
            summary["total"] += 1
            if effective_status in summary:
                summary[effective_status] += 1

        # Determine overall fleet status
        if summary["dead"] > 0 or summary["stalled"] > 0:
            summary["overall_status"] = "degraded"
        elif summary["warning"] > 0:
            summary["overall_status"] = "warning"
        elif summary["total"] == 0:
            summary["overall_status"] = "idle"
        elif summary["completed"] == summary["total"]:
            summary["overall_status"] = "completed"
        else:
            summary["overall_status"] = "healthy"

        return {"workers": workers, "summary": summary}

    def check_mail_for_issues(self, project_dir: Path) -> list[dict]:
        """
        Scan mail for error/question messages that need attention.

        Reads from the MailStore and filters for ERROR and QUESTION type
        messages that are unread, indicating issues needing orchestrator attention.

        Args:
            project_dir: Path to the project directory

        Returns:
            List of issue dicts with keys: message_id, sender, msg_type,
            subject, body, priority, created_at
        """
        issues: list[dict] = []

        try:
            from state.mail import MailStore
            store = MailStore(project_dir)
            if not store.db_path.exists():
                return []
            store.initialize()

            # Get unread error messages
            error_msgs = store.get_messages(
                msg_type="error",
                unread_only=True,
                limit=50,
            )
            for msg in error_msgs:
                issues.append({
                    "message_id": msg.id,
                    "sender": msg.sender,
                    "msg_type": msg.msg_type,
                    "subject": msg.subject,
                    "body": msg.body[:500],
                    "priority": msg.priority,
                    "created_at": msg.created_at,
                    "urgency": "high",
                })

            # Get unread question messages
            question_msgs = store.get_messages(
                msg_type="question",
                unread_only=True,
                limit=50,
            )
            for msg in question_msgs:
                issues.append({
                    "message_id": msg.id,
                    "sender": msg.sender,
                    "msg_type": msg.msg_type,
                    "subject": msg.subject,
                    "body": msg.body[:500],
                    "priority": msg.priority,
                    "created_at": msg.created_at,
                    "urgency": "medium" if msg.priority in ("high", "urgent") else "low",
                })

            store.close()
        except Exception:
            pass

        # Sort by urgency (high first)
        urgency_order = {"high": 0, "medium": 1, "low": 2}
        issues.sort(key=lambda x: urgency_order.get(x.get("urgency", "low"), 2))

        return issues

    def recommend_actions(
        self,
        health_data: dict,
        mail_issues: list[dict],
    ) -> list[dict]:
        """
        Generate recommended actions based on health + mail analysis.

        Combines fleet health status with mail issues to produce a prioritized
        list of recommended actions for the orchestrator.

        Args:
            health_data: Output from analyze_fleet_health()
            mail_issues: Output from check_mail_for_issues()

        Returns:
            List of action dicts with keys: action, reason, urgency, target_worker
        """
        actions: list[dict] = []

        # Analyze worker health issues
        for worker in health_data.get("workers", []):
            worker_id = worker.get("worker_id")
            status = worker.get("health_status", "healthy")

            if status == "dead":
                actions.append({
                    "action": "restart_worker",
                    "reason": f"Worker {worker_id} process is dead (PID no longer exists)",
                    "urgency": "high",
                    "target_worker": worker_id,
                })
            elif status == "stalled":
                escalation = worker.get("escalation_level", 0)
                if escalation >= 2:
                    actions.append({
                        "action": "investigate_and_restart",
                        "reason": f"Worker {worker_id} stalled at escalation level {escalation}",
                        "urgency": "high",
                        "target_worker": worker_id,
                    })
                else:
                    actions.append({
                        "action": "send_nudge",
                        "reason": f"Worker {worker_id} has not produced output recently",
                        "urgency": "medium",
                        "target_worker": worker_id,
                    })
            elif status == "warning":
                last_ago = worker.get("last_output_ago_seconds", -1)
                actions.append({
                    "action": "monitor_closely",
                    "reason": f"Worker {worker_id} approaching stall threshold ({last_ago}s since last output)",
                    "urgency": "low",
                    "target_worker": worker_id,
                })

        # Analyze mail issues
        for issue in mail_issues:
            sender = issue.get("sender", "unknown")
            msg_type = issue.get("msg_type", "")
            subject = issue.get("subject", "")

            if msg_type == "error":
                actions.append({
                    "action": "review_error",
                    "reason": f"Error from {sender}: {subject}",
                    "urgency": "high",
                    "target_worker": sender,
                })
            elif msg_type == "question":
                actions.append({
                    "action": "answer_question",
                    "reason": f"Question from {sender}: {subject}",
                    "urgency": issue.get("urgency", "medium"),
                    "target_worker": sender,
                })

        # Sort by urgency
        urgency_order = {"high": 0, "medium": 1, "low": 2}
        actions.sort(key=lambda x: urgency_order.get(x.get("urgency", "low"), 2))

        return actions


# ---------------------------------------------------------------------------
# Monitor Daemon — background asyncio task for continuous fleet health checks
# ---------------------------------------------------------------------------


@dataclass
class FleetHealthSummary:
    """Summary of fleet health at a point in time."""
    timestamp: str = ""
    fleet_score: int = 100
    worker_statuses: list[dict] = field(default_factory=list)
    actions_taken: list[dict] = field(default_factory=list)
    unread_urgent_mail: int = 0
    budget_percentage: float = 0.0
    check_number: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


class MonitorDaemon:
    """Background asyncio task for continuous fleet health monitoring."""

    def __init__(
        self,
        project_dir: Path,
        check_interval: float = 60.0,
        on_event: Optional[Callable] = None,
    ):
        self.project_dir = project_dir
        self.check_interval = check_interval
        self.on_event = on_event
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self.health_history: list[FleetHealthSummary] = []
        self.check_count = 0
        self._mail_store = None
        self._watchdog = None
        self._budget_tracker = None

    def set_dependencies(self, mail_store=None, watchdog=None, budget_tracker=None):
        """Set references to other system components."""
        self._mail_store = mail_store
        self._watchdog = watchdog
        self._budget_tracker = budget_tracker

    async def start(self):
        """Start the monitor daemon."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(f"Monitor daemon started (interval: {self.check_interval}s)")

    def stop(self):
        """Stop the monitor daemon."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("Monitor daemon stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    async def _run_loop(self):
        """Main monitoring loop."""
        while self._running:
            try:
                summary = await self._check_fleet_health()
                self.health_history.append(summary)
                # Keep last 30 summaries
                if len(self.health_history) > 30:
                    self.health_history = self.health_history[-30:]

                # Push health summary over WebSocket
                if self.on_event:
                    await self.on_event({
                        "type": "monitor_health_summary",
                        "fleet_score": summary.fleet_score,
                        "worker_statuses": summary.worker_statuses,
                        "actions_taken": summary.actions_taken,
                        "check_number": summary.check_number,
                        "timestamp": summary.timestamp,
                    })

                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitor daemon error: {e}")
                await asyncio.sleep(self.check_interval)

    async def _check_fleet_health(self) -> FleetHealthSummary:
        """Perform a full fleet health check."""
        self.check_count += 1
        summary = FleetHealthSummary(
            timestamp=datetime.now(timezone.utc).isoformat(),
            check_number=self.check_count,
        )

        score = 100
        actions: list[dict] = []
        worker_statuses: list[dict] = []

        # Check watchdog health data
        if self._watchdog:
            status = self._watchdog.get_status()
            workers = status.get("workers", {})

            for wid_str, wdata in workers.items():
                wid = int(wid_str) if wid_str.isdigit() else wid_str
                ws = {
                    "worker_id": wid,
                    "status": wdata.get("status", "unknown"),
                    "last_output_ago": wdata.get("last_output_ago_seconds", 0),
                    "escalation_level": wdata.get("escalation_level", 0),
                    "warnings": wdata.get("warnings", []),
                }
                worker_statuses.append(ws)

                wstatus = wdata.get("status", "healthy")
                if wstatus == "healthy":
                    pass
                elif wstatus == "warning":
                    score -= 10
                elif wstatus == "stalled":
                    score -= 25
                    # Auto-action: nudge stalled workers
                    if wdata.get("escalation_level", 0) < 2:
                        try:
                            from services.watchdog import WorkerHealth
                            health = WorkerHealth(
                                worker_id=int(wid) if isinstance(wid, str) and wid.isdigit() else wid,
                                pid=wdata.get("pid"),
                                worktree_path=wdata.get("worktree_path", ""),
                            )
                            self._watchdog._nudge_worker(health, "Monitor daemon: Please report status")
                            actions.append({
                                "type": "nudge",
                                "worker_id": wid,
                                "reason": "Stalled worker detected",
                            })
                        except Exception as e:
                            logger.warning(f"Failed to nudge worker {wid}: {e}")
                elif wstatus == "dead":
                    score -= 40
                    actions.append({
                        "type": "alert",
                        "worker_id": wid,
                        "reason": "Worker process is dead",
                    })

        # Check mail for urgent unread messages
        if self._mail_store:
            try:
                urgent_count = 0
                messages = self._mail_store.get_messages(recipient="orchestrator", unread_only=True)
                for msg in messages:
                    if msg.priority in ("urgent", "high"):
                        urgent_count += 1
                summary.unread_urgent_mail = urgent_count
                score -= urgent_count * 5

                if urgent_count > 0:
                    actions.append({
                        "type": "flag",
                        "reason": f"{urgent_count} unread urgent mail messages",
                    })
            except Exception:
                pass

        # Check budget
        if self._budget_tracker:
            try:
                budget_info = self._budget_tracker.get_budget_info()
                if budget_info.get("budget_limit"):
                    pct = (budget_info.get("total_cost", 0) / budget_info["budget_limit"]) * 100
                    summary.budget_percentage = pct
                    if pct > 80:
                        score -= 15
                        actions.append({
                            "type": "warning",
                            "reason": f"Budget at {pct:.0f}%",
                        })
            except Exception:
                pass

        summary.fleet_score = max(0, min(100, score))
        summary.worker_statuses = worker_statuses
        summary.actions_taken = actions

        return summary

    def get_status(self) -> dict:
        """Get current monitor daemon status."""
        return {
            "running": self._running,
            "check_interval": self.check_interval,
            "total_checks": self.check_count,
            "last_check": self.health_history[-1].to_dict() if self.health_history else None,
            "health_trend": [h.fleet_score for h in self.health_history[-30:]],
        }
