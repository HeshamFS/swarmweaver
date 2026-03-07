"""
Port Allocation for Swarm Workers
================================

Manages per-worker port assignment (backend + frontend) to avoid collisions
when multiple workers run servers and tests in parallel. Uses a swarm-wide
JSON store under main_project/.swarmweaver/swarm/port_allocations.json.

Port ranges (SwarmWeaver reserves 8000, 3000):
- Backend: 8010–8099
- Frontend: 3010–3099
"""

import json
import socket
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from core.paths import get_paths

BACKEND_BASE = 8010
BACKEND_RANGE = 90  # 8010–8099
FRONTEND_BASE = 3010
FRONTEND_RANGE = 90  # 3010–3099


def _port_is_bound(port: int) -> bool:
    """Check if a port is bound (in use)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            return s.connect_ex(("127.0.0.1", port)) == 0
    except Exception:
        return True


def _load_allocations(main_project_dir: Path) -> dict:
    """Load port allocations from disk."""
    paths = get_paths(main_project_dir)
    path = paths.port_allocations
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("workers", {})
    except (json.JSONDecodeError, OSError):
        return {}


def _save_allocations(main_project_dir: Path, workers: dict) -> None:
    """Persist port allocations to disk."""
    paths = get_paths(main_project_dir)
    path = paths.port_allocations
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"workers": workers}
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


@contextmanager
def _lock_file(path: Path, timeout_sec: float = 5.0):
    """Context manager for exclusive file lock (Unix fcntl). On Windows, no-op."""
    try:
        import fcntl
    except ImportError:
        yield
        return
    f = open(path, "a")
    try:
        import time
        deadline = time.monotonic() + timeout_sec
        while True:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                break
            except (BlockingIOError, OSError):
                if time.monotonic() > deadline:
                    raise RuntimeError("Port allocation lock timeout")
                time.sleep(0.05)
        yield
    finally:
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        f.close()


def allocate_ports_for_worker(main_project_dir: Path, worker_id: int) -> dict:
    """
    Allocate backend and frontend ports for a worker.

    If the worker already has allocated ports, returns them.
    Otherwise finds the next free ports in the allocation ranges,
    updates the store, and returns them.

    Args:
        main_project_dir: Main project directory (not worktree)
        worker_id: Worker identifier

    Returns:
        {"backend": int, "frontend": int}
    """
    main_project_dir = Path(main_project_dir)
    paths = get_paths(main_project_dir)
    lock_path = paths.swarm_dir / "port_allocations.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with _lock_file(lock_path):
            workers = _load_allocations(main_project_dir)
            wid = str(worker_id)

            if wid in workers:
                entry = workers[wid]
                return {"backend": int(entry["backend"]), "frontend": int(entry["frontend"])}

            used_backend = {int(w["backend"]) for w in workers.values()}
            used_frontend = {int(w["frontend"]) for w in workers.values()}

            backend_port = None
            for offset in range(BACKEND_RANGE):
                p = BACKEND_BASE + offset
                if p not in used_backend and not _port_is_bound(p):
                    backend_port = p
                    break

            frontend_port = None
            for offset in range(FRONTEND_RANGE):
                p = FRONTEND_BASE + offset
                if p not in used_frontend and not _port_is_bound(p):
                    frontend_port = p
                    break

            if backend_port is None:
                raise RuntimeError(
                    f"No free backend port in range {BACKEND_BASE}-{BACKEND_BASE + BACKEND_RANGE - 1}"
                )
            if frontend_port is None:
                raise RuntimeError(
                    f"No free frontend port in range {FRONTEND_BASE}-{FRONTEND_BASE + FRONTEND_RANGE - 1}"
                )

            workers[wid] = {"backend": backend_port, "frontend": frontend_port}
            _save_allocations(main_project_dir, workers)
            return {"backend": backend_port, "frontend": frontend_port}
    except (ImportError, AttributeError):
        # fcntl not available or lock failed, try without lock (races possible)
        workers = _load_allocations(main_project_dir)
        wid = str(worker_id)
        if wid in workers:
            entry = workers[wid]
            return {"backend": int(entry["backend"]), "frontend": int(entry["frontend"])}
        used_backend = {int(w["backend"]) for w in workers.values()}
        used_frontend = {int(w["frontend"]) for w in workers.values()}
        backend_port = next(
            (BACKEND_BASE + o for o in range(BACKEND_RANGE)
             if BACKEND_BASE + o not in used_backend and not _port_is_bound(BACKEND_BASE + o)),
            None
        )
        frontend_port = next(
            (FRONTEND_BASE + o for o in range(FRONTEND_RANGE)
             if FRONTEND_BASE + o not in used_frontend and not _port_is_bound(FRONTEND_BASE + o)),
            None
        )
        if backend_port is None or frontend_port is None:
            raise RuntimeError("No free ports available for worker")
        workers[wid] = {"backend": backend_port, "frontend": frontend_port}
        _save_allocations(main_project_dir, workers)
        return {"backend": backend_port, "frontend": frontend_port}


def get_worker_ports(main_project_dir: Path, worker_id: int) -> Optional[dict]:
    """
    Get allocated ports for a worker without allocating.

    Returns None if the worker has no allocation.
    """
    workers = _load_allocations(Path(main_project_dir))
    wid = str(worker_id)
    if wid not in workers:
        return None
    entry = workers[wid]
    return {"backend": int(entry["backend"]), "frontend": int(entry["frontend"])}


def release_ports_for_worker(main_project_dir: Path, worker_id: int) -> None:
    """
    Remove a worker's port allocation from the store.

    Does not terminate processes; caller must do that separately.
    """
    main_project_dir = Path(main_project_dir)
    paths = get_paths(main_project_dir)
    lock_path = paths.swarm_dir / "port_allocations.lock"
    try:
        with _lock_file(lock_path):
            workers = _load_allocations(main_project_dir)
            workers.pop(str(worker_id), None)
            _save_allocations(main_project_dir, workers)
    except (ImportError, AttributeError):
        workers = _load_allocations(main_project_dir)
        workers.pop(str(worker_id), None)
        _save_allocations(main_project_dir, workers)
