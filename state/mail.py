"""
Inter-Agent Mail System (SQLite)
==================================

Provides a lightweight, concurrent-safe messaging system for swarm worker coordination.

Uses SQLite with WAL mode for fast concurrent reads/writes across
multiple worker processes. Each worker gets a unique address (worker_id)
and can send/receive typed messages.

Message types:
  - status       Worker reports its current status
  - question     Worker asks the orchestrator a question
  - result       Worker reports a result
  - error        Worker reports an error
  - worker_done  Worker signals task completion
  - merge_ready  Worker signals its branch is ready to merge
  - dispatch     Orchestrator dispatches a worker with tasks
  - assign       Orchestrator assigns a specific task to a worker
  - escalation   Watchdog escalates a stalled/dead worker
  - health_check Watchdog periodic health check
  - merged       Worker branch merged successfully
  - merge_failed Worker branch merge failed
"""

import json
import sqlite3
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional


class MessageType(str, Enum):
    """Types of inter-agent messages."""
    STATUS = "status"
    QUESTION = "question"
    RESULT = "result"
    ERROR = "error"
    WORKER_DONE = "worker_done"
    MERGE_READY = "merge_ready"
    DISPATCH = "dispatch"
    ASSIGN = "assign"
    ESCALATION = "escalation"
    HEALTH_CHECK = "health_check"
    MERGED = "merged"
    MERGE_FAILED = "merge_failed"
    # Smart orchestrator message types
    DIRECTIVE = "directive"            # Orchestrator sends guidance to a worker
    TASK_REASSIGNED = "task_reassigned"  # Orchestrator moved tasks between workers
    WORKER_PROGRESS = "worker_progress"  # Periodic worker status update


