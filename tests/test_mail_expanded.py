"""
Test Expanded Message Types (state/mail.py)
=============================================

Tests the 6 new MessageType values and their integration with
swarm dispatch, merge results, and watchdog escalation.

Also covers Sprint M1/M2/M3 enhancements:
  - Schema migration, send_protocol validation, format_for_injection
  - Reply auto-routing, escalation, dead letters, rate limiting
  - on_send callback, summarize_thread, attachments, analytics
  - CLI commands
"""

import json
import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from state.mail import (
    ATTACHMENT_TYPES,
    ESCALATION_THRESHOLDS,
    MAX_ATTACHMENT_SIZE,
    MAX_ESCALATION_COUNT,
    PAYLOAD_SCHEMAS,
    RATE_LIMIT_PER_MINUTE,
    MailMessage,
    MailStore,
    MessagePriority,
    MessageType,
)


# ---------------------------------------------------------------------------
# New MessageType enum values
# ---------------------------------------------------------------------------

def test_dispatch_type_exists():
    """DISPATCH message type should exist."""
    assert hasattr(MessageType, "DISPATCH")
    assert MessageType.DISPATCH.value == "dispatch"


def test_assign_type_exists():
    """ASSIGN message type should exist."""
    assert hasattr(MessageType, "ASSIGN")
    assert MessageType.ASSIGN.value == "assign"


def test_escalation_type_exists():
    """ESCALATION message type should exist."""
    assert hasattr(MessageType, "ESCALATION")
    assert MessageType.ESCALATION.value == "escalation"


def test_health_check_type_exists():
    """HEALTH_CHECK message type should exist."""
    assert hasattr(MessageType, "HEALTH_CHECK")
    assert MessageType.HEALTH_CHECK.value == "health_check"


def test_merged_type_exists():
    """MERGED message type should exist."""
    assert hasattr(MessageType, "MERGED")
    assert MessageType.MERGED.value == "merged"


def test_merge_failed_type_exists():
    """MERGE_FAILED message type should exist."""
    assert hasattr(MessageType, "MERGE_FAILED")
    assert MessageType.MERGE_FAILED.value == "merge_failed"


# ---------------------------------------------------------------------------
# All original types still exist
# ---------------------------------------------------------------------------

def test_original_types_preserved():
    """Original 6 types should still be present."""
    assert MessageType.STATUS.value == "status"
    assert MessageType.QUESTION.value == "question"
    assert MessageType.RESULT.value == "result"
    assert MessageType.ERROR.value == "error"
    assert MessageType.WORKER_DONE.value == "worker_done"
    assert MessageType.MERGE_READY.value == "merge_ready"


def test_total_message_types():
    """Should have at least 12 message types (6 original + 6 new)."""
    values = [mt.value for mt in MessageType]
    assert len(values) >= 12


# ---------------------------------------------------------------------------
# MailStore sends/receives new types
# ---------------------------------------------------------------------------

def test_send_dispatch_message(tmp_path):
    """MailStore should accept DISPATCH type messages."""
    store = MailStore(tmp_path)
    store.initialize()
    msg_id = store.send(
        sender="orchestrator",
        recipient="@all",
        msg_type=MessageType.DISPATCH.value,
        subject="Worker 1 dispatched",
        body="Tasks: [task-1], Role: builder",
        metadata={"worker_id": 1, "task_ids": ["task-1"], "role": "builder"},
    )
    assert msg_id
    messages = store.get_messages(msg_type=MessageType.DISPATCH.value)
    assert len(messages) >= 1
    assert messages[0].msg_type == "dispatch"


def test_send_escalation_message(tmp_path):
    """MailStore should accept ESCALATION type messages."""
    store = MailStore(tmp_path)
    store.initialize()
    msg_id = store.send(
        sender="watchdog",
        recipient="orchestrator",
        msg_type=MessageType.ESCALATION.value,
        subject="Worker 2 stalled",
        body="Worker stalled for 300s",
        priority=MessagePriority.URGENT.value,
        metadata={"worker_id": 2, "elapsed_seconds": 300},
    )
    assert msg_id
    messages = store.get_messages(
        recipient="orchestrator",
        msg_type=MessageType.ESCALATION.value,
    )
    assert len(messages) >= 1
    assert messages[0].priority == "urgent"


