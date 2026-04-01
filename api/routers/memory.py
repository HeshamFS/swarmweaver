"""Memory file management API endpoints."""

import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query, HTTPException

router = APIRouter()


@router.get("/api/memory/claude-md")
async def get_claude_md_files(
    path: Optional[str] = Query(None, description="Project directory path"),
):
    """List all discovered CLAUDE.md files."""
    from services.memory_files import load_claude_md_files
    project_dir = Path(path) if path else None
    files = load_claude_md_files(project_dir)
    return {"files": [{"path": f.path, "scope": f.scope, "content": f.content, "is_rules": f.is_rules} for f in files]}


@router.get("/api/memory/claude-md/content")
async def get_claude_md_content(
    scope: str = Query("project", description="global, project, or local"),
    path: Optional[str] = Query(None, description="Project directory path"),
):
    """Get a specific CLAUDE.md file content."""
    from services.memory_files import global_claude_md, project_claude_md, project_local_claude_md

    if scope == "global":
        fpath = global_claude_md()
    elif scope == "local" and path:
        fpath = project_local_claude_md(Path(path))
    elif path:
        fpath = project_claude_md(Path(path))
    else:
        return {"content": "", "exists": False}

    if fpath.is_file():
        return {"content": fpath.read_text(encoding="utf-8"), "exists": True, "path": str(fpath)}
    return {"content": "", "exists": False, "path": str(fpath)}


@router.post("/api/memory/claude-md")
async def save_claude_md(body: dict):
    """Save CLAUDE.md content."""
    from services.memory_files import global_claude_md, project_claude_md, project_local_claude_md

    scope = body.get("scope", "project")
    content = body.get("content", "")
    project_path = body.get("path")

    if scope == "global":
        fpath = global_claude_md()
    elif scope == "local" and project_path:
        fpath = project_local_claude_md(Path(project_path))
    elif project_path:
        fpath = project_claude_md(Path(project_path))
    else:
        raise HTTPException(status_code=400, detail="path required for project/local scope")

    fpath.parent.mkdir(parents=True, exist_ok=True)
    fpath.write_text(content, encoding="utf-8")
    return {"status": "ok", "path": str(fpath)}


@router.get("/api/memory/files")
async def list_memory_files(
    scope: str = Query("project", description="global or project"),
    path: Optional[str] = Query(None, description="Project directory path"),
):
    """List memory topic files."""
    from services.memory_files import scan_memory_files, global_memory_dir, project_memory_dir

    if scope == "global":
        mem_dir = global_memory_dir()
    elif path:
        mem_dir = project_memory_dir(Path(path))
    else:
        return {"files": [], "index": ""}

    from services.memory_files import load_memory_index
    files = scan_memory_files(mem_dir)
    index = load_memory_index(mem_dir)

    return {
        "files": [f.to_dict() for f in files],
        "index": index,
        "directory": str(mem_dir),
    }


@router.post("/api/memory/files")
async def save_memory_file_endpoint(body: dict):
    """Save a memory topic file."""
    from services.memory_files import save_memory_file, update_memory_index

    name = body.get("name", "")
    content = body.get("content", "")
    memory_type = body.get("type", "project")
    description = body.get("description", "")
    scope = body.get("scope", "project")
    project_path = body.get("path")

    if not name or not content:
        raise HTTPException(status_code=400, detail="name and content required")

    project_dir = Path(project_path) if project_path else None
    file_path = save_memory_file(name, content, memory_type, description, scope, project_dir)

    # Update MEMORY.md index
    filename = re.sub(r"[^\w\-.]", "_", name.lower()) + ".md"
    hook = description[:150] if description else content[:100].replace("\n", " ")
    update_memory_index(name, filename, hook, scope, project_dir)

    return {"status": "ok", "path": str(file_path)}


@router.delete("/api/memory/files/{filename}")
async def remove_memory_file(
    filename: str,
    scope: str = Query("project"),
    path: Optional[str] = Query(None),
):
    """Delete a memory topic file."""
    from services.memory_files import delete_memory_file
    project_dir = Path(path) if path else None
    deleted = delete_memory_file(filename, scope, project_dir)
    if not deleted:
        raise HTTPException(status_code=404, detail="File not found")
    return {"status": "ok"}


@router.get("/api/memory/index")
async def get_memory_index(
    scope: str = Query("project"),
    path: Optional[str] = Query(None),
):
    """Get MEMORY.md index content."""
    from services.memory_files import load_memory_index, global_memory_dir, project_memory_dir

    if scope == "global":
        mem_dir = global_memory_dir()
    elif path:
        mem_dir = project_memory_dir(Path(path))
    else:
        return {"index": ""}

    return {"index": load_memory_index(mem_dir)}


@router.post("/api/memory/index")
async def save_memory_index(body: dict):
    """Save MEMORY.md index content directly."""
    from services.memory_files import global_memory_dir, project_memory_dir

    scope = body.get("scope", "project")
    content = body.get("content", "")
    project_path = body.get("path")

    if scope == "global":
        mem_dir = global_memory_dir()
    elif project_path:
        mem_dir = project_memory_dir(Path(project_path))
    else:
        raise HTTPException(status_code=400, detail="path required")

    mem_dir.mkdir(parents=True, exist_ok=True)
    index_path = mem_dir / "MEMORY.md"
    index_path.write_text(content, encoding="utf-8")
    return {"status": "ok"}
