"""
Git Worktree Utilities
========================

Standalone module for creating, managing, and merging git worktrees.
Used to isolate agent changes so users can review and merge/discard.

Extracted and adapted from core/swarm.py's worktree management.
"""

import subprocess
import shutil
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

from core.merge_resolver import MergeResolver, ResolutionTier
from core.paths import get_paths


BRANCH_PREFIX = "swarmweaver"


@dataclass
class WorktreeInfo:
    """Information about a created worktree."""
    run_id: str
    worktree_path: str
    branch_name: str
    original_branch: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class WorktreeStatus:
    """Status of a worktree relative to the original branch."""
    exists: bool
    run_id: str
    branch: str
    files_changed: int
    insertions: int
    deletions: int
    diff_stat: str  # compact stat output

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MergeResult:
    """Result of merging a worktree branch."""
    success: bool
    files_changed: int
    merge_output: str
    error: Optional[str] = None
    resolution_tier: int = 1  # Which tier resolved the conflict (1-4, 0=failed)
    resolution_tier_name: str = "clean"

    def to_dict(self) -> dict:
        return asdict(self)


def _run_git(*args: str, cwd: Optional[Path] = None) -> tuple[bool, str]:
    """
    Run a git command. Returns (success, output).

    Pattern reused from core/swarm.py.
    """
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(cwd) if cwd else None,
        )
        return result.returncode == 0, result.stdout + result.stderr
    except Exception as e:
        return False, str(e)


def _get_current_branch(project_dir: Path) -> str:
    """Get the current branch name."""
    ok, output = _run_git("rev-parse", "--abbrev-ref", "HEAD", cwd=project_dir)
    if ok:
        return output.strip()
    return "main"


def _ensure_git_repo(project_dir: Path) -> bool:
    """Ensure the project directory is a git repo. Initialize if needed."""
    ok, _ = _run_git("rev-parse", "--git-dir", cwd=project_dir)
    if ok:
        return True

    # Initialize git repo
    ok, _ = _run_git("init", cwd=project_dir)
    if not ok:
        return False

    _run_git("add", "-A", cwd=project_dir)
    _run_git("commit", "-m", "Initial commit (auto-created for worktree)", cwd=project_dir)
    return True


def _ensure_clean_state(project_dir: Path) -> tuple[bool, str]:
    """
    Ensure the working directory is clean enough for worktree operations.
    Commits any uncommitted changes if needed.
    """
    ok, status_output = _run_git("status", "--porcelain", cwd=project_dir)
    if not ok:
        return False, f"Failed to check git status: {status_output}"

    if status_output.strip():
        # There are uncommitted changes — auto-commit them
        _run_git("add", "-A", cwd=project_dir)
        ok, output = _run_git(
            "commit", "-m", "Auto-commit before worktree creation",
            cwd=project_dir,
        )
        if not ok and "nothing to commit" not in output.lower():
            return False, f"Failed to commit: {output}"

    return True, ""


