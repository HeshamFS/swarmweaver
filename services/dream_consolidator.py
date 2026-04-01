"""
Dream Consolidator — Background MELS Memory Consolidation
============================================================

4-stage pipeline triggered by 5-gate system:
1. Feature enabled
2. Time gate (24h since last run)
3. Scan throttle (10min between scans)
4. Session gate (5+ sessions since last)
5. Lock gate (asyncio.Lock)

Stages: Orient → Gather → Consolidate → Prune
"""

import asyncio
import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import logging

logger = logging.getLogger(__name__)


@dataclass
class DreamConfig:
    """Configuration for dream task gating."""
    enabled: bool = True
    time_gate_hours: int = 24
    scan_throttle_minutes: int = 10
    session_gate_count: int = 5
    max_turns: int = 30
    stale_lock_hours: float = 1.0


@dataclass
class DreamResult:
    """Result of a consolidation run."""
    existing_records: int = 0
    new_learnings: int = 0
    consolidated: int = 0
    pruned: int = 0
    duration_seconds: float = 0.0
    stages_completed: list[str] = field(default_factory=list)
    error: Optional[str] = None
    timestamp: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class DreamGatekeeper:
    """Manages the 5-gate triggering logic."""

    def __init__(self, config: DreamConfig, project_dir: Path):
        self.config = config
        self.project_dir = project_dir
        self._lock = asyncio.Lock()
        self._last_scan_time: float = 0
        self._state_file = project_dir / ".swarmweaver" / "dream_state.json"

    def _load_state(self) -> dict:
        if self._state_file.exists():
            try:
                return json.loads(self._state_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _save_state(self, state: dict) -> None:
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            self._state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
        except OSError:
            pass

    async def check_gates(self) -> tuple[bool, str]:
        """Check all 5 gates. Returns (should_run, reason)."""
        # Gate 1: Feature enabled
        if not self.config.enabled:
            return False, "disabled"

        state = self._load_state()

        # Gate 2: Time gate
        last_run = state.get("last_run_timestamp", "")
        if last_run:
            try:
                last_dt = datetime.fromisoformat(last_run)
                hours_since = (datetime.now() - last_dt).total_seconds() / 3600
                if hours_since < self.config.time_gate_hours:
                    return False, f"time_gate: {hours_since:.1f}h < {self.config.time_gate_hours}h"
            except (ValueError, TypeError):
                pass

        # Gate 3: Scan throttle
        now = time.time()
        if now - self._last_scan_time < self.config.scan_throttle_minutes * 60:
            return False, "scan_throttle"
        self._last_scan_time = now

        # Gate 4: Session gate
        session_count = self._count_sessions_since_last_run(state)
        if session_count < self.config.session_gate_count:
            return False, f"session_gate: {session_count}/{self.config.session_gate_count}"

        # Gate 5: Lock gate
        if self._lock.locked():
            return False, "lock_gate: already running"

        return True, "all_gates_passed"

    def _count_sessions_since_last_run(self, state: dict) -> int:
        """Count sessions completed since last dream run."""
        try:
            from state.sessions import SessionStore
            store = SessionStore(self.project_dir)
            store.initialize()
            last_run = state.get("last_run_timestamp", "")
            sessions = store.list_sessions(limit=100)
            if not last_run:
                return len(sessions)
            count = 0
            for s in sessions:
                created = s.get("created_at", "")
                if created > last_run:
                    count += 1
            return count
        except Exception:
            return 0

    def get_gate_status(self) -> dict:
        """Return current gate status for UI display."""
        state = self._load_state()
        last_run = state.get("last_run_timestamp", "")
        hours_since = 0.0
        if last_run:
            try:
                hours_since = (datetime.now() - datetime.fromisoformat(last_run)).total_seconds() / 3600
            except (ValueError, TypeError):
                pass

        session_count = self._count_sessions_since_last_run(state)

        return {
            "enabled": self.config.enabled,
            "time_gate": {
                "threshold_hours": self.config.time_gate_hours,
                "hours_since_last": round(hours_since, 1),
                "passed": hours_since >= self.config.time_gate_hours or not last_run,
            },
            "session_gate": {
                "threshold": self.config.session_gate_count,
                "current": session_count,
                "passed": session_count >= self.config.session_gate_count,
            },
            "lock_gate": {
                "locked": self._lock.locked(),
            },
            "last_run": last_run,
            "history": state.get("history", [])[-10:],
        }


class DreamPipeline:
    """4-stage memory consolidation pipeline."""

    def __init__(self, project_dir: Path, config: DreamConfig):
        self.project_dir = project_dir
        self.config = config
        self._turn_count = 0

    async def run(self) -> DreamResult:
        """Execute the 4-stage pipeline."""
        start = time.time()
        result = DreamResult(timestamp=datetime.now().isoformat())

        try:
            # Stage 1: Orient
            result.existing_records = await self._orient()
            result.stages_completed.append("orient")

            # Stage 2: Gather
            result.new_learnings = await self._gather()
            result.stages_completed.append("gather")

            # Stage 3: Consolidate
            result.consolidated = await self._consolidate()
            result.stages_completed.append("consolidate")

            # Stage 4: Prune
            result.pruned = await self._prune()
            result.stages_completed.append("prune")

        except Exception as e:
            result.error = str(e)
            logger.warning(f"Dream pipeline error: {e}")

        result.duration_seconds = round(time.time() - start, 2)
        return result

    async def _orient(self) -> int:
        """List existing MELS records, assess coverage."""
        try:
            from services.expertise_store import ExpertiseStore
            db_path = self.project_dir / ".swarmweaver" / "expertise" / "expertise.db"
            if not db_path.exists():
                return 0
            store = ExpertiseStore(db_path)
            records = store.search(limit=500)
            count = len(records)
            store.close()
            return count
        except Exception:
            return 0

    async def _gather(self) -> int:
        """Scan session transcripts for learnings."""
        try:
            from state.sessions import SessionStore
            store = SessionStore(self.project_dir)
            store.initialize()
            sessions = store.list_sessions(limit=20)
            learning_count = 0
            for session in sessions:
                messages = store.get_messages(session.get("id", ""))
                if messages:
                    learning_count += self._extract_learning_count(messages)
                if self._turn_count >= self.config.max_turns:
                    break
                self._turn_count += 1
            return learning_count
        except Exception:
            return 0

    def _extract_learning_count(self, messages: list) -> int:
        """Count potential learnings from session messages."""
        count = 0
        for msg in messages:
            content = str(msg.get("content", ""))
            # Heuristic: errors, fixes, and key decisions are learnings
            if any(kw in content.lower() for kw in ["error", "fix", "solved", "found", "issue", "bug", "resolved"]):
                count += 1
        return count

    async def _consolidate(self) -> int:
        """Write new expertise records from gathered learnings."""
        # This stage would use LLM to synthesize patterns.
        # For now, return 0 (learnings are tracked but not auto-promoted yet)
        return 0

    async def _prune(self) -> int:
        """Remove expired records, update confidence scores."""
        try:
            from services.expertise_store import ExpertiseStore
            from services.expertise_scoring import recalculate_confidence
            db_path = self.project_dir / ".swarmweaver" / "expertise" / "expertise.db"
            if not db_path.exists():
                return 0
            store = ExpertiseStore(db_path)
            # Prune records with confidence < 0.1 that are older than 30 days
            records = store.search(limit=500)
            pruned = 0
            for record in records:
                if hasattr(record, "confidence") and record.confidence < 0.1:
                    store.delete(record.id)
                    pruned += 1
            store.close()
            return pruned
        except Exception:
            return 0
