"""
File-Based Memory System
==========================

Human-readable markdown memory files alongside MELS.

Directories:
  Global:  ~/.swarmweaver/CLAUDE.md, ~/.swarmweaver/memory/
  Project: .swarmweaver/CLAUDE.md, .swarmweaver/memory/

CLAUDE.md: Always-loaded instructions (like .env but for agent behavior)
MEMORY.md: Lightweight index of topic files (200 lines, 25KB max)
Topic files: Individual memory files with YAML frontmatter
"""

import re
import os
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

# Limits (matching source CLI)
MAX_ENTRYPOINT_LINES = 200
MAX_ENTRYPOINT_BYTES = 25_000
MAX_MEMORY_FILES = 200


@dataclass
class MemoryFile:
    """A parsed memory topic file."""
    path: str
    name: str
    description: str
    memory_type: str          # "user" | "feedback" | "project" | "reference"
    content: str
    mtime: float = 0.0
    age_days: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ClaudeMdFile:
    """A discovered CLAUDE.md or rules file."""
    path: str
    scope: str                # "global" | "project" | "local"
    content: str
    is_rules: bool = False


# ── Path helpers ──

def global_dir() -> Path:
    """~/.swarmweaver/"""
    return Path.home() / ".swarmweaver"


def global_claude_md() -> Path:
    return global_dir() / "CLAUDE.md"


def global_memory_dir() -> Path:
    return global_dir() / "memory"


def global_rules_dir() -> Path:
    return global_dir() / "rules"


def project_claude_md(project_dir: Path) -> Path:
    return project_dir / ".swarmweaver" / "CLAUDE.md"


def project_local_claude_md(project_dir: Path) -> Path:
    return project_dir / ".swarmweaver" / "CLAUDE.local.md"


def project_memory_dir(project_dir: Path) -> Path:
    return project_dir / ".swarmweaver" / "memory"


def project_rules_dir(project_dir: Path) -> Path:
    return project_dir / ".swarmweaver" / "rules"


# ── CLAUDE.md Loading ──

def load_claude_md_files(project_dir: Optional[Path] = None) -> list[ClaudeMdFile]:
    """Discover and load all CLAUDE.md files. Priority: global > project > local > rules."""
    files: list[ClaudeMdFile] = []

    # 1. Global CLAUDE.md
    gpath = global_claude_md()
    if gpath.is_file():
        try:
            files.append(ClaudeMdFile(
                path=str(gpath), scope="global",
                content=gpath.read_text(encoding="utf-8"),
            ))
        except OSError:
            pass

    # 2. Global rules
    for rule_file in _scan_rules_dir(global_rules_dir()):
        files.append(ClaudeMdFile(
            path=str(rule_file), scope="global",
            content=rule_file.read_text(encoding="utf-8"),
            is_rules=True,
        ))

    if project_dir:
        # 3. Project CLAUDE.md
        ppath = project_claude_md(project_dir)
        if ppath.is_file():
            try:
                files.append(ClaudeMdFile(
                    path=str(ppath), scope="project",
                    content=ppath.read_text(encoding="utf-8"),
                ))
            except OSError:
                pass

        # 4. Project rules
        for rule_file in _scan_rules_dir(project_rules_dir(project_dir)):
            files.append(ClaudeMdFile(
                path=str(rule_file), scope="project",
                content=rule_file.read_text(encoding="utf-8"),
                is_rules=True,
            ))

        # 5. Local overrides (gitignored)
        lpath = project_local_claude_md(project_dir)
        if lpath.is_file():
            try:
                files.append(ClaudeMdFile(
                    path=str(lpath), scope="local",
                    content=lpath.read_text(encoding="utf-8"),
                ))
            except OSError:
                pass

    return files


def build_claude_md_context(project_dir: Optional[Path] = None) -> str:
    """Build the full CLAUDE.md context string for prompt injection."""
    files = load_claude_md_files(project_dir)
    if not files:
        return ""

    parts = []
    for f in files:
        label = f"Contents of {f.path} ({f.scope}):"
        parts.append(f"{label}\n{f.content}")
    return "\n\n---\n\n".join(parts)


# ── MEMORY.md & Topic Files ──

