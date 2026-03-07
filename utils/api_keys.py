"""
API Key Management for Autonomous Coding Agent
===============================================

Handles detection, prompting, and storage of API keys required by projects.
Supports interactive collection from users and persistent storage in .env files.
"""

import os
import re
from pathlib import Path
from typing import Optional


# Known API keys and their purposes
KNOWN_API_KEYS = {
    "GEMINI_API_KEY": {
        "description": "Google Gemini API for AI classification agents",
        "env_var": "GEMINI_API_KEY",
        "alt_env_vars": ["GOOGLE_API_KEY"],
        "url": "https://aistudio.google.com/app/apikey",
        "required_for": ["AI classification", "multi-agent workflows", "document generation"],
    },
    "OPENAI_API_KEY": {
        "description": "OpenAI API for GPT models",
        "env_var": "OPENAI_API_KEY",
        "alt_env_vars": [],
        "url": "https://platform.openai.com/api-keys",
        "required_for": ["GPT-based features", "embeddings"],
    },
    "ANTHROPIC_API_KEY": {
        "description": "Anthropic API for Claude models",
        "env_var": "ANTHROPIC_API_KEY",
        "alt_env_vars": [],
        "url": "https://console.anthropic.com/",
        "required_for": ["Claude-based features"],
    },
}


def get_env_file_path(project_dir: Path) -> Path:
    """Get the path to the project's .env file."""
    return project_dir / ".env"


def get_backend_env_path(project_dir: Path) -> Path:
    """Get the path to the backend's .env file (if separate)."""
    return project_dir / "backend" / ".env"


def load_env_file(env_path: Path) -> dict[str, str]:
    """Load environment variables from a .env file."""
    env_vars = {}
    if not env_path.exists():
        return env_vars

    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                env_vars[key] = value

    return env_vars


def save_env_file(env_path: Path, env_vars: dict[str, str]) -> None:
    """Save environment variables to a .env file, preserving comments."""
    existing_lines = []
    existing_keys = set()

    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                if "=" in line and not line.strip().startswith("#"):
                    key = line.split("=")[0].strip()
                    if key in env_vars:
                        # Update existing key
                        existing_lines.append(f"{key}={env_vars[key]}\n")
                        existing_keys.add(key)
                    else:
                        existing_lines.append(line)
                else:
                    existing_lines.append(line)

    # Add new keys
    for key, value in env_vars.items():
        if key not in existing_keys:
            existing_lines.append(f"{key}={value}\n")

    with open(env_path, "w") as f:
        f.writelines(existing_lines)


def check_api_key_available(key_name: str, project_dir: Path) -> tuple[bool, Optional[str]]:
    """
    Check if an API key is available in environment or .env files.

    Returns:
        Tuple of (is_available, value_if_found)
    """
    # Check environment first
    if key_name in os.environ and os.environ[key_name]:
        return True, os.environ[key_name]

    # Check alternative env var names
    if key_name in KNOWN_API_KEYS:
        for alt_var in KNOWN_API_KEYS[key_name].get("alt_env_vars", []):
            if alt_var in os.environ and os.environ[alt_var]:
                return True, os.environ[alt_var]

    # Check project .env files
    for env_path in [get_env_file_path(project_dir), get_backend_env_path(project_dir)]:
        env_vars = load_env_file(env_path)
        if key_name in env_vars and env_vars[key_name]:
            # Check it's not a placeholder
            value = env_vars[key_name]
            if not is_placeholder_value(value):
                return True, value

        # Check alternatives
        if key_name in KNOWN_API_KEYS:
            for alt_var in KNOWN_API_KEYS[key_name].get("alt_env_vars", []):
                if alt_var in env_vars and env_vars[alt_var]:
                    value = env_vars[alt_var]
                    if not is_placeholder_value(value):
                        return True, value

    return False, None


def is_placeholder_value(value: str) -> bool:
    """Check if a value is a placeholder rather than a real API key."""
    placeholders = [
        "your_api_key_here",
        "your-api-key-here",
        "YOUR_API_KEY",
        "xxx",
        "placeholder",
        "changeme",
        "your_key",
        "api_key_here",
        "insert_key_here",
        "",
    ]
    value_lower = value.lower().strip()
    return value_lower in [p.lower() for p in placeholders] or len(value) < 10


