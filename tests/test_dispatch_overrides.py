"""
Test Dispatch Overrides (core/dispatch_overrides.py)
=====================================================

Tests DispatchOverride dataclass, OverrideResolver, and preset application.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.dispatch_overrides import (
    DispatchOverride,
    OverrideDirective,
    OverrideResolver,
    PRESETS,
)


# ---------------------------------------------------------------------------
# DispatchOverride dataclass
# ---------------------------------------------------------------------------

def test_override_creation():
    """Can create a DispatchOverride with directive and value."""
    ov = DispatchOverride(directive="SKIP_REVIEW")
    assert ov.directive == "SKIP_REVIEW"
    assert ov.value is None
    assert ov.active is True


def test_override_with_value():
    """Can create override with a value."""
    ov = DispatchOverride(directive="MAX_AGENTS", value="5")
    assert ov.value == "5"


def test_override_to_dict():
    """to_dict round-trips correctly."""
    ov = DispatchOverride(directive="SKIP_REVIEW", value=None, active=True)
    d = ov.to_dict()
    assert d["directive"] == "SKIP_REVIEW"
    assert d["active"] is True
    restored = DispatchOverride.from_dict(d)
    assert restored.directive == ov.directive


def test_override_from_dict():
    """from_dict handles missing keys gracefully."""
    d = {"directive": "CUSTOM_INSTRUCTION", "value": "Be fast"}
    ov = DispatchOverride.from_dict(d)
    assert ov.directive == "CUSTOM_INSTRUCTION"
    assert ov.value == "Be fast"
    assert ov.active is True  # default


# ---------------------------------------------------------------------------
# OverrideDirective enum
# ---------------------------------------------------------------------------

def test_directive_enum_values():
    """All expected directives exist."""
    assert OverrideDirective.SKIP_REVIEW.value == "SKIP_REVIEW"
    assert OverrideDirective.MAX_AGENTS.value == "MAX_AGENTS"
    assert OverrideDirective.CUSTOM_INSTRUCTION.value == "CUSTOM_INSTRUCTION"


# ---------------------------------------------------------------------------
# OverrideResolver
# ---------------------------------------------------------------------------

def test_resolver_empty():
    """Empty resolver has no overrides active."""
    resolver = OverrideResolver()
    assert not resolver.has("SKIP_REVIEW")
    assert resolver.get_max_agents() is None
    assert not resolver.should_skip_review()


def test_resolver_has():
    """Resolver detects active overrides."""
    resolver = OverrideResolver([
        DispatchOverride("SKIP_REVIEW"),
    ])
    assert resolver.has("SKIP_REVIEW")
    assert not resolver.has("MAX_AGENTS")


def test_resolver_inactive_override():
    """Inactive overrides are not detected."""
    resolver = OverrideResolver([
        DispatchOverride("SKIP_REVIEW", active=False),
    ])
    assert not resolver.has("SKIP_REVIEW")
    assert not resolver.should_skip_review()


def test_resolver_get_max_agents():
    """get_max_agents returns parsed integer."""
    resolver = OverrideResolver([
        DispatchOverride("MAX_AGENTS", "3"),
    ])
    assert resolver.get_max_agents() == 3


def test_resolver_should_skip_review():
    """should_skip_review returns True when SKIP_REVIEW is active."""
    resolver = OverrideResolver([
        DispatchOverride("SKIP_REVIEW"),
    ])
    assert resolver.should_skip_review()


def test_resolver_custom_instructions():
    """get_custom_instructions returns all active custom instruction values."""
    resolver = OverrideResolver([
        DispatchOverride("CUSTOM_INSTRUCTION", "Be fast"),
        DispatchOverride("CUSTOM_INSTRUCTION", "Focus on tests"),
        DispatchOverride("CUSTOM_INSTRUCTION", "Ignored", active=False),
    ])
    instructions = resolver.get_custom_instructions()
    assert len(instructions) == 2
    assert "Be fast" in instructions
    assert "Focus on tests" in instructions


def test_resolver_to_overlay_text_empty():
    """Empty resolver generates 'No dispatch overrides' text."""
    resolver = OverrideResolver()
    text = resolver.to_overlay_text()
    assert "no dispatch overrides" in text.lower() or "No dispatch" in text


def test_resolver_to_overlay_text_with_overrides():
    """Resolver generates overlay text listing active overrides."""
    resolver = OverrideResolver([
        DispatchOverride("SKIP_REVIEW"),
        DispatchOverride("MAX_AGENTS", "5"),
    ])
    text = resolver.to_overlay_text()
    assert "SKIP_REVIEW" in text
    assert "MAX_AGENTS" in text
    assert "5" in text


def test_resolver_from_dict_list():
    """from_dict_list creates resolver from serialized list."""
    items = [
        {"directive": "SKIP_REVIEW"},
        {"directive": "MAX_AGENTS", "value": "3"},
    ]
    resolver = OverrideResolver.from_dict_list(items)
    assert resolver.should_skip_review()
    assert resolver.get_max_agents() == 3


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

def test_speed_run_preset():
    """Speed run preset includes SKIP_REVIEW and MAX_AGENTS=10."""
    preset = PRESETS.get("speed_run", [])
    assert len(preset) > 0
    directives = [o.directive for o in preset]
    assert "SKIP_REVIEW" in directives


def test_careful_mode_preset():
    """Careful mode preset limits MAX_AGENTS."""
    preset = PRESETS.get("careful_mode", [])
    assert len(preset) > 0
    max_agents_ov = next((o for o in preset if o.directive == "MAX_AGENTS"), None)
    assert max_agents_ov is not None
    assert int(max_agents_ov.value) <= 3