def create_worktree(project_dir: Path, run_id: str) -> WorktreeInfo:
    """
    Create a git worktree for an isolated agent run.

    Creates:
      <project_dir>/.worktrees/<run_id>/
      Branch: swarmweaver/<run_id>

    Args:
        project_dir: The original project directory
        run_id: Unique identifier for this run

    Returns:
        WorktreeInfo with paths and branch info

    Raises:
        RuntimeError: If worktree creation fails
    """
    # Ensure git repo exists
    if not _ensure_git_repo(project_dir):
        raise RuntimeError(f"Failed to initialize git repo in {project_dir}")

    # Ensure clean state
    ok, err = _ensure_clean_state(project_dir)
    if not ok:
        raise RuntimeError(f"Failed to prepare git state: {err}")

    # Get current branch before creating worktree
    original_branch = _get_current_branch(project_dir)

    branch_name = f"{BRANCH_PREFIX}/{run_id}"
    worktrees_dir = get_paths(project_dir).worktrees_dir
    worktree_path = worktrees_dir / run_id

    # Ensure .swarmweaver is gitignored
    gitignore = project_dir / ".gitignore"
    gitignore_content = ""
    if gitignore.exists():
        gitignore_content = gitignore.read_text(encoding="utf-8")
    if ".swarmweaver/" not in gitignore_content and ".swarmweaver\n" not in gitignore_content:
        with open(gitignore, "a", encoding="utf-8") as f:
            if gitignore_content and not gitignore_content.endswith("\n"):
                f.write("\n")
            f.write(".swarmweaver/\n")

    # Remove existing worktree if present (stale from previous run)
    if worktree_path.exists():
        _run_git("worktree", "remove", "--force", str(worktree_path), cwd=project_dir)
        if worktree_path.exists():
            shutil.rmtree(worktree_path, ignore_errors=True)

    # Delete branch if exists (stale)
    _run_git("branch", "-D", branch_name, cwd=project_dir)

    # Create worktrees directory
    worktrees_dir.mkdir(parents=True, exist_ok=True)

    # Create the worktree with a new branch from HEAD
    ok, output = _run_git(
        "worktree", "add", "-b", branch_name, str(worktree_path),
        cwd=project_dir,
    )

    if not ok:
        raise RuntimeError(f"Failed to create worktree: {output}")

    return WorktreeInfo(
        run_id=run_id,
        worktree_path=str(worktree_path),
        branch_name=branch_name,
        original_branch=original_branch,
    )


def merge_worktree(project_dir: Path, run_id: str, max_tier: int = 4) -> MergeResult:
    """
    Merge a worktree branch back into the original branch using
    4-tier conflict resolution.

    Args:
        project_dir: The original project directory
        run_id: The run_id used when creating the worktree
        max_tier: Maximum resolution tier (1=clean only, 2=+auto, 3=+AI, 4=+reimagine)

    Returns:
        MergeResult with success status and resolution tier details
    """
    branch_name = f"{BRANCH_PREFIX}/{run_id}"
    worktree_path = get_paths(project_dir).worktrees_dir / run_id

    # Get diff stats before merge
    files_changed = 0
    ok, stat_output = _run_git(
        "diff", "--stat", f"HEAD...{branch_name}",
        cwd=project_dir,
    )
    if ok and stat_output.strip():
        lines = stat_output.strip().splitlines()
        if lines:
            for line in lines:
                if "file" in line and "changed" in line:
                    try:
                        files_changed = int(line.strip().split()[0])
                    except (ValueError, IndexError):
                        files_changed = max(0, len(lines) - 1)

    # Use the 4-tier merge resolver
    resolver = MergeResolver(project_dir, max_tier=max_tier)
    resolution = resolver.resolve(
        branch=branch_name,
        commit_message=f"Merge swarmweaver run {run_id}",
    )

    if not resolution.success:
        return MergeResult(
            success=False,
            files_changed=0,
            merge_output=resolution.details,
            error=resolution.error,
            resolution_tier=resolution.tier.value,
            resolution_tier_name=resolution.tier.name.lower(),
        )

    # Clean up worktree and branch
    if worktree_path.exists():
        _run_git("worktree", "remove", "--force", str(worktree_path), cwd=project_dir)
    _run_git("branch", "-D", branch_name, cwd=project_dir)

    # Clean up worktrees dir if empty
    worktrees_dir = get_paths(project_dir).worktrees_dir
    if worktrees_dir.exists() and not any(worktrees_dir.iterdir()):
        shutil.rmtree(worktrees_dir, ignore_errors=True)

    return MergeResult(
        success=True,
        files_changed=files_changed,
        merge_output=resolution.details,
        resolution_tier=resolution.tier.value,
        resolution_tier_name=resolution.tier.name.lower(),
    )


