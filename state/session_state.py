"""
Session State Management for Autonomous Coding Agent
=====================================================

Persists session IDs across process restarts for conversation continuity.
Supports session resumption and forking via the Claude Agent SDK.
"""

from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
import json
from typing import Optional

from core.paths import get_paths


@dataclass
class SessionState:
    """Represents a persistent session state."""
    session_id: str
    created_at: datetime
    last_used: datetime
    iteration: int
    model: str
    is_fork: bool = False
    parent_session_id: Optional[str] = None
    phase: Optional[str] = None
    chain_id: Optional[str] = None
    sequence_number: int = 1


class SessionManager:
    """Manages session state persistence for resumption across restarts."""

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.state_file = get_paths(project_dir).session_state

    def save(self, state: SessionState) -> None:
        """Persist session state to disk."""
        data = asdict(state)
        data["created_at"] = state.created_at.isoformat()
        data["last_used"] = state.last_used.isoformat()
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.state_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Warning: Failed to save session state: {e}")

    def load(self) -> Optional[SessionState]:
        """Load session state from disk."""
        if not self.state_file.exists():
            return None

        try:
            with open(self.state_file) as f:
                data = json.load(f)
            data["created_at"] = datetime.fromisoformat(data["created_at"])
            data["last_used"] = datetime.fromisoformat(data["last_used"])
            return SessionState(**data)
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            print(f"Warning: Failed to load session state: {e}")
            return None

    def clear(self) -> bool:
        """Clear the session state file."""
        if self.state_file.exists():
            try:
                self.state_file.unlink()
                return True
            except Exception as e:
                print(f"Warning: Failed to clear session state: {e}")
                return False
        return True

    def fork(self, current_state: SessionState) -> SessionState:
        """
        Create a forked session state for experimental branches.

        The forked state maintains reference to the parent session
        and will get a new session_id when resumed with fork_session=True.
        """
        return SessionState(
            session_id=current_state.session_id,  # Will be replaced by SDK
            created_at=datetime.now(),
            last_used=datetime.now(),
            iteration=current_state.iteration,
            model=current_state.model,
            is_fork=True,
            parent_session_id=current_state.session_id,
        )

    def exists(self) -> bool:
        """Check if a session state file exists."""
        return self.state_file.exists()

    def get_age_seconds(self) -> Optional[float]:
        """Get the age of the session in seconds since last use."""
        state = self.load()
        if state:
            return (datetime.now() - state.last_used).total_seconds()
        return None

    def __repr__(self) -> str:
        state = self.load()
        if state:
            return f"SessionManager(session_id={state.session_id[:8]}..., iteration={state.iteration})"
        return "SessionManager(no session)"
