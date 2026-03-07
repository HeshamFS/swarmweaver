"""
Spec Workflow Manager
======================

Manages specification documents for tasks. Specs are stored as markdown
files under .swarmweaver/specs/<task_id>.md, providing a structured way
to define requirements before implementation begins.

Supports write, read, and list operations with metadata tracking.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional


class SpecManager:
    """Manages task specification documents."""

    SPECS_DIR = ".swarmweaver/specs"

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.specs_dir = project_dir / self.SPECS_DIR

    def write_spec(self, task_id: str, content: str, author: str = "") -> Path:
        """
        Write a spec for a task. Returns path to spec file.

        Creates the spec file and an accompanying metadata sidecar (.meta.json)
        tracking authorship and timestamps.

        Args:
            task_id: Task identifier (e.g., "TASK-001")
            content: Markdown spec content
            author: Author name (e.g., worker name or "user")

        Returns:
            Path to the written spec file
        """
        self.specs_dir.mkdir(parents=True, exist_ok=True)

        spec_file = self.specs_dir / f"{task_id}.md"
        meta_file = self.specs_dir / f"{task_id}.meta.json"

        now = datetime.now().isoformat()

        # Write spec content
        spec_file.write_text(content, encoding="utf-8")

        # Write or update metadata sidecar
        meta: dict = {}
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass

        meta.update({
            "task_id": task_id,
            "author": author or meta.get("author", ""),
            "created_at": meta.get("created_at", now),
            "updated_at": now,
            "size": len(content),
            "revisions": meta.get("revisions", 0) + 1,
        })
        meta_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")

        return spec_file

    def read_spec(self, task_id: str) -> Optional[str]:
        """
        Read spec content. Returns None if not found.

        Args:
            task_id: Task identifier

        Returns:
            Spec content as string, or None if no spec exists
        """
        spec_file = self.specs_dir / f"{task_id}.md"
        if not spec_file.exists():
            return None
        try:
            return spec_file.read_text(encoding="utf-8")
        except OSError:
            return None

    def list_specs(self) -> list[dict]:
        """
        List all specs with metadata.

        Returns:
            List of dicts with keys: task_id, author, created_at, updated_at, size, revisions
        """
        if not self.specs_dir.exists():
            return []

        results: list[dict] = []
        for spec_file in sorted(self.specs_dir.glob("*.md")):
            task_id = spec_file.stem
            meta_file = self.specs_dir / f"{task_id}.meta.json"

            entry: dict = {
                "task_id": task_id,
                "author": "",
                "created_at": "",
                "updated_at": "",
                "size": 0,
                "revisions": 0,
            }

            # Try to read metadata sidecar
            if meta_file.exists():
                try:
                    meta = json.loads(meta_file.read_text(encoding="utf-8"))
                    entry.update({
                        "author": meta.get("author", ""),
                        "created_at": meta.get("created_at", ""),
                        "updated_at": meta.get("updated_at", ""),
                        "size": meta.get("size", 0),
                        "revisions": meta.get("revisions", 0),
                    })
                except (json.JSONDecodeError, OSError):
                    pass

            # Fallback: get size from file directly
            if entry["size"] == 0:
                try:
                    entry["size"] = spec_file.stat().st_size
                except OSError:
                    pass

            results.append(entry)

        return results
