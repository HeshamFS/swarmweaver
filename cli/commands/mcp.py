"""CLI commands for MCP server management."""

from pathlib import Path
from typing import Annotated, Optional

import typer

mcp_app = typer.Typer(help="Manage MCP (Model Context Protocol) servers")


def _get_store(project_dir: Optional[Path]):
    from services.mcp_manager import MCPConfigStore
    return MCPConfigStore(project_dir)


@mcp_app.command("list")
def mcp_list(
    project_dir: Annotated[Optional[Path], typer.Option("--project-dir", "-p", help="Project directory")] = None,
    scope: Annotated[str, typer.Option("--scope", help="Filter by scope: all, global, project, builtin")] = "all",
):
    """List all configured MCP servers."""
    store = _get_store(project_dir)
    servers = store.list_servers()

    if scope != "all":
        servers = [s for s in servers if s.scope == scope or (scope == "builtin" and s.builtin)]

    if not servers:
        print("No MCP servers configured.")
        return

    try:
        from rich.console import Console
        from rich.table import Table
        console = Console()

        table = Table(title=f"MCP Servers ({len(servers)})")
        table.add_column("Name", style="bold", min_width=15)
        table.add_column("Command", min_width=20)
        table.add_column("Status", width=10)
        table.add_column("Scope", width=10)
        table.add_column("Description", min_width=25)

        for s in servers:
            status = "[green]enabled[/]" if s.enabled else "[red]disabled[/]"
            scope_label = "[dim]builtin[/]" if s.builtin else s.scope
            cmd = f"{s.command} {' '.join(s.args)}"
            if len(cmd) > 40:
                cmd = cmd[:37] + "..."
            table.add_row(s.name, cmd, status, scope_label, s.description[:40])

        console.print(table)
    except ImportError:
        for s in servers:
            status = "enabled" if s.enabled else "DISABLED"
            print(f"  {s.name:20s} {status:10s} [{s.scope}] {s.description}")


@mcp_app.command("add")
def mcp_add(
    name: Annotated[str, typer.Argument(help="Server name (alphanumeric + _ -)")],
    command: Annotated[str, typer.Option("--command", "-c", help="Server command (e.g. 'npx', 'python')")],
    args: Annotated[Optional[str], typer.Option("--args", "-a", help="Space-separated args")] = None,
    env: Annotated[Optional[str], typer.Option("--env", "-e", help="KEY=VALUE pairs, comma-separated")] = None,
    description: Annotated[str, typer.Option("--description", "-d", help="Human description")] = "",
    timeout: Annotated[int, typer.Option("--timeout", help="Start timeout in seconds")] = 30,
    scope: Annotated[str, typer.Option("--scope", help="'project' or 'global'")] = "global",
    project_dir: Annotated[Optional[Path], typer.Option("--project-dir", "-p", help="Project directory")] = None,
):
    """Add a new MCP server."""
    from services.mcp_manager import MCPServerConfig

    # Parse args: accept JSON array or space-separated string
    parsed_args: list[str] = []
    if args:
        stripped = args.strip()
        if stripped.startswith("["):
            import json as _json
            try:
                parsed_args = _json.loads(stripped)
            except _json.JSONDecodeError:
                parsed_args = stripped.split()
        else:
            parsed_args = stripped.split()

    # Parse env: accept JSON object or KEY=VALUE,KEY=VALUE string
    parsed_env: dict[str, str] = {}
    if env:
        stripped_env = env.strip()
        if stripped_env.startswith("{"):
            import json as _json
            try:
                parsed_env = _json.loads(stripped_env)
            except _json.JSONDecodeError:
                pass
        if not parsed_env:
            for pair in env.split(","):
                pair = pair.strip()
                if "=" in pair:
                    k, _, v = pair.partition("=")
                    parsed_env[k.strip()] = v.strip()

    config = MCPServerConfig(
        name=name,
        command=command,
        args=parsed_args,
        env=parsed_env,
        description=description,
        timeout=timeout,
    )

    store = _get_store(project_dir)
    validation = store.validate_server(config)
    if not validation["valid"]:
        for err in validation["errors"]:
            print(f"  ERROR: {err}")
        raise typer.Exit(1)

    for warn in validation.get("warnings", []):
        print(f"  WARNING: {warn}")

    store.add_server(config, scope=scope)
    print(f"Added MCP server '{name}' ({scope})")


@mcp_app.command("remove")
def mcp_remove(
    name: Annotated[str, typer.Argument(help="Server name to remove")],
    scope: Annotated[str, typer.Option("--scope", help="'project' or 'global'")] = "global",
    project_dir: Annotated[Optional[Path], typer.Option("--project-dir", "-p", help="Project directory")] = None,
):
    """Remove an MCP server."""
    store = _get_store(project_dir)
    server = store.get_server(name)
    if server and server.builtin:
        print(f"Cannot remove built-in server '{name}'. Use 'swarmweaver mcp disable {name}' instead.")
        raise typer.Exit(1)

    if store.remove_server(name, scope=scope):
        print(f"Removed MCP server '{name}' from {scope} config")
    else:
        print(f"Server '{name}' not found in {scope} config")
        raise typer.Exit(1)


@mcp_app.command("enable")
def mcp_enable(
    name: Annotated[str, typer.Argument(help="Server name")],
    project_dir: Annotated[Optional[Path], typer.Option("--project-dir", "-p", help="Project directory")] = None,
):
    """Enable an MCP server."""
    store = _get_store(project_dir)
    result = store.enable_server(name)
    if result:
        print(f"Enabled MCP server '{name}'")
    else:
        print(f"Server '{name}' not found")
        raise typer.Exit(1)


@mcp_app.command("disable")
def mcp_disable(
    name: Annotated[str, typer.Argument(help="Server name")],
    project_dir: Annotated[Optional[Path], typer.Option("--project-dir", "-p", help="Project directory")] = None,
):
    """Disable an MCP server."""
    store = _get_store(project_dir)
    result = store.disable_server(name)
    if result:
        print(f"Disabled MCP server '{name}'")
    else:
        print(f"Server '{name}' not found")
        raise typer.Exit(1)


@mcp_app.command("test")
def mcp_test(
    name: Annotated[str, typer.Argument(help="Server name to test")],
    project_dir: Annotated[Optional[Path], typer.Option("--project-dir", "-p", help="Project directory")] = None,
):
    """Test if an MCP server can start."""
    store = _get_store(project_dir)
    print(f"Testing MCP server '{name}'...")
    result = store.test_server(name)
    if result["success"]:
        print(f"  OK: {result['message']} ({result['duration_ms']}ms)")
    else:
        print(f"  FAILED: {result['message']} ({result['duration_ms']}ms)")
        raise typer.Exit(1)