def detect_required_api_keys(project_dir: Path) -> list[str]:
    """
    Scan project files to detect which API keys are required.
    Uses a fast targeted approach - only checks key directories and files.

    Returns:
        List of required API key names
    """
    required_keys = set()

    # Patterns that indicate API key usage
    patterns = {
        "GEMINI_API_KEY": [
            r"gemini",
            r"google\.generativeai",
            r"genai\.",
            r"GEMINI_API_KEY",
            r"google-genai",
        ],
        "OPENAI_API_KEY": [
            r"openai",
            r"OPENAI_API_KEY",
            r"gpt-[34]",
            r"ChatCompletion",
        ],
        "ANTHROPIC_API_KEY": [
            r"anthropic",
            r"ANTHROPIC_API_KEY",
            r"claude-",
        ],
    }

    # FAST APPROACH: Only check specific directories that typically contain API usage
    key_dirs = [
        project_dir / "backend" / "app",
        project_dir / "backend" / "app" / "agents",
        project_dir / "backend" / "app" / "routers",
        project_dir / "frontend" / "lib",
        project_dir / "frontend" / "app" / "api",
        project_dir / "src",
        project_dir / "lib",
        project_dir / "app",
    ]

    # Also check root config files
    config_files = [
        project_dir / "requirements.txt",
        project_dir / "package.json",
        project_dir / "backend" / "requirements.txt",
        project_dir / "frontend" / "package.json",
    ]

    # Check config files first (very fast)
    for config_file in config_files:
        if config_file.exists():
            try:
                content = config_file.read_text(errors="ignore")
                for key_name, key_patterns in patterns.items():
                    for pattern in key_patterns:
                        if re.search(pattern, content, re.IGNORECASE):
                            required_keys.add(key_name)
                            break
            except Exception:
                continue

    # Check key directories (limited depth)
    for key_dir in key_dirs:
        if not key_dir.exists():
            continue

        # Only check .py, .ts, .tsx files in this directory (not recursive)
        for ext in ["*.py", "*.ts", "*.tsx"]:
            for file_path in key_dir.glob(ext):
                try:
                    content = file_path.read_text(errors="ignore")
                    for key_name, key_patterns in patterns.items():
                        for pattern in key_patterns:
                            if re.search(pattern, content, re.IGNORECASE):
                                required_keys.add(key_name)
                                break
                except Exception:
                    continue

    return list(required_keys)


def get_missing_api_keys(project_dir: Path) -> list[dict]:
    """
    Get list of required API keys that are missing.

    Returns:
        List of dicts with key info: {name, description, url, required_for}
    """
    required = detect_required_api_keys(project_dir)
    missing = []

    for key_name in required:
        is_available, _ = check_api_key_available(key_name, project_dir)
        if not is_available:
            key_info = KNOWN_API_KEYS.get(key_name, {})
            missing.append({
                "name": key_name,
                "description": key_info.get("description", f"API key: {key_name}"),
                "url": key_info.get("url", ""),
                "required_for": key_info.get("required_for", []),
            })

    return missing


def prompt_for_api_key(key_info: dict) -> Optional[str]:
    """
    Prompt the user interactively for an API key.

    Args:
        key_info: Dict with name, description, url

    Returns:
        The API key value, or None if skipped
    """
    print("\n" + "=" * 60)
    print(f"API Key Required: {key_info['name']}")
    print("=" * 60)
    print(f"Description: {key_info['description']}")

    if key_info.get("required_for"):
        print(f"Required for: {', '.join(key_info['required_for'])}")

    if key_info.get("url"):
        print(f"Get key at: {key_info['url']}")

    print("\nOptions:")
    print("  1. Enter the API key now")
    print("  2. Skip (some features will be unavailable)")
    print()

    while True:
        choice = input("Enter choice (1/2) or paste API key directly: ").strip()

        if choice == "2":
            print(f"Skipped {key_info['name']} - some features will be unavailable")
            return None

        if choice == "1":
            key_value = input(f"Enter {key_info['name']}: ").strip()
        else:
            # User pasted the key directly
            key_value = choice

        if key_value and not is_placeholder_value(key_value):
            return key_value

        print("Invalid key. Please enter a valid API key or choose to skip.")


def collect_missing_api_keys(project_dir: Path, interactive: bool = True) -> dict[str, str]:
    """
    Collect all missing API keys from the user.

    Args:
        project_dir: Project directory
        interactive: If True, prompt user interactively

    Returns:
        Dict of collected keys {key_name: key_value}
    """
    print("Scanning project for required API keys...")
    missing = get_missing_api_keys(project_dir)

    if not missing:
        print("No missing API keys detected - all required keys are configured!")
        return {}

    if not interactive:
        print(f"\nMissing API keys detected: {[k['name'] for k in missing]}")
        print("Run with --interactive or add keys to .env file")
        return {}

    print("\n" + "=" * 60)
    print("API KEYS REQUIRED")
    print("=" * 60)
    print(f"This project requires {len(missing)} API key(s) for full functionality.")
    print("You can provide them now or skip to continue with limited features.\n")

    collected = {}
    for key_info in missing:
        key_value = prompt_for_api_key(key_info)
        if key_value:
            collected[key_info["name"]] = key_value

    # Save collected keys to .env
    if collected:
        env_path = get_backend_env_path(project_dir)
        if not env_path.parent.exists():
            env_path = get_env_file_path(project_dir)

        save_env_file(env_path, collected)
        print(f"\nSaved {len(collected)} API key(s) to {env_path}")

        # Also set in environment for current session
        for key, value in collected.items():
            os.environ[key] = value

    return collected


def check_and_prompt_api_keys(project_dir: Path, at_session_end: bool = False) -> None:
    """
    Check for missing API keys and prompt user if needed.

    Args:
        project_dir: Project directory
        at_session_end: If True, this is called at end of session (less urgent prompt)
    """
    missing = get_missing_api_keys(project_dir)

    if not missing:
        return

    if at_session_end:
        print("\n" + "-" * 60)
        print("NOTE: Some tests require API keys that are not configured:")
        for key_info in missing:
            print(f"  - {key_info['name']}: {key_info['description']}")
            if key_info.get("url"):
                print(f"    Get key at: {key_info['url']}")
        print("\nTo configure, add to your project's .env file or provide interactively")
        print("on next run with: --collect-api-keys")
        print("-" * 60)
    else:
        # Interactive collection
        collect_missing_api_keys(project_dir, interactive=True)
