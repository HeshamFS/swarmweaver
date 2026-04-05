"""
Agent Session Logic - Multi-Mode
=================================

Core agent interaction functions for running autonomous coding sessions.
Supports multiple operation modes with phase-based execution:

  greenfield: initialize → code* (loop)
  feature:    analyze → plan → implement* (loop)
  refactor:   analyze → plan → migrate* (loop)
  fix:        investigate → fix* (loop)
  evolve:     audit → improve* (loop)

Each phase runs as a separate agent session with a fresh context window.
Progress persists through files on disk (task_list.json, codebase_profile.json,
claude-progress.txt, git commits).
"""

import asyncio
import json as _json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from claude_agent_sdk import ClaudeSDKClient

from utils.api_keys import (
    get_missing_api_keys,
    collect_missing_api_keys,
    check_and_prompt_api_keys,
)
from state.checkpoints import CheckpointManager, Checkpoint
from state.session_state import SessionManager, SessionState
from state.session_checkpoint import ChainManager, ChainEntry
from state.budget import BudgetTracker
from state.agent_identity import AgentIdentityStore
from core.client import create_client
from core.paths import get_paths, ProjectPaths
from hooks import set_stop_callback
from utils.progress import print_session_header, print_progress_summary
from core.prompts import (
    copy_spec_to_project,
    build_prompt,
    get_phases,
    is_looping_phase,
    write_task_input,
)
from state.task_list import TaskList


# Configuration
AUTO_CONTINUE_DELAY_SECONDS = 3

# Phase-to-model mapping: maps phase names to phase_models keys
_PHASE_MODEL_MAP = {
    "architect": "architect",
    "initialize": "plan",
    "analyze": "plan",
    "plan": "plan",
    "investigate": "plan",
    "audit": "plan",
    "scan": "plan",
    "code": "code",
    "implement": "code",
    "migrate": "code",
    "fix": "code",
    "improve": "code",
    "remediate": "code",
}


@dataclass
class AgentContext:
    """Shared context for both CLI (run_autonomous_agent) and server (NativeEngine)."""
    paths: ProjectPaths
    checkpoint_manager: CheckpointManager
    session_manager: SessionManager
    chain_manager: ChainManager
    budget_tracker: BudgetTracker
    identity_store: AgentIdentityStore
    effective_mode: str
    phases: list
    iteration: int
    chain_id: str
    sequence_number: int
    existing_session: Optional[SessionState]
    task_list: TaskList


def prepare_agent_context(
    project_dir: Path,
    mode: str,
    model: str,
    task_input: str = "",
    spec_file: Optional[Path] = None,
    resume: bool = True,
    budget_limit: float = 0.0,
    max_hours: float = 0.0,
    quiet: bool = False,
) -> AgentContext:
    """
    Shared setup logic for agent sessions.

    Used by both run_autonomous_agent() (CLI) and NativeEngine (server).
    Handles mode detection, file setup, manager initialization, and phase resolution.

    Args:
        project_dir: Project directory path
        mode: Operation mode
        model: Claude model to use
        task_input: User's task description
        spec_file: Optional spec file path
        resume: Whether to resume previous session
        budget_limit: Budget limit in USD
        max_hours: Max runtime hours
        quiet: If True, suppress print statements (for server use)
    """
    def _print(msg: str) -> None:
        if not quiet:
            print(msg)

    # Create project directory
    project_dir.mkdir(parents=True, exist_ok=True)

    paths = get_paths(project_dir)

    # --- Fresh start: clean phase outputs so phases re-run ---
    if not resume:
        fresh_mode = mode
        if mode == "greenfield" and task_input and not spec_file:
            fresh_mode = "greenfield_from_idea"
        _clean_phase_outputs(project_dir, fresh_mode, has_spec_file=bool(spec_file))

    # --- Mode-specific setup ---
    effective_mode = mode
    if mode == "greenfield" and task_input and not spec_file:
        app_spec_path = paths.resolve_read("app_spec.txt")
        if not app_spec_path.exists():
            effective_mode = "greenfield_from_idea"
            _print("\n[ARCHITECT] Brief idea detected - will generate app_spec.txt first")
            write_task_input(project_dir, task_input)
        else:
            _print("[ARCHITECT] app_spec.txt already exists, skipping architect phase")

    if effective_mode == "greenfield" or effective_mode == "greenfield_from_idea":
        if effective_mode == "greenfield":
            copy_spec_to_project(project_dir, spec_file=spec_file)
    else:
        if task_input:
            write_task_input(project_dir, task_input)
        if spec_file and mode == "feature":
            copy_spec_to_project(project_dir, spec_file=spec_file)

    # --- Initialize managers ---
    checkpoint_manager = CheckpointManager(project_dir)
    checkpoint_manager.load()
    _print(f"Checkpoint manager: {len(checkpoint_manager)} checkpoints loaded")

    session_manager = SessionManager(project_dir)
    existing_session = session_manager.load() if resume else None
    if existing_session:
        _print(f"Found existing session: {existing_session.session_id[:16]}...")

    # Detect interrupted session via transcript + inject resume context
    if resume:
        try:
            from services.transcript import TranscriptReader
            transcript_dir = project_dir / ".swarmweaver" / "transcripts"
            if transcript_dir.is_dir():
                _transcripts = sorted(
                    transcript_dir.glob("*.jsonl"),
                    key=lambda p: p.stat().st_mtime, reverse=True,
                )
                if _transcripts:
                    _entries = TranscriptReader.load_transcript(_transcripts[0])
                    _info = TranscriptReader.detect_interruption(_entries)
                    if _info.get("interrupted"):
                        _print(
                            f"[RESUME] Interrupted session detected "
                            f"(turn={_info.get('last_turn', 0)}, "
                            f"phase={_info.get('last_phase', '')}, "
                            f"tasks={_info.get('tasks_done', 0)}/{_info.get('tasks_total', 0)})"
                        )
                        _resume_ctx = TranscriptReader.build_resume_context(_entries)
                        try:
                            _progress_file = project_dir / ".swarmweaver" / "claude-progress.txt"
                            _progress_file.parent.mkdir(parents=True, exist_ok=True)
                            _existing_progress = ""
                            if _progress_file.exists():
                                _existing_progress = _progress_file.read_text(encoding="utf-8")
                            if "Session Recovery Context" not in _existing_progress:
                                with open(_progress_file, "a", encoding="utf-8") as _pf:
                                    _pf.write(f"\n\n{_resume_ctx}\n")
                        except OSError:
                            pass
        except Exception:
            pass


    # Session chain manager
    chain_manager = ChainManager(project_dir)
    if not resume:
        chain_id = chain_manager.start_new_chain()
        _print(f"[CHAIN] New chain started: {chain_id}")
    else:
        chain_id = chain_manager.get_or_create_chain_id()
        chain_entries = chain_manager.get_chain(chain_id)
        if chain_entries:
            _print(f"[CHAIN] Resuming chain {chain_id} ({len(chain_entries)} session(s))")
        else:
            _print(f"[CHAIN] Chain {chain_id} (new)")
    sequence_number = chain_manager.get_next_sequence_number(chain_id)

    # Budget tracker
    budget_tracker = BudgetTracker(project_dir, budget_limit=budget_limit, max_hours=max_hours)
    if budget_limit > 0:
        _print(f"Budget limit: ${budget_limit:.2f}")
    if max_hours > 0:
        _print(f"Max hours: {max_hours:.1f}")
    budget_status = budget_tracker.get_status()
    if budget_status["session_count"] > 0:
        _print(f"Budget: ${budget_status['estimated_cost_usd']:.4f} spent across {budget_status['session_count']} sessions")

    # Agent identity
    identity_store = AgentIdentityStore(project_dir)
    identity_store.get_or_create(name="main", capability="builder")
    _print("[IDENTITY] Main agent registered")

    # Task list
    task_list = TaskList(project_dir)
    task_list.load()

    # Phases
    phases = get_phases(effective_mode)

    # Iteration
    iteration = existing_session.iteration if existing_session else 0

    return AgentContext(
        paths=paths,
        checkpoint_manager=checkpoint_manager,
        session_manager=session_manager,
        chain_manager=chain_manager,
        budget_tracker=budget_tracker,
        identity_store=identity_store,
        effective_mode=effective_mode,
        phases=phases,
        iteration=iteration,
        chain_id=chain_id,
        sequence_number=sequence_number,
        existing_session=existing_session,
        task_list=task_list,
    )


