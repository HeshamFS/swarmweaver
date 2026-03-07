"""Memory and expertise endpoints."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()


@router.get("/api/memory")
async def list_memories(
    category: Optional[str] = Query(None, description="Filter by category"),
):
    """List all agent memories."""
    try:
        from features.memory import AgentMemory
        mem = AgentMemory()
        entries = mem.list_all(category=category)
        return {"memories": [e.__dict__ for e in entries]}
    except Exception as e:
        return {"memories": [], "error": str(e)}


@router.post("/api/memory")
async def add_memory(
    category: str = Query("pattern", description="Memory category"),
    content: str = Query(..., description="Memory content"),
    tags: str = Query("", description="Comma-separated tags"),
    project_source: str = Query("", description="Source project"),
    domain: str = Query("", description="Expertise domain"),
):
    """Add a new memory entry with optional domain."""
    try:
        from features.memory import AgentMemory
        mem = AgentMemory()
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
        mem_id = mem.add(category, content, tag_list, project_source, domain=domain)
        return {"status": "ok", "id": mem_id}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.delete("/api/memory/{memory_id}")
async def delete_memory(memory_id: str):
    """Delete a memory entry."""
    try:
        from features.memory import AgentMemory
        mem = AgentMemory()
        removed = mem.remove(memory_id)
        return {"status": "ok" if removed else "not_found"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/api/memory/{memory_id}/outcome")
async def record_memory_outcome(memory_id: str, outcome: str = Query(..., description="One of: success, failure, partial")):
    """Record an outcome for a memory entry and adjust its relevance score."""
    if outcome not in ("success", "failure", "partial"):
        raise HTTPException(status_code=400, detail="Invalid outcome. Must be 'success', 'failure', or 'partial'.")

    from dataclasses import asdict
    from features.memory import AgentMemory

    memory = AgentMemory()
    if not memory.record_outcome(memory_id, outcome):
        raise HTTPException(status_code=404, detail="Memory entry not found")

    entry = memory.get_by_id(memory_id)
    return {"status": "ok", "entry": asdict(entry) if entry else None}


@router.get("/api/memory/search")
async def search_memories(
    q: str = Query(..., description="Search query"),
):
    """Search memories by keyword."""
    try:
        from features.memory import AgentMemory
        mem = AgentMemory()
        results = mem.search(q)
        return {"results": [e.__dict__ for e in results]}
    except Exception as e:
        return {"results": [], "error": str(e)}


@router.get("/api/memory/prime")
async def prime_memory(
    files: str = Query("", description="Comma-separated file paths"),
    domains: str = Query("", description="Comma-separated domain names"),
):
    """Get priming context from agent memory based on files and domains."""
    try:
        from features.memory import AgentMemory
        mem = AgentMemory()
        file_list = [f.strip() for f in files.split(",") if f.strip()] if files else []
        domain_list = [d.strip() for d in domains.split(",") if d.strip()] if domains else []
        context = mem.get_priming_context(file_list, domain_list if domain_list else None)
        return {"context": context, "files": file_list, "domains": domain_list}
    except Exception as e:
        return {"context": "", "error": str(e)}
