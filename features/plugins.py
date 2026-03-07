"""
Plugin & Extension System
==========================

Loads custom hooks, tools, and prompt fragments from YAML config files.
Inspired by Claude Code's agent skills pattern.

Looks for config at:
1. ~/.swarmweaver/plugins.yaml (global)
2. {project_dir}/.swarmweaver/plugins.yaml (project-level)

Plugin types:
- hook: Python file with async hook function(s)
- prompt_fragment: Markdown file injected into prompts
- tool_config: MCP server configuration
"""

import importlib.util
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Optional


GLOBAL_CONFIG_PATH = Path.home() / ".swarmweaver" / "plugins.yaml"


@dataclass
class PluginDefinition:
    """Definition of a single plugin."""
    name: str
    description: str
    type: str                    # "hook" | "prompt_fragment" | "tool_config"
    source: str                  # file path or "inline"
    trigger: str = ""            # for hooks: "pre_tool" | "post_tool" | "stop"
    modes: list[str] = field(default_factory=list)  # empty = all modes
    enabled: bool = True
    config: dict = field(default_factory=dict)  # for tool_config type


class PluginLoader:
    """Loads and manages plugins from YAML configuration."""

    def __init__(self, config_path: Optional[Path] = None, project_dir: Optional[Path] = None):
        self.config_path = config_path
        self.project_dir = Path(project_dir) if project_dir else None
        self._plugins: list[PluginDefinition] = []

    def load_config(self) -> list[PluginDefinition]:
        """Load plugin definitions from config file(s)."""
        self._plugins = []

        # Load from multiple sources
        paths_to_try = []

        # Explicit config path
        if self.config_path:
            paths_to_try.append(self.config_path)

        # Global config
        if GLOBAL_CONFIG_PATH.exists():
            paths_to_try.append(GLOBAL_CONFIG_PATH)

        # Project-level config
        if self.project_dir:
            project_config = self.project_dir / ".swarmweaver" / "plugins.yaml"
            if project_config.exists():
                paths_to_try.append(project_config)

        for path in paths_to_try:
            self._load_from_file(path)

        return self._plugins

    def _load_from_file(self, path: Path) -> None:
        """Load plugins from a single YAML config file."""
        if not path.exists():
            return

        try:
            # Use simple YAML-like parsing (avoid pyyaml dependency)
            content = path.read_text(encoding="utf-8")
            plugins_data = _parse_simple_yaml(content)

            for pdata in plugins_data:
                plugin = PluginDefinition(
                    name=pdata.get("name", "unnamed"),
                    description=pdata.get("description", ""),
                    type=pdata.get("type", "prompt_fragment"),
                    source=pdata.get("source", ""),
                    trigger=pdata.get("trigger", ""),
                    modes=pdata.get("modes", []),
                    enabled=pdata.get("enabled", True),
                    config=pdata.get("config", {}),
                )
                # Avoid duplicates
                if not any(p.name == plugin.name for p in self._plugins):
                    self._plugins.append(plugin)
        except (OSError, ValueError):
            pass

    def get_hooks(self) -> list[tuple[str, Callable]]:
        """Load hook functions from hook-type plugins.

        Returns list of (trigger, hook_function) tuples.
        """
        hooks: list[tuple[str, Callable]] = []

        for plugin in self._plugins:
            if plugin.type != "hook" or not plugin.enabled:
                continue

            source_path = Path(plugin.source).expanduser()
            if not source_path.exists():
                continue

            try:
                # Dynamically load the Python module
                spec = importlib.util.spec_from_file_location(
                    f"plugin_{plugin.name}", str(source_path)
                )
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)

                    # Look for hook function (convention: async def hook(...))
                    hook_fn = getattr(module, "hook", None)
                    if hook_fn and callable(hook_fn):
                        hooks.append((plugin.trigger or "pre_tool", hook_fn))
            except Exception:
                continue

        return hooks

    def get_prompt_fragments(self, mode: str = "", phase: str = "") -> list[str]:
        """Get prompt fragments from prompt_fragment-type plugins.

        Args:
            mode: Current mode (empty = match all)
            phase: Current phase (unused for now)

        Returns list of markdown strings to inject into prompts.
        """
        fragments: list[str] = []

        for plugin in self._plugins:
            if plugin.type != "prompt_fragment" or not plugin.enabled:
                continue

            # Check mode filter
            if plugin.modes and mode and mode not in plugin.modes:
                continue

            source_path = Path(plugin.source).expanduser()
            if source_path.exists():
                try:
                    content = source_path.read_text(encoding="utf-8")
                    fragments.append(content)
                except OSError:
                    continue

        return fragments

    def get_tool_configs(self) -> list[dict]:
        """Get MCP server configs from tool_config-type plugins.

        Returns list of dicts with 'command' and 'args' keys.
        """
        configs: list[dict] = []

        for plugin in self._plugins:
            if plugin.type != "tool_config" or not plugin.enabled:
                continue

            if plugin.config:
                configs.append(plugin.config)

        return configs

    def toggle_plugin(self, name: str) -> bool:
        """Toggle a plugin on/off. Returns new enabled state."""
        for plugin in self._plugins:
            if plugin.name == name:
                plugin.enabled = not plugin.enabled
                self._save_state()
                return plugin.enabled
        return False

    def _save_state(self) -> None:
        """Save plugin enabled states to a state file."""
        state_file = Path.home() / ".swarmweaver" / "plugin_state.json"
        try:
            state_file.parent.mkdir(parents=True, exist_ok=True)
            state = {p.name: p.enabled for p in self._plugins}
            state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
        except OSError:
            pass


def _parse_simple_yaml(content: str) -> list[dict]:
    """Simple YAML-like parser for plugin configs.

    Supports the plugin config format without requiring pyyaml.
    Falls back to trying JSON if YAML parsing fails.
    """
    # Try JSON first (some users may prefer JSON)
    try:
        data = json.loads(content)
        if isinstance(data, dict) and "plugins" in data:
            return data["plugins"]
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass

    # Try importing yaml
    try:
        import yaml
        data = yaml.safe_load(content)
        if isinstance(data, dict) and "plugins" in data:
            return data["plugins"]
        if isinstance(data, list):
            return data
    except ImportError:
        pass
    except Exception:
        pass

    return []
