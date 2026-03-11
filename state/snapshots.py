"""
Shadow Git Snapshot System
============================

Separate git repository capturing full project state before/after each
agent turn, enabling surgical per-file revert and rich diffs.

The shadow repo lives at ~/.swarmweaver/snapshots/<project_hash>/ on the
Linux filesystem (ext4) for fast git operations, while GIT_WORK_TREE points
to the actual project directory (potentially NTFS on WSL2).
"""

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


@dataclass
class SnapshotRecord:
    """Metadata for a single snapshot."""
    hash: str                    # git tree SHA
    label: str                   # "pre:code:3", "post:implement:5"
    timestamp: str
    session_id: str
    phase: str
    iteration: int
    files_count: int
    worker_id: Optional[int] = None

    def to_dict(self) -> dict:
        return asdict(self)


# Mandatory gitignore entries for the shadow repo
_SHADOW_GITIGNORE = """\
# Shadow snapshot exclusions
.swarmweaver/
node_modules/
__pycache__/
.git/
venv/
.venv/
.env
.env.*
*.pyc
*.pyo
.next/
dist/
build/
*.egg-info/
.pytest_cache/
.mypy_cache/
.tox/
coverage/
.coverage
*.db
*.db-wal
*.db-shm
"""


class SnapshotManager:
    """
    Shadow git repository for project state snapshots.

    All git commands use GIT_DIR=<shadow_repo>/.git and
    GIT_WORK_TREE=<project_dir> to keep the shadow repo
    completely separate from the project's own git.
    """

    def __init__(self, project_dir: Path, enabled: bool = True):
        self.project_dir = Path(project_dir)
        self._enabled = enabled
        self._shadow_dir_path: Optional[Path] = None
        self._available: Optional[bool] = None
        self._index_path: Optional[Path] = None
        self._warned = False

    def _project_hash(self) -> str:
        """Deterministic hash of the absolute project path."""
        return hashlib.sha256(
            str(self.project_dir.resolve()).encode()
        ).hexdigest()[:12]

    def _shadow_dir(self) -> Path:
        """~/.swarmweaver/snapshots/<hash>/"""
        if self._shadow_dir_path is None:
            home = Path.home()
            self._shadow_dir_path = (
                home / ".swarmweaver" / "snapshots" / self._project_hash()
            )
        return self._shadow_dir_path

    def _git_env(self) -> dict:
        """Environment variables to redirect git to the shadow repo."""
        env = os.environ.copy()
        env["GIT_DIR"] = str(self._shadow_dir() / ".git")
        env["GIT_WORK_TREE"] = str(self.project_dir)
        return env

    def _run_git(self, *args: str, timeout: int = 60) -> tuple[bool, str]:
        """Run a git command in the shadow repo context."""
        try:
            result = subprocess.run(
                ["git"] + list(args),
                capture_output=True,
                text=True,
                timeout=timeout,
                env=self._git_env(),
                cwd=str(self.project_dir),
            )
            return result.returncode == 0, result.stdout.strip()
        except subprocess.TimeoutExpired:
            if not self._warned:
                print("[SnapshotManager] git command timed out", flush=True)
                self._warned = True
            return False, "timeout"
        except FileNotFoundError:
            return False, "git not found"
        except Exception as e:
            return False, str(e)

    def _init_shadow_repo(self) -> bool:
        """Initialize the shadow git repository."""
        shadow = self._shadow_dir()
        git_dir = shadow / ".git"

        # Check if existing repo is healthy
        if git_dir.exists():
            ok, _ = self._run_git("status", "--porcelain")
            if ok:
                return True
            # Corrupted — reinitialize
            try:
                shutil.rmtree(shadow)
            except Exception:
                return False

        try:
            shadow.mkdir(parents=True, exist_ok=True)
        except Exception:
            return False

        # Initialize bare-ish repo
        try:
            result = subprocess.run(
                ["git", "init"],
                capture_output=True, text=True, timeout=30,
                cwd=str(shadow),
            )
            if result.returncode != 0:
                return False
        except Exception:
            return False

        # Configure for WSL2/NTFS compatibility
        configs = {
            "core.autocrlf": "false",
            "core.longpaths": "true",
            "core.symlinks": "true",
            "core.fsmonitor": "false",
            "core.preloadindex": "true",
            "gc.auto": "0",
            "user.name": "SwarmWeaver Snapshots",
            "user.email": "snapshots@swarmweaver.local",
        }
        for key, value in configs.items():
            self._run_git("config", key, value)

        # Sync gitignore
        self._sync_gitignore()

        # Initial empty commit
        self._run_git("commit", "--allow-empty", "-m", "snapshot repo init")

        return True

    def _sync_gitignore(self) -> None:
        """Copy project .gitignore + add mandatory exclusions."""
        shadow = self._shadow_dir()
        gitignore_path = shadow / ".gitignore"

        parts = [_SHADOW_GITIGNORE]

        # Copy project gitignore if it exists
        project_gitignore = self.project_dir / ".gitignore"
        if project_gitignore.exists():
            try:
                content = project_gitignore.read_text(encoding="utf-8")
                parts.append(f"\n# From project .gitignore\n{content}")
            except Exception:
                pass

        try:
            gitignore_path.write_text("\n".join(parts), encoding="utf-8")
        except Exception:
            pass

    def is_available(self) -> bool:
        """Check if snapshots are available (git installed, repo initialized)."""
        if not self._enabled:
            return False
        if self._available is not None:
            return self._available

        # Check git is installed
        try:
            subprocess.run(
                ["git", "--version"],
                capture_output=True, timeout=10,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            self._available = False
            return False

        self._available = self._init_shadow_repo()
        return self._available

    def capture(
        self,
        label: str,
        session_id: str = "",
        phase: str = "",
        iteration: int = 0,
        worker_id: Optional[int] = None,
    ) -> Optional[str]:
        """
        Capture current project state as a git tree hash.

        Returns the tree hash, or None on failure.
        """
        if not self.is_available():
            return None

        try:
            # Stage all changes (respecting .gitignore)
            ok, _ = self._run_git("add", "-A")
            if not ok:
                return None

            # Write tree (captures the index as a tree object)
            ok, tree_hash = self._run_git("write-tree")
            if not ok or not tree_hash:
                return None

            # Create a ref for GC protection
            safe_label = label.replace("/", "-").replace(" ", "_")[:50]
            ref_name = f"refs/snapshots/{safe_label}"
            # Create a commit pointing to this tree
            ok, commit_hash = self._run_git(
                "commit-tree", tree_hash, "-m", f"snapshot: {label}"
            )
            if ok and commit_hash:
                self._run_git("update-ref", ref_name, commit_hash)

            # Count files in tree
            ok, ls_output = self._run_git("ls-tree", "-r", "--name-only", tree_hash)
            files_count = len(ls_output.split("\n")) if ok and ls_output else 0

            # Record in index
            record = SnapshotRecord(
                hash=tree_hash,
                label=label,
                timestamp=datetime.utcnow().isoformat() + "Z",
                session_id=session_id,
                phase=phase,
                iteration=iteration,
                files_count=files_count,
                worker_id=worker_id,
            )
            self._append_to_index(record)

            return tree_hash

        except Exception as e:
            if not self._warned:
                print(f"[SnapshotManager] capture failed: {e}", flush=True)
                self._warned = True
            return None

    def diff(self, from_hash: str, to_hash: Optional[str] = None) -> dict:
        """
        Diff between two tree hashes.

        Returns {summary: {files_changed, insertions, deletions},
                 files: [{path, status, additions, deletions, diff}]}
        """
        result = {
            "summary": {"files_changed": 0, "insertions": 0, "deletions": 0},
            "files": [],
        }

        if not self.is_available():
            return result

        to_arg = to_hash or "HEAD"

        # Get numstat
        ok, numstat = self._run_git("diff", "--numstat", from_hash, to_arg)
        if not ok:
            return result

        # Get name-status
        ok, name_status = self._run_git("diff", "--name-status", from_hash, to_arg)
        status_map = {}
        if ok and name_status:
            for line in name_status.split("\n"):
                if not line.strip():
                    continue
                parts = line.split("\t", 1)
                if len(parts) == 2:
                    status_map[parts[1]] = parts[0]

        total_add = 0
        total_del = 0
        files = []

        if numstat:
            for line in numstat.split("\n"):
                if not line.strip():
                    continue
                parts = line.split("\t")
                if len(parts) < 3:
                    continue
                added = int(parts[0]) if parts[0] != "-" else 0
                deleted = int(parts[1]) if parts[1] != "-" else 0
                file_path = parts[2]
                total_add += added
                total_del += deleted

                # Get per-file diff
                ok, file_diff = self._run_git(
                    "diff", "--unified=3", from_hash, to_arg, "--", file_path
                )

                git_status = status_map.get(file_path, "M")
                status_label = {
                    "A": "added", "D": "deleted", "M": "modified",
                }.get(git_status[0] if git_status else "M", "modified")

                files.append({
                    "path": file_path,
                    "status": status_label,
                    "additions": added,
                    "deletions": deleted,
                    "diff": file_diff if ok else "",
                })

        result["summary"]["files_changed"] = len(files)
        result["summary"]["insertions"] = total_add
        result["summary"]["deletions"] = total_del
        result["files"] = files

        return result

    def diff_file(self, from_hash: str, to_hash: str, file_path: str) -> str:
        """Return unified diff for a single file between two snapshots."""
        if not self.is_available():
            return ""
        ok, output = self._run_git(
            "diff", "--unified=5", from_hash, to_hash, "--", file_path
        )
        return output if ok else ""

    def changed_files(self, from_hash: str, to_hash: Optional[str] = None) -> list[str]:
        """Return list of changed file paths between two snapshots."""
        if not self.is_available():
            return []
        to_arg = to_hash or "HEAD"
        ok, output = self._run_git(
            "diff", "--name-only", from_hash, to_arg
        )
        if not ok or not output:
            return []
        return [f for f in output.split("\n") if f.strip()]

    def restore(self, tree_hash: str) -> bool:
        """Full restore of project to a snapshot state."""
        if not self.is_available():
            return False
        try:
            # Read the tree into the index
            ok, _ = self._run_git("read-tree", tree_hash)
            if not ok:
                return False

            # Checkout files from index to working directory
            ok, _ = self._run_git(
                "checkout-index", "-a", "--force",
                f"--prefix={str(self.project_dir)}/"
            )
            # Note: checkout-index with --prefix adds the prefix to paths,
            # but since GIT_WORK_TREE is set, we use it without prefix
            if not ok:
                # Try without prefix (GIT_WORK_TREE handles it)
                ok, _ = self._run_git("checkout-index", "-a", "--force")

            return ok
        except Exception as e:
            print(f"[SnapshotManager] restore failed: {e}", flush=True)
            return False

    def revert_files(self, tree_hash: str, files: list[str]) -> dict:
        """
        Revert specific files from a snapshot.

        Returns {reverted: [...], failed: [...]}.
        """
        result = {"reverted": [], "failed": []}
        if not self.is_available():
            return result

        # Read the tree into index first
        ok, _ = self._run_git("read-tree", tree_hash)
        if not ok:
            result["failed"] = files
            return result

        for file_path in files:
            try:
                ok, _ = self._run_git(
                    "checkout-index", "--force", "--", file_path
                )
                if ok:
                    result["reverted"].append(file_path)
                else:
                    result["failed"].append(file_path)
            except Exception:
                result["failed"].append(file_path)

        return result

    def list_snapshots(
        self, limit: int = 50, session_id: Optional[str] = None
    ) -> list[dict]:
        """List snapshot records from the index file."""
        records = self._read_index()

        if session_id:
            records = [r for r in records if r.get("session_id") == session_id]

        # Most recent first
        records.reverse()
        return records[:limit]

    def cleanup(self, max_age_days: int = 7) -> None:
        """Delete old snapshot refs and run git gc."""
        if not self.is_available():
            return

        cutoff = (datetime.utcnow() - timedelta(days=max_age_days)).isoformat() + "Z"

        # Read index, filter out old records
        records = self._read_index()
        kept = [r for r in records if r.get("timestamp", "") >= cutoff]
        removed = [r for r in records if r.get("timestamp", "") < cutoff]

        # Delete refs for removed records
        for record in removed:
            safe_label = record.get("label", "").replace("/", "-").replace(" ", "_")[:50]
            self._run_git("update-ref", "-d", f"refs/snapshots/{safe_label}")

        # Write filtered index
        self._write_index(kept)

        # Run git gc
        self._run_git("gc", "--prune=now", timeout=120)

    def get_status(self) -> dict:
        """Return snapshot system status info."""
        shadow = self._shadow_dir()
        available = self.is_available()

        status = {
            "available": available,
            "shadow_dir": str(shadow),
            "project_hash": self._project_hash(),
            "snapshot_count": 0,
            "repo_size_mb": 0.0,
        }

        if available:
            records = self._read_index()
            status["snapshot_count"] = len(records)

            # Calculate repo size
            try:
                total_size = sum(
                    f.stat().st_size
                    for f in shadow.rglob("*")
                    if f.is_file()
                )
                status["repo_size_mb"] = round(total_size / (1024 * 1024), 2)
            except Exception:
                pass

        return status

    # ------------------------------------------------------------------
    # Index management
    # ------------------------------------------------------------------

    def _index_file(self) -> Path:
        if self._index_path is None:
            self._index_path = self._shadow_dir() / "snapshot_index.json"
        return self._index_path

    def _read_index(self) -> list[dict]:
        idx_file = self._index_file()
        if not idx_file.exists():
            return []
        try:
            return json.loads(idx_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []

    def _write_index(self, records: list[dict]) -> None:
        try:
            self._index_file().write_text(
                json.dumps(records, indent=2), encoding="utf-8"
            )
        except Exception as e:
            print(f"[SnapshotManager] write index failed: {e}", flush=True)

    def _append_to_index(self, record: SnapshotRecord) -> None:
        records = self._read_index()
        records.append(record.to_dict())
        self._write_index(records)
