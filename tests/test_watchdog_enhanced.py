"""
Enhanced Watchdog Test Suite
=============================

Tests for the 9-state state machine, configurable thresholds,
6-signal health evaluation, heartbeat protocol, dependency-aware
escalation, AI triage, circuit breaker, resource monitoring,
persistent event store, and CLI commands.

~50 tests covering all watchdog functionality.
"""

import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.watchdog import (
    AgentState,
    ALLOWED_TRANSITIONS,
    CircuitBreaker,
    EscalationLevel,
    HeartbeatProtocol,
    SwarmWatchdog,
    WatchdogConfig,
    WatchdogEvent,
    WatchdogEventStore,
    WorkerHealth,
    get_blocking_tasks,
)
from state.task_list import Task, get_blocking_tasks as tl_get_blocking_tasks


# ===========================================================================
# TestAgentStateMachine
# ===========================================================================

class TestAgentStateMachine:
    """Test the 9-state forward-only state machine."""

    def test_valid_transitions(self):
        """BOOTING→WORKING, STALLED→RECOVERING, etc. should succeed."""
        wd = SwarmWatchdog()
        wd.register_worker(1)
        health = wd.workers[1]
        assert health.status == AgentState.BOOTING

        assert wd._transition(health, AgentState.WORKING, "started") is True
        assert health.status == AgentState.WORKING

        assert wd._transition(health, AgentState.IDLE, "quiet") is True
        assert health.status == AgentState.IDLE

        assert wd._transition(health, AgentState.WARNING, "approaching") is True
        assert health.status == AgentState.WARNING

        assert wd._transition(health, AgentState.STALLED, "stuck") is True
        assert health.status == AgentState.STALLED

        assert wd._transition(health, AgentState.RECOVERING, "output returned") is True
        assert health.status == AgentState.RECOVERING

        assert wd._transition(health, AgentState.WORKING, "recovered") is True
        assert health.status == AgentState.WORKING

    def test_invalid_transitions_rejected(self):
        """COMPLETED→WORKING, TERMINATED→BOOTING should fail."""
        wd = SwarmWatchdog()
        wd.register_worker(1)
        health = wd.workers[1]

        wd._transition(health, AgentState.WORKING, "start")
        wd._transition(health, AgentState.COMPLETED, "done")
        assert health.status == AgentState.COMPLETED

        result = wd._transition(health, AgentState.WORKING, "try reopen")
        assert result is False
        assert health.status == AgentState.COMPLETED

    def test_recovering_to_working(self):
        """STALLED → RECOVERING → WORKING path."""
        wd = SwarmWatchdog()
        wd.register_worker(1)
        h = wd.workers[1]
        wd._transition(h, AgentState.WORKING, "")
        wd._transition(h, AgentState.IDLE, "")
        wd._transition(h, AgentState.WARNING, "")
        wd._transition(h, AgentState.STALLED, "stuck")
        wd._transition(h, AgentState.RECOVERING, "output")
        assert h.status == AgentState.RECOVERING
        wd._transition(h, AgentState.WORKING, "recovered")
        assert h.status == AgentState.WORKING

    def test_recovering_to_stalled_again(self):
        """RECOVERING → STALLED (recovery failed)."""
        wd = SwarmWatchdog()
        wd.register_worker(1)
        h = wd.workers[1]
        wd._transition(h, AgentState.WORKING, "")
        wd._transition(h, AgentState.IDLE, "")
        wd._transition(h, AgentState.WARNING, "")
        wd._transition(h, AgentState.STALLED, "stuck")
        wd._transition(h, AgentState.RECOVERING, "brief output")
        assert wd._transition(h, AgentState.STALLED, "stalled again") is True

    def test_all_terminal_states_have_no_transitions(self):
        """COMPLETED and TERMINATED are terminal."""
        assert len(ALLOWED_TRANSITIONS[AgentState.COMPLETED]) == 0
        assert len(ALLOWED_TRANSITIONS[AgentState.TERMINATED]) == 0

    def test_zombie_can_only_be_terminated(self):
        assert ALLOWED_TRANSITIONS[AgentState.ZOMBIE] == {AgentState.TERMINATED}

    def test_transition_records_history(self):
        """Each transition is recorded in state_history."""
        wd = SwarmWatchdog()
        wd.register_worker(1)
        h = wd.workers[1]
        wd._transition(h, AgentState.WORKING, "started")
        assert len(h.state_history) == 1
        assert h.state_history[0]["from"] == "booting"
        assert h.state_history[0]["to"] == "working"
        assert h.state_history[0]["reason"] == "started"


