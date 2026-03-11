"""
Multi-Expertise Learning System (MELS) — Migration
====================================================

Migrates from existing JSON-based systems:
- ~/.swarmweaver/memory/memories.json -> cross-project expertise.db
- .swarmweaver/expertise/index.json -> project expertise.db
- .swarmweaver/swarm/lessons.json -> project expertise.db
"""

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from services.expertise_models import ExpertiseRecord, SessionLesson
from services.expertise_store import ExpertiseStore


# Category -> record_type mapping for memories.json
_CATEGORY_TO_TYPE = {
    "pattern": "pattern",
    "mistake": "failure",
    "solution": "resolution",
    "preference": "convention",
}

# Expertise type -> record_type mapping
_EXPERTISE_TYPE_MAP = {
    "convention": "convention",
    "pattern": "pattern",
    "failure": "failure",
    "decision": "decision",
    "reference": "reference",
}


class ExpertiseMigrator:
    """Migrates legacy JSON stores to SQLite expertise stores."""

    def migrate_memories_json(self, store: ExpertiseStore) -> int:
        """Migrate ~/.swarmweaver/memory/memories.json -> expertise.db.

        Maps: pattern->pattern, mistake->failure, solution->resolution, preference->convention.
        Sets classification based on outcome history.
        Backs up to memories.json.migrated.
        """
        memories_path = Path.home() / ".swarmweaver" / "memory" / "memories.json"
        if not memories_path.exists():
            return 0

        try:
            data = json.loads(memories_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return 0

        if not isinstance(data, list):
            return 0

        count = 0
        for entry in data:
            if not isinstance(entry, dict) or not entry.get("content"):
                continue

            category = entry.get("category", "pattern")
            record_type = _CATEGORY_TO_TYPE.get(category, "pattern")

            # Override with expertise_type if present
            etype = entry.get("expertise_type", "")
            if etype and etype in _EXPERTISE_TYPE_MAP:
                record_type = _EXPERTISE_TYPE_MAP[etype]

            # Determine classification from outcome history
            outcome_count = entry.get("outcome_count", 0)
            success_count = entry.get("success_count", 0)
            if outcome_count >= 5 and (success_count / max(outcome_count, 1)) > 0.7:
                classification = "foundational"
            elif outcome_count >= 2:
                classification = "tactical"
            else:
                classification = "observational"

            content = entry["content"]
            content_hash = hashlib.sha256(content.encode()).hexdigest()

            record = ExpertiseRecord(
                id=f"mig-{entry.get('id', '')}" if entry.get("id") else "",
                record_type=record_type,
                classification=classification,
                domain=entry.get("domain", ""),
                content=content,
                created_at=entry.get("created_at", datetime.now(timezone.utc).isoformat()),
                source_project=entry.get("project_source", ""),
                confidence=0.5,
                relevance_score=entry.get("relevance_score", 1.0),
                outcome_count=outcome_count,
                success_count=int(success_count),
                failure_count=max(0, outcome_count - int(success_count)),
                content_hash=content_hash,
                tags=entry.get("tags", []),
            )

            store.add(record)
            count += 1

        # Also migrate domain files
        domains_dir = Path.home() / ".swarmweaver" / "memory" / "domains"
        if domains_dir.exists():
            for domain_file in domains_dir.glob("*.json"):
                try:
                    domain_data = json.loads(domain_file.read_text(encoding="utf-8"))
                    for entry in domain_data:
                        if not isinstance(entry, dict) or not entry.get("content"):
                            continue
                        content = entry["content"]
                        content_hash = hashlib.sha256(content.encode()).hexdigest()

                        record = ExpertiseRecord(
                            id=f"mig-{entry.get('id', '')}" if entry.get("id") else "",
                            record_type=_CATEGORY_TO_TYPE.get(entry.get("category", "pattern"), "pattern"),
                            classification="tactical",
                            domain=entry.get("domain", domain_file.stem),
                            content=content,
                            created_at=entry.get("created_at", datetime.now(timezone.utc).isoformat()),
                            source_project=entry.get("project_source", ""),
                            content_hash=content_hash,
                            tags=entry.get("tags", []),
                        )
                        store.add(record)
                        count += 1
                except (json.JSONDecodeError, OSError):
                    continue

        # Backup original
        if count > 0:
            backup_path = memories_path.parent / "memories.json.migrated"
            if not backup_path.exists():
                shutil.copy2(memories_path, backup_path)

        return count

    def migrate_project_expertise(self, project_dir: Path, store: ExpertiseStore) -> int:
        """Migrate .swarmweaver/expertise/index.json -> project expertise.db."""
        index_path = project_dir / ".swarmweaver" / "expertise" / "index.json"
        if not index_path.exists():
            return 0

        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return 0

        if not isinstance(data, list):
            return 0

        count = 0
        for entry in data:
            if not isinstance(entry, dict) or not entry.get("content"):
                continue

            category = entry.get("category", "pattern")
            record_type = _EXPERTISE_TYPE_MAP.get(category, "pattern")

            content = entry["content"]
            content_hash = hashlib.sha256(content.encode()).hexdigest()

            record = ExpertiseRecord(
                id=f"pmig-{entry.get('id', '')}" if entry.get("id") else "",
                record_type=record_type,
                classification="tactical",
                domain=entry.get("domain", ""),
                content=content,
                created_at=entry.get("created_at", datetime.now(timezone.utc).isoformat()),
                source_project=str(project_dir),
                content_hash=content_hash,
                tags=entry.get("tags", []),
                file_patterns=[entry["source_file"]] if entry.get("source_file") else [],
            )

            store.add(record)
            count += 1

        return count

    def migrate_lessons(self, project_dir: Path, store: ExpertiseStore) -> int:
        """Migrate .swarmweaver/swarm/lessons.json -> expertise.db.

        errors -> failure records, lessons -> insight records.
        """
        lessons_path = project_dir / ".swarmweaver" / "swarm" / "lessons.json"
        if not lessons_path.exists():
            # Also check legacy path
            lessons_path = project_dir / ".swarmweaver" / "lessons.json"
            if not lessons_path.exists():
                return 0

        try:
            data = json.loads(lessons_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return 0

        count = 0

        # Migrate errors
        for err in data.get("errors", []):
            if not isinstance(err, dict) or not err.get("error_message"):
                continue

            content = err["error_message"][:500]
            content_hash = hashlib.sha256(content.encode()).hexdigest()

            record = ExpertiseRecord(
                record_type="failure",
                classification="observational",
                domain="",
                content=content,
                structured={
                    "tool_name": err.get("tool_name", ""),
                    "error_pattern": content[:200],
                    "file_path": err.get("file_path", ""),
                },
                created_at=err.get("timestamp", datetime.now(timezone.utc).isoformat()),
                source_project=str(project_dir),
                source_agent=err.get("worker_name", ""),
                content_hash=content_hash,
                file_patterns=[err["file_path"]] if err.get("file_path") else [],
            )
            store.add(record)
            count += 1

        # Migrate lessons
        for lesson in data.get("lessons", []):
            if not isinstance(lesson, dict) or not lesson.get("lesson"):
                continue

            content = lesson["lesson"]
            content_hash = hashlib.sha256(content.encode()).hexdigest()

            record = ExpertiseRecord(
                record_type="insight",
                classification="tactical",
                domain="",
                content=content,
                structured={
                    "source_errors": lesson.get("source_errors", []),
                    "severity": lesson.get("severity", "medium"),
                },
                created_at=lesson.get("created_at", datetime.now(timezone.utc).isoformat()),
                source_project=str(project_dir),
                source_agent=lesson.get("created_by", "orchestrator"),
                content_hash=content_hash,
                file_patterns=lesson.get("applies_to", []),
            )
            store.add(record)
            count += 1

        return count

    def migrate_all(self, project_dir: Optional[Path] = None) -> dict:
        """Run all migrations. Returns counts."""
        from services.expertise_store import get_cross_project_store, get_project_store

        cross_store = get_cross_project_store()
        mem_count = self.migrate_memories_json(cross_store)

        proj_count = 0
        lesson_count = 0
        if project_dir:
            proj_store = get_project_store(project_dir)
            proj_count = self.migrate_project_expertise(project_dir, proj_store)
            lesson_count = self.migrate_lessons(project_dir, proj_store)

        return {
            "memories_migrated": mem_count,
            "project_expertise_migrated": proj_count,
            "lessons_migrated": lesson_count,
            "total": mem_count + proj_count + lesson_count,
        }
