"""
Smart Orchestrator
==================

An intelligent Claude agent that dynamically manages a swarm of coding workers.
Replaces the static N-workers model with autonomous decision-making.

The orchestrator:
1. Analyzes the task list to determine optimal worker count
2. Spawns workers with clear file scopes (no overlap)
3. Monitors workers via the mail system
4. Reassigns tasks, spawns/terminates workers as needed
5. Controls merge order when workers complete
6. Reports progress via WebSocket events

The orchestrator itself is a Claude agent running via ClaudeSDKClient with
custom in-process MCP tools. Workers are background asyncio.Tasks running
standard Engine instances in isolated git worktrees.
"""

import asyncio
import json
import subprocess
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Awaitable, Callable, Optional

from claude_agent_sdk import ClaudeSDKClient
from claude_agent_sdk.types import StreamEvent
from claude_agent_sdk._errors import ProcessError, CLINotFoundError, CLIConnectionError

from core.engine import Engine, OnEventCallback
from core.paths import get_paths
from core.agent_roles import generate_overlay, write_overlay_to_worktree
from core.merge_resolver import MergeResolver
from core.orchestrator_tools import create_orchestrator_tool_server
from state.task_list import TaskList, TaskStatus
from state.mail import MailStore, MessageType
from state.budget import BudgetTracker
from features.steering import write_steering_message


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

from core.models import ORCHESTRATOR_MODEL, WORKER_MODEL

POLL_INTERVAL_S = 30          # seconds between re-prompting the orchestrator
MAX_WORKERS = 50              # safety ceiling — actual count driven by complexity analysis
CONTEXT_ROTATION_THRESHOLD = 50  # re-prompt count before rotating context
STAGGER_DELAY_S = 2           # seconds between worker spawns
WORKTREE_CREATION_TIMEOUT = 180  # seconds for git worktree add (large repos need more time)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class WorkerHandle:
    """Runtime state of a managed worker."""
    worker_id: int
    name: str
    engine: Engine
    task: asyncio.Task           # asyncio task running engine.run()
    worktree_path: str
    branch_name: str
    assigned_task_ids: list[str]
    file_scope: list[str]
    role: str = "builder"
    status: str = "running"       # running | completed | error | terminated | merged
    started_at: str = ""
    completed_at: str = ""
    merge_tier: str = ""
    # Activity tracking — updated live from worker_on_event
    last_tool_name: str = ""       # most recent tool call
    last_tool_time: str = ""       # ISO timestamp of last tool call
    tool_call_count: int = 0       # total tool calls so far
    git_commit_count: int = 0      # commits made on the worker branch
    tasks_done: int = 0            # tasks marked done in worker's task_list
    using_puppeteer: bool = False  # True if the last tool was a Puppeteer MCP call
    overlap_warning: str = ""     # file scope overlap warning with other workers

    def to_dict(self) -> dict:
        return {
            "worker_id": self.worker_id,
            "name": self.name,
            "status": self.status,
            "role": self.role,
            "assigned_task_ids": self.assigned_task_ids,
            "file_scope": self.file_scope,
            "worktree_path": self.worktree_path,
            "branch_name": self.branch_name,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "merge_tier": self.merge_tier,
        }


# ---------------------------------------------------------------------------
# Task Complexity Analyzer (pure Python — no LLM call)
# ---------------------------------------------------------------------------

class TaskComplexityAnalyzer:
    """Analyze a task list to recommend worker count and task grouping.

    Uses complexity scoring to avoid over-allocating workers for simple tasks.
    A single worker can comfortably handle ~30 complexity points:
      - simple task = 1 point  (e.g. 30 simple tasks → 1 worker)
      - moderate task = 3 points (e.g. 10 moderate tasks → 1 worker)
      - complex task = 5 points  (e.g. 6 complex tasks → 1 worker)
    """

    WORKER_CAPACITY = 30  # complexity points a single worker handles well

    # Keywords (matched case-insensitively against task title + description)
    _SIMPLE_KEYWORDS = {
        "css", "style", "styling", "color", "colour", "font", "padding",
        "margin", "border", "rename", "typo", "text", "label", "placeholder",
        "icon", "logo", "image", "alt", "title", "tooltip", "comment",
        "readme", "docs", "documentation", "lint", "format", "prettier",
    }
    _COMPLEX_KEYWORDS = {
        "auth", "authentication", "authorization", "oauth", "jwt", "database",
        "migration", "schema", "architecture", "refactor", "security",
        "encryption", "websocket", "real-time", "realtime", "payment",
        "stripe", "deploy", "ci/cd", "pipeline", "infrastructure",
        "microservice", "distributed", "cache", "caching", "queue",
        "concurrency", "thread", "async", "performance", "optimization",
    }

    def _classify_task(self, task) -> str:
        """Classify a single task as simple / moderate / complex."""
        text = f"{task.title or ''} {getattr(task, 'description', '') or ''}".lower()
        n_files = len(task.files_affected or [])
        n_deps = len(task.depends_on or [])

        # Complex indicators
        if n_files >= 6 or n_deps >= 3:
            return "complex"
        if any(kw in text for kw in self._COMPLEX_KEYWORDS):
            return "complex"

        # Simple indicators
        if n_files <= 2 and any(kw in text for kw in self._SIMPLE_KEYWORDS):
            return "simple"
        if n_files <= 1 and n_deps == 0:
            return "simple"

        return "moderate"

    _SCORES = {"simple": 1, "moderate": 3, "complex": 5}

    def analyze(self, task_list: TaskList, max_workers: int = MAX_WORKERS) -> dict:
        pending = [
            t for t in task_list.tasks
            if t.status in (TaskStatus.PENDING.value, TaskStatus.IN_PROGRESS.value)
        ]
        total = len(pending)
        if total == 0:
            return {"recommended_workers": 0, "reasoning": "No pending tasks",
                    "total_tasks": 0, "independent_groups": 0,
                    "max_dependency_chain": 0, "file_groups": [],
                    "complexity": {"simple": 0, "moderate": 0, "complex": 0,
                                   "total_score": 0}}

        # Structural analysis
        file_groups = self._group_by_file_overlap(pending)
        independent = len(file_groups)
        max_chain = self._longest_dependency_chain(pending, task_list)

        # Complexity analysis
        counts = {"simple": 0, "moderate": 0, "complex": 0}
        for t in pending:
            counts[self._classify_task(t)] += 1
        total_score = sum(counts[k] * self._SCORES[k] for k in counts)

        # Worker recommendation: complexity-driven, capped by structure
        from math import ceil
        complexity_rec = max(1, ceil(total_score / self.WORKER_CAPACITY))

        if total <= 2:
            rec = 1
            reason = f"{total} tasks — single worker is optimal"
        elif independent == 1:
            rec = min(2, total)
            reason = "All tasks share files — max 2 workers to minimise conflicts"
        else:
            # Take the LOWER of complexity-based and file-group-based recommendations
            rec = min(complexity_rec, independent, max_workers)
            reason = (
                f"{total} tasks ({counts['simple']}S/{counts['moderate']}M/"
                f"{counts['complex']}C, score {total_score}), "
                f"{independent} file groups, chain depth {max_chain}"
            )

        return {
            "recommended_workers": rec,
            "total_tasks": total,
            "independent_groups": independent,
            "max_dependency_chain": max_chain,
            "complexity": {
                "simple": counts["simple"],
                "moderate": counts["moderate"],
                "complex": counts["complex"],
                "total_score": total_score,
            },
            "file_groups": [
                {
                    "task_ids": [t.id for t in grp],
                    "files": sorted({f for t in grp for f in (t.files_affected or [])}),
                }
                for grp in file_groups
            ],
            "reasoning": reason,
        }

    # -- helpers --

    def _group_by_file_overlap(self, tasks: list) -> list[list]:
        """Union-Find grouping of tasks that share files."""
        parent: dict[str, str] = {t.id: t.id for t in tasks}
        task_map = {t.id: t for t in tasks}

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: str, b: str) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for i, t1 in enumerate(tasks):
            for t2 in tasks[i + 1:]:
                if set(t1.files_affected or []) & set(t2.files_affected or []):
                    union(t1.id, t2.id)

        groups: dict[str, list] = {}
        for t in tasks:
            root = find(t.id)
            groups.setdefault(root, []).append(t)
        return list(groups.values())

    def _longest_dependency_chain(self, tasks: list, task_list: TaskList) -> int:
        task_map = {t.id: t for t in task_list.tasks}
        memo: dict[str, int] = {}

        def depth(tid: str) -> int:
            if tid in memo:
                return memo[tid]
            task = task_map.get(tid)
            if not task or not task.depends_on:
                memo[tid] = 0
                return 0
            d = 1 + max((depth(dep) for dep in task.depends_on), default=0)
            memo[tid] = d
            return d

        return max((depth(t.id) for t in tasks), default=0)


# ---------------------------------------------------------------------------
# Smart Orchestrator
# ---------------------------------------------------------------------------

