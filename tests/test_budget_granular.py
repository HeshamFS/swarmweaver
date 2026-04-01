"""
Test Granular Cost Tracking (state/budget.py)
=============================================

Tests for the enhanced budget tracking system with per-model cache pricing,
API duration tracking, code change metrics, and web search costs.
"""

import json
import os
import sys
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from state.budget import BudgetTracker, BudgetState, MODEL_COSTS_PER_MILLION, DEFAULT_MODEL


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def tmp_project(tmp_path):
    """Create a temporary project directory with .swarmweaver/."""
    project = tmp_path / "test_project"
    project.mkdir()
    sw = project / ".swarmweaver"
    sw.mkdir()
    return project


@pytest.fixture
def tracker(tmp_project):
    """Create a BudgetTracker instance."""
    return BudgetTracker(tmp_project)


# ═══════════════════════════════════════════════════════════════════════════
# Pricing Table
# ═══════════════════════════════════════════════════════════════════════════

class TestPricingTable:
    """Tests for the model pricing table."""

    def test_all_models_have_cache_pricing(self):
        """Every model should have cache_read and cache_write costs."""
        for model, costs in MODEL_COSTS_PER_MILLION.items():
            assert "cache_read" in costs, f"{model} missing cache_read"
            assert "cache_write" in costs, f"{model} missing cache_write"
            assert costs["cache_read"] > 0, f"{model} cache_read should be > 0"
            assert costs["cache_write"] > 0, f"{model} cache_write should be > 0"

    def test_cache_read_cheaper_than_input(self):
        """Cache read should always be cheaper than regular input."""
        for model, costs in MODEL_COSTS_PER_MILLION.items():
            assert costs["cache_read"] < costs["input"], (
                f"{model}: cache_read ({costs['cache_read']}) should be < input ({costs['input']})"
            )

    def test_all_models_have_standard_fields(self):
        """Every model should have input, output, cache_read, cache_write."""
        required = {"input", "output", "cache_read", "cache_write"}
        for model, costs in MODEL_COSTS_PER_MILLION.items():
            assert required <= set(costs.keys()), f"{model} missing fields"


# ═══════════════════════════════════════════════════════════════════════════
# BudgetState
# ═══════════════════════════════════════════════════════════════════════════

class TestBudgetState:
    """Tests for the BudgetState dataclass."""

    def test_new_fields_default_zero(self):
        """New fields should default to 0."""
        state = BudgetState()
        assert state.total_cache_read_tokens == 0
        assert state.total_cache_write_tokens == 0
        assert state.total_api_duration_ms == 0
        assert state.total_lines_added == 0
        assert state.total_lines_removed == 0
        assert state.web_search_count == 0

    def test_original_fields_preserved(self):
        """Original fields should still default correctly."""
        state = BudgetState()
        assert state.total_input_tokens == 0
        assert state.total_output_tokens == 0
        assert state.estimated_cost_usd == 0.0
        assert state.real_cost_usd == 0.0
        assert state.budget_limit_usd == 0.0
        assert state.max_hours == 0.0
        assert state.consecutive_errors == 0
        assert state.max_consecutive_errors == 10


# ═══════════════════════════════════════════════════════════════════════════
# Record Usage
# ═══════════════════════════════════════════════════════════════════════════

class TestRecordUsage:
    """Tests for token recording methods."""

    def test_record_usage_with_cache(self, tracker):
        """record_usage should track cache tokens."""
        tracker.record_usage(1000, 500, "claude-sonnet-4-6",
                             cache_read_tokens=200, cache_write_tokens=50)
        assert tracker.state.total_input_tokens == 1000
        assert tracker.state.total_output_tokens == 500
        assert tracker.state.total_cache_read_tokens == 200
        assert tracker.state.total_cache_write_tokens == 50

    def test_record_usage_cache_defaults_zero(self, tracker):
        """Cache tokens default to 0 for backward compat."""
        tracker.record_usage(1000, 500, "claude-sonnet-4-6")
        assert tracker.state.total_cache_read_tokens == 0
        assert tracker.state.total_cache_write_tokens == 0

    def test_record_real_usage_with_cache(self, tracker):
        """record_real_usage should track cache tokens."""
        tracker.record_real_usage(1000, 500, 0.05, "claude-sonnet-4-6",
                                  cache_read_tokens=300, cache_write_tokens=100)
        assert tracker.state.total_cache_read_tokens == 300
        assert tracker.state.total_cache_write_tokens == 100
        assert tracker.state.real_cost_usd == 0.05

    def test_record_cache_usage(self, tracker):
        """record_cache_usage should update cache totals and per-model."""
        tracker.record_cache_usage(500, 100, "claude-opus-4-6")
        assert tracker.state.total_cache_read_tokens == 500
        assert tracker.state.total_cache_write_tokens == 100
        assert tracker.state.model_usage["claude-opus-4-6"]["cache_read"] == 500
        assert tracker.state.model_usage["claude-opus-4-6"]["cache_write"] == 100

    def test_accumulates_across_calls(self, tracker):
        """Multiple calls should accumulate tokens."""
        tracker.record_usage(100, 50, cache_read_tokens=10)
        tracker.record_usage(200, 100, cache_read_tokens=20)
        assert tracker.state.total_input_tokens == 300
        assert tracker.state.total_cache_read_tokens == 30


