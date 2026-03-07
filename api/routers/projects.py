"""Project discovery, browsing, and settings endpoints."""

import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query

from core.paths import get_paths
from api.models import CloneRequest
from api.state import PROJECT_SCAN_DIRS

router = APIRouter()


def _read_project_info(entry: Path) -> dict | None:
    """Read project info from a directory. Returns None if no task files found."""
    info: dict = {
        "name": entry.name,
        "path": str(entry.resolve()),
        "has_tasks": False,
        "mode": None,
        "done": 0,
        "total": 0,
        "percentage": 0.0,
        "last_modified": None,
    }

    entry_paths = get_paths(entry)
    task_file = entry_paths.task_list
    if task_file.exists():
        try:
            data = json.loads(task_file.read_text(encoding="utf-8"))
            tasks = data.get("tasks", [])
            info["has_tasks"] = True
            info["mode"] = data.get("metadata", {}).get("mode")
            info["total"] = len(tasks)
            info["done"] = sum(1 for t in tasks if t.get("status") in ("done", "completed"))
            info["percentage"] = (
                round(info["done"] / info["total"] * 100, 1)
                if info["total"] > 0
                else 0.0
            )
            stat = task_file.stat()
            info["last_modified"] = datetime.fromtimestamp(
                stat.st_mtime
            ).isoformat()
        except (json.JSONDecodeError, OSError):
            pass
        return info

    return None


@router.get("/api/projects")
async def list_projects():
    """Discover projects across all configured scan directories."""
    projects: list[dict] = []
    seen_paths: set[str] = set()

    for scan_dir in PROJECT_SCAN_DIRS:
        root = Path(scan_dir)
        if not root.exists() or not root.is_dir():
            continue

        project_info = _read_project_info(root)
        if project_info and project_info["has_tasks"]:
            resolved = str(root.resolve())
            if resolved not in seen_paths:
                seen_paths.add(resolved)
                projects.append(project_info)

        try:
            for entry in sorted(root.iterdir()):
                if not entry.is_dir():
                    continue
                if entry.name.startswith(".") or entry.name in (
                    "node_modules", "__pycache__", ".git", "venv", ".venv",
                    "prompts", "frontend", "docs", "scripts",
                ):
                    continue
                resolved = str(entry.resolve())
                if resolved in seen_paths:
                    continue
                project_info = _read_project_info(entry)
                if project_info and project_info["has_tasks"]:
                    seen_paths.add(resolved)
                    projects.append(project_info)
        except PermissionError:
            continue

    projects.sort(
        key=lambda p: (p.get("last_modified") or "", p.get("name", "")),
        reverse=True,
    )

    return {"projects": projects}