class SmartOrchestrator:
    """
    Intelligent orchestrator that runs as a Claude agent with custom tools.

    Lifecycle:
        1. Analyse task list complexity
        2. Start orchestrator ClaudeSDKClient session
        3. Poll loop: collect worker events → re-prompt orchestrator
        4. Orchestrator uses tools to manage workers
        5. On completion, merge all workers and clean up
    """

    def __init__(
        self,
        project_dir: Path,
        mode: str,
        model: str,
        task_input: str = "",
        max_workers: int = MAX_WORKERS,
        budget_limit: float = 0.0,
        max_hours: float = 0.0,
        phase_models: Optional[dict] = None,
        on_event: Optional[OnEventCallback] = None,
        steering_event: Optional[asyncio.Event] = None,
    ):
        self.project_dir = Path(project_dir)
        self.mode = mode
        self.model = model
        self.task_input = task_input
        self.max_workers = min(max_workers, MAX_WORKERS)
        self.budget_limit = budget_limit
        self.max_hours = max_hours
        self.phase_models = phase_models
        self._on_event = on_event or self._noop
        self._steering_event = steering_event or asyncio.Event()

        self._workers: dict[int, WorkerHandle] = {}
        self._next_worker_id = 1
        self._registry_path = self.project_dir / ".swarmweaver" / "swarm" / "worker_registry.json"
        self._stopped = False
        self._complete = False
        self._current_client = None  # ClaudeSDKClient — set during run() for steering
        self._decisions: list[dict] = []
        self._mail = MailStore(self.project_dir)
        self._merge_resolver = MergeResolver(self.project_dir)
        self._budget = BudgetTracker(self.project_dir)
        # MELS: Intra-session learning
        self._expertise_store = None
        self._lesson_synth = None
        try:
            from services.expertise_store import get_project_store
            from services.expertise_synthesis import SessionLessonSynthesizer
            self._expertise_store = get_project_store(self.project_dir)
            session_key = f"smart-swarm-{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}"
            self._lesson_synth = SessionLessonSynthesizer(self._expertise_store, session_key)
        except Exception:
            pass  # MELS not available, legacy lesson system used as fallback
        # Circuit breaker: stop spawning after N consecutive failures
        self._consecutive_spawn_failures = 0
        self._max_consecutive_failures = 3
        # Track startup time — only read mail sent AFTER this timestamp
        self._start_time: str = datetime.utcnow().isoformat() + "Z"

        # Persistent session database
        self._session_store = None
        self._persistent_session_id: Optional[str] = None
        try:
            from state.sessions import SessionStore
            self._session_store = SessionStore(self.project_dir)
            self._session_store.initialize()
        except Exception as e:
            print(f"[ORCHESTRATOR] SessionStore init failed (non-fatal): {e}", flush=True)

        # Pre-create swarm directory to avoid WSL/NTFS ghost-file issues
        swarm_dir = self.project_dir / ".swarmweaver" / "swarm"
        try:
            swarm_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass  # May already exist or be a ghost file — handled during spawn

        # LSP integration — per-worktree language servers
        self._lsp_manager = None
        self._lsp_health_task: Optional[asyncio.Task] = None
        try:
            from services.lsp_manager import LSPManager, LSPConfig
            lsp_config = LSPConfig.load(self.project_dir)
            if lsp_config.enabled:
                self._lsp_manager = LSPManager(
                    self.project_dir, lsp_config, on_event=self._emit_sync
                )
                # Register with API state so REST endpoints can access it
                try:
                    from api.state import set_lsp_manager
                    set_lsp_manager(str(self.project_dir), self._lsp_manager)
                except ImportError:
                    pass  # API module may not be loaded in CLI-only mode
                print("[ORCHESTRATOR] LSP manager initialized", flush=True)
        except Exception as e:
            print(f"[ORCHESTRATOR] LSP init failed (non-fatal): {e}", flush=True)

        # Enhanced watchdog (W4-4)
        self._watchdog = None
        self._watchdog_task: Optional[asyncio.Task] = None
        try:
            from services.watchdog import SwarmWatchdog, WatchdogConfig
            watchdog_config = WatchdogConfig.load(self.project_dir)
            if watchdog_config.enabled:
                self._watchdog = SwarmWatchdog(
                    config=watchdog_config,
                    mail_store=self._mail,
                    project_dir=self.project_dir,
                    on_event=self._on_watchdog_event,
                )
                # Orchestrator manages completion via signal_complete —
                # don't let watchdog fire premature run_complete events.
                self._watchdog._auto_run_complete = False
        except Exception as e:
            print(f"[ORCHESTRATOR] Watchdog init failed (non-fatal): {e}", flush=True)

    @staticmethod
    async def _noop(event: dict) -> None:
        pass

    def _emit_sync(self, event: dict) -> None:
        """Fire-and-forget emit (for callbacks that can't be async)."""
        import asyncio as _aio
        try:
            if "timestamp" not in event:
                event["timestamp"] = datetime.utcnow().isoformat() + "Z"
            loop = _aio.get_running_loop()
            loop.create_task(self._on_event(event))
        except RuntimeError:
            pass

    def _save_worker_registry(self) -> None:
        """Persist worker state to disk AND transcript for resume capability."""
        try:
            self._registry_path.parent.mkdir(parents=True, exist_ok=True)
            registry = {
                "next_worker_id": self._next_worker_id,
                "workers": {}
            }
            active_workers = []
            for wid, handle in self._workers.items():
                wdata = {
                    "id": wid,
                    "name": getattr(handle, "name", f"worker-{wid}"),
                    "task_ids": list(getattr(handle, "assigned_task_ids", [])),
                    "worktree_path": str(getattr(handle, "worktree_path", "")),
                    "branch": getattr(handle, "branch_name", f"swarm/worker-{wid}"),
                    "status": handle.status if hasattr(handle, "status") else "unknown",
                }
                registry["workers"][str(wid)] = wdata
                if wdata["status"] in ("running", "starting"):
                    active_workers.append(wdata)
            self._registry_path.write_text(json.dumps(registry, indent=2), encoding="utf-8")

            # Also write orchestrator state to the unified transcript
            try:
                from services.transcript import TranscriptReader
                transcript_dir = self.project_dir / ".swarmweaver" / "transcripts"
                if transcript_dir.is_dir():
                    transcripts = sorted(transcript_dir.glob("*.jsonl"),
                                         key=lambda p: p.stat().st_mtime, reverse=True)
                    if transcripts:
                        # Append to the latest transcript
                        import time
                        from datetime import datetime
                        entry = {
                            "type": "orchestrator_state",
                            "num_workers": len(self._workers),
                            "active_workers": [{"id": w["id"], "name": w["name"],
                                                "task_ids": w["task_ids"], "status": w["status"],
                                                "worktree_path": w["worktree_path"],
                                                "branch": w["branch"]}
                                               for w in registry["workers"].values()],
                            "next_worker_id": self._next_worker_id,
                            "timestamp": datetime.now().isoformat(),
                        }
                        with open(transcripts[0], "a", encoding="utf-8") as f:
                            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
                            f.flush()
            except Exception:
                pass
        except Exception:
            pass

    def _load_worker_registry(self) -> dict:
        """Load worker registry from disk, falling back to transcript if missing."""
        # Try registry file first (fast path)
        if self._registry_path.exists():
            try:
                data = json.loads(self._registry_path.read_text(encoding="utf-8"))
                if data.get("workers"):
                    return data
            except (json.JSONDecodeError, OSError):
                pass

        # Fallback: rebuild from transcript (single source of truth)
        try:
            from services.transcript import TranscriptReader
            transcript_dir = self.project_dir / ".swarmweaver" / "transcripts"
            if transcript_dir.is_dir():
                transcripts = sorted(transcript_dir.glob("*.jsonl"),
                                     key=lambda p: p.stat().st_mtime, reverse=True)
                if transcripts:
                    entries = TranscriptReader.load_transcript(transcripts[0])
                    info = TranscriptReader.detect_interruption(entries)
                    workers = info.get("workers", {})
                    if workers:
                        # Rebuild registry from transcript
                        max_id = max(workers.keys()) if workers else 0
                        return {
                            "next_worker_id": max_id + 1,
                            "workers": {str(k): v for k, v in workers.items()},
                        }
        except Exception:
            pass

        return {}

    def _on_watchdog_event(self, event: dict) -> None:
        """Forward watchdog events to the main on_event callback."""
        import asyncio as _aio
        try:
            if "timestamp" not in event:
                event["timestamp"] = datetime.utcnow().isoformat() + "Z"
            loop = _aio.get_running_loop()
            loop.create_task(self._on_event(event))
        except RuntimeError:
            pass

    async def emit(self, event: dict) -> None:
        if "timestamp" not in event:
            event["timestamp"] = datetime.utcnow().isoformat() + "Z"
        try:
            await self._on_event(event)
        except Exception as e:
            print(f"[WARNING] emit() callback failed: {e}", flush=True)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Main orchestration loop."""
        try:
            await self.emit({"type": "status", "data": "running"})
            await self.emit({"type": "swarm_status", "data": {"phase": "orchestrating"}})
            # Emit session_start immediately so frontend timer begins
            await self.emit({
                "type": "session_start",
                "data": {
                    "session": 1,
                    "phase": "orchestrating",
                    "model": self.model,
                    "start_time": self._start_time,
                },
            })

            self._mail.initialize()

            # Create persistent session record
            if self._session_store:
                try:
                    self._persistent_session_id = self._session_store.create_session(
                        mode=self.mode,
                        model=self.model,
                        task_input=self.task_input,
                        is_team=True,
                        agent_count=self.max_workers,
                    )
                    await self.emit({
                        "type": "session_db_created",
                        "data": {"session_id": self._persistent_session_id},
                    })
                except Exception as e:
                    print(f"[ORCHESTRATOR] Session record creation failed: {e}", flush=True)

            # Wire WebSocket push for mail events (M2-1)
            def _mail_push(msg):
                import asyncio as _aio
                try:
                    loop = _aio.get_running_loop()
                    loop.create_task(self.emit({"type": "mail_received", "data": msg.to_dict()}))
                except RuntimeError:
                    pass
            self._mail.on_send = _mail_push
            # Clear any stale messages from previous runs
            self._mail.mark_all_read("orchestrator")
            print(f"[ORCHESTRATOR] Cleared stale mail. Start time: {self._start_time}", flush=True)

            # Start watchdog monitoring loop (W4-4)
            if self._watchdog:
                self._watchdog_task = asyncio.create_task(self._watchdog.run())
                print("[ORCHESTRATOR] Watchdog monitoring started", flush=True)

            # Start LSP health monitoring loop
            if self._lsp_manager:
                self._lsp_health_task = asyncio.create_task(
                    self._lsp_manager.run_health_loop()
                )
                print("[ORCHESTRATOR] LSP health loop started", flush=True)

            # ── RESUME: recover state from previous workers BEFORE loading tasks ──
            registry = self._load_worker_registry()
            _is_resume = bool(registry and registry.get("workers"))

            if _is_resume:
                self._next_worker_id = registry.get("next_worker_id", 1)
                print(f"[ORCHESTRATOR] RESUME detected — {len(registry['workers'])} previous workers found", flush=True)

                # Step 1: Merge each worker's git branch into main (code changes)
                for wid_str, wdata in registry["workers"].items():
                    branch = wdata.get("branch", f"swarm/worker-{wid_str}")
                    name = wdata.get("name", f"worker-{wid_str}")
                    try:
                        self._git("merge", branch, "--no-edit", "--no-ff")
                        print(f"[ORCHESTRATOR] Merged git branch from {name}", flush=True)
                    except Exception as e:
                        # Merge conflict or branch doesn't exist — try fast-forward
                        try:
                            self._git("merge", branch, "--no-edit")
                            print(f"[ORCHESTRATOR] Fast-forward merged {name}", flush=True)
                        except Exception:
                            print(f"[ORCHESTRATOR] Could not merge {name} ({branch}): {e}", flush=True)

                # Step 2: Sync task_list.json from worker worktrees into main
                # Workers write task_list.json to their worktrees, not main.
                # We need to collect task statuses from all worktrees.
                main_tl = TaskList(self.project_dir)
                main_tl.load()
                merged_statuses = 0

                for wid_str, wdata in registry["workers"].items():
                    wt_path = Path(wdata.get("worktree_path", ""))
                    wt_task_file = wt_path / ".swarmweaver" / "task_list.json"
                    if wt_task_file.exists():
                        try:
                            worker_tl = TaskList(wt_path)
                            worker_tl.load()
                            # Merge: if worker says a task is "done", update main
                            for wtask in (worker_tl.tasks if hasattr(worker_tl, "tasks") else []):
                                task_id = getattr(wtask, "id", None) or getattr(wtask, "task_id", None)
                                task_status = getattr(wtask, "status", None)
                                if task_id and task_status in ("done", "verified"):
                                    for mtask in (main_tl.tasks if hasattr(main_tl, "tasks") else []):
                                        mid = getattr(mtask, "id", None) or getattr(mtask, "task_id", None)
                                        if mid == task_id and getattr(mtask, "status", "") != task_status:
                                            mtask.status = task_status
                                            merged_statuses += 1
                        except Exception as e:
                            print(f"[ORCHESTRATOR] Could not read tasks from {wt_path}: {e}", flush=True)

                if merged_statuses > 0:
                    main_tl.save()
                    print(f"[ORCHESTRATOR] Synced {merged_statuses} task statuses from worker worktrees to main", flush=True)

            # ── NOW load tasks (after merge, so we see the real state) ──
            tl = TaskList(self.project_dir)
            tl.load()

            done_count = sum(1 for t in (tl.tasks if hasattr(tl, "tasks") else [])
                            if getattr(t, "status", "") in ("done", "verified"))
            total_count = len(tl.tasks if hasattr(tl, "tasks") else [])
            pending_count = total_count - done_count
            print(f"[ORCHESTRATOR] Tasks: {done_count} done, {pending_count} pending, {total_count} total", flush=True)

            analysis = TaskComplexityAnalyzer().analyze(tl, self.max_workers)
            print(f"[ORCHESTRATOR] Analysis: {analysis['recommended_workers']} workers recommended — {analysis['reasoning']}", flush=True)
            await self.emit({"type": "orchestrator_analysis", "data": analysis})

            if analysis["recommended_workers"] == 0:
                print("[ORCHESTRATOR] No pending tasks. Completing.", flush=True)
                await self.emit({"type": "status", "data": "completed"})
                return

            # Create orchestrator agent client
            print(f"[ORCHESTRATOR] Creating tool server and Opus client...", flush=True)
            tool_server = create_orchestrator_tool_server(self)

            initial_prompt = self._build_initial_prompt(tl, analysis)

            print(f"[ORCHESTRATOR] Sending initial prompt ({len(initial_prompt)} chars) to Opus...", flush=True)
            max_retries = 2
            for attempt in range(max_retries + 1):
                try:
                    client = self._create_orchestrator_client(tool_server)
                    self._current_client = client
                    async with client:
                        # Single continuous query — the orchestrator stays connected
                        # and uses wait_seconds() to pace itself between monitoring checks.
                        # Worker events continue streaming to the frontend during waits.
                        await client.query(initial_prompt)
                        print("[ORCHESTRATOR] Waiting for Opus response...", flush=True)
                        await self._process_response(client)
                        print(f"[ORCHESTRATOR] Session done. Workers: {len(self._workers)}, Complete: {self._complete}", flush=True)
                    break  # success
                except CLINotFoundError:
                    print("[ORCHESTRATOR] FATAL: Claude CLI not found", flush=True)
                    break
                except (ProcessError, CLIConnectionError) as e:
                    if attempt < max_retries:
                        delay = 5 * (attempt + 1)
                        print(f"[ORCHESTRATOR] SDK error (attempt {attempt+1}), retrying in {delay}s: {e}", flush=True)
                        await asyncio.sleep(delay)
                        continue
                    print(f"[ORCHESTRATOR] SDK error after {max_retries+1} attempts: {e}", flush=True)
                except Exception as e:
                    print(f"[ORCHESTRATOR] Unexpected error: {e}", flush=True)
                    break

            # Complete persistent session record
            final_status = "stopped" if self._stopped else "completed"
            if self._session_store and self._persistent_session_id:
                try:
                    self._session_store.complete_session(
                        self._persistent_session_id, status=final_status
                    )
                    self._session_store.compute_change_summary(
                        self._persistent_session_id
                    )
                    self._session_store.sync_to_global(self._persistent_session_id)
                    await self.emit({
                        "type": "session_db_completed",
                        "data": {
                            "session_id": self._persistent_session_id,
                            "status": final_status,
                        },
                    })
                except Exception as e:
                    print(f"[ORCHESTRATOR] Session completion failed: {e}", flush=True)

            # Emit status BEFORE cleanup so the WebSocket is still alive when
            # the notification reaches the frontend.  Cleanup uses blocking I/O
            # (subprocess git commands + shutil.rmtree) which would stall the
            # event loop and cause ECONNRESET on in-flight polling requests.
            await self.emit({"type": "status", "data": final_status})

            # Cleanup runs after status is delivered
            await self._cleanup()

        except Exception as e:
            # Mark persistent session as error
            if self._session_store and self._persistent_session_id:
                try:
                    self._session_store.complete_session(
                        self._persistent_session_id,
                        status="error",
                        error_message=str(e)[:500],
                    )
                    self._session_store.sync_to_global(self._persistent_session_id)
                except Exception:
                    pass

            if self._stopped:
                await self.emit({"type": "status", "data": "stopped"})
            else:
                await self.emit({
                    "type": "error",
                    "data": f"Orchestrator error: {e}\n{traceback.format_exc()}",
                })

    # ------------------------------------------------------------------
    # SDK Client Creation
    # ------------------------------------------------------------------

    def _create_orchestrator_client(self, tool_server) -> ClaudeSDKClient:
        """Create a ClaudeSDKClient configured for the orchestrator agent."""
        from core.client import create_orchestrator_client
        return create_orchestrator_client(self.project_dir, tool_server)

    # ------------------------------------------------------------------
    # Response Processing
    # ------------------------------------------------------------------

    async def _process_response(self, client: ClaudeSDKClient) -> None:
        """
        Stream all orchestrator output to the frontend.

        Handles every message type from ClaudeSDKClient.receive_response():
        - StreamEvent: real-time text deltas and tool call streaming
        - AssistantMessage: complete blocks (fallback if streaming missed)
        - UserMessage: tool results from MCP tool calls
        - ResultMessage: session completion
        """
        from claude_agent_sdk.types import StreamEvent

        # Track active tool calls for streaming
        current_tool_name: str | None = None
        current_tool_id: str | None = None
        streamed_tool_ids: set[str] = set()
        # Track accumulated text for dedup (don't re-emit from AssistantMessage
        # if StreamEvent already streamed it character by character)
        streamed_text_ids: set[str] = set()

        try:
            async for msg in client.receive_response():
                if self._stopped:
                    break
                msg_type = type(msg).__name__

                # ── StreamEvent: real-time token-level streaming ──
                if isinstance(msg, StreamEvent):
                    event = msg.event
                    etype = event.get("type", "")

                    if etype == "content_block_start":
                        block = event.get("content_block", {})
                        if block.get("type") == "tool_use":
                            current_tool_name = block.get("name", "unknown")
                            current_tool_id = block.get("id", "")
                            streamed_tool_ids.add(current_tool_id)
                            print(f"[ORCHESTRATOR TOOL START] {current_tool_name}", flush=True)
                            await self.emit({
                                "type": "tool_start",
                                "tool": current_tool_name,
                                "id": current_tool_id,
                                # no worker_id = orchestrator event
                            })
                        elif block.get("type") == "text":
                            streamed_text_ids.add(event.get("index", ""))

                    elif etype == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta":
                            text = delta.get("text", "")
                            if text:
                                await self.emit({
                                    "type": "text_delta",
                                    "text": text,
                                    # no worker_id = orchestrator
                                })
                        elif delta.get("type") == "input_json_delta":
                            chunk = delta.get("partial_json", "")
                            if chunk and current_tool_id:
                                await self.emit({
                                    "type": "tool_input_delta",
                                    "id": current_tool_id,
                                    "chunk": chunk,
                                })

                    elif etype == "content_block_stop":
                        # Do NOT emit tool_done here — that fires when the assistant
                        # finishes the tool block, not when execution completes.
                        # tool_done is emitted only when we have ToolResultBlock.
                        if current_tool_name:
                            current_tool_name = None
                            current_tool_id = None

                # ── AssistantMessage: complete content (fallback/confirmation) ──
                elif msg_type == "AssistantMessage" and hasattr(msg, "content"):
                    for block in msg.content:
                        btype = type(block).__name__
                        if btype == "TextBlock" and hasattr(block, "text"):
                            # Only emit if StreamEvent didn't already stream it
                            # (StreamEvent streams delta-by-delta; AssistantMessage is the full text)
                            # We check: if we got any text_delta StreamEvents, skip (already shown)
                            # If no streaming happened (non-streaming mode), emit now
                            if not streamed_text_ids:
                                print(f"[ORCHESTRATOR TEXT] {block.text[:200]}", flush=True)
                                await self.emit({
                                    "type": "orchestrator_text",
                                    "data": block.text,
                                })
                        elif btype == "ToolUseBlock" and hasattr(block, "name"):
                            tool_id = getattr(block, "id", "")
                            tool_name = block.name
                            print(f"[ORCHESTRATOR TOOL] {tool_name}", flush=True)
                            # Emit tool_start if streaming didn't already
                            if tool_id not in streamed_tool_ids:
                                await self.emit({
                                    "type": "tool_start",
                                    "tool": tool_name,
                                    "id": tool_id,
                                })
                            # Always emit complete input
                            tool_input = getattr(block, "input", {})
                            if tool_input:
                                await self.emit({
                                    "type": "tool_input_complete",
                                    "id": tool_id,
                                    "tool": tool_name,
                                    "input": json.dumps(tool_input, ensure_ascii=False)[:5000],
                                })
                        elif btype == "ThinkingBlock" and hasattr(block, "thinking"):
                            thinking = block.thinking
                            if thinking and len(thinking) > 10:
                                await self.emit({
                                    "type": "thinking_block",
                                    "data": {
                                        "text": thinking,
                                        "truncated": False,
                                        "agent": "orchestrator",
                                    },
                                })

                # ── UserMessage: tool results (MCP tool call responses) ──
                elif msg_type == "UserMessage" and hasattr(msg, "content"):
                    content = msg.content
                    if not isinstance(content, str):
                        for block in content:
                            btype = type(block).__name__
                            if btype == "ToolResultBlock":
                                tool_use_id = getattr(block, "tool_use_id", "")
                                result_content = getattr(block, "content", "")
                                is_error = getattr(block, "is_error", False)
                                if is_error:
                                    await self.emit({
                                        "type": "tool_error",
                                        "id": tool_use_id,
                                        "error": str(result_content)[:500],
                                    })
                                else:
                                    await self.emit({
                                        "type": "tool_result",
                                        "id": tool_use_id,
                                        "status": "success",
                                        "content": str(result_content)[:2000],
                                    })
                                # Always emit tool_done when we have the result
                                await self.emit({
                                    "type": "tool_done",
                                    "id": tool_use_id,
                                    "tool": "",
                                })

                # ── ResultMessage: session complete ──
                elif msg_type == "ResultMessage":
                    print(f"[ORCHESTRATOR DONE] session complete", flush=True)
                    # Emit a phase marker so the feed shows a clear boundary
                    await self.emit({
                        "type": "orchestrator_decision",
                        "data": {
                            "action": "turn complete",
                            "details": "",
                        },
                    })

        except Exception as e:
            print(f"[ORCHESTRATOR ERROR] _process_response: {e}\n{traceback.format_exc()}", flush=True)

    # ------------------------------------------------------------------
    # Tool Handlers (called from orchestrator_tools.py closures)
    # ------------------------------------------------------------------

    async def _broadcast_budget_stop(self, reason: str) -> None:
        """Stop all running workers when budget is exceeded."""
        for wid, handle in self._workers.items():
            if handle.status == "running":
                try:
                    handle.engine.stop()
                except Exception:
                    pass
        self._stopped = True
        await self.emit({"type": "budget_stop_broadcast", "data": {"reason": reason}})
        print(f"[ORCHESTRATOR] Budget stop broadcast: {reason}", flush=True)

    async def _tool_spawn_worker(self, args: dict) -> dict:
        """Spawn a new worker Engine in a git worktree."""
        task_ids = args.get("task_ids", [])
        file_scope = list(args.get("file_scope", []))
        role = args.get("role", "builder")
        per_task_instructions = args.get("per_task_instructions") or {}
        # Track last-seen task statuses for change detection in worker_on_event
        _last_task_statuses: dict[str, str] = {}

        if not task_ids:
            return {"success": False, "error": "No task_ids provided"}

        # Enhanced watchdog circuit breaker check (W4-4)
        if self._watchdog and self._watchdog.config.circuit_breaker_enabled:
            can_spawn, cb_reason = self._watchdog.circuit_breaker.can_spawn()
            if not can_spawn:
                await self.emit({"type": "watchdog_circuit_breaker",
                                 "data": self._watchdog.circuit_breaker.get_status()})
                return {"success": False, "error": f"Circuit breaker: {cb_reason}"}

        # Circuit breaker: stop spawning after repeated failures
        if self._consecutive_spawn_failures >= self._max_consecutive_failures:
            return {
                "success": False,
                "error": f"Circuit breaker: {self._consecutive_spawn_failures} consecutive spawn failures. "
                         "Investigate before spawning more workers."
            }

        # Only count active (running) workers against the cap
        active_count = sum(1 for w in self._workers.values() if w.status == "running")
        if active_count >= self.max_workers:
            return {"success": False, "error": f"Max active workers ({self.max_workers}) reached"}

        # Early load task list to derive file_scope and validate overlap before creating worktree
        paths_main = get_paths(self.project_dir)
        filtered_tasks_early = []
        if paths_main.task_list.exists():
            try:
                tl_data = json.loads(paths_main.task_list.read_text(encoding="utf-8"))
                all_tasks = tl_data.get("tasks", []) if isinstance(tl_data, dict) else tl_data
                assigned = {tid for tid in task_ids}
                filtered_tasks_early = [
                    t for t in all_tasks
                    if isinstance(t, dict) and t.get("id") in assigned
                ]
                if not file_scope and filtered_tasks_early:
                    derived = []
                    for t in filtered_tasks_early:
                        if isinstance(t, dict):
                            derived.extend(t.get("files_affected") or [])
                    if derived:
                        file_scope = sorted(set(derived))
            except Exception as e:
                print(f"[WARNING] File scope derivation failed: {e}", flush=True)

        # File scope overlap validation — block spawn if overlap with active workers
        if file_scope:
            file_set = set(file_scope)
            for w in self._workers.values():
                if w.status != "running":
                    continue
                other_set = set(w.file_scope or [])
                overlap = file_set & other_set
                if overlap:
                    return {
                        "success": False,
                        "error": (
                            f"file_scope overlaps with {w.name}: {list(overlap)[:5]}. "
                            "Use non-overlapping file groups. Group tasks that share files into the SAME worker."
                        ),
                    }

        worker_id = self._next_worker_id
        self._next_worker_id += 1
        name = f"worker-{worker_id}"

        # Pre-allocate ports for this worker (avoids race when multiple workers start servers)
        try:
            from state.port_allocations import allocate_ports_for_worker
            ports = allocate_ports_for_worker(self.project_dir, worker_id)
            print(f"[WORKER {name}] allocated ports: backend={ports['backend']} frontend={ports['frontend']}", flush=True)
        except Exception as e:
            print(f"[WORKER {name}] port allocation failed: {e}", flush=True)

        # Pre-spawn check: if node_modules is tracked, auto-fix before worktree creation
        ok, out = self._git("ls-files", "node_modules", timeout=10)
        if ok and out.strip():
            # node_modules is tracked — auto-remove from index
            print(f"[ORCHESTRATOR] node_modules tracked in git — auto-removing before spawn", flush=True)
            ok_rm, out_rm = self._git("rm", "-r", "--cached", "node_modules", timeout=120)
            if ok_rm:
                self._git("commit", "-m", "chore: Remove node_modules from git tracking", timeout=30)
            else:
                return {
                    "success": False,
                    "error": (
                        "node_modules is tracked in git. Run `git rm -r --cached node_modules` "
                        "and commit before spawning workers. Worktree creation times out when node_modules is tracked."
                    ),
                }

        # Create worktree
        branch = f"swarm/{name}"
        swarm_dir = get_paths(self.project_dir).swarm_dir
        swarm_dir.mkdir(parents=True, exist_ok=True)
        worktree_path = swarm_dir / name

        try:
            # Only remove worktree if it's not from a recent run (check registry)
            registry = self._load_worker_registry()
            existing_workers = registry.get("workers", {}) if registry else {}
            worktree_in_registry = any(
                w.get("worktree_path") == str(worktree_path)
                for w in existing_workers.values()
            )

            if worktree_path.exists() and not worktree_in_registry:
                # Stale worktree from a previous unregistered run - safe to remove
                try:
                    self._git("worktree", "remove", "--force", str(worktree_path))
                except Exception:
                    pass
            elif worktree_path.exists() and worktree_in_registry:
                # Worktree from a registered worker - merge its changes first
                try:
                    self._git("merge", branch, "--no-edit", "--no-ff")
                except Exception:
                    pass
                try:
                    self._git("worktree", "remove", "--force", str(worktree_path))
                except Exception:
                    pass
            self._git("branch", "-D", branch)

            ok, output = self._git(
                "worktree", "add", "-b", branch, str(worktree_path),
                timeout=WORKTREE_CREATION_TIMEOUT,
            )
            if not ok:
                err_msg = output
                if "timed out" in str(output).lower() or "timeout" in str(output).lower():
                    err_msg = (
                        f"Git worktree creation timed out ({WORKTREE_CREATION_TIMEOUT}s). "
                        "The repository may be very large (e.g. node_modules tracked). "
                        "Check with `git ls-files node_modules | wc -l` and run "
                        "`git rm -r --cached node_modules` if needed."
                    )
                return {"success": False, "error": err_msg}
        except Exception as e:
            return {"success": False, "error": str(e)}

        # Build lessons context from previous worker errors
        lessons_context = self._build_lessons_context(task_ids, file_scope)

        # Write agent overlay to worktree
        try:
            write_overlay_to_worktree(
                worktree_path=worktree_path,
                role=role,
                worker_id=worker_id,
                task_ids=task_ids,
                file_scope=file_scope,
                branch_name=branch,
                mode=self.mode,
                task_input=self.task_input,
                task_instructions=per_task_instructions,
                lessons_context=lessons_context,
            )
        except Exception as e:
            print(f"[WARNING] Overlay write failed: {e}", flush=True)

        # Copy FILTERED task list and codebase profile to worktree.
        # - Filtered task list: worker only sees its assigned tasks (prevents scope creep)
        # - Codebase profile: skip the analyze phase (saves cost, avoids unexpected behavior)
        paths_main = get_paths(self.project_dir)
        filtered_tasks = []
        try:
            src_tl = paths_main.task_list
            if src_tl.exists():
                tl_data = json.loads(src_tl.read_text(encoding="utf-8"))
                all_tasks = tl_data.get("tasks", []) if isinstance(tl_data, dict) else tl_data
                # Filter to only assigned tasks — worker stops when THESE are done
                assigned = {tid for tid in task_ids}
                filtered_tasks = [
                    t for t in all_tasks
                    if isinstance(t, dict) and t.get("id") in assigned
                ]
                filtered_data = {
                    **(tl_data if isinstance(tl_data, dict) else {}),
                    "tasks": filtered_tasks,
                }
                dst_dir = worktree_path / ".swarmweaver"
                dst_dir.mkdir(parents=True, exist_ok=True)
                (dst_dir / "task_list.json").write_text(
                    json.dumps(filtered_data, indent=2), encoding="utf-8"
                )
                print(f"[WORKER {name}] task_list filtered to {len(filtered_tasks)} tasks: {task_ids}", flush=True)
                # Prime last-seen statuses so we can detect transitions
                for t in filtered_tasks:
                    if isinstance(t, dict) and t.get("id"):
                        _last_task_statuses[t["id"]] = t.get("status", "pending")
        except Exception as e:
            print(f"[WORKER {name}] task_list copy failed: {e}", flush=True)

        # Reset progress file in worktree so worker starts fresh
        try:
            worktree_progress = worktree_path / ".swarmweaver" / "claude-progress.txt"
            if worktree_progress.exists():
                worktree_progress.write_text(
                    f"# Worker {name} starting fresh\n# Assigned tasks: {', '.join(task_ids)}\n",
                    encoding="utf-8",
                )
        except Exception as e:
            print(f"[WARNING] Progress file reset failed: {e}", flush=True)

        # Mark worktree as swarm worker (enables PreToolUse hook to block direct task_list access)
        try:
            swarm_marker = worktree_path / ".swarmweaver" / "swarm_worker"
            swarm_marker.parent.mkdir(parents=True, exist_ok=True)
            swarm_marker.write_text(f"worker-{worker_id}\n", encoding="utf-8")
        except Exception as e:
            print(f"[WARNING] Swarm marker write failed: {e}", flush=True)

        # Auto-derive file_scope from tasks' files_affected if the orchestrator didn't provide one.
        # This ensures workers can only write files that belong to their assigned tasks.
        if not file_scope and filtered_tasks:
            derived = []
            for t in filtered_tasks:
                if isinstance(t, dict):
                    derived.extend(t.get("files_affected") or [])
            if derived:
                file_scope = sorted(set(derived))
                print(f"[WORKER {name}] auto-derived file_scope from tasks: {file_scope[:10]}", flush=True)

        # Copy codebase_profile.json so the analyze phase is skipped.
        # The worktree is a checkout of the same codebase — profile is accurate.
        try:
            src_cp = paths_main.codebase_profile
            if src_cp.exists():
                dst_dir = worktree_path / ".swarmweaver"
                dst_dir.mkdir(parents=True, exist_ok=True)
                (dst_dir / "codebase_profile.json").write_text(
                    src_cp.read_text(encoding="utf-8"), encoding="utf-8"
                )
                print(f"[WORKER {name}] codebase_profile copied — analyze phase will be skipped", flush=True)
        except Exception as e:
            print(f"[WORKER {name}] codebase_profile copy failed (analyze will run): {e}", flush=True)

        # Build a focused task brief (only assigned tasks, not full app spec)
        from core.swarm import build_worker_task_brief
        worker_task_input = build_worker_task_brief(
            task_ids,
            self.project_dir,
            fallback_input=self.task_input,
            task_instructions=per_task_instructions,
        )

        # Worker budget = total / active+1
        active_count = len([w for w in self._workers.values() if w.status == "running"])
        per_worker_budget = (
            self.budget_limit / max(active_count + 1, 1)
            if self.budget_limit > 0 else 0.0
        )

        # Create worker on_event callback
        _tool_call_count = [0]  # mutable counter captured by closure

        async def worker_on_event(event: dict) -> None:
            event["worker_id"] = worker_id
            etype = event.get("type", "")

            # Never forward worker-level "status" events — they would
            # cause the frontend to treat a single worker finishing as
            # the entire run completing.  Re-label them so the UI can
            # distinguish worker lifecycle from orchestrator lifecycle.
            if etype == "status":
                await self.emit({
                    "type": "worker_status",
                    "worker_id": worker_id,
                    "data": event.get("data"),
                })
            else:
                await self.emit(event)
            evdata = event.get("data", {}) if isinstance(event.get("data"), dict) else {}

            # Report activity to watchdog (W4-4)
            if self._watchdog:
                self._watchdog.report_activity(worker_id)
                if etype in ("output", "text_delta"):
                    output_text = str(event.get("data", ""))
                    self._watchdog.report_output(worker_id, output_text)
                elif etype == "tool_start":
                    tool_name = evdata.get("tool", "")
                    self._watchdog.report_tool_activity(worker_id, tool_name)

            # ── Live activity tracking ──
            if etype == "tool_start":
                h = self._workers.get(worker_id)
                if h:
                    tool_name = evdata.get("tool", "")
                    h.last_tool_name = tool_name
                    h.last_tool_time = event.get("timestamp", "")
                    h.using_puppeteer = "puppeteer" in tool_name.lower() or "playwright" in tool_name.lower()

            if etype == "session_error":
                # session_error may have data nested or flat
                error_msg = str(
                    event.get("data", {}).get("error", "")
                    or event.get("error", "")
                )[:500]
                self._mail.send(
                    sender=name, recipient="orchestrator",
                    msg_type=MessageType.ERROR.value,
                    subject=f"Worker {name} session error",
                    body=error_msg,
                )
                # Record error for self-learning
                self._record_worker_error(
                    worker_id=worker_id, worker_name=name,
                    tool_name=event.get("tool", "") or evdata.get("tool", ""),
                    error_message=error_msg,
                )
                # Self-correction: check if a lesson matches this error
                self._try_self_correction(worker_id, error_msg, worktree_path)

            elif etype == "tool_error":
                # tool_error events are flat (not nested under "data")
                tool_err_msg = str(event.get("error", "") or evdata.get("error", ""))[:500]
                tool_err_name = event.get("tool", "") or evdata.get("tool_name", "") or evdata.get("tool", "")
                # Fall back to last known tool name from activity tracking
                if not tool_err_name:
                    h = self._workers.get(worker_id)
                    if h:
                        tool_err_name = h.last_tool_name
                self._record_worker_error(
                    worker_id=worker_id, worker_name=name,
                    tool_name=tool_err_name,
                    error_message=tool_err_msg,
                    file_path=str(event.get("file_path", "") or evdata.get("file_path", "")),
                    task_id=str(event.get("task_id", "") or evdata.get("task_id", "")),
                )
                # Self-correction: check if a lesson matches this error
                self._try_self_correction(worker_id, tool_err_msg, worktree_path)

            elif etype == "session_result":
                # Record per-worker turn in persistent session database
                if self._session_store and self._persistent_session_id:
                    try:
                        self._session_store.record_message(
                            session_id=self._persistent_session_id,
                            agent_name=name,
                            phase=evdata.get("phase", ""),
                            role="assistant",
                            content_summary=f"Worker {name} {evdata.get('status', 'unknown')} (phase: {evdata.get('phase', '')})",
                            input_tokens=evdata.get("input_tokens", 0),
                            output_tokens=evdata.get("output_tokens", 0),
                            cost_usd=evdata.get("total_cost_usd", 0.0),
                            model=evdata.get("model", self.model),
                            turn_number=evdata.get("session", 0),
                            duration_ms=int(evdata.get("duration_s", 0) * 1000),
                        )
                    except Exception as _db_err:
                        print(f"[ORCHESTRATOR] Worker message recording failed: {_db_err}", flush=True)

            elif etype == "budget_exceeded":
                asyncio.create_task(self._broadcast_budget_stop(
                    evdata.get("reason", "Worker budget exceeded")
                ))

            elif etype == "task_list_update":
                # Detect individual task status transitions and report them
                data = event.get("data", {})
                tasks = data.get("tasks", []) if isinstance(data, dict) else []
                done = len([t for t in tasks if isinstance(t, dict) and t.get("status") == "done"])
                total = len(tasks)

                # Detect transitions: find tasks whose status changed
                transitions = []
                for t in tasks:
                    if not isinstance(t, dict):
                        continue
                    tid = t.get("id", "")
                    new_status = t.get("status", "")
                    old_status = _last_task_statuses.get(tid)
                    if old_status and old_status != new_status:
                        transitions.append(f"{tid}: {old_status} → {new_status} ({t.get('title', '')})")
                    _last_task_statuses[tid] = new_status

                if transitions:
                    self._mail.send(
                        sender=name, recipient="orchestrator",
                        msg_type=MessageType.WORKER_PROGRESS.value,
                        subject=f"Worker {name} task update: {'; '.join(transitions)}",
                        body=json.dumps({
                            "worker_id": worker_id,
                            "done": done,
                            "total": total,
                            "transitions": transitions,
                        }),
                    )
                else:
                    # Still send overall progress even without transitions
                    self._mail.send(
                        sender=name, recipient="orchestrator",
                        msg_type=MessageType.WORKER_PROGRESS.value,
                        subject=f"Worker {name} progress: {done}/{total} tasks done",
                        body=json.dumps({"worker_id": worker_id, "done": done, "total": total}),
                    )

                # Auto-stop: all assigned tasks are done — worker must not go beyond its scope
                if total > 0 and done >= total:
                    print(
                        f"[ORCHESTRATOR] Worker {name} completed all {total} tasks — auto-stopping.",
                        flush=True,
                    )
                    asyncio.create_task(engine.stop())

            elif etype == "tool_done":
                # Heartbeat every 10 tool calls so orchestrator knows worker is alive
                _tool_call_count[0] += 1
                # Update handle's tool call counter
                h = self._workers.get(worker_id)
                if h:
                    h.tool_call_count = _tool_call_count[0]

                if _tool_call_count[0] % 10 == 0:
                    # Read current task statuses and git commits from worktree
                    wt_done, wt_total, wt_current, wt_commits = 0, len(task_ids), "?", 0
                    try:
                        wt_tl_path = worktree_path / ".swarmweaver" / "task_list.json"
                        if wt_tl_path.exists():
                            wt_data = json.loads(wt_tl_path.read_text(encoding="utf-8"))
                            wt_tasks = wt_data.get("tasks", []) if isinstance(wt_data, dict) else wt_data
                            wt_total = len(wt_tasks)
                            wt_done = sum(1 for t in wt_tasks if isinstance(t, dict) and t.get("status") == "done")
                            in_prog = [t for t in wt_tasks if isinstance(t, dict) and t.get("status") == "in_progress"]
                            if in_prog:
                                wt_current = f"{in_prog[0].get('id', '?')}: {in_prog[0].get('title', '')[:40]}"
                    except Exception as e:
                        print(f"[WARNING] Heartbeat task list parse failed: {e}", flush=True)
                    try:
                        import subprocess as _sp
                        r = _sp.run(
                            ["git", "rev-list", "--count", "HEAD"],
                            cwd=str(worktree_path), capture_output=True, text=True, timeout=5,
                        )
                        wt_commits = int(r.stdout.strip()) if r.returncode == 0 else 0
                    except Exception as e:
                        print(f"[WARNING] Commit count parse failed: {e}", flush=True)

                    # Update handle
                    if h:
                        h.tasks_done = wt_done
                        h.git_commit_count = wt_commits

                    # Sync worktree task statuses to main so main stays up to date if worker dies
                    try:
                        wt_tl_path = worktree_path / ".swarmweaver" / "task_list.json"
                        main_tl_path = get_paths(self.project_dir).task_list
                        if wt_tl_path.exists() and main_tl_path.exists():
                            wt_data = json.loads(wt_tl_path.read_text(encoding="utf-8"))
                            wt_tasks = wt_data.get("tasks", []) if isinstance(wt_data, dict) else wt_data
                            worker_status = {t["id"]: t for t in wt_tasks if isinstance(t, dict) and t.get("id")}
                            main_data = json.loads(main_tl_path.read_text(encoding="utf-8"))
                            main_tasks = main_data.get("tasks", []) if isinstance(main_data, dict) else main_data
                            for mt in main_tasks:
                                if isinstance(mt, dict) and mt.get("id") in worker_status:
                                    ws = worker_status[mt["id"]]
                                    mt["status"] = ws.get("status", mt.get("status"))
                                    for f in ("verification_status", "completion_notes", "completed_at"):
                                        if ws.get(f):
                                            mt[f] = ws[f]
                            if isinstance(main_data, dict):
                                main_data["tasks"] = main_tasks
                            main_tl_path.write_text(json.dumps(main_data, indent=2), encoding="utf-8")
                    except Exception as e:
                        print(f"[WARNING] Task status sync to main failed: {e}", flush=True)

                    # Emit dedicated heartbeat event for frontend observability
                    await self.emit({
                        "type": "worker_heartbeat",
                        "data": {
                            "worker_id": worker_id,
                            "tool_calls": _tool_call_count[0],
                            "tasks_done": wt_done,
                            "tasks_total": wt_total,
                        },
                    })

                    self._mail.send(
                        sender=name, recipient="orchestrator",
                        msg_type=MessageType.WORKER_PROGRESS.value,
                        subject=f"Worker {name} heartbeat: {wt_done}/{wt_total} done, {wt_commits} commits, working on: {wt_current}",
                        body=json.dumps({
                            "worker_id": worker_id,
                            "tool_calls": _tool_call_count[0],
                            "done": wt_done,
                            "total": wt_total,
                            "current_task": wt_current,
                            "git_commits": wt_commits,
                        }),
                    )

                    # Early dead-worker warning: many tool calls, no commits, no tasks done
                    if h and _tool_call_count[0] >= 50 and wt_commits == 0 and wt_done == 0:
                        warn_msg = (
                            f"EFFICIENCY ALERT: You have made {_tool_call_count[0]} tool calls "
                            f"with 0 git commits and 0 tasks marked done. "
                            f"Stop all visual testing immediately. "
                            f"Write code, mark tasks done, commit. "
                            f"If the code already exists, mark tasks done NOW without testing."
                        )
                        try:
                            from features.steering import write_steering_message
                            write_steering_message(worktree_path, warn_msg, "directive")
                            asyncio.create_task(engine.send_interrupt())
                            print(f"[ORCHESTRATOR] Sent efficiency alert to {name} at {_tool_call_count[0]} tool calls", flush=True)
                        except Exception as e:
                            print(f"[WARNING] Efficiency warning delivery failed: {e}", flush=True)

        # Create Engine with worker task scope for MCP tool enforcement
        # task_list_dir=worktree_path so worker_tools write to worktree's task_list;
        # merge sync copies worktree -> main. mail_project_dir=main for report_to_orchestrator.
        worker_max_budget = 2.0   # $2 per worker max — prevents runaway costs
        worker_max_turns = 200    # bounded turns — prevents infinite loops
        # Spawn per-worktree LSP servers for detected languages
        if self._lsp_manager:
            try:
                detected = self._lsp_manager.detect_languages(worktree_path)
                lsp_cfg = self._lsp_manager._config
                # Deduplicate: resolve each lang to its server spec, spawn once per server
                seen_servers: set[str] = set()
                spawned = 0
                for lang in detected:
                    if spawned >= lsp_cfg.max_servers_per_worktree:
                        break
                    spec = self._lsp_manager._resolve_spec(lang, Path(worktree_path))
                    if spec is None or spec.server_name in seen_servers:
                        continue
                    seen_servers.add(spec.server_name)
                    await self._lsp_manager.ensure_server(
                        lang, worktree_path, worker_id=str(worker_id)
                    )
                    spawned += 1
                print(f"[WORKER {name}] LSP servers spawned: {list(seen_servers)}", flush=True)
            except Exception as e:
                print(f"[WORKER {name}] LSP server spawn failed (non-fatal): {e}", flush=True)

        engine_kwargs = dict(
            project_dir=str(worktree_path),
            mode=self.mode,
            model=WORKER_MODEL,
            task_input=worker_task_input,
            budget_limit=per_worker_budget,
            max_hours=self.max_hours,
            phase_models=self.phase_models,
            on_event=worker_on_event,
            task_scope=task_ids if task_ids else None,
            worker_id=worker_id,
            task_list_dir=worktree_path,
            mail_project_dir=self.project_dir,
            max_budget_usd=worker_max_budget,
            max_turns=worker_max_turns,
            lsp_manager=self._lsp_manager,
            file_scope=file_scope,
        )
        try:
            engine = Engine(**engine_kwargs)
        except TypeError:
            # Fallback: Engine doesn't support new params (stale cache / older version)
            print(f"[ORCHESTRATOR] Engine doesn't accept max_budget_usd/max_turns, falling back", flush=True)
            engine_kwargs.pop("max_budget_usd", None)
            engine_kwargs.pop("max_turns", None)
            engine = Engine(**engine_kwargs)

        # Launch as background asyncio task with retry for transient errors
        async def _run_engine():
            from claude_agent_sdk._errors import ProcessError, CLINotFoundError

            max_retries = 2
            for attempt in range(max_retries + 1):
                try:
                    await engine.run()
                    handle.status = "completed"
                    handle.completed_at = datetime.utcnow().isoformat() + "Z"
                    self._consecutive_spawn_failures = 0
                    self._save_worker_registry()
                    self._mail.send(
                        sender=name, recipient="orchestrator",
                        msg_type=MessageType.WORKER_DONE.value,
                        subject=f"Worker {name} finished",
                        body=json.dumps({"worker_id": worker_id, "status": "completed"}),
                    )
                    return
                except CLINotFoundError:
                    # Fatal — don't retry, CLI binary is missing
                    handle.status = "error"
                    handle.completed_at = datetime.utcnow().isoformat() + "Z"
                    self._consecutive_spawn_failures += 1
                    self._save_worker_registry()
                    # Reset assigned tasks to pending so orchestrator can reassign
                    try:
                        tl = TaskList(self.project_dir)
                        tl.load()
                        for tid in handle.assigned_task_ids:
                            task = tl.get_task(tid)
                            if task and task.status == "in_progress":
                                task.status = "pending"
                                task.notes = f"{task.notes}\n[RECOVERY] Reset from crashed {name}".strip()
                        tl.save()
                        print(f"[ORCHESTRATOR] Reset {len(handle.assigned_task_ids)} tasks from crashed {name}", flush=True)
                    except Exception as e:
                        print(f"[ORCHESTRATOR] Task recovery failed for {name}: {e}", flush=True)
                    self._mail.send(
                        sender=name, recipient="orchestrator",
                        msg_type=MessageType.ERROR.value,
                        subject=f"Worker {name} fatal: Claude CLI not found",
                        body="Claude CLI binary not found. Install it or check PATH.",
                    )
                    return
                except ProcessError as e:
                    if attempt < max_retries:
                        print(f"[WORKER {name}] ProcessError (attempt {attempt+1}/{max_retries+1}), retrying in {5*(attempt+1)}s: {e}", flush=True)
                        await asyncio.sleep(5 * (attempt + 1))
                        continue
                    handle.status = "error"
                    handle.completed_at = datetime.utcnow().isoformat() + "Z"
                    self._consecutive_spawn_failures += 1
                    self._save_worker_registry()
                    # Reset assigned tasks to pending so orchestrator can reassign
                    try:
                        tl = TaskList(self.project_dir)
                        tl.load()
                        for tid in handle.assigned_task_ids:
                            task = tl.get_task(tid)
                            if task and task.status == "in_progress":
                                task.status = "pending"
                                task.notes = f"{task.notes}\n[RECOVERY] Reset from crashed {name}".strip()
                        tl.save()
                        print(f"[ORCHESTRATOR] Reset {len(handle.assigned_task_ids)} tasks from crashed {name}", flush=True)
                    except Exception as e2:
                        print(f"[ORCHESTRATOR] Task recovery failed for {name}: {e2}", flush=True)
                    stderr_snippet = e.stderr[:300] if hasattr(e, 'stderr') and e.stderr else 'none'
                    exit_code = e.exit_code if hasattr(e, 'exit_code') else '?'
                    self._mail.send(
                        sender=name, recipient="orchestrator",
                        msg_type=MessageType.ERROR.value,
                        subject=f"Worker {name} crashed (exit code {exit_code})",
                        body=f"{e}\nstderr: {stderr_snippet}",
                    )
                    return
                except Exception as e:
                    handle.status = "error"
                    handle.completed_at = datetime.utcnow().isoformat() + "Z"
                    self._consecutive_spawn_failures += 1
                    self._save_worker_registry()
                    # Reset assigned tasks to pending so orchestrator can reassign
                    try:
                        tl = TaskList(self.project_dir)
                        tl.load()
                        for tid in handle.assigned_task_ids:
                            task = tl.get_task(tid)
                            if task and task.status == "in_progress":
                                task.status = "pending"
                                task.notes = f"{task.notes}\n[RECOVERY] Reset from crashed {name}".strip()
                        tl.save()
                        print(f"[ORCHESTRATOR] Reset {len(handle.assigned_task_ids)} tasks from crashed {name}", flush=True)
                    except Exception as e2:
                        print(f"[ORCHESTRATOR] Task recovery failed for {name}: {e2}", flush=True)
                    self._mail.send(
                        sender=name, recipient="orchestrator",
                        msg_type=MessageType.ERROR.value,
                        subject=f"Worker {name} crashed",
                        body=str(e)[:500],
                    )
                    return

        # Stagger delay — scales with active worker count to reduce CLI contention
        if self._workers:
            active = sum(1 for w in self._workers.values() if w.status == "running")
            delay = STAGGER_DELAY_S * max(1, active // 2)
            await asyncio.sleep(delay)

        atask = asyncio.create_task(_run_engine())

        handle = WorkerHandle(
            worker_id=worker_id,
            name=name,
            engine=engine,
            task=atask,
            worktree_path=str(worktree_path),
            branch_name=branch,
            assigned_task_ids=task_ids,
            file_scope=file_scope,
            role=role,
            status="running",
            started_at=datetime.utcnow().isoformat() + "Z",
        )
        self._workers[worker_id] = handle
        self._save_worker_registry()

        # Register worker with enhanced watchdog (W4-4)
        if self._watchdog:
            self._watchdog.register_worker(
                worker_id=worker_id,
                pid=None,  # PID set when engine starts
                role=role,
                worktree_path=str(worktree_path),
                assigned_task_ids=task_ids,
                file_scope=file_scope,
                asyncio_task=atask,
            )

        # Non-blocking overlap detection with non-running workers (merged/completed)
        # Running workers already blocked above; this warns about merge-time conflicts
        if file_scope:
            file_set = set(file_scope)
            for wid, w in self._workers.items():
                if wid == worker_id or w.status == "running":
                    continue
                if w.file_scope:
                    overlap = file_set & set(w.file_scope)
                    if overlap:
                        handle.overlap_warning = f"Overlaps with {w.name} ({w.status}): {list(overlap)[:5]}"
                        print(f"[ORCHESTRATOR] {handle.overlap_warning}", flush=True)
                        break

        await self.emit({
            "type": "worker_spawned",
            "data": handle.to_dict(),
        })
        self._record_decision(f"Spawned {name} with tasks {task_ids} and scope {file_scope}")

        # Send DISPATCH beacon (M3-2) — worker's first context injection will surface this
        try:
            self._mail.send_protocol(
                sender="orchestrator",
                recipient=name,
                msg_type=MessageType.DISPATCH.value,
                subject=f"Assignment: {', '.join(task_ids[:5])}{'...' if len(task_ids) > 5 else ''}",
                body=(f"You are {name} ({role}). Tasks: {task_ids}\n"
                      f"File scope: {file_scope}\nUse get_my_tasks for details."),
                priority="high",
                payload={"task_ids": task_ids, "file_scope": file_scope,
                         "worktree_path": str(worktree_path), "role": role},
            )
        except Exception:
            pass

        return {
            "success": True,
            "worker_id": worker_id,
            "name": name,
            "worktree": str(worktree_path),
            "branch": branch,
        }

    async def _tool_list_workers(self, args: dict) -> dict:
        return {
            "workers": [w.to_dict() for w in self._workers.values()],
            "total": len(self._workers),
            "running": len([w for w in self._workers.values() if w.status == "running"]),
            "completed": len([w for w in self._workers.values() if w.status == "completed"]),
            "merged": len([w for w in self._workers.values() if w.status == "merged"]),
        }

    async def _tool_get_worker_updates(self, args: dict) -> dict:
        # Only read messages sent AFTER this orchestrator started (filter stale)
        messages = self._mail.get_messages(recipient="orchestrator", unread_only=True, limit=50)
        fresh = [m for m in messages if m.created_at >= self._start_time]
        for msg in messages:
            self._mail.mark_read(msg.id)

        # Include authoritative worker status from asyncio.Task state
        # (don't trust mail alone — the asyncio task is ground truth)
        self._check_worker_tasks()
        worker_summary = []
        for w in self._workers.values():
            # Check actual task completion in worker's filtered task_list
            tasks_done = 0
            tasks_total = 0
            try:
                wt_tl_path = Path(w.worktree_path) / ".swarmweaver" / "task_list.json"
                if wt_tl_path.exists():
                    wt_data = json.loads(wt_tl_path.read_text(encoding="utf-8"))
                    wt_tasks = wt_data.get("tasks", []) if isinstance(wt_data, dict) else wt_data
                    tasks_total = len(wt_tasks)
                    tasks_done = sum(1 for t in wt_tasks if isinstance(t, dict) and t.get("status") == "done")
            except Exception:
                pass
            worker_summary.append({
                "worker_id": w.worker_id,
                "name": w.name,
                "status": w.status,
                "assigned_tasks": w.assigned_task_ids,
                "tasks_done": tasks_done,
                "tasks_total": tasks_total,
                "task_done": w.task.done() if w.task else False,
            })

        return {
            "messages": [
                {
                    "sender": m.sender,
                    "type": m.msg_type,
                    "subject": m.subject,
                    "body": m.body[:500],
                    "time": m.created_at,
                }
                for m in fresh
            ],
            "message_count": len(fresh),
            "worker_status": worker_summary,
        }

    def _sync_task_statuses_before_merge(self, handle: WorkerHandle) -> int:
        """
        Sync completed task statuses from worker's task_list into main's task_list,
        then align the worker's copy with main to prevent merge conflicts.

        Returns the number of tasks whose status was updated.
        """
        worker_tl_path = Path(handle.worktree_path) / ".swarmweaver" / "task_list.json"
        main_tl_path = get_paths(self.project_dir).task_list

        if not worker_tl_path.exists() or not main_tl_path.exists():
            print(f"[ORCHESTRATOR] Task sync skipped: worker_tl={worker_tl_path.exists()}, main_tl={main_tl_path.exists()}", flush=True)
            return 0

        # 1. Read worker's task statuses
        worker_data = json.loads(worker_tl_path.read_text(encoding="utf-8"))
        worker_tasks = worker_data.get("tasks", []) if isinstance(worker_data, dict) else worker_data
        worker_status_map: dict[str, dict] = {}
        for wt in worker_tasks:
            if isinstance(wt, dict) and wt.get("id"):
                worker_status_map[wt["id"]] = wt
        print(f"[ORCHESTRATOR] Task sync: worker has {len(worker_status_map)} tasks, statuses: {[(t.get('id','?'), t.get('status','?')) for t in worker_tasks if isinstance(t, dict)]}", flush=True)

        # 2. Update main's task list with worker completions
        main_data = json.loads(main_tl_path.read_text(encoding="utf-8"))
        main_tasks = main_data.get("tasks", []) if isinstance(main_data, dict) else main_data

        updated = 0
        # Accept both "done" and "completed" as completion markers
        done_statuses = {"done", "completed"}
        for mt in main_tasks:
            if not isinstance(mt, dict):
                continue
            tid = mt.get("id")
            if tid not in worker_status_map:
                continue
            wt = worker_status_map[tid]
            # Transfer completion status and any verification data
            if wt.get("status") in done_statuses and mt.get("status") not in done_statuses:
                mt["status"] = "done"
                updated += 1
                print(f"[ORCHESTRATOR] Task sync: {tid} marked done (was {mt.get('status', '?')})", flush=True)
            # Transfer supplementary fields the worker may have set
            for field in ("verification_status", "completion_notes", "completed_at"):
                if wt.get(field):
                    mt[field] = wt[field]

        if isinstance(main_data, dict):
            main_data["tasks"] = main_tasks

        # 3. Write updated main task list and commit
        main_tl_path.write_text(json.dumps(main_data, indent=2), encoding="utf-8")
        self._git("add", ".swarmweaver/task_list.json")
        self._git("commit", "-m",
                   f"Sync {updated} task status(es) from {handle.name} before merge")

        # 4. Copy main's FULL task list to the worker branch so they match (no conflict)
        worker_tl_path.write_text(json.dumps(main_data, indent=2), encoding="utf-8")
        self._git("add", ".swarmweaver/task_list.json", cwd=Path(handle.worktree_path))
        self._git("commit", "-m",
                   "Align task_list.json with main for clean merge",
                   cwd=Path(handle.worktree_path))

        # 5. Also align other metadata files that can cause spurious conflicts
        for fname in ("claude-progress.txt", "session_reflections.json"):
            main_f = get_paths(self.project_dir).swarmweaver_dir / fname
            worker_f = Path(handle.worktree_path) / ".swarmweaver" / fname
            if main_f.exists() and worker_f.exists():
                worker_f.write_text(main_f.read_text(encoding="utf-8"), encoding="utf-8")
                self._git("add", f".swarmweaver/{fname}", cwd=Path(handle.worktree_path))
            elif worker_f.exists() and not main_f.exists():
                # Worker created it but main doesn't have it — leave as-is (will merge cleanly)
                pass
        # Commit any metadata alignment
        self._git("commit", "--allow-empty", "-m",
                   "Align metadata files with main for clean merge",
                   cwd=Path(handle.worktree_path))

        print(f"[ORCHESTRATOR] Synced {updated} task(s) from {handle.name} before merge", flush=True)
        return updated

    async def _tool_merge_worker(self, args: dict) -> dict:
        wid = args.get("worker_id")
        handle = self._workers.get(wid)
        if not handle:
            return {"success": False, "error": f"Worker {wid} not found"}
        if handle.status not in ("completed", "error"):
            return {"success": False, "error": f"Worker {wid} is still {handle.status}"}

        # 1. Commit untracked .swarmweaver/ files on main so they don't block the merge
        #    (git refuses to merge if untracked files would be overwritten)
        try:
            self._git("add", ".swarmweaver/")
            ok, _ = self._git("diff", "--cached", "--quiet")
            if not ok:  # staged changes exist
                self._git("commit", "-m",
                           f"Track .swarmweaver files before merging {handle.name}")
        except Exception as e:
            print(f"[ORCHESTRATOR] Pre-merge commit note: {e}", flush=True)

        # 2. Sync task statuses from worker → main BEFORE merge to prevent
        #    the worker's filtered task_list.json from overwriting main's full list.
        synced = 0
        try:
            synced = self._sync_task_statuses_before_merge(handle)
        except Exception as e:
            print(f"[ORCHESTRATOR] Task sync warning for {handle.name}: {e}", flush=True)

        # 3. Run the merge
        try:
            resolution = self._merge_resolver.resolve(
                handle.branch_name,
                commit_message=f"Merge {handle.name}: tasks {', '.join(handle.assigned_task_ids)}",
            )
            handle.status = "merged"
            handle.merge_tier = resolution.tier.value if resolution else "unknown"

            # Post-merge LSP diagnostic validation
            post_merge_errors = []
            if self._lsp_manager and resolution and resolution.success:
                try:
                    changed_files = []
                    ok_diff, diff_out = self._git("diff", "--name-only", "HEAD~1", timeout=10)
                    if ok_diff and diff_out.strip():
                        changed_files = [f.strip() for f in diff_out.strip().split("\n") if f.strip()]
                    for f in changed_files[:20]:
                        fpath = self.project_dir / f
                        if fpath.exists() and fpath.is_file():
                            try:
                                content = fpath.read_text(encoding="utf-8")
                                diags = await self._lsp_manager.notify_file_changed(str(fpath), content)
                                post_merge_errors.extend([d for d in diags if d.severity == 1])
                            except Exception:
                                pass
                    if post_merge_errors:
                        await self.emit({
                            "type": "lsp.merge_validation",
                            "data": {
                                "worker_id": wid,
                                "error_count": len(post_merge_errors),
                                "errors": [
                                    {"file": d.uri, "line": d.range_start_line + 1, "message": d.message}
                                    for d in post_merge_errors[:10]
                                ],
                            },
                        })
                except Exception as e:
                    print(f"[ORCHESTRATOR] Post-merge LSP validation failed: {e}", flush=True)

            await self.emit({
                "type": "worker_merged",
                "data": {
                    "worker_id": wid,
                    "resolution_tier": handle.merge_tier,
                    "success": resolution.success if resolution else False,
                    "tasks_synced": synced,
                    "post_merge_errors": len(post_merge_errors),
                },
            })
            self._record_decision(f"Merged {handle.name} via tier {handle.merge_tier} ({synced} tasks synced)")

            return {
                "success": resolution.success if resolution else False,
                "tier": handle.merge_tier,
                "files_conflicted": resolution.files_conflicted if resolution else [],
                "tasks_synced": synced,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _tool_terminate_worker(self, args: dict) -> dict:
        wid = args.get("worker_id")
        reason = args.get("reason", "Terminated by orchestrator")
        handle = self._workers.get(wid)
        if not handle:
            return {"success": False, "error": f"Worker {wid} not found"}

        try:
            await handle.engine.stop()
        except Exception:
            pass

        handle.status = "terminated"
        handle.completed_at = datetime.utcnow().isoformat() + "Z"

        # Release tasks back to pending
        try:
            tl = TaskList(self.project_dir)
            tl.load()
            for tid in handle.assigned_task_ids:
                task = tl.get_task(tid)
                if task and task.status == "in_progress":
                    task.status = TaskStatus.PENDING.value
            tl.save()
        except Exception:
            pass

        await self.emit({
            "type": "worker_terminated",
            "data": {"worker_id": wid, "reason": reason},
        })
        self._record_decision(f"Terminated {handle.name}: {reason}")

        return {"success": True, "worker_id": wid, "released_tasks": handle.assigned_task_ids}

    async def _tool_reassign_tasks(self, args: dict) -> dict:
        task_ids = args.get("task_ids", [])
        to_wid = args.get("to_worker_id", 0)

        if to_wid == 0:
            # Return tasks to unassigned pool
            self._record_decision(f"Returned tasks {task_ids} to pending pool")
            return {"success": True, "action": "returned_to_pool", "task_ids": task_ids}

        target = self._workers.get(to_wid)
        if not target:
            return {"success": False, "error": f"Worker {to_wid} not found"}
        if target.status != "running":
            return {"success": False, "error": f"Worker {to_wid} is {target.status}"}

        target.assigned_task_ids.extend(task_ids)
        self._record_decision(f"Reassigned tasks {task_ids} to {target.name}")

        return {"success": True, "worker_id": to_wid, "task_ids": task_ids}

    async def _tool_get_task_status(self, args: dict) -> dict:
        try:
            tl = TaskList(self.project_dir)
            tl.load()
            total = len(tl.tasks)
            by_status = {}
            for t in tl.tasks:
                by_status[t.status] = by_status.get(t.status, 0) + 1

            # Per-worker assignments
            worker_assignments = {}
            for w in self._workers.values():
                worker_assignments[w.name] = {
                    "status": w.status,
                    "tasks": w.assigned_task_ids,
                    "file_scope": w.file_scope,
                }

            return {
                "total_tasks": total,
                "by_status": by_status,
                "percent_done": round(by_status.get("done", 0) / max(total, 1) * 100, 1),
                "worker_assignments": worker_assignments,
            }
        except Exception as e:
            return {"error": str(e)}

    async def _tool_send_directive(self, args: dict) -> dict:
        wid = args.get("worker_id")
        message = args.get("message", "")
        handle = self._workers.get(wid)
        if not handle:
            return {"success": False, "error": f"Worker {wid} not found"}

        # Write steering message to worker's project dir
        try:
            write_steering_message(
                Path(handle.worktree_path), message, "directive"
            )
            self._mail.send(
                sender="orchestrator", recipient=handle.name,
                msg_type=MessageType.DIRECTIVE.value,
                subject="Orchestrator directive",
                body=message,
            )
            # Also inject any pending worker mail via steering (M1-2)
            worker_mail = self._mail.format_for_injection(handle.name, max_messages=5)
            if worker_mail:
                write_steering_message(Path(handle.worktree_path), worker_mail, "mail")
            # Interrupt the worker so it finishes its current turn and
            # reads the new directive at the start of the next turn.
            asyncio.create_task(handle.engine.send_interrupt())
            return {"success": True, "worker_id": wid}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # MELS: Lesson recording, synthesis, and context building
    # ------------------------------------------------------------------

    def _record_worker_error(
        self,
        worker_id: int,
        worker_name: str,
        tool_name: str,
        error_message: str,
        task_id: str = "",
        file_path: str = "",
    ) -> str:
        """Record a worker error via MELS synthesizer."""
        if not self._lesson_synth:
            print(f"[WARNING] MELS error not tracked — synthesizer not initialised (worker-{worker_id})", flush=True)
            return f"err-{worker_id}-untracked"

        err_id, new_lesson = self._lesson_synth.record_error(
            worker_id=str(worker_id),
            worker_name=worker_name,
            tool_name=tool_name,
            error_message=error_message,
            file_path=file_path,
            task_id=task_id,
        )
        # Emit event if a new lesson was synthesized
        if new_lesson:
            asyncio.ensure_future(self.emit({
                "type": "expertise_lesson_created",
                "lesson_id": new_lesson.id,
                "content": new_lesson.content[:200],
                "severity": new_lesson.severity,
                "quality_score": new_lesson.quality_score,
                "domain": new_lesson.domain,
            }))
            print(f"[MELS] Lesson synthesized: {new_lesson.content[:80]}", flush=True)
        # Propagate high-quality lessons to active workers
        lessons = self._lesson_synth.get_lessons_for_worker(
            file_scope=[], exclude_worker=str(worker_id),
        )
        for lesson in lessons:
            if lesson.quality_score >= 0.6 and str(worker_id) not in lesson.propagated_to:
                asyncio.ensure_future(self._propagate_lesson_to_active_workers(lesson))
        return err_id

    def _save_lesson(
        self,
        lesson: str,
        applies_to: list[str] | None = None,
        severity: str = "medium",
        source_errors: list[str] | None = None,
    ) -> str:
        """Save a lesson to MELS expertise store. Returns the lesson ID."""
        if not self._expertise_store or not self._lesson_synth:
            print(f"[WARNING] MELS lesson not saved — store not initialised: {lesson[:80]}", flush=True)
            return "lesson-untracked"

        from services.expertise_models import SessionLesson, infer_domain
        # Infer domain from file patterns
        domain = ""
        for fp in (applies_to or []):
            d = infer_domain(fp)
            if d:
                domain = d
                break
        if not domain:
            # Fallback: infer from lesson content keywords
            for kw, d in [("react", "typescript.react"), ("typescript", "typescript"),
                          ("python", "python"), ("fastapi", "python.fastapi"),
                          ("test", "testing"), ("docker", "devops.docker"),
                          ("api", "architecture.api"), ("css", "styling")]:
                if kw in lesson.lower():
                    domain = d
                    break

        mels_lesson = SessionLesson(
            session_id=self._lesson_synth._session_id,
            content=lesson,
            severity=severity if severity in ("low", "medium", "high", "critical") else "medium",
            domain=domain,
            file_patterns=applies_to or [],
            source_error_ids=source_errors or [],
            quality_score=0.7,  # Orchestrator-authored lessons are high quality
        )
        self._expertise_store.add_session_lesson(mels_lesson)
        asyncio.ensure_future(self.emit({
            "type": "expertise_lesson_created",
            "lesson_id": mels_lesson.id,
            "content": lesson[:200],
            "severity": mels_lesson.severity,
            "quality_score": mels_lesson.quality_score,
            "domain": mels_lesson.domain,
        }))
        return mels_lesson.id

    def _build_lessons_context(self, task_ids: list[str], file_scope: list[str]) -> str:
        """Build a formatted lessons section for injection into worker overlay."""
        if not self._lesson_synth:
            return ""

        lessons = self._lesson_synth.get_lessons_for_worker(file_scope)
        if not lessons:
            return ""

        lines = [
            "The following lessons were learned from previous workers' errors.",
            "Follow these to avoid repeating the same mistakes:",
            "",
        ]
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        for l in sorted(lessons, key=lambda x: severity_order.get(x.severity, 2))[:10]:
            lines.append(f"- **[{l.severity.upper()}]** {l.content}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # MELS: orchestrator tool handlers
    # ------------------------------------------------------------------

    async def _tool_get_lessons(self, args: dict) -> dict:
        """Get lessons from MELS expertise store."""
        if not self._expertise_store or not self._lesson_synth:
            return {"success": True, "error_count": 0, "lesson_count": 0, "errors": [], "lessons": []}

        lessons = self._expertise_store.get_session_lessons(self._lesson_synth._session_id)
        return {
            "success": True,
            "error_count": len(self._lesson_synth._errors),
            "lesson_count": len(lessons),
            "errors": self._lesson_synth._errors[-20:],
            "lessons": [{"id": l.id, "lesson": l.content, "severity": l.severity,
                         "quality_score": l.quality_score, "domain": l.domain,
                         "file_patterns": l.file_patterns, "created_at": l.created_at}
                        for l in lessons],
        }

    def _try_self_correction(self, worker_id: int, error_text: str, wt_path: Path) -> None:
        """If a MELS lesson matches this error, steer the worker with advice."""
        if not self._lesson_synth:
            return
        try:
            lessons = self._lesson_synth.get_lessons_for_worker(file_scope=[])
            if not lessons:
                return
            error_lower = error_text.lower()
            for lesson in lessons:
                lesson_words = {w for w in lesson.content.lower().split() if len(w) > 4}
                if sum(1 for w in lesson_words if w in error_lower) >= 2:
                    write_steering_message(
                        wt_path,
                        f"[SELF-CORRECTION] A similar error was seen before.\n"
                        f"Lesson: {lesson.content}\n"
                        f"Apply this lesson to fix your current approach.",
                        "instruction",
                    )
                    print(f"[SELF-CORRECTION] Sent lesson to worker-{worker_id}: {lesson.content[:80]}", flush=True)
                    return
        except Exception as e:
            print(f"[WARNING] Lesson send to worker failed: {e}", flush=True)

    # ------------------------------------------------------------------
    # MELS: Mid-session lesson propagation & post-session promotion
    # ------------------------------------------------------------------

    async def _propagate_lesson_to_active_workers(self, lesson) -> None:
        """Push high-severity lessons to running workers whose file scope overlaps."""
        try:
            for worker_id, handle in self._workers.items():
                if handle.status != "running":
                    continue
                if str(worker_id) in lesson.propagated_to:
                    continue
                # Check file scope overlap
                if lesson.file_patterns and hasattr(handle, "file_scope") and handle.file_scope:
                    import fnmatch as fnm
                    overlap = False
                    for pat in lesson.file_patterns:
                        for fp in handle.file_scope:
                            if fnm.fnmatch(fp, pat):
                                overlap = True
                                break
                        if overlap:
                            break
                    if not overlap:
                        continue

                # Steering message for immediate injection
                wt_path = getattr(handle, "worktree_path", None)
                if wt_path:
                    write_steering_message(
                        Path(wt_path),
                        f"[LESSON FROM PEER] {lesson.content}\nSeverity: {lesson.severity}. Apply this now.",
                        "instruction",
                    )
                    lesson.propagated_to.append(str(worker_id))
                    if self._expertise_store:
                        self._expertise_store.update_session_lesson(
                            lesson.id, propagated_to=lesson.propagated_to,
                        )
                    # Emit WebSocket event
                    await self.emit({
                        "type": "expertise_lesson_propagated",
                        "lesson_id": lesson.id,
                        "worker_id": worker_id,
                        "content": lesson.content[:200],
                    })
                    print(f"[MELS] Propagated lesson to worker-{worker_id}: {lesson.content[:80]}", flush=True)
        except Exception as e:
            print(f"[WARNING] MELS lesson propagation failed: {e}", flush=True)

    async def _promote_session_lessons(self) -> None:
        """At session end, promote high-quality lessons to permanent records."""
        if not self._expertise_store or not self._lesson_synth:
            return
        try:
            session_key = self._lesson_synth._session_id
            lessons = self._expertise_store.get_session_lessons(session_key)
            promoted = 0
            for lesson in lessons:
                if lesson.quality_score >= 0.6:
                    record_id = self._expertise_store.promote_lesson(lesson.id)
                    if record_id:
                        promoted += 1
                        await self.emit({
                            "type": "expertise_record_promoted",
                            "lesson_id": lesson.id,
                            "record_id": record_id,
                        })
            if promoted > 0:
                print(f"[MELS] Promoted {promoted} session lesson(s) to permanent records", flush=True)

            # Sync high-confidence project records to cross-project store
            self._sync_to_cross_project()
        except Exception as e:
            print(f"[WARNING] MELS lesson promotion failed: {e}", flush=True)

    def _sync_to_cross_project(self) -> None:
        """Sync high-confidence project records to cross-project store."""
        if not self._expertise_store:
            return
        try:
            from services.expertise_store import get_cross_project_store
            cross_store = get_cross_project_store()
            # Get foundational records with high confidence
            records = self._expertise_store.search(
                classification="foundational", limit=50,
            )
            synced = 0
            for rec in records:
                if rec.confidence >= 0.7:
                    cross_store.add(rec)
                    synced += 1
            if synced > 0:
                print(f"[MELS] Synced {synced} record(s) to cross-project store", flush=True)
        except Exception as e:
            print(f"[WARNING] MELS cross-project sync failed: {e}", flush=True)

    async def _tool_add_lesson(self, args: dict) -> dict:
        lesson_text = args.get("lesson", "")
        if not lesson_text:
            return {"success": False, "error": "lesson text is required"}

        lesson_id = self._save_lesson(
            lesson=lesson_text,
            applies_to=args.get("applies_to"),
            severity=args.get("severity", "medium"),
            source_errors=args.get("source_errors"),
        )
        return {"success": True, "lesson_id": lesson_id}

    async def _tool_run_verification(self, args: dict) -> dict:
        """Run quality gates on the main project directory."""
        try:
            from core.quality_gates import QualityGateChecker
            from dataclasses import asdict
            checker = QualityGateChecker(self.project_dir)
            report = checker.check_all(worker_id=0)
            return {
                "success": True,
                "passed": report.passed,
                "gates": [asdict(g) for g in report.gates],
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _tool_signal_complete(self, args: dict) -> dict:
        summary = args.get("summary", "All work completed")

        # Run quality gates before allowing completion
        try:
            from core.quality_gates import QualityGateChecker
            from dataclasses import asdict
            checker = QualityGateChecker(self.project_dir)
            report = checker.check_all(worker_id=0)
            if not report.passed:
                failed = [g for g in report.gates if not g.passed]
                details = "; ".join(f"{g.name}: {g.detail}" for g in failed)
                await self.emit({
                    "type": "orchestrator_decision",
                    "data": {"action": "verification_failed", "details": details},
                })
                return {
                    "success": False,
                    "error": f"Quality gates failed: {details}",
                    "action": "fix_and_retry",
                    "failed_gates": [asdict(g) for g in failed],
                }
        except Exception as e:
            print(f"[ORCHESTRATOR] Quality gate check error: {e}", flush=True)
            # Don't block on gate infrastructure failure

        self._complete = True
        await self.emit({
            "type": "orchestrator_decision",
            "data": {"action": "signal_complete", "summary": summary},
        })
        self._record_decision(f"Signalled completion: {summary}")
        return {"success": True, "summary": summary}

    async def _tool_wait_seconds(self, args: dict) -> dict:
        """Sleep for N seconds while keeping the SDK connection alive.

        During the wait, worker asyncio tasks continue running and streaming
        events to the frontend. After the wait, we check for finished workers
        and collect any new mail messages so the orchestrator gets fresh status.

        The sleep breaks early if a steering message arrives (via
        self._steering_event), so operator directives are delivered promptly.
        """
        seconds = min(max(args.get("seconds", 30), 1), 120)
        print(f"[ORCHESTRATOR] Waiting {seconds}s (workers continue running)...", flush=True)

        # Clear any stale steering signal before sleeping
        self._steering_event.clear()

        # Sleep in 1-second increments; break early on stop or steering
        steering_arrived = False
        for i in range(seconds):
            if self._stopped:
                break
            if self._steering_event.is_set():
                self._steering_event.clear()
                steering_arrived = True
                print(f"[ORCHESTRATOR] Wait interrupted by steering message at {i}s/{seconds}s", flush=True)
                break
            await asyncio.sleep(1)

        # After waking up, check for finished workers and collect updates
        self._check_worker_tasks()
        updates = self._collect_updates()

        # Build a fresh status snapshot for the orchestrator
        tl = TaskList(self.project_dir)
        tl.load()
        total = len(tl.tasks)
        done = len([t for t in tl.tasks if t.status == "done"])
        pending = len([t for t in tl.tasks if t.status == "pending"])
        in_progress = len([t for t in tl.tasks if t.status == "in_progress"])

        workers_detail = []
        for w in self._workers.values():
            detail: dict = {
                "name": w.name,
                "status": w.status,
                "assigned_tasks": w.assigned_task_ids,
            }
            # Read per-task status directly from the worker's worktree task_list.json
            try:
                wt_tl = Path(w.worktree_path) / ".swarmweaver" / "task_list.json"
                if wt_tl.exists():
                    wt_data = json.loads(wt_tl.read_text(encoding="utf-8"))
                    wt_tasks = wt_data.get("tasks", []) if isinstance(wt_data, dict) else wt_data
                    task_lines = []
                    for t in wt_tasks:
                        if isinstance(t, dict):
                            tid = t.get("id", "?")
                            st = t.get("status", "?")
                            title = t.get("title", "")[:50]
                            task_lines.append(f"  {tid} [{st}]: {title}")
                    detail["task_status"] = task_lines
                    wt_done = sum(1 for t in wt_tasks if isinstance(t, dict) and t.get("status") == "done")
                    detail["progress"] = f"{wt_done}/{len(wt_tasks)} tasks done"
            except Exception:
                pass
            # Tail audit log for live activity
            try:
                audit_path = Path(w.worktree_path) / ".swarmweaver" / "audit.log"
                if audit_path.exists():
                    lines = audit_path.read_text(encoding="utf-8", errors="replace").splitlines()
                    detail["recent_activity"] = lines[-8:] if len(lines) >= 8 else lines
            except Exception:
                pass
            workers_detail.append(detail)

        finished_workers = [
            w.name for w in self._workers.values()
            if w.status in ("completed", "error") and w.merge_tier == ""
        ]

        result: dict = {
            "success": True,
            "waited_seconds": seconds,
            "worker_updates": updates or "No new messages.",
            "workers": workers_detail,
            "finished_unmerged": finished_workers,
            "task_progress": f"{done}/{total} done (main list), {in_progress} in progress, {pending} pending",
        }

        # Check for steering messages and include directly in response
        # so the orchestrator reads them immediately.
        if steering_arrived:
            try:
                from features.steering import read_steering_message, mark_steering_processed
                msg = read_steering_message(self.project_dir)
                if msg:
                    mark_steering_processed(self.project_dir)
                    if msg.steering_type == "abort":
                        result["OPERATOR_DIRECTIVE"] = (
                            "ABORT requested by operator. "
                            "Stop all work immediately. Merge what you can and call signal_complete."
                        )
                    elif msg.steering_type == "reflect":
                        result["OPERATOR_DIRECTIVE"] = (
                            f"REFLECTION REQUESTED by operator:\n\n"
                            f"{msg.message}\n\n"
                            f"Re-evaluate your plan in light of this feedback. "
                            f"Adjust worker assignments, spawn/terminate workers as needed."
                        )
                    else:
                        result["OPERATOR_DIRECTIVE"] = (
                            f"INSTRUCTION from operator (you MUST follow this):\n\n"
                            f"{msg.message}\n\n"
                            f"Adjust your orchestration strategy accordingly."
                        )
                    print(f"[ORCHESTRATOR] Delivered steering to orchestrator: {msg.steering_type}", flush=True)
            except Exception as e:
                print(f"[ORCHESTRATOR] Steering read failed: {e}", flush=True)

        return result

    # ------------------------------------------------------------------
    # Prompt Builders
    # ------------------------------------------------------------------

    def _build_initial_prompt(self, tl: TaskList, analysis: dict) -> str:
        task_summary = []
        for t in tl.tasks:
            if t.status in (TaskStatus.PENDING.value, TaskStatus.IN_PROGRESS.value):
                files = ", ".join(t.files_affected[:5]) if t.files_affected else "no specific files"
                deps = ", ".join(t.depends_on) if t.depends_on else "none"
                task_summary.append(
                    f"  - {t.id}: {t.title} | files: [{files}] | deps: [{deps}] | priority: {t.priority}"
                )

        # Detect resume: check for already-completed tasks
        done_tasks = [t for t in tl.tasks if t.status in ("done", "completed", "verified")]
        pending_tasks = [t for t in tl.tasks if t.status in ("pending", "in_progress", "blocked")]
        is_resume = len(done_tasks) > 0
        resume_section = ""
        if is_resume:
            # Build a very explicit resume section
            resume_lines = []
            resume_lines.append("## !! RESUME SESSION — READ THIS FIRST !!")
            resume_lines.append("")
            resume_lines.append(f"This is a RESUMED run. {len(done_tasks)} of {len(tl.tasks)} tasks are ALREADY COMPLETE.")
            resume_lines.append("Their code has been merged into the main branch.")
            resume_lines.append("")
            resume_lines.append("### COMPLETED TASKS (DO NOT reassign, DO NOT redo)")
            for t in done_tasks:
                resume_lines.append(f"  - {t.id}: {t.title} [STATUS: {t.status}]")
            resume_lines.append("")
            resume_lines.append(f"### REMAINING TASKS ({len(pending_tasks)} tasks need workers)")
            for t in pending_tasks:
                deps = ", ".join(t.dependencies) if hasattr(t, "dependencies") and t.dependencies else "none"
                resume_lines.append(f"  - {t.id}: {t.title} [STATUS: {t.status}] deps: {deps}")
            resume_lines.append("")

            # Previous workers info
            registry = self._load_worker_registry()
            if registry and registry.get("workers"):
                resume_lines.append("### PREVIOUS WORKERS (already ran)")
                for wid_str, wdata in registry["workers"].items():
                    name = wdata.get("name", f"worker-{wid_str}")
                    task_ids = wdata.get("task_ids", [])
                    status = wdata.get("status", "unknown")
                    resume_lines.append(f"  - {name}: assigned {task_ids}, status={status}")
                resume_lines.append("")

            resume_lines.append("### YOUR ACTION")
            if pending_tasks:
                pending_ids = [t.id for t in pending_tasks]
                resume_lines.append(f"Spawn workers ONLY for these pending tasks: {', '.join(pending_ids)}")
                resume_lines.append("Do NOT create workers for completed tasks.")
                resume_lines.append(f"Use worker IDs starting from {self._next_worker_id}.")
            else:
                resume_lines.append("ALL tasks are complete. Report completion.")
            resume_lines.append("")

            # MELS lessons
            try:
                if self._expertise_store and self._lesson_synth:
                    lesson_entries = self._expertise_store.get_session_lessons(
                        self._lesson_synth._session_id
                    )
                    if lesson_entries:
                        resume_lines.append(f"### Lessons from Previous Run ({len(lesson_entries)} entries)")
                        for le in lesson_entries[-10:]:
                            resume_lines.append(f"  - {getattr(le, 'content', '')}")
            except Exception:
                pass

            resume_section = "\n".join(resume_lines)

        file_groups_text = []
        for i, fg in enumerate(analysis.get("file_groups", []), 1):
            fg_tasks = ", ".join(fg["task_ids"])
            fg_files = ", ".join(fg["files"][:10]) or "no specific files"
            file_groups_text.append(f"  Group {i}: tasks [{fg_tasks}] → files [{fg_files}]")

        budget_text = ""
        if self.budget_limit > 0:
            budget_text = f"Total budget: ${self.budget_limit:.2f}"
        if self.max_hours > 0:
            budget_text += f" | Time limit: {self.max_hours}h"
        if not budget_text:
            budget_text = "No budget limit set"

        # Include spec file content so the orchestrator understands what's being built
        spec_content = ""
        try:
            paths_main = get_paths(self.project_dir)
            for spec_name in ("app_spec.txt", "task_input.txt"):
                sp = paths_main.swarmweaver_dir / spec_name
                if sp.exists():
                    text = sp.read_text(encoding="utf-8")[:2000]
                    spec_content = f"\n## Project Specification\n{text}\n"
                    break
        except Exception as e:
            print(f"[WARNING] Spec content load failed: {e}", flush=True)

        return f"""You are coordinating a coding swarm for the following objective:
{self.task_input}
{spec_content}{resume_section}
## Task List Analysis
- Total pending tasks: {analysis['total_tasks']}
- Independent file groups: {analysis['independent_groups']}
- Max dependency chain depth: {analysis['max_dependency_chain']}
- Recommended workers (CEILING — use fewer if possible): {analysis['recommended_workers']}
- Reasoning: {analysis['reasoning']}

