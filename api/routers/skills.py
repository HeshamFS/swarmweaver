"""Skill management API endpoints."""

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query, HTTPException

router = APIRouter()


@router.get("/api/skills")
async def list_skills(
    path: Optional[str] = Query(None, description="Project directory path"),
):
    """List all discovered skills."""
    from features.skills import discover_skills
    project_dir = Path(path) if path else None
    skills = discover_skills(project_dir)
    return {"skills": [s.to_dict() for s in skills]}


@router.get("/api/skills/{name}")
async def get_skill(
    name: str,
    path: Optional[str] = Query(None, description="Project directory path"),
):
    """Get a specific skill by name."""
    from features.skills import get_skill_by_name
    project_dir = Path(path) if path else None
    skill = get_skill_by_name(name, project_dir)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
    return skill.to_dict()


@router.post("/api/skills/{name}/execute")
async def execute_skill(
    name: str,
    path: Optional[str] = Query(None, description="Project directory path"),
    body: dict = {},
):
    """Execute a skill."""
    from features.skills import get_skill_by_name, expand_skill_inline, substitute_variables
    project_dir = Path(path) if path else None
    skill = get_skill_by_name(name, project_dir)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")

    args = body.get("args", {})
    context_data = {
        "project_dir": str(project_dir) if project_dir else "",
        "session_id": "",
        "mode": body.get("mode", ""),
    }

    if skill.context == "inline":
        expanded = expand_skill_inline(skill, args, context_data)
        return {"status": "ok", "context": "inline", "expanded": expanded}
    else:
        # Fork: return the expanded prompt for the caller to run as a sub-agent
        expanded = substitute_variables(skill.body, args, {
            "skill_dir": str(Path(skill.source_path).parent),
            **context_data,
        })
        return {"status": "ok", "context": "fork", "prompt": expanded, "model": skill.model}


@router.post("/api/skills/{name}/toggle")
async def toggle_skill(name: str):
    """Toggle a skill's enabled state."""
    # For now, return success - skill enable/disable state is managed client-side
    return {"status": "ok", "name": name}


@router.post("/api/skills/upload")
async def upload_skill(body: dict):
    """Upload a new skill."""
    from features.skills import save_skill
    content = body.get("content", "")
    skill_name = body.get("name", "")
    scope = body.get("scope", "user")
    project_dir = body.get("project_dir")

    if not content or not skill_name:
        raise HTTPException(status_code=400, detail="name and content are required")

    path = save_skill(
        skill_name, content, scope,
        Path(project_dir) if project_dir else None,
    )
    return {"status": "ok", "path": str(path)}


@router.delete("/api/skills/{name}")
async def remove_skill(
    name: str,
    scope: str = Query("user", description="Scope: user or project"),
    path: Optional[str] = Query(None, description="Project directory path"),
):
    """Delete a user or project skill."""
    from features.skills import delete_skill
    if scope == "managed":
        raise HTTPException(status_code=403, detail="Cannot delete managed skills")
    project_dir = Path(path) if path else None
    deleted = delete_skill(name, scope, project_dir)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found in {scope}")
    return {"status": "ok"}