def test_send_merged_message(tmp_path):
    """MailStore should accept MERGED type messages."""
    store = MailStore(tmp_path)
    store.initialize()
    msg_id = store.send(
        sender="orchestrator",
        recipient="@all",
        msg_type=MessageType.MERGED.value,
        subject="Worker 1 branch merged",
        body="Branch swarm/worker-1 merged (tier 1)",
        metadata={"worker_id": 1, "branch": "swarm/worker-1", "tier": 1},
    )
    assert msg_id
    messages = store.get_messages(msg_type=MessageType.MERGED.value)
    assert len(messages) >= 1


def test_send_merge_failed_message(tmp_path):
    """MailStore should accept MERGE_FAILED type messages."""
    store = MailStore(tmp_path)
    store.initialize()
    msg_id = store.send(
        sender="orchestrator",
        recipient="@all",
        msg_type=MessageType.MERGE_FAILED.value,
        subject="Worker 3 merge failed",
        body="Conflict in src/main.py",
        priority=MessagePriority.HIGH.value,
    )
    assert msg_id
    messages = store.get_messages(msg_type=MessageType.MERGE_FAILED.value)
    assert len(messages) >= 1
    assert messages[0].priority == "high"


# ---------------------------------------------------------------------------
# Sprint M1/M2/M3 Tests
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_store(tmp_path):
    """Create and initialize a temporary MailStore."""
    store = MailStore(tmp_path)
    store.initialize()
    yield store
    store.close()


# --- M1-1: Schema migration, payload, send_protocol, acknowledge ---