## Complexity Analysis
- Simple tasks: {analysis.get('complexity', {}).get('simple', '?')} (1 point each)
- Moderate tasks: {analysis.get('complexity', {}).get('moderate', '?')} (3 points each)
- Complex tasks: {analysis.get('complexity', {}).get('complex', '?')} (5 points each)
- Total complexity score: {analysis.get('complexity', {}).get('total_score', '?')}
- Worker capacity: ~30 points each
- NOTE: The recommended worker count is a CEILING. Use fewer workers when possible.
  A single worker handles 25-30 simple tasks efficiently. Do not over-allocate.

## File Groups (tasks that share files)
{chr(10).join(file_groups_text) or "  No file groups detected"}

## Full Task Details
{chr(10).join(task_summary) or "  No pending tasks"}

## Budget
{budget_text}

## Planning Instructions
Before spawning workers, PLAN your approach:
1. Review the task list and file groups above
2. Identify dependency chains — tasks that must run before others
3. Group tasks into phases (tasks in the same phase run in parallel, then all merge before next phase)
4. For each worker, decide its EXACT file scope (only the files its tasks touch)

## Spawning Instructions
- Use `spawn_worker` with BOTH `task_ids` AND `file_scope` for each worker
- When tasks have non-obvious constraints, pass `per_task_instructions`, e.g. {{"TASK-001": "Only API layer; do not modify frontend"}}
- `file_scope` MUST list only the files the worker's tasks need — worker is blocked from writing elsewhere
- If you don't provide `file_scope`, it is auto-derived from the tasks' `files_affected` lists
- Start with fewer workers (1-2) and add more after merging if tasks remain

