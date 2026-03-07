"""Project-scoped expertise storage - local knowledge base per project."""
import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class ExpertiseEntry:
    id: str
    content: str
    category: str  # "convention", "pattern", "failure", "decision", "reference"
    domain: str  # "python", "typescript", "testing", etc.
    tags: list[str] = field(default_factory=list)
    source_file: str = ""
    created_at: str = ""
    relevance_score: float = 1.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ExpertiseEntry":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class ProjectExpertise:
    """Project-local expertise store at <project>/.swarmweaver/expertise/."""

    EXPERTISE_DIR = ".swarmweaver/expertise"

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.expertise_dir = project_dir / self.EXPERTISE_DIR
        self.expertise_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self.expertise_dir / "index.json"

    def _load_index(self) -> list[ExpertiseEntry]:
        if not self._index_path.exists():
            return []
        data = json.loads(self._index_path.read_text())
        return [ExpertiseEntry.from_dict(e) for e in data]

    def _save_index(self, entries: list[ExpertiseEntry]) -> None:
        self._index_path.write_text(json.dumps([e.to_dict() for e in entries], indent=2))

    def add(self, content: str, category: str, domain: str,
            tags: list[str] | None = None, source_file: str = "") -> str:
        entries = self._load_index()
        entry_id = str(uuid.uuid4())[:8]
        entry = ExpertiseEntry(
            id=entry_id,
            content=content,
            category=category,
            domain=domain,
            tags=tags or [],
            source_file=source_file,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        entries.append(entry)
        self._save_index(entries)

        # Also save to domain-specific file
        domain_file = self.expertise_dir / f"{domain}.json"
        domain_entries = []
        if domain_file.exists():
            domain_entries = json.loads(domain_file.read_text())
        domain_entries.append(entry.to_dict())
        domain_file.write_text(json.dumps(domain_entries, indent=2))

        return entry_id

    def get_all(self) -> list[ExpertiseEntry]:
        return self._load_index()

    def get_by_domain(self, domain: str) -> list[ExpertiseEntry]:
        return [e for e in self._load_index() if e.domain == domain]

    def get_domains(self) -> list[str]:
        return list(set(e.domain for e in self._load_index() if e.domain))

    def search(self, query: str, limit: int = 10) -> list[ExpertiseEntry]:
        query_lower = query.lower()
        entries = self._load_index()
        scored = []
        for e in entries:
            score = 0
            if query_lower in e.content.lower():
                score += 2
            if query_lower in e.domain.lower():
                score += 1
            if any(query_lower in t.lower() for t in e.tags):
                score += 1
            score *= e.relevance_score
            if score > 0:
                scored.append((score, e))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:limit]]

    def get_for_file_scope(self, file_scope: list[str]) -> list[ExpertiseEntry]:
        """Get expertise relevant to a set of file paths."""
        from features.memory import FILE_DOMAIN_MAP
        domains = set()
        for f in file_scope:
            ext = Path(f).suffix
            name = Path(f).name
            domain = FILE_DOMAIN_MAP.get(ext, FILE_DOMAIN_MAP.get(name, ""))
            if domain:
                domains.add(domain)

        entries = self._load_index()
        return [e for e in entries if e.domain in domains]

    def delete(self, entry_id: str) -> bool:
        entries = self._load_index()
        new_entries = [e for e in entries if e.id != entry_id]
        if len(new_entries) == len(entries):
            return False
        self._save_index(new_entries)
        return True

    def to_context_string(self, entries: list[ExpertiseEntry] | None = None) -> str:
        """Format expertise entries for overlay injection."""
        entries = entries or self._load_index()
        if not entries:
            return "No project-specific expertise available."

        by_domain: dict[str, list[ExpertiseEntry]] = {}
        for e in entries:
            by_domain.setdefault(e.domain or "general", []).append(e)

        lines = ["Project expertise:"]
        for domain, domain_entries in sorted(by_domain.items()):
            lines.append(f"\n### {domain.title()}")
            for e in domain_entries[:5]:  # Max 5 per domain to avoid bloat
                lines.append(f"- [{e.category}] {e.content}")
        return "\n".join(lines)