class TestSchemaMigration:
    def test_new_columns_exist(self, tmp_store):
        conn = tmp_store._get_connection()
        conn.execute("SELECT payload, acknowledged_at, attachments FROM messages LIMIT 0")

    def test_dead_letters_table_exists(self, tmp_store):
        conn = tmp_store._get_connection()
        conn.execute("SELECT * FROM dead_letters LIMIT 0")

    def test_migration_idempotent(self, tmp_store):
        tmp_store.initialize()
        conn = tmp_store._get_connection()
        conn.execute("SELECT payload FROM messages LIMIT 0")

    def test_migration_on_existing_db(self, tmp_path):
        import sqlite3
        db_path = tmp_path / ".swarmweaver" / "mail.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE messages (
                id TEXT PRIMARY KEY, sender TEXT, recipient TEXT,
                msg_type TEXT, subject TEXT, body TEXT DEFAULT '',
                priority TEXT DEFAULT 'normal', thread_id TEXT,
                read INTEGER DEFAULT 0, created_at TEXT, metadata TEXT DEFAULT '{}'
            )
        """)
        conn.commit()
        conn.close()

        store = MailStore(tmp_path)
        store.initialize()
        c = store._get_connection()
        c.execute("SELECT payload, acknowledged_at, attachments FROM messages LIMIT 0")
        store.close()


class TestSendProtocol:
    def test_valid_payload(self, tmp_store):
        msg_id = tmp_store.send_protocol(
            sender="orchestrator", recipient="worker-1",
            msg_type="dispatch", subject="Go",
            payload={"task_ids": ["T1", "T2"]},
        )
        assert msg_id
        msgs = tmp_store.get_messages(recipient="worker-1")
        assert len(msgs) == 1
        assert msgs[0].payload == {"task_ids": ["T1", "T2"]}

    def test_missing_required_key(self, tmp_store):
        with pytest.raises(ValueError, match="requires key 'task_ids'"):
            tmp_store.send_protocol(
                sender="orchestrator", recipient="worker-1",
                msg_type="dispatch", subject="Go",
                payload={"file_scope": ["a.py"]},
            )

    def test_no_schema_passes(self, tmp_store):
        msg_id = tmp_store.send_protocol(
            sender="w1", recipient="orchestrator",
            msg_type="status", subject="OK",
            payload={"anything": True},
        )
        assert msg_id

    def test_optional_keys_accepted(self, tmp_store):
        msg_id = tmp_store.send_protocol(
            sender="o", recipient="w1",
            msg_type="dispatch", subject="Go",
            payload={"task_ids": ["T1"], "file_scope": ["a.py"], "role": "builder"},
        )
        assert msg_id


class TestAcknowledge:
    def test_acknowledge_sets_timestamp(self, tmp_store):
        msg_id = tmp_store.send(
            sender="w1", recipient="orchestrator",
            msg_type="status", subject="Done",
        )
        assert tmp_store.acknowledge(msg_id)
        msgs = tmp_store.get_messages(recipient="orchestrator")
        assert msgs[0].acknowledged_at is not None

    def test_acknowledge_nonexistent(self, tmp_store):
        assert not tmp_store.acknowledge("nonexistent-id")


# --- M1-2: format_for_injection ---


class TestFormatForInjection:
    def test_empty_when_no_unread(self, tmp_store):
        assert tmp_store.format_for_injection("worker-1") == ""

    def test_formats_unread_messages(self, tmp_store):
        tmp_store.send(
            sender="orchestrator", recipient="worker-1",
            msg_type="dispatch", subject="Task assignment",
            body="Do task T1", priority="high",
        )
        result = tmp_store.format_for_injection("worker-1")
        assert "Unread Mail" in result
        assert "orchestrator" in result
        assert "Task assignment" in result
        assert "[HIGH]" in result

    def test_marks_read_after_injection(self, tmp_store):
        tmp_store.send(sender="o", recipient="w1", msg_type="status", subject="Hi")
        tmp_store.format_for_injection("w1")
        assert tmp_store.format_for_injection("w1") == ""

    def test_includes_payload(self, tmp_store):
        tmp_store.send(
            sender="o", recipient="w1", msg_type="dispatch",
            subject="Go", payload={"task_ids": ["T1"]},
        )
        result = tmp_store.format_for_injection("w1")
        assert "task_ids" in result

    def test_respects_max_messages(self, tmp_store):
        for i in range(10):
            tmp_store.send(sender="o", recipient="w1", msg_type="status", subject=f"Msg {i}")
        result = tmp_store.format_for_injection("w1", max_messages=3)
        assert "3 messages" in result


# --- M1-3: reply() + get_conversation() ---


class TestReply:
    def test_reply_auto_routes(self, tmp_store):
        orig_id = tmp_store.send(
            sender="worker-1", recipient="orchestrator",
            msg_type="question", subject="How do I proceed?",
            body="Stuck on merge.",
        )
        reply_id = tmp_store.reply(orig_id, body="Try rebasing.", sender="orchestrator")
        msgs = tmp_store.get_messages(recipient="worker-1")
        assert len(msgs) == 1
        assert msgs[0].subject == "Re: How do I proceed?"
        assert msgs[0].thread_id == orig_id

    def test_reply_preserves_thread_id(self, tmp_store):
        thread = str(uuid.uuid4())
        orig_id = tmp_store.send(
            sender="w1", recipient="orchestrator",
            msg_type="question", subject="Q", thread_id=thread,
        )
        tmp_store.reply(orig_id, body="A", sender="orchestrator")
        msgs = tmp_store.get_messages(thread_id=thread)
        assert len(msgs) == 2

    def test_reply_nonexistent_raises(self, tmp_store):
        with pytest.raises(ValueError, match="not found"):
            tmp_store.reply("nonexistent", body="Hello", sender="x")


class TestGetConversation:
    def test_chronological_order(self, tmp_store):
        thread = str(uuid.uuid4())
        tmp_store.send(sender="a", recipient="b", msg_type="status",
                       subject="First", thread_id=thread)
        tmp_store.send(sender="b", recipient="a", msg_type="status",
                       subject="Second", thread_id=thread)
        tmp_store.send(sender="a", recipient="b", msg_type="status",
                       subject="Third", thread_id=thread)
        conv = tmp_store.get_conversation(thread)
        assert [m.subject for m in conv] == ["First", "Second", "Third"]


# --- M1-4: check_escalations() ---


class TestEscalation:
    def test_no_escalation_when_fresh(self, tmp_store):
        tmp_store.send(
            sender="w1", recipient="orchestrator",
            msg_type="error", subject="Fail", priority="urgent",
        )
        assert tmp_store.check_escalations() == []

    def test_escalation_fires_after_threshold(self, tmp_store):
        import sqlite3 as _sq
        conn = tmp_store._get_connection()
        old_time = (datetime.now() - timedelta(seconds=600)).isoformat()
        msg_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO messages (id, sender, recipient, msg_type, subject,
               body, priority, read, created_at, metadata, payload, attachments)
               VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, '{}', '{}', '[]')""",
            (msg_id, "w1", "orchestrator", "error", "Old fail",
             "", "urgent", old_time),
        )
        conn.commit()
        reminders = tmp_store.check_escalations()
        assert len(reminders) == 1

    def test_escalation_max_count(self, tmp_store):
        conn = tmp_store._get_connection()
        old_time = (datetime.now() - timedelta(seconds=600)).isoformat()
        msg_id = str(uuid.uuid4())
        meta = json.dumps({"escalation_count": MAX_ESCALATION_COUNT})
        conn.execute(
            """INSERT INTO messages (id, sender, recipient, msg_type, subject,
               body, priority, read, created_at, metadata, payload, attachments)
               VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, '{}', '[]')""",
            (msg_id, "w1", "orchestrator", "error", "Old fail",
             "", "urgent", old_time, meta),
        )
        conn.commit()
        assert tmp_store.check_escalations() == []