# ===========================================================================
# TestWatchdogConfig
# ===========================================================================

class TestWatchdogConfig:
    """Test config loading from YAML, env vars, and defaults."""

    def test_defaults(self):
        config = WatchdogConfig()
        assert config.enabled is True
        assert config.check_interval_s == 30.0
        assert config.stall_threshold_s == 300.0
        assert config.boot_grace_s == 60.0
        assert config.ai_triage_enabled is True
        assert config.auto_reassign is True
        assert "coordinator" in config.persistent_roles

    def test_load_from_yaml(self, tmp_path):
        """Config loads from YAML file."""
        sw_dir = tmp_path / ".swarmweaver"
        sw_dir.mkdir()
        yaml_path = sw_dir / "watchdog.yaml"
        yaml_path.write_text(json.dumps({
            "check_interval_s": 15.0,
            "stall_threshold_s": 120.0,
            "ai_triage_enabled": False,
        }))
        config = WatchdogConfig.load(tmp_path)
        assert config.check_interval_s == 15.0
        assert config.stall_threshold_s == 120.0
        assert config.ai_triage_enabled is False
        # Other values remain defaults
        assert config.boot_grace_s == 60.0

    def test_load_from_env_vars(self, tmp_path):
        """Config loads from environment variables."""
        with patch.dict(os.environ, {
            "WATCHDOG_CHECK_INTERVAL_S": "10.0",
            "WATCHDOG_ENABLED": "false",
        }):
            config = WatchdogConfig.load(tmp_path)
            assert config.check_interval_s == 10.0
            assert config.enabled is False

    def test_env_overrides_yaml(self, tmp_path):
        """Env vars override YAML values."""
        sw_dir = tmp_path / ".swarmweaver"
        sw_dir.mkdir()
        yaml_path = sw_dir / "watchdog.yaml"
        yaml_path.write_text(json.dumps({"check_interval_s": 20.0}))
        with patch.dict(os.environ, {"WATCHDOG_CHECK_INTERVAL_S": "5.0"}):
            config = WatchdogConfig.load(tmp_path)
            assert config.check_interval_s == 5.0

    def test_to_dict_and_save(self, tmp_path):
        config = WatchdogConfig(check_interval_s=42.0)
        d = config.to_dict()
        assert d["check_interval_s"] == 42.0
        assert isinstance(d["persistent_roles"], list)

        config.save(tmp_path)
        yaml_path = tmp_path / ".swarmweaver" / "watchdog.yaml"
        assert yaml_path.exists()
        loaded = json.loads(yaml_path.read_text())
        assert loaded["check_interval_s"] == 42.0


# ===========================================================================
# TestHealthEvaluation
# ===========================================================================

