"""Dispatch override system for fine-tuning agent behavior per-run."""
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class OverrideDirective(str, Enum):
    SKIP_REVIEW = "SKIP_REVIEW"
    FOCUS_PERFORMANCE = "FOCUS_PERFORMANCE"
    MINIMAL_TESTS = "MINIMAL_TESTS"
    MAX_AGENTS = "MAX_AGENTS"
    CUSTOM_INSTRUCTION = "CUSTOM_INSTRUCTION"


@dataclass
class DispatchOverride:
    directive: str
    value: Optional[str] = None  # For MAX_AGENTS: "3", for CUSTOM_INSTRUCTION: free text
    active: bool = True

    def to_dict(self) -> dict:
        return {"directive": self.directive, "value": self.value, "active": self.active}

    @classmethod
    def from_dict(cls, d: dict) -> "DispatchOverride":
        return cls(directive=d["directive"], value=d.get("value"), active=d.get("active", True))


PRESETS = {
    "speed_run": [
        DispatchOverride(OverrideDirective.SKIP_REVIEW.value),
        DispatchOverride(OverrideDirective.MINIMAL_TESTS.value),
        DispatchOverride(OverrideDirective.MAX_AGENTS.value, "10"),
    ],
    "careful_mode": [
        DispatchOverride(OverrideDirective.MAX_AGENTS.value, "2"),
    ],
}


class OverrideResolver:
    """Resolves and applies dispatch overrides to swarm configuration."""

    def __init__(self, overrides: list[DispatchOverride] | None = None):
        self.overrides = overrides or []

    def has(self, directive: str) -> bool:
        return any(o.directive == directive and o.active for o in self.overrides)

    def get_value(self, directive: str) -> Optional[str]:
        for o in self.overrides:
            if o.directive == directive and o.active:
                return o.value
        return None

    def get_max_agents(self) -> Optional[int]:
        val = self.get_value(OverrideDirective.MAX_AGENTS.value)
        return int(val) if val else None

    def should_skip_review(self) -> bool:
        return self.has(OverrideDirective.SKIP_REVIEW.value)

    def get_custom_instructions(self) -> list[str]:
        return [o.value for o in self.overrides
                if o.directive == OverrideDirective.CUSTOM_INSTRUCTION.value and o.active and o.value]

    def to_overlay_text(self) -> str:
        """Generate text for overlay template injection."""
        if not self.overrides:
            return "No dispatch overrides active."
        lines = ["Active dispatch overrides:"]
        for o in self.overrides:
            if o.active:
                desc = o.directive
                if o.value:
                    desc += f" = {o.value}"
                lines.append(f"- {desc}")
        return "\n".join(lines)

    def to_dict_list(self) -> list[dict]:
        return [o.to_dict() for o in self.overrides]

    @classmethod
    def from_dict_list(cls, items: list[dict]) -> "OverrideResolver":
        return cls([DispatchOverride.from_dict(d) for d in items])
