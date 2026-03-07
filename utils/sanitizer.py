"""
Secret Sanitizer
==================

Regex-based redaction of secrets, API keys, tokens, and passwords
from strings and nested dicts. Used to prevent accidental leakage
through WebSocket output, logs, and API responses.
"""

import re
from typing import Any

SECRET_PATTERNS: list[tuple[str, str]] = [
    (r'sk-ant-[a-zA-Z0-9_-]+', '***REDACTED_API_KEY***'),
    (r'ANTHROPIC_API_KEY=[^\s]+', 'ANTHROPIC_API_KEY=***'),
    (r'Bearer\s+[a-zA-Z0-9._-]+', 'Bearer ***'),
    (r'ghp_[a-zA-Z0-9]+', '***REDACTED_GH_TOKEN***'),
    (r'github_pat_[a-zA-Z0-9_]+', '***REDACTED_GH_PAT***'),
    (r'(?i)password["\s:=]+[^\s"]+', 'password=***'),
    (r'sk-[a-zA-Z0-9]{20,}', '***REDACTED_SK_KEY***'),
    (r'(?i)secret["\s:=]+[^\s"]+', 'secret=***'),
    (r'(?i)token["\s:=]+[^\s"]{10,}', 'token=***'),
]

# Pre-compile patterns for performance
_COMPILED_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(pattern), replacement)
    for pattern, replacement in SECRET_PATTERNS
]


def sanitize(text: str) -> str:
    """Replace all secret patterns in text with redacted placeholders."""
    if not text:
        return text
    for compiled, replacement in _COMPILED_PATTERNS:
        text = compiled.sub(replacement, text)
    return text


def sanitize_dict(data: Any) -> Any:
    """
    Recursively sanitize all string values in a dict, list, or nested structure.

    Non-dict/list/str values are returned unchanged.
    """
    if isinstance(data, str):
        return sanitize(data)
    if isinstance(data, dict):
        return {k: sanitize_dict(v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [sanitize_dict(item) for item in data]
    return data
