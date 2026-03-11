"""
Swarm Orchestrator
==================

Handles worktree creation and task distribution for multi-agent swarm runs.
Workers are executed by the Swarm class (swarm.py), not here.
"""

import asyncio
import json
import subprocess
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, Callable, Any

from core.paths import get_paths
from core.dispatch_overrides import OverrideResolver
from state.task_list import TaskList, TaskStatus
from state.mail import MailStore
from services.watchdog import SwarmWatchdog, WatchdogEvent
from services.monitor import MonitorDaemon

STAGGER_DELAY_MS = 2000


class HierarchyManager:
    """Tracks agent spawn depth to prevent runaway spawning (max depth 2)."""

    MAX_DEPTH = 2

    def __init__(self):
        self._agents: dict[str, dict] = {}

    def can_spawn(self, parent_name: str) -> bool:
        info = self._agents.get(parent_name)
        if info is None:
            return True
        return info["depth"] < self.MAX_DEPTH

    def register_agent(self, name: str, parent: str, capability: str, depth: int) -> None:
        self._agents[name] = {"parent": parent, "capability": capability, "depth": depth, "children": []}
        if parent in self._agents:
            self._agents[parent]["children"].append(name)

    def get_tree(self) -> dict:
        roots = [n for n, info in self._agents.items() if info["parent"] not in self._agents]

        def _build_node(name: str) -> dict:
            info = self._agents[name]
            return {
                "name": name,
                "capability": info["capability"],
                "depth": info["depth"],
                "children": [_build_node(c) for c in info["children"]],
            }

        if not roots:
            return {"name": "orchestrator", "children": [], "depth": 0, "capability": "orchestrator"}
        return {"name": "orchestrator", "capability": "orchestrator", "depth": 0, "children": [_build_node(r) for r in roots]}


@dataclass
class WorkerState:
    """State of a single swarm worker."""
    worker_id: int
    worktree_path: str = ""
    branch_name: str = ""
    status: str = "idle"
    current_task: Optional[str] = None
    completed_tasks: list[str] = field(default_factory=list)
    error: Optional[str] = None
    pid: Optional[int] = None
    depth: int = 1
    file_scope: list[str] = field(default_factory=list)
    quality_gate_report: Optional[dict] = None

    def to_dict(self) -> dict:
        return asdict(self)


