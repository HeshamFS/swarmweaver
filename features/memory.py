"""
Cross-Project Learning (Agent Memory)
=======================================

Persists patterns, mistakes, and solutions across projects.
Stores memories in ~/.swarmweaver/memory/memories.json.
Supports domain-scoped expertise for structured retrieval.

Domains map to file patterns and technology areas, enabling
file-path-based memory retrieval.
"""

import json
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Optional


MEMORY_DIR = Path.home() / ".swarmweaver" / "memory"
MEMORY_FILE = MEMORY_DIR / "memories.json"
DOMAINS_DIR = MEMORY_DIR / "domains"

# Maps file extensions and path patterns to expertise domains
FILE_DOMAIN_MAP: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".rs": "rust",
    ".go": "golang",
    ".java": "java",
    ".sql": "database",
    ".prisma": "database",
    ".css": "styling",
    ".scss": "styling",
    ".html": "frontend",
    ".vue": "frontend",
    ".svelte": "frontend",
    ".yml": "devops",
    ".yaml": "devops",
    "Dockerfile": "devops",
    "docker-compose": "devops",
    ".github": "devops",
    "test": "testing",
    "spec": "testing",
    "__tests__": "testing",
}

# Expertise types within a domain
EXPERTISE_TYPES = ["convention", "pattern", "failure", "decision", "reference"]


@dataclass
class MemoryEntry:
    """A single memory entry."""
    id: str
    category: str       # "pattern" | "mistake" | "solution" | "preference"
    content: str
    tags: list[str]
    project_source: str
    created_at: str
    relevance_score: float = 1.0
    domain: str = ""             # Expertise domain (e.g., "python", "testing", "architecture")
    expertise_type: str = ""     # Type within domain (convention, pattern, failure, decision, reference)
    outcome: str = ""            # "success", "failure", "partial", or "" (untracked)
    outcome_count: int = 0
    success_count: float = 0


