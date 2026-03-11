"""
Enhanced Swarm Watchdog Health Monitor
=======================================

Production-grade health monitoring for SwarmWeaver multi-agent swarms.

Architecture (3-tier):
  Tier 0 — Mechanical Daemon: Forward-only state machine with 6-signal health
           evaluation, heartbeat protocol, and dependency-aware escalation
  Tier 1 — AI Triage:        LLM-based analysis with rich 7-source context,
           structured verdicts, and confidence scoring
  Tier 2 — Monitor Agent:    External fleet health monitor (services/monitor.py)

Features beyond Overstory:
  - 9-state forward-only state machine with RECOVERING state
  - 6-signal health evaluation (asyncio.Task, PID, output, tool, git, heartbeat)
  - Active heartbeat protocol with metadata
  - Dependency-aware escalation (prioritize blockers)
  - Circuit breaker (3-state: closed/open/half-open)
  - Per-worker resource monitoring via psutil
  - Persistent SQLite event log
  - YAML configuration with live editing
  - Auto-reassignment of terminated worker tasks
  - Run-level completion detection
  - Failure recording to project expertise
"""

import asyncio
import json
import logging
import os
import sqlite3
import subprocess as _sp
import sys
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum, IntEnum
from pathlib import Path
from typing import Optional, Callable, Any

logger = logging.getLogger(__name__)


# ===========================================================================
# W1-1: Forward-Only State Machine
# ===========================================================================

class AgentState(str, Enum):
    """9-state forward-only state machine for worker health."""
    BOOTING = "booting"         # Just spawned, not yet producing output
    WORKING = "working"         # Active, producing output
    IDLE = "idle"               # Alive but no recent activity (under threshold)
    WARNING = "warning"         # Approaching stall threshold (70%)
    STALLED = "stalled"         # Exceeded stall threshold, escalation in progress
    RECOVERING = "recovering"   # Was stalled, now producing output again
    COMPLETED = "completed"     # Finished all tasks
    ZOMBIE = "zombie"           # PID dead but state says working (ZFC)
    TERMINATED = "terminated"   # Killed by watchdog or orchestrator


ALLOWED_TRANSITIONS: dict[AgentState, set[AgentState]] = {
    AgentState.BOOTING:    {AgentState.WORKING, AgentState.ZOMBIE, AgentState.TERMINATED},
    AgentState.WORKING:    {AgentState.IDLE, AgentState.COMPLETED, AgentState.ZOMBIE, AgentState.TERMINATED},
    AgentState.IDLE:       {AgentState.WORKING, AgentState.WARNING, AgentState.COMPLETED, AgentState.ZOMBIE, AgentState.TERMINATED},
    AgentState.WARNING:    {AgentState.WORKING, AgentState.STALLED, AgentState.ZOMBIE, AgentState.TERMINATED},
    AgentState.STALLED:    {AgentState.RECOVERING, AgentState.ZOMBIE, AgentState.TERMINATED},
    AgentState.RECOVERING: {AgentState.WORKING, AgentState.STALLED, AgentState.ZOMBIE, AgentState.TERMINATED},
    AgentState.COMPLETED:  set(),       # Terminal
    AgentState.ZOMBIE:     {AgentState.TERMINATED},  # Can only be terminated
    AgentState.TERMINATED: set(),       # Terminal
}


class EscalationLevel(IntEnum):
    """Watchdog escalation levels."""
    LOG = 0
    NOTIFY = 1
    RESTART = 2
    TERMINATE = 3


# ===========================================================================
# W1-2: Configurable Thresholds
# ===========================================================================

@dataclass
class WatchdogConfig:
    """Watchdog configuration — loaded from YAML, env vars, or defaults."""
    enabled: bool = True
    check_interval_s: float = 30.0
    # Stall detection
    idle_threshold_s: float = 120.0       # 2 min → IDLE
    stall_threshold_s: float = 300.0      # 5 min → STALLED
    zombie_threshold_s: float = 600.0     # 10 min → ZOMBIE
    boot_grace_s: float = 60.0            # Grace for new workers
    # Escalation
    nudge_interval_s: float = 60.0
    max_nudge_attempts: int = 3
    # AI triage
    ai_triage_enabled: bool = True
    triage_timeout_s: float = 30.0
    triage_context_lines: int = 50
    triage_model: str = ""                # Default: use WORKER_MODEL
    # Monitor agent (Tier 2 — future)
    monitor_agent_enabled: bool = False
    # Auto-reassignment
    auto_reassign: bool = True
    # Circuit breaker
    circuit_breaker_enabled: bool = True
    max_failure_rate: float = 0.5
    circuit_breaker_window_s: float = 600.0
    # Persistent roles (exempt from stall detection)
    persistent_roles: set[str] = field(default_factory=lambda: {"coordinator", "monitor"})

    @classmethod
    def load(cls, project_dir: Path) -> "WatchdogConfig":
        """Load from .swarmweaver/watchdog.yaml → env vars → defaults."""
        config = cls()

        # 1. Try YAML file
        yaml_path = project_dir / ".swarmweaver" / "watchdog.yaml"
        if yaml_path.exists():
            try:
                import yaml
                with open(yaml_path) as f:
                    data = yaml.safe_load(f) or {}
                for key, value in data.items():
                    if hasattr(config, key):
                        field_type = type(getattr(config, key))
                        if field_type is set:
                            setattr(config, key, set(value) if isinstance(value, list) else value)
                        else:
                            setattr(config, key, field_type(value))
            except ImportError:
                # PyYAML not available — try JSON fallback
                try:
                    data = json.loads(yaml_path.read_text())
                    for key, value in data.items():
                        if hasattr(config, key):
                            field_type = type(getattr(config, key))
                            if field_type is set:
                                setattr(config, key, set(value) if isinstance(value, list) else value)
                            else:
                                setattr(config, key, field_type(value))
                except (json.JSONDecodeError, OSError):
                    pass
            except (OSError, Exception) as e:
                logger.warning(f"Failed to load watchdog.yaml: {e}")

        # 2. Override with env vars (WATCHDOG_CHECK_INTERVAL_S, etc.)
        env_prefix = "WATCHDOG_"
        for field_name in cls.__dataclass_fields__:
            env_key = env_prefix + field_name.upper()
            env_val = os.environ.get(env_key)
            if env_val is not None:
                field_type = type(getattr(config, field_name))
                try:
                    if field_type is bool:
                        setattr(config, field_name, env_val.lower() in ("1", "true", "yes"))
                    elif field_type is set:
                        setattr(config, field_name, set(env_val.split(",")))
                    else:
                        setattr(config, field_name, field_type(env_val))
                except (ValueError, TypeError):
                    pass

        return config

    def to_dict(self) -> dict:
        d = asdict(self)
        d["persistent_roles"] = list(d["persistent_roles"])
        return d

    def save(self, project_dir: Path) -> None:
        """Save config to .swarmweaver/watchdog.yaml (JSON format)."""
        yaml_path = project_dir / ".swarmweaver" / "watchdog.yaml"
        yaml_path.parent.mkdir(parents=True, exist_ok=True)
        yaml_path.write_text(json.dumps(self.to_dict(), indent=2))


