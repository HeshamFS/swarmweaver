"""Expertise endpoints (MELS — Multi-Expertise Learning System)."""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter()


# --- Request/Response Models ---

class ExpertiseRecordCreate(BaseModel):
    record_type: str = "pattern"
    classification: str = "tactical"
    domain: str = ""
    content: str
    structured: dict = {}
    source_project: str = ""
    source_agent: str = ""
    resolves: Optional[str] = None
    tags: list[str] = []
    file_patterns: list[str] = []


class ExpertiseRecordUpdate(BaseModel):
    content: Optional[str] = None
    classification: Optional[str] = None
    domain: Optional[str] = None
    tags: Optional[list[str]] = None
    file_patterns: Optional[list[str]] = None
    is_archived: Optional[bool] = None


class OutcomeCreate(BaseModel):
    status: str  # success | failure | partial
    agent: str = ""
    session_id: str = ""
    project: str = ""
    notes: str = ""


class DomainConfigCreate(BaseModel):
    name: str
    parent: Optional[str] = None
    description: str = ""
    soft_limit: int = 100
    warn_limit: int = 150
    hard_limit: int = 200


# --- Helpers ---

def _get_cross_store():
    from services.expertise_store import get_cross_project_store
    return get_cross_project_store()


def _get_project_store(project_dir: str):
    from services.expertise_store import get_project_store
    return get_project_store(Path(project_dir))


# --- Endpoints ---

@router.get("/api/expertise")
async def list_records(
    domain: Optional[str] = Query(None),
    record_type: Optional[str] = Query(None, alias="type"),
    classification: Optional[str] = Query(None),
    search: Optional[str] = Query(None, alias="q"),
    archived: bool = Query(False),
    project_dir: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
):
    """List expertise records with optional filters."""
    try:
        store = _get_project_store(project_dir) if project_dir else _get_cross_store()
        records = store.search(
            query=search or "",
            domain=domain,
            record_type=record_type,
            classification=classification,
            include_archived=archived,
            limit=limit,
        )
        return {
            "records": [r.to_dict() for r in records],
            "count": len(records),
        }
    except Exception as e:
        return {"records": [], "count": 0, "error": str(e)}


@router.post("/api/expertise")
async def create_record(body: ExpertiseRecordCreate, project_dir: Optional[str] = Query(None)):
    """Create a new expertise record."""
    try:
        from services.expertise_models import ExpertiseRecord, RECORD_TYPES, CLASSIFICATIONS
        import hashlib

        if body.record_type not in RECORD_TYPES:
            raise HTTPException(400, f"Invalid record_type. Must be one of: {RECORD_TYPES}")
        if body.classification not in CLASSIFICATIONS:
            raise HTTPException(400, f"Invalid classification. Must be one of: {CLASSIFICATIONS}")

        record = ExpertiseRecord(
            record_type=body.record_type,
            classification=body.classification,
            domain=body.domain,
            content=body.content,
            structured=body.structured,
            source_project=body.source_project,
            source_agent=body.source_agent,
            resolves=body.resolves,
            tags=body.tags,
            file_patterns=body.file_patterns,
            content_hash=hashlib.sha256(body.content.encode()).hexdigest(),
        )

        store = _get_project_store(project_dir) if project_dir else _get_cross_store()
        record_id = store.add(record)
        return {"status": "ok", "id": record_id}
    except HTTPException:
        raise
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/api/expertise/{record_id}")
async def get_record(record_id: str, project_dir: Optional[str] = Query(None)):
    """Get a single record with full details."""
    store = _get_project_store(project_dir) if project_dir else _get_cross_store()
    record = store.get(record_id)
    if not record:
        raise HTTPException(404, "Record not found")
    return {"record": record.to_dict()}


@router.put("/api/expertise/{record_id}")
async def update_record(record_id: str, body: ExpertiseRecordUpdate, project_dir: Optional[str] = Query(None)):
    """Update a record's fields."""
    store = _get_project_store(project_dir) if project_dir else _get_cross_store()
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(400, "No fields to update")
    if not store.update(record_id, **fields):
        raise HTTPException(404, "Record not found")
    return {"status": "ok"}


@router.delete("/api/expertise/{record_id}")
async def archive_record(record_id: str, project_dir: Optional[str] = Query(None)):
    """Archive (soft-delete) a record."""
    store = _get_project_store(project_dir) if project_dir else _get_cross_store()
    if not store.archive(record_id):
        raise HTTPException(404, "Record not found")
    return {"status": "ok"}


@router.post("/api/expertise/{record_id}/outcome")
async def record_outcome(record_id: str, body: OutcomeCreate, project_dir: Optional[str] = Query(None)):
    """Record an outcome for a record."""
    if body.status not in ("success", "failure", "partial"):
        raise HTTPException(400, "status must be 'success', 'failure', or 'partial'")

    from services.expertise_models import Outcome
    store = _get_project_store(project_dir) if project_dir else _get_cross_store()

    record = store.get(record_id)
    if not record:
        raise HTTPException(404, "Record not found")

    outcome = Outcome(
        record_id=record_id,
        status=body.status,
        agent=body.agent,
        session_id=body.session_id,
        project=body.project,
        notes=body.notes,
    )
    store.record_outcome(record_id, outcome)
    return {"status": "ok"}


