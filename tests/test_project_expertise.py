"""
Test Project-Scoped Expertise (features/project_expertise.py)
==============================================================

Tests ProjectExpertise CRUD, domain grouping, and search.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from features.project_expertise import ProjectExpertise, ExpertiseEntry


# ---------------------------------------------------------------------------
# ExpertiseEntry
# ---------------------------------------------------------------------------

def test_entry_creation():
    """ExpertiseEntry stores all fields."""
    entry = ExpertiseEntry(
        id="abc",
        content="Use pytest fixtures",
        category="convention",
        domain="python",
        tags=["testing"],
        source_file="tests/conftest.py",
    )
    assert entry.id == "abc"
    assert entry.category == "convention"
    assert entry.domain == "python"


def test_entry_to_dict():
    """ExpertiseEntry serializes to dict."""
    entry = ExpertiseEntry(id="x", content="test", category="pattern", domain="python")
    d = entry.to_dict()
    assert d["id"] == "x"
    assert d["content"] == "test"
    assert d["domain"] == "python"


def test_entry_from_dict():
    """ExpertiseEntry deserializes from dict."""
    d = {"id": "y", "content": "test", "category": "pattern", "domain": "typescript"}
    entry = ExpertiseEntry.from_dict(d)
    assert entry.id == "y"
    assert entry.domain == "typescript"


# ---------------------------------------------------------------------------
# ProjectExpertise — CRUD
# ---------------------------------------------------------------------------

def test_add_entry(tmp_path):
    """Can add an expertise entry."""
    pe = ProjectExpertise(tmp_path)
    entry_id = pe.add(
        content="Always use async/await for DB calls",
        category="convention",
        domain="python",
        tags=["database", "async"],
    )
    assert entry_id
    assert len(pe.get_all()) == 1


def test_add_multiple_entries(tmp_path):
    """Can add multiple entries."""
    pe = ProjectExpertise(tmp_path)
    pe.add("Pattern 1", "pattern", "python")
    pe.add("Pattern 2", "pattern", "typescript")
    pe.add("Pattern 3", "convention", "python")
    assert len(pe.get_all()) == 3


def test_get_by_domain(tmp_path):
    """Can filter entries by domain."""
    pe = ProjectExpertise(tmp_path)
    pe.add("Python pattern", "pattern", "python")
    pe.add("TS convention", "convention", "typescript")
    pe.add("Python convention", "convention", "python")

    py_entries = pe.get_by_domain("python")
    assert len(py_entries) == 2

    ts_entries = pe.get_by_domain("typescript")
    assert len(ts_entries) == 1


def test_get_domains(tmp_path):
    """Can list all domains."""
    pe = ProjectExpertise(tmp_path)
    pe.add("A", "pattern", "python")
    pe.add("B", "pattern", "typescript")
    pe.add("C", "pattern", "testing")

    domains = pe.get_domains()
    assert set(domains) == {"python", "typescript", "testing"}


def test_delete_entry(tmp_path):
    """Can delete an entry by ID."""
    pe = ProjectExpertise(tmp_path)
    eid = pe.add("Deletable", "pattern", "python")
    assert pe.delete(eid) is True
    assert len(pe.get_all()) == 0


def test_delete_nonexistent(tmp_path):
    """Deleting nonexistent entry returns False."""
    pe = ProjectExpertise(tmp_path)
    assert pe.delete("nonexistent") is False


# ---------------------------------------------------------------------------
# ProjectExpertise — search
# ---------------------------------------------------------------------------

def test_search_by_content(tmp_path):
    """Search finds entries by content match."""
    pe = ProjectExpertise(tmp_path)
    pe.add("Use pytest for testing", "convention", "python")
    pe.add("Use React hooks", "pattern", "typescript")

    results = pe.search("pytest")
    assert len(results) == 1
    assert "pytest" in results[0].content


def test_search_by_domain(tmp_path):
    """Search matches on domain."""
    pe = ProjectExpertise(tmp_path)
    pe.add("Some content", "pattern", "python")

    results = pe.search("python")
    assert len(results) >= 1


def test_search_empty_query(tmp_path):
    """Search with non-matching query returns empty."""
    pe = ProjectExpertise(tmp_path)
    pe.add("Something", "pattern", "python")

    results = pe.search("nonexistent_term_xyz")
    assert len(results) == 0


# ---------------------------------------------------------------------------
# ProjectExpertise — file scope matching
# ---------------------------------------------------------------------------

def test_get_for_file_scope(tmp_path):
    """Gets expertise relevant to file scope."""
    pe = ProjectExpertise(tmp_path)
    pe.add("Python convention", "convention", "python")
    pe.add("TS convention", "convention", "typescript")

    results = pe.get_for_file_scope(["src/main.py", "tests/test_main.py"])
    # Should match python and testing domains
    domains = {r.domain for r in results}
    assert "python" in domains


# ---------------------------------------------------------------------------
# ProjectExpertise — context string
# ---------------------------------------------------------------------------

def test_to_context_string_empty(tmp_path):
    """Empty expertise produces appropriate message."""
    pe = ProjectExpertise(tmp_path)
    text = pe.to_context_string()
    assert "no project" in text.lower() or "No project" in text


def test_to_context_string_with_entries(tmp_path):
    """Expertise entries are formatted for overlay injection."""
    pe = ProjectExpertise(tmp_path)
    pe.add("Always validate inputs", "convention", "python")
    pe.add("Use memo for expensive renders", "pattern", "typescript")

    text = pe.to_context_string()
    assert "Always validate inputs" in text
    assert "memo" in text


# ---------------------------------------------------------------------------
# Storage persistence
# ---------------------------------------------------------------------------

def test_persistence(tmp_path):
    """Entries persist across instances."""
    pe1 = ProjectExpertise(tmp_path)
    pe1.add("Persistent entry", "pattern", "python")

    pe2 = ProjectExpertise(tmp_path)
    entries = pe2.get_all()
    assert len(entries) == 1
    assert entries[0].content == "Persistent entry"
