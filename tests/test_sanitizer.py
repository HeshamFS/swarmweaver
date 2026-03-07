"""
Test Secret Sanitizer (utils/sanitizer.py)
============================================

Tests the sanitize() and sanitize_dict() functions that redact API keys,
tokens, passwords, and other secrets from strings and nested data structures.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.sanitizer import sanitize, sanitize_dict


# ---------------------------------------------------------------------------
# sanitize() — happy path
# ---------------------------------------------------------------------------

def test_sanitize_redacts_anthropic_api_key():
    """sk-ant-xxx style keys are replaced with ***REDACTED_API_KEY***."""
    text = "My key is sk-ant-api03-abc123XYZ_def456"
    result = sanitize(text)
    assert "sk-ant-" not in result
    assert "***REDACTED_API_KEY***" in result


def test_sanitize_redacts_anthropic_env_var():
    """ANTHROPIC_API_KEY=xxx is replaced with ANTHROPIC_API_KEY=***."""
    text = "export ANTHROPIC_API_KEY=sk-ant-some-long-key-value"
    result = sanitize(text)
    assert "ANTHROPIC_API_KEY=***" in result
    assert "sk-ant-some-long-key-value" not in result


def test_sanitize_redacts_github_personal_token():
    """ghp_xxx tokens are replaced with ***REDACTED_GH_TOKEN***."""
    text = "Using ghp_abcdef1234567890ABCDEF for auth"
    result = sanitize(text)
    assert "ghp_" not in result
    assert "***REDACTED_GH_TOKEN***" in result


def test_sanitize_redacts_bearer_token():
    """Bearer xxx is replaced with Bearer ***."""
    text = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.signature"
    result = sanitize(text)
    assert "Bearer ***" in result
    assert "eyJhbGciOiJIUzI1NiJ9" not in result


def test_sanitize_redacts_github_pat():
    """github_pat_xxx is replaced with ***REDACTED_GH_PAT***."""
    text = "Using github_pat_11ABCDEFG_someRandomString12345"
    result = sanitize(text)
    assert "github_pat_" not in result
    assert "***REDACTED_GH_PAT***" in result


def test_sanitize_redacts_generic_sk_key():
    """sk-xxxxxxxx (20+ chars) is replaced with ***REDACTED_SK_KEY***."""
    text = "key = sk-abcdefghijklmnopqrst12345"
    result = sanitize(text)
    assert "sk-abcdefghijklmnopqrst12345" not in result
    assert "***REDACTED_SK_KEY***" in result


# ---------------------------------------------------------------------------
# sanitize() — edge cases
# ---------------------------------------------------------------------------

def test_sanitize_returns_empty_for_empty_input():
    """Empty string input returns empty string."""
    assert sanitize("") == ""


def test_sanitize_returns_none_for_none_input():
    """None input returns None (falsy passthrough)."""
    assert sanitize(None) is None


def test_sanitize_leaves_clean_text_unchanged():
    """Text without secrets passes through unmodified."""
    text = "Hello, this is a normal log message with no secrets."
    assert sanitize(text) == text


# ---------------------------------------------------------------------------
# sanitize_dict() — recursive sanitization
# ---------------------------------------------------------------------------

def test_sanitize_dict_redacts_nested_dicts_and_lists():
    """Recursively sanitizes string values in dicts, lists, and nested structures."""
    data = {
        "config": {
            "api_key": "sk-ant-api03-secret123",
            "tokens": ["ghp_token123abc", "normal_value"],
        },
        "count": 42,
        "flag": True,
        "message": "Bearer eyJtoken.payload.sig",
    }
    result = sanitize_dict(data)

    # Nested dict value
    assert "***REDACTED_API_KEY***" in result["config"]["api_key"]
    assert "sk-ant-" not in result["config"]["api_key"]

    # List inside dict
    assert "***REDACTED_GH_TOKEN***" in result["config"]["tokens"][0]
    assert result["config"]["tokens"][1] == "normal_value"

    # Non-string values unchanged
    assert result["count"] == 42
    assert result["flag"] is True

    # Top-level string
    assert "Bearer ***" in result["message"]