# --- M1-5: Dead letter queue + rate limiting ---


class TestRateLimiting:
    def test_rate_limit_triggers_dead_letter(self, tmp_store):
        for i in range(RATE_LIMIT_PER_MINUTE):
            tmp_store.send(sender="spammer", recipient="o",
                           msg_type="status", subject=f"Msg {i}")
        dl_id = tmp_store.send(sender="spammer", recipient="o",
                               msg_type="status", subject="Over limit")
        assert dl_id.startswith("dl-")

    def test_high_priority_bypasses_rate_limit(self, tmp_store):
        for i in range(RATE_LIMIT_PER_MINUTE):
            tmp_store.send(sender="s", recipient="o", msg_type="status", subject=f"M{i}")
        msg_id = tmp_store.send(sender="s", recipient="o",
                                msg_type="error", subject="Urgent!", priority="urgent")
        assert not msg_id.startswith("dl-")


class TestDeadLetterQueue:
    def test_get_dead_letters(self, tmp_store):
        for i in range(RATE_LIMIT_PER_MINUTE):
            tmp_store.send(sender="s", recipient="o", msg_type="status", subject=f"M{i}")
        tmp_store.send(sender="s", recipient="o", msg_type="status", subject="Dead")
        dead = tmp_store.get_dead_letters()
        assert len(dead) == 1
        assert "Rate limit" in dead[0]["reason"]

    def test_retry_dead_letter(self, tmp_store):
        for i in range(RATE_LIMIT_PER_MINUTE):
            tmp_store.send(sender="s", recipient="o", msg_type="status", subject=f"M{i}")
        dl_id = tmp_store.send(sender="s", recipient="o", msg_type="status", subject="Retry me")
        msg_id = tmp_store.retry_dead_letter(dl_id)
        assert msg_id is not None
        assert not msg_id.startswith("dl-")
        assert len(tmp_store.get_dead_letters()) == 0

    def test_retry_nonexistent_returns_none(self, tmp_store):
        assert tmp_store.retry_dead_letter("dl-nonexistent") is None


# --- M2-1: on_send callback ---


class TestOnSendCallback:
    def test_callback_fires_on_send(self, tmp_store):
        received = []
        tmp_store.on_send = lambda msg: received.append(msg)
        tmp_store.send(sender="a", recipient="b", msg_type="status", subject="Test")
        assert len(received) == 1
        assert isinstance(received[0], MailMessage)
        assert received[0].subject == "Test"

    def test_callback_exception_swallowed(self, tmp_store):
        tmp_store.on_send = lambda msg: (_ for _ in ()).throw(RuntimeError("boom"))
        msg_id = tmp_store.send(sender="a", recipient="b", msg_type="status", subject="OK")
        assert msg_id


