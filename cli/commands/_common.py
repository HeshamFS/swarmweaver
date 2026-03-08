"""Shared CLI logic extracted from autonomous_agent_demo.py."""

import asyncio
import json
import os
import signal
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer

from dotenv import load_dotenv

from core.models import DEFAULT_MODEL, ORCHESTRATOR_MODEL

# Load environment variables from .env file
load_dotenv()

# Strip CLAUDECODE env var so the Claude Agent SDK can launch even when
# invoked from within a Claude Code session (prevents "nested session" error).
# The SDK's SubprocessCLITransport merges os.environ into the subprocess env,
# so we must remove it from the process environment itself.
os.environ.pop("CLAUDECODE", None)

# Global state for interrupt handling
_shutdown_requested = False


def signal_handler(signum, frame):
    """Handle SIGINT (Ctrl+C) gracefully."""
    global _shutdown_requested

    if _shutdown_requested:
        print("\n\nForce exit requested...")
        print("Note: State may not be fully saved. Check session_state.json and .checkpoints.json")
        sys.exit(1)

    _shutdown_requested = True
    print("\n\n" + "=" * 70)
    print("  INTERRUPT RECEIVED")
    print("=" * 70)
    print("\nSaving state and shutting down gracefully...")
    print("Press Ctrl+C again to force exit (may lose unsaved state)")
    print()


def add_signal_handler():
    """Register the SIGINT handler."""
    signal.signal(signal.SIGINT, signal_handler)


# ── Common Typer options ──────────────────────────────────────────────

ProjectDir = Annotated[
    Path,
    typer.Option("--project-dir", help="Directory for the project (existing or to be created)"),
]

Model = Annotated[
    str,
    typer.Option("--model", help=f"Claude model to use (default: {DEFAULT_MODEL})"),
]

PhaseModels = Annotated[
    Optional[str],
    typer.Option(
        "--phase-models",
        help=f'JSON dict mapping phases to models, e.g. \'{{"architect":"{ORCHESTRATOR_MODEL}","code":"{DEFAULT_MODEL}"}}\'',
    ),
]

MaxIterations = Annotated[
    Optional[int],
    typer.Option("--max-iterations", help="Maximum number of agent iterations (default: unlimited)"),
]

NoResume = Annotated[
    bool,
    typer.Option("--no-resume", help="Start fresh without resuming previous session"),
]

CollectApiKeys = Annotated[
    bool,
    typer.Option("--collect-api-keys", help="Prompt for missing API keys before starting"),
]

SkipApiKeys = Annotated[
    bool,
    typer.Option("--skip-api-keys", help="Skip API key prompts (some features will be unavailable)"),
]

Parallel = Annotated[
    int,
    typer.Option("--parallel", help="Number of parallel workers for static swarm mode (1-5, default: 1)"),
]

SmartSwarm = Annotated[
    bool,
    typer.Option("--smart-swarm", help="Enable AI-orchestrated swarm: an Opus orchestrator dynamically manages Sonnet workers"),
]

Overrides = Annotated[
    Optional[str],
    typer.Option("--overrides", help="JSON-encoded dispatch overrides for swarm mode"),
]

Budget = Annotated[
    float,
    typer.Option("--budget", help="Budget limit in USD (0 = unlimited, default: 0)"),
]

MaxHours = Annotated[
    float,
    typer.Option("--max-hours", help="Maximum runtime in hours (0 = unlimited, default: 0)"),
]

ApprovalGates = Annotated[
    bool,
    typer.Option("--approval-gates", help="Enable approval gates between phases (pause for human review)"),
]

AutoPr = Annotated[
    bool,
    typer.Option("--auto-pr", help="Auto-create GitHub PR on completion (requires gh CLI)"),
]

Worktree = Annotated[
    bool,
    typer.Option("--worktree", help="Run agent in isolated git worktree (changes can be merged or discarded after)"),
]

Interactive = Annotated[
    bool,
    typer.Option("--interactive", help="Run interactive wizard before starting the agent"),
]

JsonOutput = Annotated[
    bool,
    typer.Option("--json", help="Emit newline-delimited JSON events instead of rich output"),
]

Server = Annotated[
    Optional[str],
    typer.Option("--server", help="SwarmWeaver server URL (e.g. http://localhost:8000). Overrides SWARMWEAVER_URL env var."),
]


# ── Task input extraction ────────────────────────────────────────────

