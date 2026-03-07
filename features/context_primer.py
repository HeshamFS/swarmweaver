"""
Smart Context Priming
======================

Pre-loads relevant file snippets into the agent's prompt based on
the next task's metadata, codebase profile, and recent activity.

Uses three signals:
1. task.files_affected → read first 100 lines of each
2. codebase_profile.json → map task category to relevant directories
3. audit.log → find "hot" files from recent tool_result events

Respects a token budget (~4 chars per token) to avoid prompt bloat.
"""

import json
from pathlib import Path
from typing import Optional

from core.paths import get_paths


# Category → likely directory patterns
CATEGORY_DIR_HINTS: dict[str, list[str]] = {
    "feature": ["src", "lib", "app", "components"],
    "test": ["tests", "test", "__tests__", "spec"],
    "fix": ["src", "lib", "app"],
    "refactor": ["src", "lib"],
    "style": ["styles", "css", "scss", "src"],
    "docs": ["docs", "README.md"],
    "infra": ["docker", "ci", ".github", "scripts"],
    "migration": ["src", "lib", "migrations", "db"],
    "performance": ["src", "lib", "app"],
    "security": ["src", "lib", "auth", "middleware"],
}


class ContextPrimer:
    """Builds a context section for prompt injection."""

    def __init__(self, project_dir: Path, max_tokens: int = 10000):
        self.project_dir = Path(project_dir)
        self.max_chars = max_tokens * 4  # ~4 chars per token
        self.profile = self._load_profile()

    def build_context_section(self, next_task: Optional[dict] = None) -> str:
        """Build a context section from multiple signals.

        Args:
            next_task: Dict with task fields (files_affected, category, title, etc.)

        Returns:
            Markdown-formatted context section or empty string.
        """
        if not next_task:
            return ""

        sections: list[str] = []
        chars_used = 0

        # Signal 1: Files from task.files_affected
        files_affected = next_task.get("files_affected", [])
        if files_affected:
            for filepath in files_affected[:5]:  # Max 5 files
                content = self._read_file_head(filepath, max_lines=80)
                if content:
                    snippet = f"### {filepath}\n```\n{content}\n```\n"
                    if chars_used + len(snippet) < self.max_chars:
                        sections.append(snippet)
                        chars_used += len(snippet)

        # Signal 2: Relevant files from codebase profile based on category
        category = next_task.get("category", "")
        if category and chars_used < self.max_chars * 0.7:
            profile_files = self._get_profile_files(category)
            for filepath in profile_files[:3]:
                if filepath in [f for f in files_affected]:
                    continue  # Skip duplicates
                content = self._read_file_head(filepath, max_lines=40)
                if content:
                    snippet = f"### {filepath} (related)\n```\n{content}\n```\n"
                    if chars_used + len(snippet) < self.max_chars:
                        sections.append(snippet)
                        chars_used += len(snippet)

        # Signal 3: Hot files from audit.log
        if chars_used < self.max_chars * 0.8:
            hot_files = self._get_hot_files()
            for filepath in hot_files[:3]:
                already_included = any(filepath in s for s in sections)
                if already_included:
                    continue
                content = self._read_file_head(filepath, max_lines=30)
                if content:
                    snippet = f"### {filepath} (recently active)\n```\n{content}\n```\n"
                    if chars_used + len(snippet) < self.max_chars:
                        sections.append(snippet)
                        chars_used += len(snippet)

        # Signal 4: Domain-scoped expertise from memory
        if chars_used < self.max_chars * 0.9:
            expertise = self._get_expertise_context(files_affected)
            if expertise:
                if chars_used + len(expertise) < self.max_chars:
                    sections.append(expertise)
                    chars_used += len(expertise)

        if not sections:
            return ""

        return "## Relevant Context\n\n" + "\n".join(sections)

    def _read_file_head(self, filepath: str, max_lines: int = 100) -> str:
        """Read the first N lines of a file in the project directory."""
        full_path = self.project_dir / filepath
        if not full_path.exists() or not full_path.is_file():
            return ""
        try:
            lines = full_path.read_text(encoding="utf-8", errors="replace").splitlines()
            return "\n".join(lines[:max_lines])
        except (OSError, UnicodeDecodeError):
            return ""

    def _load_profile(self) -> dict:
        """Load codebase_profile.json if it exists."""
        profile_path = get_paths(self.project_dir).resolve_read("codebase_profile.json")
        if profile_path.exists():
            try:
                return json.loads(profile_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _get_profile_files(self, category: str) -> list[str]:
        """Get relevant files from codebase profile based on task category."""
        files: list[str] = []
        dir_hints = CATEGORY_DIR_HINTS.get(category, ["src", "lib"])

        # Look at profile's file_tree or discovered_files
        file_tree = self.profile.get("file_tree", {})
        discovered = self.profile.get("discovered_files", [])

        # From discovered files, filter by dir hints
        for f in discovered:
            filepath = f if isinstance(f, str) else f.get("path", "")
            for hint in dir_hints:
                if hint in filepath:
                    files.append(filepath)
                    break

        # From file tree keys
        for key in file_tree:
            for hint in dir_hints:
                if hint in key:
                    tree_files = file_tree[key]
                    if isinstance(tree_files, list):
                        files.extend(tree_files[:2])
                    break

        return files[:5]

    def _get_expertise_context(self, files: list[str]) -> str:
        """Get domain-scoped expertise based on files being worked on."""
        if not files:
            return ""
        try:
            from features.memory import AgentMemory
            mem = AgentMemory()
            return mem.get_expertise_context(files)
        except Exception:
            return ""

    def _get_hot_files(self) -> list[str]:
        """Find recently active files from audit.log."""
        audit_path = get_paths(self.project_dir).resolve_read("audit.log")
        if not audit_path.exists():
            return []

        file_counts: dict[str, int] = {}
        try:
            lines = audit_path.read_text(encoding="utf-8", errors="replace").splitlines()
            # Only look at recent entries (last 100 lines)
            for line in lines[-100:]:
                try:
                    entry = json.loads(line)
                    # Look for file paths in tool inputs
                    tool_input = entry.get("input", {})
                    if isinstance(tool_input, dict):
                        for key in ("file_path", "path", "filename"):
                            fpath = tool_input.get(key, "")
                            if fpath and isinstance(fpath, str):
                                # Make relative to project dir
                                try:
                                    rel = str(Path(fpath).relative_to(self.project_dir))
                                    file_counts[rel] = file_counts.get(rel, 0) + 1
                                except ValueError:
                                    file_counts[fpath] = file_counts.get(fpath, 0) + 1
                except (json.JSONDecodeError, TypeError):
                    continue
        except OSError:
            return []

        # Sort by frequency
        sorted_files = sorted(file_counts.items(), key=lambda x: x[1], reverse=True)
        return [f for f, _ in sorted_files[:5]]
