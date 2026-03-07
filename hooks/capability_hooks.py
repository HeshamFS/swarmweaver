"""
Capability Enforcement Hooks
=============================

Generates and deploys per-agent hook configurations that enforce role-based
capability restrictions:

- Scout/Reviewer: Block Write/Edit/NotebookEdit entirely. Bash restricted to
  read-only commands.
- Builder: Allow Write/Edit only within FILE_SCOPE. Block git push.
- Lead: Block source file writes but allow git add/commit for coordination.

These hooks are deployed as .claude/settings.json in each worker's worktree
so Claude Code enforces them automatically.
"""

import json
import re
from pathlib import Path
from typing import Any, Optional

# Tools that modify files
WRITE_TOOLS = ["Write", "Edit", "NotebookEdit"]

# Roles that should NOT have implementation (write) capabilities
NON_IMPLEMENTATION_CAPABILITIES = {"scout", "reviewer", "lead", "coordinator", "monitor", "merger", "orchestrator"}

# Dangerous bash patterns that should be blocked for most roles
DANGEROUS_BASH_PATTERNS = [
    r"sed\s+-i",           # In-place file editing via sed
    r"awk\s+.*-i\s+inplace",  # In-place awk
    r"echo\s+.*>(?!>)",    # Overwrite redirect (but not append)
    r"cat\s+.*>(?!>)",     # Overwrite via cat redirect
    r"tee\s+(?!-a)",       # tee without append
    r"git\s+push",         # Push to remote
    r"git\s+reset\s+--hard",  # Destructive reset
    r"git\s+clean\s+-f",   # Delete untracked files
    r"git\s+checkout\s+--\s+\.",  # Discard all changes
    r"git\s+rebase",       # Rebase (can rewrite history)
    r"git\s+merge",        # Merge (lead coordinates this)
    r"rm\s+-rf?",          # Recursive/force delete
    r"mv\s+",              # Move files
    r"cp\s+",              # Copy files (can overwrite)
    r"chmod\s+",           # Change permissions
    r"pip\s+install",      # Install packages
    r"npm\s+install",      # Install packages
    r"pnpm\s+install",     # Install packages
    r"yarn\s+add",         # Install packages
]

# Read-only bash patterns allowed for scout/reviewer
READ_ONLY_BASH_PATTERNS = [
    r"^ls\b",
    r"^cat\b",
    r"^head\b",
    r"^tail\b",
    r"^wc\b",
    r"^grep\b",
    r"^find\b",
    r"^diff\b",
    r"^git\s+log\b",
    r"^git\s+diff\b",
    r"^git\s+show\b",
    r"^git\s+status\b",
    r"^git\s+branch\b",
    r"^pwd\b",
    r"^echo\b",
    r"^python.*-c\b",      # One-liner Python for inspection
    r"^pytest\b",          # Running tests (reviewer needs this)
    r"^npm\s+test\b",      # Running tests
    r"^node\s+-e\b",       # One-liner Node for inspection
]

# Patterns that builders should never use
BUILDER_BLOCKED_BASH = [
    r"git\s+push",
    r"git\s+merge",
    r"git\s+rebase",
    r"git\s+reset\s+--hard",
    r"git\s+clean\s+-f",
    r"git\s+checkout\s+--\s+\.",
]

# Lead can use these git coordination commands
LEAD_ALLOWED_BASH = [
    r"^git\s+add\b",
    r"^git\s+commit\b",
    r"^git\s+log\b",
    r"^git\s+diff\b",
    r"^git\s+show\b",
    r"^git\s+status\b",
    r"^git\s+branch\b",
]

# Merger can use git merge commands plus read-only and test commands
MERGER_ALLOWED_BASH = [
    r"^git\s+merge\b",
    r"^git\s+commit\b",
    r"^git\s+add\b",
    r"^git\s+log\b",
    r"^git\s+diff\b",
    r"^git\s+show\b",
    r"^git\s+status\b",
    r"^git\s+branch\b",
    r"^git\s+reset\b",       # Needed for reverting failed merges
    r"^pytest\b",
    r"^npm\s+test\b",
    r"^grep\b",
]

# Merger cannot push, install, or rebase
MERGER_BLOCKED_BASH = [
    r"git\s+push",
    r"git\s+rebase",
    r"git\s+clean\s+-f",
    r"pip\s+install",
    r"npm\s+install",
]