## Monitoring
After spawning, enter the monitoring loop:
- Call `wait_seconds(30)` — returns per-worker task status and recent activity
- Merge finished workers, then call `get_task_status()` before spawning more
- The `workers` field in `wait_seconds` shows EXACTLY what each worker has done

## CRITICAL: Worker Completion Rules
- Each worker gets a FILTERED task list with ONLY its assigned tasks
- The `wait_seconds` response shows each worker's per-task status in real-time
- Only call `merge_worker` when the worker has status: completed (asyncio task done)
- **After merging, call `get_task_status()` before spawning more workers**

Begin by analysing the tasks and writing your phased plan, then spawn workers.
After spawning, call `wait_seconds(30)` and continue monitoring."""

    def _build_update_prompt(self, updates: str) -> str:
        tl = TaskList(self.project_dir)
        tl.load()
        total = len(tl.tasks)
        done = len([t for t in tl.tasks if t.status == "done"])
        pending = len([t for t in tl.tasks if t.status == "pending"])
        in_progress = len([t for t in tl.tasks if t.status == "in_progress"])
        failed = len([t for t in tl.tasks if t.status == "failed"])

        workers_text = []
        now_ts = datetime.utcnow()
        for w in self._workers.values():
            # Time since last tool call
            idle_note = ""
            if w.last_tool_time:
                try:
                    lt = datetime.fromisoformat(w.last_tool_time.replace("Z", "+00:00")).replace(tzinfo=None)
                    idle_secs = int((now_ts - lt).total_seconds())
                    if w.using_puppeteer:
                        idle_note = f" | last: {w.last_tool_name} {idle_secs}s ago [PUPPETEER — slow ops normal, wait 10+ min]"
                    elif idle_secs > 120:
                        idle_note = f" | last: {w.last_tool_name} {idle_secs}s ago [IDLE — consider nudge if >300s]"
                    else:
                        idle_note = f" | last: {w.last_tool_name} {idle_secs}s ago"
                except Exception:
                    pass
            commit_note = f" | {w.git_commit_count} commits" if w.git_commit_count >= 0 else ""
            task_note = f" | {w.tasks_done}/{len(w.assigned_task_ids)} tasks done"
            tool_note = f" | {w.tool_call_count} tool calls"
            workers_text.append(
                f"  - {w.name}: {w.status}{task_note}{commit_note}{tool_note}{idle_note}"
            )

        return f"""## Status Update