# ═══════════════════════════════════════════════════════════════════════════
# New Recording Methods
# ═══════════════════════════════════════════════════════════════════════════

class TestNewRecordingMethods:
    """Tests for record_api_call, record_code_changes, record_web_search."""

    def test_record_api_call(self, tracker):
        """record_api_call should track duration and count."""
        tracker.record_api_call(1500, "claude-sonnet-4-6")
        assert tracker.state.total_api_duration_ms == 1500
        assert tracker.state.model_usage["claude-sonnet-4-6"]["api_calls"] == 1
        assert tracker.state.model_usage["claude-sonnet-4-6"]["api_duration_ms"] == 1500

    def test_record_api_call_accumulates(self, tracker):
        """Multiple API calls should accumulate."""
        tracker.record_api_call(1000, "claude-sonnet-4-6")
        tracker.record_api_call(2000, "claude-sonnet-4-6")
        assert tracker.state.total_api_duration_ms == 3000
        assert tracker.state.model_usage["claude-sonnet-4-6"]["api_calls"] == 2

    def test_record_code_changes(self, tracker):
        """record_code_changes should track lines added/removed."""
        tracker.record_code_changes(150, 30)
        assert tracker.state.total_lines_added == 150
        assert tracker.state.total_lines_removed == 30

    def test_record_web_search(self, tracker):
        """record_web_search should increment count."""
        tracker.record_web_search()
        tracker.record_web_search()
        assert tracker.state.web_search_count == 2


# ═══════════════════════════════════════════════════════════════════════════
# Cost Calculation
# ═══════════════════════════════════════════════════════════════════════════

class TestCostCalculation:
    """Tests for cost calculation including cache tokens and web searches."""

    def test_cost_includes_cache_tokens(self, tracker):
        """_calculate_total_cost should include cache token costs."""
        tracker.record_usage(1000, 500, "claude-sonnet-4-6",
                             cache_read_tokens=200, cache_write_tokens=50)
        cost = tracker._calculate_total_cost()
        expected = (
            (1000 * 3.0 / 1_000_000) +
            (500 * 15.0 / 1_000_000) +
            (200 * 0.30 / 1_000_000) +
            (50 * 3.75 / 1_000_000)
        )
        assert abs(cost - expected) < 0.0001

    def test_cost_includes_web_search(self, tracker):
        """Web searches should add $0.01 each to total cost."""
        tracker.record_web_search()
        tracker.record_web_search()
        cost = tracker._calculate_total_cost()
        assert abs(cost - 0.02) < 0.0001

    def test_cost_display_low(self, tracker):
        """Low cost should show 4 decimal places."""
        tracker.record_usage(100, 50, "claude-haiku-4-5-20251001")
        display = tracker.get_cost_display()
        assert display.count(".") == 1
        # Low cost -> 4 decimals
        decimal_part = display.split(".")[1]
        assert len(decimal_part) == 4

    def test_cost_display_high(self, tracker):
        """High cost should show 2 decimal places."""
        tracker.state.estimated_cost_usd = 5.1234
        display = tracker.get_cost_display()
        assert display == "$5.12"


# ═══════════════════════════════════════════════════════════════════════════
# Cache Efficiency
# ═══════════════════════════════════════════════════════════════════════════

class TestCacheEfficiency:
    """Tests for the cache_efficiency property."""

    def test_cache_efficiency_zero_input(self, tracker):
        """No input tokens -> 0.0 efficiency."""
        assert tracker.cache_efficiency == 0.0

    def test_cache_efficiency_calculation(self, tracker):
        """cache_efficiency = cache_read / total_input."""
        tracker.record_usage(1000, 500, cache_read_tokens=300)
        assert tracker.cache_efficiency == pytest.approx(0.3)

    def test_cache_efficiency_in_status(self, tracker):
        """get_status should include cache_efficiency."""
        tracker.record_usage(1000, 500, cache_read_tokens=250)
        status = tracker.get_status()
        assert "cache_efficiency" in status
        assert status["cache_efficiency"] == pytest.approx(0.25)


