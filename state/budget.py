"""
Cost Budget & Circuit Breakers
===============================

Tracks real token usage per session, enforces spending limits,
and auto-stops the agent on budget/error/time thresholds.

Persists state to budget_state.json in the project directory.
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.paths import get_paths


# Cost per million tokens (USD) — updated Feb 2026
MODEL_COSTS_PER_MILLION: dict[str, dict[str, float]] = {
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-sonnet-4-5-20250929": {"input": 3.0, "output": 15.0},
    "claude-opus-4-6": {"input": 15.0, "output": 75.0},
    "claude-haiku-4-5-20251001": {"input": 0.8, "output": 4.0},
}

DEFAULT_MODEL = "claude-sonnet-4-5-20250929"


@dataclass
class BudgetState:
    """Persistent state for budget tracking."""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    real_cost_usd: float = 0.0          # Actual SDK-reported cost
    budget_limit_usd: float = 0.0       # 0 = unlimited
    max_hours: float = 0.0              # 0 = unlimited
    consecutive_errors: int = 0
    max_consecutive_errors: int = 10
    start_time: str = ""
    session_count: int = 0
    model_usage: dict[str, dict[str, int]] = field(default_factory=dict)
    # model_usage: {"claude-sonnet-...": {"input": N, "output": N}}


class BudgetTracker:
    """Tracks token usage, cost, and enforces circuit breakers."""

    def __init__(
        self,
        project_dir: Path,
        budget_limit: float = 0.0,
        max_hours: float = 0.0,
    ):
        self.project_dir = Path(project_dir)
        self.state_file = get_paths(project_dir).budget_state
        self.state = self._load()

        # Apply config (only override if explicitly set)
        if budget_limit > 0:
            self.state.budget_limit_usd = budget_limit
        if max_hours > 0:
            self.state.max_hours = max_hours
        if not self.state.start_time:
            self.state.start_time = datetime.now().isoformat()

    def _load(self) -> BudgetState:
        """Load state from disk, or create new."""
        if self.state_file.exists():
            try:
                data = json.loads(self.state_file.read_text(encoding="utf-8"))
                return BudgetState(
                    total_input_tokens=data.get("total_input_tokens", 0),
                    total_output_tokens=data.get("total_output_tokens", 0),
                    estimated_cost_usd=data.get("estimated_cost_usd", 0.0),
                    real_cost_usd=data.get("real_cost_usd", 0.0),
                    budget_limit_usd=data.get("budget_limit_usd", 0.0),
                    max_hours=data.get("max_hours", 0.0),
                    consecutive_errors=data.get("consecutive_errors", 0),
                    max_consecutive_errors=data.get("max_consecutive_errors", 10),
                    start_time=data.get("start_time", ""),
                    session_count=data.get("session_count", 0),
                    model_usage=data.get("model_usage", {}),
                )
            except (json.JSONDecodeError, OSError):
                pass
        return BudgetState()

    def save(self) -> None:
        """Persist state to disk."""
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state_file.write_text(
                json.dumps(asdict(self.state), indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    def record_usage(
        self,
        input_tokens: int,
        output_tokens: int,
        model: str = DEFAULT_MODEL,
    ) -> None:
        """Record token usage from a completed session."""
        self.state.total_input_tokens += input_tokens
        self.state.total_output_tokens += output_tokens
        self.state.session_count += 1

        # Track per-model usage
        if model not in self.state.model_usage:
            self.state.model_usage[model] = {"input": 0, "output": 0}
        self.state.model_usage[model]["input"] += input_tokens
        self.state.model_usage[model]["output"] += output_tokens

        # Recalculate total cost across all models
        self.state.estimated_cost_usd = self._calculate_total_cost()

        # Clear error streak on successful usage
        self.state.consecutive_errors = 0

        self.save()

    def record_real_usage(
        self,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        model: str = DEFAULT_MODEL,
    ) -> None:
        """Record actual SDK-reported token usage and cost from ResultMessage.

        Unlike record_usage() which estimates cost from token counts,
        this records the real total_cost_usd from the SDK's ResultMessage.
        """
        self.state.total_input_tokens += input_tokens
        self.state.total_output_tokens += output_tokens
        self.state.real_cost_usd += cost_usd
        self.state.session_count += 1

        # Track per-model usage
        if model not in self.state.model_usage:
            self.state.model_usage[model] = {"input": 0, "output": 0}
        self.state.model_usage[model]["input"] += input_tokens
        self.state.model_usage[model]["output"] += output_tokens

        # Also update estimated_cost for backward compatibility
        self.state.estimated_cost_usd = self._calculate_total_cost()

        # Clear error streak on successful usage
        self.state.consecutive_errors = 0

        self.save()

    def record_error(self) -> None:
        """Record a consecutive error."""
        self.state.consecutive_errors += 1
        self.save()

    def clear_error_streak(self) -> None:
        """Clear the consecutive error counter."""
        self.state.consecutive_errors = 0
        self.save()

    @property
    def effective_cost(self) -> float:
        """Return the best available cost: real SDK cost if available, else estimated."""
        if self.state.real_cost_usd > 0:
            return self.state.real_cost_usd
        return self.state.estimated_cost_usd

    def is_budget_exceeded(self) -> tuple[bool, str]:
        """Check all circuit breakers. Returns (exceeded, reason)."""
        # Budget limit — prefer real cost when available
        cost = self.effective_cost
        if self.state.budget_limit_usd > 0:
            if cost >= self.state.budget_limit_usd:
                return True, (
                    f"Budget limit reached: ${cost:.2f} "
                    f">= ${self.state.budget_limit_usd:.2f}"
                )

        # Time limit
        if self.state.max_hours > 0 and self.state.start_time:
            try:
                start = datetime.fromisoformat(self.state.start_time)
                elapsed_hours = (datetime.now() - start).total_seconds() / 3600
                if elapsed_hours >= self.state.max_hours:
                    return True, (
                        f"Time limit reached: {elapsed_hours:.1f}h "
                        f">= {self.state.max_hours:.1f}h"
                    )
            except (ValueError, TypeError):
                pass

        # Consecutive errors
        if self.state.consecutive_errors >= self.state.max_consecutive_errors:
            return True, (
                f"Too many consecutive errors: {self.state.consecutive_errors} "
                f">= {self.state.max_consecutive_errors}"
            )

        return False, ""

    def get_status(self) -> dict:
        """Return current budget status as a dict (for API responses)."""
        elapsed_hours = 0.0
        if self.state.start_time:
            try:
                start = datetime.fromisoformat(self.state.start_time)
                elapsed_hours = (datetime.now() - start).total_seconds() / 3600
            except (ValueError, TypeError):
                pass

        exceeded, reason = self.is_budget_exceeded()

        cost = self.effective_cost
        return {
            "total_input_tokens": self.state.total_input_tokens,
            "total_output_tokens": self.state.total_output_tokens,
            "estimated_cost_usd": round(self.state.estimated_cost_usd, 4),
            "real_cost_usd": round(self.state.real_cost_usd, 4),
            "budget_limit_usd": self.state.budget_limit_usd,
            "budget_remaining_usd": round(
                max(0, self.state.budget_limit_usd - cost), 4
            ) if self.state.budget_limit_usd > 0 else None,
            "max_hours": self.state.max_hours,
            "elapsed_hours": round(elapsed_hours, 2),
            "consecutive_errors": self.state.consecutive_errors,
            "session_count": self.state.session_count,
            "model_usage": self.state.model_usage,
            "exceeded": exceeded,
            "exceeded_reason": reason,
            "start_time": self.state.start_time,
        }

    def _calculate_total_cost(self) -> float:
        """Calculate total cost across all models."""
        total = 0.0
        for model, usage in self.state.model_usage.items():
            costs = MODEL_COSTS_PER_MILLION.get(model, MODEL_COSTS_PER_MILLION[DEFAULT_MODEL])
            total += (usage["input"] * costs["input"] / 1_000_000)
            total += (usage["output"] * costs["output"] / 1_000_000)
        return total
