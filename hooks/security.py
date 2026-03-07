"""
Security Hooks for Autonomous Coding Agent
==========================================

Pre-tool-use hooks that validate bash commands for security.
Uses an allowlist approach - only explicitly permitted commands can run.
"""

import os
import shlex


# Allowed commands for development tasks
# Expanded set for autonomous coding with full development capabilities
# NOTE: The agent also runs inside an OS-level sandbox with filesystem restrictions,
# so this allowlist is defense-in-depth, not the only security boundary.
ALLOWED_COMMANDS = {
    # File inspection (read-only)
    "ls",
    "cat",
    "head",
    "tail",
    "wc",
    "grep",
    "find",
    "diff",
    "stat",
    "file",
    "xxd",  # Hex dump for debugging encoding/line-ending issues
    "readlink",
    "realpath",
    "dirname",
    "basename",
    # File operations (agent uses SDK tools for most file ops, but these needed occasionally)
    "cp",
    "mv",
    "mkdir",
    "touch",
    "rm",  # Validated separately — blocks catastrophic patterns
    "chmod",  # For making scripts executable; validated separately
    "ln",  # Symlinks (needed for node_modules workarounds)
    # Text processing (commonly used in pipelines)
    "sort",
    "uniq",
    "tr",
    "sed",
    "awk",
    "cut",
    "paste",
    "tee",
    "xargs",
    "yes",  # Needed for piping to interactive prompts (e.g., npm init)
    # Directory navigation
    "pwd",
    "cd",  # Shell builtin, but included for completeness
    # Python development
    "python",
    "python3",
    "pip",
    "pip3",
    "uvicorn",
    "pytest",
    "alembic",
    # Virtual environment
    "source",  # Shell builtin for activating venv
    "activate",
    # Node.js development
    "npm",
    "npx",
    "node",
    "pnpm",
    "yarn",
    "next",
    "vite",
    "tsc",  # TypeScript compiler (npx tsc or ./node_modules/.bin/tsc)
    # Version control
    "git",
    # Process management
    "ps",
    "lsof",
    "sleep",
    "pkill",  # For killing dev servers; validated separately
    "kill",
    # System info (read-only)
    "date",
    "hostname",
    "whoami",
    "uname",
    "id",
    "df",
    "du",
    "free",
    # Network inspection (read-only, needed for checking dev servers)
    "ss",
    "netstat",
    "nslookup",
    # Shell utilities
    "echo",
    "printf",
    "export",
    "env",
    "which",
    "type",
    "exec",
    "test",
    "[",  # test command alias
    "true",
    "false",
    # Shell control flow (for loops, conditionals)
    "for",
    "while",
    "do",
    "done",
    "if",
    "then",
    "else",
    "fi",
    "case",
    "esac",
    "in",
    # Archive handling
    "tar",
    "zip",
    "unzip",
    "gzip",
    "gunzip",
    # HTTP utilities (for testing APIs)
    "curl",
    "wget",
    # Script execution
    "sh",
    "bash",
    "init.sh",  # Init scripts; validated separately
    # Helper scripts (validated separately)
    "start-backend.sh",
    "start-frontend.sh",
    "run_test.sh",
    "setup-frontend.sh",
}

# Commands that need additional validation even when in the allowlist
COMMANDS_NEEDING_EXTRA_VALIDATION = {
    "pkill",
    "chmod",
    "rm",
    "git",
    "init.sh",
    "start-backend.sh",
    "start-frontend.sh",
    "run_test.sh",
    "setup-frontend.sh",
}

# Paths that must not be committed (require .gitignore protection for git add . / git add -A)
_GITADD_DANGEROUS_PATHS = ("node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next", ".cache")

# Helper scripts that are allowed to be executed
ALLOWED_HELPER_SCRIPTS = {
    "init.sh",
    "start-backend.sh",
    "start-frontend.sh",
    "run_test.sh",
    "setup-frontend.sh",
}


def split_command_segments(command_string: str) -> list[str]:
    """
    Split a compound command into individual command segments.

    Handles command chaining (&&, ||, ;) but not pipes (those are single commands).

    Args:
        command_string: The full shell command

    Returns:
        List of individual command segments
    """
    import re

    # Split on && and || while preserving the ability to handle each segment
    # This regex splits on && or || that aren't inside quotes
    segments = re.split(r"\s*(?:&&|\|\|)\s*", command_string)

    # Further split on semicolons
    result = []
    for segment in segments:
        sub_segments = re.split(r'(?<!["\'])\s*;\s*(?!["\'])', segment)
        for sub in sub_segments:
            sub = sub.strip()
            if sub:
                result.append(sub)

    return result


