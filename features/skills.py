"""
Skill System
=============

Markdown-based skills with YAML frontmatter. Discovers skills from:
1. Managed (bundled): swarmweaver/skills/
2. User: ~/.swarmweaver/skills/
3. Project: .swarmweaver/skills/

Deduplication: first-wins by resolved path. Priority: managed > user > project.
"""

import re
import yaml
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


@dataclass
class SkillDefinition:
    """A skill parsed from a SKILL.md file with YAML frontmatter."""
    name: str
    description: str = ""
    when_to_use: str = ""
    allowed_tools: list[str] = field(default_factory=list)
    model: str = ""                     # "" = use session default
    context: str = "inline"             # "inline" | "fork"
    paths: list[str] = field(default_factory=list)  # conditional activation globs
    arguments: list[str] = field(default_factory=list)
    source_path: str = ""               # resolved absolute path
    source_dir: str = ""                # "managed" | "user" | "project"
    body: str = ""                      # markdown content after frontmatter
    enabled: bool = True
    user_invocable: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


# Paths
MANAGED_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"
USER_SKILLS_DIR = Path.home() / ".swarmweaver" / "skills"


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    """Extract YAML frontmatter and body from markdown content."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", content, re.DOTALL)
    if not match:
        return {}, content
    try:
        fm = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        fm = {}
    return fm, match.group(2)


def _parse_skill_file(path: Path, source_dir: str) -> Optional[SkillDefinition]:
    """Parse a SKILL.md file into a SkillDefinition."""
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return None

    fm, body = _parse_frontmatter(content)
    if not isinstance(fm, dict):
        fm = {}

    name = fm.get("name", path.parent.name)
    description = fm.get("description", "")
    if not description:
        # Extract first paragraph as description
        for line in body.split("\n"):
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                description = stripped[:200]
                break

    # Parse allowed-tools (string CSV or list)
    allowed_tools = fm.get("allowed-tools", [])
    if isinstance(allowed_tools, str):
        allowed_tools = [t.strip() for t in allowed_tools.split(",") if t.strip()]

    # Parse paths (conditional activation)
    paths_val = fm.get("paths", [])
    if isinstance(paths_val, str):
        paths_val = [p.strip() for p in paths_val.split(",") if p.strip()]

    # Parse arguments
    arguments = fm.get("arguments", [])
    if isinstance(arguments, str):
        arguments = [a.strip() for a in arguments.split(",") if a.strip()]

    return SkillDefinition(
        name=name,
        description=description,
        when_to_use=fm.get("when_to_use", fm.get("when-to-use", "")),
        allowed_tools=allowed_tools,
        model=fm.get("model", ""),
        context=fm.get("context", "inline"),
        paths=paths_val,
        arguments=arguments,
        source_path=str(path.resolve()),
        source_dir=source_dir,
        body=body.strip(),
        enabled=True,
        user_invocable=str(fm.get("user-invocable", "true")).lower() in ("true", "1", "yes"),
    )


def _scan_skills_dir(directory: Path, source_dir: str) -> list[SkillDefinition]:
    """Scan a directory for SKILL.md files in subdirectories."""
    skills = []
    if not directory.is_dir():
        return skills
    for subdir in sorted(directory.iterdir()):
        if not subdir.is_dir():
            continue
        skill_file = subdir / "SKILL.md"
        if skill_file.is_file():
            skill = _parse_skill_file(skill_file, source_dir)
            if skill:
                skills.append(skill)
    return skills


def discover_skills(project_dir: Optional[Path] = None) -> list[SkillDefinition]:
    """Discover skills from all directories. Priority: managed > user > project.
    Deduplicate by name (first wins).
    """
    seen_names: set[str] = set()
    all_skills: list[SkillDefinition] = []

    for directory, source in [
        (MANAGED_SKILLS_DIR, "managed"),
        (USER_SKILLS_DIR, "user"),
    ]:
        for skill in _scan_skills_dir(directory, source):
            if skill.name not in seen_names:
                seen_names.add(skill.name)
                all_skills.append(skill)

    # Project-level skills
    if project_dir:
        proj_skills_dir = Path(project_dir) / ".swarmweaver" / "skills"
        for skill in _scan_skills_dir(proj_skills_dir, "project"):
            if skill.name not in seen_names:
                seen_names.add(skill.name)
                all_skills.append(skill)

    return all_skills


def get_skill_by_name(name: str, project_dir: Optional[Path] = None) -> Optional[SkillDefinition]:
    """Find a specific skill by name."""
    for skill in discover_skills(project_dir):
        if skill.name == name:
            return skill
    return None


def substitute_variables(text: str, args: dict[str, str], context: dict) -> str:
    """Replace skill variables in text.

    Variables: ${arg1}, ${arg2}, ..., ${SWARMWEAVER_SKILL_DIR}, ${SWARMWEAVER_SESSION_ID}
    """
    result = text
    # Positional args
    for i, (key, value) in enumerate(args.items(), 1):
        result = result.replace(f"${{{key}}}", value)
        result = result.replace(f"${{arg{i}}}", value)

    # Context variables
    result = result.replace("${SWARMWEAVER_SKILL_DIR}", context.get("skill_dir", ""))
    result = result.replace("${SWARMWEAVER_SESSION_ID}", context.get("session_id", ""))
    result = result.replace("${SWARMWEAVER_PROJECT_DIR}", context.get("project_dir", ""))
    result = result.replace("${SWARMWEAVER_MODE}", context.get("mode", ""))

    return result


def expand_skill_inline(skill: SkillDefinition, args: dict[str, str], context: dict) -> str:
    """Expand a skill for inline injection into the agent prompt."""
    ctx = {
        "skill_dir": str(Path(skill.source_path).parent),
        **context,
    }
    return substitute_variables(skill.body, args, ctx)


def save_skill(name: str, content: str, scope: str = "user",
               project_dir: Optional[Path] = None) -> Path:
    """Save a skill to the appropriate directory."""
    if scope == "project" and project_dir:
        base = Path(project_dir) / ".swarmweaver" / "skills"
    else:
        base = USER_SKILLS_DIR

    skill_dir = base / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(content, encoding="utf-8")
    return skill_file


def delete_skill(name: str, scope: str = "user",
                 project_dir: Optional[Path] = None) -> bool:
    """Delete a skill. Cannot delete managed skills."""
    if scope == "managed":
        return False

    if scope == "project" and project_dir:
        skill_dir = Path(project_dir) / ".swarmweaver" / "skills" / name
    else:
        skill_dir = USER_SKILLS_DIR / name

    if skill_dir.is_dir():
        import shutil
        shutil.rmtree(skill_dir, ignore_errors=True)
        return True
    return False