# --- M2-2: summarize_thread() ---


class TestSummarizeThread:
    def test_short_thread_full_text(self, tmp_store):
        thread = str(uuid.uuid4())
        for i in range(3):
            tmp_store.send(sender=f"w{i}", recipient="o", msg_type="status",
                           subject=f"Msg {i}", body=f"Body {i}", thread_id=thread)
        summary = tmp_store.summarize_thread(thread)
        assert "Msg 0" in summary
        assert "Msg 2" in summary

    def test_long_thread_summarized(self, tmp_store):
        thread = str(uuid.uuid4())
        for i in range(10):
            msg_type = "worker_done" if i == 5 else "status"
            tmp_store.send(sender=f"w{i % 3}", recipient="o", msg_type=msg_type,
                           subject=f"Msg {i}", body=f"Body {i}", thread_id=thread)
        summary = tmp_store.summarize_thread(thread)
        assert "Thread:" in summary
        assert "omitted" in summary


# --- M2-3: Attachments ---


class TestAttachments:
    def test_send_with_attachments(self, tmp_store):
        tmp_store.send(
            sender="w1", recipient="o", msg_type="error", subject="Error trace",
            attachments=[{"type": "error_trace", "name": "trace.txt", "content": "line 1\nline 2"}],
        )
        msgs = tmp_store.get_messages(recipient="o")
        assert msgs[0].attachments is not None
        assert len(msgs[0].attachments) == 1
        assert msgs[0].attachments[0]["type"] == "error_trace"

    def test_invalid_attachment_type_skipped(self, tmp_store):
        tmp_store.send(
            sender="w1", recipient="o", msg_type="status", subject="Test",
            attachments=[
                {"type": "invalid_type", "name": "x", "content": "y"},
                {"type": "code_snippet", "name": "snippet.py", "content": "print(1)"},
            ],
        )
        msgs = tmp_store.get_messages(recipient="o")
        assert len(msgs[0].attachments) == 1

    def test_attachment_truncation(self, tmp_store):
        big_content = "x" * (MAX_ATTACHMENT_SIZE + 1000)
        tmp_store.send(
            sender="w1", recipient="o", msg_type="status", subject="Big",
            attachments=[{"type": "file_diff", "name": "big.diff", "content": big_content}],
        )
        msgs = tmp_store.get_messages(recipient="o")
        assert len(msgs[0].attachments[0]["content"]) <= MAX_ATTACHMENT_SIZE + 20


# --- M2-4: get_analytics() ---


class TestAnalytics:
    def test_basic_analytics(self, tmp_store):
        tmp_store.send(sender="w1", recipient="o", msg_type="status", subject="A")
        tmp_store.send(sender="w1", recipient="o", msg_type="status", subject="B")
        tmp_store.send(sender="w2", recipient="o", msg_type="error", subject="C")
        analytics = tmp_store.get_analytics()
        assert analytics["total"] == 3
        assert analytics["unread"] == 3
        assert "w1" in analytics["top_senders"]
        assert analytics["top_senders"]["w1"] == 2
        assert analytics["dead_letter_count"] == 0

    def test_avg_response_time(self, tmp_store):
        thread = str(uuid.uuid4())
        tmp_store.send(sender="w1", recipient="o", msg_type="question",
                       subject="Q", thread_id=thread)
        time.sleep(0.05)
        tmp_store.send(sender="o", recipient="w1", msg_type="question",
                       subject="A", thread_id=thread)
        analytics = tmp_store.get_analytics()
        assert analytics["avg_response_time_seconds"] is not None
        assert analytics["avg_response_time_seconds"] >= 0


# --- MailMessage.to_dict ---


class TestMailMessageToDict:
    def test_to_dict_defaults(self):
        m = MailMessage(id="test", sender="a", recipient="b",
                        msg_type="status", subject="S", body="B")
        d = m.to_dict()
        assert d["payload"] == {}
        assert d["attachments"] == []
        assert d["metadata"] == {}

    def test_to_dict_with_values(self):
        m = MailMessage(
            id="test", sender="a", recipient="b",
            msg_type="status", subject="S", body="B",
            payload={"key": "val"},
            attachments=[{"type": "file_diff", "name": "x", "content": "y"}],
        )
        d = m.to_dict()
        assert d["payload"] == {"key": "val"}
        assert len(d["attachments"]) == 1