def _patch_sdk_message_parser():
    """
    Patch the SDK's message parser to gracefully skip unknown message types
    (e.g. rate_limit_event) instead of crashing the entire session.

    The SDK's parse_message raises MessageParseError on unknown types, which
    kills the async generator and terminates the session. This patch makes it
    return None for unknown types so we can filter them out.
    """
    try:
        import claude_agent_sdk._internal.message_parser as mp

        _original_parse = mp.parse_message

        def _patched_parse(data):
            try:
                return _original_parse(data)
            except mp.MessageParseError as e:
                if "Unknown message type" in str(e):
                    msg_type = data.get("type", "unknown")
                    print(f"\n[SDK] Skipping unknown event: {msg_type}", flush=True)
                    return None  # Will be filtered in receive loop
                raise

        mp.parse_message = _patched_parse
        print("[SDK] Patched message parser for forward compatibility")
    except Exception as e:
        print(f"[SDK] Could not patch parser: {e}")


# Apply patch at import time
_patch_sdk_message_parser()


async def _receive_response_safe(client: ClaudeSDKClient):
    """
    Wrapper around client.receive_response() that filters out None messages
    (unknown types skipped by our patched parser).
    """
    async for msg in client.receive_response():
        if msg is not None:
            yield msg


async def run_agent_session(
    client: ClaudeSDKClient,
    message: str,
    project_dir: Path,
    checkpoint_manager: CheckpointManager,
    iteration: int,
) -> tuple[str, str, Optional[str]]:
    """
    Run a single agent session using Claude Agent SDK.

    Args:
        client: Claude SDK client
        message: The prompt to send
        project_dir: Project directory path
        checkpoint_manager: Manager for file checkpoints
        iteration: Current iteration number

    Returns:
        (status, response_text, session_id) where status is:
        - "continue" if agent should continue working
        - "error" if an error occurred
    """
    print("Sending prompt to Claude Agent SDK...\n")

    session_id = None
    tool_use_count = 0

    try:
        # Send the query
        await client.query(message)

        # Collect response text and show tool use
        response_text = ""
        async for msg in _receive_response_safe(client):
            msg_type = type(msg).__name__

            # Capture session_id from ResultMessage
            if msg_type == "ResultMessage":
                if hasattr(msg, "session_id") and msg.session_id:
                    session_id = msg.session_id
                elif hasattr(msg, "sessionId") and msg.sessionId:
                    session_id = msg.sessionId

            # Handle AssistantMessage (text and tool use)
            if msg_type == "AssistantMessage" and hasattr(msg, "content"):
                for block in msg.content:
                    block_type = type(block).__name__

                    if block_type == "TextBlock" and hasattr(block, "text"):
                        response_text += block.text
                        print(block.text, end="", flush=True)
                    elif block_type == "ToolUseBlock" and hasattr(block, "name"):
                        tool_use_count += 1
                        tool_name = block.name
                        print(f"\n[Tool: {tool_name}]", flush=True)
                        if hasattr(block, "input"):
                            try:
                                input_json = _json.dumps(block.input, ensure_ascii=False)
                            except (TypeError, ValueError):
                                input_json = str(block.input)
                            # File-mutating tools: send full JSON (capped at 100KB) so
                            # frontend can show diffs/content
                            if tool_name in ("Write", "Edit"):
                                cap = 100_000
                                if len(input_json) > cap:
                                    print(f"   Input: {input_json[:cap]}", flush=True)
                                else:
                                    print(f"   Input: {input_json}", flush=True)
                            else:
                                if len(input_json) > 500:
                                    print(f"   Input: {input_json[:500]}...", flush=True)
                                else:
                                    print(f"   Input: {input_json}", flush=True)

            # Handle UserMessage (tool results)
            elif msg_type == "UserMessage" and hasattr(msg, "content"):
                for block in msg.content:
                    block_type = type(block).__name__

                    if block_type == "ToolResultBlock":
                        result_content = getattr(block, "content", "")
                        is_error = getattr(block, "is_error", False)

                        if "blocked" in str(result_content).lower():
                            print(f"   [BLOCKED] {result_content}", flush=True)
                        elif is_error:
                            error_str = str(result_content)[:500]
                            print(f"   [Error] {error_str}", flush=True)
                        else:
                            print("   [Done]", flush=True)

        print("\n" + "-" * 70 + "\n")
        return "continue", response_text, session_id

    except Exception as e:
        error_str = str(e)
        print(f"Error during agent session: {error_str}")

        if "image" in error_str.lower() and ("dimension" in error_str.lower() or "size" in error_str.lower()):
            print("\n" + "=" * 60)
            print("  IMAGE SIZE ERROR DETECTED")
            print("=" * 60)
            print("The resumed session has too many large screenshots.")
            print("\nSolution: Start a fresh session with --no-resume")
            print("=" * 60)
            return "image_error", error_str, session_id

        import traceback
        traceback.print_exc()
        return "error", error_str, session_id


