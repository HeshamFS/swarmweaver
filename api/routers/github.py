"""GitHub integration endpoints."""

import asyncio
import re as _re
from pathlib import Path

from fastapi import APIRouter, Query

router = APIRouter()


@router.get("/api/github/status")
async def get_github_status(
    path: str = Query(..., description="Project directory path"),
):
    """Get GitHub CI status for current branch."""
    try:
        from features.github_integration import GitHubManager
        gh = GitHubManager(Path(path))
        if not gh.is_gh_available():
            return {"available": False, "message": "gh CLI not installed"}
        return {"available": True, **gh.get_ci_status()}
    except Exception as e:
        return {"available": False, "message": str(e)}


@router.post("/api/github/pr")
async def create_github_pr(
    path: str = Query(..., description="Project directory path"),
    title: str = Query("", description="PR title"),
    body: str = Query("", description="PR body"),
):
    """Manually create a GitHub PR."""
    try:
        from features.github_integration import GitHubManager
        gh = GitHubManager(Path(path))
        if not gh.is_gh_available():
            return {"status": "error", "message": "gh CLI not installed"}
        result = gh.create_pr(title or "SwarmWeaver changes", body or "")
        return {"status": "ok", **result}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/api/git/reset")
async def git_reset(req: dict):
    """Reset a project to a specific git commit (hard reset)."""
    import subprocess as _subprocess

    path = req.get("path", "")
    sha = req.get("sha", "")

    if not path or not sha:
        return {"status": "error", "error": "Missing 'path' or 'sha'"}

    # Validate SHA format: 7-40 hex characters
    if not _re.match(r"^[0-9a-fA-F]{7,40}$", sha):
        return {"status": "error", "error": "Invalid SHA format"}

    project_dir = Path(path)
    if not project_dir.is_dir():
        return {"status": "error", "error": "Project directory not found"}

    # Verify the SHA exists
    try:
        result = _subprocess.run(
            ["git", "rev-parse", "--verify", sha],
            capture_output=True, text=True, timeout=10,
            cwd=str(project_dir),
        )
        if result.returncode != 0:
            return {"status": "error", "error": f"SHA {sha[:8]} not found in git history"}
    except Exception as e:
        return {"status": "error", "error": f"Git verification failed: {e}"}

    # Perform hard reset
    try:
        result = _subprocess.run(
            ["git", "reset", "--hard", sha],
            capture_output=True, text=True, timeout=30,
            cwd=str(project_dir),
        )
        if result.returncode != 0:
            return {"status": "error", "error": f"Git reset failed: {result.stderr.strip()}"}
    except Exception as e:
        return {"status": "error", "error": f"Git reset failed: {e}"}

    return {"status": "ok", "sha": sha, "message": f"Reset to {sha[:8]}"}


@router.get("/api/github/connection")
async def get_github_connection():
    """Check GitHub CLI installation and auth status."""
    result = {"installed": False, "authenticated": False, "username": None}
    try:
        proc = await asyncio.wait_for(
            asyncio.create_subprocess_exec(
                "gh", "auth", "status",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            ),
            timeout=10,
        )
        stdout, stderr = await proc.communicate()
        output = (stdout or b"").decode() + (stderr or b"").decode()
        result["installed"] = True
        if proc.returncode == 0:
            result["authenticated"] = True
            match = _re.search(r"account\s+(\S+)", output)
            if match:
                result["username"] = match.group(1)
            else:
                match = _re.search(r"Logged in to .+ as (\S+)", output)
                if match:
                    result["username"] = match.group(1)
    except FileNotFoundError:
        result["installed"] = False
    except Exception:
        result["installed"] = True
    return result