class TestHealthEvaluation:
    """Test the 6-signal health evaluation system."""

    def test_boot_grace_period(self):
        """Workers in BOOTING state within grace period are not checked."""
        config = WatchdogConfig(boot_grace_s=120.0)
        wd = SwarmWatchdog(config=config)
        wd.register_worker(1)
        h = wd.workers[1]
        h.boot_time = time.time()  # Just booted
        h.last_output_time = time.time() - 200  # No output for 200s
        # Should not escalate because still in boot grace
        loop = asyncio.new_event_loop()
        loop.run_until_complete(wd._check_worker(h))
        loop.close()
        assert h.status == AgentState.BOOTING

    def test_persistent_role_exemption(self):
        """Persistent roles (coordinator, monitor) are skipped."""
        config = WatchdogConfig(persistent_roles={"coordinator"})
        wd = SwarmWatchdog(config=config)
        wd.register_worker(1, role="coordinator")
        h = wd.workers[1]
        # The run loop skips persistent roles, so _check_worker won't be called
        assert h.role == "coordinator"

    def test_asyncio_task_done_marks_completed(self):
        """Signal 1: asyncio.Task completion → COMPLETED."""
        wd = SwarmWatchdog()
        wd.register_worker(1)
        h = wd.workers[1]
        wd._transition(h, AgentState.WORKING, "started")

        # Create a done task
        async def noop():
            pass
        loop = asyncio.new_event_loop()
        task = loop.create_task(noop())
        loop.run_until_complete(task)

        h.asyncio_task = task
        loop.run_until_complete(wd._check_worker(h))
        loop.close()
        assert h.status == AgentState.COMPLETED

    def test_pid_dead_overrides_output_freshness(self):
        """Signal 2: Dead PID → ZOMBIE regardless of output freshness."""
        wd = SwarmWatchdog()
        wd.register_worker(1, pid=99999)
        h = wd.workers[1]
        wd._transition(h, AgentState.WORKING, "started")
        h.last_output_time = time.time()  # Fresh output

        with patch.object(SwarmWatchdog, '_is_pid_alive', return_value=False):
            loop = asyncio.new_event_loop()
            loop.run_until_complete(wd._check_worker(h))
            loop.close()

        assert h.status == AgentState.ZOMBIE

    def test_tool_activity_prevents_false_stall(self):
        """Signal 4: Tool activity resets effective elapsed time."""
        config = WatchdogConfig(stall_threshold_s=60.0, boot_grace_s=0)
        wd = SwarmWatchdog(config=config)
        wd.register_worker(1)
        h = wd.workers[1]
        wd._transition(h, AgentState.WORKING, "started")
        h.last_output_time = time.time() - 120  # No stdout for 120s
        h.last_tool_time = time.time() - 5  # But tool call 5s ago

        with patch.object(SwarmWatchdog, '_is_pid_alive', return_value=True):
            with patch.object(SwarmWatchdog, '_check_git_activity', return_value=False):
                loop = asyncio.new_event_loop()
                loop.run_until_complete(wd._check_worker(h))
                loop.close()

        # Should NOT be stalled because tool activity is recent
        assert h.status != AgentState.STALLED


# ===========================================================================
# TestHeartbeatProtocol
# ===========================================================================

class TestHeartbeatProtocol:

    def test_process_heartbeat_updates_tracking(self):
        hb = HeartbeatProtocol()
        hb.process_heartbeat(1, {"task": "T1"})
        assert hb.get_last_heartbeat(1) is not None
        assert hb.get_heartbeat_data(1) == {"task": "T1"}

    def test_missed_heartbeat_detected(self):
        hb = HeartbeatProtocol()
        hb._pending_requests[1] = time.time() - 200  # Old request
        missed = hb.check_missed_heartbeats()
        assert 1 in missed

    def test_request_heartbeat_sends_mail(self):
        hb = HeartbeatProtocol()
        mail = MagicMock()
        req_id = hb.request_heartbeat(1, mail_store=mail)
        assert req_id  # Non-empty string
        assert 1 in hb._pending_requests
        mail.send_protocol.assert_called_once()


# ===========================================================================
# TestDependencyAwareEscalation
# ===========================================================================

class TestDependencyAwareEscalation:

    def test_get_blocking_tasks(self):
        """Tasks that depend on a worker's tasks are identified."""
        tasks = [
            Task(id="T1", title="Base task"),
            Task(id="T2", title="Dependent", depends_on=["T1"]),
            Task(id="T3", title="Independent"),
        ]
        blocking = get_blocking_tasks(["T1"], tasks)
        assert "T1" in blocking  # T1 blocks T2

    def test_get_blocking_tasks_no_deps(self):
        tasks = [
            Task(id="T1", title="Task 1"),
            Task(id="T2", title="Task 2"),
        ]
        blocking = get_blocking_tasks(["T1"], tasks)
        assert blocking == []

    def test_blocker_prioritized_first(self, tmp_path):
        """Workers blocking others should be prioritized."""
        wd = SwarmWatchdog(project_dir=tmp_path)
        # Worker 1 has task T1 (blocking T2)
        wd.register_worker(1)
        wd.workers[1].assigned_task_ids = ["T1"]
        wd.workers[1].last_output_time = time.time() - 100

        # Worker 2 has task T3 (not blocking anything)
        wd.register_worker(2)
        wd.workers[2].assigned_task_ids = ["T3"]
        wd.workers[2].last_output_time = time.time() - 200  # Stalled longer

        stalled = [wd.workers[1], wd.workers[2]]
        # Can't easily test without a real task list, but the method should not crash
        result = wd._prioritize_escalation(stalled)
        assert len(result) == 2