# ===========================================================================
# W1-3: Enhanced WorkerHealth
# ===========================================================================

@dataclass
class WorkerHealth:
    """Health state for a single worker."""
    worker_id: int
    pid: Optional[int] = None
    status: AgentState = AgentState.BOOTING
    last_output_time: float = 0.0
    escalation_level: int = 0
    warnings: list[str] = field(default_factory=list)
    check_count: int = 0
    worktree_path: str = ""
    recorded_status: str = ""  # ZFC: last known recorded status for reconciliation
    # New fields for enhanced watchdog
    asyncio_task: Optional[asyncio.Task] = None
    last_tool_time: float = 0.0
    role: str = "builder"
    assigned_task_ids: list[str] = field(default_factory=list)
    completed_task_ids: list[str] = field(default_factory=list)
    file_scope: list[str] = field(default_factory=list)
    boot_time: float = 0.0
    resource_usage: dict = field(default_factory=dict)
    # State transition history
    state_history: list[dict] = field(default_factory=list)
    # Nudge tracking
    nudge_count: int = 0
    last_nudge_time: float = 0.0
    # LSP diagnostic trend (7th health signal)
    lsp_error_count: int = 0
    lsp_error_trend: str = ""  # "rising", "falling", "stable"
    _lsp_error_history: list = field(default_factory=list)

    def to_dict(self) -> dict:
        d = {
            "worker_id": self.worker_id,
            "pid": self.pid,
            "status": self.status.value if isinstance(self.status, AgentState) else str(self.status),
            "last_output_time": self.last_output_time,
            "escalation_level": self.escalation_level,
            "warnings": self.warnings,
            "check_count": self.check_count,
            "worktree_path": self.worktree_path,
            "recorded_status": self.recorded_status,
            "last_tool_time": self.last_tool_time,
            "role": self.role,
            "assigned_task_ids": self.assigned_task_ids,
            "completed_task_ids": self.completed_task_ids,
            "file_scope": self.file_scope,
            "boot_time": self.boot_time,
            "resource_usage": self.resource_usage,
            "nudge_count": self.nudge_count,
            "lsp_error_count": self.lsp_error_count,
            "lsp_error_trend": self.lsp_error_trend,
        }
        d["last_output_ago_seconds"] = (
            int(time.time() - self.last_output_time)
            if self.last_output_time > 0
            else -1
        )
        return d


@dataclass
class WatchdogEvent:
    """An event emitted by the watchdog."""
    event_type: str
    worker_id: int
    message: str
    escalation_level: int = 0
    timestamp: str = ""
    state_before: str = ""
    state_after: str = ""
    triage_verdict: str = ""
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return asdict(self)


# ===========================================================================
# W1-4: Heartbeat Protocol
# ===========================================================================

class HeartbeatProtocol:
    """Active heartbeat protocol for worker liveness checking."""
    HEARTBEAT_INTERVAL_S = 60    # Workers heartbeat every 60s
    HEARTBEAT_TOLERANCE_S = 90   # Grace before marking missed

    def __init__(self):
        self._last_heartbeat: dict[int, float] = {}       # worker_id → timestamp
        self._heartbeat_data: dict[int, dict] = {}         # worker_id → metadata
        self._pending_requests: dict[int, float] = {}      # worker_id → request_time

    def request_heartbeat(self, worker_id: int, mail_store: Any = None) -> str:
        """Send heartbeat request via mail. Returns request ID."""
        self._pending_requests[worker_id] = time.time()
        request_id = str(uuid.uuid4())[:8]

        if mail_store:
            try:
                mail_store.send_protocol(
                    sender="watchdog",
                    recipient=f"worker-{worker_id}",
                    msg_type="health_check",
                    subject="Heartbeat request",
                    payload={"request_id": request_id, "type": "heartbeat"},
                    priority="high",
                )
            except Exception:
                pass

        return request_id

    def process_heartbeat(self, worker_id: int, data: dict = None) -> None:
        """Process received heartbeat, update tracking."""
        self._last_heartbeat[worker_id] = time.time()
        self._heartbeat_data[worker_id] = data or {}
        self._pending_requests.pop(worker_id, None)

    def check_missed_heartbeats(self) -> list[int]:
        """Return worker IDs that missed their heartbeat window."""
        now = time.time()
        missed = []
        for worker_id, request_time in list(self._pending_requests.items()):
            if now - request_time > self.HEARTBEAT_TOLERANCE_S:
                missed.append(worker_id)
        return missed

    def get_last_heartbeat(self, worker_id: int) -> Optional[float]:
        return self._last_heartbeat.get(worker_id)

    def get_heartbeat_data(self, worker_id: int) -> dict:
        return self._heartbeat_data.get(worker_id, {})


# ===========================================================================
# W3-2: Circuit Breaker
# ===========================================================================

class CircuitBreaker:
    """Prevent cascading failures from draining budget.

    States:
        CLOSED:    Normal operation, spawning allowed
        OPEN:      Too many failures (>50%), spawning blocked
        HALF_OPEN: Tentatively allow one spawn to test recovery
    """

    def __init__(self, max_failure_rate: float = 0.5, window_s: float = 600.0):
        self.max_failure_rate = max_failure_rate
        self.window_s = window_s
        self._state = "closed"  # closed | open | half_open
        self._failures: list[float] = []  # timestamps
        self._successes: list[float] = []  # timestamps
        self._opened_at: float = 0.0
        self._cooldown_s: float = 120.0  # 2 min cooldown before half-open
        self._half_open_spawn_allowed: bool = True

    def record_failure(self) -> None:
        """Record a worker failure."""
        now = time.time()
        self._failures.append(now)
        self._cleanup_window()
        if self._state == "half_open":
            self._state = "open"
            self._opened_at = now
            return
        if self._should_open():
            self._state = "open"
            self._opened_at = now

    def record_success(self) -> None:
        """Record a worker success."""
        now = time.time()
        self._successes.append(now)
        self._cleanup_window()
        if self._state == "half_open":
            self._state = "closed"

    def can_spawn(self) -> tuple[bool, str]:
        """Check if spawning is allowed. Returns (allowed, reason)."""
        self._cleanup_window()
        self._check_half_open()

        if self._state == "closed":
            return True, "Circuit breaker closed — normal operation"
        elif self._state == "half_open":
            if self._half_open_spawn_allowed:
                self._half_open_spawn_allowed = False
                return True, "Circuit breaker half-open — test spawn allowed"
            return False, "Circuit breaker half-open — test spawn already in progress"
        else:  # open
            return False, f"Circuit breaker OPEN — failure rate {self._failure_rate():.0%} exceeds {self.max_failure_rate:.0%}"

    def get_status(self) -> dict:
        self._cleanup_window()
        return {
            "state": self._state,
            "failure_rate": round(self._failure_rate(), 3),
            "failures_in_window": len(self._failures),
            "successes_in_window": len(self._successes),
            "window_s": self.window_s,
        }

    def _failure_rate(self) -> float:
        total = len(self._failures) + len(self._successes)
        if total == 0:
            return 0.0
        return len(self._failures) / total

    def _should_open(self) -> bool:
        total = len(self._failures) + len(self._successes)
        return total >= 2 and self._failure_rate() > self.max_failure_rate

    def _cleanup_window(self) -> None:
        cutoff = time.time() - self.window_s
        self._failures = [t for t in self._failures if t > cutoff]
        self._successes = [t for t in self._successes if t > cutoff]

    def _check_half_open(self) -> None:
        if self._state == "open" and time.time() - self._opened_at > self._cooldown_s:
            self._state = "half_open"
            self._half_open_spawn_allowed = True