def discard_worktree(project_dir: Path, run_id: str) -> bool:
    """
    Discard a worktree and its branch entirely.

    Args:
        project_dir: The original project directory
        run_id: The run_id used when creating the worktree

    Returns:
        True if successfully discarded
    """
    branch_name = f"{BRANCH_PREFIX}/{run_id}"
    worktrees_dir = get_paths(project_dir).worktrees_dir
    worktree_path = worktrees_dir / run_id

    # Remove worktree
    if worktree_path.exists():
        ok, _ = _run_git("worktree", "remove", "--force", str(worktree_path), cwd=project_dir)
        # If git worktree remove fails, force-remove the directory
        if not ok and worktree_path.exists():
            shutil.rmtree(worktree_path, ignore_errors=True)

    # Delete branch
    _run_git("branch", "-D", branch_name, cwd=project_dir)

    # Clean up worktrees dir if empty
    if worktrees_dir.exists() and not any(worktrees_dir.iterdir()):
        shutil.rmtree(worktrees_dir, ignore_errors=True)

    return True


def get_worktree_status(project_dir: Path, run_id: str) -> WorktreeStatus:
    """
    Get the status of a worktree relative to the original branch.

    Args:
        project_dir: The original project directory
        run_id: The run_id used when creating the worktree

    Returns:
        WorktreeStatus with diff statistics
    """
    branch_name = f"{BRANCH_PREFIX}/{run_id}"
    worktree_path = get_paths(project_dir).worktrees_dir / run_id

    exists = worktree_path.exists()

    if not exists:
        return WorktreeStatus(
            exists=False,
            run_id=run_id,
            branch=branch_name,
            files_changed=0,
            insertions=0,
            deletions=0,
            diff_stat="",
        )

    # Get diff stat
    ok, stat_output = _run_git(
        "diff", "--stat", f"HEAD...{branch_name}",
        cwd=project_dir,
    )

    files_changed = 0
    insertions = 0
    deletions = 0
    diff_stat = ""

    if ok and stat_output.strip():
        diff_stat = stat_output.strip()
        # Parse the summary line: "N files changed, X insertions(+), Y deletions(-)"
        lines = stat_output.strip().splitlines()
        for line in lines:
            if "file" in line and "changed" in line:
                parts = line.strip().split(",")
                for part in parts:
                    part = part.strip()
                    if "file" in part and "changed" in part:
                        try:
                            files_changed = int(part.split()[0])
                        except (ValueError, IndexError):
                            pass
                    elif "insertion" in part:
                        try:
                            insertions = int(part.split()[0])
                        except (ValueError, IndexError):
                            pass
                    elif "deletion" in part:
                        try:
                            deletions = int(part.split()[0])
                        except (ValueError, IndexError):
                            pass

    return WorktreeStatus(
        exists=True,
        run_id=run_id,
        branch=branch_name,
        files_changed=files_changed,
        insertions=insertions,
        deletions=deletions,
        diff_stat=diff_stat,
    )


def get_worktree_diff(project_dir: Path, run_id: str) -> str:
    """
    Get the full diff between the worktree branch and the original branch.

    Args:
        project_dir: The original project directory
        run_id: The run_id used when creating the worktree

    Returns:
        Full diff output as a string
    """
    branch_name = f"{BRANCH_PREFIX}/{run_id}"

    ok, diff_output = _run_git(
        "diff", f"HEAD...{branch_name}",
        cwd=project_dir,
    )

    if ok:
        return diff_output
    return f"Failed to get diff: {diff_output}"


def list_worktrees(project_dir: Path) -> list[WorktreeStatus]:
    """
    List all swarmweaver worktrees for a project.

    Returns:
        List of WorktreeStatus for each worktree
    """
    worktrees_dir = get_paths(project_dir).worktrees_dir
    if not worktrees_dir.exists():
        return []

    results = []
    for entry in worktrees_dir.iterdir():
        if entry.is_dir():
            run_id = entry.name
            status = get_worktree_status(project_dir, run_id)
            results.append(status)

    return results