def _split_on_pipes(command: str) -> list[str]:
    """
    Split a command on pipe characters (|) while respecting quotes.
    Returns the individual pipe stages.
    """
    parts = []
    current = []
    in_single = False
    in_double = False
    escape = False
    i = 0

    while i < len(command):
        ch = command[i]

        if escape:
            current.append(ch)
            escape = False
            i += 1
            continue

        if ch == "\\":
            escape = True
            current.append(ch)
            i += 1
            continue

        if ch == "'" and not in_double:
            in_single = not in_single
            current.append(ch)
        elif ch == '"' and not in_single:
            in_double = not in_double
            current.append(ch)
        elif ch == "|" and not in_single and not in_double:
            # Check it's not || (logical OR)
            if i + 1 < len(command) and command[i + 1] == "|":
                current.append("||")
                i += 2
                continue
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)

        i += 1

    remaining = "".join(current).strip()
    if remaining:
        parts.append(remaining)

    return parts


def _strip_inline_comments(command: str) -> str:
    """Remove inline comments (# ...) while respecting quotes."""
    in_single = False
    in_double = False
    escaped = False
    for i, ch in enumerate(command):
        if escaped:
            escaped = False
            continue
        if ch == '\\':
            escaped = True
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == '#' and not in_single and not in_double:
            if i == 0 or command[i - 1] in (' ', '\t'):
                return command[:i].rstrip()
    return command


def extract_commands(command_string: str) -> list[str]:
    """
    Extract command names from a shell command string.

    Handles pipes, command chaining (&&, ||, ;), and subshells.
    Returns the base command names (without paths).

    Args:
        command_string: The full shell command

    Returns:
        List of command names found in the string
    """
    commands = []

    import re

    # Strip output redirections (2>&1) so they don't confuse parsing
    processed = re.sub(r'\d*>&\d+', '', command_string)

    # Strip inline comments: everything after unquoted # is a comment
    processed = _strip_inline_comments(processed)

    # Split on && and || first (command chaining)
    chain_segments = re.split(r'\s*(?:&&|\|\|)\s*', processed)
    
    # Process each chain segment
    segments = []
    for seg in chain_segments:
        seg = seg.strip()
        if not seg:
            continue
            
        # Check for python -c or node -e ANYWHERE in the segment (might be after a pipe)
        # Don't split on semicolons if inline code is present (semicolons in the code)
        inline_code_match = re.search(
            r'(?:^|\|)\s*(?:\S+/)*(?:python[\d.]*(?:\.exe)?\s+-c|node(?:\.exe)?\s+-e)\s+', seg
        )
        if inline_code_match:
            # Don't split inline code commands - treat as single segment
            segments.append(seg)
        else:
            # Safe to split on semicolons for non-python-c commands
            sub_segs = re.split(r'\s*;\s*', seg)
            segments.extend([s.strip() for s in sub_segs if s.strip()])

    for segment in segments:
        # Split on pipes — but not inside quotes
        # Simple approach: split on | that's preceded/followed by spaces
        # and not inside single or double quotes
        pipe_parts = _split_on_pipes(segment)

        for pipe_part in pipe_parts:
            pipe_part = pipe_part.strip()
            if not pipe_part:
                continue

            # Handle $() command substitution in variable assignments: VAR=$(cmd)
            # Must check BEFORE stripping parentheses to avoid mangling $(...)
            var_sub_match = re.match(r'^(\w+)=\$\((.+)\)$', pipe_part.strip())
            if var_sub_match:
                inner_cmd = var_sub_match.group(2)
                inner_commands = extract_commands(inner_cmd)
                commands.extend(inner_commands)
                continue

            # Strip subshell parentheses (only leading/trailing, not $(...))
            while pipe_part.startswith('(') and not pipe_part.startswith('$('):
                pipe_part = pipe_part[1:].strip()
            while pipe_part.endswith(')') and '$(' not in pipe_part:
                pipe_part = pipe_part[:-1].strip()
            if not pipe_part:
                continue

            # Special handling for python -c / node -e with complex inline code.
            # Inline code can contain pipes, semicolons, nested quotes —
            # impossible to parse with shlex. Just extract the command name.
            first_words = pipe_part.strip().split()
            if len(first_words) >= 2:
                base = os.path.basename(first_words[0])
                base_normalized = base.removesuffix(".exe") if base.endswith(".exe") else base
                if re.match(r'^python[\d.]*$', base_normalized) and first_words[1] == "-c":
                    commands.append(base)
                    continue
                if base_normalized in ("node", "npx") and first_words[1] == "-e":
                    commands.append(base)
                    continue

            try:
                tokens = shlex.split(pipe_part)
            except ValueError:
                # shlex failed (complex quoting) — extract just the first word
                if first_words:
                    cmd = os.path.basename(first_words[0])
                    commands.append(cmd)
                continue

            if not tokens:
                continue

            # Track when we expect a command vs arguments
            expect_command = True
            skip_for_var = False  # After 'for', skip the loop variable name

            for token in tokens:
                # After 'for' keyword, the next token is the loop variable — skip it
                if skip_for_var:
                    skip_for_var = False
                    continue

                # Shell operators indicate a new command follows
                if token in ("|", "||", "&&", "&"):
                    expect_command = True
                    continue

                # Skip shell keywords that precede commands
                if token in (
                    "if",
                    "then",
                    "else",
                    "elif",
                    "fi",
                    "while",
                    "until",
                    "do",
                    "done",
                    "case",
                    "esac",
                    "in",
                    "!",
                    "{",
                    "}",
                ):
                    continue

                # 'for' keyword — skip it AND the next token (loop variable)
                if token == "for":
                    skip_for_var = True
                    continue

                # Skip flags/options
                if token.startswith("-"):
                    continue

                # Skip variable assignments (VAR=value)
                if "=" in token and not token.startswith("="):
                    continue

                if expect_command:
                    # Extract the base command name (handle paths like /usr/bin/python, .venv/Scripts/python.exe)
                    cmd = os.path.basename(token)
                    commands.append(cmd)
                    expect_command = False

    return commands


