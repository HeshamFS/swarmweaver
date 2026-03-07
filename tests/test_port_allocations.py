"""
Port Allocations Tests
======================

Tests for state.port_allocations: allocate_ports_for_worker, get_worker_ports,
release_ports_for_worker.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.paths import get_paths
from state.port_allocations import (
    allocate_ports_for_worker,
    get_worker_ports,
    release_ports_for_worker,
    BACKEND_BASE,
    FRONTEND_BASE,
)


def test_allocate_ports_for_worker_returns_backend_and_frontend(tmp_path):
    """allocate_ports_for_worker returns backend and frontend in valid ranges."""
    paths = get_paths(tmp_path)
    paths.swarm_dir.mkdir(parents=True, exist_ok=True)

    result = allocate_ports_for_worker(tmp_path, 1)

    assert "backend" in result
    assert "frontend" in result
    assert BACKEND_BASE <= result["backend"] < BACKEND_BASE + 90
    assert FRONTEND_BASE <= result["frontend"] < FRONTEND_BASE + 90


def test_allocate_ports_for_worker_idempotent(tmp_path):
    """Same worker_id returns same ports on second call."""
    paths = get_paths(tmp_path)
    paths.swarm_dir.mkdir(parents=True, exist_ok=True)

    r1 = allocate_ports_for_worker(tmp_path, 1)
    r2 = allocate_ports_for_worker(tmp_path, 1)

    assert r1["backend"] == r2["backend"]
    assert r1["frontend"] == r2["frontend"]


def test_allocate_ports_for_different_workers_differ(tmp_path):
    """Different workers get different ports."""
    paths = get_paths(tmp_path)
    paths.swarm_dir.mkdir(parents=True, exist_ok=True)

    r1 = allocate_ports_for_worker(tmp_path, 1)
    r2 = allocate_ports_for_worker(tmp_path, 2)

    assert r1["backend"] != r2["backend"] or r1["frontend"] != r2["frontend"]


def test_get_worker_ports_returns_none_when_not_allocated(tmp_path):
    """get_worker_ports returns None for worker with no allocation."""
    paths = get_paths(tmp_path)
    paths.swarm_dir.mkdir(parents=True, exist_ok=True)

    result = get_worker_ports(tmp_path, 99)
    assert result is None


def test_get_worker_ports_returns_allocated(tmp_path):
    """get_worker_ports returns allocated ports."""
    paths = get_paths(tmp_path)
    paths.swarm_dir.mkdir(parents=True, exist_ok=True)

    allocated = allocate_ports_for_worker(tmp_path, 1)
    result = get_worker_ports(tmp_path, 1)

    assert result is not None
    assert result["backend"] == allocated["backend"]
    assert result["frontend"] == allocated["frontend"]


def test_release_ports_for_worker_removes_allocation(tmp_path):
    """release_ports_for_worker removes entry; next allocate can reuse."""
    paths = get_paths(tmp_path)
    paths.swarm_dir.mkdir(parents=True, exist_ok=True)

    r1 = allocate_ports_for_worker(tmp_path, 1)
    release_ports_for_worker(tmp_path, 1)
    assert get_worker_ports(tmp_path, 1) is None

    r2 = allocate_ports_for_worker(tmp_path, 2)
    # Worker 2 should get ports; worker 1's ports may be reused
    assert r2["backend"] >= BACKEND_BASE
    assert r2["frontend"] >= FRONTEND_BASE


def test_port_allocations_persisted(tmp_path):
    """Allocations are persisted to port_allocations.json."""
    paths = get_paths(tmp_path)
    paths.swarm_dir.mkdir(parents=True, exist_ok=True)

    allocate_ports_for_worker(tmp_path, 1)

    path = paths.port_allocations
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "workers" in data
    assert "1" in data["workers"]
    assert data["workers"]["1"]["backend"] >= BACKEND_BASE
    assert data["workers"]["1"]["frontend"] >= FRONTEND_BASE