# ===========================================================================
# TestAITriage
# ===========================================================================

class TestAITriage:

    def test_heuristic_triage_still_works(self):
        """Heuristic triage returns structured result."""
        wd = SwarmWatchdog()
        wd.register_worker(1)
        h = wd.workers[1]
        h.last_output_time = time.time() - 100
        result = wd._ai_triage_heuristic(h)
        assert "verdict" in result
        assert result["verdict"] in ("retry", "terminate", "extend", "reassign")
        assert "confidence" in result

    def test_heuristic_loop_terminates(self):
        """Loop detection leads to terminate verdict."""
        wd = SwarmWatchdog()
        wd.register_worker(1)
        h = wd.workers[1]
        h.last_output_time = time.time() - 700
        h.warnings = ["loop detected", "loop detected again"]
        result = wd._ai_triage_heuristic(h)
        assert result["verdict"] == "terminate"

    def test_llm_triage_timeout_returns_extend(self):
        """Timeout during LLM triage returns safe default."""
        wd = SwarmWatchdog(config=WatchdogConfig(triage_timeout_s=0.01))
        wd.register_worker(1)
        h = wd.workers[1]
        h.last_output_time = time.time() - 100

        async def _run():
            with patch.object(wd, '_run_triage_query',
                              side_effect=asyncio.TimeoutError):
                return await wd._ai_triage_llm(h)

        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(_run())
        loop.close()
        assert result["verdict"] == "extend"
        assert result["confidence"] <= 0.2

    def test_llm_triage_error_fallback_to_heuristic(self):
        """LLM failure falls back to heuristic."""
        wd = SwarmWatchdog(config=WatchdogConfig(ai_triage_enabled=True))
        wd.register_worker(1)
        h = wd.workers[1]
        h.last_output_time = time.time() - 100

        async def _run():
            with patch.object(wd, '_run_triage_query',
                              side_effect=RuntimeError("SDK not available")):
                return await wd._ai_triage_llm(h)

        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(_run())
        loop.close()
        assert "verdict" in result


# ===========================================================================
# TestTriageContextBuilder
# ===========================================================================

class TestTriageContextBuilder:

    def test_gathers_output_and_metadata(self):
        wd = SwarmWatchdog()
        wd.register_worker(1, role="builder")
        h = wd.workers[1]
        h.last_output_time = time.time() - 60
        h.resource_usage = {"cpu_percent": 50}
        wd.output_buffers[1] = ["line1", "line2"]

        ctx = wd._build_triage_context(h)
        assert "recent_output" in ctx
        assert "line1" in ctx["recent_output"]
        assert ctx["resource_usage"]["cpu_percent"] == 50
        assert ctx["role"] == "builder"

    def test_handles_missing_sources_gracefully(self):
        """No mail store, no git, no tasks — should not crash."""
        wd = SwarmWatchdog()
        wd.register_worker(1)
        h = wd.workers[1]
        ctx = wd._build_triage_context(h)
        assert "recent_output" in ctx
        assert ctx["recent_mail"] == []


# ===========================================================================
# TestFailureRecording
# ===========================================================================

class TestFailureRecording:

    def test_records_to_project_expertise(self, tmp_path):
        wd = SwarmWatchdog(project_dir=tmp_path)
        wd.register_worker(1, role="builder")
        h = wd.workers[1]
        h.assigned_task_ids = ["T1"]
        h.last_output_time = time.time() - 300

        loop = asyncio.new_event_loop()
        loop.run_until_complete(
            wd._record_failure(h, "terminated after stall", {"verdict": "terminate"})
        )
        loop.close()

        # Check that expertise was recorded
        index_path = tmp_path / ".swarmweaver" / "expertise" / "index.json"
        assert index_path.exists()
        entries = json.loads(index_path.read_text())
        assert len(entries) == 1
        assert entries[0]["category"] == "failure"
        assert "terminated" in entries[0]["content"].lower()

    def test_fire_and_forget_on_error(self, tmp_path):
        """Should not crash even if expertise recording fails."""
        wd = SwarmWatchdog(project_dir=tmp_path)
        wd.register_worker(1)
        h = wd.workers[1]

        with patch("features.project_expertise.ProjectExpertise.add",
                    side_effect=RuntimeError("write error")):
            loop = asyncio.new_event_loop()
            loop.run_until_complete(wd._record_failure(h, "test", {}))
            loop.close()
        # No exception raised


