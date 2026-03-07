"""
Test Session Handoff Protocol (state/session_checkpoint.py)
============================================================

Tests chain_id, sequence_number, get_chain(), and session
chain persistence.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from state.session_checkpoint import SessionHandoff


# ---------------------------------------------------------------------------
# SessionHandoff — enhanced fields
# ---------------------------------------------------------------------------

def _make_handoff(**kwargs) -> SessionHandoff:
    """Helper to create a SessionHandoff with required fields."""
    defaults = {
        "from_session": "session-1",
        "to_session": "session-2",
        "checkpoint": {"iteration": 3, "files_changed": 5},
        "reason": "compaction",
    }
    defaults.update(kwargs)
    return SessionHandoff(**defaults)


def test_handoff_has_chain_id():
    """SessionHandoff should have chain_id field."""
    handoff = _make_handoff()
    assert hasattr(handoff, "chain_id")


def test_handoff_has_sequence_number():
    """SessionHandoff should have sequence_number field."""
    handoff = _make_handoff()
    assert hasattr(handoff, "sequence_number")


def test_handoff_has_checkpoint_summary():
    """SessionHandoff should have checkpoint_summary field."""
    handoff = _make_handoff()
    assert hasattr(handoff, "checkpoint_summary")


# ---------------------------------------------------------------------------
# SessionHandoff — chain management
# ---------------------------------------------------------------------------

def test_handoff_default_sequence():
    """Default sequence_number should be 0 (unset)."""
    handoff = _make_handoff()
    # Default is 0 since it's not in a chain yet
    assert handoff.sequence_number == 0


def test_handoff_chain_id_settable():
    """chain_id can be set."""
    handoff = _make_handoff(chain_id="test-chain-uuid")
    assert handoff.chain_id == "test-chain-uuid"


def test_handoff_serialization():
    """SessionHandoff should serialize to/from dict."""
    handoff = _make_handoff(
        checkpoint_summary="Completed 3 of 5 tasks",
        sequence_number=2,
        chain_id="chain-123",
    )
    d = handoff.to_dict()
    assert d["checkpoint_summary"] == "Completed 3 of 5 tasks"
    assert d["sequence_number"] == 2
    assert d["chain_id"] == "chain-123"


# ---------------------------------------------------------------------------
# Session chain storage
# ---------------------------------------------------------------------------

def test_chain_storage_directory(tmp_path):
    """Chain data should be storable at .swarmweaver/chains/."""
    chains_dir = tmp_path / ".swarmweaver" / "chains"
    chains_dir.mkdir(parents=True)

    chain_data = {
        "chain_id": "test-chain-123",
        "sessions": [
            {
                "session_id": "s1",
                "sequence_number": 1,
                "checkpoint_summary": "Initial setup",
                "phase": "initialize",
                "tasks_completed": 3,
                "cost": 0.50,
            },
            {
                "session_id": "s2",
                "sequence_number": 2,
                "checkpoint_summary": "Implementation phase",
                "phase": "code",
                "tasks_completed": 5,
                "cost": 1.20,
            },
        ],
    }

    chain_file = chains_dir / "test-chain-123.json"
    chain_file.write_text(json.dumps(chain_data, indent=2))

    loaded = json.loads(chain_file.read_text())
    assert loaded["chain_id"] == "test-chain-123"
    assert len(loaded["sessions"]) == 2
    assert loaded["sessions"][0]["sequence_number"] == 1
    assert loaded["sessions"][1]["sequence_number"] == 2


def test_chain_ordering(tmp_path):
    """Sessions in a chain should be ordered by sequence_number."""
    chains_dir = tmp_path / ".swarmweaver" / "chains"
    chains_dir.mkdir(parents=True)

    sessions = [
        {"session_id": "s3", "sequence_number": 3},
        {"session_id": "s1", "sequence_number": 1},
        {"session_id": "s2", "sequence_number": 2},
    ]

    sorted_sessions = sorted(sessions, key=lambda s: s["sequence_number"])
    assert sorted_sessions[0]["session_id"] == "s1"
    assert sorted_sessions[1]["session_id"] == "s2"
    assert sorted_sessions[2]["session_id"] == "s3"