@router.get("/api/project-status")
async def get_project_status(
    path: str = Query(..., description="Project directory path"),
):
    """Check if a project directory has existing tasks (for resume detection)."""
    project_dir = Path(path)

    if not project_dir.exists():
        return {"exists": False, "has_tasks": False, "resumable": False}

    paths = get_paths(project_dir)
    task_file = paths.task_list
    progress_file = paths.progress_notes

    # Load saved run config (swarm settings) if available
    run_config = None
    run_config_file = paths.run_config
    if run_config_file.exists():
        try:
            run_config = json.loads(run_config_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    result: dict = {
        "exists": True,
        "has_tasks": False,
        "resumable": False,
        "mode": None,
        "done": 0,
        "total": 0,
        "percentage": 0.0,
        "has_progress_notes": progress_file.exists(),
        "run_config": run_config,
    }

    if task_file.exists():
        try:
            data = json.loads(task_file.read_text(encoding="utf-8"))
            tasks = data.get("tasks", [])
            result["has_tasks"] = True
            result["mode"] = data.get("metadata", {}).get("mode")
            result["total"] = len(tasks)
            result["done"] = sum(1 for t in tasks if t.get("status") in ("done", "completed"))
            result["percentage"] = (
                round(result["done"] / result["total"] * 100, 1)
                if result["total"] > 0
                else 0.0
            )
            remaining = result["total"] - result["done"]
            result["resumable"] = remaining > 0
        except (json.JSONDecodeError, OSError):
            pass

    return result


@router.get("/api/project-files")
async def get_project_files(
    path: str = Query(..., description="Project directory path"),
    query: str = Query("", description="Filter query"),
    limit: int = Query(200, description="Max files to return"),
):
    """List source files in a project directory, recursively."""
    project_dir = Path(path)
    if not project_dir.exists():
        return {"files": []}

    profile = get_paths(project_dir).resolve_read("codebase_profile.json")
    if profile.exists():
        try:
            data = json.loads(profile.read_text(encoding="utf-8"))
            files = data.get("discovered_files")
            if files and isinstance(files, list) and len(files) > 0:
                if query:
                    files = [f for f in files if query.lower() in f.lower()]
                return {"files": files[:limit]}
        except (json.JSONDecodeError, OSError):
            pass

    excluded = {".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build", ".next", ".cache"}
    skip_ext = {".pyc", ".o", ".so", ".dll", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2", ".ttf", ".map"}
    files = []
    try:
        for root_dir, dirs, filenames in os.walk(project_dir):
            dirs[:] = [d for d in dirs if d not in excluded and not d.startswith(".")]
            for fname in filenames:
                if any(fname.endswith(ext) for ext in skip_ext):
                    continue
                try:
                    rel = str((Path(root_dir) / fname).relative_to(project_dir)).replace("\\", "/")
                    if not query or query.lower() in rel.lower():
                        files.append(rel)
                    if len(files) >= limit:
                        return {"files": files}
                except ValueError:
                    continue
    except PermissionError:
        pass
    return {"files": files}


@router.get("/api/browse")
async def browse_directory(
    path: str = Query("", description="Directory to browse (empty = home dir)"),
):
    """Browse the local filesystem for folder selection."""
    if not path:
        path = str(Path.home())

    target = Path(path).resolve()

    if not target.exists():
        return {"error": f"Path not found: {path}", "entries": [], "current": path}

    if not target.is_dir():
        target = target.parent

    entries = []

    parent = target.parent
    if parent != target:
        entries.append({"name": "..", "path": str(parent), "is_dir": True})

    try:
        for item in sorted(target.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if item.name.startswith(".") or item.name in (
                "node_modules", "__pycache__", ".git", "venv", ".venv",
            ):
                continue
            try:
                entries.append({
                    "name": item.name,
                    "path": str(item),
                    "is_dir": item.is_dir(),
                })
            except PermissionError:
                continue
    except PermissionError:
        return {"error": "Permission denied", "entries": [], "current": str(target)}

    return {"current": str(target), "entries": entries}


@router.post("/api/mkdir")
async def create_directory(body: dict):
    """Create a new directory inside a given parent path."""
    parent_path = body.get("parent", "")
    name = body.get("name", "").strip()

    if not parent_path or not name:
        return {"error": "Both 'parent' and 'name' are required."}

    if "/" in name or "\\" in name or name in (".", ".."):
        return {"error": "Invalid folder name."}

    target = Path(parent_path).resolve() / name

    if target.exists():
        return {"error": f"'{name}' already exists.", "path": str(target)}

    try:
        target.mkdir(parents=False, exist_ok=False)
    except PermissionError:
        return {"error": "Permission denied."}
    except OSError as e:
        return {"error": str(e)}

    return {"status": "ok", "path": str(target)}


@router.post("/api/clone")
async def clone_repository(req: CloneRequest):
    """Clone a git repository into a directory."""
    url = req.url.strip()
    if not url:
        return {"success": False, "error": "URL is required", "path": ""}

    match = re.search(r"/([^/]+?)(?:\.git)?$", url)
    repo_name = match.group(1) if match else "cloned-repo"

    parent_dir = Path(req.target_dir) if req.target_dir else Path("generations")
    target_path = (parent_dir / repo_name).resolve()

    if target_path.exists() and any(target_path.iterdir()):
        return {"success": False, "error": f"Folder already exists: {target_path}", "path": str(target_path)}

    parent_dir.resolve().mkdir(parents=True, exist_ok=True)

    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "clone", url, str(target_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

        if proc.returncode != 0:
            err_msg = stderr.decode().strip() if stderr else "git clone failed"
            return {"success": False, "error": err_msg, "path": str(target_path)}

        return {"success": True, "path": str(target_path), "error": None}
    except asyncio.TimeoutError:
        return {"success": False, "error": "Clone timed out after 120 seconds", "path": str(target_path)}
    except FileNotFoundError:
        return {"success": False, "error": "git is not installed or not in PATH", "path": ""}
