"""
Execution Engine
================

Runs the autonomous agent loop in-process using the Claude Agent SDK,
streaming rich events (tool_start, text_delta, tool_done, etc.) directly
to a WebSocket via the on_event callback.

Provides token-level streaming, direct tool events, and actual SDK cost
tracking — the only execution path in this system.
"""

import asyncio
import json
import traceback
from datetime import datetime
from pathlib import Path
from typing import Awaitable, Callable, Optional

from claude_agent_sdk import ClaudeSDKClient
from claude_agent_sdk._errors import ProcessError, CLIConnectionError, CLINotFoundError

from core.agent import (
    AgentContext,
    prepare_agent_context,
    _detect_phase_completion,
    _has_pending_tasks,
    _receive_response_safe,
    _PHASE_MODEL_MAP,
)
from core.client import create_client
from core.prompts import build_prompt, is_looping_phase
from state.session_state import SessionState
from state.session_checkpoint import ChainEntry
from state.task_list import TaskList
from features.context_primer import ContextPrimer


# Callback type: receives a dict event and sends it (e.g., via WebSocket)
OnEventCallback = Callable[[dict], Awaitable[None]]

# Phase-specific thinking effort — planning phases get deep reasoning,
# implementation phases get balanced speed/quality
PHASE_EFFORT = {
    "architect": "high", "initialize": "high",
    "analyze": "high", "plan": "high",
    "investigate": "high", "audit": "high", "scan": "high",
    "code": "medium", "implement": "medium",
    "migrate": "medium", "fix": "medium",
    "improve": "medium", "remediate": "medium",
}

CONTEXT_WARNING_TOKENS = 80_000  # Warn when input tokens approach context limit


def _extract_tool_result_text(content) -> str:
    """Extract plain text from MCP content blocks (list of {type, text})."""
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif hasattr(block, "text"):
                parts.append(getattr(block, "text", ""))
        return "\n".join(parts) if parts else str(content)
    return str(content)


def _is_known_block(content_str: str) -> bool:
    """True if content matches a known block pattern from hooks."""
    s = content_str.strip()
    return (
        "[STEERING]" in content_str
        or "[DIRECTIVE FROM ORCHESTRATOR]" in content_str
        or "[CAPABILITY]" in content_str
        or "Message from operator" in content_str
        or s.lower().startswith("blocked:")
        or "[BLOCKED]" in content_str
        or "Direct access to .swarmweaver/task_list.json is disabled" in content_str
    )


def _is_task_data_success(content_str: str) -> bool:
    """True if content looks like get_my_tasks/get_task_status success JSON (has blocked as status value)."""
    return (
        '"worker_id"' in content_str
        and ('"assigned_task_ids"' in content_str or '"tasks"' in content_str)
    )