def _clean_phase_outputs(project_dir: Path, mode: str, has_spec_file: bool) -> None:
    """
    Remove phase output files so _detect_phase_completion() won't skip phases.

    Called when resume=False (fresh start) to ensure a clean slate.
    NEVER deletes source code or git history.
    """
    # Files that are always safe to remove on fresh start
    always_remove = [
        "session_reflections.json",
        "budget_state.json",
        "claude-progress.txt",
        "session_state.json",
    ]

    # Mode-specific output files
    mode_files: dict[str, list[str]] = {
        "greenfield_from_idea": [
            "app_spec.txt", "task_list.json",
            "architect_notes.md", "task_input.txt",
        ],
        "greenfield": [
            # Keep app_spec.txt — user provided it via spec_file
            "task_list.json",
        ],
        "feature": [
            "codebase_profile.json", "task_list.json", "task_input.txt",
        ],
        "refactor": [
            "codebase_profile.json", "task_list.json", "task_input.txt",
        ],
        "evolve": [
            "codebase_profile.json", "task_list.json", "task_input.txt",
        ],
        "fix": [
            "task_list.json", "task_input.txt",
        ],
        "security": [
            "security_report.json", "task_list.json", "task_input.txt",
        ],
    }

    files_to_remove = always_remove + mode_files.get(mode, [])

    paths = get_paths(project_dir)
    removed = []
    for fname in files_to_remove:
        fpath = paths.swarmweaver_dir / fname
        if fpath.exists():
            fpath.unlink()
            removed.append(fname)

    if removed:
        print(f"[FRESH] Cleaned {len(removed)} phase output file(s): {', '.join(removed)}")


def _detect_phase_completion(project_dir: Path, mode: str, phase: str) -> bool:
    """
    Check if a non-looping phase has already been completed.

    Returns True if the phase's output files already exist.
    """
    clean_phase = phase.rstrip("*")
    paths = get_paths(project_dir)

    if clean_phase == "architect":
        return paths.resolve_read("app_spec.txt").exists()

    if clean_phase in ("analyze",):
        return paths.resolve_read("codebase_profile.json").exists()

    if clean_phase == "scan":
        return paths.resolve_read("security_report.json").exists()

    if clean_phase in ("initialize", "plan", "audit", "investigate"):
        # Planning phases are done when task_list.json exists
        return paths.task_list.exists()

    return False


def _has_pending_tasks(project_dir: Path) -> bool:
    """Check if there are remaining tasks to work on."""
    tl = TaskList(project_dir)
    if tl.load():
        return tl.has_pending_tasks()
    # If no task list exists, assume there's work to do
    return True


