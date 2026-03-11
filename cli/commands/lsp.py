"""CLI commands for LSP language server management."""

from pathlib import Path
from typing import Annotated, Optional

import typer

lsp_app = typer.Typer(help="LSP language server management")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TIER_LABELS = {1: "core", 2: "secondary", 3: "specialty", 4: "config/markup"}
SEVERITY_LABELS = {1: "error", 2: "warning", 3: "info", 4: "hint"}
SEVERITY_MAP = {"error": 1, "warning": 2, "info": 3, "hint": 4}


def _load_config(project_dir: Path):
    from services.lsp_manager import LSPConfig
    return LSPConfig.load(project_dir)


def _load_manager_state(project_dir: Path):
    """Load LSP server state from the runtime state file if it exists."""
    import json

    state_file = project_dir / ".swarmweaver" / "lsp_state.json"
    if state_file.exists():
        try:
            return json.loads(state_file.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return None


# ---------------------------------------------------------------------------
# lsp status
# ---------------------------------------------------------------------------

@lsp_app.command("status")
def lsp_status(
    project_dir: Annotated[Path, typer.Option("--project-dir", "-p", help="Project directory")] = Path("."),
):
    """Show all running LSP servers (language, server name, status, PID, file count, diagnostic count)."""
    import json

    config = _load_config(project_dir)

    try:
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel
        console = Console()

        # Config summary
        lines = [
            f"Enabled: {config.enabled}",
            f"Auto-detect: {config.auto_detect}",
            f"Auto-install: {config.auto_install}",
            f"Max servers/worktree: {config.max_servers_per_worktree}",
            f"Request timeout: {config.request_timeout_s}s",
            f"Health check interval: {config.health_check_interval_s}s",
            f"Diagnostics debounce: {config.diagnostics_debounce_ms}ms",
        ]
        if config.disabled_servers:
            lines.append(f"Disabled servers: {', '.join(config.disabled_servers)}")
        console.print(Panel("\n".join(lines), title="LSP Configuration"))

        # Try to load runtime state
        state = _load_manager_state(project_dir)
        if state and state.get("servers"):
            servers = state["servers"]
            table = Table(title=f"Running LSP Servers ({len(servers)})")
            table.add_column("Language", width=12)
            table.add_column("Server", width=28)
            table.add_column("Status", width=10)
            table.add_column("PID", width=8, justify="right")
            table.add_column("Files", width=7, justify="right")
            table.add_column("Diagnostics", width=12, justify="right")

            STATUS_COLORS = {
                "ready": "green",
                "starting": "blue",
                "degraded": "yellow",
                "crashed": "red",
                "stopped": "dim",
            }

            for srv in servers:
                status = srv.get("status", "unknown")
                color = STATUS_COLORS.get(status, "")
                pid = srv.get("pid")
                pid_str = str(pid) if pid else "-"
                files = srv.get("open_files", 0)
                diag_count = srv.get("diagnostic_count", 0)

                table.add_row(
                    srv.get("language_id", ""),
                    srv.get("server_name", ""),
                    f"[{color}]{status}[/{color}]" if color else status,
                    pid_str,
                    str(files),
                    str(diag_count),
                )
            console.print(table)
        else:
            console.print("\n[dim]No running LSP servers. Start a swarm session to auto-launch servers.[/]")

    except ImportError:
        print(f"LSP config for {project_dir}:")
        print(f"  Enabled: {config.enabled}")
        print(f"  Auto-detect: {config.auto_detect}")
        print(f"  Auto-install: {config.auto_install}")
        print(f"  Max servers/worktree: {config.max_servers_per_worktree}")

        state = _load_manager_state(project_dir)
        if state and state.get("servers"):
            print(f"\nRunning servers ({len(state['servers'])}):")
            for srv in state["servers"]:
                print(f"  {srv.get('language_id', '?'):12s}  {srv.get('server_name', '?'):28s}  {srv.get('status', '?'):10s}  PID={srv.get('pid', '-')}")
        else:
            print("\nNo running LSP servers.")


# ---------------------------------------------------------------------------
# lsp diagnostics
# ---------------------------------------------------------------------------

@lsp_app.command("diagnostics")
def lsp_diagnostics(
    project_dir: Annotated[Path, typer.Option("--project-dir", "-p", help="Project directory")] = Path("."),
    severity: Annotated[Optional[str], typer.Option("--severity", "-s", help="Filter by severity (error, warning, info, hint)")] = None,
    file_filter: Annotated[Optional[str], typer.Option("--file", "-f", help="Filter by file path substring")] = None,
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max diagnostics to show")] = 50,
):
    """Show diagnostics table (file, line, severity, message, source)."""
    import json

    state = _load_manager_state(project_dir)
    if not state or not state.get("servers"):
        print("No LSP state found. Run a swarm session first to collect diagnostics.")
        raise typer.Exit(1)

    # Collect all diagnostics from state
    all_diags: list[dict] = []
    for srv in state.get("servers", []):
        for uri, diags in srv.get("diagnostics", {}).items():
            for d in diags:
                all_diags.append({
                    "file": uri,
                    "line": d.get("range", {}).get("start", {}).get("line", 0) + 1,
                    "severity": d.get("severity", 4),
                    "message": d.get("message", ""),
                    "source": d.get("source", ""),
                })

    # Also check the dedicated diagnostics state file
    diag_file = project_dir / ".swarmweaver" / "lsp_diagnostics.json"
    if diag_file.exists():
        try:
            diag_data = json.loads(diag_file.read_text())
            for d in diag_data if isinstance(diag_data, list) else diag_data.get("diagnostics", []):
                all_diags.append({
                    "file": d.get("uri", d.get("file", "")),
                    "line": d.get("line", d.get("start_line", 0) + 1),
                    "severity": d.get("severity", 4),
                    "message": d.get("message", ""),
                    "source": d.get("source", ""),
                })
        except (json.JSONDecodeError, OSError):
            pass

    if not all_diags:
        print("No diagnostics recorded.")
        return

    # Apply severity filter
    if severity:
        sev_value = SEVERITY_MAP.get(severity.lower())
        if sev_value is None:
            print(f"Unknown severity: {severity}. Use: error, warning, info, hint")
            raise typer.Exit(1)
        all_diags = [d for d in all_diags if d["severity"] == sev_value]

    # Apply file filter
    if file_filter:
        all_diags = [d for d in all_diags if file_filter in d["file"]]

    # Sort by severity (errors first), then file, then line
    all_diags.sort(key=lambda d: (d["severity"], d["file"], d["line"]))
    total = len(all_diags)
    all_diags = all_diags[:limit]

    try:
        from rich.console import Console
        from rich.table import Table
        console = Console()

        table = Table(title=f"LSP Diagnostics ({len(all_diags)} of {total})")
        table.add_column("File", min_width=20)
        table.add_column("Line", width=6, justify="right")
        table.add_column("Severity", width=10)
        table.add_column("Message", min_width=30)
        table.add_column("Source", width=14)

        SEVERITY_COLORS = {1: "red", 2: "yellow", 3: "cyan", 4: "dim"}

        for d in all_diags:
            sev = d["severity"]
            sev_label = SEVERITY_LABELS.get(sev, "unknown")
            color = SEVERITY_COLORS.get(sev, "")
            # Trim file URI prefix for readability
            file_path = d["file"]
            if file_path.startswith("file://"):
                file_path = file_path[7:]

            table.add_row(
                file_path[-40:] if len(file_path) > 40 else file_path,
                str(d["line"]),
                f"[{color}]{sev_label}[/{color}]" if color else sev_label,
                d["message"][:80],
                d["source"],
            )
        console.print(table)
    except ImportError:
        print(f"LSP Diagnostics ({len(all_diags)} of {total}):")
        for d in all_diags:
            sev_label = SEVERITY_LABELS.get(d["severity"], "?")
            file_path = d["file"]
            if file_path.startswith("file://"):
                file_path = file_path[7:]
            print(f"  {file_path}:{d['line']}  [{sev_label}]  {d['message'][:60]}  ({d['source']})")


# ---------------------------------------------------------------------------
# lsp servers
# ---------------------------------------------------------------------------

@lsp_app.command("servers")
def lsp_servers(
    project_dir: Annotated[Path, typer.Option("--project-dir", "-p", help="Project directory")] = Path("."),
):
    """List all available LSP server specifications (22 built-in servers)."""
    from services.lsp_manager import BUILTIN_SERVER_SPECS

    config = _load_config(project_dir)

    try:
        from rich.console import Console
        from rich.table import Table
        console = Console()

        table = Table(title=f"Available LSP Servers ({len(BUILTIN_SERVER_SPECS)})")
        table.add_column("Language", width=14)
        table.add_column("Server Name", width=30)
        table.add_column("Command", width=24)
        table.add_column("Install Command", min_width=20)
        table.add_column("Tier", width=14)

        for spec in BUILTIN_SERVER_SPECS:
            disabled = spec.server_name in config.disabled_servers
            tier_label = TIER_LABELS.get(spec.priority, str(spec.priority))
            name_display = f"[dim strikethrough]{spec.server_name}[/]" if disabled else spec.server_name
            cmd_str = f"{spec.command} {' '.join(spec.args)}".strip()

            table.add_row(
                spec.language_id,
                name_display,
                cmd_str,
                spec.install_command or "[dim]-[/]",
                tier_label,
            )
        console.print(table)

        if config.disabled_servers:
            console.print(f"\n[dim]Disabled: {', '.join(config.disabled_servers)}[/]")

    except ImportError:
        print(f"Available LSP Servers ({len(BUILTIN_SERVER_SPECS)}):")
        for spec in BUILTIN_SERVER_SPECS:
            disabled = " (DISABLED)" if spec.server_name in config.disabled_servers else ""
            tier_label = TIER_LABELS.get(spec.priority, str(spec.priority))
            cmd_str = f"{spec.command} {' '.join(spec.args)}".strip()
            print(f"  {spec.language_id:14s}  {spec.server_name:30s}  {cmd_str:24s}  tier={tier_label}{disabled}")


# ---------------------------------------------------------------------------
# lsp config
# ---------------------------------------------------------------------------

@lsp_app.command("config")
def lsp_config_cmd(
    project_dir: Annotated[Path, typer.Option("--project-dir", "-p", help="Project directory")] = Path("."),
    set_value: Annotated[Optional[str], typer.Option("--set", help="Set a config value (KEY=VALUE)")] = None,
):
    """View or edit LSP config (.swarmweaver/lsp.yaml)."""
    config = _load_config(project_dir)

    if set_value:
        if "=" not in set_value:
            print("Use --set KEY=VALUE format")
            raise typer.Exit(1)
        key, value = set_value.split("=", 1)
        if not hasattr(config, key):
            print(f"Unknown config key: {key}")
            print(f"Valid keys: enabled, auto_install, auto_detect, max_servers_per_worktree, "
                  f"health_check_interval_s, request_timeout_s, diagnostics_debounce_ms, "
                  f"diagnostics_timeout_s, max_diagnostics_per_file")
            raise typer.Exit(1)

        field_type = type(getattr(config, key))
        try:
            if field_type is bool:
                setattr(config, key, value.lower() in ("1", "true", "yes"))
            elif field_type is list:
                setattr(config, key, [v.strip() for v in value.split(",") if v.strip()])
            elif field_type is dict:
                import json
                setattr(config, key, json.loads(value))
            else:
                setattr(config, key, field_type(value))
        except (ValueError, TypeError) as e:
            print(f"Invalid value for {key}: {e}")
            raise typer.Exit(1)

        # Write updated config to lsp.yaml
        yaml_path = project_dir / ".swarmweaver" / "lsp.yaml"
        yaml_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            import yaml

            # Load existing config or start fresh
            existing: dict = {}
            if yaml_path.exists():
                with open(yaml_path) as f:
                    existing = yaml.safe_load(f) or {}
            existing[key] = getattr(config, key)
            with open(yaml_path, "w") as f:
                yaml.safe_dump(existing, f, default_flow_style=False)
            print(f"Set {key} = {getattr(config, key)}")
        except ImportError:
            # Fallback: write as simple key=value if yaml unavailable
            import json
            existing = {}
            if yaml_path.exists():
                try:
                    existing = json.loads(yaml_path.read_text())
                except Exception:
                    pass
            existing[key] = getattr(config, key)
            yaml_path.write_text(json.dumps(existing, indent=2))
            print(f"Set {key} = {getattr(config, key)} (saved as JSON; install pyyaml for YAML format)")
    else:
        import json

        # Build a dict of all config fields
        config_dict = {
            "enabled": config.enabled,
            "auto_install": config.auto_install,
            "auto_detect": config.auto_detect,
            "max_servers_per_worktree": config.max_servers_per_worktree,
            "health_check_interval_s": config.health_check_interval_s,
            "request_timeout_s": config.request_timeout_s,
            "diagnostics_debounce_ms": config.diagnostics_debounce_ms,
            "diagnostics_timeout_s": config.diagnostics_timeout_s,
            "max_diagnostics_per_file": config.max_diagnostics_per_file,
            "disabled_servers": config.disabled_servers,
            "custom_servers": config.custom_servers,
            "server_overrides": config.server_overrides,
        }
        print(json.dumps(config_dict, indent=2))


# ---------------------------------------------------------------------------
# lsp restart
# ---------------------------------------------------------------------------

@lsp_app.command("restart")
def lsp_restart(
    server_id: Annotated[Optional[str], typer.Argument(help="Server name to restart (e.g. 'pyright'), or omit for all")] = None,
    project_dir: Annotated[Path, typer.Option("--project-dir", "-p", help="Project directory")] = Path("."),
):
    """Restart a specific LSP server or all servers."""
    import json

    state = _load_manager_state(project_dir)
    if not state or not state.get("servers"):
        print("No running LSP servers found.")
        raise typer.Exit(1)

    servers = state["servers"]

    if server_id:
        # Find the matching server
        matching = [s for s in servers if s.get("server_name") == server_id]
        if not matching:
            available = [s.get("server_name", "?") for s in servers]
            print(f"Server '{server_id}' not found. Running servers: {', '.join(available)}")
            raise typer.Exit(1)

        for srv in matching:
            pid = srv.get("pid")
            if pid:
                _signal_restart(pid, srv.get("server_name", "?"))
            else:
                print(f"No PID for {srv.get('server_name', '?')}; cannot restart.")
    else:
        # Restart all
        restarted = 0
        for srv in servers:
            pid = srv.get("pid")
            if pid:
                _signal_restart(pid, srv.get("server_name", "?"))
                restarted += 1
        if restarted == 0:
            print("No servers with PIDs to restart.")
        else:
            print(f"Sent restart signal to {restarted} server(s).")


def _signal_restart(pid: int, name: str) -> None:
    """Send SIGUSR1 to an LSP server process to trigger a restart, or SIGTERM + note."""
    import signal
    import os

    try:
        # Check if process is alive
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        print(f"  {name} (PID {pid}): process not running")
        return

    try:
        os.kill(pid, signal.SIGTERM)
        print(f"  {name} (PID {pid}): terminated (will be auto-restarted by manager)")
    except (OSError, PermissionError) as e:
        print(f"  {name} (PID {pid}): failed to signal — {e}")
