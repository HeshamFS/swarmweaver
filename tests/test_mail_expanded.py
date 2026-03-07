"""
Test Expanded Message Types (state/mail.py)
=============================================

Tests the 6 new MessageType values and their integration with
swarm dispatch, merge results, and watchdog escalation.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from state.mail import MessageType, MessagePriority, MailStore


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