def _is_read_only_command(command: str) -> bool:
    """Check if a bash command is read-only (safe for scout/reviewer)."""
    command = command.strip()
    # Handle compound commands — each segment must be read-only
    segments = re.split(r'\s*(?:&&|\|\||\|)\s*', command)
    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue
        if not any(re.match(pat, segment) for pat in READ_ONLY_BASH_PATTERNS):
            return False
    return True


def _is_within_file_scope(file_path: str, file_scope: list[str]) -> bool:
    """Check if a file path falls within the allowed file scope."""
    if not file_scope:
        return True  # No scope restriction

    file_path_obj = Path(file_path)

    for scope_pattern in file_scope:
        scope_path = Path(scope_pattern)
        # Exact match
        if str(file_path_obj) == str(scope_path):
            return True
        # Glob-style: scope pattern ends with /*
        if scope_pattern.endswith("/*") or scope_pattern.endswith("/**"):
            scope_dir = Path(scope_pattern.rstrip("/*"))
            try:
                file_path_obj.relative_to(scope_dir)
                return True
            except ValueError:
                continue
        # Directory containment
        try:
            file_path_obj.relative_to(scope_path)
            return True
        except ValueError:
            continue

    return False


def _has_dangerous_bash(command: str, blocked_patterns: list[str]) -> Optional[str]:
    """Check if a command matches any blocked pattern. Returns the matched pattern or None."""
    for pattern in blocked_patterns:
        if re.search(pattern, command):
            return pattern
    return None


def generate_hooks_config(capability: str, file_scope: list[str]) -> dict:
    """
    Generate .claude/settings.json content for an agent based on its capability.

    The settings configure Claude Code's built-in permission system to enforce
    role-based access control.

    Args:
        capability: Agent role/capability (scout, builder, reviewer, lead)
        file_scope: List of file paths/glob patterns the agent may modify

    Returns:
        Dict suitable for writing as .claude/settings.json
    """
    capability = capability.lower()

    # Base config all agents share
    config: dict[str, Any] = {
        "_comment": f"Auto-generated capability hooks for {capability} agent",
        "capability": capability,
        "file_scope": file_scope,
    }

    if capability in ("scout", "reviewer"):
        # Read-only agents: block all write tools entirely
        config["blocked_tools"] = WRITE_TOOLS.copy()
        config["bash_mode"] = "read_only"
        config["bash_allowed_patterns"] = READ_ONLY_BASH_PATTERNS.copy()
        config["bash_blocked_patterns"] = DANGEROUS_BASH_PATTERNS.copy()

    elif capability == "builder":
        # Implementation agent: allow writes within scope, block dangerous git ops
        config["blocked_tools"] = []  # Write/Edit allowed (scope-checked at runtime)
        config["bash_mode"] = "scoped"
        config["bash_blocked_patterns"] = BUILDER_BLOCKED_BASH.copy()
        config["file_scope_enforced"] = True

    elif capability == "merger":
        # Merge specialist: block source writes, allow git merge commands
        config["blocked_tools"] = WRITE_TOOLS.copy()
        config["bash_mode"] = "merge"
        config["bash_allowed_patterns"] = MERGER_ALLOWED_BASH.copy()
        config["bash_blocked_patterns"] = MERGER_BLOCKED_BASH.copy()
        # Merger can write to .swarm/ directory only
        config["writable_files"] = [
            ".swarm/merge_report.json",
            ".swarm/*",
        ]

    elif capability == "orchestrator":
        # Smart orchestrator: read-only, coordination via custom MCP tools
        config["blocked_tools"] = WRITE_TOOLS.copy()
        config["bash_mode"] = "read_only"
        config["bash_allowed_patterns"] = READ_ONLY_BASH_PATTERNS.copy()
        config["bash_blocked_patterns"] = DANGEROUS_BASH_PATTERNS.copy()
        config["writable_files"] = [
            "task_list.json",
            "swarm_plan.json",
            "steering_input.json",
            "orchestrator_state.json",
        ]

    elif capability == "lead":
        # Coordinator: block source writes, allow git coordination
        config["blocked_tools"] = WRITE_TOOLS.copy()
        config["bash_mode"] = "coordination"
        config["bash_allowed_patterns"] = LEAD_ALLOWED_BASH.copy()
        config["bash_blocked_patterns"] = [
            r"git\s+push",
            r"git\s+reset\s+--hard",
            r"git\s+clean\s+-f",
            r"git\s+rebase",
        ]
        # Lead can write to coordination files only
        config["writable_files"] = [
            "task_list.json",
            "swarm_plan.json",
            "escalations.json",
        ]

    else:
        # Unknown capability — default to read-only for safety
        config["blocked_tools"] = WRITE_TOOLS.copy()
        config["bash_mode"] = "read_only"
        config["bash_allowed_patterns"] = READ_ONLY_BASH_PATTERNS.copy()
        config["bash_blocked_patterns"] = DANGEROUS_BASH_PATTERNS.copy()

    return config


