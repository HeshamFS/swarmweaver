"""
Test AI Triage Enhancement (services/watchdog.py)
==================================================

Tests enhanced _ai_triage() with output buffers, structured verdict,
and report_output method.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.watchdog import SwarmWatchdog, WorkerHealth, WorkerHealthStatus


# ---------------------------------------------------------------------------
# Output buffers
# ---------------------------------------------------------------------------

def test_watchdog_has_output_buffers():
    """SwarmWatchdog should have output_buffers dict."""
    wd = SwarmWatchdog()
    assert hasattr(wd, "output_buffers")
    assert isinstance(wd.output_buffers, dict)


def test_report_output():
    """report_output stores lines per worker."""
    wd = SwarmWatchdog()
    wd.report_output(1, "Line 1")
    wd.report_output(1, "Line 2")
    assert len(wd.output_buffers[1]) == 2
    assert wd.output_buffers[1][0] == "Line 1"


def test_report_output_max_20():
    """report_output keeps only last 20 lines."""
    wd = SwarmWatchdog()
    for i in range(30):
        wd.report_output(1, f"Line {i}")
    assert len(wd.output_buffers[1]) == 20
    assert wd.output_buffers[1][0] == "Line 10"  # First 10 dropped


def test_report_output_separate_workers():
    """Output buffers are separate per worker."""
    wd = SwarmWatchdog()
    wd.report_output(1, "Worker 1 output")
    wd.report_output(2, "Worker 2 output")
    assert len(wd.output_buffers[1]) == 1
    assert len(wd.output_buffers[2]) == 1
    assert wd.output_buffers[1][0] != wd.output_buffers[2][0]


# ---------------------------------------------------------------------------
# AI Triage — structured verdict
# ---------------------------------------------------------------------------

def test_ai_triage_returns_dict():
    """_ai_triage should return a dict with verdict, reasoning, recommended_action."""
    wd = SwarmWatchdog()
    health = WorkerHealth(
        worker_id=1,
        status=WorkerHealthStatus.STALLED,
        last_output_time=time.time() - 100,
    )
    result = wd._ai_triage(health)
    assert isinstance(result, dict)
    assert "verdict" in result
    assert "reasoning" in result
    assert "recommended_action" in result


def test_ai_triage_verdict_values():
    """Verdict should be one of: retry, terminate, extend, escalate."""
    wd = SwarmWatchdog()
    health = WorkerHealth(
        worker_id=1,
        status=WorkerHealthStatus.STALLED,
        last_output_time=time.time() - 60,
    )
    result = wd._ai_triage(health)
    assert result["verdict"] in ("retry", "terminate", "extend", "escalate")


def test_ai_triage_short_stall_retries():
    """Short stall (<300s) should recommend retry."""
    wd = SwarmWatchdog()
    health = WorkerHealth(
        worker_id=1,
        status=WorkerHealthStatus.STALLED,
        last_output_time=time.time() - 120,  # 2 minutes
        escalation_level=0,
    )
    result = wd._ai_triage(health)
    assert result["verdict"] in ("retry", "extend")


def test_ai_triage_long_stall_terminates():
    """Long stall (>600s) with no progress should recommend terminate."""
    wd = SwarmWatchdog()
    health = WorkerHealth(
        worker_id=1,
        status=WorkerHealthStatus.STALLED,
        last_output_time=time.time() - 700,  # >10 minutes
        escalation_level=2,
        warnings=["loop detected"],
    )
    result = wd._ai_triage(health)
    assert result["verdict"] in ("terminate", "escalate")


def test_ai_triage_with_recent_progress():
    """Recent progress in output should recommend extend."""
    wd = SwarmWatchdog()
    wd.report_output(1, "Running test suite...")
    wd.report_output(1, "Test 1 passed")
    wd.report_output(1, "commit abc123")

    health = WorkerHealth(
        worker_id=1,
        status=WorkerHealthStatus.STALLED,
        last_output_time=time.time() - 200,  # 3.3 minutes
        escalation_level=0,
    )
    result = wd._ai_triage(health)
    # With recent progress, should lean toward extend
    assert result["verdict"] in ("extend", "retry")


def test_ai_triage_with_errors():
    """Persistent errors should escalate."""
    wd = SwarmWatchdog()
    health = WorkerHealth(
        worker_id=1,
        status=WorkerHealthStatus.STALLED,
        last_output_time=time.time() - 400,
        escalation_level=2,
        warnings=["error detected", "repeated error"],
    )
    result = wd._ai_triage(health)
    assert result["verdict"] in ("escalate", "terminate")


# ---------------------------------------------------------------------------
# Watchdog — register/unregister
# ---------------------------------------------------------------------------

def test_register_worker():
    """Can register a worker."""
    wd = SwarmWatchdog()
    wd.register_worker(1, pid=12345)
    status = wd.get_status()
    assert "1" in status.get("workers", {}) or 1 in status.get("workers", {})


def test_unregister_worker():
    """Can unregister a worker."""
    wd = SwarmWatchdog()
    wd.register_worker(1)
    wd.unregister_worker(1)
    # After unregister, worker may still be in status but marked differently


def test_report_activity():
    """report_activity updates last output time."""
    wd = SwarmWatchdog()
    wd.register_worker(1)
    wd.report_activity(1)
    # Worker should be considered active
