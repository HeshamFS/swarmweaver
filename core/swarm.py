"""
Swarm Mode
==========

Multi-agent execution using concurrent Engine instances,
each running in its own git worktree. Uses SwarmOrchestrator
for worktree setup and task distribution, with in-process SDK clients.

Two swarm modes:
  - Swarm: Static N workers (legacy --parallel N)
  - SmartSwarm: AI-orchestrated (--smart-swarm) — runs planning with
    a single Engine, then hands off to SmartOrchestrator for execution.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Awaitable, Callable, Optional

from core.engine import Engine, OnEventCallback
from core.orchestrator import SwarmOrchestrator, WorkerState
from core.merge_resolver import MergeResolver
from core.paths import get_paths
from core.agent_roles import write_overlay_to_worktree, assign_role
from core.dispatch_overrides import OverrideResolver, DispatchOverride
from core.quality_gates import QualityGateChecker
from state.task_list import TaskList


def build_worker_task_brief(
    task_ids: list[str],
    task_list_dir,
    fallback_input: str = "",
    task_instructions: dict[str, str] | None = None,
) -> str:
    """
    Build a focused task brief for a worker from its assigned task IDs.

    Instead of passing the full app spec (which motivates workers to implement
    everything), this builds a minimal brief from only the assigned tasks'
    titles, descriptions, and acceptance criteria.

    Args:
        task_ids: Task IDs assigned to this worker
        task_list_dir: Directory containing task_list.json (main project dir)
        fallback_input: Full task_input to fall back to if task list unavailable
        task_instructions: Optional per-task constraints, e.g. {"TASK-001": "Only API; no UI"}

    Returns:
        Focused brief string covering only the assigned tasks
    """
    if not task_ids:
        return fallback_input

    try:
        from pathlib import Path
        tl = TaskList(Path(task_list_dir))
        if not tl.load():
            return fallback_input

        assigned = {t.id: t for t in tl.tasks if t.id in task_ids}
        if not assigned:
            return fallback_input

        lines = [
            f"You are responsible for implementing the following {len(task_ids)} task(s).",
            "Focus ONLY on these tasks — do not implement anything outside them.",
            "",
            "## Your Assigned Tasks",
            "",
        ]
        instructions = task_instructions or {}
        for tid in task_ids:
            task = assigned.get(tid)
            if not task:
                lines.append(f"- {tid} (details not found)")
                continue
            lines.append(f"### {tid}: {task.title}")
            if tid in instructions:
                lines.append(f"**Constraint:** {instructions[tid]}")
            if task.description:
                lines.append(task.description)
            if task.acceptance_criteria:
                lines.append("**Acceptance criteria:**")
                if isinstance(task.acceptance_criteria, list):
                    for ac in task.acceptance_criteria:
                        lines.append(f"- {ac}")
                else:
                    lines.append(str(task.acceptance_criteria))
            lines.append("")

        return "\n".join(lines)
    except Exception:
        return fallback_input


class Swarm:
    """
    Multi-agent swarm using concurrent Engine instances.

    Each worker runs in its own git worktree with an independent
    Engine. Events are prefixed with worker_id for frontend routing.
    """

    def __init__(
        self,
        project_dir: str | Path,
        mode: str,
        model: str,
        num_workers: int,
        task_input: str = "",
        max_iterations: Optional[int] = None,
        resume: bool = True,
        budget_limit: float = 0.0,
        max_hours: float = 0.0,
        phase_models: Optional[dict] = None,
        overrides: Optional[list[dict]] = None,
        on_event: Optional[OnEventCallback] = None,
    ):
        self.project_dir = Path(project_dir)
        self.mode = mode
        self.model = model
        self.num_workers = num_workers
        self.task_input = task_input
        self.max_iterations = max_iterations
        self.resume = resume
        self.budget_limit = budget_limit
        self.max_hours = max_hours
        self.phase_models = phase_models
        self.overrides = overrides
        self._on_event = on_event or self._noop_event
        self._engines: dict[int, Engine] = {}
        self._stopped = False

    @staticmethod
    async def _noop_event(event: dict) -> None:
        pass

    async def emit(self, event: dict) -> None:
        if "timestamp" not in event:
            event["timestamp"] = datetime.utcnow().isoformat() + "Z"
        try:
            await self._on_event(event)
        except Exception as e:
            print(f"[WARNING] Swarm emit failed: {e}", flush=True)

    async def run(self) -> None:
        """
        Main swarm execution:
        1. Set up worktrees via SwarmOrchestrator
        2. Distribute tasks to workers
        3. Run Engine per worker concurrently
        4. Merge results back
        """
        try:
            await self.emit({"type": "status", "data": "running"})

            # Use SwarmOrchestrator for worktree setup and task distribution
            orchestrator = SwarmOrchestrator(
                project_dir=self.project_dir,
                model=self.model,
                num_workers=self.num_workers,
                mode=self.mode,
                task_input=self.task_input,
                overrides=self.overrides,
                resume=self.resume,
            )

            # Setup worktrees
            await self.emit({
                "type": "swarm_status",
                "data": {"phase": "setup", "workers": self.num_workers},
            })
            workers = await orchestrator.setup_worktrees()

            # Distribute tasks
            assignments = orchestrator.distribute_tasks()

            # Build override resolver for custom instructions
            override_resolver = OverrideResolver(
                [DispatchOverride.from_dict(o) for o in (self.overrides or [])]
            )

            await self.emit({
                "type": "swarm_status",
                "data": {
                    "phase": "running",
                    "workers": [
                        {
                            "id": w.worker_id,
                            "task_ids": w.task_ids,
                            "worktree": w.worktree_path,
                        }
                        for w in workers
                    ],
                },
            })

            # Create Engine per worker
            per_worker_budget = (
                self.budget_limit / self.num_workers
                if self.budget_limit > 0
                else 0.0
            )

            async def run_worker(worker: WorkerState, task_ids: list[str]) -> None:
                worker_id = worker.worker_id

                async def worker_on_event(event: dict) -> None:
                    # Prefix events with worker_id for frontend routing
                    event["worker_id"] = worker_id
                    etype = event.get("type", "")
                    # Never forward worker-level "status" events — they
                    # would cause the frontend to treat a single worker
                    # finishing as the entire run completing.
                    if etype == "status":
                        await self.emit({
                            "type": "worker_status",
                            "worker_id": worker_id,
                            "data": event.get("data"),
                        })
                    else:
                        await self.emit(event)

                # Assign role based on worker position
                role = assign_role(worker_id, task_ids, self.num_workers)

                # Build a focused task brief (only assigned tasks, not full app spec)
                worker_task_input = build_worker_task_brief(
                    task_ids, self.project_dir, fallback_input=self.task_input
                )

                # Write agent role overlay to worktree (Layer 2 of two-layer agent system)
                try:
                    custom_instructions = override_resolver.get_custom_instructions()
                    extra = ("\n\n" + "\n".join(custom_instructions)) if custom_instructions else ""
                    write_overlay_to_worktree(
                        worktree_path=Path(worker.worktree_path),
                        role=role,
                        worker_id=worker_id,
                        task_ids=task_ids,
                        file_scope=worker.file_scope,
                        branch_name=worker.branch_name,
                        mode=self.mode,
                        task_input=worker_task_input + extra,
                    )
                except Exception:
                    pass  # Overlay is advisory, not blocking

                engine = Engine(
                    project_dir=worker.worktree_path,
                    mode=self.mode,
                    model=self.model,
                    task_input=worker_task_input,
                    max_iterations=self.max_iterations,
                    resume=self.resume,
                    budget_limit=per_worker_budget,
                    max_hours=self.max_hours,
                    phase_models=self.phase_models,
                    on_event=worker_on_event,
                    task_scope=task_ids if task_ids else None,
                    worker_id=worker_id,
                    task_list_dir=self.project_dir,
                )
                self._engines[worker_id] = engine

                try:
                    await engine.run()
                    worker.status = "completed"

                    # Run quality gates after worker completes
                    try:
                        checker = QualityGateChecker(worker.worktree_path)
                        report = checker.check_all(worker_id)
                        worker.quality_gate_report = report.to_dict()
                        await self.emit({
                            "type": "quality_gate_report",
                            "worker_id": worker_id,
                            "data": report.to_dict(),
                        })
                    except Exception:
                        pass
                except Exception as e:
                    worker.status = "error"
                    await self.emit({
                        "type": "worker_error",
                        "worker_id": worker_id,
                        "data": {"error": str(e)[:500]},
                    })
                finally:
                    self._engines.pop(worker_id, None)

            # Run all workers concurrently with stagger delay
            tasks = []
            for i, worker in enumerate(workers):
                if self._stopped:
                    break
                if i > 0:
                    await asyncio.sleep(2)  # Stagger delay
                worker_task_ids = assignments.get(worker.worker_id, [])
                task = asyncio.create_task(run_worker(worker, worker_task_ids))
                tasks.append(task)

            # Wait for all workers
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

            # Merge results
            await self.emit({
                "type": "swarm_status",
                "data": {"phase": "merging"},
            })

            try:
                merge_resolver = MergeResolver(self.project_dir)
                for worker in workers:
                    if worker.status == "completed":
                        resolution = merge_resolver.merge_worker(
                            worker.worktree_path,
                            worker.branch_name,
                        )
                        await self.emit({
                            "type": "merge_event",
                            "data": {
                                "worker_id": worker.worker_id,
                                "resolution": resolution.tier.value if resolution else "unknown",
                            },
                        })
            except Exception as e:
                await self.emit({
                    "type": "merge_error",
                    "data": {"error": str(e)[:500]},
                })

            # Cleanup worktrees
            try:
                await orchestrator.cleanup_worktrees()
            except Exception as e:
                print(f"[WARNING] Worktree cleanup failed: {e}", flush=True)

            # Aggregate budget across workers
            total_cost = 0.0
            for worker in workers:
                try:
                    from state.budget import BudgetTracker

                    bt = BudgetTracker(Path(worker.worktree_path))
                    status = bt.get_status()
                    total_cost += status.get("real_cost_usd", 0) or status.get(
                        "estimated_cost_usd", 0
                    )
                except Exception as e:
                    print(f"[WARNING] Budget aggregation failed: {e}", flush=True)

            await self.emit({
                "type": "budget_update",
                "data": {"total_cost_usd": total_cost, "workers": self.num_workers},
            })

            await self.emit({"type": "status", "data": "completed"})

        except Exception as e:
            import traceback

            await self.emit({
                "type": "error",
                "data": f"Swarm error: {e}\n{traceback.format_exc()}",
            })

    async def stop(self) -> None:
        """Stop all worker engines."""
        self._stopped = True
        for engine in list(self._engines.values()):
            try:
                await engine.stop()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Smart Swarm (AI-orchestrated)
# ---------------------------------------------------------------------------


class SmartSwarm:
    """
    Intelligent swarm with an autonomous orchestrator agent.

    Workflow:
        1. Run planning phases (analyse → plan) with a single Engine
        2. After planning, inspect the task list
        3. Hand off to SmartOrchestrator which dynamically manages workers
    """

    def __init__(
        self,
        project_dir: str | Path,
        mode: str,
        model: str,
        task_input: str = "",
        spec_file: Optional[str | Path] = None,
        max_iterations: Optional[int] = None,
        resume: bool = True,
        budget_limit: float = 0.0,
        max_hours: float = 0.0,
        max_workers: int = 50,
        phase_models: Optional[dict] = None,
        on_event: Optional[OnEventCallback] = None,
    ):
        self.project_dir = Path(project_dir)
        self.mode = mode
        self.model = model
        self.task_input = task_input
        self.spec_file = spec_file
        self.max_iterations = max_iterations
        self.resume = resume
        self.budget_limit = budget_limit
        self.max_hours = max_hours
        self.max_workers = max_workers
        self.phase_models = phase_models
        self._on_event = on_event or self._noop_event
        self._stopped = False
        self._planning_engine: Optional[Engine] = None
        self._orchestrator = None  # SmartOrchestrator instance
        self._steering_event = asyncio.Event()  # Wakes up wait_seconds on steering

    @staticmethod
    async def _noop_event(event: dict) -> None:
        pass

    async def emit(self, event: dict) -> None:
        if "timestamp" not in event:
            event["timestamp"] = datetime.utcnow().isoformat() + "Z"
        try:
            await self._on_event(event)
        except Exception:
            pass

    async def run(self) -> None:
        """
        Main smart swarm execution:
        1. Run planning phases with a single Engine
        2. Hand off to SmartOrchestrator for execution
        """
        from core.smart_orchestrator import SmartOrchestrator
        from core.prompts import get_phases, is_looping_phase

        try:
            await self.emit({"type": "status", "data": "running"})
            await self.emit({"type": "swarm_status", "data": {"phase": "planning"}})

            # Determine planning vs execution phases
            phases = get_phases(self.mode)
            planning_phases = []
            execution_phases = []
            for phase in phases:
                if is_looping_phase(phase):
                    execution_phases.append(phase)
                else:
                    planning_phases.append(phase)

            # Check if task_list.json already exists with pending tasks
            # (written by the wizard before the run started — skip planning if so)
            _tl_check = TaskList(self.project_dir)
            _has_pending = (
                _tl_check.load()
                and _tl_check.tasks
                and any(t.status in ("pending", "in_progress") for t in _tl_check.tasks)
            )
            if _has_pending:
                _pending_count = sum(1 for t in _tl_check.tasks if t.status in ("pending", "in_progress"))
                await self.emit({
                    "type": "orchestrator_decision",
                    "data": {
                        "action": "skip_planning",
                        "reason": f"Task list already has {_pending_count} pending tasks from wizard — skipping planning phase",
                    },
                })

            # Phase 1: Planning (single Engine) — only if no existing task list
            if planning_phases and not self._stopped and not _has_pending:
                self._planning_engine = Engine(
                    project_dir=self.project_dir,
                    mode=self.mode,
                    model=self.model,
                    task_input=self.task_input,
                    spec_file=self.spec_file,
                    max_iterations=len(planning_phases),
                    resume=self.resume,
                    budget_limit=self.budget_limit * 0.2 if self.budget_limit > 0 else 0.0,
                    max_hours=self.max_hours,
                    phase_models=self.phase_models,
                    on_event=self._on_event,
                )
                await self._planning_engine.run()
                self._planning_engine = None

            if self._stopped:
                await self.emit({"type": "status", "data": "stopped"})
                return

            # Phase 2: Check task list and decide execution strategy
            tl = TaskList(self.project_dir)
            tl.load()
            pending = [t for t in tl.tasks if t.status in ("pending", "in_progress")]

            if not pending:
                # All tasks completed during planning
                await self.emit({"type": "status", "data": "completed"})
                return

            if len(pending) < 3:
                # Too few tasks — continue with single Engine
                await self.emit({
                    "type": "orchestrator_decision",
                    "data": {
                        "action": "single_agent",
                        "reason": f"Only {len(pending)} pending tasks — using single agent",
                    },
                })
                single_engine = Engine(
                    project_dir=self.project_dir,
                    mode=self.mode,
                    model=self.model,
                    task_input=self.task_input,
                    max_iterations=self.max_iterations,
                    resume=True,
                    budget_limit=self.budget_limit * 0.8 if self.budget_limit > 0 else 0.0,
                    max_hours=self.max_hours,
                    phase_models=self.phase_models,
                    on_event=self._on_event,
                )
                await single_engine.run()
            else:
                # 3+ tasks — use SmartOrchestrator
                await self.emit({
                    "type": "orchestrator_decision",
                    "data": {
                        "action": "smart_orchestrator",
                        "reason": f"{len(pending)} pending tasks — switching to AI orchestrator",
                    },
                })
                self._orchestrator = SmartOrchestrator(
                    project_dir=self.project_dir,
                    mode=self.mode,
                    model=self.model,
                    task_input=self.task_input,
                    max_workers=self.max_workers,
                    budget_limit=self.budget_limit * 0.8 if self.budget_limit > 0 else 0.0,
                    max_hours=self.max_hours,
                    phase_models=self.phase_models,
                    on_event=self._on_event,
                    steering_event=self._steering_event,
                )
                await self._orchestrator.run()

            if self._stopped:
                await self.emit({"type": "status", "data": "stopped"})
            else:
                await self.emit({"type": "status", "data": "completed"})

        except Exception as e:
            import traceback as tb
            await self.emit({
                "type": "error",
                "data": f"SmartSwarm error: {e}\n{tb.format_exc()}",
            })

    def notify_steering(self) -> None:
        """Signal that a steering message is waiting — wakes up wait_seconds()."""
        self._steering_event.set()

    async def stop(self) -> None:
        """Stop planning engine and/or orchestrator."""
        self._stopped = True
        if self._planning_engine:
            try:
                await self._planning_engine.stop()
            except Exception:
                pass
        if self._orchestrator:
            try:
                await self._orchestrator.stop()
            except Exception:
                pass

    def get_state(self) -> dict:
        """Return orchestrator state if active."""
        if self._orchestrator:
            return self._orchestrator.get_state()
        return {"phase": "planning", "stopped": self._stopped}
