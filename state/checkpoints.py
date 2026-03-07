"""
Checkpoint Management for Autonomous Coding Agent
==================================================

Tracks file checkpoints during agent sessions for rollback capability.
Uses the Claude Agent SDK's file checkpointing feature.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import json
from typing import Optional

from core.paths import get_paths


@dataclass
class Checkpoint:
    """Represents a file state checkpoint."""
    id: str
    description: str
    timestamp: datetime
    session_id: str
    iteration: int


class CheckpointManager:
    """Manages checkpoint storage and retrieval for file rollback."""

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.checkpoints_file = get_paths(project_dir).checkpoints
        self.checkpoints: list[Checkpoint] = []

    def add(self, checkpoint: Checkpoint) -> None:
        """Add a new checkpoint and persist to disk."""
        self.checkpoints.append(checkpoint)
        self.save()

    def get_latest(self) -> Optional[Checkpoint]:
        """Get the most recent checkpoint."""
        return self.checkpoints[-1] if self.checkpoints else None

    def get_by_id(self, checkpoint_id: str) -> Optional[Checkpoint]:
        """Get a checkpoint by its ID."""
        for checkpoint in self.checkpoints:
            if checkpoint.id == checkpoint_id:
                return checkpoint
        return None

    def get_by_session(self, session_id: str) -> list[Checkpoint]:
        """Get all checkpoints for a specific session."""
        return [c for c in self.checkpoints if c.session_id == session_id]

    def get_by_iteration(self, iteration: int) -> list[Checkpoint]:
        """Get all checkpoints for a specific iteration."""
        return [c for c in self.checkpoints if c.iteration == iteration]

    def clear_old_checkpoints(self, keep_last_n: int = 50) -> int:
        """Remove old checkpoints, keeping only the most recent N."""
        if len(self.checkpoints) <= keep_last_n:
            return 0
        removed_count = len(self.checkpoints) - keep_last_n
        self.checkpoints = self.checkpoints[-keep_last_n:]
        self.save()
        return removed_count

    def save(self) -> None:
        """Persist checkpoints to disk."""
        data = [
            {
                "id": c.id,
                "description": c.description,
                "timestamp": c.timestamp.isoformat(),
                "session_id": c.session_id,
                "iteration": c.iteration,
            }
            for c in self.checkpoints
        ]
        try:
            self.checkpoints_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.checkpoints_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Warning: Failed to save checkpoints: {e}")

    def load(self) -> None:
        """Load checkpoints from disk."""
        if not self.checkpoints_file.exists():
            self.checkpoints = []
            return

        try:
            with open(self.checkpoints_file) as f:
                data = json.load(f)
            self.checkpoints = [
                Checkpoint(
                    id=c["id"],
                    description=c["description"],
                    timestamp=datetime.fromisoformat(c["timestamp"]),
                    session_id=c["session_id"],
                    iteration=c["iteration"],
                )
                for c in data
            ]
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Warning: Failed to load checkpoints: {e}")
            self.checkpoints = []

    def __len__(self) -> int:
        return len(self.checkpoints)

    def __repr__(self) -> str:
        return f"CheckpointManager({len(self.checkpoints)} checkpoints)"