class AgentMemory:
    """Manages cross-project learning memories with domain-scoped expertise."""

    def __init__(self):
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        DOMAINS_DIR.mkdir(parents=True, exist_ok=True)
        self.entries: list[MemoryEntry] = self._load()

    def _load(self) -> list[MemoryEntry]:
        """Load memories from disk (flat file + domain files)."""
        entries = []

        # Load flat memories
        if MEMORY_FILE.exists():
            try:
                data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
                for e in data:
                    entries.append(MemoryEntry(
                        id=e.get("id", str(uuid.uuid4())[:8]),
                        category=e.get("category", "pattern"),
                        content=e.get("content", ""),
                        tags=e.get("tags", []),
                        project_source=e.get("project_source", ""),
                        created_at=e.get("created_at", ""),
                        relevance_score=e.get("relevance_score", 1.0),
                        domain=e.get("domain", ""),
                        expertise_type=e.get("expertise_type", ""),
                        outcome=e.get("outcome", ""),
                        outcome_count=e.get("outcome_count", 0),
                        success_count=e.get("success_count", 0),
                    ))
            except (json.JSONDecodeError, OSError):
                pass

        # Load domain-specific memories
        if DOMAINS_DIR.exists():
            for domain_file in DOMAINS_DIR.glob("*.json"):
                domain_name = domain_file.stem
                try:
                    domain_data = json.loads(domain_file.read_text(encoding="utf-8"))
                    for e in domain_data:
                        # Avoid duplicates (check by id)
                        if any(x.id == e.get("id") for x in entries):
                            continue
                        entries.append(MemoryEntry(
                            id=e.get("id", str(uuid.uuid4())[:8]),
                            category=e.get("category", "pattern"),
                            content=e.get("content", ""),
                            tags=e.get("tags", []),
                            project_source=e.get("project_source", ""),
                            created_at=e.get("created_at", ""),
                            relevance_score=e.get("relevance_score", 1.0),
                            domain=e.get("domain", domain_name),
                            expertise_type=e.get("expertise_type", ""),
                            outcome=e.get("outcome", ""),
                            outcome_count=e.get("outcome_count", 0),
                            success_count=e.get("success_count", 0),
                        ))
                except (json.JSONDecodeError, OSError):
                    continue

        return entries

    def _save(self) -> None:
        """Save memories to disk (flat file + domain-scoped files)."""
        try:
            # Save flat memories (entries without domain)
            flat = [asdict(e) for e in self.entries if not e.domain]
            MEMORY_FILE.write_text(json.dumps(flat, indent=2), encoding="utf-8")

            # Save domain-scoped entries to domain files
            by_domain: dict[str, list[dict]] = {}
            for e in self.entries:
                if e.domain:
                    if e.domain not in by_domain:
                        by_domain[e.domain] = []
                    by_domain[e.domain].append(asdict(e))

            for domain, entries in by_domain.items():
                domain_file = DOMAINS_DIR / f"{domain}.json"
                domain_file.write_text(json.dumps(entries, indent=2), encoding="utf-8")

        except OSError:
            pass

    def add(
        self,
        category: str,
        content: str,
        tags: list[str],
        project_source: str = "",
        domain: str = "",
        expertise_type: str = "",
    ) -> str:
        """Add a new memory entry. Returns the memory ID."""
        mem_id = str(uuid.uuid4())[:8]
        entry = MemoryEntry(
            id=mem_id,
            category=category,
            content=content,
            tags=tags,
            project_source=project_source,
            created_at=datetime.now().isoformat(),
            domain=domain,
            expertise_type=expertise_type,
        )
        self.entries.append(entry)
        self._save()
        return mem_id

    def search(self, query: str, limit: int = 5) -> list[MemoryEntry]:
        """Search memories by keyword matching.

        Scores by: tag overlap + content word overlap.
        """
        query_words = set(query.lower().split())
        if not query_words:
            return self.entries[:limit]

        scored: list[tuple[float, MemoryEntry]] = []
        for entry in self.entries:
            score = 0.0
            # Tag matching (higher weight)
            entry_tags = set(t.lower() for t in entry.tags)
            tag_overlap = len(query_words & entry_tags)
            score += tag_overlap * 3.0

            # Content word matching
            content_words = set(entry.content.lower().split())
            word_overlap = len(query_words & content_words)
            score += word_overlap * 1.0

            # Category matching
            if entry.category.lower() in query.lower():
                score += 2.0

            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:limit]]

    def list_all(self, category: Optional[str] = None) -> list[MemoryEntry]:
        """List all memories, optionally filtered by category."""
        if category:
            return [e for e in self.entries if e.category == category]
        return list(self.entries)

    def remove(self, memory_id: str) -> bool:
        """Remove a memory entry by ID."""
        original_len = len(self.entries)
        self.entries = [e for e in self.entries if e.id != memory_id]
        if len(self.entries) < original_len:
            self._save()
            return True
        return False

    def record_outcome(self, memory_id: str, outcome: str) -> bool:
        """Record an outcome for a memory entry and adjust relevance_score.

        Args:
            memory_id: The memory entry ID
            outcome: One of "success", "failure", "partial"

        Returns:
            True if the memory was found and updated
        """
        for entry in self.entries:
            if entry.id == memory_id:
                entry.outcome_count += 1
                if outcome == "success":
                    entry.success_count += 1
                elif outcome == "partial":
                    entry.success_count += 0.5
                # Adjust relevance_score based on success rate
                if entry.outcome_count > 0:
                    success_rate = entry.success_count / entry.outcome_count
                    # Scale relevance: 0.5 (all failures) to 1.5 (all successes)
                    entry.relevance_score = 0.5 + success_rate
                entry.outcome = outcome  # Last recorded outcome
                self._save()
                return True
        return False

    def save_lesson(
        self,
        error_pattern: str,
        resolution: str,
        project_type: str = "",
        tags: list[str] | None = None,
        project_source: str = "",
    ) -> str:
        """Save a structured error→resolution lesson for cross-run learning."""
        if project_type:
            content = f"In {project_type} projects: {error_pattern} -> {resolution}"
        else:
            content = f"{error_pattern} -> {resolution}"

        # Deduplicate
        content_lower = content.lower()
        for existing in self.entries:
            if existing.content.lower() == content_lower:
                return existing.id

        return self.add(
            category="solution",
            content=content,
            tags=tags or ["lesson", "error-resolution"],
            project_source=project_source,
        )

    def get_by_id(self, memory_id: str) -> Optional[MemoryEntry]:
        """Get a specific memory entry by ID."""
        for entry in self.entries:
            if entry.id == memory_id:
                return entry
        return None

    def get_relevant_context(
        self,
        task_description: str,
        project_tech_stack: Optional[list[str]] = None,
    ) -> str:
        """Get relevant memories formatted for prompt injection.

        Args:
            task_description: The current task description
            project_tech_stack: Optional list of technologies used

        Returns:
            Formatted markdown of relevant memories, or empty string.
        """
        # Build search query from task + tech stack
        search_terms = task_description
        if project_tech_stack:
            search_terms += " " + " ".join(project_tech_stack)

        results = self.search(search_terms, limit=5)
        if not results:
            return ""

        lines = ["## Agent Memory (Cross-Project Learnings)\n"]
        for entry in results:
            category_icon = {
                "pattern": "P",
                "mistake": "!",
                "solution": "S",
                "preference": "*",
            }.get(entry.category, "?")

            lines.append(f"- [{category_icon}] {entry.content}")
            if entry.tags:
                lines.append(f"  Tags: {', '.join(entry.tags)}")

        return "\n".join(lines) + "\n"

    # --- Domain-Scoped Expertise ---

    def get_domains(self) -> list[str]:
        """Get all unique domains with stored expertise."""
        return sorted(set(e.domain for e in self.entries if e.domain))

    def get_by_domain(self, domain: str, limit: int = 20) -> list[MemoryEntry]:
        """Get all memories for a specific domain."""
        return [e for e in self.entries if e.domain == domain][:limit]

    def get_expertise_for_files(
        self,
        files: list[str],
        limit: int = 10,
    ) -> list[MemoryEntry]:
        """
        Get relevant expertise based on file paths.

        Maps file extensions and path patterns to domains, then
        retrieves memories for those domains.

        Args:
            files: List of file paths to match against
            limit: Max entries to return

        Returns:
            Relevant domain-scoped memories
        """
        # Determine relevant domains from file paths
        relevant_domains: set[str] = set()

        for filepath in files:
            filepath_lower = filepath.lower()

            # Check extension
            for ext_or_pattern, domain in FILE_DOMAIN_MAP.items():
                if filepath_lower.endswith(ext_or_pattern) or ext_or_pattern in filepath_lower:
                    relevant_domains.add(domain)

        if not relevant_domains:
            return []

        # Collect memories from relevant domains
        results: list[MemoryEntry] = []
        for entry in self.entries:
            if entry.domain in relevant_domains:
                results.append(entry)

        # Sort by relevance score
        results.sort(key=lambda e: e.relevance_score, reverse=True)
        return results[:limit]

    def get_expertise_context(self, files: list[str]) -> str:
        """
        Build a formatted expertise section for prompt injection.

        Args:
            files: List of files being worked on

        Returns:
            Markdown-formatted expertise section or empty string.
        """
        entries = self.get_expertise_for_files(files, limit=8)
        if not entries:
            return ""

        # Group by domain
        by_domain: dict[str, list[MemoryEntry]] = {}
        for e in entries:
            if e.domain not in by_domain:
                by_domain[e.domain] = []
            by_domain[e.domain].append(e)

        lines = ["## Loaded Expertise\n"]
        for domain, domain_entries in by_domain.items():
            lines.append(f"### {domain.title()}")
            for entry in domain_entries:
                type_label = f"[{entry.expertise_type}]" if entry.expertise_type else ""
                lines.append(f"- {type_label} {entry.content}")
            lines.append("")

        return "\n".join(lines)

    def infer_domains(self, files: list[str]) -> list[str]:
        """
        Map file paths to expertise domains using FILE_DOMAIN_MAP.

        Args:
            files: List of file paths to analyze

        Returns:
            Deduplicated list of inferred domain names
        """
        domains: set[str] = set()
        for filepath in files:
            filepath_lower = filepath.lower()
            for ext_or_pattern, domain in FILE_DOMAIN_MAP.items():
                if filepath_lower.endswith(ext_or_pattern) or ext_or_pattern in filepath_lower:
                    domains.add(domain)
        return sorted(domains)

    def get_priming_context(
        self,
        file_scope: list[str],
        domains: Optional[list[str]] = None,
    ) -> str:
        """
        Returns formatted expertise block for prompt injection.

        Combines file-based domain inference with explicit domain selection
        to build a comprehensive priming context.

        Args:
            file_scope: List of file paths the agent will work on
            domains: Optional explicit list of domains to include

        Returns:
            Markdown-formatted expertise block, or empty string if no matches
        """
        # Infer domains from files
        inferred = set(self.infer_domains(file_scope))

        # Merge with explicit domains
        if domains:
            inferred.update(domains)

        if not inferred:
            # Fallback to file-based expertise retrieval
            return self.get_expertise_context(file_scope)

        # Collect entries from all relevant domains
        entries: list[MemoryEntry] = []
        seen_ids: set[str] = set()
        for domain in inferred:
            for entry in self.get_by_domain(domain, limit=10):
                if entry.id not in seen_ids:
                    entries.append(entry)
                    seen_ids.add(entry.id)

        # Also get file-specific expertise
        for entry in self.get_expertise_for_files(file_scope, limit=10):
            if entry.id not in seen_ids:
                entries.append(entry)
                seen_ids.add(entry.id)

        if not entries:
            return ""

        # Sort by relevance score
        entries.sort(key=lambda e: e.relevance_score, reverse=True)
        entries = entries[:15]  # Cap at 15 entries

        # Group by domain
        by_domain: dict[str, list[MemoryEntry]] = {}
        for e in entries:
            d = e.domain or "general"
            if d not in by_domain:
                by_domain[d] = []
            by_domain[d].append(e)

        lines = ["## Primed Expertise\n"]
        for domain, domain_entries in sorted(by_domain.items()):
            lines.append(f"### {domain.title()}")
            for entry in domain_entries:
                type_label = f"[{entry.expertise_type}]" if entry.expertise_type else ""
                cat_label = f"({entry.category})" if entry.category else ""
                lines.append(f"- {type_label} {entry.content} {cat_label}".rstrip())
            lines.append("")

        return "\n".join(lines)

    def record_from_session(self, analysis: dict) -> int:
        """
        Auto-import insights from a session analysis dict as domain-scoped entries.

        Expected analysis format:
        {
            "insights": [
                {"content": "...", "category": "pattern|mistake|solution",
                 "domain": "python", "tags": ["..."]}
            ],
            "project_source": "my-project",
            "files_touched": ["src/main.py", ...]
        }

        Args:
            analysis: Dict containing insights and metadata

        Returns:
            Number of entries added
        """
        insights = analysis.get("insights", [])
        project_source = analysis.get("project_source", "")
        files_touched = analysis.get("files_touched", [])

        # Infer domains from touched files for entries without explicit domain
        inferred_domains = self.infer_domains(files_touched)
        default_domain = inferred_domains[0] if inferred_domains else ""

        count = 0
        for insight in insights:
            if not isinstance(insight, dict):
                continue

            content = insight.get("content", "")
            if not content or len(content) < 10:
                continue

            category = insight.get("category", "pattern")
            domain = insight.get("domain", default_domain)
            tags = insight.get("tags", [])
            expertise_type = insight.get("expertise_type", "")

            # Infer expertise_type from category if not provided
            if not expertise_type:
                expertise_type = {
                    "pattern": "pattern",
                    "mistake": "failure",
                    "solution": "reference",
                    "preference": "convention",
                }.get(category, "reference")

            # Check for duplicate content (skip if very similar entry exists)
            content_lower = content.lower()
            duplicate = False
            for existing in self.entries:
                if existing.domain == domain and existing.content.lower() == content_lower:
                    duplicate = True
                    break
            if duplicate:
                continue

            self.add(
                category=category,
                content=content,
                tags=tags if tags else ([domain] if domain else []),
                project_source=project_source,
                domain=domain,
                expertise_type=expertise_type,
            )
            count += 1

        return count

    def record_from_reflections(
        self,
        reflections_path: Path,
        project_source: str = "",
    ) -> int:
        """
        Auto-record learnings from session_reflections.json with domain tags.

        Reads reflections, infers domains from mentioned file paths,
        and stores them as domain-scoped memories.

        Args:
            reflections_path: Path to session_reflections.json
            project_source: Name of the source project

        Returns:
            Number of new memories recorded
        """
        if not reflections_path.exists():
            return 0

        try:
            data = json.loads(reflections_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return 0

        count = 0
        reflections = data if isinstance(data, list) else data.get("reflections", [])

        for reflection in reflections:
            if isinstance(reflection, str):
                content = reflection
                category = "pattern"
            elif isinstance(reflection, dict):
                content = reflection.get("content", reflection.get("reflection", ""))
                category = reflection.get("category", "pattern")
            else:
                continue

            if not content or len(content) < 10:
                continue

            # Infer domain from content keywords
            domain = ""
            content_lower = content.lower()
            for keyword, dom in [
                ("python", "python"), ("typescript", "typescript"),
                ("react", "frontend"), ("next.js", "frontend"),
                ("database", "database"), ("sql", "database"),
                ("test", "testing"), ("docker", "devops"),
                ("security", "security"), ("api", "architecture"),
                ("performance", "performance"),
            ]:
                if keyword in content_lower:
                    domain = dom
                    break

            self.add(
                category=category,
                content=content,
                tags=[domain] if domain else [],
                project_source=project_source,
                domain=domain,
                expertise_type="pattern" if category == "pattern" else "failure" if category == "mistake" else "reference",
            )
            count += 1

        return count
