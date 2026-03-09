"""CLI commands for watchdog health monitoring."""

from pathlib import Path
from typing import Annotated, Optional

import typer

watchdog_app = typer.Typer(help="Watchdog health monitoring")


def _get_config(project_dir: Path):
    from services.watchdog import WatchdogConfig
    return WatchdogConfig.load(project_dir)


def _get_store(project_dir: Path):
    from services.watchdog import WatchdogEventStore
    store = WatchdogEventStore(project_dir)
    if not store.db_path.exists():
        print("No watchdog events database found. Run a swarm session first.")
        raise typer.Exit(1)
    store.initialize()
    return store


@watchdog_app.command("status")
def watchdog_status(
    project_dir: Annotated[Path, typer.Option("--project-dir", "-p", help="Project directory")] = Path("."),
):
    """Show fleet health score, worker states, and circuit breaker status."""
    from services.watchdog import WatchdogConfig, WatchdogEventStore, SwarmWatchdog
    import json

    config = WatchdogConfig.load(project_dir)

    try:
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel
        console = Console()

        # Config summary
        lines = [
            f"Enabled: {config.enabled}",
            f"Check interval: {config.check_interval_s}s",
            f"Idle threshold: {config.idle_threshold_s}s",
            f"Stall threshold: {config.stall_threshold_s}s",
            f"Boot grace: {config.boot_grace_s}s",
            f"AI triage: {'enabled' if config.ai_triage_enabled else 'disabled'}",
            f"Auto-reassign: {config.auto_reassign}",
            f"Circuit breaker: {'enabled' if config.circuit_breaker_enabled else 'disabled'}",
        ]
        console.print(Panel("\n".join(lines), title="Watchdog Configuration"))

        # Try to load health state from swarm
        health_file = project_dir / ".swarmweaver" / "swarm" / "watchdog_state.json"
        if health_file.exists():
            try:
                data = json.loads(health_file.read_text())
                workers = data.get("workers", {})
                if workers:
                    table = Table(title=f"Worker Health ({len(workers)} workers)")
                    table.add_column("ID", width=5, justify="center")
                    table.add_column("Status", width=12)
                    table.add_column("Role", width=10)
                    table.add_column("Last Activity", width=15)
                    table.add_column("Escalation", width=10, justify="center")

                    STATUS_COLORS = {
                        "booting": "blue", "working": "green", "idle": "dim",
                        "warning": "yellow", "stalled": "red", "recovering": "cyan",
                        "completed": "green", "zombie": "magenta", "terminated": "dim",
                    }

                    for wid, w in workers.items():
                        status = w.get("status", "unknown")
                        color = STATUS_COLORS.get(status, "")
                        ago = w.get("last_output_ago_seconds", -1)
                        ago_str = f"{ago}s ago" if ago >= 0 else "N/A"
                        table.add_row(
                            str(wid),
                            f"[{color}]{status}[/{color}]" if color else status,
                            w.get("role", ""),
                            ago_str,
                            str(w.get("escalation_level", 0)),
                        )
                    console.print(table)

                # Circuit breaker
                cb = data.get("circuit_breaker", {})
                if cb:
                    state = cb.get("state", "closed")
                    cb_color = "green" if state == "closed" else "yellow" if state == "half_open" else "red"
                    console.print(f"\nCircuit Breaker: [{cb_color}]{state.upper()}[/{cb_color}] (failure rate: {cb.get('failure_rate', 0):.0%})")
            except (json.JSONDecodeError, OSError):
                pass

        # Recent events
        store_path = project_dir / ".swarmweaver" / "watchdog_events.db"
        if store_path.exists():
            store = WatchdogEventStore(project_dir)
            store.initialize()
            events = store.query(limit=5)
            store.close()
            if events:
                table = Table(title="Recent Events")
                table.add_column("Time", width=19)
                table.add_column("Type", width=14)
                table.add_column("Worker", width=7, justify="center")
                table.add_column("Message", min_width=30)

                for ev in events:
                    ts = ev.get("timestamp", "")[:19].replace("T", " ")
                    table.add_row(
                        ts,
                        ev.get("event_type", ""),
                        str(ev.get("worker_id", "")),
                        (ev.get("message", ""))[:60],
                    )
                console.print(table)
        else:
            console.print("\n[dim]No watchdog events recorded yet.[/]")

    except ImportError:
        print(f"Watchdog config for {project_dir}:")
        print(f"  Enabled: {config.enabled}")
        print(f"  Check interval: {config.check_interval_s}s")
        print(f"  Stall threshold: {config.stall_threshold_s}s")


@watchdog_app.command("events")
def watchdog_events(
    project_dir: Annotated[Path, typer.Option("--project-dir", "-p", help="Project directory")] = Path("."),
    worker_id: Annotated[Optional[int], typer.Option("--worker-id", "-w", help="Filter by worker ID")] = None,
    event_type: Annotated[Optional[str], typer.Option("--type", "-t", help="Filter by event type")] = None,
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max events to return")] = 20,
):
    """Show recent watchdog events."""
    store = _get_store(project_dir)
    events = store.query(worker_id=worker_id, event_type=event_type, limit=limit)
    store.close()

    if not events:
        print("No events found.")
        return

    try:
        from rich.console import Console
        from rich.table import Table
        console = Console()

        table = Table(title=f"Watchdog Events ({len(events)})")
        table.add_column("Time", width=19)
        table.add_column("Type", width=14)
        table.add_column("Worker", width=7, justify="center")
        table.add_column("Before", width=10)
        table.add_column("After", width=10)
        table.add_column("Message", min_width=30)

        for ev in events:
            ts = ev.get("timestamp", "")[:19].replace("T", " ")
            table.add_row(
                ts,
                ev.get("event_type", ""),
                str(ev.get("worker_id", "")),
                ev.get("state_before", ""),
                ev.get("state_after", ""),
                (ev.get("message", ""))[:50],
            )
        console.print(table)
    except ImportError:
        for ev in events:
            ts = ev.get("timestamp", "")[:19].replace("T", " ")
            print(f"  {ts}  [{ev.get('event_type', '')}]  W{ev.get('worker_id', '?')}  {ev.get('message', '')[:60]}")


