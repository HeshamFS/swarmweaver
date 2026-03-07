"""
Run Management System
========================

Tracks "runs" — logical groupings of agent sessions spawned from one
orchestration command. Each run has an ID, status, agent count, and lifecycle.
"""

import json
import sqlite3
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class Run:
    id: str
    status: str  # active, completed, failed
    mode: str
    project_dir: str
    agent_count: int
    created_at: str
    completed_at: str

    def to_dict(self) -> dict:
        return asdict(self)


class RunStore:
    """SQLite-backed run tracking."""

    DB_DIR = ".swarmweaver"
    DB_NAME = "runs.db"

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.db_path = project_dir / self.DB_DIR / self.DB_NAME
        self._conn: Optional[sqlite3.Connection] = None

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._get_conn()
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                status TEXT DEFAULT 'active',
                mode TEXT DEFAULT '',
                project_dir TEXT DEFAULT '',
                agent_count INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                completed_at TEXT DEFAULT ''
            )
        """)
        conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), timeout=10)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def create_run(self, mode: str = "", project_dir: str = "") -> str:
        run_id = f"run-{datetime.now().strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:6]}"
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO runs (id, status, mode, project_dir, agent_count, created_at) VALUES (?, 'active', ?, ?, 1, ?)",
            (run_id, mode, project_dir, datetime.now().isoformat()),
        )
        conn.commit()
        return run_id

    def get_run(self, run_id: str) -> Optional[Run]:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            return None
        return Run(**dict(row))

    def get_active_run(self) -> Optional[Run]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM runs WHERE status = 'active' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        return Run(**dict(row))

    def increment_agent_count(self, run_id: str) -> None:
        conn = self._get_conn()
        conn.execute("UPDATE runs SET agent_count = agent_count + 1 WHERE id = ?", (run_id,))
        conn.commit()

    def complete_run(self, run_id: str, status: str = "completed") -> None:
        conn = self._get_conn()
        conn.execute(
            "UPDATE runs SET status = ?, completed_at = ? WHERE id = ?",
            (status, datetime.now().isoformat(), run_id),
        )
        conn.commit()

    def list_runs(self, limit: int = 20, status: Optional[str] = None) -> list[Run]:
        conn = self._get_conn()
        if status:
            rows = conn.execute(
                "SELECT * FROM runs WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [Run(**dict(r)) for r in rows]

    def get_stats(self) -> dict:
        conn = self._get_conn()
        total = conn.execute("SELECT COUNT(*) as cnt FROM runs").fetchone()["cnt"]
        by_status = {}
        for r in conn.execute("SELECT status, COUNT(*) as cnt FROM runs GROUP BY status").fetchall():
            by_status[r["status"]] = r["cnt"]
        return {"total": total, "by_status": by_status}
