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
import time
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable, Optional


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


# --- Typed Protocol Payload Schemas (M1-1) ---

PAYLOAD_SCHEMAS: dict[str, dict] = {
    "dispatch": {"required": ["task_ids"], "optional": ["file_scope", "worktree_path", "role"]},
    "worker_done": {"required": [], "optional": ["status", "tasks_completed", "branch"]},
    "worker_progress": {"required": [], "optional": ["done", "total", "current_task_id", "transitions"]},
    "error": {"required": [], "optional": ["error_type", "stack_trace", "tool_name"]},
    "escalation": {"required": ["worker_id"], "optional": ["elapsed_seconds", "escalation_level"]},
    "merged": {"required": ["branch"], "optional": ["merge_commit", "files_changed"]},
    "merge_failed": {"required": ["branch"], "optional": ["conflict_files", "error"]},
    "directive": {"required": [], "optional": ["directive_type", "urgency"]},
    "task_reassigned": {"required": ["task_id"], "optional": ["from_worker", "to_worker", "reason"]},
    "assign": {"required": ["task_id"], "optional": ["files_affected", "depends_on"]},
}

# --- Attachment Constants (M2-3) ---

ATTACHMENT_TYPES = {"file_diff", "code_snippet", "task_list", "error_trace"}
MAX_ATTACHMENT_SIZE = 5000

# --- Escalation Constants (M1-4) ---

MAX_ESCALATION_COUNT = 3
ESCALATION_THRESHOLDS = {"urgent": 300, "high": 900}  # seconds

# --- Rate Limiting (M1-5) ---