def get_task_input(
    mode: str,
    *,
    spec: Optional[Path] = None,
    idea: Optional[str] = None,
    description: Optional[str] = None,
    goal: Optional[str] = None,
    issue: Optional[str] = None,
    focus: Optional[str] = None,
) -> str:
    """Extract the task input text based on mode and CLI arguments."""
    if mode == "greenfield":
        if idea:
            return idea
        if spec:
            return "Build a project from the specification in app_spec.txt"
        return "Build a project from app_spec.txt"
    elif mode == "feature":
        if description:
            return description
        elif spec:
            return Path(spec).read_text(encoding="utf-8")
        return ""
    elif mode == "refactor":
        return goal or ""
    elif mode == "fix":
        return issue or ""
    elif mode == "evolve":
        return goal or ""
    elif mode == "security":
        return focus if focus else "Full security audit"
    return ""


# ── Main agent runner ─────────────────────────────────────────────────

def cli_event_handler(event: dict) -> None:
    """Print agent events to stdout for CLI usage."""
    etype = event.get("type", "")
    if etype == "text_delta":
        print(event.get("text", ""), end="", flush=True)
    elif etype == "output":
        print(event.get("data", ""), flush=True)
    elif etype in ("tool_start", "tool_done"):
        tool = event.get("tool", event.get("data", {}).get("tool", "?"))
        status = "\u2192" if etype == "tool_start" else "\u2713"
        print(f"  [{status} {tool}]", flush=True)
    elif etype == "phase_change":
        phase = event.get("data", {}).get("phase", "?")
        print(f"\n[PHASE] {phase.upper()}", flush=True)
    elif etype == "session_start":
        session = event.get("data", {}).get("session", "?")
        phase = event.get("data", {}).get("phase", "")
        print(f"\n[SESSION {session}] {phase}", flush=True)
    elif etype == "error":
        print(f"\n[ERROR] {event.get('data', '')}", flush=True)
    elif etype == "status":
        print(f"\n[STATUS] {event.get('data', '')}", flush=True)


async def _cli_on_event(event: dict) -> None:
    cli_event_handler(event)


