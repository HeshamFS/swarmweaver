"""
Persistent Session Database
============================

SQLite-backed store recording every session, agent turn, and file change.
Provides cross-project indexing for enterprise-grade session history.

Follows the MailStore pattern: WAL mode, busy_timeout=5000, Row factory.
"""

import json
import os
import sqlite3
import subprocess
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


class SessionStore:
    """
    Project-local session database at .swarmweaver/sessions.db.

    Records every session (Engine.run / SmartOrchestrator.run),
    agent turn (prompt→response pair), and file change.
    """

    DB_DIR = ".swarmweaver"
    DB_NAME = "sessions.db"

    def __init__(self, project_dir: Path):
        self.project_dir = Path(project_dir)
        self.db_path = self.project_dir / self.DB_DIR / self.DB_NAME
        self._connection: Optional[sqlite3.Connection] = None

    def initialize(self) -> None:
        """Create database and tables if they don't exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._get_connection()
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        self._ensure_tables(conn)
        conn.commit()

    def _get_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            self._connection = sqlite3.connect(
                str(self.db_path), timeout=10
            )
            self._connection.row_factory = sqlite3.Row
        return self._connection

    def close(self) -> None:
        if self._connection:
            self._connection.close()
            self._connection = None

    def _ensure_tables(self, conn: sqlite3.Connection) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                project_dir TEXT NOT NULL,
                mode TEXT NOT NULL,
                model TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'running',
                is_team INTEGER NOT NULL DEFAULT 0,
                agent_count INTEGER NOT NULL DEFAULT 1,
                chain_id TEXT DEFAULT NULL,
                parent_session_id TEXT DEFAULT NULL,
                tasks_total INTEGER DEFAULT 0,
                tasks_completed INTEGER DEFAULT 0,
                files_added INTEGER DEFAULT 0,
                files_modified INTEGER DEFAULT 0,
                files_deleted INTEGER DEFAULT 0,
                lines_added INTEGER DEFAULT 0,
                lines_deleted INTEGER DEFAULT 0,
                changed_files TEXT DEFAULT '[]',
                total_input_tokens INTEGER DEFAULT 0,
                total_output_tokens INTEGER DEFAULT 0,
                total_cost_usd REAL DEFAULT 0.0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT DEFAULT NULL,
                task_input TEXT DEFAULT '',
                error_message TEXT DEFAULT NULL,
                tags TEXT DEFAULT '[]',
                start_commit_sha TEXT DEFAULT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                agent_name TEXT NOT NULL DEFAULT '',
                phase TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL,
                content_summary TEXT NOT NULL DEFAULT '',
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                cost_usd REAL DEFAULT 0.0,
                model TEXT DEFAULT '',
                sdk_session_id TEXT DEFAULT NULL,
                turn_number INTEGER DEFAULT 0,
                duration_ms INTEGER DEFAULT 0,
                snapshot_before TEXT DEFAULT NULL,
                snapshot_after TEXT DEFAULT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS file_changes (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                file_path TEXT NOT NULL,
                change_type TEXT NOT NULL,
                additions INTEGER DEFAULT 0,
                deletions INTEGER DEFAULT 0,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)

        # Indexes
        for idx_sql in [
            "CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions (status)",
            "CREATE INDEX IF NOT EXISTS idx_sessions_mode ON sessions (mode)",
            "CREATE INDEX IF NOT EXISTS idx_sessions_created ON sessions (created_at)",
            "CREATE INDEX IF NOT EXISTS idx_sessions_chain ON sessions (chain_id)",
            "CREATE INDEX IF NOT EXISTS idx_messages_session ON messages (session_id)",
            "CREATE INDEX IF NOT EXISTS idx_messages_agent ON messages (agent_name)",
            "CREATE INDEX IF NOT EXISTS idx_file_changes_session ON file_changes (session_id)",
        ]:
            conn.execute(idx_sql)

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def create_session(
        self,
        mode: str,
        model: str,
        task_input: str = "",
        is_team: bool = False,
        agent_count: int = 1,
        chain_id: Optional[str] = None,
        title: str = "",
        parent_session_id: Optional[str] = None,
    ) -> str:
        """Create a new session record. Returns session ID."""
        session_id = uuid.uuid4().hex[:16]
        now = datetime.utcnow().isoformat() + "Z"

        # Capture starting commit SHA for later diff
        start_sha = self._get_head_sha()

        # Auto-generate title from task_input
        if not title and task_input:
            title = task_input.strip()[:80]
            if len(task_input.strip()) > 80:
                title += "..."

        conn = self._get_connection()
        conn.execute(
            """INSERT INTO sessions
               (id, project_dir, mode, model, title, status, is_team,
                agent_count, chain_id, parent_session_id, task_input,
                start_commit_sha, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'running', ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id,
                str(self.project_dir),
                mode,
                model,
                title,
                1 if is_team else 0,
                agent_count,
                chain_id,
                parent_session_id,
                task_input,
                start_sha,
                now,
                now,
            ),
        )
        conn.commit()
        return session_id

    def update_session(self, session_id: str, **fields) -> None:
        """Update arbitrary session fields."""
        if not fields:
            return
        now = datetime.utcnow().isoformat() + "Z"
        fields["updated_at"] = now

        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [session_id]

        conn = self._get_connection()
        conn.execute(
            f"UPDATE sessions SET {set_clause} WHERE id = ?", values
        )
        conn.commit()

    def complete_session(
        self,
        session_id: str,
        status: str = "completed",
        error_message: Optional[str] = None,
    ) -> None:
        """Mark a session as completed/stopped/error."""
        now = datetime.utcnow().isoformat() + "Z"
        fields = {
            "status": status,
            "completed_at": now,
            "updated_at": now,
        }
        if error_message:
            fields["error_message"] = error_message

        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [session_id]

        conn = self._get_connection()
        conn.execute(
            f"UPDATE sessions SET {set_clause} WHERE id = ?", values
        )
        conn.commit()

    def archive_session(self, session_id: str) -> None:
        """Soft-delete by setting status to 'archived'."""
        self.update_session(session_id, status="archived")

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    def record_message(
        self,
        session_id: str,
        agent_name: str = "",
        phase: str = "",
        role: str = "assistant",
        content_summary: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
        model: str = "",
        sdk_session_id: Optional[str] = None,
        turn_number: int = 0,
        duration_ms: int = 0,
        snapshot_before: Optional[str] = None,
        snapshot_after: Optional[str] = None,
    ) -> str:
        """Record a message (agent turn) within a session."""
        msg_id = uuid.uuid4().hex[:16]
        now = datetime.utcnow().isoformat() + "Z"

        conn = self._get_connection()
        conn.execute(
            """INSERT INTO messages
               (id, session_id, agent_name, phase, role, content_summary,
                input_tokens, output_tokens, cost_usd, model,
                sdk_session_id, turn_number, duration_ms,
                snapshot_before, snapshot_after, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                msg_id,
                session_id,
                agent_name,
                phase,
                role,
                content_summary[:500] if content_summary else "",
                input_tokens,
                output_tokens,
                cost_usd,
                model,
                sdk_session_id,
                turn_number,
                duration_ms,
                snapshot_before,
                snapshot_after,
                now,
            ),
        )

        # Update session cumulative totals
        conn.execute(
            """UPDATE sessions SET
                 total_input_tokens = total_input_tokens + ?,
                 total_output_tokens = total_output_tokens + ?,
                 total_cost_usd = total_cost_usd + ?,
                 updated_at = ?
               WHERE id = ?""",
            (input_tokens, output_tokens, cost_usd, now, session_id),
        )
        conn.commit()
        return msg_id

    # ------------------------------------------------------------------
    # File changes
    # ------------------------------------------------------------------

    def record_file_changes(self, session_id: str, changes: list[dict]) -> None:
        """Record a list of file changes for a session."""
        conn = self._get_connection()
        for change in changes:
            change_id = uuid.uuid4().hex[:16]
            conn.execute(
                """INSERT INTO file_changes
                   (id, session_id, file_path, change_type, additions, deletions)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    change_id,
                    session_id,
                    change.get("file_path", ""),
                    change.get("change_type", "modified"),
                    change.get("additions", 0),
                    change.get("deletions", 0),
                ),
            )
        conn.commit()

    def compute_change_summary(self, session_id: str) -> dict:
        """
        Compute file change summary via git diff from start_commit_sha to HEAD.
        Populates file_changes table and updates session summary fields.
        Returns the summary dict.
        """
        conn = self._get_connection()
        row = conn.execute(
            "SELECT start_commit_sha FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()

        if not row or not row["start_commit_sha"]:
            return {"files_added": 0, "files_modified": 0, "files_deleted": 0,
                    "lines_added": 0, "lines_deleted": 0, "changed_files": []}

        start_sha = row["start_commit_sha"]
        summary = {
            "files_added": 0, "files_modified": 0, "files_deleted": 0,
            "lines_added": 0, "lines_deleted": 0, "changed_files": [],
        }

        try:
            result = subprocess.run(
                ["git", "diff", "--numstat", f"{start_sha}..HEAD"],
                capture_output=True, text=True, timeout=30,
                cwd=str(self.project_dir),
            )
            if result.returncode != 0:
                return summary

            changes = []
            for line in result.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                parts = line.split("\t")
                if len(parts) < 3:
                    continue
                added = int(parts[0]) if parts[0] != "-" else 0
                deleted = int(parts[1]) if parts[1] != "-" else 0
                file_path = parts[2]

                summary["lines_added"] += added
                summary["lines_deleted"] += deleted
                summary["changed_files"].append(file_path)

                # Determine change type
                change_type = "modified"
                if added > 0 and deleted == 0:
                    # Could be new file — check with diff --diff-filter
                    change_type = "added"
                    summary["files_added"] += 1
                elif added == 0 and deleted > 0:
                    change_type = "deleted"
                    summary["files_deleted"] += 1
                else:
                    summary["files_modified"] += 1

                changes.append({
                    "file_path": file_path,
                    "change_type": change_type,
                    "additions": added,
                    "deletions": deleted,
                })

            # More accurate change type detection
            try:
                diff_filter_result = subprocess.run(
                    ["git", "diff", "--name-status", f"{start_sha}..HEAD"],
                    capture_output=True, text=True, timeout=30,
                    cwd=str(self.project_dir),
                )
                if diff_filter_result.returncode == 0:
                    status_map = {}
                    for line in diff_filter_result.stdout.strip().split("\n"):
                        if not line.strip():
                            continue
                        parts = line.split("\t", 1)
                        if len(parts) == 2:
                            status_map[parts[1]] = parts[0]

                    # Recount with accurate statuses
                    summary["files_added"] = 0
                    summary["files_modified"] = 0
                    summary["files_deleted"] = 0
                    for change in changes:
                        git_status = status_map.get(change["file_path"], "M")
                        if git_status.startswith("A"):
                            change["change_type"] = "added"
                            summary["files_added"] += 1
                        elif git_status.startswith("D"):
                            change["change_type"] = "deleted"
                            summary["files_deleted"] += 1
                        else:
                            change["change_type"] = "modified"
                            summary["files_modified"] += 1
            except Exception:
                pass  # Use heuristic counts from numstat

            # Persist file changes
            self.record_file_changes(session_id, changes)

            # Update session summary
            now = datetime.utcnow().isoformat() + "Z"
            conn.execute(
                """UPDATE sessions SET
                     files_added = ?, files_modified = ?, files_deleted = ?,
                     lines_added = ?, lines_deleted = ?,
                     changed_files = ?, updated_at = ?
                   WHERE id = ?""",
                (
                    summary["files_added"],
                    summary["files_modified"],
                    summary["files_deleted"],
                    summary["lines_added"],
                    summary["lines_deleted"],
                    json.dumps(summary["changed_files"]),
                    now,
                    session_id,
                ),
            )
            conn.commit()

        except Exception as e:
            print(f"[SessionStore] compute_change_summary failed: {e}", flush=True)

        return summary

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_session(self, session_id: str) -> Optional[dict]:
        conn = self._get_connection()
        row = conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_sessions(
        self,
        status: Optional[str] = None,
        mode: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        conn = self._get_connection()
        query = "SELECT * FROM sessions WHERE 1=1"
        params: list = []

        if status:
            query += " AND status = ?"
            params.append(status)
        if mode:
            query += " AND mode = ?"
            params.append(mode)

        # Exclude archived by default
        if status != "archived":
            query += " AND status != 'archived'"

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def get_messages(
        self,
        session_id: str,
        agent_name: Optional[str] = None,
        limit: int = 200,
    ) -> list[dict]:
        conn = self._get_connection()
        query = "SELECT * FROM messages WHERE session_id = ?"
        params: list = [session_id]

        if agent_name:
            query += " AND agent_name = ?"
            params.append(agent_name)

        query += " ORDER BY created_at ASC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def get_file_changes(self, session_id: str) -> list[dict]:
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT * FROM file_changes WHERE session_id = ? ORDER BY file_path",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_detail(self, session_id: str) -> Optional[dict]:
        """Get full session detail: session + messages + file_changes."""
        session = self.get_session(session_id)
        if not session:
            return None
        session["messages"] = self.get_messages(session_id)
        session["file_changes"] = self.get_file_changes(session_id)
        return session

    # ------------------------------------------------------------------
    # Analytics
    # ------------------------------------------------------------------

    def get_analytics(
        self,
        since: Optional[str] = None,
        mode: Optional[str] = None,
    ) -> dict:
        conn = self._get_connection()
        where = "WHERE status != 'archived'"
        params: list = []

        if since:
            where += " AND created_at >= ?"
            params.append(since)
        if mode:
            where += " AND mode = ?"
            params.append(mode)

        # Total sessions
        total = conn.execute(
            f"SELECT COUNT(*) as cnt FROM sessions {where}", params
        ).fetchone()["cnt"]

        # By status
        by_status = {}
        rows = conn.execute(
            f"SELECT status, COUNT(*) as cnt FROM sessions {where} GROUP BY status",
            params,
        ).fetchall()
        for r in rows:
            by_status[r["status"]] = r["cnt"]

        # By mode
        by_mode = {}
        rows = conn.execute(
            f"SELECT mode, COUNT(*) as cnt FROM sessions {where} GROUP BY mode",
            params,
        ).fetchall()
        for r in rows:
            by_mode[r["mode"]] = r["cnt"]

        # Cost totals
        cost_row = conn.execute(
            f"""SELECT
                  SUM(total_cost_usd) as total_cost,
                  AVG(total_cost_usd) as avg_cost,
                  SUM(total_input_tokens) as total_input,
                  SUM(total_output_tokens) as total_output
                FROM sessions {where}""",
            params,
        ).fetchone()

        return {
            "total_sessions": total,
            "by_status": by_status,
            "by_mode": by_mode,
            "total_cost_usd": cost_row["total_cost"] or 0.0,
            "avg_cost_usd": cost_row["avg_cost"] or 0.0,
            "total_input_tokens": cost_row["total_input"] or 0,
            "total_output_tokens": cost_row["total_output"] or 0,
        }

    # ------------------------------------------------------------------
    # Cross-project sync
    # ------------------------------------------------------------------

    def sync_to_global(self, session_id: str) -> None:
        """Push session data to the global cross-project index."""
        session = self.get_session(session_id)
        if not session:
            return
        try:
            idx = GlobalSessionIndex()
            idx.initialize()
            idx.upsert(session)
        except Exception as e:
            print(f"[SessionStore] sync_to_global failed: {e}", flush=True)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def purge(self, older_than_days: int = 90) -> int:
        """Delete sessions older than N days. Returns count deleted."""
        cutoff = (datetime.utcnow() - timedelta(days=older_than_days)).isoformat() + "Z"
        conn = self._get_connection()

        # Get IDs to delete
        rows = conn.execute(
            "SELECT id FROM sessions WHERE created_at < ? AND status IN ('completed', 'error', 'archived')",
            (cutoff,),
        ).fetchall()
        ids = [r["id"] for r in rows]

        if not ids:
            return 0

        placeholders = ",".join("?" * len(ids))
        conn.execute(f"DELETE FROM file_changes WHERE session_id IN ({placeholders})", ids)
        conn.execute(f"DELETE FROM messages WHERE session_id IN ({placeholders})", ids)
        conn.execute(f"DELETE FROM sessions WHERE id IN ({placeholders})", ids)
        conn.commit()
        return len(ids)

    def delete_session(self, session_id: str) -> bool:
        """Delete a single session and all related data."""
        conn = self._get_connection()
        conn.execute("DELETE FROM file_changes WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        result = conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()
        return result.rowcount > 0

    # ------------------------------------------------------------------
    # Migration from chains
    # ------------------------------------------------------------------

    def migrate_from_chains(self) -> int:
        """Import existing chain JSON files into sessions table."""
        chains_dir = self.project_dir / ".swarmweaver" / "chains"
        if not chains_dir.exists():
            return 0

        conn = self._get_connection()
        # Skip if we already have sessions
        count = conn.execute("SELECT COUNT(*) as cnt FROM sessions").fetchone()["cnt"]
        if count > 0:
            return 0

        migrated = 0
        for chain_file in chains_dir.glob("*.json"):
            if chain_file.stem.startswith("_") or chain_file.stem.endswith("_structured"):
                continue
            try:
                entries = json.loads(chain_file.read_text(encoding="utf-8"))
                chain_id = chain_file.stem
                for entry in entries:
                    sid = entry.get("session_id", uuid.uuid4().hex[:16])
                    now = datetime.utcnow().isoformat() + "Z"
                    conn.execute(
                        """INSERT OR IGNORE INTO sessions
                           (id, project_dir, mode, model, title, status,
                            is_team, chain_id, tasks_total, tasks_completed,
                            total_cost_usd, created_at, updated_at, completed_at,
                            task_input)
                           VALUES (?, ?, ?, '', ?, 'completed', 0, ?, ?, ?, ?, ?, ?, ?, '')""",
                        (
                            sid,
                            str(self.project_dir),
                            entry.get("phase", "unknown"),
                            entry.get("checkpoint_summary", "")[:80] or f"Session {entry.get('sequence_number', 0)}",
                            chain_id,
                            entry.get("tasks_total", 0),
                            entry.get("tasks_completed", 0),
                            entry.get("cost", 0.0),
                            entry.get("start_time", now),
                            now,
                            entry.get("end_time", now),
                        ),
                    )
                    migrated += 1
            except Exception as e:
                print(f"[SessionStore] migrate chain {chain_file.name}: {e}", flush=True)

        conn.commit()
        return migrated

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_head_sha(self) -> Optional[str]:
        """Get current git HEAD SHA."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=10,
                cwd=str(self.project_dir),
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None


class GlobalSessionIndex:
    """
    Cross-project session index at ~/.swarmweaver/sessions.db.

    Stores lightweight copies of session records from all projects
    for global browsing and analytics.
    """

    def __init__(self):
        home = Path.home()
        self.db_path = home / ".swarmweaver" / "sessions.db"
        self._connection: Optional[sqlite3.Connection] = None

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._get_connection()
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS session_index (
                id TEXT PRIMARY KEY,
                project_dir TEXT NOT NULL,
                mode TEXT NOT NULL,
                model TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'running',
                is_team INTEGER NOT NULL DEFAULT 0,
                agent_count INTEGER NOT NULL DEFAULT 1,
                tasks_total INTEGER DEFAULT 0,
                tasks_completed INTEGER DEFAULT 0,
                total_cost_usd REAL DEFAULT 0.0,
                created_at TEXT NOT NULL,
                completed_at TEXT DEFAULT NULL,
                task_input TEXT DEFAULT ''
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_global_project ON session_index (project_dir)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_global_created ON session_index (created_at)"
        )
        conn.commit()

    def _get_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            self._connection = sqlite3.connect(
                str(self.db_path), timeout=10
            )
            self._connection.row_factory = sqlite3.Row
        return self._connection

    def close(self) -> None:
        if self._connection:
            self._connection.close()
            self._connection = None

    def upsert(self, session_data: dict) -> None:
        """Insert or update a session record in the global index."""
        conn = self._get_connection()
        conn.execute(
            """INSERT OR REPLACE INTO session_index
               (id, project_dir, mode, model, title, status, is_team,
                agent_count, tasks_total, tasks_completed, total_cost_usd,
                created_at, completed_at, task_input)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session_data["id"],
                session_data.get("project_dir", ""),
                session_data.get("mode", ""),
                session_data.get("model", ""),
                session_data.get("title", ""),
                session_data.get("status", "running"),
                session_data.get("is_team", 0),
                session_data.get("agent_count", 1),
                session_data.get("tasks_total", 0),
                session_data.get("tasks_completed", 0),
                session_data.get("total_cost_usd", 0.0),
                session_data.get("created_at", ""),
                session_data.get("completed_at"),
                session_data.get("task_input", ""),
            ),
        )
        conn.commit()

    def list_sessions(
        self,
        project_dir: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        conn = self._get_connection()
        query = "SELECT * FROM session_index WHERE 1=1"
        params: list = []

        if project_dir:
            query += " AND project_dir = ?"
            params.append(project_dir)
        if status:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def get_analytics(self) -> dict:
        conn = self._get_connection()

        total = conn.execute(
            "SELECT COUNT(*) as cnt FROM session_index"
        ).fetchone()["cnt"]

        by_project = {}
        rows = conn.execute(
            "SELECT project_dir, COUNT(*) as cnt, SUM(total_cost_usd) as cost "
            "FROM session_index GROUP BY project_dir"
        ).fetchall()
        for r in rows:
            by_project[r["project_dir"]] = {
                "count": r["cnt"],
                "total_cost_usd": r["cost"] or 0.0,
            }

        cost_row = conn.execute(
            "SELECT SUM(total_cost_usd) as total FROM session_index"
        ).fetchone()

        return {
            "total_sessions": total,
            "by_project": by_project,
            "total_cost_usd": cost_row["total"] or 0.0,
        }