class SwarmOrchestrator:
    """
    Sets up git worktrees and distributes tasks to parallel workers.

    Workflow:
    1. setup_worktrees() — create N git worktrees
    2. distribute_tasks() — assign tasks to workers by file scope / category
    3. (workers run externally via Swarm)
    4. cleanup_worktrees() — remove worktrees and branches
    """

    def __init__(
        self,
        project_dir: Path,
        model: str,
        num_workers: int,
        mode: str = "feature",
        task_input: str = "",
        max_depth: int = 2,
        overrides: list[dict] | None = None,
        resume: bool = True,
    ):
        self.project_dir = project_dir
        self.model = model
        self.mode = mode
        self.task_input = task_input
        self.max_depth = max_depth
        self.resume = resume

        self.override_resolver = OverrideResolver.from_dict_list(overrides) if overrides else OverrideResolver()
        max_agents = self.override_resolver.get_max_agents()
        self.num_workers = min(max_agents or num_workers, 10)

        self.workers: list[WorkerState] = []
        self.mail = MailStore(project_dir)
        self.watchdog = SwarmWatchdog(stale_timeout=300, check_interval=30, mail_store=self.mail)
        self._watchdog_task: Optional[asyncio.Task] = None
        self.monitor_daemon: Optional[MonitorDaemon] = None
        self.hierarchy = HierarchyManager()
        self.stagger_delay_ms = STAGGER_DELAY_MS

    @property
    def swarm_dir(self) -> Path:
        return get_paths(self.project_dir).swarm_dir

    @property
    def state_file(self) -> Path:
        return get_paths(self.project_dir).swarm_state

    def _run_git(self, *args: str, cwd: Optional[Path] = None) -> tuple[bool, str]:
        try:
            result = subprocess.run(
                ["git", *args],
                capture_output=True, text=True, timeout=60,
                cwd=str(cwd or self.project_dir),
            )
            return result.returncode == 0, result.stdout + result.stderr
        except Exception as e:
            return False, str(e)

    def _save_state(self) -> None:
        self.swarm_dir.mkdir(parents=True, exist_ok=True)
        state = {
            "num_workers": self.num_workers,
            "max_depth": self.max_depth,
            "mode": self.mode,
            "workers": [w.to_dict() for w in self.workers],
            "overrides": self.override_resolver.to_dict_list(),
        }
        self.state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")

    async def setup_worktrees(self) -> list[WorkerState]:
        """Create git worktrees for each worker, resuming existing ones if possible."""
        self.swarm_dir.mkdir(parents=True, exist_ok=True)
        self.mail.initialize()

        ok, _ = self._run_git("rev-parse", "--git-dir")
        if not ok:
            self._run_git("init")
            self._run_git("add", "-A")
            self._run_git("commit", "-m", "Initial commit for swarm mode")

        # --- Resume existing worktrees if available ---
        if self.resume and self.state_file.exists():
            try:
                saved = json.loads(self.state_file.read_text(encoding="utf-8"))
                saved_workers = saved.get("workers", [])
                if saved_workers:
                    resumed = []
                    for w_dict in saved_workers:
                        worktree = Path(w_dict["worktree_path"])
                        branch = w_dict["branch_name"]
                        if worktree.exists() and worktree.is_dir():
                            # Reuse existing worktree — agent will pick up remaining tasks
                            worker = WorkerState(**{
                                k: v for k, v in w_dict.items()
                                if k in WorkerState.__dataclass_fields__
                            })
                            worker.status = "idle"
                            worker.error = None
                        else:
                            # Worktree was cleaned up — recreate it on the existing branch
                            ok2, _ = self._run_git("worktree", "add", str(worktree), branch)
                            if not ok2:
                                # Branch gone too — create fresh
                                self._run_git("worktree", "add", "-b", branch, str(worktree))
                            worker = WorkerState(**{
                                k: v for k, v in w_dict.items()
                                if k in WorkerState.__dataclass_fields__
                            })
                            worker.status = "idle"
                            worker.error = None
                        resumed.append(worker)
                    if resumed:
                        self.workers = resumed
                        self._save_state()
                        return self.workers
            except Exception:
                pass  # Fall through to fresh setup

        # --- Fresh setup ---
        self.workers = []
        for i in range(1, self.num_workers + 1):
            branch = f"swarm/worker-{i}"
            worktree = self.swarm_dir / f"worker-{i}"
            if worktree.exists():
                self._run_git("worktree", "remove", "--force", str(worktree))
            self._run_git("branch", "-D", branch)
            ok, output = self._run_git("worktree", "add", "-b", branch, str(worktree))
            worker = WorkerState(
                worker_id=i,
                worktree_path=str(worktree),
                branch_name=branch,
                status="idle" if ok else "error",
                error=output if not ok else None,
            )
            self.workers.append(worker)

        self._save_state()
        return self.workers

    def distribute_tasks(self) -> dict[int, list[str]]:
        """Assign tasks to workers using file-scope-aware grouping."""
        task_list = TaskList(self.project_dir)
        task_list.load()

        pending_tasks = [
            t for t in task_list.tasks
            if t.status in (TaskStatus.PENDING.value, TaskStatus.IN_PROGRESS.value)
        ]
        scoped_tasks = [t for t in pending_tasks if t.files_affected]
        unscoped_tasks = [t for t in pending_tasks if not t.files_affected]

        assignments: dict[int, list[str]] = {w.worker_id: [] for w in self.workers}
        worker_files: dict[int, set[str]] = {w.worker_id: set() for w in self.workers}

        for task in scoped_tasks:
            task_files = set(task.files_affected)
            best_worker = None
            best_overlap = 0
            for worker in self.workers:
                wid = worker.worker_id
                overlap = len(task_files & worker_files[wid])
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_worker = wid
            if best_worker is None:
                best_worker = min(assignments, key=lambda wid: len(assignments[wid]))
            assignments[best_worker].append(task.id)
            worker_files[best_worker].update(task_files)

        by_category: dict[str, list[str]] = {}
        for task in unscoped_tasks:
            cat = task.category or "general"
            by_category.setdefault(cat, []).append(task.id)

        for cat in by_category:
            target = min(assignments, key=lambda wid: len(assignments[wid]))
            assignments[target].extend(by_category[cat])

        if self.num_workers >= 3:
            for i, worker in enumerate(self.workers):
                role = "lead" if i == 0 else "builder"
                self.hierarchy.register_agent(
                    name=f"worker-{worker.worker_id}",
                    parent="orchestrator",
                    capability=role,
                    depth=worker.depth,
                )

        for worker in self.workers:
            worker.file_scope = sorted(worker_files[worker.worker_id])

        # Send DISPATCH mail for each worker assignment (M3-1)
        for worker in self.workers:
            wid = worker.worker_id
            task_ids = assignments.get(wid, [])
            if task_ids:
                try:
                    from state.mail import MessageType
                    self.mail.send(
                        sender="orchestrator",
                        recipient=f"worker-{wid}",
                        msg_type=MessageType.DISPATCH.value,
                        subject=f"Worker {wid}: {len(task_ids)} tasks assigned",
                        body=f"Tasks: {', '.join(task_ids)}",
                        metadata={"task_ids": task_ids},
                    )
                except Exception:
                    pass

        return assignments

    async def cleanup_worktrees(self) -> None:
        """Stop workers, sync progress, and clean up for safe resume."""
        if self.monitor_daemon:
            self.monitor_daemon.stop()
        self.stop_watchdog()

        # Sync task statuses from workers before removing worktrees
        for worker in self.workers:
            worktree = Path(worker.worktree_path)
            if not worktree.exists():
                continue
            try:
                wt_tl_path = worktree / ".swarmweaver" / "task_list.json"
                main_tl_path = get_paths(self.project_dir).task_list
                if wt_tl_path.exists() and main_tl_path.exists():
                    wt_data = json.loads(wt_tl_path.read_text(encoding="utf-8"))
                    wt_tasks = wt_data.get("tasks", []) if isinstance(wt_data, dict) else wt_data
                    main_data = json.loads(main_tl_path.read_text(encoding="utf-8"))
                    main_tasks = main_data.get("tasks", []) if isinstance(main_data, dict) else main_data
                    done_statuses = {"done", "completed"}
                    for mt in main_tasks:
                        if not isinstance(mt, dict):
                            continue
                        tid = mt.get("id")
                        for wt in wt_tasks:
                            if isinstance(wt, dict) and wt.get("id") == tid:
                                if wt.get("status") in done_statuses and mt.get("status") not in done_statuses:
                                    mt["status"] = "done"
                                break
                    if isinstance(main_data, dict):
                        main_data["tasks"] = main_tasks
                    main_tl_path.write_text(json.dumps(main_data, indent=2), encoding="utf-8")
            except Exception as e:
                print(f"[CLEANUP] Task sync failed for worker-{worker.worker_id}: {e}", flush=True)

        # Reset in_progress tasks to pending for resume
        try:
            tl = TaskList(self.project_dir)
            tl.load()
            for t in tl.tasks:
                if t.status == TaskStatus.IN_PROGRESS.value:
                    t.status = TaskStatus.PENDING.value
            tl.save()
        except Exception:
            pass

        # Remove worktrees and branches
        for worker in self.workers:
            worktree = Path(worker.worktree_path)
            if worktree.exists():
                self._run_git("worktree", "remove", "--force", str(worktree))
            self._run_git("branch", "-D", worker.branch_name)

        self.mail.close()
        import shutil
        if self.swarm_dir.exists():
            _preserve = {"mail.db", "merge_queue.db", "merge_history.json"}
            for child in self.swarm_dir.iterdir():
                if child.name in _preserve:
                    continue
                try:
                    if child.is_dir():
                        shutil.rmtree(child, ignore_errors=True)
                    else:
                        child.unlink(missing_ok=True)
                except OSError:
                    pass

    async def start_watchdog(self, on_event: Optional[Callable[[WatchdogEvent], Any]] = None) -> None:
        if self._watchdog_task is None or self._watchdog_task.done():
            self._watchdog_task = asyncio.create_task(self.watchdog.run(on_event=on_event))

    def stop_watchdog(self) -> None:
        self.watchdog.stop()
        if self._watchdog_task and not self._watchdog_task.done():
            self._watchdog_task.cancel()

    def get_state(self) -> dict:
        return {
            "num_workers": self.num_workers,
            "mode": self.mode,
            "workers": [w.to_dict() for w in self.workers],
            "mail_stats": self.mail.get_stats() if self.mail.db_path.exists() else {},
            "watchdog": self.watchdog.get_status(),
            "hierarchy": self.hierarchy.get_tree(),
            "stagger_delay_ms": self.stagger_delay_ms,
            "overrides": self.override_resolver.to_dict_list(),
        }