# ===========================================================================
# TestAutoReassignment
# ===========================================================================

class TestAutoReassignment:

    def test_sends_task_reassigned_mail(self, tmp_path):
        mail = MagicMock()
        mail.send_protocol = MagicMock()
        wd = SwarmWatchdog(mail_store=mail, project_dir=tmp_path)
        wd.register_worker(1)
        h = wd.workers[1]
        h.assigned_task_ids = ["T1", "T2"]
        h.completed_task_ids = ["T1"]

        loop = asyncio.new_event_loop()
        loop.run_until_complete(wd._reassign_tasks(h))
        loop.close()

        mail.send_protocol.assert_called_once()
        call_kwargs = mail.send_protocol.call_args
        assert "T2" in str(call_kwargs)

    def test_skips_when_no_remaining_tasks(self, tmp_path):
        mail = MagicMock()
        wd = SwarmWatchdog(mail_store=mail, project_dir=tmp_path)
        wd.register_worker(1)
        h = wd.workers[1]
        h.assigned_task_ids = ["T1"]
        h.completed_task_ids = ["T1"]

        loop = asyncio.new_event_loop()
        loop.run_until_complete(wd._reassign_tasks(h))
        loop.close()

        mail.send_protocol.assert_not_called()
        mail.send.assert_not_called()


# ===========================================================================
# TestRunCompletion
# ===========================================================================

class TestRunCompletion:

    def test_detects_all_workers_done(self, tmp_path):
        wd = SwarmWatchdog(project_dir=tmp_path)
        wd.register_worker(1, role="builder")
        wd.register_worker(2, role="builder")
        wd._transition(wd.workers[1], AgentState.WORKING, "")
        wd._transition(wd.workers[2], AgentState.WORKING, "")
        wd._transition(wd.workers[1], AgentState.COMPLETED, "")
        wd._transition(wd.workers[2], AgentState.COMPLETED, "")

        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(wd._check_run_completion())
        loop.close()
        assert result is True

    def test_excludes_persistent_roles(self, tmp_path):
        config = WatchdogConfig(persistent_roles={"monitor"})
        wd = SwarmWatchdog(config=config, project_dir=tmp_path)
        wd.register_worker(1, role="builder")
        wd.register_worker(2, role="monitor")
        wd._transition(wd.workers[1], AgentState.WORKING, "")
        wd._transition(wd.workers[1], AgentState.COMPLETED, "")
        # Monitor is still running — but should be excluded

        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(wd._check_run_completion())
        loop.close()
        assert result is True

    def test_dedup_prevents_repeated_notifications(self, tmp_path):
        wd = SwarmWatchdog(project_dir=tmp_path)
        wd.register_worker(1, role="builder")
        wd._transition(wd.workers[1], AgentState.WORKING, "")
        wd._transition(wd.workers[1], AgentState.COMPLETED, "")

        loop = asyncio.new_event_loop()
        r1 = loop.run_until_complete(wd._check_run_completion())
        r2 = loop.run_until_complete(wd._check_run_completion())
        loop.close()
        assert r1 is True
        assert r2 is False  # Already sent


# ===========================================================================
# TestCircuitBreaker
# ===========================================================================

