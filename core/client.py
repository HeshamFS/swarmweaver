"""
Claude SDK Client Configuration - Enhanced
==========================================

Functions for creating and configuring the Claude Agent SDK client
with all enhancement features:
- File checkpointing for rollback
- Session resumption across restarts
- Programmatic subagents for parallel tasks
- Enhanced hooks for audit logging and graceful shutdown
- Structured outputs for reliable progress tracking
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
from claude_agent_sdk.types import HookMatcher

from hooks import (
    bash_security_hook,
    protect_swarmweaver_backend_hook,
    audit_log_hook,
    stop_hook,
    pre_compact_hook,
    subagent_stop_hook,
    server_management_hook,
    environment_management_hook,
    file_management_hook,
    port_config_hook,
    test_script_port_hook,
    knowledge_injection_hook,
    log_consolidation_hook,
    progress_file_management_hook,
    shell_script_lf_hook,
    write_before_read_hook,
    steering_hook,
    worker_scope_hook,
    mail_injection_hook,
    set_audit_log_path,
    set_transcript_archive_path,
    set_project_dir,
    set_cleanup_on_stop,
    set_mail_store,
    tool_permissions_hook,
    set_permissions_project_dir,
    lsp_post_edit_hook,
    lsp_diagnostic_watchdog_signal,
)
from hooks.marathon_hooks import (
    configure_marathon,
    auto_commit_hook,
    health_monitor_hook,
    loop_detection_hook,
    resource_monitor_hook,
    session_stats_hook,
    force_commit,
)
from core.models import ORCHESTRATOR_MODEL, WORKER_MODEL
from core.paths import get_paths
from state.process_registry import get_registry, check_and_register_server
from services.subagents import SUBAGENT_DEFINITIONS
from services.schemas import FEATURE_COMPLETION_SCHEMA


# Puppeteer MCP tools for browser automation
PUPPETEER_TOOLS = [
    "mcp__puppeteer__puppeteer_navigate",
    "mcp__puppeteer__puppeteer_screenshot",
    "mcp__puppeteer__puppeteer_click",
    "mcp__puppeteer__puppeteer_fill",
    "mcp__puppeteer__puppeteer_select",
    "mcp__puppeteer__puppeteer_hover",
    "mcp__puppeteer__puppeteer_evaluate",
]

# Web search MCP tools for fetching external information
WEB_SEARCH_TOOLS = [
    "mcp__web_search__search",
]

# Built-in tools
BUILTIN_TOOLS = [
    "Read",
    "Write",
    "Edit",
    "Glob",
    "Grep",
    "Bash",
    "Task",        # Required for subagent invocation
    "TodoWrite",   # For task tracking
    "WebSearch",   # Built-in web search (in addition to MCP)
    "WebFetch",    # Fetch and analyze web pages
]


def create_client(
    project_dir: Path,
    model: str,
    # Session management
    resume_session_id: Optional[str] = None,
    fork_session: bool = False,
    # Feature flags
    enable_checkpointing: bool = True,
    enable_subagents: bool = True,
    enable_audit_logging: bool = True,
    enable_structured_output: bool = False,
    enable_streaming: bool = True,
    # Worker scope injection (swarm mode only)
    extra_mcp_servers: Optional[dict] = None,
    extra_allowed_tools: Optional[list] = None,
    # Worker budget and turn limits
    max_budget_usd: Optional[float] = None,
    max_turns: Optional[int] = None,
    # Extended thinking configuration
    thinking: Optional[dict] = None,
    effort: Optional[str] = None,
) -> ClaudeSDKClient:
    """
    Create a Claude Agent SDK client with all enhancements.

    Args:
        project_dir: Directory for the project
        model: Claude model to use
        resume_session_id: Optional session ID to resume
        fork_session: If True, fork the session instead of continuing
        enable_checkpointing: Enable file checkpointing for rollback
        enable_subagents: Enable programmatic subagents
        enable_audit_logging: Enable PostToolUse audit logging
        enable_structured_output: Enable structured JSON output
        enable_streaming: Enable partial message streaming

    Returns:
        Configured ClaudeSDKClient

    Security layers (defense in depth):
    1. Sandbox - OS-level bash command isolation prevents filesystem escape
    2. Permissions - File operations restricted to project_dir only
    3. Security hooks - Bash commands validated against an allowlist
       (see security.py for ALLOWED_COMMANDS)
    """
    # Auth info — the SDK itself handles authentication via env vars OR
    # Claude CLI config (~/.claude/).  We just log which method is detected.
    oauth_token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if oauth_token:
        print("Using CLAUDE_CODE_OAUTH_TOKEN for authentication (Claude Code Max)")
    elif api_key:
        print("Using ANTHROPIC_API_KEY for authentication")
    else:
        print("Using Claude CLI config for authentication")

    # Ensure project directory exists
    project_dir.mkdir(parents=True, exist_ok=True)

    # Initialize centralized paths
    paths = get_paths(project_dir)
    paths.ensure_dir()

    # Load user-configured MCP servers
    from services.mcp_manager import MCPConfigStore
    mcp_store = MCPConfigStore(project_dir)
    user_mcp_servers = mcp_store.get_enabled_sdk_servers()
    user_mcp_tool_names = mcp_store.get_enabled_tool_names()

    # Configure hook file paths and process registry
    if enable_audit_logging:
        set_audit_log_path(paths.audit_log)
    set_transcript_archive_path(paths.transcript_archive)
    set_project_dir(project_dir)
    set_permissions_project_dir(project_dir)
    set_cleanup_on_stop(True)  # Cleanup background processes on shutdown

    # Configure marathon hooks for long-running sessions
    configure_marathon(project_dir, commit_interval_minutes=15)

    # Initialize process registry and cleanup dead processes from previous sessions
    try:
        registry = get_registry(project_dir)
        dead = registry.cleanup_dead_processes()
        if dead:
            print(f"Cleaned up {len(dead)} dead processes from previous session")
        status = registry.get_status()
        if status["total"] > 0:
            print(f"Process registry: {status['total']} active processes")
            for port in status["ports_in_use"]:
                print(f"   - Port {port} in use")
    except Exception as e:
        print(f"Warning: Could not initialize process registry: {e}")

    # Build hooks configuration
    # Autonomous hooks run in order for each tool type
    hooks = {
        "PreToolUse": [
            # Steering hook — runs on ALL tools to check for operator messages
            HookMatcher(hooks=[steering_hook]),
            # User-defined tool permissions (deny list from project_settings.json)
            HookMatcher(hooks=[tool_permissions_hook]),
            # Swarm worker: block direct task_list.json access (use MCP tools instead)
            HookMatcher(hooks=[worker_scope_hook]),
            # Bash command hooks
            HookMatcher(matcher="Bash", hooks=[
                bash_security_hook,               # Security validation first
                protect_swarmweaver_backend_hook,  # Prevent killing SwarmWeaver backend on 8000
                port_config_hook,                # Auto-fix port references
                environment_management_hook,    # Auto-manage venv/node_modules
                server_management_hook,         # Auto-manage server processes
            ]),
            # Write-before-read safety — applies to Write, Edit, and Read
            HookMatcher(hooks=[write_before_read_hook]),
            # File operation hooks
            HookMatcher(matcher="Write", hooks=[
                file_management_hook,         # Auto-organize files
                log_consolidation_hook,       # Consolidate log files
                test_script_port_hook,        # Auto-fix ports in test scripts
            ]),
            HookMatcher(matcher="Edit", hooks=[
                file_management_hook,         # Auto-organize files
            ]),
        ],
        "PostToolUse": [
            HookMatcher(matcher="Edit", hooks=[
                progress_file_management_hook,  # Warn if progress file too large
                lsp_post_edit_hook,             # LSP diagnostics after edit
            ]),
            HookMatcher(matcher="Write", hooks=[
                shell_script_lf_hook,  # Normalize .sh files to LF (fix CRLF in WSL)
                lsp_post_edit_hook,    # LSP diagnostics after write
            ]),
        ],
        "Stop": [HookMatcher(hooks=[stop_hook])],
        "PreCompact": [HookMatcher(hooks=[pre_compact_hook])],
        "SubagentStop": [HookMatcher(hooks=[subagent_stop_hook])],
    }

    if enable_audit_logging:
        hooks["PostToolUse"].append(HookMatcher(hooks=[
            audit_log_hook,
            knowledge_injection_hook,
            mail_injection_hook,
            lsp_diagnostic_watchdog_signal,
            # Marathon hooks for long-running sessions
            session_stats_hook,
            loop_detection_hook,
            auto_commit_hook,
            health_monitor_hook,
            resource_monitor_hook,
        ]))

    # Create comprehensive security settings
    # Note: Using relative paths ("./**") restricts access to project directory
    # since cwd is set to project_dir
    # Use absolute paths for security settings to prevent writes outside project
    abs_project = str(project_dir.resolve())
    security_settings = {
        "sandbox": {"enabled": True, "autoAllowBashIfSandboxed": True},
        "permissions": {
            "defaultMode": "acceptEdits",  # Auto-approve edits within allowed directories
            "allow": [
                # Allow all file operations within the project directory (absolute paths)
                f"Read({abs_project}/**)",
                f"Write({abs_project}/**)",
                f"Edit({abs_project}/**)",
                f"Glob({abs_project}/**)",
                f"Grep({abs_project}/**)",
                # Bash permission granted here, but actual commands are validated
                # by the bash_security_hook (see security.py for allowed commands)
                "Bash(*)",
                # Allow Task tool for subagent invocation
                "Task(*)",
                # Allow built-in web and task tools
                "TodoWrite(*)",
                "WebSearch(*)",
                "WebFetch(*)",
                # Allow all configured MCP server tools
                *[f"mcp__{s}__*" for s in user_mcp_servers.keys()],
            ],
        },
    }

    # Write settings to a file in the project directory
    settings_file = paths.claude_settings
    try:
        with open(settings_file, "w") as f:
            json.dump(security_settings, f, indent=2)
    except OSError as e:
        print(f"[WARNING] Failed to write security settings: {e}", flush=True)
        settings_file = None

    # Build options dictionary
    options_kwargs = {
        "model": model,
        "system_prompt": """You are an expert full-stack developer building a production-quality web application.