class Engine:
    """
    In-process agent execution engine with SDK event streaming.

    Replaces subprocess-based execution with direct SDK integration,
    providing token-level streaming, real cost tracking, and rich tool events.
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
        approval_gates: bool = False,
        auto_pr: bool = False,
        phase_models: Optional[dict] = None,
        on_event: Optional[OnEventCallback] = None,
        # Swarm worker scope — enforces task boundaries via MCP tools
        task_scope: Optional[list[str]] = None,
        worker_id: int = 0,
        task_list_dir: Optional[Path] = None,
        mail_project_dir: Optional[Path] = None,
        # Per-worker budget and turn limits (smart swarm)
        max_budget_usd: Optional[float] = None,
        max_turns: Optional[int] = None,
        # LSP integration (smart swarm — per-worktree language servers)
        lsp_manager: Optional[object] = None,
        file_scope: Optional[list[str]] = None,
    ):
        self.project_dir = Path(project_dir)
        self.mode = mode
        self.model = model
        self.task_input = task_input
        self.spec_file = Path(spec_file) if spec_file else None
        self.max_iterations = max_iterations
        self.resume = resume
        self.budget_limit = budget_limit
        self.max_hours = max_hours
        self.approval_gates = approval_gates
        self.auto_pr = auto_pr
        self.phase_models = phase_models
        self._on_event = on_event or self._noop_event
        self._current_client: Optional[ClaudeSDKClient] = None
        self._stopped = False
        # Worker scope (swarm mode): scoped MCP tools so agent only sees its tasks
        self._task_scope: Optional[list[str]] = task_scope
        self._worker_id: int = worker_id
        self._task_list_dir: Path = Path(task_list_dir) if task_list_dir else self.project_dir
        self._mail_project_dir: Optional[Path] = Path(mail_project_dir) if mail_project_dir else None
        self._ctx: Optional[AgentContext] = None
        # Per-worker budget/turn caps (passed through to create_client)
        self._max_budget_usd: Optional[float] = max_budget_usd
        self._max_turns: Optional[int] = max_turns
        # Cumulative token counters updated in real-time from message_start / message_delta
        self._cumulative_input_tokens: int = 0
        self._cumulative_output_tokens: int = 0
        self._cumulative_cache_read_tokens: int = 0
        self._cumulative_cache_creation_tokens: int = 0
        self._context_warning_sent: bool = False
        # LSP integration
        self._lsp_manager = lsp_manager
        self._file_scope: Optional[list[str]] = file_scope

    @staticmethod
    async def _noop_event(event: dict) -> None:
        pass

    async def emit(self, event: dict) -> None:
        """Emit an event to the callback, adding timestamp if missing."""
        if "timestamp" not in event:
            event["timestamp"] = datetime.utcnow().isoformat() + "Z"
        event_type = event.get("type", "?")
        if event_type in ("tool_start", "tool_done", "tool_input_complete", "tool_error", "tool_blocked"):
            print(f"[NATIVE EMIT] {event_type}: tool={event.get('tool', event.get('id', '?'))}", flush=True)
        try:
            await self._on_event(event)
        except Exception as e:
            print(f"[WARNING] emit() callback failed for event '{event_type}': {e}", flush=True)

    async def run(self) -> None:
        """
        Main execution loop: iterate phases, create client per session,
        stream events to the callback.
        """
        try:
            await self.emit({"type": "status", "data": "running"})

            # Prepare shared context
            self._ctx = prepare_agent_context(
                project_dir=self.project_dir,
                mode=self.mode,
                model=self.model,
                task_input=self.task_input,
                spec_file=self.spec_file,
                resume=self.resume,
                budget_limit=self.budget_limit,
                max_hours=self.max_hours,
                quiet=True,
            )
            ctx = self._ctx

            starting_iteration = ctx.iteration
            iteration = ctx.iteration

            # Handle max_iterations=0
            if self.max_iterations is not None and self.max_iterations == 0:
                await self.emit({"type": "status", "data": "completed"})
                return

            # --- Main phase loop ---
            for phase in ctx.phases:
                if self._stopped:
                    break

                clean_phase = phase.rstrip("*")
                looping = is_looping_phase(phase)

                # Skip completed non-looping phases
                if not looping and _detect_phase_completion(
                    self.project_dir, self.mode, phase
                ):
                    await self.emit({
                        "type": "phase_skipped",
                        "data": {"phase": clean_phase, "reason": "already_completed"},
                    })
                    continue

                await self.emit({
                    "type": "phase_change",
                    "data": {
                        "phase": clean_phase,
                        "mode": self.mode,
                        "looping": looping,
                    },
                })

                phase_iteration = 0
                while True:
                    if self._stopped:
                        break

                    iteration += 1
                    phase_iteration += 1
                    iterations_this_run = iteration - starting_iteration

                    # Budget check
                    budget_exceeded, budget_reason = ctx.budget_tracker.is_budget_exceeded()
                    if budget_exceeded:
                        await self.emit({
                            "type": "budget_exceeded",
                            "data": {"reason": budget_reason},
                        })
                        break

                    # Max iterations check
                    if (
                        self.max_iterations is not None
                        and iterations_this_run > self.max_iterations
                    ):
                        await self.emit({
                            "type": "max_iterations_reached",
                            "data": {"iterations": iterations_this_run - 1},
                        })
                        break

                    # Task completion check for looping phases
                    if looping and phase_iteration > 1 and not _has_pending_tasks(
                        self.project_dir
                    ):
                        await self.emit({
                            "type": "phase_complete",
                            "data": {"phase": clean_phase, "reason": "all_tasks_done"},
                        })
                        break

                    # Determine session resume ID
                    resume_id = None
                    existing = ctx.existing_session
                    if existing and iteration == existing.iteration + 1:
                        saved_phase = getattr(existing, "phase", None)
                        if saved_phase is None or saved_phase == clean_phase:
                            resume_id = existing.session_id

                    # Phase model selection
                    phase_model = self.model
                    if self.phase_models:
                        pm_key = _PHASE_MODEL_MAP.get(clean_phase, "code")
                        if pm_key in self.phase_models:
                            phase_model = self.phase_models[pm_key]

                    # Check for mid-execution model override
                    override_path = ctx.paths.model_override
                    if override_path.exists():
                        try:
                            override_data = json.loads(override_path.read_text())
                            new_model = override_data.get("model", "")
                            if new_model and new_model != self.model:
                                self.model = new_model
                                phase_model = new_model
                            override_path.unlink()
                        except Exception as e:
                            print(f"[WARNING] Model override parse failed: {e}", flush=True)

                    # Build worker scope tools if this is a scoped swarm worker
                    _extra_mcp: dict | None = None
                    _extra_tools: list | None = None
                    if self._task_scope:
                        try:
                            from core.worker_tools import (
                                create_worker_tool_server,
                                WORKER_TOOL_NAMES,
                            )
                            _extra_mcp = {
                                "worker_tools": create_worker_tool_server(
                                    worker_id=self._worker_id,
                                    task_ids=self._task_scope,
                                    task_list_dir=self._task_list_dir,
                                    mail_project_dir=self._mail_project_dir,
                                )
                            }
                            _extra_tools = WORKER_TOOL_NAMES
                        except Exception as _wt_err:
                            print(f"[Engine] Worker tools init failed: {_wt_err}", flush=True)

                    # LSP tool injection for scoped workers
                    if self._lsp_manager and self._file_scope:
                        try:
                            from services.lsp_tools import (
                                create_lsp_tool_server,
                                LSP_TOOL_NAMES,
                            )
                            if _extra_mcp is None:
                                _extra_mcp = {}
                            if _extra_tools is None:
                                _extra_tools = []
                            _extra_mcp["lsp_tools"] = create_lsp_tool_server(
                                lsp_manager=self._lsp_manager,
                                worker_id=self._worker_id,
                                file_scope=self._file_scope,
                                worktree_path=self.project_dir,
                            )
                            _extra_tools.extend(LSP_TOOL_NAMES)
                        except Exception as _lsp_err:
                            print(f"[Engine] LSP tools init failed: {_lsp_err}", flush=True)

                    # Create SDK client
                    client = create_client(
                        self.project_dir,
                        phase_model,
                        resume_session_id=resume_id,
                        enable_checkpointing=True,
                        enable_subagents=True,
                        enable_audit_logging=True,
                        extra_mcp_servers=_extra_mcp,
                        extra_allowed_tools=_extra_tools,
                        max_budget_usd=self._max_budget_usd,
                        max_turns=self._max_turns,
                        thinking={"type": "adaptive"},
                        effort=PHASE_EFFORT.get(clean_phase, "medium"),
                    )
                    self._current_client = client

                    # Wire mail injection for swarm workers (M1-2)
                    if self._mail_project_dir and self._worker_id:
                        try:
                            from hooks import set_mail_store
                            from state.mail import MailStore
                            _worker_mail_store = MailStore(self._mail_project_dir)
                            _worker_mail_store.initialize()
                            set_mail_store(_worker_mail_store, f"worker-{self._worker_id}")
                        except Exception as _mail_err:
                            print(f"[Engine] Mail injection setup failed: {_mail_err}", flush=True)

                    # Wire LSP context for post-edit diagnostic hooks
                    if self._lsp_manager:
                        try:
                            from hooks.lsp_hooks import set_lsp_context
                            set_lsp_context(self._lsp_manager, self.project_dir)
                        except Exception as _lsp_ctx_err:
                            print(f"[Engine] LSP context setup failed: {_lsp_ctx_err}", flush=True)

                    # Smart context priming
                    context_prime = ""
                    if looping:
                        try:
                            tl = TaskList(self.project_dir)
                            tl.load()
                            next_task = tl.get_next_actionable()
                            if next_task:
                                primer = ContextPrimer(self.project_dir)
                                context_prime = primer.build_context_section(
                                    next_task.__dict__
                                )
                        except Exception:
                            pass

                    # Build prompt (use swarm-specific prompts when task_scope is set)
                    prompt = build_prompt(
                        mode=ctx.effective_mode,
                        phase=phase,
                        task_input=self.task_input,
                        task_input_short=self.task_input[:80] if self.task_input else "",
                        project_dir=self.project_dir,
                        use_worker_tools=self._task_scope is not None,
                    )

                    # Swarm worker: inject one-task-at-a-time reminder
                    if self._task_scope:
                        prompt = (
                            "STRICT: Work on ONE task at a time. Call start_task → implement → "
                            "complete_task → git commit → repeat. Never batch multiple tasks.\n\n"
                            + prompt
                        )

                    if context_prime:
                        prompt = prompt.replace("{context_prime}", context_prime)

                    # Inject context from previous phase
                    structured_cp = ctx.chain_manager.get_structured_checkpoint(ctx.chain_id)
                    prev_summary = ctx.chain_manager.get_previous_summary(ctx.chain_id)
                    if structured_cp:
                        done_count = len(structured_cp.get("completed", []))
                        pending = structured_cp.get("pending_count", 0)
                        last_phase = structured_cp.get("phase", "unknown")
                        in_prog = structured_cp.get("in_progress", [])
                        in_prog_str = ", ".join(f"{t['id']}: {t['title'][:30]}" for t in in_prog[:3]) if in_prog else "none"
                        cp_text = (
                            f"[CONTEXT] Previous phase '{last_phase}': {done_count} tasks done, "
                            f"{pending} pending. In-progress: {in_prog_str}."
                        )
                        prompt = f"{cp_text}\n\n{prompt}"
                    elif prev_summary:
                        prompt = f"Previous session summary: {prev_summary}\n\n{prompt}"

                    # Stream the session
                    session_start_time = datetime.now()

                    # Emit session start (includes start_time for frontend timer)
                    await self.emit({
                        "type": "session_start",
                        "data": {
                            "session": iteration,
                            "phase": clean_phase,
                            "model": phase_model,
                            "start_time": session_start_time.isoformat(),
                        },
                    })
                    try:
                        async with client:
                            # Emit MCP server status so the frontend Processes panel shows them
                            try:
                                mcp_status = await client.get_mcp_status()
                                if mcp_status:
                                    servers = [
                                        {"name": name, "status": str(info)}
                                        for name, info in mcp_status.items()
                                    ]
                                    await self.emit({"type": "mcp_servers", "servers": servers})
                            except Exception as e:
                                print(f"[WARNING] MCP server status report failed: {e}", flush=True)

                            status, response, session_id, usage = (
                                await self._stream_session(client, prompt)
                            )
                    except ProcessError as e:
                        error_detail = f"Claude CLI process failed (exit code {e.exit_code}): {e}"
                        if hasattr(e, 'stderr') and e.stderr:
                            error_detail += f"\nstderr: {e.stderr[:1000]}"
                        await self.emit({"type": "engine_error", "data": {"error": error_detail, "phase": clean_phase}})
                        raise
                    except CLINotFoundError as e:
                        await self.emit({"type": "engine_error", "data": {"error": f"Claude CLI not found: {e}", "phase": clean_phase}})
                        raise
                    except CLIConnectionError as e:
                        await self.emit({"type": "engine_error", "data": {"error": f"CLI connection failed: {e}", "phase": clean_phase}})
                        raise

                    self._current_client = None

                    # Save session state
                    if session_id:
                        state = SessionState(
                            session_id=session_id,
                            created_at=(
                                existing.created_at
                                if existing
                                else datetime.now()
                            ),
                            last_used=datetime.now(),
                            iteration=iteration,
                            model=phase_model,
                            phase=clean_phase,
                            chain_id=ctx.chain_id,
                            sequence_number=ctx.sequence_number,
                        )
                        ctx.session_manager.save(state)
                        ctx.existing_session = state
                        existing = state

                    # Record real costs from SDK
                    if usage:
                        ctx.budget_tracker.record_real_usage(
                            input_tokens=usage.get("input_tokens", 0),
                            output_tokens=usage.get("output_tokens", 0),
                            cost_usd=usage.get("cost_usd", 0.0),
                            model=phase_model,
                        )
                    else:
                        # Fallback to estimated if SDK didn't provide usage
                        response_len = len(response) if response else 0
                        estimated_output = max(200, response_len // 4)
                        estimated_input = max(500, len(prompt) // 4)
                        ctx.budget_tracker.record_usage(
                            estimated_input, estimated_output, phase_model
                        )

                    # Push budget update
                    bs = ctx.budget_tracker.get_status()
                    await self.emit({
                        "type": "budget_update",
                        "data": {
                            "total_input_tokens": bs["total_input_tokens"],
                            "total_output_tokens": bs["total_output_tokens"],
                            "estimated_cost_usd": bs["estimated_cost_usd"],
                            "real_cost_usd": bs["real_cost_usd"],
                            "session_count": bs["session_count"],
                        },
                    })

                    # Save structured checkpoint for cross-phase context
                    try:
                        tl_snap = TaskList(self.project_dir)
                        tl_snap.load()
                        structured_cp = {
                            "completed": [t.id for t in tl_snap.tasks if t.status == "done"],
                            "in_progress": [{"id": t.id, "title": t.title} for t in tl_snap.tasks if t.status == "in_progress"],
                            "pending_count": tl_snap.pending_count,
                            "phase": clean_phase,
                            "iteration": iteration,
                            "timestamp": datetime.utcnow().isoformat() + "Z",
                        }
                        ctx.chain_manager.save_structured_checkpoint(ctx.chain_id, structured_cp)
                    except Exception as e:
                        print(f"[WARNING] Structured checkpoint save failed: {e}", flush=True)

                    # Push session result
                    await self.emit({
                        "type": "session_result",
                        "data": {
                            "session": iteration,
                            "phase": clean_phase,
                            "status": status,
                            "total_cost_usd": usage.get("cost_usd", 0.0) if usage else 0.0,
                            "input_tokens": usage.get("input_tokens", 0) if usage else 0,
                            "output_tokens": usage.get("output_tokens", 0) if usage else 0,
                            "duration_s": (datetime.now() - session_start_time).total_seconds(),
                        },
                    })

                    # Record in chain
                    if session_id:
                        tl_chain = TaskList(self.project_dir)
                        tl_chain.load()
                        tasks_done = (
                            len([t for t in tl_chain.tasks if t.status == "done"])
                            if tl_chain.tasks
                            else 0
                        )
                        tasks_total = len(tl_chain.tasks) if tl_chain.tasks else 0
                        summary_text = ""
                        if response:
                            summary_text = response.strip()[:200]
                            if len(response.strip()) > 200:
                                summary_text += "..."
                        chain_entry = ChainEntry(
                            session_id=session_id,
                            chain_id=ctx.chain_id,
                            sequence_number=ctx.sequence_number,
                            checkpoint_summary=summary_text,
                            start_time=session_start_time.isoformat(),
                            end_time=datetime.now().isoformat(),
                            phase=clean_phase,
                            tasks_completed=tasks_done,
                            tasks_total=tasks_total,
                            cost=bs["real_cost_usd"] or bs["estimated_cost_usd"],
                        )
                        ctx.chain_manager.add_entry(chain_entry)
                        ctx.sequence_number += 1

                    # Push task list update
                    try:
                        tl_push = TaskList(self.project_dir)
                        if tl_push.load() and tl_push.tasks:
                            await self.emit({
                                "type": "task_list_update",
                                "data": tl_push.to_dict(),
                            })
                    except Exception as e:
                        print(f"[WARNING] task_list_update emit failed: {e}", flush=True)

                    # Self-healing verification loop
                    if status == "continue" and looping:
                        try:
                            from features.verification import VerificationManager

                            verifier = VerificationManager(self.project_dir)
                            actions = verifier.verify_completed_tasks()
                            for action in actions:
                                await self.emit({
                                    "type": "verification",
                                    "data": action,
                                })
                        except Exception as e:
                            print(f"[WARNING] Verification loop failed: {e}", flush=True)

                    # Approval gates
                    if status == "continue" and self.approval_gates and looping:
                        await self._handle_approval_gate(ctx, clean_phase, phase_iteration)

                    # Handle error / stop status
                    if status == "stopped" or self._stopped:
                        # User-requested stop — break all loops cleanly
                        break
                    elif status == "error":
                        ctx.budget_tracker.record_error()
                        # Auth errors are fatal — stop immediately
                        if isinstance(response, str) and "Authentication failed" in response:
                            self._stopped = True
                            break
                        await asyncio.sleep(3)
                    elif status == "image_error":
                        # Clear session to force fresh start
                        if ctx.paths.session_state.exists():
                            ctx.paths.session_state.unlink()
                        ctx.existing_session = None
                        break
                    elif status == "continue":
                        await asyncio.sleep(1)

                    # Clean up old checkpoints
                    ctx.checkpoint_manager.clear_old_checkpoints(keep_last_n=100)

                    if not looping:
                        break

                # Check max iterations for outer loop
                if (
                    self.max_iterations is not None
                    and (iteration - starting_iteration) >= self.max_iterations
                ):
                    break

            # --- Post-session ---
            await self._post_session(ctx)
            if self._stopped:
                await self.emit({"type": "status", "data": "stopped"})
            else:
                await self.emit({"type": "status", "data": "completed"})

        except (ProcessError, CLINotFoundError, CLIConnectionError):
            # SDK errors must propagate for retry logic in smart_orchestrator
            raise
        except Exception as e:
            if self._stopped:
                # Exception caused by interrupt — emit stopped, not error
                await self.emit({"type": "status", "data": "stopped"})
            else:
                await self.emit({
                    "type": "error",
                    "data": f"Engine error: {e}\n{traceback.format_exc()}",
                })

    async def _stream_session(
        self,
        client: ClaudeSDKClient,
        prompt: str,
    ) -> tuple[str, str, Optional[str], Optional[dict]]:
        """
        Stream one SDK session, emitting tool and text events.

        Pattern adapted from _stream_wizard_response() in server.py.

        Returns:
            (status, response_text, session_id, usage_dict)
            where usage_dict = {"input_tokens": N, "output_tokens": N, "cost_usd": F}
        """
        from claude_agent_sdk.types import StreamEvent

        session_id = None
        response_text = ""
        usage = None
        # Track tool IDs that got a tool_start via StreamEvent so we
        # don't double-emit from AssistantMessage.
        streamed_tool_ids: set[str] = set()
        current_tool_name = None
        current_tool_id = None

        try:
            await client.query(prompt)

            msg_count = 0
            async for msg in _receive_response_safe(client):
                if self._stopped:
                    break

                msg_type = type(msg).__name__
                msg_count += 1
                if msg_count <= 5 or msg_type in ("AssistantMessage", "UserMessage"):
                    print(f"[NATIVE MSG #{msg_count}] type={msg_type}", flush=True)

                # --- StreamEvent: text deltas + optional tool streaming ---
                if isinstance(msg, StreamEvent):
                    event = msg.event
                    event_type = event.get("type")

                    if event_type == "message_start":
                        # Real-time token counts — includes cache_read and cache_creation
                        msg_usage = event.get("message", {}).get("usage", {})
                        it = msg_usage.get("input_tokens", 0)
                        cr = msg_usage.get("cache_read_input_tokens", 0)
                        cc = msg_usage.get("cache_creation_input_tokens", 0)
                        if it or cr or cc:
                            self._cumulative_input_tokens += it
                            self._cumulative_cache_read_tokens += cr
                            self._cumulative_cache_creation_tokens += cc
                            await self.emit({
                                "type": "token_update",
                                "input_tokens": self._cumulative_input_tokens,
                                "output_tokens": self._cumulative_output_tokens,
                                "cache_read_tokens": self._cumulative_cache_read_tokens,
                                "cache_creation_tokens": self._cumulative_cache_creation_tokens,
                            })

                            # Context budget warning
                            if (self._cumulative_input_tokens > CONTEXT_WARNING_TOKENS
                                    and not self._context_warning_sent):
                                self._context_warning_sent = True
                                await self.emit({
                                    "type": "context_budget_warning",
                                    "data": {
                                        "input_tokens": self._cumulative_input_tokens,
                                        "threshold": CONTEXT_WARNING_TOKENS,
                                    },
                                })
                                try:
                                    from features.steering import write_steering_message
                                    write_steering_message(
                                        self.project_dir,
                                        f"[CONTEXT WARNING] Approaching context limit "
                                        f"({self._cumulative_input_tokens:,} tokens). "
                                        f"Be concise. Commit often. Focus on current task.",
                                        "instruction",
                                    )
                                except Exception as e:
                                    print(f"[WARNING] Tool event emit failed: {e}", flush=True)

                    elif event_type == "message_delta":
                        # Real-time output token count from the API
                        ot = event.get("usage", {}).get("output_tokens", 0)
                        if ot:
                            self._cumulative_output_tokens += ot
                            await self.emit({
                                "type": "token_update",
                                "input_tokens": self._cumulative_input_tokens,
                                "output_tokens": self._cumulative_output_tokens,
                                "cache_read_tokens": self._cumulative_cache_read_tokens,
                                "cache_creation_tokens": self._cumulative_cache_creation_tokens,
                            })

                    elif event_type == "content_block_start":
                        content_block = event.get("content_block", {})
                        if content_block.get("type") == "tool_use":
                            current_tool_name = content_block.get("name", "Unknown")
                            current_tool_id = content_block.get("id", "")
                            streamed_tool_ids.add(current_tool_id)
                            await self.emit({
                                "type": "tool_start",
                                "tool": current_tool_name,
                                "id": current_tool_id,
                            })

                    elif event_type == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta":
                            text = delta.get("text", "")
                            response_text += text
                            await self.emit({
                                "type": "text_delta",
                                "text": text,
                            })
                        elif delta.get("type") == "thinking_delta":
                            thinking_chunk = delta.get("thinking", "")
                            if thinking_chunk:
                                await self.emit({
                                    "type": "thinking_delta",
                                    "data": thinking_chunk,
                                })
                        elif delta.get("type") == "input_json_delta":
                            chunk = delta.get("partial_json", "")
                            if current_tool_id:
                                await self.emit({
                                    "type": "tool_input_delta",
                                    "id": current_tool_id,
                                    "chunk": chunk,
                                })

                    elif event_type == "content_block_stop":
                        # Do NOT emit tool_done here — that fires when the assistant
                        # finishes the tool block, not when execution completes.
                        # tool_done is emitted only when we have ToolResultBlock.
                        if current_tool_name:
                            current_tool_name = None
                            current_tool_id = None

                # --- ResultMessage: session completion ---
                elif msg_type == "ResultMessage":
                    if hasattr(msg, "session_id") and msg.session_id:
                        session_id = msg.session_id
                    elif hasattr(msg, "sessionId") and msg.sessionId:
                        session_id = msg.sessionId

                    # Extract real cost and usage from SDK (ResultMessage.usage is a dict)
                    usage = {}
                    if hasattr(msg, "total_cost_usd"):
                        usage["cost_usd"] = msg.total_cost_usd or 0.0
                    if hasattr(msg, "usage") and msg.usage:
                        u = msg.usage  # dict with input_tokens, output_tokens, cache_* keys
                        if isinstance(u, dict):
                            usage["input_tokens"] = u.get("input_tokens", 0) or 0
                            usage["output_tokens"] = u.get("output_tokens", 0) or 0
                            usage["cache_read_tokens"] = u.get("cache_read_input_tokens", 0) or 0
                            usage["cache_creation_tokens"] = u.get("cache_creation_input_tokens", 0) or 0
                        else:
                            usage["input_tokens"] = getattr(u, "input_tokens", 0) or 0
                            usage["output_tokens"] = getattr(u, "output_tokens", 0) or 0
                            usage["cache_read_tokens"] = getattr(u, "cache_read_input_tokens", 0) or 0
                            usage["cache_creation_tokens"] = getattr(u, "cache_creation_input_tokens", 0) or 0
                    usage.setdefault("input_tokens", 0)
                    usage.setdefault("output_tokens", 0)
                    usage.setdefault("cache_read_tokens", 0)
                    usage.setdefault("cache_creation_tokens", 0)
                    usage.setdefault("cost_usd", 0.0)

                # --- AssistantMessage: primary tool_start source ---
                elif msg_type == "AssistantMessage" and hasattr(msg, "content"):
                    block_types = [type(b).__name__ for b in msg.content]
                    print(f"[NATIVE ASSISTANT] blocks={block_types}", flush=True)
                    for block in msg.content:
                        block_type = type(block).__name__
                        if block_type == "TextBlock" and hasattr(block, "text"):
                            response_text += block.text

                        elif block_type == "ThinkingBlock" and hasattr(block, "thinking"):
                            thinking_text = getattr(block, "thinking", "")
                            if thinking_text and len(thinking_text) > 10:
                                agent_label = f"worker-{self._worker_id}" if self._worker_id else ""
                                await self.emit({
                                    "type": "thinking_block",
                                    "data": {
                                        "text": thinking_text,
                                        "truncated": False,
                                        "agent": agent_label,
                                    },
                                })
                        elif block_type == "ToolUseBlock" and hasattr(block, "name"):
                            tool_id = getattr(block, "id", "")
                            tool_name = block.name
                            # Emit tool_start if StreamEvent didn't already
                            if tool_id not in streamed_tool_ids:
                                await self.emit({
                                    "type": "tool_start",
                                    "tool": tool_name,
                                    "id": tool_id,
                                })
                            # Always emit the complete input
                            tool_input = getattr(block, "input", {})
                            if tool_input:
                                try:
                                    input_json = json.dumps(tool_input, ensure_ascii=False)
                                except (TypeError, ValueError):
                                    input_json = str(tool_input)
                                # File write/edit tools need more room for code content
                                max_input_len = 50000 if tool_name in ("Write", "Edit") else 10000
                                await self.emit({
                                    "type": "tool_input_complete",
                                    "id": tool_id,
                                    "tool": tool_name,
                                    "input": input_json[:max_input_len],
                                })

                # --- UserMessage: tool results + tool_done ---
                elif msg_type == "UserMessage" and hasattr(msg, "content"):
                    content = msg.content
                    if isinstance(content, str):
                        continue
                    for block in content:
                        block_type = type(block).__name__
                        if block_type == "ToolResultBlock":
                            result_content = getattr(block, "content", "")
                            is_error = getattr(block, "is_error", False)
                            tool_use_id = getattr(block, "tool_use_id", "")

                            content_str = _extract_tool_result_text(result_content)
                            is_task_data = _is_task_data_success(content_str)
                            is_known_block = _is_known_block(content_str)

                            if is_known_block and not is_task_data:
                                await self.emit({
                                    "type": "tool_blocked",
                                    "id": tool_use_id,
                                    "reason": content_str[:500],
                                })
                            elif is_error:
                                await self.emit({
                                    "type": "tool_error",
                                    "id": tool_use_id,
                                    "error": content_str[:500],
                                })
                            else:
                                await self.emit({
                                    "type": "tool_result",
                                    "id": tool_use_id,
                                    "status": "success",
                                    "content": content_str[:2048],
                                })

                            # Always emit tool_done when we have the result
                            await self.emit({
                                "type": "tool_done",
                                "id": tool_use_id,
                                "tool": "",
                            })

            # Detect authentication errors returned as text (not raised as exceptions)
            if response_text and "authentication_error" in response_text:
                auth_msg = "Authentication failed. "
                if "expired" in response_text.lower():
                    auth_msg += "OAuth token has expired — run 'claude setup-token' to refresh."
                elif "invalid" in response_text.lower():
                    auth_msg += "Invalid API key or OAuth token."
                else:
                    auth_msg += "Check your CLAUDE_CODE_OAUTH_TOKEN or ANTHROPIC_API_KEY."
                await self.emit({
                    "type": "session_error",
                    "data": {"error": auth_msg},
                })
                return "error", auth_msg, session_id, usage

            return "continue", response_text, session_id, usage

        except Exception as e:
            # User-triggered stop — ProcessError exit -15 (SIGTERM) is expected.
            # Return "stopped" cleanly; do not emit session_error to the frontend.
            if self._stopped:
                return "stopped", response_text, session_id, usage

            error_str = str(e)
            if "image" in error_str.lower() and (
                "dimension" in error_str.lower() or "size" in error_str.lower()
            ):
                return "image_error", error_str, session_id, usage

            await self.emit({
                "type": "session_error",
                "data": {"error": error_str[:500]},
            })
            return "error", error_str, session_id, usage

    async def _handle_approval_gate(
        self, ctx: AgentContext, clean_phase: str, phase_iteration: int
    ) -> None:
        """Handle approval gate between sessions."""
        try:
            from features.approval import request_approval, wait_for_approval

            tl = TaskList(self.project_dir)
            tl.load()
            completed = [t.title for t in tl.tasks if t.status == "done"]
            remaining = [
                t.title for t in tl.tasks if t.status in ("pending", "in_progress")
            ]
            if not completed:
                return

            req_id = request_approval(
                self.project_dir,
                gate_type="phase_complete",
                summary=f"Phase '{clean_phase}' session {phase_iteration} complete",
                tasks_completed=completed[-3:],
                tasks_remaining=remaining[:5],
            )

            await self.emit({
                "type": "approval_request",
                "data": {
                    "request_id": req_id,
                    "gate_type": "phase_complete",
                    "summary": f"Phase '{clean_phase}' session {phase_iteration} complete",
                    "tasks_completed": completed[-3:],
                    "tasks_remaining": remaining[:5],
                },
            })

            # Wait for approval (polls disk)
            decision, feedback = await wait_for_approval(self.project_dir)

            await self.emit({
                "type": "approval_resolved",
                "data": {"decision": decision, "feedback": feedback},
            })

            if decision == "rejected":
                done_tasks = [t for t in tl.tasks if t.status == "done"]
                if done_tasks:
                    last_done = done_tasks[-1]
                    tl.reopen_task(last_done.id, feedback or "Rejected by operator")
            elif decision == "reflect":
                from features.steering import write_steering_message

                write_steering_message(
                    self.project_dir,
                    feedback or "Please reflect on the approach",
                    "reflect",
                )
        except Exception as e:
            print(f"[WARNING] Approval gate update failed: {e}", flush=True)

    async def _post_session(self, ctx: AgentContext) -> None:
        """Post-session cleanup: memory harvesting, insights, identity update."""
        budget_final = ctx.budget_tracker.get_status()

        # Harvest session reflections
        try:
            from features.memory import AgentMemory

            mem = AgentMemory()
            reflections_file = ctx.paths.session_reflections

            if reflections_file.exists():
                try:
                    reflections = json.loads(
                        reflections_file.read_text(encoding="utf-8")
                    )
                    if isinstance(reflections, list):
                        saved_count = 0
                        for entry in reflections:
                            if not isinstance(entry, dict) or not entry.get("content"):
                                continue
                            category = entry.get("category", "pattern")
                            if category not in (
                                "pattern",
                                "mistake",
                                "solution",
                                "preference",
                            ):
                                category = "pattern"
                            tags = entry.get("tags", [])
                            if self.mode not in tags:
                                tags.append(self.mode)
                            mem.add(
                                category,
                                entry["content"],
                                tags=tags,
                                project_source=str(self.project_dir),
                            )
                            saved_count += 1
                        reflections_file.unlink(missing_ok=True)
                except (json.JSONDecodeError, OSError):
                    pass

            # Auto-save error pattern if session had consecutive errors
            if budget_final["consecutive_errors"] > 0:
                mem.add(
                    "mistake",
                    f"Session ended with {budget_final['consecutive_errors']} "
                    f"consecutive errors in {self.mode} mode",
                    tags=[self.mode, "errors"],
                    project_source=str(self.project_dir),
                )

            # Auto-save success pattern
            if not _has_pending_tasks(self.project_dir) and budget_final["session_count"] > 0:
                tl_path = ctx.paths.resolve_read("task_list.json")
                if tl_path.exists():
                    try:
                        tl = TaskList(self.project_dir)
                        tl.load()
                        done_count = len(
                            [t for t in tl.tasks if t.status == "done"]
                        )
                        if done_count > 0:
                            cost = budget_final["real_cost_usd"] or budget_final["estimated_cost_usd"]
                            mem.add(
                                "pattern",
                                f"Successfully completed all {done_count} tasks in {self.mode} mode "
                                f"across {budget_final['session_count']} sessions "
                                f"(${cost:.4f})",
                                tags=[self.mode, "completed", "success"],
                                project_source=str(self.project_dir),
                            )
                    except Exception:
                        pass
        except Exception:
            pass

        # Auto-PR on completion
        if self.auto_pr and not _has_pending_tasks(self.project_dir):
            try:
                from features.github_integration import GitHubManager
                import re

                gh = GitHubManager(self.project_dir)
                if gh.is_gh_available():
                    slug = (
                        re.sub(
                            r"[^a-zA-Z0-9]+",
                            "-",
                            (self.task_input or self.mode)[:40],
                        )
                        .strip("-")
                        .lower()
                    )
                    branch_name = f"swarmweaver/{self.mode}/{slug}"
                    if gh.create_branch(branch_name):
                        if gh.push_branch():
                            pr_title = f"[SwarmWeaver] {self.mode}: {(self.task_input or 'changes')[:50]}"
                            pr = gh.create_pr(
                                title=pr_title,
                                body=f"Automated changes by SwarmWeaver in {self.mode} mode.",
                            )
                            if pr.get("success"):
                                await self.emit({
                                    "type": "github_pr",
                                    "data": {"url": pr["url"]},
                                })
            except Exception:
                pass

        # Auto-harvest session insights from audit log
        _session_analysis = None
        try:
            from services.insights import SessionInsightAnalyzer

            analyzer = SessionInsightAnalyzer(self.project_dir)
            analysis = analyzer.analyze_audit_log()
            _session_analysis = analysis
            if analysis.insights:
                count = analyzer.record_to_memory(
                    analysis, project_source=str(self.project_dir)
                )
        except Exception:
            pass

        # Harvest insights into project-scoped expertise
        try:
            from features.project_expertise import ProjectExpertise

            proj_expertise = ProjectExpertise(self.project_dir)
            pe_reflections = ctx.paths.session_reflections
            if pe_reflections.exists():
                pe_data = json.loads(pe_reflections.read_text(encoding="utf-8"))
                if isinstance(pe_data, list):
                    for pe_entry in pe_data:
                        if not isinstance(pe_entry, dict) or not pe_entry.get(
                            "content"
                        ):
                            continue
                        pe_cat = pe_entry.get("category", "pattern")
                        if pe_cat not in (
                            "convention",
                            "pattern",
                            "failure",
                            "decision",
                            "reference",
                        ):
                            pe_cat = "pattern"
                        proj_expertise.add(
                            content=pe_entry["content"],
                            category=pe_cat,
                            domain=pe_entry.get("domain", ""),
                            tags=pe_entry.get("tags", []),
                            source_file=pe_entry.get("source_file", ""),
                        )
        except Exception:
            pass

        # Update agent identity with session insights
        try:
            tl_final = TaskList(self.project_dir)
            tl_final.load()
            completed_tasks = [
                {"id": t.id, "title": t.title}
                for t in tl_final.tasks
                if t.status == "done"
            ]
            identity = ctx.identity_store.update_after_session(
                name="main",
                completed_tasks=completed_tasks,
                domains=[self.mode],
            )
            # Enrich identity with session insights
            if _session_analysis is not None:
                try:
                    from services.insights import enrich_identity_from_insights
                    from datetime import datetime as dt

                    enrich_identity_from_insights(
                        identity, _session_analysis, 0.0
                    )
                    ctx.identity_store.save(identity)
                except Exception:
                    pass
        except Exception:
            pass

    async def stop(self) -> None:
        """Interrupt the current SDK client and stop the engine."""
        self._stopped = True
        self._cumulative_cache_read_tokens = 0
        self._cumulative_cache_creation_tokens = 0
        if self._current_client:
            try:
                await self._current_client.interrupt()
            except Exception:
                pass

    async def send_interrupt(self) -> None:
        """Send a non-destructive interrupt to the running client.

        Forces the agent to finish its current turn and start a fresh one,
        allowing it to read new steering messages — without terminating the engine.
        """
        if self._current_client and not self._stopped:
            try:
                await self._current_client.interrupt()
            except Exception:
                pass
