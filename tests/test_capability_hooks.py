"""
Test Capability Enforcement Hooks (hooks/capability_hooks.py)
===============================================================

Tests the hook generation, deployment, and helper functions that enforce
role-based capability restrictions for scout, builder, reviewer, and lead agents.

Uses tmp_path fixture for deploy_hooks_to_worktree tests.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from hooks.capability_hooks import (
    generate_hooks_config,
    deploy_hooks_to_worktree,
    _is_read_only_command,
    _is_within_file_scope,
    _has_dangerous_bash,
    WRITE_TOOLS,
    BUILDER_BLOCKED_BASH,
)


# ---------------------------------------------------------------------------
# generate_hooks_config()
# ---------------------------------------------------------------------------

def test_scout_blocks_write_tools_and_sets_read_only():
    """Scout config blocks all WRITE_TOOLS and uses read_only bash mode."""
    config = generate_hooks_config("scout", [])
    assert config["blocked_tools"] == WRITE_TOOLS
    assert config["bash_mode"] == "read_only"
    assert "bash_allowed_patterns" in config
    assert "bash_blocked_patterns" in config


def test_builder_allows_writes_with_scoped_bash():
    """Builder config allows writes (empty blocked_tools) with scoped bash."""
    config = generate_hooks_config("builder", ["src/*"])
    assert config["blocked_tools"] == []
    assert config["bash_mode"] == "scoped"
    assert config["file_scope"] == ["src/*"]
    assert config["file_scope_enforced"] is True
    assert "bash_blocked_patterns" in config


def test_reviewer_blocks_write_tools():
    """Reviewer config blocks all WRITE_TOOLS (same as scout)."""
    config = generate_hooks_config("reviewer", [])
    assert config["blocked_tools"] == WRITE_TOOLS
    assert config["bash_mode"] == "read_only"


def test_lead_blocks_write_tools_allows_git_coordination():
    """Lead config blocks WRITE_TOOLS but allows git coordination commands."""
    config = generate_hooks_config("lead", [])
    assert config["blocked_tools"] == WRITE_TOOLS
    assert config["bash_mode"] == "coordination"
    assert "bash_allowed_patterns" in config
    # Lead should have writable_files for coordination
    assert "writable_files" in config
    assert "task_list.json" in config["writable_files"]


# ---------------------------------------------------------------------------
# deploy_hooks_to_worktree()
# ---------------------------------------------------------------------------

def test_deploy_hooks_creates_settings_json(tmp_path):
    """deploy_hooks_to_worktree creates .claude/settings.json in the worktree."""
    worktree = tmp_path / "worker-1"
    worktree.mkdir()

    settings_path = deploy_hooks_to_worktree(worktree, "builder", ["src/*"])

    assert settings_path.exists()
    assert settings_path.name == "settings.json"
    assert settings_path.parent.name == ".claude"

    config = json.loads(settings_path.read_text(encoding="utf-8"))
    assert config["capability"] == "builder"
    assert config["file_scope"] == ["src/*"]


# ---------------------------------------------------------------------------
# _is_read_only_command()
# ---------------------------------------------------------------------------

def test_is_read_only_command_accepts_ls():
    """'ls' is recognized as a read-only command."""
    assert _is_read_only_command("ls") is True
    assert _is_read_only_command("ls -la /tmp") is True


def test_is_read_only_command_rejects_rm():
    """'rm -rf' is NOT a read-only command."""
    assert _is_read_only_command("rm -rf /tmp/stuff") is False


def test_is_read_only_command_accepts_compound_readonly():
    """Compound commands where all segments are read-only pass."""
    assert _is_read_only_command("ls -la && cat file.txt") is True
    assert _is_read_only_command("git log | grep fix") is True


def test_is_read_only_command_rejects_compound_with_write():
    """Compound commands with any non-read-only segment fail."""
    assert _is_read_only_command("ls -la && rm -rf /tmp") is False


# ---------------------------------------------------------------------------
# _is_within_file_scope()
# ---------------------------------------------------------------------------

def test_is_within_file_scope_matches_glob():
    """File inside a glob scope pattern returns True."""
    assert _is_within_file_scope("src/app.py", ["src/*"]) is True


def test_is_within_file_scope_rejects_outside():
    """File outside all scope patterns returns False."""
    assert _is_within_file_scope("tests/test.py", ["src/*"]) is False


def test_is_within_file_scope_empty_scope_allows_all():
    """Empty file_scope list means no restrictions (allows everything)."""
    assert _is_within_file_scope("anything/anywhere.py", []) is True


# ---------------------------------------------------------------------------
# _has_dangerous_bash()
# ---------------------------------------------------------------------------

def test_has_dangerous_bash_detects_blocked_pattern():
    """Commands matching BUILDER_BLOCKED_BASH return the matched pattern."""
    result = _has_dangerous_bash("git push origin main", BUILDER_BLOCKED_BASH)
    assert result is not None
    assert "git\\s+push" in result


def test_has_dangerous_bash_returns_none_for_safe_command():
    """Safe commands that match no blocked pattern return None."""
    result = _has_dangerous_bash("git status", BUILDER_BLOCKED_BASH)
    assert result is None


def test_has_dangerous_bash_detects_reset_hard():
    """'git reset --hard' is detected as dangerous."""
    result = _has_dangerous_bash("git reset --hard HEAD~1", BUILDER_BLOCKED_BASH)
    assert result is not None
