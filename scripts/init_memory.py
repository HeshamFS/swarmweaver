"""Initialize default memory structure for SwarmWeaver."""

from pathlib import Path


def init_global_memory():
    """Create ~/.swarmweaver/ with default CLAUDE.md and memory/MEMORY.md."""
    base = Path.home() / ".swarmweaver"

    # CLAUDE.md
    claude_md = base / "CLAUDE.md"
    if not claude_md.exists():
        base.mkdir(parents=True, exist_ok=True)
        claude_md.write_text(
            "# Global SwarmWeaver Instructions\n\n"
            "These instructions apply to ALL projects.\n\n"
            "## Preferences\n\n"
            "<!-- Add your global preferences here -->\n",
            encoding="utf-8",
        )

    # memory/MEMORY.md
    mem_dir = base / "memory"
    mem_index = mem_dir / "MEMORY.md"
    if not mem_index.exists():
        mem_dir.mkdir(parents=True, exist_ok=True)
        mem_index.write_text(
            "<!-- Global memory index. Each entry should be one line, under 150 chars. -->\n",
            encoding="utf-8",
        )

    # rules/
    rules_dir = base / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)


def init_project_memory(project_dir: Path):
    """Create .swarmweaver/ memory structure for a project."""
    sw = project_dir / ".swarmweaver"

    # CLAUDE.md
    claude_md = sw / "CLAUDE.md"
    if not claude_md.exists():
        sw.mkdir(parents=True, exist_ok=True)
        claude_md.write_text(
            "# Project Instructions\n\n"
            "These instructions apply to this project only.\n\n"
            "## Architecture\n\n"
            "<!-- Describe your project architecture here -->\n",
            encoding="utf-8",
        )

    # memory/MEMORY.md
    mem_dir = sw / "memory"
    mem_index = mem_dir / "MEMORY.md"
    if not mem_index.exists():
        mem_dir.mkdir(parents=True, exist_ok=True)
        mem_index.write_text(
            "<!-- Project memory index. Each entry should be one line, under 150 chars. -->\n",
            encoding="utf-8",
        )

    # rules/
    rules_dir = sw / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    init_global_memory()
    print("Global memory initialized at ~/.swarmweaver/")
