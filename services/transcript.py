"""
Real-Time Session Transcript
==============================

Persists every engine event to a JSONL file as it happens.
Enables session recovery even after crashes/interrupts.

Storage:
  Global:  ~/.swarmweaver/transcripts/{session_id}.jsonl
  Project: .swarmweaver/transcripts/{session_id}.jsonl
"""

import json
import time
import os
from pathlib import Path
from datetime import datetime
from typing import Optional


class TranscriptWriter:
    """Appends events to a JSONL transcript file in real-time."""

    def __init__(self, project_dir: Path, session_id: str):
        self.project_dir = project_dir
        self.session_id = session_id
        self._file = None
        self._event_count = 0

        # Project-level transcript
        self._project_path = project_dir / ".swarmweaver" / "transcripts"
        self._project_path.mkdir(parents=True, exist_ok=True)
        self._project_file = self._project_path / f"{session_id}.jsonl"

        # Global transcript (cross-project index)
        self._global_path = Path.home() / ".swarmweaver" / "transcripts"
        self._global_path.mkdir(parents=True, exist_ok=True)
        self._global_file = self._global_path / f"{session_id}.jsonl"

    def open(self) -> None:
        """Open transcript files for appending."""
        self._file = open(self._project_file, "a", encoding="utf-8")
        # Write session header
        self._write_entry({
            "type": "session_start",
            "session_id": self.session_id,
            "project_dir": str(self.project_dir),
            "timestamp": datetime.now().isoformat(),
        })

    def write_event(self, event: dict) -> None:
        """Append an event to the transcript (real-time, every event)."""
        if not self._file:
            return
        entry = {
            **event,
            "_ts": time.time(),
            "_seq": self._event_count,
        }
        self._write_entry(entry)
        self._event_count += 1

    def write_turn_start(self, iteration: int, phase: str, model: str) -> None:
        """Mark the beginning of a new turn."""
        self._write_entry({
            "type": "turn_start",
            "iteration": iteration,
            "phase": phase,
            "model": model,
            "timestamp": datetime.now().isoformat(),
        })

    def write_turn_end(self, iteration: int, phase: str, input_tokens: int = 0,
                       output_tokens: int = 0, cost_usd: float = 0.0) -> None:
        """Mark the completion of a turn."""
        self._write_entry({
            "type": "turn_end",
            "iteration": iteration,
            "phase": phase,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost_usd,
            "timestamp": datetime.now().isoformat(),
        })

    def write_task_update(self, task_id: str, status: str, title: str = "") -> None:
        """Record a task status change."""
        self._write_entry({
            "type": "task_update",
            "task_id": task_id,
            "status": status,
            "title": title,
            "timestamp": datetime.now().isoformat(),
        })

    def write_progress(self, summary: str, tasks_done: int = 0, tasks_total: int = 0) -> None:
        """Save progress notes (called by engine, not relying on agent)."""
        self._write_entry({
            "type": "progress",
            "summary": summary,
            "tasks_done": tasks_done,
            "tasks_total": tasks_total,
            "timestamp": datetime.now().isoformat(),
        })

    def write_interruption(self) -> None:
        """Mark that the session was interrupted (not cleanly ended)."""
        self._write_entry({
            "type": "session_interrupted",
            "timestamp": datetime.now().isoformat(),
            "event_count": self._event_count,
        })

    # ── Swarm/Worker events ──────────────────────────────────────────

    def write_worker_spawned(self, worker_id: int, name: str, task_ids: list,
                             worktree_path: str = "", branch: str = "") -> None:
        """Record a worker being spawned."""
        self._write_entry({
            "type": "worker_spawned",
            "worker_id": worker_id,
            "name": name,
            "task_ids": task_ids,
            "worktree_path": worktree_path,
            "branch": branch,
            "timestamp": datetime.now().isoformat(),
        })

    def write_worker_completed(self, worker_id: int, name: str,
                               task_ids: list, status: str = "completed") -> None:
        """Record a worker completing or failing."""
        self._write_entry({
            "type": "worker_completed",
            "worker_id": worker_id,
            "name": name,
            "task_ids": task_ids,
            "status": status,
            "timestamp": datetime.now().isoformat(),
        })

    def write_orchestrator_state(self, num_workers: int, active_workers: list,
                                 pending_tasks: list) -> None:
        """Periodic orchestrator state snapshot for resume."""
        self._write_entry({
            "type": "orchestrator_state",
            "num_workers": num_workers,
            "active_workers": active_workers,
            "pending_tasks": pending_tasks,
            "timestamp": datetime.now().isoformat(),
        })

    def close(self, clean: bool = True) -> None:
        """Close the transcript file."""
        if self._file:
            if clean:
                self._write_entry({
                    "type": "session_end",
                    "event_count": self._event_count,
                    "timestamp": datetime.now().isoformat(),
                })
            self._file.flush()
            self._file.close()
            self._file = None

        # Copy to global transcripts for cross-project resume
        self._sync_to_global()

    def _write_entry(self, entry: dict) -> None:
        """Write a single JSON line."""
        if not self._file:
            return
        try:
            line = json.dumps(entry, ensure_ascii=False, default=str)
            self._file.write(line + "\n")
            self._file.flush()  # Flush immediately for crash safety
        except (OSError, ValueError):
            pass

    def _sync_to_global(self) -> None:
        """Copy project transcript to global directory."""
        try:
            if self._project_file.exists():
                import shutil
                shutil.copy2(str(self._project_file), str(self._global_file))
        except OSError:
            pass