CRITICAL: You have access to powerful tools - USE THEM:

1. **Web Search** (mcp__web_search__search): Search the web for current docs, troubleshooting, best practices
   - Use when: errors, unfamiliar APIs, version-specific info, external services
   - Example: mcp__web_search__search(query="FastAPI SQLAlchemy async session")

2. **Local Docs** (Read + Grep): Project has docs/ folder with specifications and references
   - Use Grep to search: Grep(pattern="Annex III", path="docs/")
   - Use Read to view: Read(file_path="docs/04_EU_AI_ACT_REFERENCE.md")
   - ALWAYS read relevant docs before implementing features

3. **Browser Testing** (puppeteer tools): Verify UI features through actual browser
   - puppeteer_navigate, puppeteer_click, puppeteer_fill, puppeteer_screenshot

DON'T GUESS - SEARCH! Web search is fast and free. Read docs before implementing.""",
        "allowed_tools": [
            *BUILTIN_TOOLS,
            *user_mcp_tool_names,
        ],
        "mcp_servers": user_mcp_servers,
        "hooks": hooks,
        "max_turns": 1000,
        "cwd": str(project_dir.resolve()),
    }

    if settings_file:
        options_kwargs["settings"] = str(settings_file.resolve())

    # Per-worker budget cap (prevents runaway costs)
    if max_budget_usd is not None:
        options_kwargs["max_budget_usd"] = max_budget_usd

    # Override max_turns if specified (e.g., workers get bounded turns)
    if max_turns is not None:
        options_kwargs["max_turns"] = max_turns

    # Extended thinking configuration
    if thinking is not None:
        options_kwargs["thinking"] = thinking
    if effort is not None:
        options_kwargs["effort"] = effort

    # Session resumption
    if resume_session_id:
        options_kwargs["resume"] = resume_session_id
        print(f"Resuming session: {resume_session_id[:16]}...")
        if fork_session:
            options_kwargs["fork_session"] = True
            print("  (forking to new session)")

    # File checkpointing for rollback capability
    if enable_checkpointing:
        options_kwargs["enable_file_checkpointing"] = True
        options_kwargs["permission_mode"] = "acceptEdits"
        extra_args = {"replay-user-messages": None}
        # Worker sessions get debug-to-stderr for crash diagnostics
        if max_budget_usd is not None:
            extra_args["debug-to-stderr"] = None
        options_kwargs["extra_args"] = extra_args
        # Ensure USER and HOME for worker worktrees (WSL npm-cache symlinks need $USER)
        _user = os.environ.get("USER") or os.environ.get("USERNAME") or "swarmweaver"
        _home = os.environ.get("HOME") or os.path.expanduser("~")
        options_kwargs["env"] = {
            "USER": _user,
            "HOME": _home,
            "CLAUDE_CODE_ENABLE_SDK_FILE_CHECKPOINTING": "1"
        }

    # Programmatic subagents for parallel tasks
    if enable_subagents:
        options_kwargs["agents"] = SUBAGENT_DEFINITIONS

    # Structured output for reliable progress tracking
    if enable_structured_output:
        options_kwargs["output_format"] = {
            "type": "json_schema",
            "schema": FEATURE_COMPLETION_SCHEMA,
        }

    # Partial message streaming for real-time display
    if enable_streaming:
        options_kwargs["include_partial_messages"] = True

    # Worker scope injection — merge in any extra MCP servers and allowed tools
    if extra_mcp_servers:
        options_kwargs["mcp_servers"] = {
            **options_kwargs.get("mcp_servers", {}),
            **extra_mcp_servers,
        }
    if extra_allowed_tools:
        existing = list(options_kwargs.get("allowed_tools", []))
        for t in extra_allowed_tools:
            if t not in existing:
                existing.append(t)
        options_kwargs["allowed_tools"] = existing

    # Print configuration summary
    print(f"Created security settings at {settings_file}")
    print("   - Sandbox enabled (OS-level bash isolation)")
    print(f"   - Filesystem restricted to: {project_dir.resolve()}")
    print("   - Bash commands restricted to allowlist (see security.py)")
    mcp_names = list(user_mcp_servers.keys())
    print(f"   - MCP servers: {', '.join(mcp_names) if mcp_names else 'none'}")
    print(f"   - Checkpointing: {'enabled' if enable_checkpointing else 'disabled'}")
    print(f"   - Subagents: {'enabled' if enable_subagents else 'disabled'}")
    print(f"   - Audit logging: {'enabled' if enable_audit_logging else 'disabled'}")
    print(f"   - Streaming: {'enabled' if enable_streaming else 'disabled'}")
    print()

    try:
        return ClaudeSDKClient(options=ClaudeAgentOptions(**options_kwargs))
    except TypeError:
        # SDK version may not support all kwargs — strip optional ones and retry
        for key in ("max_budget_usd", "max_turns", "extra_args", "thinking", "effort"):
            options_kwargs.pop(key, None)
        return ClaudeSDKClient(options=ClaudeAgentOptions(**options_kwargs))


