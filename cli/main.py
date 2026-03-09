"""SwarmWeaver CLI - Typer application entry point."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

import typer

from cli.commands import greenfield as greenfield_mod
from cli.commands import feature as feature_mod
from cli.commands import refactor as refactor_mod
from cli.commands import fix as fix_mod
from cli.commands import evolve as evolve_mod
from cli.commands import security as security_mod
from cli.commands._common import ProjectDir

app = typer.Typer(
    name="swarmweaver",
    help="Autonomous Coding Agent - Multi-Mode",
    add_completion=True,
    no_args_is_help=True,
)


@app.callback(invoke_without_command=True)
def _load_config(ctx: typer.Context):
    """Load config from ~/.swarmweaver/config.toml before any command."""
    from cli.config import load_config
    ctx.ensure_object(dict)
    ctx.obj["config"] = load_config()

app.command("greenfield")(greenfield_mod.greenfield)
app.command("feature")(feature_mod.feature)
app.command("refactor")(refactor_mod.refactor)
app.command("fix")(fix_mod.fix)
app.command("evolve")(evolve_mod.evolve)
app.command("security")(security_mod.security)


# ── Status command ──────────────────────────────────────────────────

@app.command("status")
def status_cmd(
    project_dir: ProjectDir,
):
    """Show current project status (tasks, sessions, budget)."""
    from core.paths import get_paths
    from state.task_list import TaskList

    try:
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel
        console = Console()
        has_rich = True
    except ImportError:
        console = None
        has_rich = False

    paths = get_paths(project_dir)
    tl = TaskList(project_dir)
    tl.load()

    if has_rich:
        # Header
        console.print(f"\n[bold]Project:[/] {project_dir}")

        # Session info
        session_file = paths.session_state
        if session_file.exists():
            data = json.loads(session_file.read_text(encoding="utf-8"))
            console.print(f"[bold]Session:[/] {data.get('session_id', 'N/A')}")
            console.print(f"[bold]Phase:[/] {data.get('phase', 'N/A')}")

        # Budget info
        budget_file = paths.budget_state
        if budget_file.exists():
            data = json.loads(budget_file.read_text(encoding="utf-8"))
            spent = data.get("total_spent", 0)
            limit = data.get("limit", 0)
            if limit:
                console.print(f"[bold]Budget:[/] ${spent:.2f} / ${limit:.2f}")
            else:
                console.print(f"[bold]Budget:[/] ${spent:.2f} (unlimited)")

        # Task table
        if tl.tasks:
            table = Table(title=f"Tasks ({tl.done_count}/{tl.total} done, {tl.percentage_done:.0f}%)")
            table.add_column("ID", style="dim", width=12)
            table.add_column("Title", min_width=30)
            table.add_column("Status", width=12)
            table.add_column("Category", width=12)
            table.add_column("Priority", width=8, justify="center")

            STATUS_STYLES = {
                "done": "green",
                "in_progress": "yellow",
                "pending": "dim",
                "blocked": "red",
                "failed": "bold red",
                "skipped": "dim italic",
            }

            for task in tl.tasks:
                style = STATUS_STYLES.get(task.status, "")
                table.add_row(
                    task.id,
                    task.title[:50],
                    f"[{style}]{task.status}[/{style}]" if style else task.status,
                    task.category,
                    str(task.priority),
                )

            console.print()
            console.print(table)
        else:
            console.print("\n[dim]No tasks found.[/]")
    else:
        # Plain text fallback
        print(f"\nProject: {project_dir}")

        total = tl.total
        done = tl.done_count
        in_progress = tl.in_progress_count
        pending = tl.pending_count

        print(f"Tasks: {done}/{total} done, {in_progress} in progress, {pending} pending")

        session_file = paths.session_state
        if session_file.exists():
            data = json.loads(session_file.read_text(encoding="utf-8"))
            print(f"Session: {data.get('session_id', 'N/A')}")
            print(f"Phase: {data.get('phase', 'N/A')}")

        budget_file = paths.budget_state
        if budget_file.exists():
            data = json.loads(budget_file.read_text(encoding="utf-8"))
            spent = data.get("total_spent", 0)
            limit = data.get("limit", 0)
            if limit:
                print(f"Budget: ${spent:.2f} / ${limit:.2f}")
            else:
                print(f"Budget: ${spent:.2f} (unlimited)")


# ── Steer command ───────────────────────────────────────────────────

@app.command("steer")
def steer_cmd(
    run_id: Annotated[str, typer.Argument(help="Run ID to steer")],
    message: Annotated[str, typer.Argument(help="Steering instruction")],
    project_dir: Annotated[Path, typer.Option("--project-dir", help="Project directory")] = Path("."),
):
    """Send a steering message to a running agent."""
    from core.paths import get_paths

    paths = get_paths(project_dir)
    paths.ensure_dir()

    steering_data = {
        "message": message,
        "type": "instruction",
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
    }
    paths.steering_input.write_text(
        json.dumps(steering_data, indent=2), encoding="utf-8"
    )
    print(f"Steering message sent to run {run_id}:")
    print(f"  {message}")


# ── Merge command ───────────────────────────────────────────────────

@app.command("merge")
def merge_cmd(
    project_dir: Annotated[Path, typer.Option("--project-dir", help="Project directory")] = Path("."),
    discard: Annotated[bool, typer.Option("--discard", help="Discard instead of merge")] = False,
    run_id: Annotated[Optional[str], typer.Option("--run-id", help="Worktree run ID")] = None,
):
    """Merge or discard a worktree."""
    from core.worktree import (
        merge_worktree,
        discard_worktree,
        list_worktrees,
    )

    # If no run_id given, find the most recent worktree
    if not run_id:
        worktrees = list_worktrees(project_dir)
        if not worktrees:
            print("No worktrees found.")
            raise typer.Exit(1)
        if len(worktrees) == 1:
            run_id = worktrees[0].run_id
            print(f"Using worktree: {run_id}")
        else:
            print("Multiple worktrees found. Please specify --run-id:")
            for wt in worktrees:
                print(f"  {wt.run_id}  ({wt.files_changed} files changed)")
            raise typer.Exit(1)

    if discard:
        confirm = typer.confirm("Are you sure you want to discard all changes?")
        if not confirm:
            raise typer.Abort()
        discard_worktree(project_dir, run_id)
        print(f"Worktree {run_id} discarded. Original code is untouched.")
    else:
        result = merge_worktree(project_dir, run_id)
        if result.success:
            print(f"Merged {result.files_changed} files (tier: {result.resolution_tier_name})")
        else:
            print(f"Merge failed: {result.error}")
            raise typer.Exit(1)


# ── Logs command ────────────────────────────────────────────────────

@app.command("logs")
def logs_cmd(
    run_id: Annotated[Optional[str], typer.Argument(help="Run ID to filter (optional)")] = None,
    project_dir: Annotated[Path, typer.Option("--project-dir", help="Project directory")] = Path("."),
    event_type: Annotated[Optional[str], typer.Option("--type", help="Filter by event type (e.g. tool_start, error)")] = None,
    level: Annotated[Optional[str], typer.Option("--level", help="Filter by level (info, warn, error)")] = None,
    limit: Annotated[int, typer.Option("--limit", help="Max events to show")] = 50,
):
    """Show event logs from .swarmweaver/events.db."""
    from state.events import EventStore

    store = EventStore(project_dir)
    db_path = project_dir / ".swarmweaver" / "events.db"
    if not db_path.exists():
        print("No events database found. Run an agent first.")
        return

    store.initialize()
    events = store.query(
        run_id=run_id,
        event_type=event_type,
        level=level,
        limit=limit,
    )
    store.close()

    if not events:
        print("No events found.")
        return

    try:
        from rich.console import Console
        from rich.table import Table
        console = Console()

        table = Table(title=f"Event Logs ({len(events)} events)")
        table.add_column("Time", width=19)
        table.add_column("Type", width=14)
        table.add_column("Level", width=6)
        table.add_column("Agent", width=12)
        table.add_column("Tool", width=15)
        table.add_column("Duration", width=8, justify="right")

        LEVEL_STYLES = {"error": "bold red", "warn": "yellow", "info": "dim"}

        for ev in reversed(events):  # chronological order
            ts = ev.created_at[:19].replace("T", " ") if ev.created_at else ""
            lvl_style = LEVEL_STYLES.get(ev.level, "")
            dur = f"{ev.duration_ms}ms" if ev.duration_ms else ""
            table.add_row(
                ts,
                ev.event_type,
                f"[{lvl_style}]{ev.level}[/{lvl_style}]" if lvl_style else ev.level,
                ev.agent_name[:12] if ev.agent_name else "",
                ev.tool_name[:15] if ev.tool_name else "",
                dur,
            )

        console.print(table)
    except ImportError:
        for ev in reversed(events):
            ts = ev.created_at[:19].replace("T", " ") if ev.created_at else ""
            dur = f" ({ev.duration_ms}ms)" if ev.duration_ms else ""
            agent = f" [{ev.agent_name}]" if ev.agent_name else ""
            tool = f" {ev.tool_name}" if ev.tool_name else ""
            print(f"  {ts} {ev.level:5} {ev.event_type}{agent}{tool}{dur}")


# ── Checkpoint commands ─────────────────────────────────────────────

checkpoint_app = typer.Typer(help="Checkpoint management commands")
app.add_typer(checkpoint_app, name="checkpoint")

from cli.commands.mcp import mcp_app
app.add_typer(mcp_app, name="mcp")


@checkpoint_app.command("list")
def checkpoint_list(
    project_dir: Annotated[Path, typer.Option("--project-dir", help="Project directory")] = Path("."),
):
    """List available checkpoints."""
    from state.checkpoints import CheckpointManager

    mgr = CheckpointManager(project_dir)
    mgr.load()

    if not mgr.checkpoints:
        print("No checkpoints found.")
        return

    try:
        from rich.console import Console
        from rich.table import Table
        console = Console()

        table = Table(title=f"Checkpoints ({len(mgr.checkpoints)})")
        table.add_column("ID", style="dim", width=12)
        table.add_column("Description", min_width=30)
        table.add_column("Session", width=15)
        table.add_column("Iteration", width=10, justify="center")
        table.add_column("Timestamp", width=20)

        for cp in reversed(mgr.checkpoints[-20:]):  # Show most recent 20
            table.add_row(
                cp.id,
                cp.description[:50],
                cp.session_id[:15] if cp.session_id else "N/A",
                str(cp.iteration),
                cp.timestamp.strftime("%Y-%m-%d %H:%M"),
            )
        console.print(table)
    except ImportError:
        for cp in reversed(mgr.checkpoints[-20:]):
            print(f"  {cp.id}  {cp.description[:50]}  (iter {cp.iteration}, {cp.timestamp.strftime('%Y-%m-%d %H:%M')})")


@checkpoint_app.command("restore")
def checkpoint_restore(
    checkpoint_id: Annotated[str, typer.Argument(help="Checkpoint ID to restore")],
    project_dir: Annotated[Path, typer.Option("--project-dir", help="Project directory")] = Path("."),
):
    """Restore a checkpoint."""
    from state.checkpoints import CheckpointManager

    mgr = CheckpointManager(project_dir)
    mgr.load()

    cp = mgr.get_by_id(checkpoint_id)
    if not cp:
        print(f"Checkpoint '{checkpoint_id}' not found.")
        raise typer.Exit(1)

    confirm = typer.confirm(
        f"Restore checkpoint '{cp.description}' from {cp.timestamp.strftime('%Y-%m-%d %H:%M')}?"
    )
    if not confirm:
        raise typer.Abort()

    # Note: actual file restoration depends on the checkpoint system's capabilities.
    # The CheckpointManager stores metadata; file rollback is handled by the agent SDK.
    print(f"Checkpoint '{checkpoint_id}' marked for restoration.")
    print(f"  Description: {cp.description}")
    print(f"  Session: {cp.session_id}")
    print(f"  Iteration: {cp.iteration}")
    print("Note: File rollback requires the agent SDK checkpoint system.")


# ── Init command ────────────────────────────────────────────────────

@app.command("init")
def init_cmd(
    project_dir: Annotated[Path, typer.Option("--project-dir", help="Project directory")] = Path("."),
):
    """Initialize SwarmWeaver for a project (check auth, git, config)."""
    from cli.config import write_default_config, CONFIG_FILE

    print("SwarmWeaver Init")
    print("=" * 40)

    # 1. Check .env
    env_file = project_dir / ".env"
    if env_file.exists():
        print(f"\n[ok] .env file found at {env_file}")
    else:
        print("\n[!] No .env file found.")
        has_oauth = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "")
        has_api = os.environ.get("ANTHROPIC_API_KEY", "")
        if has_oauth:
            print("  CLAUDE_CODE_OAUTH_TOKEN is set in environment.")
        elif has_api:
            print("  ANTHROPIC_API_KEY is set in environment.")
        else:
            print("  No authentication found.")
            print("\n  Choose authentication method:")
            print("  1) Claude Code Max (OAuth token)")
            print("  2) Anthropic API key")
            choice = input("\n  Choice [1/2]: ").strip()
            if choice == "1":
                token = input("  Enter your OAuth token: ").strip()
                if token:
                    env_file.write_text(
                        f"CLAUDE_CODE_OAUTH_TOKEN={token}\n",
                        encoding="utf-8",
                    )
                    print(f"  Written to {env_file}")
            elif choice == "2":
                key = input("  Enter your API key: ").strip()
                if key:
                    env_file.write_text(
                        f"ANTHROPIC_API_KEY={key}\n",
                        encoding="utf-8",
                    )
                    print(f"  Written to {env_file}")
            else:
                print("  Skipped. Set credentials manually later.")

    # 2. Check git
    import subprocess
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True, cwd=str(project_dir),
    )
    if result.returncode == 0:
        print(f"\n[ok] Git repository detected in {project_dir}")
    else:
        print(f"\n[!] No git repository in {project_dir}")
        do_init = typer.confirm("  Initialize git?", default=True)
        if do_init:
            subprocess.run(["git", "init"], cwd=str(project_dir))
            print("  Git initialized.")

    # 3. Config file
    config_path = write_default_config()
    print(f"\n[ok] Config file: {config_path}")

    # 4. Model choice
    from core.models import DEFAULT_MODEL as _dm
    print(f"\n  Default model: {_dm}")
    print("  (Change in ~/.swarmweaver/config.toml or use --model flag)")

    print("\nSetup complete. Run 'swarmweaver --help' to get started.")


if __name__ == "__main__":
    app()