def deploy_hooks_to_worktree(
    worktree_path: Path,
    capability: str,
    file_scope: list[str],
) -> Path:
    """
    Write hooks config to a worker's worktree.

    Creates .claude/settings.json in the worktree directory with the
    appropriate capability restrictions for the agent's role.

    Args:
        worktree_path: Path to the worker's worktree directory
        capability: Agent role (scout, builder, reviewer, lead)
        file_scope: Files/patterns the agent may modify

    Returns:
        Path to the written settings file
    """
    config = generate_hooks_config(capability, file_scope)

    settings_dir = worktree_path / ".claude"
    settings_dir.mkdir(parents=True, exist_ok=True)

    settings_path = settings_dir / "settings.json"
    settings_path.write_text(
        json.dumps(config, indent=2) + "\n",
        encoding="utf-8",
    )

    return settings_path


# --- PreToolUse Hook for Runtime Enforcement ---

# Runtime state (set by deploy function or externally)
_active_capability: Optional[str] = None
_active_file_scope: list[str] = []


def set_active_capability(capability: str, file_scope: list[str]) -> None:
    """Configure the active capability for runtime hook enforcement."""
    global _active_capability, _active_file_scope
    _active_capability = capability.lower()
    _active_file_scope = file_scope


async def capability_enforcement_hook(
    input_data: dict[str, Any],
    tool_use_id: Optional[str] = None,
    context: Any = None,
) -> dict[str, Any]:
    """
    PreToolUse hook that enforces capability restrictions at runtime.

    This hook is registered in the agent's hook chain and checks every tool
    call against the agent's assigned capability.

    Returns:
        Empty dict to allow, or {"decision": "block", "reason": "..."} to block
    """
    if _active_capability is None:
        return {}  # No capability set — allow everything (backward compat)

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    # --- Block write tools for non-implementation roles ---
    if _active_capability in NON_IMPLEMENTATION_CAPABILITIES:
        if tool_name in WRITE_TOOLS:
            # Special case: lead can write to coordination files
            if _active_capability == "lead":
                file_path = tool_input.get("file_path", "")
                filename = Path(file_path).name if file_path else ""
                coordination_files = {
                    "task_list.json", "swarm_plan.json", "escalations.json",
                }
                if filename in coordination_files:
                    return {}  # Allow

            # Special case: scout can write to findings/spec files
            if _active_capability == "scout":
                file_path = tool_input.get("file_path", "")
                filename = Path(file_path).name if file_path else ""
                if (
                    filename == "scout_findings.json"
                    or filename == "codebase_profile.json"
                    or filename.startswith("spec_")
                ):
                    return {}  # Allow

            # Special case: reviewer can write to review files
            if _active_capability == "reviewer":
                file_path = tool_input.get("file_path", "")
                filename = Path(file_path).name if file_path else ""
                if (
                    filename == "review_report.json"
                    or filename.startswith("review_")
                ):
                    return {}  # Allow

            # Special case: merger can write to .swarm/ directory
            if _active_capability == "merger":
                file_path = tool_input.get("file_path", "")
                if file_path and "/.swarm/" in file_path or file_path.endswith("/.swarm"):
                    return {}  # Allow

            # Special case: orchestrator can write to coordination/task files only
            if _active_capability == "orchestrator":
                file_path = tool_input.get("file_path", "")
                filename = Path(file_path).name if file_path else ""
                orchestrator_writable = {
                    "task_list.json", "swarm_plan.json", "steering_input.json",
                    "claude-progress.txt", "orchestrator_state.json",
                }
                if filename in orchestrator_writable or ".swarmweaver/" in file_path:
                    return {}  # Allow

            return {
                "decision": "block",
                "reason": (
                    f"[CAPABILITY] {_active_capability} agents cannot use {tool_name}. "
                    f"Only implementation agents (builder) may modify files."
                ),
            }

    # --- Enforce file scope for builders ---
    if _active_capability == "builder" and tool_name in WRITE_TOOLS:
        file_path = tool_input.get("file_path", "")
        if file_path and _active_file_scope:
            if not _is_within_file_scope(file_path, _active_file_scope):
                return {
                    "decision": "block",
                    "reason": (
                        f"[CAPABILITY] File '{file_path}' is outside your assigned scope. "
                        f"Allowed scope: {_active_file_scope}"
                    ),
                }

    # --- Bash command restrictions ---
    if tool_name == "Bash":
        command = tool_input.get("command", "")
        if not command:
            return {}

        if _active_capability in ("scout", "reviewer"):
            if not _is_read_only_command(command):
                return {
                    "decision": "block",
                    "reason": (
                        f"[CAPABILITY] {_active_capability} agents may only run "
                        f"read-only bash commands. Blocked: {command[:100]}"
                    ),
                }

        elif _active_capability == "builder":
            matched = _has_dangerous_bash(command, BUILDER_BLOCKED_BASH)
            if matched:
                return {
                    "decision": "block",
                    "reason": (
                        f"[CAPABILITY] Builder agents cannot run '{matched}'. "
                        f"Coordinate with the Lead for push/merge/rebase operations."
                    ),
                }

        elif _active_capability == "merger":
            # Merger can run git merge commands, tests, and read-only commands
            is_merge_cmd = any(
                re.match(pat, command.strip()) for pat in MERGER_ALLOWED_BASH
            )
            is_read_only = _is_read_only_command(command)

            if not is_merge_cmd and not is_read_only:
                return {
                    "decision": "block",
                    "reason": (
                        f"[CAPABILITY] Merger agents may only run git merge/diff "
                        f"commands, tests, and read-only commands. Blocked: {command[:100]}"
                    ),
                }

            # Block dangerous patterns even for allowed commands
            blocked = _has_dangerous_bash(command, MERGER_BLOCKED_BASH)
            if blocked:
                return {
                    "decision": "block",
                    "reason": (
                        f"[CAPABILITY] Merger agents cannot run '{blocked}'. "
                        f"This operation is not permitted for merge agents."
                    ),
                }

        elif _active_capability == "orchestrator":
            # Orchestrator can only run read-only and git status commands
            is_read_only = _is_read_only_command(command)
            if not is_read_only:
                return {
                    "decision": "block",
                    "reason": (
                        f"[CAPABILITY] Orchestrator agents may only run "
                        f"read-only bash commands. Blocked: {command[:100]}"
                    ),
                }

        elif _active_capability == "lead":
            # Lead can only run git coordination commands and read-only commands
            is_git_coord = any(
                re.match(pat, command.strip()) for pat in LEAD_ALLOWED_BASH
            )
            is_read_only = _is_read_only_command(command)

            if not is_git_coord and not is_read_only:
                return {
                    "decision": "block",
                    "reason": (
                        f"[CAPABILITY] Lead agents may only run git coordination "
                        f"commands and read-only commands. Blocked: {command[:100]}"
                    ),
                }

            # Even for allowed git commands, block dangerous patterns
            blocked = _has_dangerous_bash(command, [
                r"git\s+push",
                r"git\s+reset\s+--hard",
                r"git\s+clean\s+-f",
                r"git\s+rebase",
            ])
            if blocked:
                return {
                    "decision": "block",
                    "reason": (
                        f"[CAPABILITY] Lead agents cannot run '{blocked}'. "
                        f"This operation requires operator approval."
                    ),
                }

    return {}


# Export
__all__ = [
    "WRITE_TOOLS",
    "NON_IMPLEMENTATION_CAPABILITIES",
    "DANGEROUS_BASH_PATTERNS",
    "generate_hooks_config",
    "deploy_hooks_to_worktree",
    "set_active_capability",
    "capability_enforcement_hook",
]
