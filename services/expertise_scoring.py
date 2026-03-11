"""
Multi-Expertise Learning System (MELS) — Confidence & Relevance Scoring
=========================================================================

Multi-signal confidence, time-decay relevance, and priming score computation.
"""

import fnmatch
import math
from datetime import datetime, timezone

from services.expertise_models import ExpertiseRecord


def compute_confidence(record: ExpertiseRecord) -> float:
    """Multi-signal confidence score (0.0-1.0).

    Weights:
    - 50%: success_rate = success_count / outcome_count
    - 20%: recency = exp(-0.03 * days_since_last_update)
    - 30%: confirmation_density = min(outcome_count / 10, 1.0)

    New records without outcomes start at 0.5 (neutral).
    """
    if record.outcome_count == 0:
        return 0.5

    # Success rate component (50%)
    success_rate = record.success_count / max(record.outcome_count, 1)
    success_component = success_rate * 0.5

    # Recency component (20%)
    try:
        updated = datetime.fromisoformat(record.updated_at.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        days = max((now - updated).total_seconds() / 86400, 0)
        recency = math.exp(-0.03 * days)
    except (ValueError, TypeError):
        recency = 0.5
    recency_component = recency * 0.2

    # Confirmation density (30%)
    density = min(record.outcome_count / 10.0, 1.0)
    density_component = density * 0.3

    return min(max(success_component + recency_component + density_component, 0.0), 1.0)


def compute_relevance(record: ExpertiseRecord) -> float:
    """Decay-based relevance score (0.0-1.0).

    Decay based on classification:
    - foundational: no decay (1.0)
    - tactical: linear decay over 30 days
    - observational: exponential decay (exp(-0.05 * days))

    Each update resets the decay clock.
    """
    if record.classification == "foundational":
        return 1.0

    try:
        updated = datetime.fromisoformat(record.updated_at.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        days = max((now - updated).total_seconds() / 86400, 0)
    except (ValueError, TypeError):
        return 0.5

    if record.classification == "tactical":
        return max(1.0 - (days / 30.0), 0.0)
    elif record.classification == "observational":
        return math.exp(-0.05 * days)

    return 1.0


def score_for_priming(
    record: ExpertiseRecord,
    file_scope: list[str],
    task_keywords: list[str],
) -> float:
    """Composite ranking score for priming selection.

    Components:
    - domain_match (0-0.3): how well file_scope maps to record's domain
    - file_pattern_match (0-0.3): fnmatch against record file_patterns
    - keyword_relevance (0-0.2): task keyword overlap with content/tags
    - confidence_boost (0-0.1): from record confidence
    - recency_boost (0-0.1): from record relevance_score
    """
    score = 0.0

    # Domain match (0-0.3)
    if record.domain and file_scope:
        from services.expertise_models import infer_domain, domain_matches
        for fp in file_scope:
            inferred = infer_domain(fp)
            if inferred and domain_matches(inferred, record.domain):
                score += 0.3
                break

    # File pattern match (0-0.3)
    if record.file_patterns and file_scope:
        for pat in record.file_patterns:
            for fp in file_scope:
                if fnmatch.fnmatch(fp, pat):
                    score += 0.3
                    break
            if score >= 0.6:
                break

    # Keyword relevance (0-0.2)
    if task_keywords:
        kw_set = set(w.lower() for w in task_keywords if len(w) > 2)
        if kw_set:
            content_words = set(record.content.lower().split())
            tag_words = set(t.lower() for t in record.tags)
            overlap = len(kw_set & (content_words | tag_words))
            score += min(overlap / max(len(kw_set), 1) * 0.2, 0.2)

    # Confidence boost (0-0.1)
    score += record.confidence * 0.1

    # Recency boost (0-0.1)
    score += record.relevance_score * 0.1

    return min(score, 1.0)


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars per token)."""
    return max(len(text) // 4, 1)
