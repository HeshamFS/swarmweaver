"""
Session Checkpoint & Handoff
================================

Saves agent working state at session boundaries so work can be
resumed after context compaction, crashes, or manual restarts.

Session chains link multiple sessions in a logical run sequence,
enabling handoff context and chain-level progress tracking.
"""

import json
import os
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class SessionCheckpoint:
    """Snapshot of agent state at a point in time."""
    agent_name: str
    session_id: str
    run_id: str
    progress_summary: str
    files_modified: list[str]
    current_branch: str
    pending_work: str
    domains_worked: list[str]
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SessionHandoff:
    """Records a session transition."""
    from_session: str
    to_session: str
    checkpoint: dict
    reason: str  # compaction, crash, manual, timeout
    chain_id: str = ""
    sequence_number: int = 0
    checkpoint_summary: str = ""
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ChainEntry:
    """A single session entry within a session chain."""
    session_id: str
    chain_id: str
    sequence_number: int
    checkpoint_summary: str = ""
    start_time: str = ""
    end_time: str = ""
    phase: str = ""
    tasks_completed: int = 0
    tasks_total: int = 0
    cost: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


class CheckpointManager:
    """
    Manages session checkpoints for agent continuity.

    Usage:
        mgr = CheckpointManager(project_dir)
        mgr.save_checkpoint(SessionCheckpoint(...))
        checkpoint = mgr.load_checkpoint(agent_name)
    """

    CHECKPOINT_DIR = ".swarmweaver/checkpoints"

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.checkpoint_dir = project_dir / self.CHECKPOINT_DIR

    def save_checkpoint(self, checkpoint: SessionCheckpoint) -> Path:
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        filepath = self.checkpoint_dir / f"{checkpoint.agent_name}.json"
        filepath.write_text(
            json.dumps(checkpoint.to_dict(), indent=2), encoding="utf-8"
        )
        return filepath

    def load_checkpoint(self, agent_name: str) -> Optional[SessionCheckpoint]:
        filepath = self.checkpoint_dir / f"{agent_name}.json"
        if not filepath.exists():
            return None
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            return SessionCheckpoint(**data)
        except (json.JSONDecodeError, TypeError, KeyError):
            return None

    def save_handoff(self, handoff: SessionHandoff) -> Path:
        handoffs_dir = self.checkpoint_dir / "handoffs"
        handoffs_dir.mkdir(parents=True, exist_ok=True)
        filepath = handoffs_dir / f"{handoff.from_session}_to_{handoff.to_session}.json"
        filepath.write_text(
            json.dumps(handoff.to_dict(), indent=2), encoding="utf-8"
        )
        return filepath

    def list_checkpoints(self) -> list[SessionCheckpoint]:
        if not self.checkpoint_dir.exists():
            return []
        results = []
        for f in self.checkpoint_dir.glob("*.json"):
            if f.name == "handoffs":
                continue
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                results.append(SessionCheckpoint(**data))
            except (json.JSONDecodeError, TypeError, KeyError):
                continue
        return results

    def clear_checkpoint(self, agent_name: str) -> bool:
        filepath = self.checkpoint_dir / f"{agent_name}.json"
        if filepath.exists():
            filepath.unlink()
            return True
        return False

    def get_checkpoint_context(self, agent_name: str) -> str:
        """Format checkpoint as context for prompt injection."""
        cp = self.load_checkpoint(agent_name)
        if not cp:
            return ""
        lines = [
            "## Previous Session Checkpoint",
            f"**Progress**: {cp.progress_summary}",
        ]
        if cp.pending_work:
            lines.append(f"**Pending Work**: {cp.pending_work}")
        if cp.files_modified:
            lines.append(f"**Files Modified**: {', '.join(cp.files_modified[:10])}")
        if cp.current_branch:
            lines.append(f"**Branch**: {cp.current_branch}")
        if cp.domains_worked:
            lines.append(f"**Domains**: {', '.join(cp.domains_worked)}")
        return "\n".join(lines) + "\n"