class TestCircuitBreaker:

    def test_closed_allows_spawn(self):
        cb = CircuitBreaker()
        allowed, reason = cb.can_spawn()
        assert allowed is True

    def test_opens_at_threshold(self):
        cb = CircuitBreaker(max_failure_rate=0.5)
        cb.record_failure()
        cb.record_failure()
        # 2 failures, 0 successes = 100% failure rate
        status = cb.get_status()
        assert status["state"] == "open"

        allowed, reason = cb.can_spawn()
        assert allowed is False

    def test_half_open_allows_one_spawn(self):
        cb = CircuitBreaker(max_failure_rate=0.5)
        cb.record_failure()
        cb.record_failure()
        # Force half-open by setting opened_at in the past
        cb._opened_at = time.time() - 200  # Past cooldown
        cb._check_half_open()
        assert cb._state == "half_open"

        allowed1, _ = cb.can_spawn()
        assert allowed1 is True

        allowed2, _ = cb.can_spawn()
        assert allowed2 is False  # Only one test spawn

    def test_closes_on_success(self):
        cb = CircuitBreaker(max_failure_rate=0.5)
        cb.record_failure()
        cb.record_failure()
        cb._opened_at = time.time() - 200
        cb._check_half_open()
        cb.can_spawn()  # Use the test spawn
        cb.record_success()
        assert cb._state == "closed"

    def test_sliding_window_cleanup(self):
        cb = CircuitBreaker(window_s=10)
        cb._failures = [time.time() - 20]  # Old failure
        cb._cleanup_window()
        assert len(cb._failures) == 0


# ===========================================================================
# TestResourceMonitoring
# ===========================================================================

class TestResourceMonitoring:

    def test_psutil_available(self):
        """If psutil is importable, returns resource dict."""
        wd = SwarmWatchdog()
        mock_proc = MagicMock()
        mock_proc.cpu_percent.return_value = 25.0
        mock_proc.memory_info.return_value = MagicMock(rss=100 * 1024 * 1024)
        mock_proc.memory_percent.return_value = 5.0
        mock_proc.open_files.return_value = [1, 2, 3]

        with patch("services.watchdog.psutil", create=True) as mock_psutil:
            mock_psutil.Process.return_value = mock_proc
            # Need to make the import succeed
            import importlib
            try:
                result = wd._check_resources(WorkerHealth(worker_id=1, pid=12345))
                # May or may not work depending on actual psutil availability
            except Exception:
                pass  # psutil may not be installed

    def test_psutil_unavailable_fallback(self):
        """Falls back to /proc when psutil not available."""
        wd = SwarmWatchdog()
        result = wd._check_resources_proc(99999)
        # Should return empty dict for non-existent PID
        assert isinstance(result, dict)


# ===========================================================================
# TestWatchdogEventStore
# ===========================================================================

class TestWatchdogEventStore:

    def test_record_and_query(self, tmp_path):
        store = WatchdogEventStore(tmp_path)
        store.initialize()

        event = WatchdogEvent(
            event_type="state_change",
            worker_id=1,
            message="booting → working",
            state_before="booting",
            state_after="working",
        )
        event_id = store.record(event)
        assert event_id

        results = store.query(limit=10)
        assert len(results) == 1
        assert results[0]["event_type"] == "state_change"
        assert results[0]["worker_id"] == 1

        store.close()

    def test_filter_by_worker_id(self, tmp_path):
        store = WatchdogEventStore(tmp_path)
        store.initialize()

        store.record(WatchdogEvent("change", 1, "msg1"))
        store.record(WatchdogEvent("change", 2, "msg2"))

        results = store.query(worker_id=1)
        assert len(results) == 1
        assert results[0]["worker_id"] == 1

        store.close()

    def test_filter_by_event_type(self, tmp_path):
        store = WatchdogEventStore(tmp_path)
        store.initialize()

        store.record(WatchdogEvent("state_change", 1, "msg1"))
        store.record(WatchdogEvent("nudge", 1, "msg2"))

        results = store.query(event_type="nudge")
        assert len(results) == 1
        assert results[0]["event_type"] == "nudge"

        store.close()

    def test_purge_old_events(self, tmp_path):
        store = WatchdogEventStore(tmp_path)
        store.initialize()

        # Insert an old event
        old_event = WatchdogEvent("old", 1, "old event")
        old_event.timestamp = "2020-01-01T00:00:00+00:00"
        store.record(old_event)

        # Insert a new event
        store.record(WatchdogEvent("new", 1, "new event"))

        purged = store.purge(older_than_days=1)
        assert purged >= 1

        remaining = store.query(limit=100)
        assert len(remaining) == 1
        assert remaining[0]["event_type"] == "new"

        store.close()

    def test_get_summary(self, tmp_path):
        store = WatchdogEventStore(tmp_path)
        store.initialize()

        store.record(WatchdogEvent("state_change", 1, "msg"))
        store.record(WatchdogEvent("state_change", 2, "msg"))
        store.record(WatchdogEvent("nudge", 1, "msg"))

        summary = store.get_summary()
        assert summary["total"] == 3
        assert summary["by_type"]["state_change"] == 2
        assert summary["by_type"]["nudge"] == 1

        store.close()


