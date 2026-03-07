"""
GitHub Integration
===================

Auto-create branches, open PRs, and check CI status using the gh CLI.
All operations are optional — gracefully degrade if gh is not installed.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional


class GitHubManager:
    """Manages GitHub operations via the gh CLI."""

    def __init__(self, project_dir: Path):
        self.project_dir = Path(project_dir)

    def is_gh_available(self) -> bool:
        """Check if gh CLI is installed and authenticated."""
        if not shutil.which("gh"):
            return False
        try:
            result = subprocess.run(
                ["gh", "auth", "status"],
                cwd=str(self.project_dir),
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return False

    def create_branch(self, branch_name: str) -> bool:
        """Create and checkout a new git branch."""
        # Sanitize branch name
        safe_name = re.sub(r"[^a-zA-Z0-9/_-]", "-", branch_name)[:60]
        try:
            result = subprocess.run(
                ["git", "checkout", "-b", safe_name],
                cwd=str(self.project_dir),
                capture_output=True,
                text=True,
                timeout=15,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return False

    def push_branch(self) -> bool:
        """Push the current branch to origin."""
        try:
            # Get current branch
            branch_result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(self.project_dir),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if branch_result.returncode != 0:
                return False
            branch = branch_result.stdout.strip()

            # Push with upstream
            result = subprocess.run(
                ["git", "push", "-u", "origin", branch],
                cwd=str(self.project_dir),
                capture_output=True,
                text=True,
                timeout=60,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return False

    def create_pr(
        self,
        title: str,
        body: str,
        base: str = "main",
    ) -> dict:
        """Create a pull request using gh CLI.

        Returns dict with 'url' and 'number' keys.
        """
        try:
            result = subprocess.run(
                [
                    "gh", "pr", "create",
                    "--title", title,
                    "--body", body,
                    "--base", base,
                ],
                cwd=str(self.project_dir),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                url = result.stdout.strip()
                # Extract PR number from URL
                number_match = re.search(r"/pull/(\d+)", url)
                number = int(number_match.group(1)) if number_match else 0
                return {"url": url, "number": number, "success": True}
            return {"url": "", "number": 0, "success": False, "error": result.stderr.strip()}
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            return {"url": "", "number": 0, "success": False, "error": str(e)}

    def get_ci_status(self, branch: Optional[str] = None) -> dict:
        """Get CI/checks status for a branch."""
        cmd = ["gh", "pr", "checks"]
        if branch:
            cmd += ["--branch", branch]

        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.project_dir),
                capture_output=True,
                text=True,
                timeout=15,
            )

            checks: list[dict] = []
            if result.returncode == 0 and result.stdout.strip():
                for line in result.stdout.strip().splitlines():
                    parts = line.split("\t")
                    if len(parts) >= 3:
                        checks.append({
                            "name": parts[0].strip(),
                            "status": parts[1].strip(),
                            "url": parts[-1].strip() if len(parts) > 3 else "",
                        })

            # Overall state
            states = [c["status"].lower() for c in checks]
            if all(s == "pass" for s in states):
                overall = "success"
            elif any(s == "fail" for s in states):
                overall = "failure"
            elif any(s == "pending" for s in states):
                overall = "pending"
            else:
                overall = "unknown"

            return {"state": overall, "checks": checks}
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return {"state": "unknown", "checks": []}

    def add_pr_comment(self, pr_number: int, body: str) -> bool:
        """Add a comment to a PR."""
        try:
            result = subprocess.run(
                ["gh", "pr", "comment", str(pr_number), "--body", body],
                cwd=str(self.project_dir),
                capture_output=True,
                text=True,
                timeout=15,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return False

    def get_pr_diff(self, pr_number: int) -> str:
        """Get the diff for a PR."""
        try:
            result = subprocess.run(
                ["gh", "pr", "diff", str(pr_number)],
                cwd=str(self.project_dir),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        return ""