RATE_LIMIT_PER_MINUTE = 20


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
    payload: Optional[dict] = None
    acknowledged_at: Optional[str] = None
    attachments: Optional[list[dict]] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        if d["metadata"] is None:
            d["metadata"] = {}
        if d["payload"] is None:
            d["payload"] = {}
        if d["attachments"] is None:
            d["attachments"] = []
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
        self._on_send: Optional[Callable] = None
        self._send_counts: dict[str, list[float]] = {}

    @property
    def on_send(self):
        return self._on_send

    @on_send.setter
    def on_send(self, callback):
        self._on_send = callback

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

        # Schema migration: add columns for protocol payloads, acknowledgments, attachments
        for col, default in [("payload", "'{}'"), ("acknowledged_at", "NULL"), ("attachments", "'[]'")]:
            try:
                conn.execute(f"SELECT {col} FROM messages LIMIT 0")
            except sqlite3.OperationalError:
                conn.execute(f"ALTER TABLE messages ADD COLUMN {col} TEXT DEFAULT {default}")

        # Dead letter queue table (M1-5)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dead_letters (
                id TEXT PRIMARY KEY,
                sender TEXT,
                recipient TEXT,
                msg_type TEXT,
                subject TEXT,
                body TEXT,
                priority TEXT,
                thread_id TEXT,
                created_at TEXT,
                metadata TEXT,
                payload TEXT,
                reason TEXT NOT NULL,
                dead_at TEXT NOT NULL
            )
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

    # --- Rate Limiting (M1-5) ---

    def _check_rate_limit(self, sender: str, priority: str) -> Optional[str]:
        """Check if sender is rate-limited. Returns reason string if limited, None if OK."""
        # Only rate-limit low and normal priority
        if priority in (MessagePriority.HIGH.value, MessagePriority.URGENT.value):
            return None

        now = time.time()
        timestamps = self._send_counts.get(sender, [])
        # Prune timestamps older than 60s
        timestamps = [t for t in timestamps if now - t < 60]
        self._send_counts[sender] = timestamps

        if len(timestamps) >= RATE_LIMIT_PER_MINUTE:
            return f"Rate limit exceeded: {sender} sent {len(timestamps)} messages in the last minute"
        return None

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
        payload: Optional[dict] = None,
        attachments: Optional[list[dict]] = None,
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
            payload: Optional typed protocol payload dict
            attachments: Optional list of attachment dicts

        Returns:
            The message ID (prefixed with 'dl-' if dead-lettered)
        """
        msg_id = str(uuid.uuid4())
        created_at = datetime.now().isoformat()

        # Validate and truncate attachments
        if attachments:
            validated = []
            for att in attachments:
                att_type = att.get("type", "")
                if att_type not in ATTACHMENT_TYPES:
                    continue  # skip invalid attachment types
                content = att.get("content", "")
                if len(content) > MAX_ATTACHMENT_SIZE:
                    att = {**att, "content": content[:MAX_ATTACHMENT_SIZE] + "\n... [truncated]"}
                validated.append(att)
            attachments = validated if validated else None

        # Rate limiting check
        rate_reason = self._check_rate_limit(sender, priority)
        if rate_reason:
            return self._dead_letter(
                msg_id, sender, recipient, msg_type, subject, body,
                priority, thread_id, created_at, metadata, payload, rate_reason,
            )

        conn = self._get_connection()
        conn.execute(
            """
            INSERT INTO messages (id, sender, recipient, msg_type, subject,
                                  body, priority, thread_id, read, created_at,
                                  metadata, payload, acknowledged_at, attachments)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, NULL, ?)
            """,
            (
                msg_id, sender, recipient, msg_type, subject,
                body, priority, thread_id, created_at,
                json.dumps(metadata or {}),
                json.dumps(payload or {}),
                json.dumps(attachments or []),
            ),
        )
        conn.commit()

        # Track send timestamp for rate limiting
        self._send_counts.setdefault(sender, []).append(time.time())

        # Fire on_send callback for WebSocket push
        if self._on_send:
            try:
                msg = MailMessage(
                    id=msg_id, sender=sender, recipient=recipient,
                    msg_type=msg_type, subject=subject, body=body,
                    priority=priority, thread_id=thread_id, read=False,
                    created_at=created_at, metadata=metadata or {},
                    payload=payload, acknowledged_at=None, attachments=attachments,
                )
                self._on_send(msg)
            except Exception:
                pass

        return msg_id

    # --- Typed Protocol Send (M1-1) ---

    def send_protocol(
        self,
        sender: str,
        recipient: str,
        msg_type: str,
        subject: str,
        body: str = "",
        priority: str = MessagePriority.NORMAL.value,
        thread_id: Optional[str] = None,
        metadata: Optional[dict] = None,
        payload: Optional[dict] = None,
        attachments: Optional[list[dict]] = None,
    ) -> str:
        """Send a message with typed protocol payload validation.

        Validates payload against PAYLOAD_SCHEMAS if a schema exists for msg_type.
        Raises ValueError on missing required keys.
        """
        if payload and msg_type in PAYLOAD_SCHEMAS:
            schema = PAYLOAD_SCHEMAS[msg_type]
            for key in schema["required"]:
                if key not in payload:
                    raise ValueError(
                        f"Payload for '{msg_type}' requires key '{key}'. "
                        f"Required: {schema['required']}"
                    )
        return self.send(
            sender=sender, recipient=recipient, msg_type=msg_type,
            subject=subject, body=body, priority=priority,
            thread_id=thread_id, metadata=metadata,
            payload=payload, attachments=attachments,
        )

    # --- Acknowledge (M1-1) ---

    def acknowledge(self, message_id: str) -> bool:
        """Set acknowledged_at timestamp on a message."""
        conn = self._get_connection()
        now = datetime.now().isoformat()
        cursor = conn.execute(
            "UPDATE messages SET acknowledged_at = ? WHERE id = ?",
            (now, message_id),
        )
        conn.commit()
        return cursor.rowcount > 0

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

            # Parse new columns with fallback for pre-migration DBs
            payload = None
            acknowledged_at = None
            attachments = None
            try:
                payload_raw = row["payload"]
                if payload_raw:
                    payload = json.loads(payload_raw)
                    if not payload:  # empty dict → None for cleaner output
                        payload = None
            except (KeyError, json.JSONDecodeError, TypeError):
                pass
            try:
                acknowledged_at = row["acknowledged_at"]
            except (KeyError, TypeError):
                pass
            try:
                att_raw = row["attachments"]
                if att_raw:
                    attachments = json.loads(att_raw)
                    if not attachments:  # empty list → None
                        attachments = None
            except (KeyError, json.JSONDecodeError, TypeError):
                pass

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
                payload=payload,
                acknowledged_at=acknowledged_at,
                attachments=attachments,
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

    # --- Context Injection (M1-2) ---

    def format_for_injection(self, agent_name: str, max_messages: int = 10) -> str:
        """Format unread messages as human-readable text for agent prompt injection.

        Returns empty string if no unread. Marks formatted messages as read.
        """
        messages = self.get_messages(recipient=agent_name, unread_only=True, limit=max_messages)
        if not messages:
            return ""

        # Check if any thread has >5 messages — use summarization
        thread_counts: dict[str, int] = {}
        for m in messages:
            tid = m.thread_id or m.id
            thread_counts[tid] = thread_counts.get(tid, 0) + 1

        lines = [f"\n## Unread Mail ({len(messages)} messages)\n"]
        seen_threads: set[str] = set()

        for m in messages:
            tid = m.thread_id or m.id
            # If this thread has >5 msgs and we haven't summarized it yet, summarize
            if tid in thread_counts and thread_counts[tid] > 5 and tid not in seen_threads and m.thread_id:
                seen_threads.add(tid)
                lines.append(self.summarize_thread(tid))
                lines.append("")
                # Mark all in thread as read
                thread_msgs = self.get_messages(thread_id=tid, limit=1000)
                for tm in thread_msgs:
                    self.mark_read(tm.id)
                continue
            elif tid in seen_threads:
                # Already summarized this thread
                self.mark_read(m.id)
                continue

            priority_tag = f" [{m.priority.upper()}]" if m.priority in ("high", "urgent") else ""
            lines.append(f"--- From: {m.sender}{priority_tag} ({m.msg_type}) ---")
            lines.append(f"Subject: {m.subject}")
            if m.body:
                lines.append(m.body[:300])
            if m.payload:
                lines.append(f"Payload: {json.dumps(m.payload)}")
            if m.attachments:
                for att in m.attachments:
                    lines.append(f"[Attachment: {att.get('type', '?')}/{att.get('name', '?')}]")
            lines.append(f"[Message ID: {m.id}]")
            lines.append("")
            self.mark_read(m.id)

        return "\n".join(lines)

    # --- Reply with Auto-Routing (M1-3) ---

    def reply(
        self,
        original_message_id: str,
        body: str,
        sender: str,
        priority: Optional[str] = None,
        payload: Optional[dict] = None,
    ) -> str:
        """Reply to a message, auto-routing to the original sender.

        Thread ID is set to the original message's thread_id (or its own ID if no thread).
        """
        conn = self._get_connection()
        row = conn.execute(
            "SELECT * FROM messages WHERE id = ?", (original_message_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"Message {original_message_id!r} not found")

        thread_id = row["thread_id"] or original_message_id
        return self.send(
            sender=sender,
            recipient=row["sender"],
            msg_type=row["msg_type"],
            subject=f"Re: {row['subject']}",
            body=body,
            priority=priority or row["priority"],
            thread_id=thread_id,
            payload=payload,
        )

    def get_conversation(self, thread_id: str) -> list[MailMessage]:
        """Get all messages in a thread, chronological order."""
        msgs = self.get_messages(thread_id=thread_id, limit=1000)
        return list(reversed(msgs))  # get_messages returns newest-first

    # --- Smart Priority Escalation (M1-4) ---

    def check_escalations(self) -> list[str]:
        """Find unread messages past their escalation threshold, re-send with [REMINDER]."""
        conn = self._get_connection()
        now = datetime.now()
        reminder_ids = []

        for priority, threshold_s in ESCALATION_THRESHOLDS.items():
            rows = conn.execute(
                "SELECT * FROM messages WHERE read = 0 AND priority = ? AND created_at IS NOT NULL",
                (priority,),
            ).fetchall()

            for row in rows:
                try:
                    created = datetime.fromisoformat(row["created_at"])
                except (ValueError, TypeError):
                    continue

                if (now - created).total_seconds() < threshold_s:
                    continue

                meta = json.loads(row["metadata"] or "{}")
                esc_count = meta.get("escalation_count", 0)
                if esc_count >= MAX_ESCALATION_COUNT:
                    continue

                meta["escalation_count"] = esc_count + 1
                conn.execute(
                    "UPDATE messages SET metadata = ? WHERE id = ?",
                    (json.dumps(meta), row["id"]),
                )

                reminder_id = self.send(
                    sender=row["sender"],
                    recipient=row["recipient"],
                    msg_type=row["msg_type"],
                    subject=f"[REMINDER x{esc_count + 1}] {row['subject']}",
                    body=row["body"],
                    priority=row["priority"],
                    thread_id=row["thread_id"] or row["id"],
                )
                reminder_ids.append(reminder_id)

        conn.commit()
        return reminder_ids

    # --- Dead Letter Queue (M1-5) ---

    def _dead_letter(
        self,
        msg_id: str,
        sender: str,
        recipient: str,
        msg_type: str,
        subject: str,
        body: str,
        priority: str,
        thread_id: Optional[str],
        created_at: str,
        metadata: Optional[dict],
        payload: Optional[dict],
        reason: str,
    ) -> str:
        """Insert a message into the dead letter queue instead of the main table."""
        dl_id = f"dl-{msg_id}"
        conn = self._get_connection()
        conn.execute(
            """
            INSERT INTO dead_letters (id, sender, recipient, msg_type, subject,
                                      body, priority, thread_id, created_at,
                                      metadata, payload, reason, dead_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dl_id, sender, recipient, msg_type, subject,
                body, priority, thread_id, created_at,
                json.dumps(metadata or {}),
                json.dumps(payload or {}),
                reason,
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
        return dl_id

    def get_dead_letters(self, limit: int = 50) -> list[dict]:
        """Retrieve dead-lettered messages."""
        conn = self._get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM dead_letters ORDER BY dead_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        except sqlite3.OperationalError:
            return []

        results = []
        for row in rows:
            results.append({
                "id": row["id"],
                "sender": row["sender"],
                "recipient": row["recipient"],
                "msg_type": row["msg_type"],
                "subject": row["subject"],
                "body": row["body"],
                "priority": row["priority"],
                "thread_id": row["thread_id"],
                "created_at": row["created_at"],
                "reason": row["reason"],
                "dead_at": row["dead_at"],
            })
        return results

    def retry_dead_letter(self, dl_id: str) -> Optional[str]:
        """Retry a dead-lettered message by re-sending it."""
        conn = self._get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM dead_letters WHERE id = ?", (dl_id,)
            ).fetchone()
        except sqlite3.OperationalError:
            return None

        if not row:
            return None

        # Clear rate limit for this sender to allow retry
        sender = row["sender"]
        self._send_counts.pop(sender, None)

        payload = None
        try:
            payload = json.loads(row["payload"]) if row["payload"] else None
        except (json.JSONDecodeError, TypeError):
            pass

        metadata = None
        try:
            metadata = json.loads(row["metadata"]) if row["metadata"] else None
        except (json.JSONDecodeError, TypeError):
            pass

        msg_id = self.send(
            sender=sender,
            recipient=row["recipient"],
            msg_type=row["msg_type"],
            subject=row["subject"],
            body=row["body"],
            priority=row["priority"],
            thread_id=row["thread_id"],
            metadata=metadata,
            payload=payload,
        )

        # Remove from dead letters
        conn.execute("DELETE FROM dead_letters WHERE id = ?", (dl_id,))
        conn.commit()
        return msg_id

    # --- Conversation Summarization (M2-2) ---

    def summarize_thread(self, thread_id: str) -> str:
        """Summarize a conversation thread, keeping key messages and trimming the middle."""
        msgs = self.get_conversation(thread_id)
        if len(msgs) <= 5:
            return "\n".join(f"[{m.sender}] {m.subject}: {m.body[:200]}" for m in msgs)

        KEY_TYPES = {"worker_done", "merged", "merge_failed", "error", "escalation"}
        participants = set(m.sender for m in msgs)
        first = msgs[0]
        key_msgs = [m for m in msgs[1:-3] if m.msg_type in KEY_TYPES]
        last_3 = msgs[-3:]
        skipped = len(msgs) - 1 - len(key_msgs) - 3

        lines = [f"[Thread: {len(msgs)} msgs, {len(participants)} participants]"]
        lines.append(f"[{first.sender}] {first.subject}: {first.body[:200]}")
        if key_msgs:
            for m in key_msgs[:5]:
                lines.append(f"[{m.sender}] ({m.msg_type}) {m.subject}")
        if skipped > 0:
            lines.append(f"  ... {skipped} messages omitted ...")
        for m in last_3:
            lines.append(f"[{m.sender}] {m.subject}: {m.body[:200]}")
        return "\n".join(lines)

    # --- Analytics (M2-4) ---

    def get_analytics(self) -> dict:
        """Get comprehensive mail analytics including response times and bottlenecks."""
        conn = self._get_connection()
        stats = self.get_stats()

        # Top senders
        top_senders = {
            r["sender"]: r["cnt"]
            for r in conn.execute(
                "SELECT sender, COUNT(*) as cnt FROM messages GROUP BY sender ORDER BY cnt DESC LIMIT 10"
            ).fetchall()
        }

        # Unread by recipient (bottleneck detection)
        unread_by = {
            r["recipient"]: r["cnt"]
            for r in conn.execute(
                "SELECT recipient, COUNT(*) as cnt FROM messages WHERE read = 0 GROUP BY recipient"
            ).fetchall()
        }

        # Average response time (threads with replies)
        avg_response_s = None
        try:
            threads = conn.execute("""
                SELECT thread_id, MIN(created_at) as first_at
                FROM messages WHERE thread_id IS NOT NULL
                GROUP BY thread_id HAVING COUNT(*) > 1
            """).fetchall()
            deltas = []
            for t in threads[:50]:
                second = conn.execute(
                    "SELECT MIN(created_at) as at FROM messages WHERE thread_id = ? AND created_at > ?",
                    (t["thread_id"], t["first_at"]),
                ).fetchone()
                if second and second["at"]:
                    d = (datetime.fromisoformat(second["at"]) - datetime.fromisoformat(t["first_at"])).total_seconds()
                    deltas.append(d)
            if deltas:
                avg_response_s = sum(deltas) / len(deltas)
        except Exception:
            pass

        # Dead letter count
        dead_count = 0
        try:
            dead_count = conn.execute("SELECT COUNT(*) as cnt FROM dead_letters").fetchone()["cnt"]
        except (sqlite3.OperationalError, TypeError):
            pass

        return {
            **stats,
            "top_senders": top_senders,
            "unread_by_recipient": unread_by,
            "avg_response_time_seconds": avg_response_s,
            "dead_letter_count": dead_count,
        }