class TranscriptReader:
    """Reads and analyzes JSONL transcript files for session recovery."""

    @staticmethod
    def load_transcript(path: Path) -> list[dict]:
        """Load all entries from a JSONL transcript file."""
        entries = []
        if not path.is_file():
            return entries
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except OSError:
            pass
        return entries

    @staticmethod
    def detect_interruption(entries: list[dict]) -> dict:
        """Detect if a session was interrupted (no clean session_end).

        Returns full state including swarm worker info for unified resume.
        """
        if not entries:
            return {"interrupted": False}

        has_session_end = any(e.get("type") == "session_end" for e in entries)
        has_interruption = any(e.get("type") == "session_interrupted" for e in entries)

        # Find last completed turn
        last_turn = 0
        last_phase = ""
        for e in entries:
            if e.get("type") == "turn_end":
                last_turn = e.get("iteration", 0)
                last_phase = e.get("phase", "")

        # Find last progress
        progress_summary = ""
        tasks_done = 0
        tasks_total = 0
        for e in reversed(entries):
            if e.get("type") == "progress":
                progress_summary = e.get("summary", "")
                tasks_done = e.get("tasks_done", 0)
                tasks_total = e.get("tasks_total", 0)
                break

        # Rebuild worker state from transcript events
        workers: dict[int, dict] = {}
        for e in entries:
            etype = e.get("type", "")
            if etype == "worker_spawned":
                wid = e.get("worker_id", 0)
                workers[wid] = {
                    "id": wid,
                    "name": e.get("name", f"worker-{wid}"),
                    "task_ids": e.get("task_ids", []),
                    "worktree_path": e.get("worktree_path", ""),
                    "branch": e.get("branch", ""),
                    "status": "running",
                }
            elif etype == "worker_completed":
                wid = e.get("worker_id", 0)
                if wid in workers:
                    workers[wid]["status"] = e.get("status", "completed")

        # Get latest orchestrator state snapshot
        orchestrator_state = None
        for e in reversed(entries):
            if e.get("type") == "orchestrator_state":
                orchestrator_state = e
                break

        last_timestamp = ""
        if entries:
            last_timestamp = entries[-1].get("timestamp", "")

        return {
            "interrupted": not has_session_end or has_interruption,
            "last_turn": last_turn,
            "last_phase": last_phase,
            "last_timestamp": last_timestamp,
            "tasks_done": tasks_done,
            "tasks_total": tasks_total,
            "progress_summary": progress_summary,
            "workers": workers,
            "orchestrator_state": orchestrator_state,
        }

    @staticmethod
    def build_resume_context(entries: list[dict]) -> str:
        """Build a context summary from transcript for injecting into a new session.

        This is used when SDK session has expired and we need to
        reconstruct context from the transcript.
        """
        phases_completed = []
        tasks_updates = []
        progress_notes = []
        errors = []
        last_phase = ""
        last_iteration = 0

        for e in entries:
            etype = e.get("type", "")
            if etype == "turn_end":
                last_phase = e.get("phase", "")
                last_iteration = e.get("iteration", 0)
                phases_completed.append(f"Turn {last_iteration}: {last_phase}")
            elif etype == "task_update":
                tasks_updates.append(f"- {e.get('task_id', '')}: {e.get('status', '')} — {e.get('title', '')}")
            elif etype == "progress":
                progress_notes.append(e.get("summary", ""))
            elif etype in ("tool_error", "tool_blocked"):
                err = e.get("error", e.get("reason", ""))
                if err:
                    errors.append(err[:200])

        # Rebuild worker state
        workers: dict[int, dict] = {}
        for e in entries:
            etype = e.get("type", "")
            if etype == "worker_spawned":
                wid = e.get("worker_id", 0)
                workers[wid] = {
                    "name": e.get("name", f"worker-{wid}"),
                    "task_ids": e.get("task_ids", []),
                    "worktree_path": e.get("worktree_path", ""),
                    "branch": e.get("branch", ""),
                    "status": "running",
                }
            elif etype == "worker_completed":
                wid = e.get("worker_id", 0)
                if wid in workers:
                    workers[wid]["status"] = e.get("status", "completed")

        parts = []
        parts.append("## Session Recovery Context\n")
        parts.append(f"This session is being resumed. Last completed turn: {last_iteration}, phase: {last_phase}\n")

        if progress_notes:
            parts.append("### Previous Progress\n")
            parts.append(progress_notes[-1])

        if tasks_updates:
            parts.append("\n### Task Status Changes\n")
            parts.append("\n".join(tasks_updates[-20:]))

        if workers:
            parts.append("\n### Previous Workers\n")
            parts.append("These workers were active in the previous session:\n")
            for wid, w in workers.items():
                from pathlib import Path as P
                wt_exists = P(w["worktree_path"]).exists() if w["worktree_path"] else False
                parts.append(
                    f"- {w['name']}: tasks={w['task_ids']}, status={w['status']}, "
                    f"branch={w['branch']}, worktree_exists={'YES' if wt_exists else 'NO'}"
                )
            parts.append("\nDO NOT recreate workers whose tasks are already done.")
            parts.append("Only spawn NEW workers for UNASSIGNED pending tasks.")

        if errors:
            parts.append("\n### Recent Errors\n")
            parts.append("\n".join(f"- {e}" for e in errors[-5:]))

        parts.append("\n\n**Continue from where the previous session left off.**")
        return "\n".join(parts)

    @staticmethod
    def list_sessions(project_dir: Path) -> list[dict]:
        """List all transcript sessions for a project."""
        transcript_dir = project_dir / ".swarmweaver" / "transcripts"
        if not transcript_dir.is_dir():
            return []

        sessions = []
        for f in sorted(transcript_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True):
            entries = TranscriptReader.load_transcript(f)
            if not entries:
                continue

            # Get session info from header
            header = entries[0] if entries else {}
            info = TranscriptReader.detect_interruption(entries)

            sessions.append({
                "session_id": header.get("session_id", f.stem),
                "project_dir": header.get("project_dir", str(project_dir)),
                "started_at": header.get("timestamp", ""),
                "event_count": len(entries),
                "interrupted": info["interrupted"],
                "last_phase": info["last_phase"],
                "last_turn": info["last_turn"],
                "tasks_done": info["tasks_done"],
                "tasks_total": info["tasks_total"],
                "file": str(f),
            })

        return sessions[:20]  # Last 20 sessions