# ===========================================================================
# W3-4: Persistent Watchdog Event Store
# ===========================================================================

class WatchdogEventStore:
    """SQLite store at .swarmweaver/watchdog_events.db."""

    def __init__(self, project_dir: Path):
        self.db_path = project_dir / ".swarmweaver" / "watchdog_events.db"
        self._conn: Optional[sqlite3.Connection] = None

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), timeout=10)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS watchdog_events (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                worker_id INTEGER,
                message TEXT,
                escalation_level INTEGER DEFAULT 0,
                state_before TEXT,
                state_after TEXT,
                triage_verdict TEXT,
                metadata_json TEXT
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_watchdog_worker
            ON watchdog_events(worker_id)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_watchdog_type
            ON watchdog_events(event_type)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_watchdog_ts
            ON watchdog_events(timestamp)
        """)
        self._conn.commit()

    def record(self, event: WatchdogEvent) -> str:
        if not self._conn:
            self.initialize()
        event_id = str(uuid.uuid4())[:12]
        self._conn.execute(
            """INSERT INTO watchdog_events
               (id, timestamp, event_type, worker_id, message,
                escalation_level, state_before, state_after,
                triage_verdict, metadata_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event_id,
                event.timestamp,
                event.event_type,
                event.worker_id,
                event.message,
                event.escalation_level,
                event.state_before,
                event.state_after,
                event.triage_verdict,
                json.dumps(event.metadata) if event.metadata else None,
            ),
        )
        self._conn.commit()
        return event_id

    def query(
        self,
        worker_id: Optional[int] = None,
        event_type: Optional[str] = None,
        since: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        if not self._conn:
            self.initialize()
        sql = "SELECT * FROM watchdog_events WHERE 1=1"
        params: list = []
        if worker_id is not None:
            sql += " AND worker_id = ?"
            params.append(worker_id)
        if event_type:
            sql += " AND event_type = ?"
            params.append(event_type)
        if since:
            sql += " AND timestamp >= ?"
            params.append(since)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        cursor = self._conn.execute(sql, params)
        columns = [c[0] for c in cursor.description]
        rows = cursor.fetchall()
        results = []
        for row in rows:
            d = dict(zip(columns, row))
            if d.get("metadata_json"):
                try:
                    d["metadata"] = json.loads(d.pop("metadata_json"))
                except (json.JSONDecodeError, TypeError):
                    d["metadata"] = {}
                    del d["metadata_json"]
            else:
                d.pop("metadata_json", None)
                d["metadata"] = {}
            results.append(d)
        return results

    def get_summary(self) -> dict:
        if not self._conn:
            self.initialize()
        cursor = self._conn.execute(
            "SELECT event_type, COUNT(*) FROM watchdog_events GROUP BY event_type"
        )
        by_type = dict(cursor.fetchall())
        cursor = self._conn.execute("SELECT COUNT(*) FROM watchdog_events")
        total = cursor.fetchone()[0]
        recent = self.query(limit=10)
        return {"total": total, "by_type": by_type, "recent_events": recent}

    def purge(self, older_than_days: int = 7) -> int:
        if not self._conn:
            self.initialize()
        cutoff = datetime.now(timezone.utc).isoformat()
        # Simple: delete entries older than N days based on timestamp string comparison
        from datetime import timedelta
        cutoff_dt = datetime.now(timezone.utc) - timedelta(days=older_than_days)
        cutoff_str = cutoff_dt.isoformat()
        cursor = self._conn.execute(
            "DELETE FROM watchdog_events WHERE timestamp < ?", (cutoff_str,)
        )
        self._conn.commit()
        return cursor.rowcount

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None


# ===========================================================================
# Main SwarmWatchdog Class
# ===========================================================================

class SwarmWatchdog:
    """
    Enhanced background health monitor for swarm workers.

    Features:
      - 9-state forward-only state machine
      - 6-signal health evaluation
      - Heartbeat protocol
      - Dependency-aware escalation
      - LLM-based AI triage with fallback heuristics
      - Circuit breaker for cascade failure prevention
      - Per-worker resource monitoring
      - Persistent SQLite event log
      - Auto-reassignment of terminated worker tasks
      - Run completion detection

    Usage:
        config = WatchdogConfig.load(project_dir)
        watchdog = SwarmWatchdog(
            config=config,
            mail_store=mail_store,
            project_dir=project_dir,
            on_event=ws_send,
        )

        watchdog.register_worker(worker_id=1, pid=12345, role="builder", ...)
        task = asyncio.create_task(watchdog.run())
        watchdog.stop()
    """

    def __init__(
        self,
        config: Optional[WatchdogConfig] = None,
        mail_store: Optional[Any] = None,
        project_dir: Optional[Path] = None,
        on_event: Optional[Callable] = None,
        # Backward compatibility
        stale_timeout: float = 300.0,
        check_interval: float = 30.0,
        max_escalation: int = EscalationLevel.TERMINATE,
    ):
        self.config = config or WatchdogConfig()
        # Backward compat: if stale_timeout/check_interval differ from defaults,
        # they were explicitly passed — respect them
        if stale_timeout != 300.0:
            self.config.stall_threshold_s = stale_timeout
        if check_interval != 30.0:
            self.config.check_interval_s = check_interval

        self.mail_store = mail_store
        self.project_dir = project_dir or Path(".")
        self._on_event = on_event

        self.workers: dict[int, WorkerHealth] = {}
        self.output_buffers: dict[int, list[str]] = {}
        self.nudge_history: dict[int, list[dict]] = {}
        self._running = False
        self._events: list[WatchdogEvent] = []
        self._triage_results: dict[int, dict] = {}
        self._run_complete_sent = False
        self._auto_run_complete = True  # Set False when orchestrator manages completion

        # Enhanced components
        self.heartbeat = HeartbeatProtocol()
        self.circuit_breaker = CircuitBreaker(
            max_failure_rate=self.config.max_failure_rate,
            window_s=self.config.circuit_breaker_window_s,
        )
        self._event_store: Optional[WatchdogEventStore] = None
        if project_dir:
            self._event_store = WatchdogEventStore(project_dir)
            try:
                self._event_store.initialize()
            except Exception as e:
                logger.warning(f"Failed to initialize watchdog event store: {e}")
                self._event_store = None

        # Backward compat aliases
        self.stale_timeout = self.config.stall_threshold_s
        self.check_interval = self.config.check_interval_s
        self.max_escalation = min(max_escalation, EscalationLevel.TERMINATE)

    # ------------------------------------------------------------------
    # Worker registration
    # ------------------------------------------------------------------

    def register_worker(
        self,
        worker_id: int,
        pid: Optional[int] = None,
        role: str = "builder",
        worktree_path: str = "",
        assigned_task_ids: Optional[list[str]] = None,
        file_scope: Optional[list[str]] = None,
        asyncio_task: Optional[asyncio.Task] = None,
    ) -> None:
        """Register a worker for health monitoring."""
        now = time.time()
        self.workers[worker_id] = WorkerHealth(
            worker_id=worker_id,
            pid=pid,
            status=AgentState.BOOTING,
            last_output_time=now,
            worktree_path=worktree_path,
            role=role,
            assigned_task_ids=assigned_task_ids or [],
            file_scope=file_scope or [],
            asyncio_task=asyncio_task,
            boot_time=now,
        )

    def unregister_worker(self, worker_id: int) -> None:
        """Remove a worker from monitoring."""
        self.workers.pop(worker_id, None)
        self.output_buffers.pop(worker_id, None)

    def report_activity(self, worker_id: int) -> None:
        """Report that a worker produced output (is still active)."""
        if worker_id in self.workers:
            health = self.workers[worker_id]
            health.last_output_time = time.time()
            # Transition to WORKING if was in a recoverable state
            if health.status in (AgentState.BOOTING, AgentState.IDLE, AgentState.RECOVERING):
                self._transition(health, AgentState.WORKING, "Activity detected")
            elif health.status == AgentState.WARNING:
                self._transition(health, AgentState.WORKING, "Activity resumed — warning cleared")
            elif health.status == AgentState.STALLED:
                self._transition(health, AgentState.RECOVERING, "Activity detected after stall")

    def report_output(self, worker_id: int, line: str) -> None:
        """Record output line from a worker for triage context."""
        if worker_id not in self.output_buffers:
            self.output_buffers[worker_id] = []
        self.output_buffers[worker_id].append(line)
        if len(self.output_buffers[worker_id]) > 50:
            self.output_buffers[worker_id] = self.output_buffers[worker_id][-50:]

    def report_tool_activity(self, worker_id: int, tool_name: str = "") -> None:
        """Report that a worker made a tool call (may not produce output)."""
        if worker_id in self.workers:
            self.workers[worker_id].last_tool_time = time.time()
            self.report_activity(worker_id)

    def report_task_completion(self, worker_id: int, task_id: str) -> None:
        """Report that a worker completed a task."""
        if worker_id in self.workers:
            health = self.workers[worker_id]
            if task_id not in health.completed_task_ids:
                health.completed_task_ids.append(task_id)

    def mark_completed(self, worker_id: int) -> None:
        """Mark a worker as completed (all tasks done)."""
        if worker_id in self.workers:
            self._transition(self.workers[worker_id], AgentState.COMPLETED,
                             "All tasks completed")
            self.circuit_breaker.record_success()

    def update_pid(self, worker_id: int, pid: int) -> None:
        """Update a worker's PID (e.g., after restart)."""
        if worker_id in self.workers:
            self.workers[worker_id].pid = pid

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------

    def _transition(self, health: WorkerHealth, new_state: AgentState,
                    reason: str = "") -> bool:
        """Validate and execute a state transition."""
        old_state = health.status
        if not isinstance(old_state, AgentState):
            # Backward compat: convert string to AgentState
            try:
                old_state = AgentState(old_state)
            except ValueError:
                old_state = AgentState.WORKING

        allowed = ALLOWED_TRANSITIONS.get(old_state, set())
        if new_state not in allowed:
            logger.debug(
                f"Rejected transition {old_state.value} → {new_state.value} "
                f"for worker {health.worker_id}: {reason}"
            )
            return False

        health.status = new_state
        transition_record = {
            "from": old_state.value,
            "to": new_state.value,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        health.state_history.append(transition_record)

        # Record to persistent store
        event = WatchdogEvent(
            event_type="state_change",
            worker_id=health.worker_id,
            message=f"{old_state.value} → {new_state.value}: {reason}",
            state_before=old_state.value,
            state_after=new_state.value,
        )
        self._record_event(event)

        # Emit WebSocket event
        self._emit({
            "type": "watchdog_state_change",
            "worker_id": health.worker_id,
            "old_state": old_state.value,
            "new_state": new_state.value,
            "reason": reason,
        })

        # Reset escalation on recovery
        if new_state in (AgentState.WORKING, AgentState.RECOVERING):
            health.escalation_level = 0
            health.warnings = []

        return True

    # ------------------------------------------------------------------
    # Main monitoring loop
    # ------------------------------------------------------------------

    async def run(
        self,
        on_event: Optional[Callable[[WatchdogEvent], Any]] = None,
    ) -> None:
        """Main monitoring loop. Runs until stop() is called."""
        self._running = True
        if on_event:
            self._on_event = on_event

        while self._running:
            await asyncio.sleep(self.config.check_interval_s)

            if not self._running:
                break

            for worker_id, health in list(self.workers.items()):
                health.check_count += 1

                # Skip persistent roles
                if health.role in self.config.persistent_roles:
                    continue

                # Skip terminal states
                if health.status in (AgentState.COMPLETED, AgentState.TERMINATED):
                    continue

                await self._check_worker(health)

            # Check run completion
            await self._check_run_completion()

            # Check heartbeats
            missed = self.heartbeat.check_missed_heartbeats()
            for wid in missed:
                if wid in self.workers:
                    health = self.workers[wid]
                    if health.status not in (AgentState.COMPLETED, AgentState.TERMINATED,
                                             AgentState.ZOMBIE):
                        health.warnings.append("Missed heartbeat")

    def stop(self) -> None:
        """Stop the monitoring loop."""
        self._running = False

    # ------------------------------------------------------------------
    # W1-3: 6-Signal Health Evaluation
    # ------------------------------------------------------------------

    async def _check_worker(self, health: WorkerHealth) -> None:
        """Check a single worker using 6-signal priority hierarchy."""

        # Signal 1 (highest): asyncio.Task state
        if health.asyncio_task is not None:
            if health.asyncio_task.done():
                exc = health.asyncio_task.exception() if not health.asyncio_task.cancelled() else None
                if exc:
                    self._transition(health, AgentState.ZOMBIE,
                                     f"asyncio.Task raised exception: {exc}")
                elif health.asyncio_task.cancelled():
                    self._transition(health, AgentState.TERMINATED,
                                     "asyncio.Task was cancelled")
                else:
                    # Task completed normally
                    if health.status != AgentState.COMPLETED:
                        self._transition(health, AgentState.COMPLETED,
                                         "asyncio.Task completed normally")
                return

        # Signal 2: PID liveness
        if health.pid is not None and not self._is_pid_alive(health.pid):
            if health.status != AgentState.ZOMBIE:
                old_recorded = health.recorded_status
                if old_recorded in ("working", "running"):
                    health.warnings.append(
                        f"ZFC: Recorded '{old_recorded}' but PID {health.pid} dead"
                    )
                self._transition(health, AgentState.ZOMBIE,
                                 f"PID {health.pid} no longer running")
            return

        # Boot grace period
        if health.status == AgentState.BOOTING:
            if time.time() - health.boot_time < self.config.boot_grace_s:
                return  # Still in grace period

        # Signal 3: Output freshness
        elapsed = time.time() - health.last_output_time if health.last_output_time > 0 else 0

        # Signal 4: Tool call activity (may produce no stdout)
        tool_elapsed = time.time() - health.last_tool_time if health.last_tool_time > 0 else float("inf")

        # Signal 5: Git commit activity
        git_active = self._check_git_activity(health)

        # Signal 6: Heartbeat data
        last_hb = self.heartbeat.get_last_heartbeat(health.worker_id)
        hb_elapsed = time.time() - last_hb if last_hb else float("inf")

        # Signal 7: LSP diagnostic trend
        if health.lsp_error_count > 0:
            health._lsp_error_history.append(health.lsp_error_count)
            if len(health._lsp_error_history) > 10:
                health._lsp_error_history = health._lsp_error_history[-10:]
            if len(health._lsp_error_history) >= 3:
                recent = health._lsp_error_history[-3:]
                if recent[-1] > recent[-2] > recent[-3]:
                    health.lsp_error_trend = "rising"
                    if health.status in (AgentState.WORKING, AgentState.IDLE):
                        self._transition(health, AgentState.WARNING,
                                         f"LSP errors rising: {recent}")
                elif recent[-1] < recent[-2]:
                    health.lsp_error_trend = "falling"
                else:
                    health.lsp_error_trend = "stable"

        # Determine effective freshness — use the most recent signal
        effective_elapsed = min(
            elapsed,
            tool_elapsed,
            hb_elapsed,
        )
        if git_active:
            effective_elapsed = 0  # Git activity means worker is alive

        # Resource monitoring
        resource_data = self._check_resources(health)
        if resource_data:
            health.resource_usage = resource_data

        # State evaluation
        if effective_elapsed <= 0:
            return  # Worker is active

        if effective_elapsed > self.config.stall_threshold_s:
            # Stalled
            if health.status in (AgentState.WORKING, AgentState.IDLE, AgentState.WARNING):
                self._transition(health, AgentState.WARNING, "Approaching stall")
                self._transition(health, AgentState.STALLED,
                                 f"No activity for {int(effective_elapsed)}s")
            elif health.status == AgentState.WARNING:
                self._transition(health, AgentState.STALLED,
                                 f"No activity for {int(effective_elapsed)}s")
            elif health.status == AgentState.RECOVERING:
                self._transition(health, AgentState.STALLED,
                                 f"Recovery failed — stalled again for {int(effective_elapsed)}s")
            if health.status == AgentState.STALLED:
                await self._escalate_stall(health, effective_elapsed)

        elif effective_elapsed > self.config.stall_threshold_s * 0.7:
            # Warning
            if health.status in (AgentState.WORKING, AgentState.IDLE):
                self._transition(health, AgentState.WARNING,
                                 f"Approaching stall threshold ({int(effective_elapsed)}s / {int(self.config.stall_threshold_s)}s)")

        elif effective_elapsed > self.config.idle_threshold_s:
            # Idle
            if health.status == AgentState.WORKING:
                self._transition(health, AgentState.IDLE,
                                 f"No activity for {int(effective_elapsed)}s")

    def _check_git_activity(self, health: WorkerHealth) -> bool:
        """Check if worker has recent git commits (signal 5)."""
        if not health.worktree_path:
            return False
        try:
            result = _sp.run(
                ["git", "log", "--oneline", "--since=2 minutes ago", "-1"],
                cwd=health.worktree_path,
                capture_output=True, text=True, timeout=5,
            )
            return bool(result.stdout.strip())
        except Exception:
            return False

    # ------------------------------------------------------------------
    # W3-3: Resource Monitoring
    # ------------------------------------------------------------------

    def _check_resources(self, health: WorkerHealth) -> dict:
        """Check CPU/memory using psutil (optional)."""
        if health.pid is None:
            return {}
        try:
            import psutil
            proc = psutil.Process(health.pid)
            mem_info = proc.memory_info()
            return {
                "cpu_percent": proc.cpu_percent(interval=0),
                "memory_mb": round(mem_info.rss / (1024 * 1024), 1),
                "memory_percent": round(proc.memory_percent(), 1),
                "open_files": len(proc.open_files()),
            }
        except ImportError:
            # Fallback to /proc/PID/stat on Linux
            return self._check_resources_proc(health.pid)
        except Exception:
            return {}

    @staticmethod
    def _check_resources_proc(pid: int) -> dict:
        """Fallback resource check using /proc filesystem."""
        try:
            stat_path = Path(f"/proc/{pid}/stat")
            if not stat_path.exists():
                return {}
            stat_content = stat_path.read_text().split()
            # Field 23 is RSS in pages
            rss_pages = int(stat_content[23])
            page_size = os.sysconf("SC_PAGE_SIZE")
            memory_mb = round(rss_pages * page_size / (1024 * 1024), 1)
            return {"memory_mb": memory_mb}
        except Exception:
            return {}

    # ------------------------------------------------------------------
    # W1-5: Dependency-Aware Escalation
    # ------------------------------------------------------------------

    async def _escalate_stall(self, health: WorkerHealth, elapsed: float) -> None:
        """Escalate a stalled worker through progressive levels."""
        if health.escalation_level < self.max_escalation:
            health.escalation_level += 1

        level = health.escalation_level
        msg = (
            f"Worker {health.worker_id} stalled: no activity for {int(elapsed)}s "
            f"(escalation level {level})"
        )
        health.warnings.append(msg)

        # Level 1: Nudge
        if level == EscalationLevel.NOTIFY:
            nudge_result = self._nudge_worker(health)
            msg += f" — nudge sent via {nudge_result['method']}"
            self._emit({
                "type": "watchdog_nudge",
                "worker_id": health.worker_id,
                "method": nudge_result["method"],
                "message": nudge_result.get("nudge_message", ""),
                "success": nudge_result["success"],
            })

        # Level 2: AI Triage
        elif level == EscalationLevel.RESTART:
            triage_result = await self._ai_triage_llm(health)
            self._triage_results[health.worker_id] = triage_result
            verdict = triage_result.get("verdict", "extend")

            self._emit({
                "type": "watchdog_triage",
                "worker_id": health.worker_id,
                "verdict": verdict,
                "reasoning": triage_result.get("reasoning", ""),
                "confidence": triage_result.get("confidence", 0),
            })

            if verdict == "terminate":
                health.escalation_level = EscalationLevel.TERMINATE
                level = EscalationLevel.TERMINATE
            elif verdict == "reassign":
                # Reassign tasks and terminate
                await self._reassign_tasks(health)
                health.escalation_level = EscalationLevel.TERMINATE
                level = EscalationLevel.TERMINATE
            elif verdict == "retry":
                nudge_msg = triage_result.get("suggested_nudge_message",
                                              "You appear stuck. Please re-evaluate your approach.")
                self._nudge_worker(health, nudge_msg)
                msg += f" — AI triage: {verdict}"
            else:  # "extend"
                msg += " — AI triage: extend (continuing to monitor)"

        # Level 3: Terminate
        if level >= EscalationLevel.TERMINATE:
            if health.pid:
                self._kill_pid(health.pid)
            self._transition(health, AgentState.TERMINATED,
                             f"Terminated after escalation level {level}")
            self.circuit_breaker.record_failure()

            # Record failure to project expertise
            triage_result = self._triage_results.get(health.worker_id)
            await self._record_failure(health, msg, triage_result)

            # Auto-reassign remaining tasks
            if self.config.auto_reassign:
                await self._reassign_tasks(health)

        # Send escalation mail
        if self.mail_store:
            try:
                from state.mail import MessageType, MessagePriority
                self.mail_store.send(
                    sender="watchdog",
                    recipient="orchestrator",
                    msg_type=MessageType.ESCALATION.value,
                    subject=f"Worker {health.worker_id} stalled",
                    body=msg,
                    priority=MessagePriority.URGENT.value,
                    metadata={
                        "worker_id": health.worker_id,
                        "elapsed_seconds": elapsed,
                        "escalation_level": health.escalation_level,
                    },
                )
            except Exception:
                pass

        event = WatchdogEvent(
            event_type="stalled" if level < EscalationLevel.TERMINATE else "terminated",
            worker_id=health.worker_id,
            message=msg,
            escalation_level=level,
        )
        self._record_event(event)

    def _prioritize_escalation(self, stalled_workers: list[WorkerHealth]) -> list[WorkerHealth]:
        """Order stalled workers by escalation priority:
        1. Workers blocking other workers (task dependencies)
        2. Workers with higher-priority tasks
        3. Workers stalled longest
        4. Workers with most remaining tasks
        """
        def priority_key(health: WorkerHealth) -> tuple:
            # Blocking count (higher = more urgent = lower sort key)
            blocking_count = 0
            try:
                from state.task_list import TaskList
                tl = TaskList(self.project_dir)
                tl.load()
                blocking = get_blocking_tasks(health.assigned_task_ids, tl.tasks)
                blocking_count = len(blocking)
            except Exception:
                pass

            # Stall duration (longer = more urgent = lower sort key)
            stall_duration = time.time() - health.last_output_time

            # Remaining tasks count
            remaining = len([t for t in health.assigned_task_ids
                             if t not in health.completed_task_ids])

            return (-blocking_count, -stall_duration, -remaining)

        return sorted(stalled_workers, key=priority_key)

    # ------------------------------------------------------------------
    # W2-1: True LLM-Based AI Triage
    # ------------------------------------------------------------------

    async def _ai_triage_llm(self, health: WorkerHealth) -> dict:
        """Tier 1: Ephemeral Claude session to analyze stalled worker."""
        if not self.config.ai_triage_enabled:
            return self._ai_triage_heuristic(health)

        context = self._build_triage_context(health)
        prompt = f"""You are a swarm health monitor analyzing a stalled coding worker.

Worker #{health.worker_id} (role: {health.role}) has been stalled for {int(time.time() - health.last_output_time)}s.

Context:
{json.dumps(context, indent=2, default=str)}

Analyze the situation and return a JSON verdict with these fields:
- "verdict": one of "retry" | "terminate" | "extend" | "reassign"
  - retry: worker might recover with a nudge
  - extend: worker is making progress, just slow
  - reassign: redistribute tasks to other workers
  - terminate: kill the worker, it's stuck
- "reasoning": brief explanation (1-2 sentences)
- "recommended_action": what to do next
- "suggested_nudge_message": if verdict is "retry", what to tell the worker
- "tasks_to_reassign": if verdict is "reassign", which task IDs to redistribute
- "confidence": float 0.0-1.0 for how confident you are

Respond with ONLY the JSON object, no markdown fencing."""

        try:
            result = await asyncio.wait_for(
                self._run_triage_query(prompt),
                timeout=self.config.triage_timeout_s,
            )
            return result
        except asyncio.TimeoutError:
            logger.warning(f"AI triage timed out for worker {health.worker_id}")
            return {"verdict": "extend", "confidence": 0.1,
                    "reasoning": "Triage timed out — defaulting to extend"}
        except Exception as e:
            logger.warning(f"AI triage failed for worker {health.worker_id}: {e}")
            return self._ai_triage_heuristic(health)

    async def _run_triage_query(self, prompt: str) -> dict:
        """Run triage query using Claude SDK."""
        try:
            from claude_agent_sdk import ClaudeSDKClient
            from core.models import WORKER_MODEL

            model = self.config.triage_model or WORKER_MODEL
            client = ClaudeSDKClient()
            async with client:
                result = await client.query(
                    prompt,
                    model=model,
                    max_turns=1,
                )
                # Parse response
                text = ""
                if hasattr(result, "text"):
                    text = result.text
                elif hasattr(result, "content"):
                    for block in result.content:
                        if hasattr(block, "text"):
                            text += block.text

                # Try to parse JSON
                text = text.strip()
                if text.startswith("```"):
                    text = text.split("\n", 1)[1].rsplit("```", 1)[0]
                return json.loads(text)
        except Exception as e:
            logger.warning(f"Triage LLM query failed: {e}")
            raise

    def _ai_triage_heuristic(self, health: WorkerHealth) -> dict:
        """Fallback heuristic-based triage (original logic)."""
        recent_output = self.output_buffers.get(health.worker_id, [])
        stall_duration = time.time() - health.last_output_time if health.last_output_time else 0

        has_errors = any("error" in w.lower() for w in health.warnings)
        has_loop = any("loop" in w.lower() or "repeated" in w.lower()
                       for w in health.warnings)
        output_has_progress = any(
            "commit" in l.lower() or "test" in l.lower() or "done" in l.lower()
            for l in recent_output[-5:]
        ) if recent_output else False

        if has_loop and stall_duration > 600:
            return {
                "verdict": "terminate",
                "reasoning": "Worker stuck in detected loop for >10min",
                "recommended_action": "Terminate and reassign tasks",
                "confidence": 0.8,
            }
        elif has_errors and health.escalation_level >= 2:
            return {
                "verdict": "reassign",
                "reasoning": f"Persistent errors after {health.escalation_level} escalations",
                "recommended_action": "Reassign tasks to a fresh worker",
                "tasks_to_reassign": [t for t in health.assigned_task_ids
                                      if t not in health.completed_task_ids],
                "confidence": 0.7,
            }
        elif output_has_progress and stall_duration < 600:
            return {
                "verdict": "extend",
                "reasoning": "Recent output shows progress, may need more time",
                "recommended_action": "Continue monitoring",
                "confidence": 0.6,
            }
        elif stall_duration < 300:
            return {
                "verdict": "retry",
                "reasoning": f"Stalled for {stall_duration:.0f}s, within retry window",
                "recommended_action": "Send nudge and wait",
                "suggested_nudge_message": "You appear stuck. Please re-evaluate your current approach.",
                "confidence": 0.5,
            }
        else:
            return {
                "verdict": "terminate",
                "reasoning": f"No progress for {stall_duration:.0f}s",
                "recommended_action": "Terminate and reassign",
                "confidence": 0.7,
            }

    # ------------------------------------------------------------------
    # W2-2: Triage Context Builder
    # ------------------------------------------------------------------

    def _build_triage_context(self, health: WorkerHealth) -> dict:
        """Gather context from 7 data sources."""
        context: dict[str, Any] = {}

        # 1. Recent output
        recent = self.output_buffers.get(health.worker_id, [])
        context["recent_output"] = "\n".join(
            recent[-self.config.triage_context_lines:]
        ) if recent else "No recent output"

        # 2. Task summary
        try:
            from state.task_list import TaskList
            tl = TaskList(self.project_dir)
            tl.load()
            assigned_tasks = [t for t in tl.tasks if t.id in health.assigned_task_ids]
            context["task_summary"] = [
                {"id": t.id, "title": t.title, "status": t.status}
                for t in assigned_tasks
            ]
        except Exception:
            context["task_summary"] = health.assigned_task_ids

        # 3. Recent mail
        if self.mail_store:
            try:
                msgs = self.mail_store.get_messages(
                    recipient=f"worker-{health.worker_id}", limit=10
                )
                context["recent_mail"] = [
                    {"from": m.sender, "subject": m.subject, "type": m.msg_type}
                    for m in msgs
                ]
            except Exception:
                context["recent_mail"] = []
        else:
            context["recent_mail"] = []

        # 4. Git status
        if health.worktree_path:
            try:
                result = _sp.run(
                    ["git", "status", "--porcelain"],
                    cwd=health.worktree_path,
                    capture_output=True, text=True, timeout=5,
                )
                context["git_status"] = result.stdout[:500] if result.returncode == 0 else ""
            except Exception:
                context["git_status"] = ""

        # 5. Git log
        if health.worktree_path:
            try:
                result = _sp.run(
                    ["git", "log", "--oneline", "-5"],
                    cwd=health.worktree_path,
                    capture_output=True, text=True, timeout=5,
                )
                context["git_log"] = result.stdout[:500] if result.returncode == 0 else ""
            except Exception:
                context["git_log"] = ""

        # 6. Nudge history
        context["nudge_history"] = self.nudge_history.get(health.worker_id, [])

        # 7. Resource usage
        context["resource_usage"] = health.resource_usage

        # Additional context
        context["stall_duration_seconds"] = int(
            time.time() - health.last_output_time
        ) if health.last_output_time else 0
        context["escalation_level"] = health.escalation_level
        context["role"] = health.role

        return context

    # ------------------------------------------------------------------
    # W2-3: Failure Recording
    # ------------------------------------------------------------------

    async def _record_failure(self, health: WorkerHealth, reason: str,
                              triage_result: dict = None) -> None:
        """Record failure to .swarmweaver/expertise/ for future learning."""
        try:
            from features.project_expertise import ProjectExpertise
            expertise = ProjectExpertise(self.project_dir)
            expertise.add(
                content=(
                    f"Worker {health.worker_id} ({health.role}) terminated: {reason}\n"
                    f"Tasks: {health.assigned_task_ids}\n"
                    f"Stall: {int(time.time() - health.last_output_time)}s\n"
                    f"Triage: {triage_result.get('verdict') if triage_result else 'N/A'}"
                ),
                category="failure",
                domain="swarm",
                tags=["watchdog", "auto-recorded", f"role:{health.role}"],
            )
        except Exception:
            pass  # Fire-and-forget

    # ------------------------------------------------------------------
    # W2-4: Auto-Reassignment
    # ------------------------------------------------------------------

    async def _reassign_tasks(self, health: WorkerHealth) -> None:
        """Send TASK_REASSIGNED mail to orchestrator for redistribution."""
        remaining = [t for t in health.assigned_task_ids
                     if t not in health.completed_task_ids]
        if remaining and self.mail_store:
            try:
                from state.mail import MessageType, MessagePriority
                # Use send_protocol if available, otherwise send()
                if hasattr(self.mail_store, "send_protocol"):
                    self.mail_store.send_protocol(
                        sender="watchdog",
                        recipient="orchestrator",
                        msg_type="task_reassigned",
                        subject=f"Worker {health.worker_id} terminated — {len(remaining)} tasks need reassignment",
                        payload={
                            "from_worker": f"worker-{health.worker_id}",
                            "task_ids": remaining,
                            "reason": "worker_terminated",
                            "file_scope": health.file_scope,
                        },
                        priority="urgent",
                    )
                else:
                    self.mail_store.send(
                        sender="watchdog",
                        recipient="orchestrator",
                        msg_type=MessageType.TASK_REASSIGNED.value,
                        subject=f"Worker {health.worker_id} terminated — {len(remaining)} tasks need reassignment",
                        body=f"Tasks: {remaining}",
                        priority=MessagePriority.URGENT.value,
                        metadata={
                            "from_worker": f"worker-{health.worker_id}",
                            "task_ids": remaining,
                            "file_scope": health.file_scope,
                        },
                    )
            except Exception:
                pass

    # ------------------------------------------------------------------
    # W3-1: Run-Level Completion Detection
    # ------------------------------------------------------------------

    async def _check_run_completion(self) -> bool:
        """Detect when all non-persistent workers are done."""
        if not self._auto_run_complete:
            return False
        if self._run_complete_sent:
            return False

        non_persistent = [
            h for h in self.workers.values()
            if h.role not in self.config.persistent_roles
        ]

        if not non_persistent:
            return False

        all_done = all(
            h.status in (AgentState.COMPLETED, AgentState.TERMINATED, AgentState.ZOMBIE)
            for h in non_persistent
        )

        if not all_done:
            return False

        completed = sum(1 for h in non_persistent if h.status == AgentState.COMPLETED)
        failed = sum(1 for h in non_persistent
                     if h.status in (AgentState.TERMINATED, AgentState.ZOMBIE))
        total = len(non_persistent)

        self._run_complete_sent = True

        # Send mail notification
        if self.mail_store:
            try:
                from state.mail import MessageType, MessagePriority
                if hasattr(self.mail_store, "send_protocol"):
                    self.mail_store.send_protocol(
                        sender="watchdog",
                        recipient="orchestrator",
                        msg_type="worker_done",
                        subject=f"Run complete: {completed}/{total} succeeded, {failed} failed",
                        payload={
                            "completed": completed,
                            "failed": failed,
                            "total": total,
                        },
                        priority="high",
                    )
                else:
                    self.mail_store.send(
                        sender="watchdog",
                        recipient="orchestrator",
                        msg_type=MessageType.WORKER_DONE.value,
                        subject=f"Run complete: {completed}/{total}",
                        body=f"Completed: {completed}, Failed: {failed}, Total: {total}",
                    )
            except Exception:
                pass

        # Emit WebSocket event
        self._emit({
            "type": "run_complete",
            "completed": completed,
            "failed": failed,
            "total": total,
        })

        event = WatchdogEvent(
            event_type="run_complete",
            worker_id=-1,
            message=f"Run complete: {completed}/{total} succeeded, {failed} failed",
            metadata={"completed": completed, "failed": failed, "total": total},
        )
        self._record_event(event)

        return True

    # ------------------------------------------------------------------
    # Nudge worker
    # ------------------------------------------------------------------

    def _tmux_nudge(self, health: WorkerHealth, message: str = "") -> bool:
        """Try to nudge a worker via tmux keystroke injection."""
        if not health.pid:
            return False
        try:
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
            return True

        except (FileNotFoundError, _sp.TimeoutExpired):
            return False

    def _nudge_worker(self, health: WorkerHealth, message: str = "") -> dict:
        """Nudge a stalled worker. Returns method used and success status."""
        result = {"method": "none", "success": False, "worker_id": health.worker_id}

        if self._tmux_nudge(health, message):
            result["method"] = "tmux"
            result["success"] = True
            result["nudge_message"] = message
            self._record_nudge(health.worker_id, result, message)
            return result

        if health.worktree_path:
            steering_path = Path(health.worktree_path) / ".claude" / "steering.md"
            try:
                steering_path.parent.mkdir(parents=True, exist_ok=True)
                nudge_msg = message or (
                    f"Watchdog: You have been silent for "
                    f"{int(time.time() - health.last_output_time)}s. "
                    "Please report progress or indicate if you are blocked."
                )
                steering_path.write_text(f"# Nudge\n\n{nudge_msg}\n")
                result["method"] = "steering_file"
                result["success"] = True
                result["nudge_message"] = nudge_msg
            except Exception as e:
                logger.warning(f"Steering file nudge failed for worker {health.worker_id}: {e}")

        self._record_nudge(health.worker_id, result, message)
        health.nudge_count += 1
        health.last_nudge_time = time.time()
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

    # ------------------------------------------------------------------
    # Process management
    # ------------------------------------------------------------------

    @staticmethod
    def _is_pid_alive(pid: int) -> bool:
        """Check if a process with the given PID is still running."""
        try:
            if sys.platform == "win32":
                result = _sp.run(
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
                _sp.run(
                    ["taskkill", "/PID", str(pid), "/F"],
                    capture_output=True, timeout=5,
                )
            else:
                import signal
                os.kill(pid, signal.SIGTERM)
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Event recording & emission
    # ------------------------------------------------------------------

    def _record_event(self, event: WatchdogEvent) -> None:
        """Record event to in-memory list and persistent store."""
        self._events.append(event)
        if self._event_store:
            try:
                self._event_store.record(event)
            except Exception:
                pass

    def _emit(self, data: dict) -> None:
        """Emit event via on_event callback (WebSocket push)."""
        if self._on_event:
            try:
                result = self._on_event(data)
                if asyncio.iscoroutine(result):
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(result)
                    except RuntimeError:
                        pass
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Status getters (backward compatible)
    # ------------------------------------------------------------------

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
            "circuit_breaker": self.circuit_breaker.get_status(),
            "config": self.config.to_dict(),
        }

    def get_events(self, limit: int = 50) -> list[dict]:
        """Get recent watchdog events."""
        if self._event_store:
            try:
                return self._event_store.query(limit=limit)
            except Exception:
                pass
        return [e.to_dict() for e in self._events[-limit:]]

    def get_config(self) -> dict:
        return self.config.to_dict()

    def update_config(self, updates: dict) -> dict:
        """Live-update config values. Returns updated config."""
        for key, value in updates.items():
            if hasattr(self.config, key):
                field_type = type(getattr(self.config, key))
                try:
                    if field_type is set:
                        setattr(self.config, key, set(value) if isinstance(value, list) else value)
                    else:
                        setattr(self.config, key, field_type(value))
                except (ValueError, TypeError):
                    pass
        # Save to disk
        if self.project_dir:
            self.config.save(self.project_dir)
        return self.config.to_dict()

    # ------------------------------------------------------------------
    # Backward compat aliases
    # ------------------------------------------------------------------

    def _ai_triage(self, health: WorkerHealth) -> dict:
        """Backward-compatible synchronous triage (uses heuristic)."""
        return self._ai_triage_heuristic(health)


# ===========================================================================
# Utility: get_blocking_tasks (used by dependency-aware escalation)
# ===========================================================================

def get_blocking_tasks(worker_task_ids: list[str], all_tasks: list) -> list[str]:
    """Return task IDs that depend on the given worker's incomplete tasks.

    If worker A has task T1 and worker B's task T2 depends_on T1,
    then T1 is a "blocking task" — stalling worker A blocks worker B.
    """
    worker_set = set(worker_task_ids)
    blocked_by = []
    for task in all_tasks:
        deps = getattr(task, "depends_on", []) or []
        for dep in deps:
            if dep in worker_set and task.id not in worker_set:
                if dep not in blocked_by:
                    blocked_by.append(dep)
    return blocked_by