async def run_autonomous_agent(
    project_dir: Path,
    model: str,
    max_iterations: Optional[int] = None,
    resume: bool = True,
    collect_api_keys: bool = True,
    mode: str = "greenfield",
    task_input: str = "",
    spec_file: Optional[Path] = None,
    budget_limit: float = 0.0,
    max_hours: float = 0.0,
    approval_gates: bool = False,
    auto_pr: bool = False,
    phase_models: Optional[dict] = None,
) -> None:
    """
    Run the autonomous agent loop with multi-mode support.

    Args:
        project_dir: Directory for the project
        model: Claude model to use
        max_iterations: Maximum number of iterations (None for unlimited)
        resume: If True, attempt to resume previous session
        collect_api_keys: If True, prompt for missing API keys interactively
        mode: Operation mode (greenfield, feature, refactor, fix, evolve)
        task_input: The user's task description/goal/issue
        spec_file: Optional path to a custom spec file
        budget_limit: Maximum spend in USD (0 = unlimited)
        max_hours: Maximum runtime in hours (0 = unlimited)
        approval_gates: If True, pause between phases for human approval
        auto_pr: If True, auto-create GitHub PR on completion
        phase_models: Optional dict mapping phase names to model IDs
    """
    MODE_LABELS = {
        "greenfield": "GREENFIELD",
        "feature": "FEATURE",
        "refactor": "REFACTOR",
        "fix": "FIX",
        "evolve": "EVOLVE",
    }

    print("\n" + "=" * 70)
    print(f"  AUTONOMOUS CODING AGENT - {MODE_LABELS.get(mode, mode.upper())} MODE")
    print("=" * 70)
    print(f"\nProject directory: {project_dir}")
    if phase_models:
        print(f"Models: architect={phase_models.get('architect', model)}, plan={phase_models.get('plan', model)}, code={phase_models.get('code', model)}")
    else:
        print(f"Model: {model}")
    if max_iterations:
        print(f"Max iterations: {max_iterations}")
    else:
        print("Max iterations: Unlimited (will run until completion)")
    print()

    # --- Use shared context preparation ---
    ctx = prepare_agent_context(
        project_dir=project_dir,
        mode=mode,
        model=model,
        task_input=task_input,
        spec_file=spec_file,
        resume=resume,
        budget_limit=budget_limit,
        max_hours=max_hours,
        quiet=False,
    )

    paths = ctx.paths
    checkpoint_manager = ctx.checkpoint_manager
    session_manager = ctx.session_manager
    chain_manager = ctx.chain_manager
    budget_tracker = ctx.budget_tracker
    identity_store = ctx.identity_store
    effective_mode = ctx.effective_mode
    chain_id = ctx.chain_id
    sequence_number = ctx.sequence_number
    existing_session = ctx.existing_session
    task_list = ctx.task_list
    has_tasks = task_list.total > 0

    print()

    # Set up stop callback for graceful shutdown
    async def save_state_on_stop():
        checkpoint_manager.save()
        print("[State] Checkpoints saved")

    set_stop_callback(save_state_on_stop)

    if has_tasks:
        print("Continuing existing project")
        print_progress_summary(project_dir)

        # Check for missing API keys
        if collect_api_keys:
            missing_keys = get_missing_api_keys(project_dir)
            if missing_keys:
                print()
                print("-" * 70)
                print(f"  MISSING API KEYS DETECTED ({len(missing_keys)})")
                print("-" * 70)
                print("Some features require API keys that are not configured.")
                response = input("Collect API keys now? (y/n): ").strip().lower()
                if response in ("y", "yes"):
                    collect_missing_api_keys(project_dir, interactive=True)
                else:
                    print("Skipped - some tests will be unavailable")
                print()
    else:
        if effective_mode == "greenfield_from_idea":
            print("Starting greenfield from idea - architect will generate spec first")
            print()
        elif mode == "greenfield":
            print("Starting greenfield - will create task list from spec")
            print()
        else:
            print(f"Starting {mode} mode on existing codebase")
            print()

    # --- Determine phases ---

    phases = ctx.phases
    iteration = ctx.iteration
    starting_iteration = iteration

    # Handle max_iterations=0
    if max_iterations is not None and max_iterations == 0:
        print("\n--max-iterations 0: Exiting without running any sessions")
        return

    # --- Main phase loop ---

    for phase in phases:
        clean_phase = phase.rstrip("*")
        looping = is_looping_phase(phase)

        # Skip completed non-looping phases
        if not looping and _detect_phase_completion(project_dir, mode, phase):
            print(f"\n[Phase '{clean_phase}' already completed, skipping]")
            continue

        # For looping phases, repeat until tasks are done or max iterations reached
        phase_iteration = 0
        while True:
            iteration += 1
            phase_iteration += 1
            iterations_this_run = iteration - starting_iteration

            # Check budget circuit breakers
            budget_exceeded, budget_reason = budget_tracker.is_budget_exceeded()
            if budget_exceeded:
                print(f"\n[BUDGET] Circuit breaker triggered: {budget_reason}")
                print("[BUDGET] Agent stopping. Adjust --budget or --max-hours to continue.")
                break

            # Check max iterations
            if max_iterations is not None and iterations_this_run > max_iterations:
                print(f"\nReached max iterations for this run ({max_iterations})")
                print(f"Total iterations: {iteration - 1}")
                print("To continue, run the script again")
                break

            # For looping phases, check if there are remaining tasks
            if looping and phase_iteration > 1 and not _has_pending_tasks(project_dir):
                print(f"\n[All tasks completed! Phase '{clean_phase}' done]")
                break

            # Print session header
            display_mode = mode  # Use original mode for display
            phase_label = f"{MODE_LABELS.get(display_mode, display_mode.upper())} / {clean_phase.upper()}"
            print("\n" + "=" * 70)
            print(f"  SESSION {iteration}: {phase_label}")
            print("=" * 70)
            print()

            # Determine if we should resume the previous session
            # Only resume within the same phase — resuming across phases causes SDK errors
            resume_id = None
            if existing_session and iteration == existing_session.iteration + 1:
                saved_phase = getattr(existing_session, "phase", None)
                if saved_phase is None or saved_phase == clean_phase:
                    resume_id = existing_session.session_id
                    print(f"Attempting to resume session: {resume_id[:16]}...")
                else:
                    print(f"[Session] Phase changed ({saved_phase} -> {clean_phase}), starting fresh session")

            # Check for mid-execution model override
            model_override_path = paths.model_override
            if model_override_path.exists():
                try:
                    import json as _json
                    override_data = _json.loads(model_override_path.read_text())
                    new_model = override_data.get("model", "")
                    if new_model and new_model != model:
                        print(f"[MODEL] Switching from {model} to {new_model}")
                        model = new_model
                    model_override_path.unlink()
                except Exception:
                    pass

            # Select model for this phase (phase_models override > mid-exec override > default)
            phase_model = model
            if phase_models:
                pm_key = _PHASE_MODEL_MAP.get(clean_phase, "code")
                if pm_key in phase_models:
                    phase_model = phase_models[pm_key]
            print(f"Model: {phase_model}")

            # Create client with all enhancements
            client = create_client(
                project_dir,
                phase_model,
                resume_session_id=resume_id,
                enable_checkpointing=True,
                enable_subagents=True,
                enable_audit_logging=True,
            )

            # Smart context priming: inject relevant file snippets
            context_prime = ""
            if looping:
                try:
                    from features.context_primer import ContextPrimer
                    tl = TaskList(project_dir)
                    tl.load()
                    next_task = tl.get_next_actionable()
                    if next_task:
                        primer = ContextPrimer(project_dir)
                        context_prime = primer.build_context_section(next_task.__dict__)
                except Exception:
                    pass

            # Build the prompt for this mode and phase
            prompt = build_prompt(
                mode=effective_mode,
                phase=phase,
                task_input=task_input,
                task_input_short=task_input[:80] if task_input else "",
                project_dir=project_dir,
            )

            # Inject context prime into prompt
            if context_prime:
                prompt = prompt.replace("{context_prime}", context_prime)

            # Inject previous session handoff summary into prompt
            prev_summary = chain_manager.get_previous_summary(chain_id)
            if prev_summary:
                prompt = f"Previous session summary: {prev_summary}\n\n{prompt}"

            # Run session
            async with client:
                status, response, session_id = await run_agent_session(
                    client, prompt, project_dir, checkpoint_manager, iteration
                )

            # Save session state
            session_start_time = datetime.now()
            if session_id:
                state = SessionState(
                    session_id=session_id,
                    created_at=existing_session.created_at if existing_session else datetime.now(),
                    last_used=datetime.now(),
                    iteration=iteration,
                    model=phase_model,
                    phase=clean_phase,
                    chain_id=chain_id,
                    sequence_number=sequence_number,
                )
                session_manager.save(state)
                existing_session = state
                print(f"[Session saved: {session_id[:16]}...]")

            # Record token usage for budget tracking
            # Estimate tokens from response length (SDK doesn't expose usage directly via subprocess)
            # ~4 chars per token for output, tool calls ~500 input tokens each
            response_len = len(response) if response else 0
            estimated_output = max(200, response_len // 4)
            estimated_input = max(500, len(prompt) // 4)
            budget_tracker.record_usage(estimated_input, estimated_output, phase_model)
            bs = budget_tracker.get_status()
            print(f"[BUDGET] ${bs['estimated_cost_usd']:.4f} spent ({bs['total_input_tokens']} in / {bs['total_output_tokens']} out tokens)")

            # Record session in chain
            if session_id:
                tl_chain = TaskList(project_dir)
                tl_chain.load()
                tasks_done = len([t for t in tl_chain.tasks if t.status == "done"]) if tl_chain.tasks else 0
                tasks_total = len(tl_chain.tasks) if tl_chain.tasks else 0
                # Build a summary from response (first ~200 chars of meaningful text)
                summary_text = ""
                if response:
                    summary_text = response.strip()[:200]
                    if len(response.strip()) > 200:
                        summary_text += "..."
                chain_entry = ChainEntry(
                    session_id=session_id,
                    chain_id=chain_id,
                    sequence_number=sequence_number,
                    checkpoint_summary=summary_text,
                    start_time=session_start_time.isoformat(),
                    end_time=datetime.now().isoformat(),
                    phase=clean_phase,
                    tasks_completed=tasks_done,
                    tasks_total=tasks_total,
                    cost=bs["estimated_cost_usd"],
                )
                chain_manager.add_entry(chain_entry)
                sequence_number += 1
                print(f"[CHAIN] Session S{chain_entry.sequence_number} recorded in chain {chain_id}")

            # Self-healing verification loop: verify completed tasks
            if status == "continue" and looping:
                try:
                    from features.verification import VerificationManager
                    verifier = VerificationManager(project_dir)
                    actions = verifier.verify_completed_tasks()
                    for action in actions:
                        action_type = action.get("action", "")
                        task_id = action.get("task_id", "")
                        msg = action.get("message", "")
                        if action_type == "verified":
                            print(f"[VERIFY] {task_id}: \u2714 {msg}")
                        elif action_type == "reopened":
                            print(f"[VERIFY] {task_id}: \u21BB Reopened - {msg}")
                        elif action_type == "failed_verification":
                            print(f"[VERIFY] {task_id}: \u2717 {msg}")
                        else:
                            print(f"[VERIFY] {task_id}: {action_type} - {msg}")
                except Exception as e:
                    print(f"[VERIFY] Verification error (non-fatal): {e}")

            # Task Approval Gate (between sessions)
            if status == "continue" and approval_gates and looping:
                try:
                    from features.approval import request_approval, wait_for_approval
                    tl = TaskList(project_dir)
                    tl.load()
                    completed = [t.title for t in tl.tasks if t.status == "done"]
                    remaining = [t.title for t in tl.tasks if t.status in ("pending", "in_progress")]
                    if completed:  # Only gate if something was completed
                        req_id = request_approval(
                            project_dir,
                            gate_type="phase_complete",
                            summary=f"Phase '{clean_phase}' session {phase_iteration} complete",
                            tasks_completed=completed[-3:],  # Last 3
                            tasks_remaining=remaining[:5],     # Next 5
                        )
                        print(f"\n[APPROVAL] Waiting for human review (request {req_id}...)")
                        print("[APPROVAL] Approve, Reject, Reflect, or Skip via the dashboard.")
                        decision, feedback = await wait_for_approval(project_dir)
                        print(f"[APPROVAL] Decision: {decision}")
                        if feedback:
                            print(f"[APPROVAL] Feedback: {feedback}")

                        if decision == "rejected":
                            # Reopen the most recently completed task
                            done_tasks = [t for t in tl.tasks if t.status == "done"]
                            if done_tasks:
                                last_done = done_tasks[-1]
                                tl.reopen_task(last_done.id, feedback or "Rejected by operator")
                                print(f"[APPROVAL] Reopened task: {last_done.title}")
                        elif decision == "reflect":
                            # Trigger reflection via steering
                            from features.steering import write_steering_message
                            write_steering_message(project_dir, feedback or "Please reflect on the approach", "reflect")
                            print("[APPROVAL] Reflection triggered for next session")
                except Exception as e:
                    print(f"[APPROVAL] Gate error (non-fatal): {e}")

            # Handle status
            if status == "continue":
                print(f"\nAgent will auto-continue in {AUTO_CONTINUE_DELAY_SECONDS}s...")
                # Only print task progress if task list exists (not after architect phase)
                tl_check = TaskList(project_dir)
                if tl_check.load() and tl_check.total > 0:
                    print_progress_summary(project_dir)
                await asyncio.sleep(AUTO_CONTINUE_DELAY_SECONDS)

            elif status == "image_error":
                print("\nClearing session state to force fresh start on next run...")
                session_state_file = paths.session_state
                if session_state_file.exists():
                    session_state_file.unlink()
                existing_session = None
                print(f"\nRun again with --no-resume to start fresh")
                break

            elif status == "error":
                print("\nSession encountered an error")
                budget_tracker.record_error()
                latest_checkpoint = checkpoint_manager.get_latest()
                if latest_checkpoint:
                    print(f"Last checkpoint available: {latest_checkpoint.id[:16]}...")
                print("Will retry with a fresh session...")
                await asyncio.sleep(AUTO_CONTINUE_DELAY_SECONDS)

            # Clean up old checkpoints
            removed = checkpoint_manager.clear_old_checkpoints(keep_last_n=100)
            if removed > 0:
                print(f"[Cleaned up {removed} old checkpoints]")

            # If this is a non-looping phase, run it only once
            if not looping:
                break

            # Small delay between sessions
            if max_iterations is None or iterations_this_run < max_iterations:
                print("\nPreparing next session...\n")
                await asyncio.sleep(1)

        # Check if we hit max iterations (break outer loop too)
        if max_iterations is not None and (iteration - starting_iteration) >= max_iterations:
            break

    # --- Auto-PR on completion ---

    if auto_pr and not _has_pending_tasks(project_dir):
        try:
            from features.github_integration import GitHubManager
            import re as _re
            gh = GitHubManager(project_dir)
            if gh.is_gh_available():
                slug = _re.sub(r"[^a-zA-Z0-9]+", "-", (task_input or mode)[:40]).strip("-").lower()
                branch_name = f"swarmweaver/{mode}/{slug}"
                if gh.create_branch(branch_name):
                    if gh.push_branch():
                        pr_title = f"[SwarmWeaver] {mode}: {(task_input or 'changes')[:50]}"
                        pr = gh.create_pr(title=pr_title, body=f"Automated changes by SwarmWeaver in {mode} mode.")
                        if pr.get("success"):
                            print(f"\n[GITHUB] PR created: {pr['url']}")
                        else:
                            print(f"\n[GITHUB] PR creation failed: {pr.get('error', 'unknown')}")
                    else:
                        print("\n[GITHUB] Failed to push branch")
                else:
                    print("\n[GITHUB] Failed to create branch")
            else:
                print("\n[GITHUB] gh CLI not available, skipping auto-PR")
        except Exception as e:
            print(f"\n[GITHUB] Auto-PR error (non-fatal): {e}")

    # --- Harvest session reflections into MELS expertise store ---

    budget_final = budget_tracker.get_status()

    try:
        import json as _json
        import hashlib as _hashlib
        from services.expertise_store import get_cross_project_store, get_project_store
        from services.expertise_models import ExpertiseRecord, Outcome, infer_domain

        cross_store = get_cross_project_store()
        proj_store = get_project_store(project_dir)
        reflections_file = paths.session_reflections

        # Category -> record_type mapping
        _CAT_MAP = {
            "pattern": "pattern", "mistake": "failure",
            "solution": "resolution", "preference": "convention",
        }

        # 1. Harvest agent-written reflections as typed ExpertiseRecords
        if reflections_file.exists():
            try:
                reflections = _json.loads(reflections_file.read_text(encoding="utf-8"))
                if isinstance(reflections, list):
                    saved_count = 0
                    for entry in reflections:
                        if not isinstance(entry, dict) or not entry.get("content"):
                            continue
                        category = entry.get("category", "pattern")
                        record_type = _CAT_MAP.get(category, "pattern")
                        content = entry["content"]
                        tags = entry.get("tags", [])
                        if mode not in tags:
                            tags.append(mode)
                        domain = entry.get("domain", "")
                        if not domain:
                            # Infer from content keywords
                            for kw, d in [("python", "python"), ("typescript", "typescript"),
                                          ("react", "typescript.react"), ("test", "testing"),
                                          ("docker", "devops.docker"), ("api", "architecture.api")]:
                                if kw in content.lower():
                                    domain = d
                                    break

                        record = ExpertiseRecord(
                            record_type=record_type,
                            classification="tactical",
                            domain=domain,
                            content=content,
                            source_project=str(project_dir),
                            source_agent="session-agent",
                            tags=tags,
                            content_hash=_hashlib.sha256(content.encode()).hexdigest(),
                        )
                        proj_store.add(record)
                        cross_store.add(record)
                        saved_count += 1
                    if saved_count > 0:
                        print(f"[MELS] Saved {saved_count} reflection(s) to expertise stores")
                reflections_file.unlink(missing_ok=True)
            except (_json.JSONDecodeError, OSError) as e:
                print(f"[MELS] Could not parse session_reflections.json: {e}")

        # Mode to domain heuristic
        _MODE_DOMAIN = {
            "greenfield": "", "feature": "", "refactor": "",
            "fix": "", "evolve": "", "security": "architecture.api",
        }

        # 2. Auto-save error pattern as failure record
        if budget_final["consecutive_errors"] > 0:
            content = f"Session ended with {budget_final['consecutive_errors']} consecutive errors in {mode} mode"
            proj_store.add(ExpertiseRecord(
                record_type="failure",
                classification="observational",
                domain=_MODE_DOMAIN.get(mode, ""),
                content=content,
                source_project=str(project_dir),
                tags=[mode, "errors"],
                content_hash=_hashlib.sha256(content.encode()).hexdigest(),
            ))

        # 3. Auto-save success pattern
        if not _has_pending_tasks(project_dir) and budget_final["session_count"] > 0:
            tl_path = paths.resolve_read("task_list.json")
            if tl_path.exists():
                try:
                    tl = TaskList(project_dir)
                    tl.load()
                    done_count = len([t for t in tl.tasks if t.status == "done"])
                    if done_count > 0:
                        content = (
                            f"Successfully completed all {done_count} tasks in {mode} mode "
                            f"across {budget_final['session_count']} sessions "
                            f"(${budget_final['estimated_cost_usd']:.4f})"
                        )
                        proj_store.add(ExpertiseRecord(
                            record_type="pattern",
                            classification="tactical",
                            domain=_MODE_DOMAIN.get(mode, ""),
                            content=content,
                            source_project=str(project_dir),
                            tags=[mode, "completed", "success"],
                            content_hash=_hashlib.sha256(content.encode()).hexdigest(),
                        ))
                        print(f"[MELS] Saved completion pattern ({done_count} tasks, {mode} mode)")
                except Exception:
                    pass

        # 4. Error→resolution patterns as linked failure + resolution records
        try:
            from services.expertise_models import infer_domain as _infer_domain
            tl_retry = TaskList(project_dir)
            tl_retry.load()
            retry_count = 0
            for task in tl_retry.tasks:
                if (task.status == "done"
                        and getattr(task, "verification_attempts", 0) > 0
                        and getattr(task, "last_verification_error", "")):
                    # Infer domain from task file scope
                    task_domain = ""
                    for fp in getattr(task, "file_scope", []) or []:
                        d = _infer_domain(fp)
                        if d:
                            task_domain = d
                            break

                    # Create failure record
                    fail_content = f"[{mode}] Task '{task.title}' failed with: {task.last_verification_error[:150]}"
                    fail_record = ExpertiseRecord(
                        record_type="failure",
                        classification="observational",
                        domain=task_domain,
                        content=fail_content,
                        source_project=str(project_dir),
                        tags=[mode, "error-resolution"],
                        file_patterns=getattr(task, "file_scope", []) or [],
                        content_hash=_hashlib.sha256(fail_content.encode()).hexdigest(),
                    )
                    fail_id = proj_store.add(fail_record)

                    # Create linked resolution record
                    res_content = f"[{mode}] Task '{task.title}' eventually resolved after {task.verification_attempts} attempts"
                    res_record = ExpertiseRecord(
                        record_type="resolution",
                        classification="tactical",
                        domain=task_domain,
                        content=res_content,
                        source_project=str(project_dir),
                        resolves=fail_id,
                        tags=[mode, "error-resolution"],
                        file_patterns=getattr(task, "file_scope", []) or [],
                        content_hash=_hashlib.sha256(res_content.encode()).hexdigest(),
                    )
                    proj_store.add(res_record)
                    retry_count += 1
            if retry_count > 0:
                print(f"[MELS] Saved {retry_count} error→resolution chain(s)")
        except Exception as e:
            print(f"[MELS] Error→resolution save failed: {e}")

        # 5. Track outcomes for records that were primed into this session
        try:
            relevant = cross_store.search(query=task_input or mode, limit=5)
            if relevant:
                all_done = not _has_pending_tasks(project_dir)
                had_errors = budget_final.get("consecutive_errors", 0) > 2
                for rec in relevant:
                    status = "success" if all_done else ("partial" if had_errors else None)
                    if status:
                        cross_store.record_outcome(rec.id, Outcome(
                            record_id=rec.id,
                            status=status,
                            agent="session-agent",
                            project=str(project_dir),
                        ))
        except Exception as e:
            print(f"[MELS] Outcome tracking failed: {e}")

        # 6. Auto-detect project conventions from audit log
        try:
            if not _has_pending_tasks(project_dir):
                audit_path = paths.audit_log
                if audit_path.exists():
                    audit_text = audit_path.read_text(encoding="utf-8", errors="ignore")[:50000]
                    detections = [
                        ("pytest", "Uses pytest for testing", "python.testing"),
                        ("jest", "Uses Jest for testing", "typescript.testing"),
                        ("vitest", "Uses Vitest for testing", "typescript.testing"),
                        ("fastapi", "Uses FastAPI framework", "python.fastapi"),
                        ("django", "Uses Django framework", "python.django"),
                        ("next build", "Uses Next.js", "typescript.nextjs"),
                        ("vite build", "Uses Vite bundler", "javascript"),
                        ("tailwindcss", "Uses Tailwind CSS", "styling"),
                    ]
                    audit_lower = audit_text.lower()
                    det_count = 0
                    for keyword, desc, domain in detections:
                        if keyword in audit_lower:
                            proj_store.add(ExpertiseRecord(
                                record_type="convention",
                                classification="foundational",
                                domain=domain,
                                content=desc,
                                source_project=str(project_dir),
                                tags=[mode, "auto-detected"],
                                content_hash=_hashlib.sha256(desc.encode()).hexdigest(),
                            ))
                            det_count += 1
                    if det_count > 0:
                        print(f"[MELS] Auto-detected {det_count} convention(s)")
        except Exception as e:
            print(f"[MELS] Convention auto-detect failed: {e}")

        # 7. Cross-project insight detection: check for 3+ similar records across projects
        try:
            all_records = cross_store.search(limit=100)
            # Group by content_hash prefix for similarity
            by_hash: dict[str, list] = {}
            for rec in all_records:
                if rec.content_hash:
                    prefix = rec.content_hash[:8]
                    by_hash.setdefault(prefix, []).append(rec)

            for _prefix, group in by_hash.items():
                projects = set(r.source_project for r in group if r.source_project)
                if len(projects) >= 3 and group[0].classification != "foundational":
                    # Promote to foundational insight
                    cross_store.update(
                        group[0].id,
                        classification="foundational",
                        record_type="insight",
                    )
        except Exception:
            pass

    except Exception as e:
        print(f"[MELS] Reflection harvest error (non-fatal): {e}")

    # --- Auto-harvest session insights from audit log ---
    _session_analysis = None
    try:
        from services.insights import SessionInsightAnalyzer
        analyzer = SessionInsightAnalyzer(project_dir)
        analysis = analyzer.analyze_audit_log()
        _session_analysis = analysis
        if analysis.insights:
            count = analyzer.record_to_expertise(analysis, project_source=str(project_dir))
            if count > 0:
                print(f"[MELS] Auto-harvested {count} insight(s) from session "
                      f"({analysis.total_tool_calls} tool calls, {analysis.error_frequency} errors)")
    except Exception:
        # Fallback to legacy insights recording
        try:
            from services.insights import SessionInsightAnalyzer
            analyzer = SessionInsightAnalyzer(project_dir)
            analysis = analyzer.analyze_audit_log()
            _session_analysis = analysis
            if analysis.insights:
                count = analyzer.record_to_expertise(analysis, project_source=str(project_dir))
                if count > 0:
                    print(f"[INSIGHTS] Auto-harvested {count} insight(s)")
        except Exception:
            pass

    # --- Update main agent identity with final stats ---
    try:
        tl_final = TaskList(project_dir)
        tl_final.load()
        completed_tasks = [
            {"id": t.id, "title": t.title}
            for t in tl_final.tasks
            if t.status == "done"
        ]
        identity = identity_store.update_after_session(
            name="main",
            completed_tasks=completed_tasks,
            domains=[mode],
        )
        # Enrich identity with session insights (tools, task types, error patterns)
        if _session_analysis is not None:
            from services.insights import enrich_identity_from_insights
            session_mins = (datetime.now() - session_start_time).total_seconds() / 60.0
            enrich_identity_from_insights(identity, _session_analysis, session_mins)
            identity_store.save(identity)
        print(f"[IDENTITY] Main agent stats updated ({len(completed_tasks)} tasks done)")
    except Exception as e:
        print(f"[IDENTITY] Stats update error (non-fatal): {e}")

    # --- Final summary ---

    print("\n" + "=" * 70)
    print("  SESSION COMPLETE")
    print("=" * 70)
    print(f"\nProject directory: {project_dir}")
    print(f"Mode: {mode}")
    print_progress_summary(project_dir)
    print(f"\nCheckpoints stored: {len(checkpoint_manager)}")
    print(f"Budget: ${budget_final['estimated_cost_usd']:.4f} across {budget_final['session_count']} sessions")
    if existing_session:
        print(f"Session ID: {existing_session.session_id[:32]}...")

    check_and_prompt_api_keys(project_dir, at_session_end=True)

    print("\n" + "-" * 70)
    print("  TO RESUME:")
    print("-" * 70)
    print(f"\n  swarmweaver {mode} --project-dir {project_dir}")
    if mode == "greenfield":
        print(f"\n  TO RUN THE APPLICATION:")
        print(f"  cd {project_dir.resolve()}")
        print("  ./init.sh")
    print("-" * 70)

    print("\nDone!")