# ---------------------------------------------------------------------------
# Orchestrator Client
# ---------------------------------------------------------------------------

def create_orchestrator_client(
    project_dir: Path,
    orchestrator_tool_server,
    resume_session_id: Optional[str] = None,
) -> ClaudeSDKClient:
    """
    Create a Claude SDK client configured for the smart orchestrator agent.

    The orchestrator is read-only (no Write/Edit) and uses custom MCP tools
    for worker management.  Always runs on Opus for best coordination reasoning.

    Args:
        project_dir: Project directory
        orchestrator_tool_server: McpSdkServerConfig from create_orchestrator_tool_server()

    Returns:
        Configured ClaudeSDKClient
    """
    from core.orchestrator_tools import ORCHESTRATOR_TOOL_NAMES

    project_dir = Path(project_dir)
    project_dir.mkdir(parents=True, exist_ok=True)
    paths = get_paths(project_dir)
    paths.ensure_dir()

    # Load orchestrator system prompt
    orchestrator_prompt_path = Path(__file__).parent.parent / "prompts" / "agents" / "orchestrator.md"
    if orchestrator_prompt_path.exists():
        system_prompt = orchestrator_prompt_path.read_text(encoding="utf-8")
    else:
        system_prompt = "You are an intelligent orchestrator coordinating coding workers."

    # Append output formatting guide so orchestrator uses structured output and icon shortcodes
    output_formatting_path = Path(__file__).parent.parent / "prompts" / "shared" / "output_formatting.md"
    if output_formatting_path.exists():
        system_prompt = system_prompt + "\n\n---\n\n" + output_formatting_path.read_text(encoding="utf-8")

    # Read-only tools + orchestrator MCP tools
    allowed_tools = [
        "Read", "Grep", "Glob", "Bash", "TodoWrite",
        *ORCHESTRATOR_TOOL_NAMES,
    ]

    # Lightweight security settings (read-only)
    abs_project = str(project_dir.resolve())
    security_settings = {
        "sandbox": {"enabled": True, "autoAllowBashIfSandboxed": True},
        "permissions": {
            "defaultMode": "acceptEdits",
            "allow": [
                f"Read({abs_project}/**)",
                f"Glob({abs_project}/**)",
                f"Grep({abs_project}/**)",
                "Bash(*)",
                "TodoWrite(*)",
                *ORCHESTRATOR_TOOL_NAMES,
            ],
        },
    }
    settings_file = paths.claude_settings
    try:
        with open(settings_file, "w") as f:
            json.dump(security_settings, f, indent=2)
    except OSError as e:
        print(f"[WARNING] Failed to write orchestrator security settings: {e}", flush=True)
        settings_file = None

    # Configure hook context so steering_hook can find the project dir
    set_project_dir(project_dir)
    set_permissions_project_dir(project_dir)

    # Minimal hooks — only security + steering + tool permissions
    hooks = {
        "PreToolUse": [
            HookMatcher(hooks=[steering_hook]),
            HookMatcher(hooks=[tool_permissions_hook]),
            HookMatcher(matcher="Bash", hooks=[bash_security_hook]),
        ],
    }

    options_kwargs = {
        "model": ORCHESTRATOR_MODEL,
        "system_prompt": system_prompt,
        "allowed_tools": allowed_tools,
        "mcp_servers": {
            "orchestrator_tools": orchestrator_tool_server,
        },
        "hooks": hooks,
        "max_turns": 200,
        "cwd": str(project_dir.resolve()),
        "permission_mode": "acceptEdits",
        "include_partial_messages": True,
        "thinking": {"type": "adaptive"},
        "effort": "high",
        "env": {
            "USER": os.environ.get("USER") or os.environ.get("USERNAME") or "swarmweaver",
            "HOME": os.environ.get("HOME") or os.path.expanduser("~"),
        },
    }

    if settings_file:
        options_kwargs["settings"] = str(settings_file.resolve())

    if resume_session_id:
        options_kwargs["resume_session_id"] = resume_session_id
        print(f"[ORCHESTRATOR] Resuming session: {resume_session_id[:16]}...")

    print(f"[ORCHESTRATOR] Created client: model={ORCHESTRATOR_MODEL}, cwd={project_dir}")
    try:
        return ClaudeSDKClient(options=ClaudeAgentOptions(**options_kwargs))
    except TypeError:
        for key in ("max_budget_usd", "max_turns", "extra_args", "thinking", "effort"):
            options_kwargs.pop(key, None)
        return ClaudeSDKClient(options=ClaudeAgentOptions(**options_kwargs))
