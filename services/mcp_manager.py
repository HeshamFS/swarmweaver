"""MCP Server Configuration Manager.

Manages user-configurable MCP servers at two levels:
- Global: ~/.swarmweaver/mcp_servers.json (shared across all projects)
- Project: <project>/.swarmweaver/mcp_servers.json (project-specific overrides)

Servers are merged at runtime: project configs override global configs by name.
Built-in servers (puppeteer, web_search) are always available but can be disabled.
"""

import json
import shutil
import subprocess
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional
from enum import Enum


class MCPTransport(str, Enum):
    STDIO = "stdio"
    # Future: SSE = "sse", HTTP = "http"


class MCPServerStatus(str, Enum):
    CONNECTED = "connected"      # Running and healthy
    DISCONNECTED = "disconnected" # Not started
    FAILED = "failed"            # Failed to start or lost connection
    DISABLED = "disabled"        # Explicitly disabled by user


@dataclass
class MCPServerConfig:
    """Configuration for a single MCP server."""
    name: str
    command: str                            # e.g. "npx" or "python"
    args: list[str] = field(default_factory=list)  # e.g. ["puppeteer-mcp-server"]
    env: dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    transport: str = "stdio"               # Only stdio for now
    timeout: int = 30                      # Seconds to wait for server start
    description: str = ""                  # Human-readable description
    scope: str = "project"                 # "global" or "project"
    builtin: bool = False                  # True for puppeteer, web_search

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "MCPServerConfig":
        # Remove unknown keys gracefully
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)

    def to_sdk_format(self) -> dict:
        """Convert to the format expected by claude_agent_sdk mcp_servers dict."""
        result = {
            "command": _wsl_fixup_path(self.command),
            "args": _wsl_fixup_args(list(self.args)),
        }
        if self.env:
            result["env"] = dict(self.env)
        return result


GLOBAL_CONFIG_DIR = Path.home() / ".swarmweaver"
GLOBAL_MCP_FILE = GLOBAL_CONFIG_DIR / "mcp_servers.json"

# Detect WSL for automatic path conversion
_IS_WSL = False
try:
    _IS_WSL = "microsoft" in Path("/proc/version").read_text().lower()
except Exception:
    pass


def _wsl_fixup_path(p: str) -> str:
    """Convert Windows-style paths (D:/...) to WSL paths (/mnt/d/...) when running in WSL."""
    if not _IS_WSL:
        return p
    # Match D:/ or D:\ style Windows paths
    if len(p) >= 3 and p[0].isalpha() and p[1] == ":" and p[2] in ("/", "\\"):
        drive = p[0].lower()
        rest = p[3:].replace("\\", "/")
        return f"/mnt/{drive}/{rest}"
    return p


def _wsl_fixup_args(args: list[str]) -> list[str]:
    """Apply WSL path fixup to command arguments that look like file paths."""
    return [_wsl_fixup_path(a) for a in args]


def _project_mcp_file(project_dir: Path) -> Path:
    return project_dir / ".swarmweaver" / "mcp_servers.json"


