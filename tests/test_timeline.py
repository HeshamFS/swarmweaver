"""
Test Cross-Agent Timeline (services/timeline.py)
===================================================

Tests the CrossAgentTimeline class that merges events from audit logs
(NDJSON), EventStore, and MailStore into a unified chronological stream.

Uses tmp_path fixture to create temporary audit.log files with sample entries.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.timeline import CrossAgentTimeline


def _write_audit_log(project_dir: Path, entries: list[dict]) -> Path:
    """Helper: write NDJSON audit log entries to project_dir/.swarmweaver/audit.log."""
    swarmweaver_dir = project_dir / ".swarmweaver"
    swarmweaver_dir.mkdir(parents=True, exist_ok=True)
    audit_path = swarmweaver_dir / "audit.log"
    lines = [json.dumps(e) for e in entries]
    audit_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return audit_path


SAMPLE_ENTRIES = [
    {
        "timestamp": "2025-06-01T10:00:00",
        "agent_name": "builder-1",
        "tool_name": "Edit",
        "is_error": False,
    },
    {
        "timestamp": "2025-06-01T10:01:00",
        "agent_name": "builder-1",
        "tool_name": "Bash",
        "is_error": False,
    },
    {
        "timestamp": "2025-06-01T10:02:00",
        "agent_name": "scout-1",
        "tool_name": "Read",
        "is_error": True,
    },
    {
        "timestamp": "2025-06-01T10:03:00",
        "agent_name": "builder-1",
        "tool_name": "Write",
        "is_error": False,
    },
    {
        "timestamp": "2025-06-01T10:04:00",
        "agent_name": "scout-1",
        "tool_name": "Grep",
        "is_error": False,
    },
]


# ---------------------------------------------------------------------------
# get_timeline() — empty / basic
# ---------------------------------------------------------------------------

def test_get_timeline_empty_when_no_sources(tmp_path):
    """Returns empty list when project_dir has no audit.log or databases."""
    tl = CrossAgentTimeline()
    result = tl.get_timeline(tmp_path)
    assert result == []


def test_load_audit_log_parses_valid_ndjson(tmp_path):
    """_load_audit_log correctly parses valid NDJSON entries."""
    _write_audit_log(tmp_path, SAMPLE_ENTRIES)
    tl = CrossAgentTimeline()
    events = tl._load_audit_log(tmp_path, since=None, agent_filter=None)
    assert len(events) == 5
    assert all(e["source"] == "audit_log" for e in events)


def test_load_audit_log_skips_invalid_json_lines(tmp_path):
    """Invalid JSON lines in audit.log are silently skipped."""
    swarmweaver_dir = tmp_path / ".swarmweaver"
    swarmweaver_dir.mkdir(parents=True, exist_ok=True)
    audit_path = swarmweaver_dir / "audit.log"
    lines = [
        json.dumps(SAMPLE_ENTRIES[0]),
        "THIS IS NOT VALID JSON {{{",
        "",  # blank line
        json.dumps(SAMPLE_ENTRIES[1]),
    ]
    audit_path.write_text("\n".join(lines), encoding="utf-8")

    tl = CrossAgentTimeline()
    events = tl._load_audit_log(tmp_path, since=None, agent_filter=None)
    assert len(events) == 2


# ---------------------------------------------------------------------------
# get_timeline() — filtering
# ---------------------------------------------------------------------------

def test_get_timeline_respects_limit(tmp_path):
    """Returned events are capped at the limit parameter."""
    _write_audit_log(tmp_path, SAMPLE_ENTRIES)
    tl = CrossAgentTimeline()
    result = tl.get_timeline(tmp_path, limit=2)
    assert len(result) == 2


def test_get_timeline_filters_by_since(tmp_path):
    """Only events after the `since` timestamp are returned."""
    _write_audit_log(tmp_path, SAMPLE_ENTRIES)
    tl = CrossAgentTimeline()
    result = tl.get_timeline(tmp_path, since="2025-06-01T10:02:30")
    # Only entries at 10:03 and 10:04 should pass
    assert len(result) == 2
    for ev in result:
        assert ev["timestamp"] >= "2025-06-01T10:02:30"


def test_get_timeline_filters_by_agent(tmp_path):
    """Only events from the specified agent_filter are returned."""
    _write_audit_log(tmp_path, SAMPLE_ENTRIES)
    tl = CrossAgentTimeline()
    result = tl.get_timeline(tmp_path, agent_filter="scout-1")
    assert len(result) == 2
    assert all(ev["agent"] == "scout-1" for ev in result)


# ---------------------------------------------------------------------------
# Sorting and stats
# ---------------------------------------------------------------------------

def test_timeline_events_sorted_newest_first(tmp_path):
    """Events are returned sorted by timestamp descending (newest first)."""
    _write_audit_log(tmp_path, SAMPLE_ENTRIES)
    tl = CrossAgentTimeline()
    result = tl.get_timeline(tmp_path)
    timestamps = [ev["timestamp"] for ev in result]
    assert timestamps == sorted(timestamps, reverse=True)


def test_get_timeline_stats_computes_correct_counts(tmp_path):
    """get_timeline_stats returns correct by_type and by_agent counts."""
    _write_audit_log(tmp_path, SAMPLE_ENTRIES)
    tl = CrossAgentTimeline()
    stats = tl.get_timeline_stats(tmp_path)

    assert stats["total_events"] == 5

    # 4 tool_call entries, 1 error entry
    assert stats["events_by_type"]["audit:tool_call"] == 4
    assert stats["events_by_type"]["audit:error"] == 1

    # builder-1 has 3 entries, scout-1 has 2
    assert stats["events_by_agent"]["builder-1"] == 3
    assert stats["events_by_agent"]["scout-1"] == 2

    # Time range
    assert stats["time_range"]["earliest"] == "2025-06-01T10:00:00"
    assert stats["time_range"]["latest"] == "2025-06-01T10:04:00"