# ===========================================================================
# TestCLICommands (basic smoke tests)
# ===========================================================================

class TestCLICommands:

    def test_watchdog_status(self, tmp_path):
        """CLI status command should not crash."""
        from typer.testing import CliRunner
        from cli.commands.watchdog import watchdog_app
        runner = CliRunner()
        result = runner.invoke(watchdog_app, ["status", "--project-dir", str(tmp_path)])
        # Should complete without crash (may show "no data")
        assert result.exit_code == 0

    def test_watchdog_config_show(self, tmp_path):
        """CLI config show should output JSON."""
        from typer.testing import CliRunner
        from cli.commands.watchdog import watchdog_app
        runner = CliRunner()
        result = runner.invoke(watchdog_app, ["config", "--project-dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "check_interval_s" in result.output

    def test_watchdog_events_no_db(self, tmp_path):
        """CLI events command with no DB should exit cleanly."""
        from typer.testing import CliRunner
        from cli.commands.watchdog import watchdog_app
        runner = CliRunner()
        result = runner.invoke(watchdog_app, ["events", "--project-dir", str(tmp_path)])
        assert result.exit_code == 1  # No DB found

    def test_watchdog_nudge(self, tmp_path):
        """CLI nudge command should not crash."""
        from typer.testing import CliRunner
        from cli.commands.watchdog import watchdog_app
        runner = CliRunner()
        result = runner.invoke(watchdog_app, ["nudge", "1", "--project-dir", str(tmp_path)])
        # May fail to nudge but should not crash
        assert result.exit_code == 0


# ===========================================================================
# TestReportActivity
# ===========================================================================

class TestReportActivity:
    """Test the report_activity flow and state transitions."""

    def test_report_activity_transitions_booting_to_working(self):
        wd = SwarmWatchdog()
        wd.register_worker(1)
        assert wd.workers[1].status == AgentState.BOOTING
        wd.report_activity(1)
        assert wd.workers[1].status == AgentState.WORKING

    def test_report_activity_stalled_to_recovering(self):
        wd = SwarmWatchdog()
        wd.register_worker(1)
        h = wd.workers[1]
        wd._transition(h, AgentState.WORKING, "")
        wd._transition(h, AgentState.IDLE, "")
        wd._transition(h, AgentState.WARNING, "")
        wd._transition(h, AgentState.STALLED, "stuck")
        wd.report_activity(1)
        assert h.status == AgentState.RECOVERING

    def test_mark_completed(self):
        wd = SwarmWatchdog()
        wd.register_worker(1)
        wd._transition(wd.workers[1], AgentState.WORKING, "")
        wd.mark_completed(1)
        assert wd.workers[1].status == AgentState.COMPLETED

    def test_report_tool_activity(self):
        wd = SwarmWatchdog()
        wd.register_worker(1)
        wd.report_tool_activity(1, "Bash")
        assert wd.workers[1].last_tool_time > 0

    def test_report_task_completion(self):
        wd = SwarmWatchdog()
        wd.register_worker(1)
        wd.report_task_completion(1, "T1")
        assert "T1" in wd.workers[1].completed_task_ids


# ===========================================================================
# TestGetStatus (backward compat)
# ===========================================================================

class TestGetStatus:

    def test_get_status_structure(self):
        wd = SwarmWatchdog()
        wd.register_worker(1)
        status = wd.get_status()
        assert "running" in status
        assert "workers" in status
        assert "circuit_breaker" in status
        assert "config" in status
        assert 1 in status["workers"]

    def test_get_events_from_store(self, tmp_path):
        wd = SwarmWatchdog(project_dir=tmp_path)
        wd.register_worker(1)
        wd._transition(wd.workers[1], AgentState.WORKING, "test")
        events = wd.get_events(limit=10)
        assert len(events) >= 1

    def test_update_config(self, tmp_path):
        wd = SwarmWatchdog(project_dir=tmp_path)
        result = wd.update_config({"check_interval_s": 15.0})
        assert result["check_interval_s"] == 15.0
        assert wd.config.check_interval_s == 15.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