{updates or "No new messages from workers."}

## Worker Status
{chr(10).join(workers_text) or "  No workers yet"}

## Task Progress
Done: {done}/{total} ({round(done / max(total, 1) * 100)}%)
In Progress: {in_progress}
Pending: {pending}
Failed: {failed}

## Puppeteer Patience Reminder
Workers using Puppeteer MCP go SILENT for 30-120s per operation (browser startup,
navigate, screenshot, click). A worker showing "PUPPETEER" in its last tool is NOT stalled.
Wait at least 10 minutes of silence AFTER a Puppeteer call before sending a directive.
Only terminate a worker after 20+ minutes of complete silence AND a failed directive.

Continue your monitoring loop:
- If a worker finished → merge it, then call get_task_status() to see what's really done
- If tasks remain unassigned → spawn more workers
- If nothing to do → share a status update and call wait_seconds(30)
- If all tasks done and merged → call signal_complete"""

    def _build_state_summary(self) -> str:
        lines = ["## Orchestrator State Summary (context rotation)"]
        lines.append(f"Mode: {self.mode}")
        lines.append(f"Objective: {self.task_input[:200]}")
        lines.append(f"Decisions made: {len(self._decisions)}")
        for d in self._decisions[-20:]:
            lines.append(f"  - [{d['time']}] {d['action']}")
        for w in self._workers.values():
            lines.append(f"Worker {w.name}: {w.status}, tasks={w.assigned_task_ids}, merge={w.merge_tier}")
        return "\n".join(lines)

    def _build_rotation_prompt(self, summary: str) -> str:
        return f"""Context has been rotated to keep the conversation fresh.