def validate_pkill_command(command_string: str) -> tuple[bool, str]:
    """
    Validate pkill commands - only allow killing dev-related processes.

    Uses shlex to parse the command, avoiding regex bypass vulnerabilities.

    Returns:
        Tuple of (is_allowed, reason_if_blocked)
    """
    # Allowed process names for pkill
    allowed_process_names = {
        # Node.js processes
        "node",
        "npm",
        "npx",
        "vite",
        "next",
        # Python processes
        "python",
        "python3",
        "uvicorn",
        "gunicorn",
        "pytest",
        "alembic",
    }

    try:
        tokens = shlex.split(command_string)
    except ValueError:
        return False, "Could not parse pkill command"

    if not tokens:
        return False, "Empty pkill command"

    # Separate flags from arguments
    args = []
    for token in tokens[1:]:
        if not token.startswith("-"):
            args.append(token)

    if not args:
        return False, "pkill requires a process name"

    # The target is typically the last non-flag argument
    target = args[-1]

    # For -f flag (full command line match), extract the first word as process name
    # e.g., "pkill -f 'node server.js'" -> target is "node server.js", process is "node"
    if " " in target:
        target = target.split()[0]

    if target in allowed_process_names:
        return True, ""
    # Allow patterns that start with an allowed process name (e.g. "vite.*3010" for pkill -f)
    if any(target.startswith(p) for p in allowed_process_names):
        return True, ""
    return False, f"pkill only allowed for dev processes: {allowed_process_names}"


def validate_chmod_command(command_string: str) -> tuple[bool, str]:
    """
    Validate chmod commands - only allow making files executable with +x.

    Returns:
        Tuple of (is_allowed, reason_if_blocked)
    """
    try:
        tokens = shlex.split(command_string)
    except ValueError:
        return False, "Could not parse chmod command"

    if not tokens or tokens[0] != "chmod":
        return False, "Not a chmod command"

    # Look for the mode argument
    # Valid modes: +x, u+x, a+x, etc. (anything ending with +x for execute permission)
    mode = None
    files = []

    for token in tokens[1:]:
        if token.startswith("-"):
            # Skip flags like -R (we don't allow recursive chmod anyway)
            return False, "chmod flags are not allowed"
        elif mode is None:
            mode = token
        else:
            files.append(token)

    if mode is None:
        return False, "chmod requires a mode"

    if not files:
        return False, "chmod requires at least one file"

    # Only allow +x variants (making files executable)
    # This matches: +x, u+x, g+x, o+x, a+x, ug+x, etc.
    import re

    if not re.match(r"^[ugoa]*\+x$", mode):
        return False, f"chmod only allowed with +x mode, got: {mode}"

    return True, ""