@watchdog_app.command("config")
def watchdog_config_cmd(
    project_dir: Annotated[Path, typer.Option("--project-dir", "-p", help="Project directory")] = Path("."),
    set_value: Annotated[Optional[str], typer.Option("--set", help="Set a config value (KEY=VALUE)")] = None,
):
    """Show or edit watchdog configuration."""
    config = _get_config(project_dir)

    if set_value:
        if "=" not in set_value:
            print("Use --set KEY=VALUE format")
            raise typer.Exit(1)
        key, value = set_value.split("=", 1)
        if not hasattr(config, key):
            print(f"Unknown config key: {key}")
            raise typer.Exit(1)
        field_type = type(getattr(config, key))
        try:
            if field_type is bool:
                setattr(config, key, value.lower() in ("1", "true", "yes"))
            elif field_type is set:
                setattr(config, key, set(value.split(",")))
            else:
                setattr(config, key, field_type(value))
        except (ValueError, TypeError) as e:
            print(f"Invalid value for {key}: {e}")
            raise typer.Exit(1)
        config.save(project_dir)
        print(f"Set {key} = {getattr(config, key)}")
    else:
        import json
        print(json.dumps(config.to_dict(), indent=2))


@watchdog_app.command("triage")
def watchdog_triage(
    worker_id: Annotated[int, typer.Argument(help="Worker ID to triage")],
    project_dir: Annotated[Path, typer.Option("--project-dir", "-p", help="Project directory")] = Path("."),
):
    """Manually trigger AI triage for a specific worker."""
    import asyncio as _aio
    from services.watchdog import SwarmWatchdog, WatchdogConfig, WorkerHealth, AgentState

    config = WatchdogConfig.load(project_dir)
    watchdog = SwarmWatchdog(config=config, project_dir=project_dir)

    # Create a synthetic health record
    health = WorkerHealth(
        worker_id=worker_id,
        status=AgentState.STALLED,
        last_output_time=0,
        role="builder",
    )

    print(f"Running AI triage for worker {worker_id}...")

    async def _run():
        return await watchdog._ai_triage_llm(health)

    try:
        result = _aio.run(_run())
    except Exception:
        result = watchdog._ai_triage_heuristic(health)

    try:
        from rich.console import Console
        from rich.panel import Panel
        import json
        console = Console()

        verdict = result.get("verdict", "unknown")
        confidence = result.get("confidence", 0)
        verdict_color = {"retry": "yellow", "extend": "cyan", "reassign": "magenta", "terminate": "red"}.get(verdict, "white")

        lines = [
            f"Verdict: [{verdict_color}]{verdict.upper()}[/{verdict_color}]",
            f"Confidence: {confidence:.0%}",
            f"Reasoning: {result.get('reasoning', 'N/A')}",
            f"Action: {result.get('recommended_action', 'N/A')}",
        ]
        if result.get("suggested_nudge_message"):
            lines.append(f"Nudge: {result['suggested_nudge_message']}")
        if result.get("tasks_to_reassign"):
            lines.append(f"Reassign: {result['tasks_to_reassign']}")

        console.print(Panel("\n".join(lines), title=f"Triage Result — Worker {worker_id}"))
    except ImportError:
        import json
        print(json.dumps(result, indent=2))


@watchdog_app.command("nudge")
def watchdog_nudge(
    worker_id: Annotated[int, typer.Argument(help="Worker ID to nudge")],
    project_dir: Annotated[Path, typer.Option("--project-dir", "-p", help="Project directory")] = Path("."),
    message: Annotated[str, typer.Option("--message", "-m", help="Nudge message")] = "",
):
    """Send a nudge to a specific worker."""
    from services.watchdog import SwarmWatchdog, WorkerHealth, AgentState
    import json

    # Try to find worker info from swarm state
    health_file = project_dir / ".swarmweaver" / "swarm" / "watchdog_state.json"
    worktree_path = str(project_dir)
    pid = None

    if health_file.exists():
        try:
            data = json.loads(health_file.read_text())
            workers = data.get("workers", {})
            w = workers.get(str(worker_id), {})
            worktree_path = w.get("worktree_path", str(project_dir))
            pid = w.get("pid")
        except (json.JSONDecodeError, OSError):
            pass

    health = WorkerHealth(
        worker_id=worker_id,
        pid=pid,
        worktree_path=worktree_path,
        status=AgentState.STALLED,
    )

    watchdog = SwarmWatchdog()
    result = watchdog._nudge_worker(health, message)

    if result["success"]:
        print(f"Nudge sent to worker {worker_id} via {result['method']}")
    else:
        print(f"Failed to nudge worker {worker_id}")