# ═══════════════════════════════════════════════════════════════════════════
# Status Output
# ═══════════════════════════════════════════════════════════════════════════

class TestGetStatus:
    """Tests for the get_status method."""

    def test_status_includes_all_new_fields(self, tracker):
        """get_status should include all new granular fields."""
        status = tracker.get_status()
        new_fields = [
            "total_cache_read_tokens",
            "total_cache_write_tokens",
            "total_api_duration_ms",
            "total_lines_added",
            "total_lines_removed",
            "web_search_count",
            "cache_efficiency",
            "cost_display",
        ]
        for field in new_fields:
            assert field in status, f"Missing field: {field}"

    def test_status_preserves_original_fields(self, tracker):
        """get_status should still include all original fields."""
        status = tracker.get_status()
        original_fields = [
            "total_input_tokens",
            "total_output_tokens",
            "estimated_cost_usd",
            "real_cost_usd",
            "budget_limit_usd",
            "max_hours",
            "elapsed_hours",
            "consecutive_errors",
            "session_count",
            "model_usage",
            "exceeded",
            "exceeded_reason",
            "start_time",
        ]
        for field in original_fields:
            assert field in status, f"Missing original field: {field}"


# ═══════════════════════════════════════════════════════════════════════════
# Persistence & Backward Compatibility
# ═══════════════════════════════════════════════════════════════════════════

class TestPersistence:
    """Tests for save/load and backward compatibility."""

    def test_save_and_reload(self, tmp_project):
        """Saved state should be fully reloaded."""
        tracker = BudgetTracker(tmp_project)
        tracker.record_usage(1000, 500, "claude-sonnet-4-6",
                             cache_read_tokens=200, cache_write_tokens=50)
        tracker.record_api_call(2000, "claude-sonnet-4-6")
        tracker.record_code_changes(80, 20)
        tracker.record_web_search()
        tracker.save()

        tracker2 = BudgetTracker(tmp_project)
        assert tracker2.state.total_cache_read_tokens == 200
        assert tracker2.state.total_cache_write_tokens == 50
        assert tracker2.state.total_api_duration_ms == 2000
        assert tracker2.state.total_lines_added == 80
        assert tracker2.state.total_lines_removed == 20
        assert tracker2.state.web_search_count == 1

    def test_backward_compat_old_json(self, tmp_project):
        """Old budget_state.json without new fields should load fine."""
        old_data = {
            "total_input_tokens": 500,
            "total_output_tokens": 200,
            "estimated_cost_usd": 0.01,
            "budget_limit_usd": 0,
            "max_hours": 0,
            "consecutive_errors": 0,
            "max_consecutive_errors": 10,
            "start_time": "",
            "session_count": 1,
            "model_usage": {"claude-sonnet-4-6": {"input": 500, "output": 200}},
        }
        budget_file = tmp_project / ".swarmweaver" / "budget_state.json"
        budget_file.write_text(json.dumps(old_data))

        tracker = BudgetTracker(tmp_project)
        assert tracker.state.total_input_tokens == 500
        assert tracker.state.total_cache_read_tokens == 0
        assert tracker.state.total_cache_write_tokens == 0
        assert tracker.state.total_api_duration_ms == 0
        assert tracker.state.total_lines_added == 0
        assert tracker.state.web_search_count == 0

    def test_backward_compat_old_model_usage(self, tmp_project):
        """Old model_usage without cache fields should get backfilled."""
        old_data = {
            "total_input_tokens": 500,
            "total_output_tokens": 200,
            "model_usage": {"claude-sonnet-4-6": {"input": 500, "output": 200}},
        }
        budget_file = tmp_project / ".swarmweaver" / "budget_state.json"
        budget_file.write_text(json.dumps(old_data))

        tracker = BudgetTracker(tmp_project)
        tracker._ensure_model_usage("claude-sonnet-4-6")
        usage = tracker.state.model_usage["claude-sonnet-4-6"]
        assert "cache_read" in usage
        assert "cache_write" in usage
        assert "api_calls" in usage
        assert "api_duration_ms" in usage
        assert usage["cache_read"] == 0