def run_agent(
    *,
    project_dir: Path,
    mode: str,
    task_input: str,
    model: str = DEFAULT_MODEL,
    phase_models_json: Optional[str] = None,
    max_iterations: Optional[int] = None,
    no_resume: bool = False,
    collect_api_keys: bool = False,
    skip_api_keys: bool = False,
    parallel: int = 1,
    smart_swarm: bool = False,
    overrides_json: Optional[str] = None,
    budget: float = 0.0,
    max_hours: float = 0.0,
    approval_gates: bool = False,
    auto_pr: bool = False,
    worktree: bool = False,
    spec: Optional[Path] = None,
    idea: Optional[str] = None,
    interactive: bool = False,
    json_output: bool = False,
    server: Optional[str] = None,
) -> None:
    """Run the agent - handles worktree setup, engine/swarm dispatch, worktree interactive prompt.

    This is the full main() logic from autonomous_agent_demo.py minus argument parsing.
    If a server URL is set (--server flag or SWARMWEAVER_URL env), routes through the
    REST/WebSocket client instead of running in-process.
    """
    add_signal_handler()

    # Build event handler based on output mode
    if json_output:
        from cli.output import JsonEventRenderer
        _renderer = JsonEventRenderer()
        on_event = _renderer.on_event
    else:
        try:
            from cli.output import RichEventRenderer
            _renderer = RichEventRenderer()
            on_event = _renderer.on_event
        except ImportError:
            from cli.output import make_plain_on_event
            on_event = make_plain_on_event()

    # Interactive wizard
    if interactive:
        from cli.wizard import CLIWizard
        wizard = CLIWizard()
        refined = asyncio.run(wizard.run(
            mode=mode,
            task_input=task_input,
            project_dir=project_dir,
            model=model,
        ))
        if refined is None:
            print("Wizard cancelled. Exiting.")
            return
        task_input = refined

    # Connected mode: route through server if URL is set
    server_url = server or os.environ.get("SWARMWEAVER_URL", "")
    if server_url:
        _run_connected(
            server_url=server_url,
            project_dir=project_dir,
            mode=mode,
            task_input=task_input,
            model=model,
            max_iterations=max_iterations,
            no_resume=no_resume,
            parallel=parallel,
            smart_swarm=smart_swarm,
            budget=budget,
            worktree=worktree,
            on_event=on_event,
        )
        return

    # Check for authentication
    if not skip_api_keys:
        if not os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") and not os.environ.get("ANTHROPIC_API_KEY"):
            print("Error: No authentication configured")
            print("\nSet one of the following:")
            print("\n  Option 1 - Claude Code Max subscription (OAuth):")
            print("    Run 'claude setup-token' to generate a token, then:")
            print("    export CLAUDE_CODE_OAUTH_TOKEN='your-oauth-token'")
            print("\n  Option 2 - Anthropic API key:")
            print("    Get your API key from: https://console.anthropic.com/")
            print("    export ANTHROPIC_API_KEY='your-api-key-here'")
            return

    # Resolve project directory
    if mode == "greenfield" and not project_dir.is_absolute():
        if not str(project_dir).startswith("generations/"):
            project_dir = Path("generations") / project_dir

    # Ensure project directory exists
    project_dir.mkdir(parents=True, exist_ok=True)

    # Handle explicit --collect-api-keys flag
    if collect_api_keys:
        from utils.api_keys import collect_missing_api_keys

        print("\n" + "=" * 70)
        print("  API KEY COLLECTION MODE")
        print("=" * 70)
        collect_missing_api_keys(project_dir, interactive=True)
        print()

    # Print mode info
    MODE_LABELS = {
        "greenfield": "GREENFIELD - Building new project",
        "feature": "FEATURE - Adding to existing codebase",
        "refactor": "REFACTOR - Restructuring codebase",
        "fix": "FIX - Diagnosing and fixing bugs",
        "evolve": "EVOLVE - Improving codebase",
        "security": "SECURITY - Scanning and hardening",
    }

    print("\n" + "=" * 70)
    print("  AUTONOMOUS CODING AGENT")
    print(f"  Mode: {MODE_LABELS.get(mode, mode)}")
    print("=" * 70)
    print(f"\n  Project: {project_dir}")
    if mode == "greenfield" and idea:
        display = idea[:100] + "..." if len(idea) > 100 else idea
        print(f"  Idea: {display}")
        print("  Flow: architect -> initialize -> code")
    elif task_input and mode != "greenfield":
        display = task_input[:100] + "..." if len(task_input) > 100 else task_input
        print(f"  Task: {display}")
    print()

    # Worktree isolation
    use_worktree = worktree
    worktree_info = None
    original_project_dir = project_dir

    if use_worktree and parallel <= 1:
        import secrets as _secrets
        from core.worktree import create_worktree as _create_wt

        run_id = f"run-{int(__import__('time').time())}-{_secrets.token_hex(3)}"
        print(f"\n[WORKTREE] Creating isolated worktree: {run_id}")
        try:
            worktree_info = _create_wt(project_dir, run_id)
            project_dir = Path(worktree_info.worktree_path)
            print(f"[WORKTREE] Agent will work in: {project_dir}")
            print(f"[WORKTREE] Branch: {worktree_info.branch_name}")
            print(f"[WORKTREE] Original code is safe on: {worktree_info.original_branch}\n")
        except RuntimeError as e:
            print(f"[WORKTREE] Failed to create worktree: {e}")
            print("[WORKTREE] Falling back to direct mode\n")
            worktree_info = None
            use_worktree = False

    # Parse phase-models JSON if provided
    phase_models = None
    if phase_models_json:
        try:
            phase_models = json.loads(phase_models_json)
        except (ValueError, TypeError):
            print("Warning: Invalid --phase-models JSON, ignoring")

    # Parse dispatch overrides if provided
    overrides_list = None
    if overrides_json:
        try:
            overrides_list = json.loads(overrides_json)
        except (ValueError, TypeError):
            pass

    # Run the agent (smart swarm, static swarm, or single mode)
    try:
        if smart_swarm:
            print(f"\n{'=' * 70}")
            print("  SMART SWARM MODE: AI orchestrator (Opus) + dynamic workers (Sonnet)")
            print(f"{'=' * 70}\n")

            from core.swarm import SmartSwarm
            smart = SmartSwarm(
                project_dir=project_dir,
                mode=mode,
                model=model,
                task_input=task_input,
                spec_file=spec,
                max_iterations=max_iterations,
                resume=not no_resume,
                budget_limit=budget,
                max_hours=max_hours,
                phase_models=phase_models,
                on_event=on_event,
            )
            asyncio.run(smart.run())
        elif parallel > 1:
            print(f"\n{'=' * 70}")
            print(f"  SWARM MODE: {parallel} parallel workers")
            print(f"{'=' * 70}\n")

            from core.swarm import Swarm
            swarm = Swarm(
                project_dir=project_dir,
                mode=mode,
                model=model,
                num_workers=parallel,
                task_input=task_input,
                max_iterations=max_iterations,
                resume=not no_resume,
                budget_limit=budget,
                max_hours=max_hours,
                phase_models=phase_models,
                overrides=overrides_list,
                on_event=on_event,
            )
            asyncio.run(swarm.run())
        else:
            from core.engine import Engine
            engine = Engine(
                project_dir=project_dir,
                mode=mode,
                model=model,
                task_input=task_input,
                spec_file=spec,
                max_iterations=max_iterations,
                resume=not no_resume,
                budget_limit=budget,
                max_hours=max_hours,
                approval_gates=approval_gates,
                auto_pr=auto_pr,
                phase_models=phase_models,
                on_event=on_event,
            )
            asyncio.run(engine.run())
    except KeyboardInterrupt:
        print("\n" + "-" * 70)
        print("  SESSION INTERRUPTED")
        print("-" * 70)
        print(f"\nProject directory: {project_dir.resolve()}")
        print("\nState has been saved. To resume:")
        print(f"  swarmweaver {mode} --project-dir {original_project_dir}")
        print("\nTo start fresh (ignore saved session):")
        print(f"  swarmweaver {mode} --project-dir {original_project_dir} --no-resume")
        print("-" * 70)
    except Exception as e:
        print(f"\nFatal error: {e}")
        raise

    # Interactive worktree merge/discard prompt (CLI only)
    if worktree_info and use_worktree:
        _worktree_interactive_prompt(original_project_dir, worktree_info)


