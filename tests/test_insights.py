"""
Test Session Insight Analyzer (services/insights.py)
======================================================

Tests the SessionInsightAnalyzer class that extracts tool usage profiles,
hot files, error patterns, and structured insights from audit.log files.

Uses tmp_path for temporary audit logs and overrides HOME to isolate
AgentMemory during record_to_memory tests.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.insights import SessionInsightAnalyzer


def _write_audit_log(project_dir: Path, entries: list[dict]) -> Path:
    """Helper: write NDJSON audit log entries to project_dir/.swarmweaver/audit.log."""
    swarmweaver_dir = project_dir / ".swarmweaver"
    swarmweaver_dir.mkdir(parents=True, exist_ok=True)
    audit_path = swarmweaver_dir / "audit.log"
    lines = [json.dumps(e) for e in entries]
    audit_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return audit_path


def _make_tool_entry(tool_name: str, is_error: bool = False, file_path: str = "") -> dict:
    """Helper: build a single audit log entry dict."""
    entry = {"tool_name": tool_name, "is_error": is_error}
    if file_path:
        entry["input"] = {"file_path": file_path}
    return entry


# ---------------------------------------------------------------------------
# analyze_audit_log() — empty / basic
# ---------------------------------------------------------------------------

def test_analyze_returns_empty_when_no_audit_log(tmp_path):
    """Returns zeroed InsightAnalysis when audit.log does not exist."""
    analyzer = SessionInsightAnalyzer(tmp_path)
    result = analyzer.analyze_audit_log()
    assert result.total_tool_calls == 0
    assert result.error_frequency == 0
    assert result.top_tools == []
    assert result.hot_files == []
    assert result.insights == []


def test_analyze_counts_tool_calls(tmp_path):
    """Correctly counts total tool calls and per-tool breakdown."""
    entries = [
        _make_tool_entry("Read"),
        _make_tool_entry("Read"),
        _make_tool_entry("Edit"),
        _make_tool_entry("Bash"),
        _make_tool_entry("Bash"),
        _make_tool_entry("Bash"),
    ]
    _write_audit_log(tmp_path, entries)

    analyzer = SessionInsightAnalyzer(tmp_path)
    result = analyzer.analyze_audit_log()

    assert result.total_tool_calls == 6
    # top_tools are sorted by count descending
    tool_names = [t["name"] for t in result.top_tools]
    assert tool_names[0] == "Bash"  # 3 calls
    assert result.top_tools[0]["count"] == 3


def test_analyze_counts_errors(tmp_path):
    """Correctly counts error entries."""
    entries = [
        _make_tool_entry("Read", is_error=False),
        _make_tool_entry("Bash", is_error=True),
        _make_tool_entry("Edit", is_error=True),
        _make_tool_entry("Read", is_error=False),
    ]
    _write_audit_log(tmp_path, entries)

    analyzer = SessionInsightAnalyzer(tmp_path)
    result = analyzer.analyze_audit_log()

    assert result.error_frequency == 2


def test_analyze_identifies_hot_files(tmp_path):
    """Files edited 3+ times appear in hot_files list."""
    hot_path = str(tmp_path / "src" / "app.py")
    cold_path = str(tmp_path / "src" / "utils.py")

    entries = [
        _make_tool_entry("Edit", file_path=hot_path),
        _make_tool_entry("Edit", file_path=hot_path),
        _make_tool_entry("Edit", file_path=hot_path),
        _make_tool_entry("Edit", file_path=hot_path),
        _make_tool_entry("Edit", file_path=cold_path),
        _make_tool_entry("Edit", file_path=cold_path),
    ]
    _write_audit_log(tmp_path, entries)

    analyzer = SessionInsightAnalyzer(tmp_path)
    result = analyzer.analyze_audit_log()

    hot_paths = [hf["path"] for hf in result.hot_files]
    # hot_path should appear (4 edits >= 3), cold_path should not (2 edits < 3)
    assert len(result.hot_files) >= 1
    # The hot file path is stored relative to project_dir if possible
    assert any(hf["edit_count"] >= 3 for hf in result.hot_files)
    # cold_path should NOT be in hot files
    cold_counts = [hf for hf in result.hot_files if hf["edit_count"] < 3]
    assert len(cold_counts) == 0


# ---------------------------------------------------------------------------
# Insight generation
# ---------------------------------------------------------------------------

def test_analyze_generates_high_error_rate_insight(tmp_path):
    """When >15% of tool calls are errors, a 'failure' insight is generated."""
    # 20 total calls, 5 errors = 25% error rate
    entries = []
    for _ in range(15):
        entries.append(_make_tool_entry("Read"))
    for _ in range(5):
        entries.append(_make_tool_entry("Bash", is_error=True))
    _write_audit_log(tmp_path, entries)

    analyzer = SessionInsightAnalyzer(tmp_path)
    result = analyzer.analyze_audit_log()

    failure_insights = [i for i in result.insights if i.insight_type == "failure"]
    assert len(failure_insights) >= 1
    assert "error rate" in failure_insights[0].content.lower()


def test_analyze_generates_hot_file_insights(tmp_path):
    """Hot files produce 'pattern' insights about modification frequency."""
    hot_path = str(tmp_path / "src" / "complex.py")
    entries = [_make_tool_entry("Edit", file_path=hot_path) for _ in range(5)]
    _write_audit_log(tmp_path, entries)

    analyzer = SessionInsightAnalyzer(tmp_path)
    result = analyzer.analyze_audit_log()

    pattern_insights = [i for i in result.insights if i.insight_type == "pattern"]
    assert len(pattern_insights) >= 1
    assert "hot file" in pattern_insights[0].content.lower()


def test_generate_insights_detects_heavy_bash_usage(tmp_path):
    """When Bash is >40% of tool calls, a 'convention' insight is generated."""
    entries = []
    # 6 Bash out of 10 total = 60%
    for _ in range(6):
        entries.append(_make_tool_entry("Bash"))
    for _ in range(4):
        entries.append(_make_tool_entry("Read"))
    _write_audit_log(tmp_path, entries)

    analyzer = SessionInsightAnalyzer(tmp_path)
    result = analyzer.analyze_audit_log()

    # Must have total_calls > 10 for the Bash insight, so add more entries
    # Actually, looking at the code: tool_counts.get("Bash", 0) > total_calls * 0.4
    # AND the high error rate check requires total_calls > 10
    # But the Bash check has no minimum — let's verify
    convention_insights = [i for i in result.insights if i.insight_type == "convention"]
    assert len(convention_insights) >= 1
    assert "bash" in convention_insights[0].content.lower()


# ---------------------------------------------------------------------------
# record_to_memory()
# ---------------------------------------------------------------------------

def test_record_to_memory_saves_insights(tmp_path, monkeypatch):
    """record_to_memory() writes insights to the AgentMemory store."""
    # Redirect HOME so AgentMemory writes to tmp_path instead of real home
    fake_home = tmp_path / "fakehome"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    # Also patch the module-level paths in features.memory
    import features.memory as mem_module
    monkeypatch.setattr(mem_module, "MEMORY_DIR", fake_home / ".swarmweaver" / "memory")
    monkeypatch.setattr(mem_module, "MEMORY_FILE", fake_home / ".swarmweaver" / "memory" / "memories.json")
    monkeypatch.setattr(mem_module, "DOMAINS_DIR", fake_home / ".swarmweaver" / "memory" / "domains")

    # Create an audit log with enough data to produce at least one insight
    entries = []
    for _ in range(15):
        entries.append(_make_tool_entry("Read"))
    for _ in range(5):
        entries.append(_make_tool_entry("Bash", is_error=True))
    _write_audit_log(tmp_path, entries)

    analyzer = SessionInsightAnalyzer(tmp_path)
    analysis = analyzer.analyze_audit_log()
    assert len(analysis.insights) > 0

    count = analyzer.record_to_memory(analysis, project_source="test-project")
    assert count > 0

    # Verify memory files were created
    memory_dir = fake_home / ".swarmweaver" / "memory"
    assert memory_dir.exists()
