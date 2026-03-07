"""
Test Spec Workflow Manager (features/spec_workflow.py)
========================================================

Tests the SpecManager class that manages task specification documents.
Specs are stored as markdown files with metadata sidecar (.meta.json).

Uses tmp_path fixture as the project directory.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from features.spec_workflow import SpecManager


# ---------------------------------------------------------------------------
# write_spec()
# ---------------------------------------------------------------------------

def test_write_spec_creates_md_file(tmp_path):
    """write_spec() creates the .md spec file in the specs directory."""
    mgr = SpecManager(tmp_path)
    spec_path = mgr.write_spec("TASK-001", "# My Spec\n\nRequirements here.", author="user")

    assert spec_path.exists()
    assert spec_path.name == "TASK-001.md"
    content = spec_path.read_text(encoding="utf-8")
    assert "# My Spec" in content
    assert "Requirements here." in content


def test_write_spec_creates_meta_json_sidecar(tmp_path):
    """write_spec() creates the .meta.json sidecar alongside the spec file."""
    mgr = SpecManager(tmp_path)
    mgr.write_spec("TASK-002", "Some content", author="builder-1")

    meta_path = tmp_path / ".swarmweaver" / "specs" / "TASK-002.meta.json"
    assert meta_path.exists()

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["task_id"] == "TASK-002"
    assert meta["author"] == "builder-1"
    assert meta["revisions"] == 1
    assert meta["size"] == len("Some content")
    assert "created_at" in meta
    assert "updated_at" in meta


def test_write_spec_increments_revision_on_update(tmp_path):
    """Calling write_spec() again for the same task_id increments the revision count."""
    mgr = SpecManager(tmp_path)
    mgr.write_spec("TASK-003", "Version 1", author="user")
    mgr.write_spec("TASK-003", "Version 2 with more detail", author="user")

    meta_path = tmp_path / ".swarmweaver" / "specs" / "TASK-003.meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["revisions"] == 2
    assert meta["size"] == len("Version 2 with more detail")


# ---------------------------------------------------------------------------
# read_spec()
# ---------------------------------------------------------------------------

def test_read_spec_returns_content_for_existing_spec(tmp_path):
    """read_spec() returns the markdown content for an existing spec."""
    mgr = SpecManager(tmp_path)
    mgr.write_spec("TASK-010", "# Feature X\n\nDetailed requirements.")

    content = mgr.read_spec("TASK-010")
    assert content is not None
    assert "# Feature X" in content
    assert "Detailed requirements." in content


def test_read_spec_returns_none_for_nonexistent(tmp_path):
    """read_spec() returns None when the spec file does not exist."""
    mgr = SpecManager(tmp_path)
    result = mgr.read_spec("TASK-MISSING")
    assert result is None


# ---------------------------------------------------------------------------
# list_specs()
# ---------------------------------------------------------------------------

def test_list_specs_returns_empty_when_no_specs(tmp_path):
    """list_specs() returns [] when no specs have been written."""
    mgr = SpecManager(tmp_path)
    result = mgr.list_specs()
    assert result == []


def test_list_specs_returns_all_specs_with_metadata(tmp_path):
    """list_specs() returns all specs with their metadata fields."""
    mgr = SpecManager(tmp_path)
    mgr.write_spec("TASK-A", "Spec A content", author="alice")
    mgr.write_spec("TASK-B", "Spec B content", author="bob")

    specs = mgr.list_specs()
    assert len(specs) == 2

    task_ids = [s["task_id"] for s in specs]
    assert "TASK-A" in task_ids
    assert "TASK-B" in task_ids

    for spec in specs:
        assert "author" in spec
        assert "created_at" in spec
        assert "updated_at" in spec
        assert "size" in spec
        assert "revisions" in spec


# ---------------------------------------------------------------------------
# Metadata tracking
# ---------------------------------------------------------------------------

def test_spec_metadata_tracks_author_and_timestamps(tmp_path):
    """Metadata sidecar correctly records author, created_at, and updated_at."""
    mgr = SpecManager(tmp_path)
    mgr.write_spec("TASK-META", "Initial content", author="lead-agent")

    meta_path = tmp_path / ".swarmweaver" / "specs" / "TASK-META.meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    assert meta["author"] == "lead-agent"
    assert meta["created_at"] != ""
    assert meta["updated_at"] != ""

    # Update the spec — created_at should stay the same, updated_at should change
    first_created = meta["created_at"]
    mgr.write_spec("TASK-META", "Updated content", author="lead-agent")

    meta2 = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta2["created_at"] == first_created
    # updated_at should be >= the original (same or later)
    assert meta2["updated_at"] >= first_created