Here is a summary of everything that happened so far:

{summary}

Continue managing the swarm. Use wait_seconds(30) between checks, merge finished workers,
spawn new workers for remaining tasks, and call signal_complete when all done."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _check_worker_tasks(self) -> None:
        """Check asyncio tasks for completion."""
        for w in self._workers.values():
            if w.status == "running" and w.task.done():
                exc = w.task.exception() if not w.task.cancelled() else None
                if exc:
                    w.status = "error"
                elif w.status == "running":
                    w.status = "completed"
                w.completed_at = datetime.utcnow().isoformat() + "Z"

    def _collect_updates(self) -> str:
        """Read unread mail messages for orchestrator using format_for_injection."""
        # Use format_for_injection for rich formatting (M1-2)
        raw = self._mail.format_for_injection("orchestrator", max_messages=50)
        if not raw:
            return ""
        return raw

    def _any_workers_finished(self) -> bool:
        return any(
            w.status in ("completed", "error") and w.merge_tier == ""
            for w in self._workers.values()
        )

    def _record_decision(self, action: str) -> None:
        self._decisions.append({
            "time": datetime.utcnow().isoformat() + "Z",
            "action": action,
        })

    def _git(self, *args: str, cwd: Optional[Path] = None, timeout: int = 60) -> tuple[bool, str]:
        try:
            result = subprocess.run(
                ["git", *args],
                capture_output=True, text=True, timeout=timeout,
                cwd=str(cwd or self.project_dir),
            )
            return result.returncode == 0, result.stdout + result.stderr
        except subprocess.TimeoutExpired as e:
            return False, f"Command timed out after {timeout}s: {e}"
        except Exception as e:
            return False, str(e)

    async def _cleanup(self) -> None:
        """Stop workers, sync progress, and clean up for safe resume.

        All blocking I/O (subprocess git commands, shutil.rmtree) is offloaded
        to a thread-pool executor so the asyncio event loop stays responsive
        during cleanup and in-flight HTTP requests are not dropped.
        """
        # MELS: Promote high-quality session lessons before cleanup
        await self._promote_session_lessons()
        import shutil

        loop = asyncio.get_event_loop()

        # 1. Signal all running workers to stop and cancel their asyncio tasks
        for w in self._workers.values():
            if w.status == "running":
                try:
                    await w.engine.stop()
                except Exception:
                    pass
                if not w.task.done():
                    w.task.cancel()

        # 1b. Stop LSP servers and health loop
        if self._lsp_health_task and not self._lsp_health_task.done():
            self._lsp_health_task.cancel()
        if self._lsp_manager:
            try:
                await self._lsp_manager.stop_all()
                print("[CLEANUP] LSP servers stopped", flush=True)
            except Exception as e:
                print(f"[CLEANUP] LSP cleanup failed: {e}", flush=True)

        # 2. Wait for all worker tasks to finish (give them a few seconds)
        pending_tasks = [w.task for w in self._workers.values() if not w.task.done()]
        if pending_tasks:
            await asyncio.gather(*pending_tasks, return_exceptions=True)

        # 3. Sync task statuses from ALL workers to main before cleanup.
        #    This preserves progress so resume knows which tasks are done.
        for w in list(self._workers.values()):
            if w.status == "merged":
                continue  # already synced during merge
            try:
                worktree_path = Path(w.worktree_path)
                if worktree_path.exists():
                    synced = self._sync_task_statuses_before_merge(w)
                    print(f"[CLEANUP] Synced {synced} task(s) from {w.name} before shutdown", flush=True)
            except Exception as e:
                print(f"[CLEANUP] Task sync failed for {w.name}: {e}", flush=True)

        # 4. Merge completed (but un-merged) workers so their code is preserved
        for w in list(self._workers.values()):
            if w.status in ("completed",) and Path(w.worktree_path).exists():
                try:
                    resolution = self._merge_resolver.resolve(
                        w.branch_name,
                        commit_message=f"Auto-merge {w.name} on shutdown: tasks {', '.join(w.assigned_task_ids)}",
                    )
                    if resolution and resolution.success:
                        w.status = "merged"
                        print(f"[CLEANUP] Auto-merged {w.name} (tier {resolution.tier.value})", flush=True)
                    else:
                        print(f"[CLEANUP] Auto-merge failed for {w.name}, branch preserved", flush=True)
                except Exception as e:
                    print(f"[CLEANUP] Auto-merge error for {w.name}: {e}", flush=True)

        # 5. Reset in_progress tasks back to pending so they get re-assigned on resume
        try:
            tl = TaskList(self.project_dir)
            tl.load()
            reset_count = 0
            for t in tl.tasks:
                if t.status == TaskStatus.IN_PROGRESS.value:
                    t.status = TaskStatus.PENDING.value
                    reset_count += 1
            if reset_count > 0:
                tl.save()
                print(f"[CLEANUP] Reset {reset_count} in-progress task(s) to pending for resume", flush=True)
        except Exception as e:
            print(f"[CLEANUP] Task reset failed: {e}", flush=True)

        # 6. Remove worktrees and branches without blocking the event loop
        project_dir_str = str(self.project_dir)
        for w in list(self._workers.values()):
            wpath = w.worktree_path
            branch = w.branch_name

            def _remove_worktree(p=wpath, cwd=project_dir_str):
                if Path(p).exists():
                    subprocess.run(
                        ["git", "worktree", "remove", "--force", p],
                        cwd=cwd, capture_output=True, timeout=30,
                    )

            def _delete_branch(b=branch, cwd=project_dir_str):
                subprocess.run(
                    ["git", "branch", "-D", b],
                    cwd=cwd, capture_output=True, timeout=30,
                )

            await loop.run_in_executor(None, _remove_worktree)
            # Only delete branches for merged workers; keep un-merged branches
            # so their code can potentially be recovered
            if w.status == "merged":
                await loop.run_in_executor(None, _delete_branch)

        # 7. Close mail store
        self._mail.close()

        # 8. Clean up temporary files in swarm dir but preserve state for resume
        #    (mail.db, merge_queue.db, etc. are needed if user resumes)
        swarm_dir = get_paths(self.project_dir).swarm_dir
        if swarm_dir.exists():
            _preserve = {"mail.db", "merge_queue.db", "merge_history.json", "worker_registry.json"}

            def _selective_cleanup(sd=swarm_dir):
                for child in sd.iterdir():
                    if child.name in _preserve:
                        continue
                    try:
                        if child.is_dir():
                            shutil.rmtree(child, ignore_errors=True)
                        else:
                            child.unlink(missing_ok=True)
                    except OSError:
                        pass

            await loop.run_in_executor(None, _selective_cleanup)

    async def stop(self) -> None:
        """Stop orchestrator and all workers."""
        self._stopped = True
        # Stop watchdog
        if self._watchdog:
            self._watchdog.stop()
        if self._watchdog_task and not self._watchdog_task.done():
            self._watchdog_task.cancel()
        for handle in list(self._workers.values()):
            try:
                await handle.engine.stop()
            except Exception:
                pass

    def get_state(self) -> dict:
        """Return current orchestrator state (for REST endpoint)."""
        return {
            "mode": self.mode,
            "model": ORCHESTRATOR_MODEL,
            "worker_model": WORKER_MODEL,
            "stopped": self._stopped,
            "complete": self._complete,
            "workers": [w.to_dict() for w in self._workers.values()],
            "decisions": self._decisions[-50:],
            "mail_stats": self._mail.get_stats() if self._mail.db_path.exists() else {},
        }