# --- M3-3: CLI commands ---


class TestCLICommands:
    @pytest.fixture
    def cli_store(self, tmp_path):
        store = MailStore(tmp_path)
        store.initialize()
        store.send(sender="w1", recipient="orchestrator",
                   msg_type="status", subject="Worker 1 ready")
        store.send(sender="w2", recipient="orchestrator",
                   msg_type="error", subject="Worker 2 failed", priority="high")
        store.close()
        return tmp_path

    def test_mail_list(self, cli_store):
        from typer.testing import CliRunner
        from cli.commands.mail import mail_app
        runner = CliRunner()
        result = runner.invoke(mail_app, ["list", "--project-dir", str(cli_store)])
        assert result.exit_code == 0

    def test_mail_stats(self, cli_store):
        from typer.testing import CliRunner
        from cli.commands.mail import mail_app
        runner = CliRunner()
        result = runner.invoke(mail_app, ["stats", "--project-dir", str(cli_store)])
        assert result.exit_code == 0

    def test_mail_send(self, cli_store):
        from typer.testing import CliRunner
        from cli.commands.mail import mail_app
        runner = CliRunner()
        result = runner.invoke(mail_app, [
            "send", "--project-dir", str(cli_store),
            "--to", "w1", "--subject", "Hello from CLI",
        ])
        assert result.exit_code == 0
        assert "sent" in result.output.lower()

    def test_mail_read_all(self, cli_store):
        from typer.testing import CliRunner
        from cli.commands.mail import mail_app
        runner = CliRunner()
        result = runner.invoke(mail_app, [
            "read", "--project-dir", str(cli_store),
            "--all", "orchestrator",
        ])
        assert result.exit_code == 0
        assert "Marked" in result.output

    def test_mail_purge_with_yes(self, cli_store):
        from typer.testing import CliRunner
        from cli.commands.mail import mail_app
        runner = CliRunner()
        result = runner.invoke(mail_app, [
            "purge", "--project-dir", str(cli_store),
            "--days", "0", "--yes",
        ])
        assert result.exit_code == 0

    def test_mail_no_db(self, tmp_path):
        from typer.testing import CliRunner
        from cli.commands.mail import mail_app
        runner = CliRunner()
        result = runner.invoke(mail_app, ["list", "--project-dir", str(tmp_path)])
        assert result.exit_code == 1


# --- Mail injection hook ---


class TestMailInjectionHook:
    def test_hook_returns_empty_without_store(self):
        import asyncio
        from hooks.main_hooks import mail_injection_hook
        result = asyncio.run(mail_injection_hook({}, None, None))
        assert result == {}

    def test_hook_delivers_mail(self, tmp_store):
        import asyncio
        from hooks.main_hooks import mail_injection_hook, set_mail_store, MAIL_INJECT_EVERY_N, _mail_inject_counter

        set_mail_store(tmp_store, "worker-1")
        # Send a message to worker-1
        tmp_store.send(sender="orchestrator", recipient="worker-1",
                       msg_type="dispatch", subject="Test delivery")

        # Force counter to trigger on next call
        _mail_inject_counter.set(MAIL_INJECT_EVERY_N - 1)

        result = asyncio.run(mail_injection_hook({}, None, None))
        assert "message" in result
        assert "Test delivery" in result["message"]

    def test_hook_throttles(self, tmp_store):
        import asyncio
        from hooks.main_hooks import mail_injection_hook, set_mail_store, _mail_inject_counter

        set_mail_store(tmp_store, "worker-1")
        tmp_store.send(sender="o", recipient="worker-1", msg_type="status", subject="Hi")

        # Reset counter to 0 — should NOT trigger (not at boundary)
        _mail_inject_counter.set(0)
        result = asyncio.run(mail_injection_hook({}, None, None))
        assert result == {}
