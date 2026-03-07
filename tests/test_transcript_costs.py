"""
Test Transcript Cost Analyzer (services/transcript_costs.py)
==============================================================

Tests the TranscriptCostAnalyzer class that parses JSONL transcript files
and calculates dollar costs based on token usage and model pricing tiers.

Uses tmp_path fixture to create temporary JSONL transcript files.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.transcript_costs import TranscriptCostAnalyzer


def _write_transcript(path: Path, entries: list[dict]) -> Path:
    """Helper: write JSONL transcript entries to a file."""
    lines = [json.dumps(e) for e in entries]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# _resolve_model_key()
# ---------------------------------------------------------------------------

def test_resolve_model_key_maps_sonnet():
    """'claude-sonnet-4-5' resolves to 'sonnet' pricing tier."""
    analyzer = TranscriptCostAnalyzer()
    assert analyzer._resolve_model_key("claude-sonnet-4-5-20250929") == "sonnet"


def test_resolve_model_key_maps_opus():
    """'claude-opus-4' resolves to 'opus' pricing tier."""
    analyzer = TranscriptCostAnalyzer()
    assert analyzer._resolve_model_key("claude-opus-4") == "opus"


def test_resolve_model_key_maps_haiku():
    """'claude-haiku-4-5' resolves to 'haiku' pricing tier."""
    analyzer = TranscriptCostAnalyzer()
    assert analyzer._resolve_model_key("claude-haiku-4-5-20250929") == "haiku"


def test_resolve_model_key_defaults_to_sonnet():
    """Unknown model strings default to 'sonnet' tier."""
    analyzer = TranscriptCostAnalyzer()
    assert analyzer._resolve_model_key("some-unknown-model") == "sonnet"
    assert analyzer._resolve_model_key("") == "sonnet"


# ---------------------------------------------------------------------------
# parse_transcript()
# ---------------------------------------------------------------------------

def test_parse_transcript_returns_zero_for_nonexistent_file(tmp_path):
    """Non-existent transcript file returns zeroed usage dict."""
    analyzer = TranscriptCostAnalyzer()
    result = analyzer.parse_transcript(tmp_path / "does_not_exist.jsonl")
    assert result["messages"] == 0
    assert result["input_tokens"] == 0
    assert result["output_tokens"] == 0
    assert result["cache_read_tokens"] == 0
    assert result["cache_creation_tokens"] == 0


def test_parse_transcript_extracts_token_counts(tmp_path):
    """Correctly sums token counts from JSONL entries with usage data."""
    entries = [
        {
            "model": "claude-sonnet-4-5-20250929",
            "agent_name": "builder-1",
            "usage": {
                "input_tokens": 1000,
                "output_tokens": 500,
                "cache_read_input_tokens": 200,
                "cache_creation_input_tokens": 100,
            },
        },
        {
            "model": "claude-sonnet-4-5-20250929",
            "agent_name": "builder-1",
            "usage": {
                "input_tokens": 2000,
                "output_tokens": 800,
                "cache_read_input_tokens": 300,
                "cache_creation_input_tokens": 150,
            },
        },
    ]
    transcript = tmp_path / "transcript.jsonl"
    _write_transcript(transcript, entries)

    analyzer = TranscriptCostAnalyzer()
    result = analyzer.parse_transcript(transcript)

    assert result["messages"] == 2
    assert result["model"] == "claude-sonnet-4-5-20250929"
    assert result["agent"] == "builder-1"
    assert result["input_tokens"] == 3000
    assert result["output_tokens"] == 1300
    assert result["cache_read_tokens"] == 500
    assert result["cache_creation_tokens"] == 250


def test_parse_transcript_handles_nested_usage(tmp_path):
    """Token usage nested under message.usage is also extracted."""
    entries = [
        {
            "model": "claude-sonnet-4-5-20250929",
            "message": {
                "usage": {
                    "input_tokens": 500,
                    "output_tokens": 250,
                },
            },
        },
    ]
    transcript = tmp_path / "transcript.jsonl"
    _write_transcript(transcript, entries)

    analyzer = TranscriptCostAnalyzer()
    result = analyzer.parse_transcript(transcript)

    assert result["messages"] == 1
    assert result["input_tokens"] == 500
    assert result["output_tokens"] == 250


# ---------------------------------------------------------------------------
# calculate_costs()
# ---------------------------------------------------------------------------

def test_calculate_costs_sonnet_tier():
    """Costs computed correctly for the sonnet pricing tier."""
    analyzer = TranscriptCostAnalyzer()
    usage = {
        "model": "claude-sonnet-4-5-20250929",
        "input_tokens": 1_000_000,
        "output_tokens": 1_000_000,
        "cache_read_tokens": 1_000_000,
        "cache_creation_tokens": 1_000_000,
    }
    costs = analyzer.calculate_costs(usage)

    # Sonnet rates: input=$3, output=$15, cache_read=$0.30, cache_creation=$0.75
    assert costs["input_cost"] == 3.0
    assert costs["output_cost"] == 15.0
    assert costs["cache_read_cost"] == 0.3
    assert costs["cache_creation_cost"] == 0.75
    assert costs["total"] == 3.0 + 15.0 + 0.3 + 0.75
    assert costs["model_key"] == "sonnet"


def test_calculate_costs_opus_tier():
    """Costs computed correctly for the opus pricing tier."""
    analyzer = TranscriptCostAnalyzer()
    usage = {
        "model": "claude-opus-4",
        "input_tokens": 1_000_000,
        "output_tokens": 1_000_000,
        "cache_read_tokens": 1_000_000,
        "cache_creation_tokens": 1_000_000,
    }
    costs = analyzer.calculate_costs(usage)

    # Opus rates: input=$15, output=$75, cache_read=$1.50, cache_creation=$3.75
    assert costs["input_cost"] == 15.0
    assert costs["output_cost"] == 75.0
    assert costs["cache_read_cost"] == 1.5
    assert costs["cache_creation_cost"] == 3.75
    assert costs["total"] == 15.0 + 75.0 + 1.5 + 3.75
    assert costs["model_key"] == "opus"


def test_calculate_costs_handles_zero_tokens():
    """Zero tokens result in zero costs with no division errors."""
    analyzer = TranscriptCostAnalyzer()
    usage = {
        "model": "claude-sonnet-4-5-20250929",
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_creation_tokens": 0,
    }
    costs = analyzer.calculate_costs(usage)

    assert costs["total"] == 0.0
    assert costs["input_cost"] == 0.0
    assert costs["output_cost"] == 0.0
    assert costs["cache_read_cost"] == 0.0
    assert costs["cache_creation_cost"] == 0.0
