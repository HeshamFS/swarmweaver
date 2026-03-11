"""
Multi-Expertise Learning System (MELS) — Session Lesson Synthesizer
=====================================================================

Synthesizes lessons from worker errors in real-time (intra-session).
Pattern: record errors -> detect clusters (2+ similar across workers) ->
synthesize lesson with quality gating -> propagate to active peers.
"""

import fnmatch
import hashlib
import re
from datetime import datetime, timezone

from services.expertise_models import SessionLesson, infer_domain
from services.expertise_store import ExpertiseStore


def _normalize_error(msg: str) -> str:
    """Normalize error message for clustering.

    Strips line numbers, hex addresses, UUIDs, timestamps, and paths
    to produce a stable hash for grouping similar errors.
    """
    # Remove line numbers
    normalized = re.sub(r"line \d+", "line N", msg, flags=re.IGNORECASE)
    # Remove hex addresses
    normalized = re.sub(r"0x[0-9a-fA-F]+", "0xADDR", normalized)
    # Remove UUIDs
    normalized = re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "UUID", normalized)
    # Remove timestamps
    normalized = re.sub(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}", "TIMESTAMP", normalized)
    # Simplify paths (keep last component)
    normalized = re.sub(r"(/[a-zA-Z0-9._-]+)+/", "PATH/", normalized)
    # Remove numbers that look like counts/IDs
    normalized = re.sub(r"\b\d{3,}\b", "NUM", normalized)
    return normalized.strip().lower()


