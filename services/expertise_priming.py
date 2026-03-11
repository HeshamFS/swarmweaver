"""
Multi-Expertise Learning System (MELS) — Priming Engine
=========================================================

Token-budget-aware record selection and formatting for prompt injection.
Uses greedy knapsack to maximize value within token budget.
"""

from services.expertise_models import ExpertiseRecord, infer_domain, domain_matches
from services.expertise_scoring import score_for_priming, estimate_tokens
from services.expertise_store import ExpertiseStore


class PrimingEngine:
    """Select and format expertise records for prompt injection."""

    DEFAULT_BUDGET_TOKENS = 2000  # ~500 words

    def prime(
        self,
        store: ExpertiseStore,
        file_scope: list[str] | None = None,
        domains: list[str] | None = None,
        task_description: str = "",
        budget_tokens: int = DEFAULT_BUDGET_TOKENS,
        record_types: list[str] | None = None,
    ) -> str:
        """Select and format expertise for prompt injection.

        1. Query records by domain match + file_pattern match
        2. Score each with score_for_priming()
        3. Greedy knapsack fill up to budget_tokens
        4. Group by domain, format as markdown
        5. Include causal chain indicators (failure -> resolution linked)
        """
        file_scope = file_scope or []
        candidates: list[ExpertiseRecord] = []
        seen_ids: set[str] = set()

        # Gather candidates from multiple sources
        # 1. Domain-based query
        if domains:
            for d in domains:
                for rec in store.get_by_domain(d, include_children=True):
                    if rec.id not in seen_ids:
                        candidates.append(rec)
                        seen_ids.add(rec.id)

        # 2. File-scope-based domain inference
        if file_scope:
            inferred_domains: set[str] = set()
            for fp in file_scope:
                d = infer_domain(fp)
                if d:
                    inferred_domains.add(d)

            for d in inferred_domains:
                for rec in store.get_by_domain(d, include_children=True):
                    if rec.id not in seen_ids:
                        candidates.append(rec)
                        seen_ids.add(rec.id)

            # File pattern matches
            for rec in store.get_for_file_scope(file_scope):
                if rec.id not in seen_ids:
                    candidates.append(rec)
                    seen_ids.add(rec.id)

        # 3. If no candidates from domain/file, do a keyword search
        if not candidates and task_description:
            keywords = [w for w in task_description.split() if len(w) > 3][:5]
            for kw in keywords:
                for rec in store.search(query=kw, limit=10):
                    if rec.id not in seen_ids:
                        candidates.append(rec)
                        seen_ids.add(rec.id)

        # 4. If still nothing, get top records by confidence
        if not candidates:
            candidates = store.search(limit=10)

        if not candidates:
            return ""

        # Filter by record_types if specified
        if record_types:
            candidates = [r for r in candidates if r.record_type in record_types]

        # Score and sort
        task_keywords = [w for w in task_description.split() if len(w) > 2] if task_description else []
        scored = [
            (score_for_priming(rec, file_scope, task_keywords), rec)
            for rec in candidates
        ]
        scored.sort(key=lambda x: x[0], reverse=True)

        # Greedy knapsack within token budget
        selected: list[ExpertiseRecord] = []
        tokens_used = 0
        header_tokens = estimate_tokens("## Loaded Expertise (X records, Y domains)\n\n")
        tokens_used += header_tokens

        for _score, rec in scored:
            entry_text = self._format_entry(rec)
            entry_tokens = estimate_tokens(entry_text)

            # Account for domain header if this is a new domain
            current_domains = set(r.domain for r in selected)
            if rec.domain not in current_domains:
                entry_tokens += estimate_tokens(f"\n### {rec.domain.title()}\n")

            if tokens_used + entry_tokens <= budget_tokens:
                selected.append(rec)
                tokens_used += entry_tokens
            elif len(selected) >= 3:
                break  # Have enough, stop

        if not selected:
            return ""

        return self._format_output(selected)

    def _format_entry(self, rec: ExpertiseRecord) -> str:
        """Format a single record as a markdown list item."""
        parts = [f"[{rec.record_type}]"]

        # Causal chain indicator
        if rec.record_type == "failure" and rec.resolved_by:
            parts.append("(resolved)")
        elif rec.record_type == "resolution" and rec.resolves:
            parts.append("(fixes failure)")

        parts.append(rec.content)

        # Confidence indicator for heuristics
        if rec.record_type == "heuristic" and rec.outcome_count > 0:
            parts.append(f"(confidence: {rec.confidence:.2f}, n={rec.outcome_count})")

        return f"- {' '.join(parts)}"

    def _format_output(self, records: list[ExpertiseRecord]) -> str:
        """Format selected records grouped by domain as markdown."""
        # Group by domain
        by_domain: dict[str, list[ExpertiseRecord]] = {}
        for rec in records:
            domain = rec.domain or "general"
            if domain not in by_domain:
                by_domain[domain] = []
            by_domain[domain].append(rec)

        domain_count = len(by_domain)
        record_count = len(records)

        lines = [f"## Loaded Expertise ({record_count} records, {domain_count} domains)\n"]

        for domain, domain_records in sorted(by_domain.items()):
            lines.append(f"### {domain.replace('.', ' > ').title()}")

            # Show failure -> resolution pairs together
            failures_with_resolutions: dict[str, list[ExpertiseRecord]] = {}
            standalone: list[ExpertiseRecord] = []

            for rec in domain_records:
                if rec.record_type == "failure" and rec.resolved_by:
                    failures_with_resolutions[rec.id] = [rec]
                elif rec.record_type == "resolution" and rec.resolves:
                    if rec.resolves in failures_with_resolutions:
                        failures_with_resolutions[rec.resolves].append(rec)
                    else:
                        standalone.append(rec)
                else:
                    standalone.append(rec)

            # Output causal chains first
            for _fid, chain in failures_with_resolutions.items():
                failure = chain[0]
                resolutions = chain[1:]
                resolution_text = resolutions[0].content if resolutions else "unresolved"
                lines.append(f"- [failure -> resolution] {failure.content} -> {resolution_text}")

            # Then standalone records
            for rec in standalone:
                lines.append(self._format_entry(rec))

            lines.append("")

        return "\n".join(lines)
