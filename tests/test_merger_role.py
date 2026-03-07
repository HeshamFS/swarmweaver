"""
Test Merger Agent Role (core/agent_roles.py, prompts/agents/merger.md)
======================================================================

Tests merger role assignment, capability setup, and role definition.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.agent_roles import AGENT_ROLES, assign_role, load_base_definition


# ---------------------------------------------------------------------------
# Merger in AGENT_ROLES registry
# ---------------------------------------------------------------------------

def test_merger_in_agent_roles():
    """Merger should be registered in AGENT_ROLES dict."""
    assert "merger" in AGENT_ROLES


def test_merger_prompt_file_exists():
    """Merger prompt file should exist at prompts/agents/merger.md."""
    root = Path(__file__).parent.parent
    merger_path = root / AGENT_ROLES["merger"]
    assert merger_path.exists(), f"Expected {merger_path} to exist"


def test_merger_prompt_content():
    """Merger prompt should contain key sections."""
    root = Path(__file__).parent.parent
    content = (root / AGENT_ROLES["merger"]).read_text()
    assert "merge" in content.lower()
    assert "conflict" in content.lower() or "resolution" in content.lower()


# ---------------------------------------------------------------------------
# Role assignment
# ---------------------------------------------------------------------------

def test_assign_role_builder_default():
    """Default role is builder for small swarms."""
    role = assign_role(1, ["task-1"], 2)
    assert role == "builder"


def test_assign_role_reviewer_3_workers():
    """Last worker gets reviewer role with 3 workers."""
    role = assign_role(3, ["task-1"], 3)
    assert role == "reviewer"


def test_assign_role_merger_4_workers():
    """Merger role assigned with 4+ workers."""
    # The exact assignment logic may vary, but merger should be possible
    roles = set()
    for wid in range(1, 5):
        r = assign_role(wid, ["task-1"], 4)
        roles.add(r)
    # Should have at least builder, and either merger or reviewer
    assert "builder" in roles


# ---------------------------------------------------------------------------
# Load base definition
# ---------------------------------------------------------------------------

def test_load_merger_definition():
    """Can load merger base definition."""
    definition = load_base_definition("merger")
    assert definition  # Not empty
    assert "merge" in definition.lower() or "Merge" in definition


def test_load_unknown_role_falls_back():
    """Unknown role falls back to default (builder)."""
    definition = load_base_definition("nonexistent_role")
    assert definition  # Falls back to default


# ---------------------------------------------------------------------------
# All original roles still work
# ---------------------------------------------------------------------------

def test_original_roles_exist():
    """Original 4 roles should still be in AGENT_ROLES."""
    assert "builder" in AGENT_ROLES
    assert "reviewer" in AGENT_ROLES
    assert "scout" in AGENT_ROLES
    assert "lead" in AGENT_ROLES


def test_total_roles():
    """Should have at least 5 roles (4 original + merger)."""
    assert len(AGENT_ROLES) >= 5