class MessagePriority(str, Enum):
    """Priority levels for messages."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class MailMessage:
    """A single inter-agent message."""
    id: str
    sender: str  # worker_id or "orchestrator"
    recipient: str  # worker_id, "orchestrator", or "@all"
    msg_type: str
    subject: str
    body: str
    priority: str = MessagePriority.NORMAL.value
    thread_id: Optional[str] = None  # For conversation tracking
    read: bool = False
    created_at: str = ""
    metadata: Optional[dict] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        if d["metadata"] is None:
            d["metadata"] = {}
        return d


class MailStore:
    """
    SQLite-backed mail system for inter-agent communication.

    Usage:
        store = MailStore(project_dir)
        store.initialize()

        # Send a message
        store.send(sender="worker-1", recipient="orchestrator",
                   msg_type="worker_done", subject="Task TASK-001 complete",
                   body="All tests passing")

        # Check for messages
        messages = store.get_messages(recipient="orchestrator", unread_only=True)

        # Mark as read
        store.mark_read(message_id)
    """

    DB_DIR = ".swarmweaver"
    DB_NAME = "mail.db"

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.db_path = project_dir / self.DB_DIR / self.DB_NAME
        self._connection: Optional[sqlite3.Connection] = None

    def initialize(self) -> None:
        """Create the mail database and table if they don't exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = self._get_connection()
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                sender TEXT NOT NULL,
                recipient TEXT NOT NULL,
                msg_type TEXT NOT NULL,
                subject TEXT NOT NULL,
                body TEXT DEFAULT '',
                priority TEXT DEFAULT 'normal',
                thread_id TEXT,
                read INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                metadata TEXT DEFAULT '{}'
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_recipient_read
            ON messages (recipient, read)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_sender
            ON messages (sender)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_msg_type
            ON messages (msg_type)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_thread_id
            ON messages (thread_id)
        """)

        conn.commit()

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create a database connection."""
        if self._connection is None:
            self._connection = sqlite3.connect(
                str(self.db_path),
                timeout=10,
            )
            self._connection.row_factory = sqlite3.Row
        return self._connection

    def close(self) -> None:
        """Close the database connection."""
        if self._connection:
            self._connection.close()
            self._connection = None

    # --- Broadcast Group Addressing (F18) ---

    @staticmethod
    def is_group_address(target: str) -> bool:
        """Check if a recipient is a group address."""
        return target.startswith("@")

    @staticmethod
    def resolve_group_address(
        target: str,
        workers: list[dict],
    ) -> list[str]:
        """
        Resolve a group address to individual worker names.

        Args:
            target: Group address like "@all", "@builders", "@scouts", "@reviewers"
            workers: List of worker dicts with 'worker_id' and optionally 'role' keys

        Returns:
            List of individual recipient names
        """
        if target == "@all":
            return [f"worker-{w.get('worker_id', w.get('id', i))}" for i, w in enumerate(workers)]

        role_map = {
            "@builders": "builder",
            "@reviewers": "reviewer",
            "@scouts": "scout",
        }
        target_role = role_map.get(target)
        if target_role:
            return [
                f"worker-{w.get('worker_id', w.get('id', i))}"
                for i, w in enumerate(workers)
                if w.get("role", "builder") == target_role
            ]

        # Unknown group — return empty
        return []

    def broadcast(
        self,
        sender: str,
        target: str,
        workers: list[dict],
        msg_type: str,
        subject: str,
        body: str = "",
        priority: str = MessagePriority.NORMAL.value,
        thread_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> list[str]:
        """
        Send a message to a group address, creating individual messages for each recipient.

        Returns list of created message IDs.
        """
        if self.is_group_address(target):
            recipients = self.resolve_group_address(target, workers)
        else:
            recipients = [target]

        msg_ids = []
        for recipient in recipients:
            msg_id = self.send(
                sender=sender, recipient=recipient, msg_type=msg_type,
                subject=subject, body=body, priority=priority,
                thread_id=thread_id, metadata=metadata,
            )
            msg_ids.append(msg_id)
        return msg_ids

    def send(
        self,
        sender: str,
        recipient: str,
        msg_type: str,
        subject: str,
        body: str = "",
        priority: str = MessagePriority.NORMAL.value,
        thread_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        """
        Send a message.

        Args:
            sender: Sender address (e.g., "worker-1", "orchestrator")
            recipient: Recipient address (e.g., "worker-2", "orchestrator", "@all")
            msg_type: Message type (see MessageType enum)
            subject: Short subject line
            body: Message body (can be multi-line)
            priority: Priority level
            thread_id: Optional thread ID for conversation tracking
            metadata: Optional extra data dict

        Returns:
            The message ID
        """
        msg_id = str(uuid.uuid4())
        created_at = datetime.now().isoformat()

        conn = self._get_connection()
        conn.execute(
            """
            INSERT INTO messages (id, sender, recipient, msg_type, subject,
                                  body, priority, thread_id, read, created_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                msg_id, sender, recipient, msg_type, subject,
                body, priority, thread_id, created_at,
                json.dumps(metadata or {}),
            ),
        )
        conn.commit()
        return msg_id

    def get_messages(
        self,
        recipient: Optional[str] = None,
        sender: Optional[str] = None,
        msg_type: Optional[str] = None,
        thread_id: Optional[str] = None,
        unread_only: bool = False,
        limit: int = 100,
    ) -> list[MailMessage]:
        """
        Retrieve messages with optional filters.

        Args:
            recipient: Filter by recipient (also matches "@all")
            sender: Filter by sender
            msg_type: Filter by message type
            thread_id: Filter by thread
            unread_only: Only return unread messages
            limit: Maximum number of messages to return

        Returns:
            List of MailMessage objects, newest first
        """
        conn = self._get_connection()

        conditions = []
        params: list = []

        if recipient:
            conditions.append("(recipient = ? OR recipient = '@all')")
            params.append(recipient)

        if sender:
            conditions.append("sender = ?")
            params.append(sender)

        if msg_type:
            conditions.append("msg_type = ?")
            params.append(msg_type)

        if thread_id:
            conditions.append("thread_id = ?")
            params.append(thread_id)

        if unread_only:
            conditions.append("read = 0")

        where = " AND ".join(conditions) if conditions else "1=1"

        rows = conn.execute(
            f"SELECT * FROM messages WHERE {where} ORDER BY created_at DESC LIMIT ?",
            params + [limit],
        ).fetchall()

        messages = []
        for row in rows:
            try:
                metadata = json.loads(row["metadata"]) if row["metadata"] else {}
            except (json.JSONDecodeError, TypeError):
                metadata = {}

            messages.append(MailMessage(
                id=row["id"],
                sender=row["sender"],
                recipient=row["recipient"],
                msg_type=row["msg_type"],
                subject=row["subject"],
                body=row["body"],
                priority=row["priority"],
                thread_id=row["thread_id"],
                read=bool(row["read"]),
                created_at=row["created_at"],
                metadata=metadata,
            ))

        return messages

    def mark_read(self, message_id: str) -> bool:
        """Mark a message as read."""
        conn = self._get_connection()
        cursor = conn.execute(
            "UPDATE messages SET read = 1 WHERE id = ?",
            (message_id,),
        )
        conn.commit()
        return cursor.rowcount > 0

    def mark_all_read(self, recipient: str) -> int:
        """Mark all messages for a recipient as read."""
        conn = self._get_connection()
        cursor = conn.execute(
            "UPDATE messages SET read = 1 WHERE (recipient = ? OR recipient = '@all') AND read = 0",
            (recipient,),
        )
        conn.commit()
        return cursor.rowcount

    def get_unread_count(self, recipient: str) -> int:
        """Get count of unread messages for a recipient."""
        conn = self._get_connection()
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM messages WHERE (recipient = ? OR recipient = '@all') AND read = 0",
            (recipient,),
        ).fetchone()
        return row["cnt"] if row else 0

    def get_thread(self, thread_id: str) -> list[MailMessage]:
        """Get all messages in a thread, ordered chronologically."""
        return self.get_messages(thread_id=thread_id, limit=1000)

    def delete_old_messages(self, days: int = 7) -> int:
        """Delete messages older than N days."""
        conn = self._get_connection()
        cutoff = datetime.now().isoformat()  # simplified; real impl would subtract days
        cursor = conn.execute(
            "DELETE FROM messages WHERE read = 1 AND created_at < datetime('now', ?)",
            (f"-{days} days",),
        )
        conn.commit()
        return cursor.rowcount

    def get_stats(self) -> dict:
        """Get mail system statistics."""
        conn = self._get_connection()

        total = conn.execute("SELECT COUNT(*) as cnt FROM messages").fetchone()["cnt"]
        unread = conn.execute("SELECT COUNT(*) as cnt FROM messages WHERE read = 0").fetchone()["cnt"]

        by_type = {}
        for row in conn.execute(
            "SELECT msg_type, COUNT(*) as cnt FROM messages GROUP BY msg_type"
        ).fetchall():
            by_type[row["msg_type"]] = row["cnt"]

        return {
            "total": total,
            "unread": unread,
            "by_type": by_type,
        }
