"""
Session Replay & Time Travel
===============================

Scrubs through git commit history to reconstruct task state and
code diffs at each point in time. Enables "time travel" through
the agent's work to understand what changed and when.
"""

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class CommitSnapshot:
    """A single commit in the project history."""
    sha: str
    message: str
    timestamp: str
    author: str = ""
    files_changed: int = 0
    insertions: int = 0
    deletions: int = 0

    def to_dict(self) -> dict:
        return {
            "sha": self.sha,
            "message": self.message,
            "timestamp": self.timestamp,
            "author": self.author,
            "files_changed": self.files_changed,
            "insertions": self.insertions,
            "deletions": self.deletions,
        }


class SessionReplayManager:
    """
    Manages session replay by reading git history and
    reconstructing task state at each commit.
    """

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir

    def _run_git(self, *args: str, timeout: int = 30) -> Optional[str]:
        """Run a git command in the project directory."""
        try:
            result = subprocess.run(
                ["git", *args],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(self.project_dir),
            )
            if result.returncode == 0:
                return result.stdout
            return None
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None

    def get_commit_history(self, limit: int = 50) -> list[CommitSnapshot]:
        """Get commit history with file change stats."""
        output = self._run_git(
            "log",
            f"--max-count={limit}",
            "--pretty=format:%H|%s|%aI|%an",
            "--shortstat",
        )

        if not output:
            return []

        commits = []
        lines = output.strip().split("\n")
        i = 0

        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue

            parts = line.split("|", 3)
            if len(parts) >= 3 and len(parts[0]) == 40:
                commit = CommitSnapshot(
                    sha=parts[0],
                    message=parts[1] if len(parts) > 1 else "",
                    timestamp=parts[2] if len(parts) > 2 else "",
                    author=parts[3] if len(parts) > 3 else "",
                )

                # Check next line for stat info
                i += 1
                if i < len(lines):
                    stat_line = lines[i].strip()
                    if stat_line and "file" in stat_line:
                        import re
                        files_m = re.search(r"(\d+)\s+file", stat_line)
                        ins_m = re.search(r"(\d+)\s+insertion", stat_line)
                        del_m = re.search(r"(\d+)\s+deletion", stat_line)
                        commit.files_changed = int(files_m.group(1)) if files_m else 0
                        commit.insertions = int(ins_m.group(1)) if ins_m else 0
                        commit.deletions = int(del_m.group(1)) if del_m else 0
                        i += 1
                    # Otherwise the next line is another commit, don't advance

                commits.append(commit)
            else:
                i += 1

        return commits

    def get_task_state_at_commit(self, sha: str) -> Optional[dict]:
        """Get the task_list.json content at a specific commit."""
        # Try .swarmweaver/ path first, then root for old commits
        output = self._run_git("show", f"{sha}:.swarmweaver/task_list.json")
        if not output:
            output = self._run_git("show", f"{sha}:task_list.json")
        if output:
            try:
                return json.loads(output)
            except json.JSONDecodeError:
                return None

        return None

    def get_diff_at_commit(self, sha: str) -> Optional[str]:
        """Get the diff stat for a specific commit."""
        return self._run_git("diff", f"{sha}~1..{sha}", "--stat")

    def get_full_timeline(self, limit: int = 50) -> list[dict]:
        """Get commits with task state populated."""
        commits = self.get_commit_history(limit)
        timeline = []

        for commit in commits:
            entry = commit.to_dict()
            # Only populate task state for commits that likely modified tasks
            if any(kw in commit.message.lower() for kw in [
                "task", "feature", "test", "pass", "fail", "implement",
                "fix", "complete", "mark", "feat:", "fix:", "refactor:",
            ]):
                task_state = self.get_task_state_at_commit(commit.sha)
                if task_state:
                    tasks = task_state.get("tasks", [])
                    done = sum(
                        1 for t in tasks
                        if (isinstance(t, dict) and t.get("status") in ("done", "completed"))
                        or (isinstance(t, dict) and t.get("passes", False))
                    )
                    entry["task_summary"] = {
                        "total": len(tasks),
                        "done": done,
                    }
            timeline.append(entry)

        return timeline

    def get_audit_timeline(self) -> list[dict]:
        """Parse audit.log JSONL for tool execution history."""
        from core.paths import get_paths
        audit_path = get_paths(self.project_dir).resolve_read("audit.log")
        if not audit_path.exists():
            return []

        entries = []
        try:
            for line in audit_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    entries.append(entry)
                except json.JSONDecodeError:
                    continue
        except OSError:
            pass

        # Return most recent 500 entries
        return entries[-500:]
