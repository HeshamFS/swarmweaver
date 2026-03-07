"""
Project Template System
========================

Pre-built project specifications for common project types.
Each template contains metadata and a spec file that can be used
with greenfield mode to scaffold new projects.
"""

from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional


TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


@dataclass
class ProjectTemplate:
    id: str                     # e.g., "nextjs-saas"
    name: str                   # e.g., "Next.js SaaS Starter"
    description: str            # Short description
    category: str               # "web", "api", "cli", "fullstack"
    tags: list[str] = field(default_factory=list)
    spec_filename: str = ""     # filename under templates/
    difficulty: str = "intermediate"  # beginner | intermediate | advanced
    estimated_tasks: int = 0

    @property
    def spec_path(self) -> Path:
        return TEMPLATES_DIR / self.spec_filename

    def load_spec(self) -> str:
        """Load the spec content from disk."""
        if self.spec_path.exists():
            return self.spec_path.read_text(encoding="utf-8")
        return ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["spec_available"] = self.spec_path.exists()
        return d


# ---------------------------------------------------------------------------
# Template registry
# ---------------------------------------------------------------------------

TEMPLATE_REGISTRY: dict[str, ProjectTemplate] = {}


def register_template(template: ProjectTemplate) -> None:
    TEMPLATE_REGISTRY[template.id] = template


def get_template(template_id: str) -> Optional[ProjectTemplate]:
    return TEMPLATE_REGISTRY.get(template_id)


def list_templates(category: Optional[str] = None) -> list[ProjectTemplate]:
    templates = list(TEMPLATE_REGISTRY.values())
    if category:
        templates = [t for t in templates if t.category == category]
    return sorted(templates, key=lambda t: t.name)


# ---------------------------------------------------------------------------
# Built-in templates
# ---------------------------------------------------------------------------

_BUILTINS = [
    ProjectTemplate(
        id="nextjs-saas",
        name="Next.js SaaS Starter",
        description="Full-stack SaaS with authentication, billing integration, dashboard, and a polished landing page",
        category="web",
        tags=["nextjs", "react", "tailwind", "auth", "stripe"],
        spec_filename="nextjs_saas.txt",
        difficulty="advanced",
        estimated_tasks=50,
    ),
    ProjectTemplate(
        id="fastapi-crud",
        name="FastAPI REST API",
        description="Production REST API with SQLAlchemy models, JWT auth, CRUD endpoints, and OpenAPI docs",
        category="api",
        tags=["python", "fastapi", "sqlalchemy", "postgresql", "jwt"],
        spec_filename="fastapi_crud.txt",
        difficulty="intermediate",
        estimated_tasks=30,
    ),
    ProjectTemplate(
        id="react-dashboard",
        name="React Admin Dashboard",
        description="Data visualization dashboard with charts, tables, filters, and responsive sidebar navigation",
        category="web",
        tags=["react", "tailwind", "charts", "recharts", "tables"],
        spec_filename="react_dashboard.txt",
        difficulty="intermediate",
        estimated_tasks=40,
    ),
    ProjectTemplate(
        id="cli-tool",
        name="Python CLI Tool",
        description="Feature-rich CLI with subcommands, config file support, rich terminal output, and packaging",
        category="cli",
        tags=["python", "click", "rich", "toml"],
        spec_filename="cli_tool.txt",
        difficulty="beginner",
        estimated_tasks=20,
    ),
    ProjectTemplate(
        id="fullstack-todo",
        name="Full-Stack Todo App",
        description="Classic CRUD app with Next.js frontend, FastAPI backend, SQLite database, and real-time updates",
        category="fullstack",
        tags=["nextjs", "fastapi", "sqlite", "websocket", "crud"],
        spec_filename="fullstack_todo.txt",
        difficulty="beginner",
        estimated_tasks=25,
    ),
]

for _t in _BUILTINS:
    register_template(_t)
