"""Config file support for SwarmWeaver CLI.

Loads defaults from ~/.swarmweaver/config.toml (if it exists).
CLI arguments always override config file values.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from core.models import DEFAULT_MODEL


CONFIG_DIR = Path.home() / ".swarmweaver"
CONFIG_FILE = CONFIG_DIR / "config.toml"


@dataclass
class CLIConfig:
    """Resolved CLI configuration (config file + env + defaults)."""
    default_model: str = DEFAULT_MODEL
    default_budget: float = 0.0
    default_server_url: str = ""
    default_max_hours: float = 0.0


def load_config() -> CLIConfig:
    """Load config from ~/.swarmweaver/config.toml if it exists.

    Falls back to defaults if the file is missing or unparseable.
    Uses tomllib (Python 3.11+) or tomli as fallback.
    """
    cfg = CLIConfig()

    if not CONFIG_FILE.exists():
        return cfg

    try:
        raw = CONFIG_FILE.read_text(encoding="utf-8")
    except OSError:
        return cfg

    data = _parse_toml(raw)
    if not data:
        return cfg

    cli_section = data.get("cli", {})
    cfg.default_model = str(cli_section.get("default_model", cfg.default_model))
    cfg.default_budget = float(cli_section.get("default_budget", cfg.default_budget))
    cfg.default_server_url = str(cli_section.get("default_server_url", cfg.default_server_url))
    cfg.default_max_hours = float(cli_section.get("default_max_hours", cfg.default_max_hours))

    return cfg


def _parse_toml(raw: str) -> Optional[dict]:
    """Parse TOML string, trying stdlib then fallback."""
    # Python 3.11+ has tomllib in stdlib
    try:
        import tomllib
        return tomllib.loads(raw)
    except ImportError:
        pass

    # Try tomli (pip install tomli)
    try:
        import tomli
        return tomli.loads(raw)
    except ImportError:
        pass

    # Minimal fallback: parse key=value lines under [cli] section
    return _minimal_toml_parse(raw)


def _minimal_toml_parse(raw: str) -> dict:
    """Ultra-minimal TOML parser for flat [cli] section only."""
    result: dict = {}
    current_section = ""
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current_section = line[1:-1].strip()
            result.setdefault(current_section, {})
            continue
        if "=" in line and current_section:
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            # Try to coerce types
            if val.lower() in ("true", "false"):
                result[current_section][key] = val.lower() == "true"
            else:
                try:
                    result[current_section][key] = float(val) if "." in val else int(val)
                except ValueError:
                    result[current_section][key] = val
    return result


def write_default_config() -> Path:
    """Create a default config.toml if none exists. Returns the path."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(
            '# SwarmWeaver CLI configuration\n'
            '# This file is loaded before CLI arguments.\n'
            '# CLI flags always override these values.\n'
            '\n'
            '[cli]\n'
            f'# default_model = "{DEFAULT_MODEL}"\n'
            '# default_budget = 0.0\n'
            '# default_server_url = ""\n'
            '# default_max_hours = 0.0\n',
            encoding="utf-8",
        )
    return CONFIG_FILE