def validate_rm_command(command_string: str) -> tuple[bool, str]:
    """
    Validate rm commands — block catastrophic patterns like rm -rf /, rm -rf ~.
    Allow removing build artifacts (node_modules, dist, .venv, __pycache__, etc.).

    Returns:
        Tuple of (is_allowed, reason_if_blocked)
    """
    try:
        tokens = shlex.split(command_string)
    except ValueError:
        return False, "Could not parse rm command"

    if not tokens:
        return False, "Empty rm command"

    # Extract targets (non-flag arguments)
    targets = [t for t in tokens[1:] if not t.startswith("-")]

    if not targets:
        return False, "rm requires at least one target"

    # Block catastrophic patterns
    import re
    dangerous_patterns = [
        r"^/$",           # rm /
        r"^/[a-z]+$",     # rm /usr, /etc, /home, etc.
        r"^~/?$",         # rm ~ or rm ~/
        r"^\$HOME/?$",    # rm $HOME
        r"^/home/?$",     # rm /home
        r"^/root/?$",     # rm /root
        r"^\.\.$",        # rm ..
        r"^\.$",          # rm .
    ]

    for target in targets:
        # Check both the raw target and the expanded version
        expanded = os.path.expanduser(os.path.expandvars(target))
        for check in (target, expanded):
            for pattern in dangerous_patterns:
                if re.match(pattern, check):
                    return False, f"rm target '{target}' is too dangerous — would delete system directory"
        # Also block if expanded path is a top-level dir (e.g., ~ → /home/user)
        if expanded == os.path.expanduser("~") or expanded == os.path.expanduser("~/"):
            return False, f"rm target '{target}' is too dangerous — would delete home directory"

    return True, ""


def validate_git_add_command(command_string: str, project_dir=None) -> tuple[bool, str]:
    """
    Validate git add commands — block `git add .` and `git add -A` when the project
    has node_modules (or similar) that could be staged without .gitignore protection.

    Returns:
        Tuple of (is_allowed, reason_if_blocked)
    """
    import re
    from pathlib import Path

    try:
        tokens = shlex.split(command_string)
    except ValueError:
        # shlex can't parse (e.g., heredoc in git commit) — check raw string
        # Only block if this actually looks like a `git add .` / `git add -A`
        if not re.search(r'\bgit\s+add\s+[.\-]', command_string):
            return True, ""  # Not a git add wildcard — allow
        return False, "Could not parse git command"

    if not tokens or tokens[0] != "git":
        return True, ""  # Not a git command, let other validation handle

    # Find "add" and its arguments
    if "add" not in tokens:
        return True, ""  # git status, commit, etc. — allow

    add_idx = tokens.index("add")
    args = tokens[add_idx + 1 :]
    # Skip flags like -f, -n, -v
    paths = [a for a in args if not a.startswith("-")]

    # Check if this is a broad add (git add . or git add -A / --all)
    is_broad_add = (
        "." in paths
        or "-A" in tokens
        or "--all" in tokens
    )

    if not is_broad_add:
        return True, ""  # Explicit paths — allow (agent is being specific)

    # Broad add — need to verify .gitignore protects dangerous paths
    if project_dir is None:
        try:
            from hooks.main_hooks import _get_project_dir
            project_dir = _get_project_dir()
        except ImportError:
            pass
        if project_dir is None:
            return True, ""  # Can't check — fail open to avoid breaking

    project_dir = Path(project_dir)
    gitignore_path = project_dir / ".gitignore"

    # Check if any dangerous path exists and might be staged
    for name in _GITADD_DANGEROUS_PATHS:
        if (project_dir / name).exists():
            # This path exists — .gitignore must exclude it
            if not gitignore_path.exists():
                return False, (
                    f"Blocked: `git add .` / `git add -A` would stage '{name}/' which must not be committed. "
                    "Create a .gitignore file with 'node_modules', '.venv', 'dist', etc. before running git add ."
                )
            content = gitignore_path.read_text(encoding="utf-8")
            # Check for exclusion (node_modules, /node_modules, node_modules/, etc.)
            if name not in content and f"/{name}" not in content and f"{name}/" not in content:
                return False, (
                    f"Blocked: `git add .` would stage '{name}/'. Add '{name}' to .gitignore first."
                )

    return True, ""