class ChainManager:
    """
    Manages session chains -- sequences of sessions in one logical run.

    Chain data is stored at <project>/.swarmweaver/chains/{chain_id}.json.
    Each chain file contains a list of ChainEntry dicts sorted by sequence_number.
    """

    CHAINS_DIR = ".swarmweaver/chains"

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.chains_dir = project_dir / self.CHAINS_DIR

    def _chain_path(self, chain_id: str) -> Path:
        return self.chains_dir / f"{chain_id}.json"

    def get_or_create_chain_id(self) -> str:
        """Return the active chain_id for this project, or create a new one."""
        active_file = self.chains_dir / "_active_chain.txt"
        if active_file.exists():
            chain_id = active_file.read_text(encoding="utf-8").strip()
            if chain_id and self._chain_path(chain_id).exists():
                return chain_id
        # Create a new chain
        chain_id = uuid.uuid4().hex[:12]
        self.chains_dir.mkdir(parents=True, exist_ok=True)
        active_file.write_text(chain_id, encoding="utf-8")
        return chain_id

    def get_active_chain_id(self) -> Optional[str]:
        """Return the active chain_id or None if no chain exists."""
        active_file = self.chains_dir / "_active_chain.txt"
        if active_file.exists():
            chain_id = active_file.read_text(encoding="utf-8").strip()
            if chain_id:
                return chain_id
        return None

    def start_new_chain(self) -> str:
        """Force-start a new chain (e.g. for fresh runs)."""
        chain_id = uuid.uuid4().hex[:12]
        self.chains_dir.mkdir(parents=True, exist_ok=True)
        active_file = self.chains_dir / "_active_chain.txt"
        active_file.write_text(chain_id, encoding="utf-8")
        return chain_id

    def add_entry(self, entry: ChainEntry) -> None:
        """Append a session entry to the chain file."""
        self.chains_dir.mkdir(parents=True, exist_ok=True)
        chain_path = self._chain_path(entry.chain_id)
        entries = []
        if chain_path.exists():
            try:
                entries = json.loads(chain_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                entries = []
        # Update existing entry with same session_id, or append
        found = False
        for i, e in enumerate(entries):
            if e.get("session_id") == entry.session_id:
                entries[i] = entry.to_dict()
                found = True
                break
        if not found:
            entries.append(entry.to_dict())
        # Sort by sequence_number
        entries.sort(key=lambda e: e.get("sequence_number", 0))
        chain_path.write_text(json.dumps(entries, indent=2), encoding="utf-8")

    def get_chain(self, chain_id: Optional[str] = None) -> list[dict]:
        """
        Get all session entries in a chain, sorted by sequence_number.

        If chain_id is None, uses the active chain.
        """
        if chain_id is None:
            chain_id = self.get_active_chain_id()
        if not chain_id:
            return []
        chain_path = self._chain_path(chain_id)
        if not chain_path.exists():
            return []
        try:
            entries = json.loads(chain_path.read_text(encoding="utf-8"))
            entries.sort(key=lambda e: e.get("sequence_number", 0))
            return entries
        except (json.JSONDecodeError, OSError):
            return []

    def get_next_sequence_number(self, chain_id: Optional[str] = None) -> int:
        """Get the next sequence number for a chain."""
        entries = self.get_chain(chain_id)
        if not entries:
            return 1
        return max(e.get("sequence_number", 0) for e in entries) + 1

    def get_previous_summary(self, chain_id: Optional[str] = None) -> Optional[str]:
        """Get the checkpoint_summary from the most recent entry in the chain."""
        entries = self.get_chain(chain_id)
        if not entries:
            return None
        last = entries[-1]
        return last.get("checkpoint_summary") or None

    def save_structured_checkpoint(self, chain_id: str, checkpoint: dict) -> None:
        """Save structured checkpoint for context recovery between phases."""
        cp_file = self.chains_dir / f"{chain_id}_structured.json"
        cp_file.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write
        tmp = cp_file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")
        os.replace(tmp, cp_file)

    def get_structured_checkpoint(self, chain_id: str) -> Optional[dict]:
        """Load structured checkpoint data from last phase."""
        cp_file = self.chains_dir / f"{chain_id}_structured.json"
        if not cp_file.exists():
            return None
        try:
            return json.loads(cp_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def list_all_chains(self) -> list[str]:
        """List all chain IDs in this project."""
        if not self.chains_dir.exists():
            return []
        return [
            f.stem for f in self.chains_dir.glob("*.json")
            if f.stem != "_active_chain"
        ]
