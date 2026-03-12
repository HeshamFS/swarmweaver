"""
Shadow Git Snapshot System (Enhanced)
=====================================

Separate git repository capturing full project state before/after each
agent turn with proper commit chain, SQLite-backed index, and named
bookmarks for precision time-travel and full project restoration.

The shadow repo lives at ~/.swarmweaver/snapshots/<project_hash>/ on the
Linux filesystem (ext4) for fast git operations, while GIT_WORK_TREE points
to the actual project directory (potentially NTFS on WSL2).

Key features:
- SQLite index (atomic, concurrent-safe, queryable) replaces JSON file
- Proper git commit chain (linear history, parent links)
- Named bookmarks (git tags + SQLite) for precision restore points
- Preview before restore (see what would change)
- Commit + tree hash dual tracking
"""

import hashlib
import os
import shutil
import sqlite3
import subprocess
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


@dataclass
class SnapshotRecord:
    """Metadata for a single snapshot."""
    hash: str                    # git tree SHA (primary external ID)
    label: str                   # "pre:code:3", "post:implement:5"
    timestamp: str
    session_id: str
    phase: str
    iteration: int
    files_count: int
    worker_id: Optional[int] = None
    id: str = ""                 # UUID (internal primary key)
    commit_hash: str = ""        # git commit SHA (for history chain)

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

    Snapshots are stored as proper git commits in a linear chain
    with metadata indexed in SQLite for fast querying. Named
    bookmarks protect important snapshots from cleanup and enable
    precision time-travel.
    """

    def __init__(self, project_dir: Path, enabled: bool = True):
        self.project_dir = Path(project_dir)
        self._enabled = enabled
        self._shadow_dir_path: Optional[Path] = None
        self._available: Optional[bool] = None
        self._warned = False
        self._conn: Optional[sqlite3.Connection] = None

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

    def _db_path(self) -> Path:
        """SQLite database path in the shadow repo directory."""
        return self._shadow_dir() / "snapshots.db"

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

    # ------------------------------------------------------------------
    # SQLite index
    # ------------------------------------------------------------------

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create SQLite connection with WAL mode."""
        if self._conn is None:
            db = self._db_path()
            db.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(db), timeout=10)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=5000")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._ensure_tables()
        return self._conn

    def _ensure_tables(self) -> None:
        """Create SQLite tables if they don't exist."""
        conn = self._conn
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS snapshots (
                id TEXT PRIMARY KEY,
                commit_hash TEXT NOT NULL,
                tree_hash TEXT NOT NULL,
                label TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                session_id TEXT DEFAULT '',
                phase TEXT DEFAULT '',
                iteration INTEGER DEFAULT 0,
                files_count INTEGER DEFAULT 0,
                worker_id INTEGER DEFAULT NULL
            );

            CREATE TABLE IF NOT EXISTS bookmarks (
                name TEXT PRIMARY KEY,
                snapshot_id TEXT NOT NULL,
                commit_hash TEXT NOT NULL,
                tree_hash TEXT NOT NULL,
                description TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (snapshot_id) REFERENCES snapshots(id)
            );

            CREATE INDEX IF NOT EXISTS idx_snapshots_session
                ON snapshots(session_id);
            CREATE INDEX IF NOT EXISTS idx_snapshots_timestamp
                ON snapshots(timestamp);
            CREATE INDEX IF NOT EXISTS idx_snapshots_tree_hash
                ON snapshots(tree_hash);
            CREATE INDEX IF NOT EXISTS idx_snapshots_commit_hash
                ON snapshots(commit_hash);
        """)
        conn.commit()

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

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

        # Initialize repo
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

        # Initial empty commit (establishes branch for commit chain)
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

    # ------------------------------------------------------------------
    # Core capture
    # ------------------------------------------------------------------

    def capture(
        self,
        label: str,
        session_id: str = "",
        phase: str = "",
        iteration: int = 0,
        worker_id: Optional[int] = None,
    ) -> Optional[str]:
        """
        Capture current project state as a git commit.

        Creates a proper commit on the snapshot branch (if there are
        changes), records metadata in SQLite. Returns the tree hash
        (for backward compatibility), or None on failure.
        """
        if not self.is_available():
            return None

        try:
            # Stage all changes (respecting .gitignore)
            ok, _ = self._run_git("add", "-A")
            if not ok:
                return None

            # Check if there are staged changes vs HEAD
            has_changes_result, _ = self._run_git("diff", "--cached", "--quiet")
            has_changes = not has_changes_result  # exit 1 = has changes

            if has_changes:
                ok, _ = self._run_git("commit", "-m", f"snapshot: {label}")
                if not ok:
                    # Fallback: allow-empty
                    ok, _ = self._run_git(
                        "commit", "--allow-empty", "-m", f"snapshot: {label}"
                    )
                    if not ok:
                        return None

            # Get current commit and tree hashes
            ok, commit_hash = self._run_git("rev-parse", "HEAD")
            if not ok or not commit_hash:
                return None

            ok, tree_hash = self._run_git("rev-parse", "HEAD^{tree}")
            if not ok or not tree_hash:
                return None

            # Count files in tree
            ok, ls_output = self._run_git(
                "ls-tree", "-r", "--name-only", tree_hash
            )
            files_count = len(ls_output.split("\n")) if ok and ls_output else 0

            # Record in SQLite
            snap_id = str(uuid.uuid4())[:8]
            timestamp = datetime.utcnow().isoformat() + "Z"

            conn = self._get_connection()
            conn.execute(
                """INSERT INTO snapshots
                   (id, commit_hash, tree_hash, label, timestamp,
                    session_id, phase, iteration, files_count, worker_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    snap_id, commit_hash, tree_hash, label, timestamp,
                    session_id, phase, iteration, files_count, worker_id,
                ),
            )
            conn.commit()

            return tree_hash

        except Exception as e:
            if not self._warned:
                print(f"[SnapshotManager] capture failed: {e}", flush=True)
                self._warned = True
            return None

    # ------------------------------------------------------------------
    # Diff operations
    # ------------------------------------------------------------------

    def diff(self, from_hash: str, to_hash: Optional[str] = None) -> dict:
        """
        Diff between two tree/commit hashes.

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
        ok, name_status = self._run_git(
            "diff", "--name-status", from_hash, to_arg
        )
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

    def changed_files(
        self, from_hash: str, to_hash: Optional[str] = None
    ) -> list[str]:
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

    # ------------------------------------------------------------------
    # Restore operations
    # ------------------------------------------------------------------

    def restore(self, tree_hash: str) -> bool:
        """
        Full restore of project to a snapshot state.

        Uses git read-tree + checkout-index for reliable cross-platform
        restoration.
        """
        if not self.is_available():
            return False
        try:
            # Read the tree into the index
            ok, _ = self._run_git("read-tree", tree_hash)
            if not ok:
                return False

            # Checkout files from index to working directory
            ok, _ = self._run_git("checkout-index", "-a", "--force")
            if ok:
                return True

            # Fallback: try with commit hash
            commit = self._find_commit_for_tree(tree_hash)
            if commit:
                ok, _ = self._run_git("checkout", commit, "--", ".")
                return ok

            return False
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

    def preview_restore(self, tree_hash: str) -> dict:
        """
        Preview what would change if restoring to this snapshot.

        Shows the diff between current working state and the target
        snapshot — what files would be modified, added, or removed.
        """
        if not self.is_available():
            return {
                "summary": {"files_changed": 0, "insertions": 0, "deletions": 0},
                "files": [],
            }

        # Capture current state first (stage everything)
        ok, _ = self._run_git("add", "-A")
        if not ok:
            return {
                "summary": {"files_changed": 0, "insertions": 0, "deletions": 0},
                "files": [],
            }

        ok, current_tree = self._run_git("write-tree")
        if not ok:
            return {
                "summary": {"files_changed": 0, "insertions": 0, "deletions": 0},
                "files": [],
            }

        # Diff: target → current (shows what would change)
        return self.diff(current_tree, tree_hash)

    # ------------------------------------------------------------------
    # Bookmarks
    # ------------------------------------------------------------------

    def bookmark(
        self, tree_hash: str, name: str, description: str = ""
    ) -> bool:
        """
        Create a named bookmark for a snapshot.

        Stored as a git tag (for GC protection) and in SQLite for
        fast querying. Bookmarked snapshots are preserved during cleanup.
        """
        if not self.is_available():
            return False

        conn = self._get_connection()

        # Find the snapshot record
        row = conn.execute(
            "SELECT id, commit_hash FROM snapshots WHERE tree_hash = ? "
            "ORDER BY timestamp DESC LIMIT 1",
            (tree_hash,),
        ).fetchone()
        if not row:
            return False

        snap_id = row["id"]
        commit_hash = row["commit_hash"]

        # Create git tag for GC protection
        safe_name = name.replace(" ", "-").replace("/", "-")[:50]
        tag_name = f"bookmark/{safe_name}"
        ok, _ = self._run_git("tag", "-f", tag_name, commit_hash)
        if not ok:
            return False

        # Record in SQLite
        conn.execute(
            """INSERT OR REPLACE INTO bookmarks
               (name, snapshot_id, commit_hash, tree_hash, description, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                name, snap_id, commit_hash, tree_hash, description,
                datetime.utcnow().isoformat() + "Z",
            ),
        )
        conn.commit()
        return True

    def list_bookmarks(self) -> list[dict]:
        """List all bookmarks with snapshot metadata."""
        if not self.is_available():
            return []

        conn = self._get_connection()
        rows = conn.execute(
            """SELECT b.name, b.description, b.created_at,
                      b.commit_hash, b.tree_hash,
                      s.label, s.session_id, s.phase,
                      s.iteration, s.files_count,
                      s.timestamp as snap_timestamp
               FROM bookmarks b
               LEFT JOIN snapshots s ON s.id = b.snapshot_id
               ORDER BY b.created_at DESC"""
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_bookmark(self, name: str) -> bool:
        """Delete a bookmark (snapshot itself is preserved)."""
        if not self.is_available():
            return False

        conn = self._get_connection()

        # Delete git tag
        safe_name = name.replace(" ", "-").replace("/", "-")[:50]
        self._run_git("tag", "-d", f"bookmark/{safe_name}")

        # Delete from SQLite
        conn.execute("DELETE FROM bookmarks WHERE name = ?", (name,))
        conn.commit()
        return True

    def get_bookmark(self, name: str) -> Optional[dict]:
        """Get a single bookmark by name."""
        if not self.is_available():
            return None

        conn = self._get_connection()
        row = conn.execute(
            """SELECT b.name, b.description, b.created_at,
                      b.commit_hash, b.tree_hash,
                      s.label, s.session_id, s.phase,
                      s.iteration, s.files_count,
                      s.timestamp as snap_timestamp
               FROM bookmarks b
               LEFT JOIN snapshots s ON s.id = b.snapshot_id
               WHERE b.name = ?""",
            (name,),
        ).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_snapshot(self, tree_hash: str) -> Optional[dict]:
        """Get a single snapshot by tree hash."""
        if not self.is_available():
            return None

        conn = self._get_connection()
        row = conn.execute(
            "SELECT * FROM snapshots WHERE tree_hash = ? "
            "ORDER BY timestamp DESC LIMIT 1",
            (tree_hash,),
        ).fetchone()
        return dict(row) if row else None

    def list_snapshots(
        self, limit: int = 50, session_id: Optional[str] = None
    ) -> list[dict]:
        """List snapshot records from SQLite index."""
        if not self.is_available():
            return []

        conn = self._get_connection()
        if session_id:
            rows = conn.execute(
                """SELECT * FROM snapshots
                   WHERE session_id = ?
                   ORDER BY timestamp DESC LIMIT ?""",
                (session_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM snapshots ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()

        results = []
        for row in rows:
            d = dict(row)
            # Include "hash" key for backward compatibility
            d["hash"] = d["tree_hash"]
            results.append(d)

        return results

    def get_history(self, limit: int = 50) -> list[dict]:
        """
        Get the git commit history of the snapshot branch.

        Returns commits in reverse chronological order with
        snapshot metadata joined from SQLite.
        """
        if not self.is_available():
            return []

        ok, log_output = self._run_git(
            "log", f"--max-count={limit}", "--format=%H|%at|%s",
        )
        if not ok or not log_output:
            return []

        conn = self._get_connection()
        history = []
        for line in log_output.split("\n"):
            if not line.strip():
                continue
            parts = line.split("|", 2)
            if len(parts) < 3:
                continue

            commit_hash = parts[0]
            unix_ts = parts[1]
            subject = parts[2]

            # Look up snapshot metadata
            row = conn.execute(
                "SELECT * FROM snapshots WHERE commit_hash = ? LIMIT 1",
                (commit_hash,),
            ).fetchone()

            entry = {
                "commit_hash": commit_hash,
                "timestamp": (
                    datetime.utcfromtimestamp(int(unix_ts)).isoformat() + "Z"
                    if unix_ts.isdigit() else ""
                ),
                "message": subject,
            }
            if row:
                entry.update({
                    "tree_hash": row["tree_hash"],
                    "label": row["label"],
                    "session_id": row["session_id"],
                    "phase": row["phase"],
                    "iteration": row["iteration"],
                    "files_count": row["files_count"],
                })

            # Check if bookmarked
            bm = conn.execute(
                "SELECT name FROM bookmarks WHERE commit_hash = ?",
                (commit_hash,),
            ).fetchone()
            if bm:
                entry["bookmark"] = bm["name"]

            history.append(entry)

        return history

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup(self, max_age_days: int = 7) -> int:
        """Delete old snapshots (preserving bookmarked ones) and run git gc."""
        if not self.is_available():
            return 0

        cutoff = (
            datetime.utcnow() - timedelta(days=max_age_days)
        ).isoformat() + "Z"

        conn = self._get_connection()

        # Get bookmarked snapshot IDs — these are preserved
        bookmarked_ids = {
            r["snapshot_id"]
            for r in conn.execute("SELECT snapshot_id FROM bookmarks").fetchall()
        }

        rows = conn.execute(
            "SELECT id FROM snapshots WHERE timestamp < ?",
            (cutoff,),
        ).fetchall()

        removed = 0
        for row in rows:
            if row["id"] in bookmarked_ids:
                continue
            conn.execute("DELETE FROM snapshots WHERE id = ?", (row["id"],))
            removed += 1

        conn.commit()

        # Run git gc
        self._run_git("gc", "--prune=now", timeout=120)

        return removed

    def get_status(self) -> dict:
        """Return snapshot system status info."""
        shadow = self._shadow_dir()
        available = self.is_available()

        status = {
            "available": available,
            "shadow_dir": str(shadow),
            "project_hash": self._project_hash(),
            "snapshot_count": 0,
            "bookmark_count": 0,
            "repo_size_mb": 0.0,
        }

        if available:
            conn = self._get_connection()
            row = conn.execute("SELECT COUNT(*) as c FROM snapshots").fetchone()
            status["snapshot_count"] = row["c"]

            row = conn.execute("SELECT COUNT(*) as c FROM bookmarks").fetchone()
            status["bookmark_count"] = row["c"]

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

    def close(self) -> None:
        """Close the SQLite connection."""
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_commit_for_tree(self, tree_hash: str) -> Optional[str]:
        """Find the commit hash that produced a given tree hash."""
        conn = self._get_connection()
        row = conn.execute(
            "SELECT commit_hash FROM snapshots WHERE tree_hash = ? "
            "ORDER BY timestamp DESC LIMIT 1",
            (tree_hash,),
        ).fetchone()
        return row["commit_hash"] if row else None