class MCPConfigStore:
    """Manages MCP server configurations with two-level merge (global + project)."""

    def __init__(self, project_dir: Optional[Path] = None):
        self.project_dir = Path(project_dir) if project_dir else None

    # ── CRUD ──────────────────────────────────────────────────────

    def list_servers(self, include_builtin: bool = True) -> list[MCPServerConfig]:
        """Return merged list of all MCP servers (global + project).
        Project configs override global by name.
        """
        servers: dict[str, MCPServerConfig] = {}

        # 1. Built-in servers (always present, can be overridden/disabled)
        if include_builtin:
            for s in self._builtin_servers():
                servers[s.name] = s

        # 2. Global user configs
        for s in self._load_file(GLOBAL_MCP_FILE, scope="global"):
            servers[s.name] = s

        # 3. Project configs (highest priority)
        if self.project_dir:
            pf = _project_mcp_file(self.project_dir)
            for s in self._load_file(pf, scope="project"):
                servers[s.name] = s

        return sorted(servers.values(), key=lambda s: (not s.builtin, s.name))

    def get_server(self, name: str) -> Optional[MCPServerConfig]:
        for s in self.list_servers():
            if s.name == name:
                return s
        return None

    def add_server(self, config: MCPServerConfig, scope: str = "project") -> MCPServerConfig:
        """Add or update an MCP server config."""
        config.scope = scope
        target = self._target_file(scope)
        servers = self._load_file(target, scope=scope)
        # Replace if exists, else append
        servers = [s for s in servers if s.name != config.name]
        servers.append(config)
        self._save_file(target, servers)
        return config

    def remove_server(self, name: str, scope: str = "project") -> bool:
        """Remove an MCP server config. Returns True if found and removed."""
        target = self._target_file(scope)
        servers = self._load_file(target, scope=scope)
        before = len(servers)
        servers = [s for s in servers if s.name != name]
        if len(servers) == before:
            return False
        self._save_file(target, servers)
        return True

    def enable_server(self, name: str) -> Optional[MCPServerConfig]:
        """Enable a server. Searches project then global."""
        return self._set_enabled(name, True)

    def disable_server(self, name: str) -> Optional[MCPServerConfig]:
        """Disable a server. Searches project then global."""
        return self._set_enabled(name, False)

    def get_enabled_sdk_servers(self) -> dict[str, dict]:
        """Return MCP servers dict ready for Claude SDK's mcp_servers param.
        Only returns enabled servers.
        """
        result = {}
        for s in self.list_servers():
            if s.enabled:
                result[s.name] = s.to_sdk_format()
        return result

    def get_enabled_tool_names(self) -> list[str]:
        """Return tool name patterns for all enabled MCP servers (mcp__{name}__*)."""
        return [f"mcp__{s.name}__*" for s in self.list_servers() if s.enabled]

    # ── Validation ────────────────────────────────────────────────

    def validate_server(self, config: MCPServerConfig) -> dict:
        """Validate that a server config is likely to work.
        Returns {"valid": bool, "errors": [...], "warnings": [...]}.
        """
        errors = []
        warnings = []

        if not config.name:
            errors.append("Server name is required")
        elif not config.name.replace("_", "").replace("-", "").isalnum():
            errors.append("Server name must be alphanumeric (plus _ and -)")

        if not config.command:
            errors.append("Command is required")
        else:
            # Check if command is available on PATH
            cmd_path = shutil.which(config.command)
            if not cmd_path:
                warnings.append(f"Command '{config.command}' not found on PATH (may still work if installed later)")

        if config.timeout < 1 or config.timeout > 300:
            errors.append("Timeout must be between 1 and 300 seconds")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }

    def test_server(self, name: str) -> dict:
        """Test if a server can start by attempting to run its command.
        Returns {"success": bool, "message": str, "duration_ms": int}.
        """
        server = self.get_server(name)
        if not server:
            return {"success": False, "message": f"Server '{name}' not found", "duration_ms": 0}

        if not server.enabled:
            return {"success": False, "message": f"Server '{name}' is disabled", "duration_ms": 0}

        start = time.monotonic()
        try:
            cmd = [_wsl_fixup_path(server.command)] + _wsl_fixup_args(server.args)
            env = {**dict(__import__("os").environ), **server.env} if server.env else None
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
            # Give it a brief moment to crash or start
            try:
                proc.wait(timeout=3)
                # If it exited, check return code
                stderr = proc.stderr.read().decode(errors="replace")[:500]
                if proc.returncode != 0:
                    return {
                        "success": False,
                        "message": f"Process exited with code {proc.returncode}: {stderr}",
                        "duration_ms": int((time.monotonic() - start) * 1000),
                    }
                return {
                    "success": True,
                    "message": "Server started and exited cleanly (may be a one-shot server)",
                    "duration_ms": int((time.monotonic() - start) * 1000),
                }
            except subprocess.TimeoutExpired:
                # Still running after 3s = good for a long-running MCP server
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
                return {
                    "success": True,
                    "message": "Server started successfully (still running after 3s)",
                    "duration_ms": int((time.monotonic() - start) * 1000),
                }
        except FileNotFoundError:
            return {
                "success": False,
                "message": f"Command not found: {server.command}",
                "duration_ms": int((time.monotonic() - start) * 1000),
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error: {e}",
                "duration_ms": int((time.monotonic() - start) * 1000),
            }

    def export_config(self, scope: str = "project") -> list[dict]:
        """Export configs for a given scope as JSON-serializable dicts."""
        target = self._target_file(scope)
        return [s.to_dict() for s in self._load_file(target, scope=scope)]

    def import_config(self, configs: list[dict], scope: str = "project") -> int:
        """Import configs from a list of dicts. Returns count imported."""
        target = self._target_file(scope)
        existing = {s.name: s for s in self._load_file(target, scope=scope)}
        count = 0
        for data in configs:
            try:
                config = MCPServerConfig.from_dict(data)
                config.scope = scope
                config.builtin = False
                existing[config.name] = config
                count += 1
            except Exception:
                continue
        self._save_file(target, list(existing.values()))
        return count

    # ── Internal ──────────────────────────────────────────────────

    def _builtin_servers(self) -> list[MCPServerConfig]:
        """Return the default built-in MCP servers."""
        import sys
        return [
            MCPServerConfig(
                name="puppeteer",
                command="npx",
                args=["puppeteer-mcp-server"],
                env={"PUPPETEER_LAUNCH_OPTIONS": '{"protocolTimeout": 300000}'},
                enabled=True,
                description="Browser automation for UI testing",
                builtin=True,
                scope="builtin",
            ),
            MCPServerConfig(
                name="web_search",
                command=sys.executable,
                args=[str(Path(__file__).parent.parent.resolve() / "services" / "web_search_server.py")],
                enabled=True,
                description="Web search via Claude's web search tool",
                builtin=True,
                scope="builtin",
            ),
        ]

    def _target_file(self, scope: str) -> Path:
        if scope == "global":
            return GLOBAL_MCP_FILE
        if self.project_dir:
            return _project_mcp_file(self.project_dir)
        return GLOBAL_MCP_FILE

    def _load_file(self, path: Path, scope: str = "project") -> list[MCPServerConfig]:
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                return []
            configs = []
            for item in data:
                try:
                    c = MCPServerConfig.from_dict(item)
                    c.scope = scope
                    configs.append(c)
                except Exception:
                    continue
            return configs
        except (json.JSONDecodeError, OSError):
            return []

    def _save_file(self, path: Path, servers: list[MCPServerConfig]):
        path.parent.mkdir(parents=True, exist_ok=True)
        # Don't persist builtin servers -- they're always generated at runtime
        to_save = [s for s in servers if not s.builtin]
        data = [s.to_dict() for s in to_save]
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def _set_enabled(self, name: str, enabled: bool) -> Optional[MCPServerConfig]:
        """Toggle enabled state. Searches project first, then global.
        For built-in servers, creates a project-level override.
        """
        # Check project scope first
        if self.project_dir:
            pf = _project_mcp_file(self.project_dir)
            servers = self._load_file(pf, scope="project")
            for s in servers:
                if s.name == name:
                    s.enabled = enabled
                    self._save_file(pf, servers)
                    return s

        # Check global scope
        servers = self._load_file(GLOBAL_MCP_FILE, scope="global")
        for s in servers:
            if s.name == name:
                s.enabled = enabled
                self._save_file(GLOBAL_MCP_FILE, servers)
                return s

        # If it's a builtin server, create a project-level override
        for b in self._builtin_servers():
            if b.name == name:
                override = MCPServerConfig(
                    name=b.name,
                    command=b.command,
                    args=b.args,
                    env=b.env,
                    enabled=enabled,
                    description=b.description,
                    scope="project",
                    builtin=False,
                )
                self.add_server(override, scope="project")
                return override

        return None