def _parse_frontmatter(content: str) -> tuple[dict, str]:
    """Extract YAML frontmatter and body from markdown."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)", content, re.DOTALL)
    if not match:
        return {}, content
    try:
        import yaml
        fm = yaml.safe_load(match.group(1)) or {}
    except Exception:
        fm = {}
    return fm, match.group(2)


def truncate_entrypoint(content: str) -> str:
    """Truncate MEMORY.md to 200 lines / 25KB (matching source CLI limits)."""
    lines = content.split("\n")
    truncated = False

    if len(lines) > MAX_ENTRYPOINT_LINES:
        lines = lines[:MAX_ENTRYPOINT_LINES]
        truncated = True

    result = "\n".join(lines)

    if len(result.encode("utf-8")) > MAX_ENTRYPOINT_BYTES:
        # Find last newline before byte limit
        encoded = result.encode("utf-8")[:MAX_ENTRYPOINT_BYTES]
        result = encoded.rsplit(b"\n", 1)[0].decode("utf-8", errors="replace")
        truncated = True

    if truncated:
        result += "\n\n> WARNING: MEMORY.md was truncated. Only part of it was loaded."

    return result


def load_memory_index(memory_dir: Path) -> str:
    """Load and truncate MEMORY.md from a memory directory."""
    index_path = memory_dir / "MEMORY.md"
    if not index_path.is_file():
        return ""
    try:
        content = index_path.read_text(encoding="utf-8")
        return truncate_entrypoint(content)
    except OSError:
        return ""


def scan_memory_files(memory_dir: Path) -> list[MemoryFile]:
    """Scan a memory directory for topic files (excluding MEMORY.md)."""
    if not memory_dir.is_dir():
        return []

    files: list[MemoryFile] = []
    now = time.time()

    for f in sorted(memory_dir.iterdir()):
        if not f.is_file() or f.suffix != ".md" or f.name == "MEMORY.md":
            continue
        if len(files) >= MAX_MEMORY_FILES:
            break

        try:
            content = f.read_text(encoding="utf-8")
            stat = f.stat()
            mtime = stat.st_mtime
            age_days = int((now - mtime) / 86400)
        except OSError:
            continue

        fm, body = _parse_frontmatter(content)

        files.append(MemoryFile(
            path=str(f),
            name=fm.get("name", f.stem),
            description=fm.get("description", ""),
            memory_type=fm.get("type", "project"),
            content=body.strip(),
            mtime=mtime,
            age_days=age_days,
        ))

    return files


def build_memory_context(project_dir: Optional[Path] = None) -> str:
    """Build the full memory context: global MEMORY.md + project MEMORY.md."""
    parts = []

    # Global memory index
    global_index = load_memory_index(global_memory_dir())
    if global_index:
        parts.append(f"# Global Memory\n\n{global_index}")

    # Project memory index
    if project_dir:
        proj_index = load_memory_index(project_memory_dir(project_dir))
        if proj_index:
            parts.append(f"# Project Memory\n\n{proj_index}")

    return "\n\n---\n\n".join(parts)


def save_memory_file(
    name: str,
    content: str,
    memory_type: str = "project",
    description: str = "",
    scope: str = "project",
    project_dir: Optional[Path] = None,
) -> Path:
    """Save a memory topic file."""
    if scope == "global":
        mem_dir = global_memory_dir()
    elif project_dir:
        mem_dir = project_memory_dir(project_dir)
    else:
        mem_dir = global_memory_dir()

    mem_dir.mkdir(parents=True, exist_ok=True)

    # Build file with frontmatter
    filename = re.sub(r"[^\w\-.]", "_", name.lower()) + ".md"
    file_path = mem_dir / filename

    frontmatter = f"---\nname: {name}\ndescription: {description}\ntype: {memory_type}\n---\n\n"
    file_path.write_text(frontmatter + content, encoding="utf-8")

    return file_path


def update_memory_index(
    entry_title: str,
    entry_file: str,
    entry_hook: str,
    scope: str = "project",
    project_dir: Optional[Path] = None,
) -> None:
    """Add or update an entry in MEMORY.md index."""
    if scope == "global":
        mem_dir = global_memory_dir()
    elif project_dir:
        mem_dir = project_memory_dir(project_dir)
    else:
        return

    mem_dir.mkdir(parents=True, exist_ok=True)
    index_path = mem_dir / "MEMORY.md"

    existing = ""
    if index_path.is_file():
        try:
            existing = index_path.read_text(encoding="utf-8")
        except OSError:
            pass

    # Check if entry already exists (by filename)
    new_line = f"- [{entry_title}]({entry_file}) — {entry_hook}"
    lines = existing.strip().split("\n") if existing.strip() else []

    updated = False
    for i, line in enumerate(lines):
        if f"]({entry_file})" in line:
            lines[i] = new_line
            updated = True
            break

    if not updated:
        lines.append(new_line)

    index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def delete_memory_file(
    filename: str,
    scope: str = "project",
    project_dir: Optional[Path] = None,
) -> bool:
    """Delete a memory topic file and remove from index."""
    if scope == "global":
        mem_dir = global_memory_dir()
    elif project_dir:
        mem_dir = project_memory_dir(project_dir)
    else:
        return False

    file_path = mem_dir / filename
    if file_path.is_file():
        file_path.unlink()
        # Remove from MEMORY.md index
        index_path = mem_dir / "MEMORY.md"
        if index_path.is_file():
            try:
                content = index_path.read_text(encoding="utf-8")
                lines = [l for l in content.split("\n") if f"]({filename})" not in l]
                index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            except OSError:
                pass
        return True
    return False


def _scan_rules_dir(rules_dir: Path) -> list[Path]:
    """Scan a rules directory for .md files."""
    if not rules_dir.is_dir():
        return []
    return sorted(f for f in rules_dir.iterdir() if f.is_file() and f.suffix == ".md")
