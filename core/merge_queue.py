"""
FIFO Merge Queue (SQLite)
============================

Provides ordered, tracked merging
of worker branches with status tracking and resolution tier recording.

Workers enqueue their branch when done. The orchestrator dequeues and
merges through the 4-tier resolver. Queue enables:
- Optimal merge ordering (by file overlap risk, completion time)
- Status tracking per branch (pending, merging, merged, conflict, failed)
- Resolution tier recording for observability and learning
"""

import json
import sqlite3
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional


class MergeStatus(str, Enum):
    """Status of a merge queue entry."""
    PENDING = "pending"
    MERGING = "merging"
    MERGED = "merged"
    CONFLICT = "conflict"
    FAILED = "failed"


@dataclass
class MergeQueueEntry:
    """A single entry in the merge queue."""
    id: str
    branch_name: str
    worker_name: str
    files_modified: list[str]
    status: str = MergeStatus.PENDING.value
    resolution_tier: int = 0  # 0=not attempted, 1-4=resolution tier
    resolution_details: str = ""
    enqueued_at: str = ""
    merged_at: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class MergeQueue:
    """
    SQLite-backed FIFO merge queue for swarm branch integration.

    Usage:
        queue = MergeQueue(project_dir)
        queue.initialize()

        # Worker enqueues branch
        queue.enqueue("swarm/worker-1", "worker-1", ["src/api.py", "src/models.py"])

        # Orchestrator processes queue
        entry = queue.dequeue()
        if entry:
            # ... run merge resolver ...
            queue.update_status(entry.id, MergeStatus.MERGED, tier=1)
    """

    DB_DIR = ".swarm"
    DB_NAME = "merge_queue.db"

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.db_path = project_dir / self.DB_DIR / self.DB_NAME
        self._connection: Optional[sqlite3.Connection] = None

    def initialize(self) -> None:
        """Create the queue database and table."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = self._get_connection()
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS merge_queue (
                id TEXT PRIMARY KEY,
                branch_name TEXT NOT NULL,
                worker_name TEXT NOT NULL,
                files_modified TEXT DEFAULT '[]',
                status TEXT DEFAULT 'pending',
                resolution_tier INTEGER DEFAULT 0,
                resolution_details TEXT DEFAULT '',
                enqueued_at TEXT NOT NULL,
                merged_at TEXT DEFAULT '',
                error TEXT DEFAULT ''
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_status
            ON merge_queue (status)
        """)

        conn.commit()

    def _get_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            self._connection = sqlite3.connect(str(self.db_path), timeout=10)
            self._connection.row_factory = sqlite3.Row
        return self._connection

    def close(self) -> None:
        if self._connection:
            self._connection.close()
            self._connection = None

    def enqueue(
        self,
        branch_name: str,
        worker_name: str,
        files_modified: Optional[list[str]] = None,
    ) -> str:
        """
        Add a branch to the merge queue.

        Args:
            branch_name: Git branch to merge
            worker_name: Name of the worker that completed
            files_modified: Files changed by this worker

        Returns:
            Queue entry ID
        """
        entry_id = str(uuid.uuid4())[:12]
        conn = self._get_connection()
        conn.execute(
            """
            INSERT INTO merge_queue (id, branch_name, worker_name, files_modified,
                                     status, enqueued_at)
            VALUES (?, ?, ?, ?, 'pending', ?)
            """,
            (
                entry_id,
                branch_name,
                worker_name,
                json.dumps(files_modified or []),
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
        return entry_id

    def dequeue(self) -> Optional[MergeQueueEntry]:
        """
        Get the next pending entry from the queue (FIFO order).

        Returns:
            Next MergeQueueEntry or None if queue is empty
        """
        conn = self._get_connection()
        row = conn.execute(
            "SELECT * FROM merge_queue WHERE status = 'pending' ORDER BY enqueued_at ASC LIMIT 1",
        ).fetchone()

        if not row:
            return None

        # Mark as merging
        conn.execute(
            "UPDATE merge_queue SET status = 'merging' WHERE id = ?",
            (row["id"],),
        )
        conn.commit()

        return MergeQueueEntry(
            id=row["id"],
            branch_name=row["branch_name"],
            worker_name=row["worker_name"],
            files_modified=json.loads(row["files_modified"]),
            status=MergeStatus.MERGING.value,
            enqueued_at=row["enqueued_at"],
        )

    def update_status(
        self,
        entry_id: str,
        status: MergeStatus,
        tier: int = 0,
        details: str = "",
        error: str = "",
    ) -> None:
        """Update the status of a queue entry after merge attempt."""
        conn = self._get_connection()
        merged_at = datetime.now().isoformat() if status == MergeStatus.MERGED else ""

        conn.execute(
            """
            UPDATE merge_queue
            SET status = ?, resolution_tier = ?, resolution_details = ?,
                merged_at = ?, error = ?
            WHERE id = ?
            """,
            (status.value, tier, details, merged_at, error, entry_id),
        )
        conn.commit()

    def get_queue(self, status: Optional[str] = None) -> list[MergeQueueEntry]:
        """Get all queue entries, optionally filtered by status."""
        conn = self._get_connection()

        if status:
            rows = conn.execute(
                "SELECT * FROM merge_queue WHERE status = ? ORDER BY enqueued_at ASC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM merge_queue ORDER BY enqueued_at ASC",
            ).fetchall()

        return [
            MergeQueueEntry(
                id=row["id"],
                branch_name=row["branch_name"],
                worker_name=row["worker_name"],
                files_modified=json.loads(row["files_modified"]),
                status=row["status"],
                resolution_tier=row["resolution_tier"],
                resolution_details=row["resolution_details"],
                enqueued_at=row["enqueued_at"],
                merged_at=row["merged_at"],
                error=row["error"],
            )
            for row in rows
        ]

    def get_stats(self) -> dict:
        """Get merge queue statistics."""
        conn = self._get_connection()
        total = conn.execute("SELECT COUNT(*) as cnt FROM merge_queue").fetchone()["cnt"]

        by_status = {}
        for row in conn.execute(
            "SELECT status, COUNT(*) as cnt FROM merge_queue GROUP BY status"
        ).fetchall():
            by_status[row["status"]] = row["cnt"]

        by_tier = {}
        for row in conn.execute(
            "SELECT resolution_tier, COUNT(*) as cnt FROM merge_queue "
            "WHERE resolution_tier > 0 GROUP BY resolution_tier"
        ).fetchall():
            tier_names = {1: "clean", 2: "auto_resolve", 3: "ai_resolve", 4: "reimagine"}
            tier_name = tier_names.get(row["resolution_tier"], f"tier_{row['resolution_tier']}")
            by_tier[tier_name] = row["cnt"]

        return {
            "total": total,
            "by_status": by_status,
            "by_resolution_tier": by_tier,
        }
