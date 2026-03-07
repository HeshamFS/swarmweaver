"""
Test Outcome Tracking for Memory (features/memory.py)
======================================================

Tests record_outcome(), relevance_score adjustment, and
outcome fields on MemoryEntry.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from features.memory import AgentMemory, MemoryEntry


# ---------------------------------------------------------------------------
# MemoryEntry — new outcome fields
# ---------------------------------------------------------------------------

def test_memory_entry_has_outcome_fields():
    """MemoryEntry should have outcome, outcome_count, success_count."""
    entry = MemoryEntry(
        id="test",
        category="pattern",
        content="Test content",
        tags=["test"],
        project_source="test_project",
        created_at="2026-01-01",
    )
    assert hasattr(entry, "outcome")
    assert hasattr(entry, "outcome_count")
    assert hasattr(entry, "success_count")


def test_memory_entry_default_outcome():
    """Default outcome fields should be empty/zero."""
    entry = MemoryEntry(
        id="test",
        category="pattern",
        content="Test",
        tags=[],
        project_source="",
        created_at="2026-01-01",
    )
    assert entry.outcome == ""
    assert entry.outcome_count == 0
    assert entry.success_count == 0


# ---------------------------------------------------------------------------
# AgentMemory — record_outcome
# ---------------------------------------------------------------------------

def test_record_outcome_success(monkeypatch, tmp_path):
    """Recording success increases success_count and adjusts relevance."""
    # Redirect memory storage to tmp
    monkeypatch.setenv("HOME", str(tmp_path))
    mem_dir = tmp_path / ".swarmweaver" / "memory"
    mem_dir.mkdir(parents=True)
    (mem_dir / "memories.json").write_text("[]")

    memory = AgentMemory()
    memory.memory_dir = mem_dir
    memory.memory_file = mem_dir / "memories.json"

    mid = memory.add(
        category="pattern",
        content="Always run tests before commit",
        tags=["testing"],
        project_source="test_project",
    )

    result = memory.record_outcome(mid, "success")
    assert result is True

    entry = memory.get_by_id(mid)
    assert entry is not None
    assert entry.outcome == "success"
    assert entry.outcome_count == 1
    assert entry.success_count == 1
    assert entry.relevance_score > 1.0  # Boosted


def test_record_outcome_failure(monkeypatch, tmp_path):
    """Recording failure decreases relevance."""
    monkeypatch.setenv("HOME", str(tmp_path))
    mem_dir = tmp_path / ".swarmweaver" / "memory"
    mem_dir.mkdir(parents=True)
    (mem_dir / "memories.json").write_text("[]")

    memory = AgentMemory()
    memory.memory_dir = mem_dir
    memory.memory_file = mem_dir / "memories.json"

    mid = memory.add(
        category="pattern",
        content="Use global state for caching",
        tags=["caching"],
        project_source="test_project",
    )

    memory.record_outcome(mid, "failure")

    entry = memory.get_by_id(mid)
    assert entry is not None
    assert entry.outcome == "failure"
    assert entry.outcome_count == 1
    assert entry.success_count == 0
    assert entry.relevance_score < 1.0  # Decreased


def test_record_outcome_partial(monkeypatch, tmp_path):
    """Recording partial counts as half success."""
    monkeypatch.setenv("HOME", str(tmp_path))
    mem_dir = tmp_path / ".swarmweaver" / "memory"
    mem_dir.mkdir(parents=True)
    (mem_dir / "memories.json").write_text("[]")

    memory = AgentMemory()
    memory.memory_dir = mem_dir
    memory.memory_file = mem_dir / "memories.json"

    mid = memory.add(
        category="pattern",
        content="Partial test",
        tags=[],
        project_source="",
    )

    memory.record_outcome(mid, "partial")

    entry = memory.get_by_id(mid)
    assert entry is not None
    assert entry.outcome_count == 1
    assert entry.success_count == 0.5


def test_record_outcome_nonexistent(monkeypatch, tmp_path):
    """Recording outcome for nonexistent ID returns False."""
    monkeypatch.setenv("HOME", str(tmp_path))
    mem_dir = tmp_path / ".swarmweaver" / "memory"
    mem_dir.mkdir(parents=True)
    (mem_dir / "memories.json").write_text("[]")

    memory = AgentMemory()
    memory.memory_dir = mem_dir
    memory.memory_file = mem_dir / "memories.json"

    result = memory.record_outcome("nonexistent_id", "success")
    assert result is False


def test_record_multiple_outcomes(monkeypatch, tmp_path):
    """Multiple outcomes accumulate correctly."""
    monkeypatch.setenv("HOME", str(tmp_path))
    mem_dir = tmp_path / ".swarmweaver" / "memory"
    mem_dir.mkdir(parents=True)
    (mem_dir / "memories.json").write_text("[]")

    memory = AgentMemory()
    memory.memory_dir = mem_dir
    memory.memory_file = mem_dir / "memories.json"

    mid = memory.add("pattern", "Multi-outcome test", ["test"], "")

    memory.record_outcome(mid, "success")
    memory.record_outcome(mid, "success")
    memory.record_outcome(mid, "failure")
    memory.record_outcome(mid, "success")

    entry = memory.get_by_id(mid)
    assert entry.outcome_count == 4
    assert entry.success_count == 3
    # 3/4 = 0.75 success rate → relevance = 0.5 + 0.75 = 1.25
    assert 1.1 < entry.relevance_score < 1.4


# ---------------------------------------------------------------------------
# AgentMemory — get_by_id
# ---------------------------------------------------------------------------

def test_get_by_id_exists(monkeypatch, tmp_path):
    """get_by_id returns the entry when it exists."""
    monkeypatch.setenv("HOME", str(tmp_path))
    mem_dir = tmp_path / ".swarmweaver" / "memory"
    mem_dir.mkdir(parents=True)
    (mem_dir / "memories.json").write_text("[]")

    memory = AgentMemory()
    memory.memory_dir = mem_dir
    memory.memory_file = mem_dir / "memories.json"

    mid = memory.add("pattern", "Find me", ["test"], "")
    entry = memory.get_by_id(mid)
    assert entry is not None
    assert entry.content == "Find me"


def test_get_by_id_not_found(monkeypatch, tmp_path):
    """get_by_id returns None for unknown ID."""
    monkeypatch.setenv("HOME", str(tmp_path))
    mem_dir = tmp_path / ".swarmweaver" / "memory"
    mem_dir.mkdir(parents=True)
    (mem_dir / "memories.json").write_text("[]")

    memory = AgentMemory()
    memory.memory_dir = mem_dir
    memory.memory_file = mem_dir / "memories.json"

    entry = memory.get_by_id("does_not_exist")
    assert entry is None