@router.get("/api/expertise/search")
async def search_records(
    q: str = Query(...),
    domain: Optional[str] = Query(None),
    record_type: Optional[str] = Query(None, alias="type"),
    project_dir: Optional[str] = Query(None),
    limit: int = Query(20),
):
    """Full-text + domain + type search."""
    store = _get_project_store(project_dir) if project_dir else _get_cross_store()
    records = store.search(query=q, domain=domain, record_type=record_type, limit=limit)
    return {"results": [r.to_dict() for r in records], "count": len(records)}


@router.get("/api/expertise/prime")
async def get_priming(
    files: str = Query(""),
    domains: str = Query(""),
    task: str = Query(""),
    budget: int = Query(2000),
    project_dir: Optional[str] = Query(None),
):
    """Get priming context for files/domains."""
    try:
        from services.expertise_priming import PrimingEngine

        store = _get_project_store(project_dir) if project_dir else _get_cross_store()
        engine = PrimingEngine()

        file_list = [f.strip() for f in files.split(",") if f.strip()] if files else []
        domain_list = [d.strip() for d in domains.split(",") if d.strip()] if domains else None

        context = engine.prime(
            store,
            file_scope=file_list,
            domains=domain_list,
            task_description=task,
            budget_tokens=budget,
        )
        return {"context": context, "files": file_list, "domains": domain_list or []}
    except Exception as e:
        return {"context": "", "error": str(e)}


@router.get("/api/expertise/causal-chain/{record_id}")
async def get_causal_chain(record_id: str, project_dir: Optional[str] = Query(None)):
    """Get failure -> resolution chain for a record."""
    store = _get_project_store(project_dir) if project_dir else _get_cross_store()
    chain = store.get_causal_chain(record_id)
    return chain


@router.get("/api/expertise/domains")
async def list_domains(project_dir: Optional[str] = Query(None)):
    """List all domains with stats."""
    store = _get_project_store(project_dir) if project_dir else _get_cross_store()
    return {"domains": store.get_domains()}


@router.post("/api/expertise/domains")
async def configure_domain(body: DomainConfigCreate, project_dir: Optional[str] = Query(None)):
    """Create or configure a domain."""
    from services.expertise_models import DomainConfig
    store = _get_project_store(project_dir) if project_dir else _get_cross_store()
    config = DomainConfig(
        name=body.name,
        parent=body.parent,
        description=body.description,
        soft_limit=body.soft_limit,
        warn_limit=body.warn_limit,
        hard_limit=body.hard_limit,
    )
    store.configure_domain(config)
    return {"status": "ok"}


@router.get("/api/expertise/analytics")
async def get_analytics(project_dir: Optional[str] = Query(None)):
    """Dashboard data: top records, domain health, stats."""
    store = _get_project_store(project_dir) if project_dir else _get_cross_store()
    return store.get_analytics()


@router.get("/api/expertise/session-lessons")
async def get_session_lessons(session_id: Optional[str] = Query(None), project_dir: Optional[str] = Query(None), limit: int = Query(20)):
    """Get lessons for a specific session, or all recent lessons if no session_id."""
    store = _get_project_store(project_dir) if project_dir else _get_cross_store()
    if session_id:
        lessons = store.get_session_lessons(session_id)
    else:
        lessons = store.get_recent_session_lessons(limit=limit)
    return {"lessons": [
        {
            "id": l.id,
            "session_id": l.session_id,
            "content": l.content,
            "severity": l.severity,
            "domain": l.domain,
            "file_patterns": l.file_patterns,
            "quality_score": l.quality_score,
            "propagated_to": l.propagated_to,
            "created_at": l.created_at,
            "promoted_to_record_id": l.promoted_to_record_id,
        }
        for l in lessons
    ]}


@router.post("/api/expertise/migrate")
async def trigger_migration(project_dir: Optional[str] = Query(None)):
    """Trigger migration from legacy JSON stores."""
    try:
        from services.expertise_migration import ExpertiseMigrator
        migrator = ExpertiseMigrator()
        result = migrator.migrate_all(
            project_dir=Path(project_dir) if project_dir else None,
        )
        return {"status": "ok", **result}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/api/expertise/prune")
async def trigger_prune(dry_run: bool = Query(False), project_dir: Optional[str] = Query(None)):
    """Trigger pruning of expired/low-confidence records."""
    store = _get_project_store(project_dir) if project_dir else _get_cross_store()
    result = store.prune(dry_run=dry_run)
    return {"status": "ok", **result}


@router.get("/api/expertise/export")
async def export_records(project_dir: Optional[str] = Query(None)):
    """Export all records as JSON."""
    store = _get_project_store(project_dir) if project_dir else _get_cross_store()
    return {"records": store.export_all()}
