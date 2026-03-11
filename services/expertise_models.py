"""
Multi-Expertise Learning System (MELS) — Data Models
=====================================================

10 record types, hierarchical domains, shelf-life classifications,
causal chain linking, and confidence scoring.
"""

import hashlib
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional


# --- Record Types (10, up from Overstory's 6) ---

RECORD_TYPES = [
    "convention",    # How we do things (coding standards, naming)
    "pattern",       # Reusable solution approach
    "failure",       # Something that went wrong
    "decision",      # Architectural/design decision with rationale
    "reference",     # Key file/API/resource reference
    "guide",         # Step-by-step procedural knowledge
    "resolution",    # Fix for a specific failure (linked via resolves)
    "insight",       # Cross-cutting observation from multiple sessions
    "antipattern",   # What NOT to do (prescriptive avoidance)
    "heuristic",     # Rule of thumb with confidence bounds
]

# --- Classifications with shelf lives ---

CLASSIFICATIONS = ["foundational", "tactical", "observational"]

SHELF_LIFE_DAYS = {
    "foundational": None,  # permanent
    "tactical": 30,
    "observational": 14,
}


@dataclass
class ExpertiseRecord:
    """A single expertise record in the MELS system."""
    record_type: str                 # One of 10 RECORD_TYPES
    classification: str              # foundational | tactical | observational
    domain: str                      # Hierarchical: "python.fastapi", "typescript.react"
    content: str                     # Primary content (natural language)
    id: str = ""                     # "exp-<8 hex chars>" — auto-generated if empty
    structured: dict = field(default_factory=dict)  # Type-specific data

    # Temporal
    created_at: str = ""
    updated_at: str = ""
    expires_at: Optional[str] = None  # Computed from classification shelf life

    # Provenance
    source_project: str = ""
    source_session: str = ""
    source_agent: str = ""           # "worker-1", "orchestrator", etc.
    evidence: list = field(default_factory=list)  # [{type, ref}]

    # Causal chain
    resolves: Optional[str] = None   # ID of failure record this fixes
    resolved_by: list = field(default_factory=list)  # IDs of resolution records
    supersedes: list = field(default_factory=list)    # IDs of replaced records
    relates_to: list = field(default_factory=list)    # IDs of related records

    # Scoring
    confidence: float = 0.5          # 0.0-1.0 (neutral start)
    relevance_score: float = 1.0     # 0.0-1.0 (decays over time)
    outcome_count: int = 0
    success_count: int = 0
    failure_count: int = 0

    # Metadata
    content_hash: str = ""           # SHA-256 for dedup
    tags: list = field(default_factory=list)
    file_patterns: list = field(default_factory=list)  # Glob patterns
    is_archived: bool = False

    def __post_init__(self):
        if not self.id:
            self.id = f"exp-{uuid.uuid4().hex[:8]}"
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at
        if not self.content_hash and self.content:
            self.content_hash = hashlib.sha256(self.content.encode()).hexdigest()
        if not self.expires_at and self.classification in SHELF_LIFE_DAYS:
            days = SHELF_LIFE_DAYS.get(self.classification)
            if days is not None:
                created = datetime.fromisoformat(self.created_at.replace("Z", "+00:00"))
                self.expires_at = (created + timedelta(days=days)).isoformat()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ExpertiseRecord":
        known = cls.__dataclass_fields__
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class Outcome:
    """Tracks the outcome of applying an expertise record."""
    id: str = ""
    record_id: str = ""
    status: str = ""                 # success | failure | partial
    agent: str = ""
    session_id: str = ""
    project: str = ""
    notes: str = ""
    recorded_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = f"out-{uuid.uuid4().hex[:8]}"
        if not self.recorded_at:
            self.recorded_at = datetime.now(timezone.utc).isoformat()


@dataclass
class DomainConfig:
    """Governance limits for a domain."""
    name: str = ""                   # "python.fastapi"
    parent: Optional[str] = None     # "python"
    description: str = ""
    soft_limit: int = 100            # UI warning
    warn_limit: int = 150            # auto-compact suggested
    hard_limit: int = 200            # oldest observational pruned


@dataclass
class SessionLesson:
    """A lesson synthesized from errors within a single session."""
    id: str = ""
    session_id: str = ""
    content: str = ""
    severity: str = "medium"         # low | medium | high | critical
    domain: str = ""
    file_patterns: list = field(default_factory=list)
    source_error_ids: list = field(default_factory=list)
    quality_score: float = 0.0       # 0-1 (specificity + actionability)
    propagated_to: list = field(default_factory=list)  # Worker IDs
    created_at: str = ""
    promoted_to_record_id: Optional[str] = None

    def __post_init__(self):
        if not self.id:
            self.id = f"lsn-{uuid.uuid4().hex[:8]}"
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


# --- Hierarchical Domain Taxonomy ---

HIERARCHICAL_DOMAIN_MAP = {
    # Python ecosystem
    ".py": "python",
    "fastapi": "python.fastapi",
    "django": "python.django",
    "flask": "python.flask",
    "pytest": "python.testing",
    # TypeScript ecosystem
    ".ts": "typescript",
    ".tsx": "typescript.react",
    "next.config": "typescript.nextjs",
    "jest": "typescript.testing",
    "vitest": "typescript.testing",
    # JavaScript
    ".js": "javascript",
    ".jsx": "javascript.react",
    # Infrastructure
    "Dockerfile": "devops.docker",
    "docker-compose": "devops.docker",
    ".github/workflows": "devops.ci",
    ".yml": "devops",
    ".yaml": "devops",
    # Database
    ".sql": "database.sql",
    ".prisma": "database.orm",
    "migrations": "database.migrations",
    # Testing
    "test_": "testing.unit",
    ".test.": "testing.unit",
    ".spec.": "testing.unit",
    "e2e": "testing.e2e",
    # Architecture
    "api/": "architecture.api",
    "models/": "architecture.data",
    "routes/": "architecture.api",
    # Styling
    ".css": "styling",
    ".scss": "styling",
    # Rust / Go / Java
    ".rs": "rust",
    ".go": "golang",
    ".java": "java",
}


def infer_domain(file_path: str) -> str:
    """Infer hierarchical domain from file path.

    Checks filename/path components for sub-domain first, then extension.
    Returns most specific match.
    """
    if not file_path:
        return ""

    fp_lower = file_path.lower()
    best_domain = ""
    best_specificity = 0

    for pattern, domain in HIERARCHICAL_DOMAIN_MAP.items():
        if pattern.startswith("."):
            # Extension match
            if fp_lower.endswith(pattern):
                specificity = domain.count(".") + 1
                if specificity > best_specificity:
                    best_domain = domain
                    best_specificity = specificity
        else:
            # Path component match (case-insensitive)
            if pattern.lower() in fp_lower:
                specificity = domain.count(".") + 1
                if specificity > best_specificity:
                    best_domain = domain
                    best_specificity = specificity

    return best_domain


def domain_matches(query_domain: str, record_domain: str) -> bool:
    """Hierarchical match: 'python' matches 'python.fastapi'.

    Also matches exact and reverse (python.fastapi matches python).
    """
    if not query_domain or not record_domain:
        return False
    if query_domain == record_domain:
        return True
    # Parent matches child
    if record_domain.startswith(query_domain + "."):
        return True
    # Child matches parent
    if query_domain.startswith(record_domain + "."):
        return True
    return False