def _worktree_interactive_prompt(original_project_dir: Path, worktree_info) -> None:
    """Interactive merge/discard prompt for worktree mode."""
    from core.worktree import (
        merge_worktree as _merge_wt,
        discard_worktree as _discard_wt,
        get_worktree_status as _wt_status,
        get_worktree_diff as _wt_diff,
    )

    status = _wt_status(original_project_dir, worktree_info.run_id)
    print("\n" + "=" * 70)
    print("  WORKTREE: REVIEW CHANGES")
    print("=" * 70)
    print(f"\n  Branch: {worktree_info.branch_name}")
    print(f"  Files changed: {status.files_changed}")
    print(f"  Insertions: +{status.insertions}  Deletions: -{status.deletions}")
    if status.diff_stat:
        print(f"\n{status.diff_stat}")

    while True:
        print(f"\n  [m]erge   - Apply changes to '{worktree_info.original_branch}'")
        print("  [d]iscard - Throw away all changes")
        print("  [i]nspect - Show full diff")
        print("  [k]eep   - Keep worktree for manual inspection")

        try:
            choice = input("\n  Choice: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n[WORKTREE] Keeping worktree for manual inspection")
            break

        if choice in ("m", "merge"):
            result = _merge_wt(original_project_dir, worktree_info.run_id)
            if result.success:
                print(f"\n[WORKTREE] Merged {result.files_changed} files into '{worktree_info.original_branch}'")
                print("[WORKTREE] Worktree cleaned up")
            else:
                print(f"\n[WORKTREE] Merge failed: {result.error}")
                print("[WORKTREE] Worktree preserved for manual resolution")
            break

        elif choice in ("d", "discard"):
            confirm = input("  Are you sure? This cannot be undone. (y/n): ").strip().lower()
            if confirm in ("y", "yes"):
                _discard_wt(original_project_dir, worktree_info.run_id)
                print("\n[WORKTREE] All changes discarded. Original code is untouched.")
                break
            else:
                continue

        elif choice in ("i", "inspect"):
            diff = _wt_diff(original_project_dir, worktree_info.run_id)
            print("\n" + "-" * 70)
            print(diff[:5000])
            if len(diff) > 5000:
                print(f"\n... ({len(diff)} chars total, truncated)")
            print("-" * 70)

        elif choice in ("k", "keep"):
            print(f"\n[WORKTREE] Worktree preserved at: {worktree_info.worktree_path}")
            print(f"[WORKTREE] To merge later:  git merge {worktree_info.branch_name}")
            print(f"[WORKTREE] To discard:      git worktree remove --force {worktree_info.worktree_path}")
            break
        else:
            print("  Invalid choice. Please enter m, d, i, or k.")


def _run_connected(
    *,
    server_url: str,
    project_dir: Path,
    mode: str,
    task_input: str,
    model: str,
    max_iterations: Optional[int],
    no_resume: bool,
    parallel: int,
    smart_swarm: bool,
    budget: float,
    worktree: bool,
    on_event,
) -> None:
    """Run the agent via a remote SwarmWeaver server (connected mode)."""
    from cli.client import SwarmWeaverClient

    print(f"\n[CONNECTED] Streaming from server: {server_url}")

    client = SwarmWeaverClient(server_url)
    config = {
        "mode": mode,
        "project_dir": str(project_dir.resolve()),
        "task_input": task_input,
        "model": model,
        "max_iterations": max_iterations,
        "no_resume": no_resume,
        "parallel": parallel,
        "smart_swarm": smart_swarm,
        "budget": budget,
        "worktree": worktree,
    }

    async def _stream():
        try:
            async for event in client.stream_run(config):
                await on_event(event)
        except Exception as e:
            print(f"\n[CONNECTED] Connection error: {e}")

    try:
        asyncio.run(_stream())
    except KeyboardInterrupt:
        print("\n[CONNECTED] Disconnected.")
