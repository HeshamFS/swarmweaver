"""Session History API — browse, search, and manage persistent session records."""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query

from state.sessions import SessionStore, GlobalSessionIndex

router = APIRouter()


def _get_store(project_dir: str) -> SessionStore:
    store = SessionStore(Path(project_dir))
    store.initialize()
    return store


@router.get("/api/sessions")
async def list_sessions(
    path: str = Query(..., description="Project directory"),
    status: Optional[str] = Query(None),
    mode: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
):
    """List sessions with optional filters."""
    try:
        store = _get_store(path)
        sessions = store.list_sessions(
            status=status, mode=mode, limit=limit, offset=offset
        )
        return {"sessions": sessions, "count": len(sessions)}
    except Exception as e:
        return {"sessions": [], "count": 0, "error": str(e)}


@router.get("/api/sessions/analytics")
async def session_analytics(
    path: str = Query(..., description="Project directory"),
    since: Optional[str] = Query(None),
    mode: Optional[str] = Query(None),
):
    """Session analytics (total, avg cost, by mode/status)."""
    try:
        store = _get_store(path)
        return store.get_analytics(since=since, mode=mode)
    except Exception as e:
        return {"error": str(e)}


@router.get("/api/sessions/global")
async def global_sessions(
    project_dir: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
):
    """Cross-project session list from global index."""
    try:
        idx = GlobalSessionIndex()
        idx.initialize()
        sessions = idx.list_sessions(
            project_dir=project_dir, status=status,
            limit=limit, offset=offset,
        )
        return {"sessions": sessions, "count": len(sessions)}
    except Exception as e:
        return {"sessions": [], "count": 0, "error": str(e)}


@router.get("/api/sessions/{session_id}")
async def get_session_detail(
    session_id: str,
    path: str = Query(..., description="Project directory"),
):
    """Full session detail (session + messages + file_changes)."""
    try:
        store = _get_store(path)
        detail = store.get_detail(session_id)
        if not detail:
            return {"error": "Session not found"}
        return detail
    except Exception as e:
        return {"error": str(e)}


@router.get("/api/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    path: str = Query(..., description="Project directory"),
    agent_name: Optional[str] = Query(None),
    limit: int = Query(200, le=500),
):
    """Messages for a session."""
    try:
        store = _get_store(path)
        messages = store.get_messages(
            session_id, agent_name=agent_name, limit=limit
        )
        return {"messages": messages, "count": len(messages)}
    except Exception as e:
        return {"messages": [], "count": 0, "error": str(e)}


@router.get("/api/sessions/{session_id}/files")
async def get_session_files(
    session_id: str,
    path: str = Query(..., description="Project directory"),
):
    """File change list for a session."""
    try:
        store = _get_store(path)
        changes = store.get_file_changes(session_id)
        return {"file_changes": changes, "count": len(changes)}
    except Exception as e:
        return {"file_changes": [], "count": 0, "error": str(e)}


@router.post("/api/sessions/{session_id}/archive")
async def archive_session(
    session_id: str,
    path: str = Query(..., description="Project directory"),
):
    """Archive (soft-delete) a session."""
    try:
        store = _get_store(path)
        store.archive_session(session_id)
        return {"status": "archived", "session_id": session_id}
    except Exception as e:
        return {"error": str(e)}


@router.delete("/api/sessions/{session_id}")
async def delete_session(
    session_id: str,
    path: str = Query(..., description="Project directory"),
):
    """Delete session and all related data."""
    try:
        store = _get_store(path)
        deleted = store.delete_session(session_id)
        return {"deleted": deleted, "session_id": session_id}
    except Exception as e:
        return {"error": str(e)}


@router.post("/api/sessions/migrate")
async def migrate_chains(
    path: str = Query(..., description="Project directory"),
):
    """Trigger chain→sessions migration."""
    try:
        store = _get_store(path)
        count = store.migrate_from_chains()
        return {"migrated": count}
    except Exception as e:
        return {"error": str(e)}