class SessionLessonSynthesizer:
    """Synthesizes lessons from worker errors in real-time."""

    def __init__(self, store: ExpertiseStore, session_id: str):
        self._store = store
        self._session_id = session_id
        self._errors: list[dict] = []  # in-memory error buffer for speed
        self._error_hashes: dict[str, list[int]] = {}  # normalized_hash -> [error_indices]
        self._lessons_created: set[str] = set()  # deduplicate lesson content hashes

    def record_error(
        self,
        worker_id: str,
        worker_name: str,
        tool_name: str,
        error_message: str,
        file_path: str,
        task_id: str,
    ) -> tuple[str, "SessionLesson | None"]:
        """Record a worker error and check for cluster-based lesson synthesis.

        Returns (error_id, newly_created_lesson_or_None).
        """
        err_id = f"err-{len(self._errors):03d}"
        error = {
            "id": err_id,
            "worker_id": worker_id,
            "worker_name": worker_name,
            "tool_name": tool_name,
            "error_message": error_message[:500],
            "file_path": file_path,
            "task_id": task_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        idx = len(self._errors)
        self._errors.append(error)

        # Index by normalized error hash
        norm = _normalize_error(error_message)
        norm_hash = hashlib.md5(norm.encode()).hexdigest()[:12]
        if norm_hash not in self._error_hashes:
            self._error_hashes[norm_hash] = []
        self._error_hashes[norm_hash].append(idx)

        # Check for cluster (2+ similar errors across different workers)
        new_lesson = None
        cluster = self._detect_error_cluster(norm_hash)
        if cluster:
            lesson = self._synthesize_lesson(cluster)
            if lesson:
                self._store.add_session_lesson(lesson)
                new_lesson = lesson

        return err_id, new_lesson

    def _detect_error_cluster(self, norm_hash: str) -> list[dict] | None:
        """Return cluster if 2+ similar errors exist, ideally across different workers."""
        indices = self._error_hashes.get(norm_hash, [])
        if len(indices) < 2:
            return None

        cluster = [self._errors[i] for i in indices]

        # Prefer cross-worker clusters
        workers = set(e["worker_id"] for e in cluster)
        if len(workers) >= 2:
            return cluster

        # Accept same-worker cluster if 3+ occurrences (persistent issue)
        if len(cluster) >= 3:
            return cluster

        return None

    def _synthesize_lesson(self, cluster: list[dict]) -> SessionLesson | None:
        """Create a lesson from an error cluster.

        Quality scoring: specificity (0-0.5) + actionability (0-0.5).
        Only create if quality_score >= 0.4.
        """
        # Deduplicate: don't create same lesson twice
        first_msg = cluster[0]["error_message"]
        content_hash = hashlib.md5(first_msg[:200].encode()).hexdigest()[:12]
        if content_hash in self._lessons_created:
            return None

        # Extract common elements
        tool_names = set(e["tool_name"] for e in cluster if e["tool_name"])
        file_paths = set(e["file_path"] for e in cluster if e["file_path"])
        worker_names = set(e["worker_name"] for e in cluster)
        error_ids = [e["id"] for e in cluster]

        # Synthesize lesson content
        content_parts = []

        # Describe the pattern
        workers_desc = f"across workers ({', '.join(sorted(worker_names))})" if len(worker_names) > 1 else f"by {next(iter(worker_names))}"
        content_parts.append(f"Repeated error {workers_desc}:")

        # Core error message (deduplicated first occurrence)
        core_msg = first_msg[:200]
        content_parts.append(f'"{core_msg}"')

        # Tools involved
        if tool_names:
            content_parts.append(f"Tools involved: {', '.join(sorted(tool_names))}")

        # File context
        if file_paths:
            content_parts.append(f"Files affected: {', '.join(sorted(list(file_paths)[:5]))}")

        content = ". ".join(content_parts)

        # Determine severity
        if len(cluster) >= 5:
            severity = "critical"
        elif len(worker_names) >= 3:
            severity = "high"
        elif len(worker_names) >= 2:
            severity = "medium"
        else:
            severity = "low"

        # Infer domain from file paths
        domain = ""
        for fp in file_paths:
            d = infer_domain(fp)
            if d:
                domain = d
                break

        # Build file patterns for scope matching
        file_patterns = []
        for fp in file_paths:
            # Convert to glob pattern (e.g., "src/utils/auth.py" -> "src/utils/*.py")
            if "." in fp:
                parts = fp.rsplit("/", 1)
                ext = fp.rsplit(".", 1)[-1]
                if len(parts) == 2:
                    file_patterns.append(f"{parts[0]}/*.{ext}")
                else:
                    file_patterns.append(f"*.{ext}")

        # Quality scoring
        quality_score = self._score_quality(content, file_patterns)
        if quality_score < 0.4:
            return None

        self._lessons_created.add(content_hash)

        return SessionLesson(
            session_id=self._session_id,
            content=content,
            severity=severity,
            domain=domain,
            file_patterns=file_patterns,
            source_error_ids=error_ids,
            quality_score=quality_score,
        )

    def _score_quality(self, content: str, file_patterns: list[str]) -> float:
        """Quality score: specificity (0-0.5) + actionability (0-0.5)."""
        score = 0.0

        # Specificity (0-0.5): mentions specific files, tools, or error messages
        specificity = 0.0
        if file_patterns:
            specificity += 0.2
        if any(kw in content.lower() for kw in ["error", "exception", "failed", "traceback"]):
            specificity += 0.15
        if len(content) > 100:
            specificity += 0.15
        score += min(specificity, 0.5)

        # Actionability (0-0.5): patterns suggesting action
        actionability = 0.0
        action_patterns = ["use", "instead", "avoid", "always", "never", "should", "must", "don't", "do not"]
        content_lower = content.lower()
        for pat in action_patterns:
            if pat in content_lower:
                actionability += 0.1
        # Specific tools/file mentions are actionable
        if "Tools involved:" in content:
            actionability += 0.1
        if "Files affected:" in content:
            actionability += 0.1
        score += min(actionability, 0.5)

        return min(score, 1.0)

    def get_lessons_for_worker(
        self,
        file_scope: list[str],
        exclude_worker: str | None = None,
    ) -> list[SessionLesson]:
        """Get session lessons relevant to a worker's file scope.

        Filters by file_scope relevance, excludes originating worker if specified.
        """
        lessons = self._store.get_session_lessons(self._session_id)
        if not lessons:
            return []

        relevant = []
        for lesson in lessons:
            # Skip already-promoted lessons
            if lesson.promoted_to_record_id:
                continue

            # File scope relevance check
            if file_scope and lesson.file_patterns:
                matches = False
                for pat in lesson.file_patterns:
                    for fp in file_scope:
                        if fnmatch.fnmatch(fp, pat):
                            matches = True
                            break
                    if matches:
                        break
                if not matches:
                    continue
            # If no file_patterns on lesson, it's global — include it

            relevant.append(lesson)

        # Sort by quality score (best first)
        relevant.sort(key=lambda l: -l.quality_score)

        return relevant
