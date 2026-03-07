"""
Persistent Event Store (SQLite)
=================================

Provides a queryable, persistent record of all agent activity — tool calls, sessions, errors, mail events.

Unlike the ephemeral EventParser (stdout parsing), this store survives
page refreshes and session restarts.
"""

import json
import sqlite3
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class EventRecord:
    """A single recorded event."""
    id: str
    agent_name: str
    run_id: str
    event_type: str  # tool_start, tool_end, session_start, session_end, mail_sent, error, custom
    tool_name: str
    duration_ms: int
    level: str  # info, warn, error
    data: dict
    created_at: str

    def to_dict(self) -> dict:
        return asdict(self)


class EventStore:
    """
    SQLite-backed persistent event store for agent activity tracking.

    Usage:
        store = EventStore(project_dir)
        store.initialize()
        store.record("tool_start", tool_name="Read", agent_name="worker-1")
        events = store.query(agent_name="worker-1", event_type="error")
        stats = store.tool_statistics()
    """

    DB_DIR = ".swarmweaver"
    DB_NAME = "events.db"

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
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                agent_name TEXT DEFAULT '',
                run_id TEXT DEFAULT '',
                event_type TEXT NOT NULL,
                tool_name TEXT DEFAULT '',
                duration_ms INTEGER DEFAULT 0,
                level TEXT DEFAULT 'info',
                data_json TEXT DEFAULT '{}',
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events (event_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_agent ON events (agent_name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_time ON events (created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_run ON events (run_id)")
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

    def record(
        self,
        event_type: str,
        tool_name: str = "",
        agent_name: str = "",
        run_id: str = "",
        duration_ms: int = 0,
        level: str = "info",
        data: Optional[dict] = None,
    ) -> str:
        event_id = uuid.uuid4().hex[:12]
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO events (id, agent_name, run_id, event_type, tool_name,
               duration_ms, level, data_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (event_id, agent_name, run_id, event_type, tool_name,
             duration_ms, level, json.dumps(data or {}), datetime.now().isoformat()),
        )
        conn.commit()
        return event_id

    def query(
        self,
        agent_name: Optional[str] = None,
        run_id: Optional[str] = None,
        event_type: Optional[str] = None,
        level: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        limit: int = 200,
    ) -> list[EventRecord]:
        conn = self._get_conn()
        conditions = []
        params: list = []

        if agent_name:
            conditions.append("agent_name = ?")
            params.append(agent_name)
        if run_id:
            conditions.append("run_id = ?")
            params.append(run_id)
        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)
        if level:
            conditions.append("level = ?")
            params.append(level)
        if since:
            conditions.append("created_at >= ?")
            params.append(since)
        if until:
            conditions.append("created_at <= ?")
            params.append(until)

        where = " AND ".join(conditions) if conditions else "1=1"
        rows = conn.execute(
            f"SELECT * FROM events WHERE {where} ORDER BY created_at DESC LIMIT ?",
            params + [limit],
        ).fetchall()

        return [
            EventRecord(
                id=r["id"], agent_name=r["agent_name"], run_id=r["run_id"],
                event_type=r["event_type"], tool_name=r["tool_name"],
                duration_ms=r["duration_ms"], level=r["level"],
                data=json.loads(r["data_json"]) if r["data_json"] else {},
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def tool_statistics(self, run_id: Optional[str] = None) -> list[dict]:
        conn = self._get_conn()
        where = "WHERE run_id = ?" if run_id else ""
        params = [run_id] if run_id else []
        rows = conn.execute(
            f"""SELECT tool_name,
                       COUNT(*) as call_count,
                       AVG(duration_ms) as avg_duration,
                       MAX(duration_ms) as max_duration,
                       SUM(CASE WHEN level = 'error' THEN 1 ELSE 0 END) as error_count
                FROM events {where}
                WHERE tool_name != ''
                GROUP BY tool_name
                ORDER BY call_count DESC""",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    def purge(self, older_than_days: int = 30) -> int:
        conn = self._get_conn()
        cursor = conn.execute(
            "DELETE FROM events WHERE created_at < datetime('now', ?)",
            (f"-{older_than_days} days",),
        )
        conn.commit()
        return cursor.rowcount

    def get_stats(self) -> dict:
        conn = self._get_conn()
        total = conn.execute("SELECT COUNT(*) as cnt FROM events").fetchone()["cnt"]
        errors = conn.execute("SELECT COUNT(*) as cnt FROM events WHERE level = 'error'").fetchone()["cnt"]
        by_type = {}
        for r in conn.execute("SELECT event_type, COUNT(*) as cnt FROM events GROUP BY event_type").fetchall():
            by_type[r["event_type"]] = r["cnt"]
        return {"total": total, "errors": errors, "by_type": by_type}
