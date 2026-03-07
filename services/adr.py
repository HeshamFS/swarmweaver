"""
Architecture Decision Records (ADR) System
=============================================

Auto-generates and manages ADR files during analyze/plan phases.
Each ADR documents a significant architectural decision with context,
alternatives considered, and consequences.

ADR files are stored in docs/adr/ with sequential numbering.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class ADR:
    """A single Architecture Decision Record."""
    number: int
    title: str
    status: str = "accepted"  # proposed | accepted | deprecated | superseded
    context: str = ""
    decision: str = ""
    consequences: str = ""
    alternatives: list[str] = field(default_factory=list)
    date: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))

    @property
    def slug(self) -> str:
        """Generate URL-friendly slug from title."""
        s = self.title.lower().strip()
        s = re.sub(r"[^a-z0-9\s-]", "", s)
        s = re.sub(r"[\s-]+", "-", s)
        return s[:60].rstrip("-")

    @property
    def filename(self) -> str:
        return f"{self.number:04d}-{self.slug}.md"

    def to_markdown(self) -> str:
        """Render ADR as standard markdown format."""
        lines = [
            f"# {self.number}. {self.title}",
            "",
            f"**Date:** {self.date}",
            f"**Status:** {self.status}",
            "",
            "## Context",
            "",
            self.context,
            "",
            "## Decision",
            "",
            self.decision,
            "",
        ]

        if self.alternatives:
            lines.extend([
                "## Alternatives Considered",
                "",
            ])
            for alt in self.alternatives:
                lines.append(f"- {alt}")
            lines.append("")

        lines.extend([
            "## Consequences",
            "",
            self.consequences,
            "",
        ])

        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "number": self.number,
            "title": self.title,
            "status": self.status,
            "context": self.context,
            "decision": self.decision,
            "consequences": self.consequences,
            "alternatives": self.alternatives,
            "date": self.date,
            "filename": self.filename,
        }


class ADRManager:
    """
    Manages Architecture Decision Records for a project.

    ADR files are stored in docs/adr/ with sequential numbering
    (0001-slug.md, 0002-slug.md, etc.).
    """

    ADR_DIR = "docs/adr"

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.adr_dir = project_dir / self.ADR_DIR

    def _ensure_dir(self) -> None:
        """Create ADR directory if it doesn't exist."""
        self.adr_dir.mkdir(parents=True, exist_ok=True)

    def get_next_number(self) -> int:
        """Get the next sequential ADR number."""
        if not self.adr_dir.exists():
            return 1

        numbers = []
        for f in self.adr_dir.glob("*.md"):
            m = re.match(r"(\d{4})-", f.name)
            if m:
                numbers.append(int(m.group(1)))

        return max(numbers, default=0) + 1

    def write_adr(self, adr: ADR) -> Path:
        """Write an ADR to disk and return the file path."""
        self._ensure_dir()
        path = self.adr_dir / adr.filename
        path.write_text(adr.to_markdown(), encoding="utf-8")
        return path

    def list_adrs(self) -> list[dict]:
        """List all ADRs with metadata parsed from files."""
        if not self.adr_dir.exists():
            return []

        adrs = []
        for f in sorted(self.adr_dir.glob("*.md")):
            try:
                metadata = self._parse_adr_metadata(f)
                if metadata:
                    adrs.append(metadata)
            except OSError:
                continue

        return adrs

    def read_adr(self, filename: str) -> Optional[str]:
        """Read the full content of an ADR file."""
        path = self.adr_dir / filename
        if path.exists():
            return path.read_text(encoding="utf-8")
        return None

    def _parse_adr_metadata(self, path: Path) -> Optional[dict]:
        """Parse ADR metadata from a markdown file."""
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            return None

        # Parse number from filename
        m = re.match(r"(\d{4})-", path.name)
        number = int(m.group(1)) if m else 0

        # Parse title from first heading
        title_match = re.search(r"^#\s+\d+\.\s*(.+)$", content, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else path.stem

        # Parse status
        status_match = re.search(r"\*\*Status:\*\*\s*(\w+)", content)
        status = status_match.group(1).lower() if status_match else "accepted"

        # Parse date
        date_match = re.search(r"\*\*Date:\*\*\s*([\d-]+)", content)
        date = date_match.group(1) if date_match else ""

        return {
            "number": number,
            "title": title,
            "status": status,
            "date": date,
            "filename": path.name,
        }