def validate_helper_script(command_string: str) -> tuple[bool, str]:
    """
    Validate helper script execution - only allow scripts in ALLOWED_HELPER_SCRIPTS.

    Returns:
        Tuple of (is_allowed, reason_if_blocked)
    """
    try:
        tokens = shlex.split(command_string)
    except ValueError:
        return False, "Could not parse script command"

    if not tokens:
        return False, "Empty command"

    # The command should be a script from ALLOWED_HELPER_SCRIPTS
    script = tokens[0]
    script_name = os.path.basename(script)

    # Allow ./script.sh or paths ending in /script.sh for allowed scripts
    if script_name in ALLOWED_HELPER_SCRIPTS:
        # Must be executed with ./ prefix or full path
        if script.startswith("./") or script.startswith("/") or "/" in script:
            return True, ""
        return False, f"Script must be executed with path (e.g., ./{script_name})"

    return False, f"Script '{script_name}' is not in allowed helper scripts: {ALLOWED_HELPER_SCRIPTS}"


# Keep backward compatibility alias
def validate_init_script(command_string: str) -> tuple[bool, str]:
    """Backward compatibility alias for validate_helper_script."""
    return validate_helper_script(command_string)


def get_command_for_validation(cmd: str, segments: list[str]) -> str:
    """
    Find the specific command segment that contains the given command.

    Args:
        cmd: The command name to find
        segments: List of command segments

    Returns:
        The segment containing the command, or empty string if not found
    """
    for segment in segments:
        segment_commands = extract_commands(segment)
        if cmd in segment_commands:
            return segment
    return ""


async def bash_security_hook(input_data, tool_use_id=None, context=None):
    """
    Pre-tool-use hook that validates bash commands using an allowlist.

    Only commands in ALLOWED_COMMANDS are permitted.

    Args:
        input_data: Dict containing tool_name and tool_input
        tool_use_id: Optional tool use ID
        context: Optional context

    Returns:
        Empty dict to allow, or {"decision": "block", "reason": "..."} to block
    """
    if input_data.get("tool_name") != "Bash":
        return {}

    command = input_data.get("tool_input", {}).get("command", "")
    if not command:
        return {}

    # Extract all commands from the command string
    commands = extract_commands(command)

    if not commands:
        # Could not parse - fail safe by blocking
        return {
            "decision": "block",
            "reason": f"Could not parse command for security validation: {command}",
        }

    # Split into segments for per-command validation
    segments = split_command_segments(command)

    # Check each command against the allowlist
    for cmd in commands:
        # Normalize Windows .exe extensions (e.g., python.exe -> python)
        normalized = cmd.removesuffix(".exe") if cmd.endswith(".exe") else cmd
        if normalized not in ALLOWED_COMMANDS and cmd not in ALLOWED_COMMANDS:
            return {
                "decision": "block",
                "reason": f"Command '{cmd}' is not in the allowed commands list",
            }
        # Use normalized name for downstream validation
        cmd = normalized

        # Additional validation for sensitive commands
        if cmd in COMMANDS_NEEDING_EXTRA_VALIDATION:
            # Find the specific segment containing this command
            cmd_segment = get_command_for_validation(cmd, segments)
            if not cmd_segment:
                cmd_segment = command  # Fallback to full command

            if cmd == "pkill":
                allowed, reason = validate_pkill_command(cmd_segment)
                if not allowed:
                    return {"decision": "block", "reason": reason}
            elif cmd == "chmod":
                allowed, reason = validate_chmod_command(cmd_segment)
                if not allowed:
                    return {"decision": "block", "reason": reason}
            elif cmd == "rm":
                allowed, reason = validate_rm_command(cmd_segment)
                if not allowed:
                    return {"decision": "block", "reason": reason}
            elif cmd == "git":
                allowed, reason = validate_git_add_command(cmd_segment)
                if not allowed:
                    return {"decision": "block", "reason": reason}
            elif cmd in ALLOWED_HELPER_SCRIPTS:
                allowed, reason = validate_helper_script(cmd_segment)
                if not allowed:
                    return {"decision": "block", "reason": reason}

    return {}
