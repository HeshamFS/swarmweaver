"""
Multi-Expertise Learning System (MELS) — SQLite Expertise Store
================================================================

Follows state/mail.py pattern (WAL mode, _ensure_tables()).
Tables: records, outcomes, domains, session_lessons.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from services.expertise_models import (
    ExpertiseRecord,
    Outcome,
    DomainConfig,
    SessionLesson,
    RECORD_TYPES,
    CLASSIFICATIONS,
    SHELF_LIFE_DAYS,
    domain_matches,
    infer_domain,
)
from services.expertise_scoring import (
    compute_confidence,
    compute_relevance,
)


def _json_col(val) -> str:
    """Serialize a Python value to JSON string for SQLite storage."""
    if val is None:
        return "[]"
    return json.dumps(val)


def _json_load(text: str):
    """Deserialize JSON string from SQLite."""
    if not text:
        return []
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return []


class ExpertiseStore:
    """SQLite-backed expertise store with WAL mode, concurrent-safe."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._ensure_tables()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), timeout=5)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=5000")
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _ensure_tables(self) -> None:
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS records (
                id TEXT PRIMARY KEY,
                record_type TEXT NOT NULL,
                classification TEXT NOT NULL,
                domain TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL,
                structured TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                expires_at TEXT,
                source_project TEXT NOT NULL DEFAULT '',
                source_session TEXT NOT NULL DEFAULT '',
                source_agent TEXT NOT NULL DEFAULT '',
                evidence TEXT NOT NULL DEFAULT '[]',
                resolves TEXT,
                resolved_by TEXT NOT NULL DEFAULT '[]',
                supersedes TEXT NOT NULL DEFAULT '[]',
                relates_to TEXT NOT NULL DEFAULT '[]',
                confidence REAL NOT NULL DEFAULT 0.5,
                relevance_score REAL NOT NULL DEFAULT 1.0,
                outcome_count INTEGER NOT NULL DEFAULT 0,
                success_count INTEGER NOT NULL DEFAULT 0,
                failure_count INTEGER NOT NULL DEFAULT 0,
                content_hash TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '[]',
                file_patterns TEXT NOT NULL DEFAULT '[]',
                is_archived INTEGER NOT NULL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_records_domain ON records(domain);
            CREATE INDEX IF NOT EXISTS idx_records_type ON records(record_type);
            CREATE INDEX IF NOT EXISTS idx_records_classification ON records(classification);
            CREATE INDEX IF NOT EXISTS idx_records_hash ON records(content_hash);
            CREATE INDEX IF NOT EXISTS idx_records_archived ON records(is_archived);
            CREATE INDEX IF NOT EXISTS idx_records_resolves ON records(resolves);

            CREATE TABLE IF NOT EXISTS outcomes (
                id TEXT PRIMARY KEY,
                record_id TEXT NOT NULL,
                status TEXT NOT NULL,
                agent TEXT NOT NULL DEFAULT '',
                session_id TEXT NOT NULL DEFAULT '',
                project TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                recorded_at TEXT NOT NULL,
                FOREIGN KEY (record_id) REFERENCES records(id)
            );

            CREATE INDEX IF NOT EXISTS idx_outcomes_record ON outcomes(record_id);

            CREATE TABLE IF NOT EXISTS domains (
                name TEXT PRIMARY KEY,
                parent TEXT,
                description TEXT NOT NULL DEFAULT '',
                soft_limit INTEGER NOT NULL DEFAULT 100,
                warn_limit INTEGER NOT NULL DEFAULT 150,
                hard_limit INTEGER NOT NULL DEFAULT 200
            );

            CREATE TABLE IF NOT EXISTS session_lessons (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                content TEXT NOT NULL,
                severity TEXT NOT NULL DEFAULT 'medium',
                domain TEXT NOT NULL DEFAULT '',
                file_patterns TEXT NOT NULL DEFAULT '[]',
                source_error_ids TEXT NOT NULL DEFAULT '[]',
                quality_score REAL NOT NULL DEFAULT 0.0,
                propagated_to TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                promoted_to_record_id TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_lessons_session ON session_lessons(session_id);
        """)
        conn.commit()

    # --- Record CRUD ---

    def add(self, record: ExpertiseRecord) -> str:
        """Insert a record with content_hash dedup. Returns the record ID."""
        conn = self._get_conn()

        # Dedup check
        if record.content_hash:
            existing = conn.execute(
                "SELECT id FROM records WHERE content_hash = ? AND is_archived = 0",
                (record.content_hash,),
            ).fetchone()
            if existing:
                return existing["id"]

        conn.execute(
            """INSERT INTO records (
                id, record_type, classification, domain, content, structured,
                created_at, updated_at, expires_at,
                source_project, source_session, source_agent, evidence,
                resolves, resolved_by, supersedes, relates_to,
                confidence, relevance_score, outcome_count, success_count, failure_count,
                content_hash, tags, file_patterns, is_archived
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.id, record.record_type, record.classification,
                record.domain, record.content, json.dumps(record.structured),
                record.created_at, record.updated_at, record.expires_at,
                record.source_project, record.source_session, record.source_agent,
                _json_col(record.evidence),
                record.resolves, _json_col(record.resolved_by),
                _json_col(record.supersedes), _json_col(record.relates_to),
                record.confidence, record.relevance_score,
                record.outcome_count, record.success_count, record.failure_count,
                record.content_hash, _json_col(record.tags),
                _json_col(record.file_patterns), int(record.is_archived),
            ),
        )

        # Update causal chain: if this resolves a failure, update that failure's resolved_by
        if record.resolves:
            failure = self.get(record.resolves)
            if failure:
                rb = list(failure.resolved_by)
                if record.id not in rb:
                    rb.append(record.id)
                    conn.execute(
                        "UPDATE records SET resolved_by = ? WHERE id = ?",
                        (_json_col(rb), record.resolves),
                    )

        conn.commit()
        return record.id

    def get(self, record_id: str) -> Optional[ExpertiseRecord]:
        """Get a record by ID."""
        row = self._get_conn().execute(
            "SELECT * FROM records WHERE id = ?", (record_id,),
        ).fetchone()
        if not row:
            return None
        return self._row_to_record(row)

    def update(self, record_id: str, **fields) -> bool:
        """Update specific fields on a record."""
        if not fields:
            return False

        conn = self._get_conn()
        json_fields = {"structured", "evidence", "resolved_by", "supersedes",
                       "relates_to", "tags", "file_patterns"}

        set_parts = []
        values = []
        for key, val in fields.items():
            if key in ("id",):
                continue
            set_parts.append(f"{key} = ?")
            if key in json_fields:
                values.append(_json_col(val))
            elif key == "is_archived":
                values.append(int(val))
            else:
                values.append(val)

        if not set_parts:
            return False

        # Always update updated_at
        set_parts.append("updated_at = ?")
        values.append(datetime.now(timezone.utc).isoformat())

        values.append(record_id)
        result = conn.execute(
            f"UPDATE records SET {', '.join(set_parts)} WHERE id = ?",
            values,
        )
        conn.commit()
        return result.rowcount > 0

    def archive(self, record_id: str) -> bool:
        """Soft-delete a record."""
        return self.update(record_id, is_archived=True)

    # --- Search & Query ---

    def search(
        self,
        query: str = "",
        domain: Optional[str] = None,
        record_type: Optional[str] = None,
        classification: Optional[str] = None,
        include_archived: bool = False,
        limit: int = 20,
    ) -> list[ExpertiseRecord]:
        """Keyword + domain + type filter search."""
        conn = self._get_conn()

        conditions = []
        params = []

        if not include_archived:
            conditions.append("is_archived = 0")

        if query:
            conditions.append("(content LIKE ? OR tags LIKE ?)")
            like = f"%{query}%"
            params.extend([like, like])

        if domain:
            # Hierarchical domain match
            conditions.append("(domain = ? OR domain LIKE ? OR ? LIKE domain || '.%')")
            params.extend([domain, f"{domain}.%", domain])

        if record_type:
            conditions.append("record_type = ?")
            params.append(record_type)

        if classification:
            conditions.append("classification = ?")
            params.append(classification)

        where = " AND ".join(conditions) if conditions else "1=1"

        rows = conn.execute(
            f"SELECT * FROM records WHERE {where} ORDER BY confidence DESC, updated_at DESC LIMIT ?",
            params + [limit],
        ).fetchall()

        return [self._row_to_record(r) for r in rows]

    def get_by_domain(self, domain: str, include_children: bool = True) -> list[ExpertiseRecord]:
        """Get records by domain with optional hierarchical matching."""
        conn = self._get_conn()
        if include_children:
            rows = conn.execute(
                "SELECT * FROM records WHERE (domain = ? OR domain LIKE ?) AND is_archived = 0 ORDER BY confidence DESC",
                (domain, f"{domain}.%"),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM records WHERE domain = ? AND is_archived = 0 ORDER BY confidence DESC",
                (domain,),
            ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def get_for_file_scope(self, file_scope: list[str]) -> list[ExpertiseRecord]:
        """Get records whose file_patterns match any of the given files."""
        import fnmatch as fnm

        all_records = self._get_conn().execute(
            "SELECT * FROM records WHERE is_archived = 0 AND file_patterns != '[]'",
        ).fetchall()

        results = []
        for row in all_records:
            record = self._row_to_record(row)
            for pat in record.file_patterns:
                for fp in file_scope:
                    if fnm.fnmatch(fp, pat):
                        results.append(record)
                        break
                else:
                    continue
                break

        return results

    def get_causal_chain(self, record_id: str) -> dict:
        """Get the full failure -> resolution chain for a record."""
        record = self.get(record_id)
        if not record:
            return {"root": None, "chain": []}

        chain = [record.to_dict()]

        # If this is a failure, get its resolutions
        if record.record_type == "failure" and record.resolved_by:
            for rid in record.resolved_by:
                resolution = self.get(rid)
                if resolution:
                    chain.append(resolution.to_dict())

        # If this is a resolution, get the failure it resolves
        if record.record_type == "resolution" and record.resolves:
            failure = self.get(record.resolves)
            if failure:
                chain.insert(0, failure.to_dict())
                # Also get sibling resolutions
                for rid in failure.resolved_by:
                    if rid != record_id:
                        sibling = self.get(rid)
                        if sibling:
                            chain.append(sibling.to_dict())

        return {"root": record_id, "chain": chain}

    # --- Outcome Tracking ---

    def record_outcome(self, record_id: str, outcome: Outcome) -> None:
        """Append an outcome and recompute confidence."""
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO outcomes (id, record_id, status, agent, session_id, project, notes, recorded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (outcome.id, record_id, outcome.status, outcome.agent,
             outcome.session_id, outcome.project, outcome.notes, outcome.recorded_at),
        )

        # Update record counts
        record = self.get(record_id)
        if record:
            record.outcome_count += 1
            if outcome.status == "success":
                record.success_count += 1
            elif outcome.status == "failure":
                record.failure_count += 1
            elif outcome.status == "partial":
                record.success_count += 0.5

            record.confidence = compute_confidence(record)
            record.relevance_score = compute_relevance(record)

            conn.execute(
                """UPDATE records SET outcome_count=?, success_count=?, failure_count=?,
                   confidence=?, relevance_score=?, updated_at=? WHERE id=?""",
                (record.outcome_count, record.success_count, record.failure_count,
                 record.confidence, record.relevance_score,
                 datetime.now(timezone.utc).isoformat(), record_id),
            )

        conn.commit()

    # --- Pruning & Governance ---

    def prune(self, dry_run: bool = False) -> dict:
        """Remove expired + low-confidence records."""
        conn = self._get_conn()
        now = datetime.now(timezone.utc).isoformat()

        # Find expired records
        expired = conn.execute(
            "SELECT id FROM records WHERE expires_at IS NOT NULL AND expires_at < ? AND is_archived = 0",
            (now,),
        ).fetchall()

        # Find very low confidence records (< 0.1 with 5+ outcomes)
        low_conf = conn.execute(
            "SELECT id FROM records WHERE confidence < 0.1 AND outcome_count >= 5 AND is_archived = 0",
        ).fetchall()

        to_archive = set(r["id"] for r in expired) | set(r["id"] for r in low_conf)

        result = {
            "expired_count": len(expired),
            "low_confidence_count": len(low_conf),
            "total_pruned": len(to_archive),
            "dry_run": dry_run,
        }

        if not dry_run and to_archive:
            placeholders = ",".join("?" * len(to_archive))
            conn.execute(
                f"UPDATE records SET is_archived = 1 WHERE id IN ({placeholders})",
                list(to_archive),
            )
            conn.commit()

        return result

    def get_domain_health(self) -> list[dict]:
        """Record counts vs governance limits per domain."""
        conn = self._get_conn()

        domain_counts = conn.execute(
            "SELECT domain, COUNT(*) as count FROM records WHERE is_archived = 0 GROUP BY domain ORDER BY count DESC",
        ).fetchall()

        results = []
        for row in domain_counts:
            domain = row["domain"]
            count = row["count"]

            # Check governance limits
            config_row = conn.execute(
                "SELECT * FROM domains WHERE name = ?", (domain,),
            ).fetchone()

            if config_row:
                cfg = DomainConfig(
                    name=config_row["name"],
                    parent=config_row["parent"],
                    description=config_row["description"],
                    soft_limit=config_row["soft_limit"],
                    warn_limit=config_row["warn_limit"],
                    hard_limit=config_row["hard_limit"],
                )
            else:
                cfg = DomainConfig(name=domain)

            status = "ok"
            if count >= cfg.hard_limit:
                status = "critical"
            elif count >= cfg.warn_limit:
                status = "warning"
            elif count >= cfg.soft_limit:
                status = "soft_warning"

            results.append({
                "domain": domain,
                "count": count,
                "soft_limit": cfg.soft_limit,
                "warn_limit": cfg.warn_limit,
                "hard_limit": cfg.hard_limit,
                "status": status,
            })

        return results

    # --- Domain Management ---

    def configure_domain(self, config: DomainConfig) -> None:
        """Create or update a domain configuration."""
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO domains (name, parent, description, soft_limit, warn_limit, hard_limit)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (config.name, config.parent, config.description,
             config.soft_limit, config.warn_limit, config.hard_limit),
        )
        conn.commit()

    def get_domains(self) -> list[dict]:
        """List all domains with record counts."""
        conn = self._get_conn()
        rows = conn.execute("""
            SELECT r.domain, COUNT(*) as count,
                   d.parent, d.description, d.soft_limit, d.warn_limit, d.hard_limit
            FROM records r
            LEFT JOIN domains d ON r.domain = d.name
            WHERE r.is_archived = 0 AND r.domain != ''
            GROUP BY r.domain
            ORDER BY count DESC
        """).fetchall()

        return [{
            "name": r["domain"],
            "count": r["count"],
            "parent": r["parent"],
            "description": r["description"] or "",
            "soft_limit": r["soft_limit"] or 100,
            "warn_limit": r["warn_limit"] or 150,
            "hard_limit": r["hard_limit"] or 200,
        } for r in rows]

    # --- Session Lessons ---

    def add_session_lesson(self, lesson: SessionLesson) -> str:
        """Insert a session lesson."""
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO session_lessons
               (id, session_id, content, severity, domain, file_patterns,
                source_error_ids, quality_score, propagated_to, created_at, promoted_to_record_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                lesson.id, lesson.session_id, lesson.content, lesson.severity,
                lesson.domain, _json_col(lesson.file_patterns),
                _json_col(lesson.source_error_ids), lesson.quality_score,
                _json_col(lesson.propagated_to), lesson.created_at,
                lesson.promoted_to_record_id,
            ),
        )
        conn.commit()
        return lesson.id

    def get_session_lessons(self, session_id: str) -> list[SessionLesson]:
        """Get all lessons for a session."""
        rows = self._get_conn().execute(
            "SELECT * FROM session_lessons WHERE session_id = ? ORDER BY quality_score DESC",
            (session_id,),
        ).fetchall()
        return [self._row_to_lesson(r) for r in rows]

    def get_recent_session_lessons(self, limit: int = 20) -> list[SessionLesson]:
        """Get all recent session lessons across all sessions."""
        rows = self._get_conn().execute(
            "SELECT * FROM session_lessons ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_lesson(r) for r in rows]

    def update_session_lesson(self, lesson_id: str, **fields) -> bool:
        """Update fields on a session lesson."""
        conn = self._get_conn()
        json_fields = {"file_patterns", "source_error_ids", "propagated_to"}
        set_parts = []
        values = []
        for key, val in fields.items():
            set_parts.append(f"{key} = ?")
            if key in json_fields:
                values.append(_json_col(val))
            else:
                values.append(val)
        if not set_parts:
            return False
        values.append(lesson_id)
        result = conn.execute(
            f"UPDATE session_lessons SET {', '.join(set_parts)} WHERE id = ?",
            values,
        )
        conn.commit()
        return result.rowcount > 0

    def promote_lesson(self, lesson_id: str) -> Optional[str]:
        """Promote a session lesson to a permanent expertise record."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM session_lessons WHERE id = ?", (lesson_id,),
        ).fetchone()
        if not row:
            return None

        lesson = self._row_to_lesson(row)
        if lesson.promoted_to_record_id:
            return lesson.promoted_to_record_id  # Already promoted

        record = ExpertiseRecord(
            record_type="insight",
            classification="tactical",
            domain=lesson.domain,
            content=lesson.content,
            structured={"source_lesson_id": lesson.id, "source_errors": lesson.source_error_ids},
            source_session=lesson.session_id,
            tags=["auto-promoted", "session-lesson"],
            file_patterns=lesson.file_patterns,
        )
        record_id = self.add(record)

        self.update_session_lesson(lesson_id, promoted_to_record_id=record_id)
        return record_id

    # --- Analytics ---

    def get_analytics(self) -> dict:
        """Dashboard data: top records, domain health, stats."""
        conn = self._get_conn()

        total = conn.execute("SELECT COUNT(*) as c FROM records WHERE is_archived = 0").fetchone()["c"]
        by_type = conn.execute(
            "SELECT record_type, COUNT(*) as c FROM records WHERE is_archived = 0 GROUP BY record_type"
        ).fetchall()
        by_class = conn.execute(
            "SELECT classification, COUNT(*) as c FROM records WHERE is_archived = 0 GROUP BY classification"
        ).fetchall()
        top_confidence = conn.execute(
            "SELECT id, content, confidence, domain FROM records WHERE is_archived = 0 ORDER BY confidence DESC LIMIT 10"
        ).fetchall()
        recent_outcomes = conn.execute(
            "SELECT * FROM outcomes ORDER BY recorded_at DESC LIMIT 20"
        ).fetchall()

        return {
            "total_records": total,
            "by_type": {r["record_type"]: r["c"] for r in by_type},
            "by_classification": {r["classification"]: r["c"] for r in by_class},
            "top_records": [
                {"id": r["id"], "content": r["content"][:100], "confidence": r["confidence"], "domain": r["domain"]}
                for r in top_confidence
            ],
            "recent_outcomes": [dict(r) for r in recent_outcomes],
            "domain_health": self.get_domain_health(),
        }

    # --- Export ---

    def export_all(self) -> list[dict]:
        """Export all non-archived records as dicts."""
        rows = self._get_conn().execute(
            "SELECT * FROM records WHERE is_archived = 0 ORDER BY domain, record_type"
        ).fetchall()
        return [self._row_to_record(r).to_dict() for r in rows]

    # --- Helpers ---

    def _row_to_record(self, row: sqlite3.Row) -> ExpertiseRecord:
        return ExpertiseRecord(
            id=row["id"],
            record_type=row["record_type"],
            classification=row["classification"],
            domain=row["domain"],
            content=row["content"],
            structured=json.loads(row["structured"]) if row["structured"] else {},
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            expires_at=row["expires_at"],
            source_project=row["source_project"],
            source_session=row["source_session"],
            source_agent=row["source_agent"],
            evidence=_json_load(row["evidence"]),
            resolves=row["resolves"],
            resolved_by=_json_load(row["resolved_by"]),
            supersedes=_json_load(row["supersedes"]),
            relates_to=_json_load(row["relates_to"]),
            confidence=row["confidence"],
            relevance_score=row["relevance_score"],
            outcome_count=row["outcome_count"],
            success_count=row["success_count"],
            failure_count=row["failure_count"],
            content_hash=row["content_hash"],
            tags=_json_load(row["tags"]),
            file_patterns=_json_load(row["file_patterns"]),
            is_archived=bool(row["is_archived"]),
        )

    def _row_to_lesson(self, row: sqlite3.Row) -> SessionLesson:
        return SessionLesson(
            id=row["id"],
            session_id=row["session_id"],
            content=row["content"],
            severity=row["severity"],
            domain=row["domain"],
            file_patterns=_json_load(row["file_patterns"]),
            source_error_ids=_json_load(row["source_error_ids"]),
            quality_score=row["quality_score"],
            propagated_to=_json_load(row["propagated_to"]),
            created_at=row["created_at"],
            promoted_to_record_id=row["promoted_to_record_id"],
        )

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None


# --- Singleton Access ---

_cross_project_store: Optional[ExpertiseStore] = None
_project_stores: dict[str, ExpertiseStore] = {}


def get_cross_project_store() -> ExpertiseStore:
    """Get the global cross-project expertise store (~/.swarmweaver/expertise/)."""
    global _cross_project_store
    if _cross_project_store is None:
        db_path = Path.home() / ".swarmweaver" / "expertise" / "expertise.db"
        _cross_project_store = ExpertiseStore(db_path)
    return _cross_project_store


def get_project_store(project_dir: Path) -> ExpertiseStore:
    """Get the project-local expertise store (.swarmweaver/expertise/)."""
    key = str(project_dir)
    if key not in _project_stores:
        db_path = project_dir / ".swarmweaver" / "expertise" / "expertise.db"
        _project_stores[key] = ExpertiseStore(db_path)
    return _project_stores[key]
