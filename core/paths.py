"""
Centralized Project Paths
===========================

Single source of truth for all SwarmWeaver artifact paths.
Every artifact lives under ``<project>/.swarmweaver/`` so users can
``rm -rf .swarmweaver`` to completely clean up.
"""

import os
from pathlib import Path
from typing import Optional


class ProjectPaths:
    """Resolves every SwarmWeaver artifact to ``.swarmweaver/``."""

    def __init__(self, project_dir: Path):
        self.project_dir = Path(project_dir)
        self.swarmweaver_dir = self.project_dir / ".swarmweaver"

    # ------------------------------------------------------------------
    # Ensure .swarmweaver exists
    # ------------------------------------------------------------------
    def ensure_dir(self) -> None:
        """Create .swarmweaver/ and memory subdirectories if they don't exist."""
        p = str(self.swarmweaver_dir)
        if not os.path.isdir(p):
            try:
                os.makedirs(p, exist_ok=True)
            except (FileExistsError, OSError):
                # WSL2/NTFS ghost entry: mkdir fails with EEXIST for a directory
                # name that was previously deleted but left a phantom MFT record.
                # Neither os.path.exists nor os.path.isdir can see it, but mkdir
                # refuses to create it.  Fall back to Windows cmd.exe mkdir.
                if os.path.isdir(p):
                    pass
                elif p.startswith("/mnt/"):
                    self._wsl_mkdir_fallback(p)
                else:
                    raise

        # Auto-initialize memory structure for this project
        self._ensure_memory_structure()

    def _ensure_memory_structure(self) -> None:
        """Create memory subdirectories and default files if missing."""
        try:
            # memory/ directory
            mem_dir = self.swarmweaver_dir / "memory"
            mem_dir.mkdir(parents=True, exist_ok=True)

            # memory/MEMORY.md index
            mem_index = mem_dir / "MEMORY.md"
            if not mem_index.exists():
                mem_index.write_text(
                    "<!-- Project memory index. Each entry is one line, under 150 chars. -->\n",
                    encoding="utf-8",
                )

            # rules/ directory
            (self.swarmweaver_dir / "rules").mkdir(exist_ok=True)

            # Also ensure global memory exists (once)
            _ensure_global_memory()
        except OSError:
            pass  # Non-fatal: memory is best-effort

    @staticmethod
    def _wsl_mkdir_fallback(unix_path: str) -> None:
        """Create a directory via cmd.exe on WSL2/NTFS as a last resort."""
        import subprocess
        # Convert /mnt/d/foo/bar → D:\foo\bar
        parts = unix_path.split("/")  # ['', 'mnt', 'd', 'foo', 'bar']
        if len(parts) >= 3:
            drive = parts[2].upper()
            win_path = f"{drive}:\\" + "\\".join(parts[3:])
            subprocess.run(
                ["cmd.exe", "/C", f"mkdir {win_path}"],
                capture_output=True, timeout=5,
            )
        if not os.path.isdir(unix_path):
            raise OSError(f"Failed to create directory: {unix_path}")

    # ------------------------------------------------------------------
    # Core artifacts (JSON / text)
    # ------------------------------------------------------------------
    @property
    def task_list(self) -> Path:
        return self.swarmweaver_dir /"task_list.json"

    @property
    def codebase_profile(self) -> Path:
        return self.swarmweaver_dir /"codebase_profile.json"

    @property
    def security_report(self) -> Path:
        return self.swarmweaver_dir /"security_report.json"

    @property
    def session_reflections(self) -> Path:
        return self.swarmweaver_dir /"session_reflections.json"

    @property
    def session_state(self) -> Path:
        return self.swarmweaver_dir /"session_state.json"

    @property
    def progress_notes(self) -> Path:
        return self.swarmweaver_dir /"claude-progress.txt"

    @property
    def app_spec(self) -> Path:
        return self.swarmweaver_dir /"app_spec.txt"

    @property
    def task_input(self) -> Path:
        return self.swarmweaver_dir /"task_input.txt"

    @property
    def audit_log(self) -> Path:
        return self.swarmweaver_dir /"audit.log"

    @property
    def agent_output_log(self) -> Path:
        return self.swarmweaver_dir /"agent_output.log"

    @property
    def budget_state(self) -> Path:
        return self.swarmweaver_dir /"budget_state.json"

    @property
    def approval_pending(self) -> Path:
        return self.swarmweaver_dir /"approval_pending.json"

    @property
    def approval_resolved(self) -> Path:
        return self.swarmweaver_dir /"approval_resolved.json"

    @property
    def model_override(self) -> Path:
        return self.swarmweaver_dir /"model_override.json"

    @property
    def process_registry(self) -> Path:
        return self.swarmweaver_dir /"process_registry.json"

    @property
    def claude_settings(self) -> Path:
        return self.swarmweaver_dir /"claude_settings.json"

    @property
    def checkpoints(self) -> Path:
        return self.swarmweaver_dir /"checkpoints.json"

    @property
    def architect_notes(self) -> Path:
        return self.swarmweaver_dir /"architect_notes.md"

    @property
    def steering_input(self) -> Path:
        return self.swarmweaver_dir /"steering_input.json"

    @property
    def transcript_archive(self) -> Path:
        return self.swarmweaver_dir /"transcript_archive.jsonl"

    @property
    def activity_log(self) -> Path:
        """JSONL log of all WebSocket activity events — persisted so completed
        projects can be replayed in the frontend without losing history."""
        return self.swarmweaver_dir / "activity_log.jsonl"

    @property
    def error_log(self) -> Path:
        """JSONL log of all tool/session errors with agent, tool, input, and error message."""
        return self.swarmweaver_dir / "error_log.jsonl"

    @property
    def run_config(self) -> Path:
        """Saved swarm/run configuration for resume detection."""
        return self.swarmweaver_dir / "run_config.json"

    # ------------------------------------------------------------------
    # Directories
    # ------------------------------------------------------------------
    @property
    def swarm_dir(self) -> Path:
        return self.swarmweaver_dir /"swarm"

    @property
    def swarm_state(self) -> Path:
        return self.swarmweaver_dir /"swarm" / "state.json"

    @property
    def port_allocations(self) -> Path:
        return self.swarm_dir / "port_allocations.json"

    @property
    def worktrees_dir(self) -> Path:
        return self.swarmweaver_dir /"worktrees"

    @property
    def runs_dir(self) -> Path:
        return self.swarmweaver_dir /"runs"

    @property
    def specs_dir(self) -> Path:
        return self.swarmweaver_dir /"specs"

    @property
    def agents_dir(self) -> Path:
        return self.swarmweaver_dir /"agents"

    @property
    def lsp_config(self) -> Path:
        return self.swarmweaver_dir / "lsp.yaml"

    @property
    def sessions_db(self) -> Path:
        return self.swarmweaver_dir / "sessions.db"

    # ------------------------------------------------------------------
    # Artifact lookup
    # ------------------------------------------------------------------
    def resolve_read(self, filename: str) -> Path:
        """Return the canonical path for an artifact under .swarmweaver/."""
        return self.swarmweaver_dir / filename


def get_paths(project_dir) -> ProjectPaths:
    """Convenience factory — returns a ``ProjectPaths`` instance."""
    return ProjectPaths(Path(project_dir))


def _ensure_global_memory() -> None:
    """Create ~/.swarmweaver/ global memory structure if missing (idempotent)."""
    try:
        base = Path.home() / ".swarmweaver"
        base.mkdir(parents=True, exist_ok=True)

        # Global CLAUDE.md
        claude_md = base / "CLAUDE.md"
        if not claude_md.exists():
            claude_md.write_text(
                "# Global SwarmWeaver Instructions\n\n"
                "These instructions apply to ALL projects.\n\n"
                "## Preferences\n\n"
                "<!-- Add your global preferences here -->\n",
                encoding="utf-8",
            )

        # Global memory/MEMORY.md
        mem_dir = base / "memory"
        mem_dir.mkdir(exist_ok=True)
        mem_index = mem_dir / "MEMORY.md"
        if not mem_index.exists():
            mem_index.write_text(
                "<!-- Global memory index. Each entry is one line, under 150 chars. -->\n",
                encoding="utf-8",
            )

        # Global rules/
        (base / "rules").mkdir(exist_ok=True)
    except OSError:
        pass  # Non-fatal
