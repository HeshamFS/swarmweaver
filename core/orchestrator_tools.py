"""
Orchestrator MCP Tools
=======================

Custom in-process MCP tools for the Smart Orchestrator agent.

Uses the @tool decorator and create_sdk_mcp_server() from the Claude Agent SDK
to define tools that run in-process with direct access to the orchestrator's
WorkerPool, MailStore, TaskList, and MergeResolver.

The create_orchestrator_tool_server() function returns an McpSdkServerConfig
that is passed to ClaudeAgentOptions.mcp_servers when creating the
orchestrator's SDK client.
"""

from typing import Any

from claude_agent_sdk import tool, create_sdk_mcp_server


def create_orchestrator_tool_server(orchestrator: Any):
    """
    Create an in-process MCP server with orchestrator management tools.

    Each tool is a closure that captures the ``orchestrator`` instance,
    giving it direct access to the worker pool, mail system, task list,
    and merge infrastructure.

    Args:
        orchestrator: SmartOrchestrator instance (from core.smart_orchestrator)

    Returns:
        McpSdkServerConfig suitable for ClaudeAgentOptions.mcp_servers
    """

    @tool(
        "spawn_worker",
        "Spawn a new coding worker in its own git worktree. "
        "Assigns specific tasks and a file scope to the worker. "
        "The worker gets ONLY its assigned tasks — it cannot see or touch other tasks. "
        "If file_scope is omitted, it is auto-derived from the tasks' files_affected lists. "
        "The worker sends heartbeats every 10 tool calls and reports each task transition. "
        "Returns the worker_id and initial status.",
        {
            "type": "object",
            "properties": {
                "task_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Task IDs from the task list to assign to this worker (e.g. ['TASK-001', 'TASK-003'])",
                },
                "file_scope": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "File paths this worker is allowed to modify. "
                        "Must NOT overlap with other active workers. "
                        "If omitted, auto-derived from the tasks' files_affected field. "
                        "Provide explicit paths to override (e.g. ['src/components/Foo.tsx', 'src/hooks/useBar.ts'])."
                    ),
                },
                "role": {
                    "type": "string",
                    "enum": ["builder", "reviewer", "scout"],
                    "description": "Agent role: builder (implements code), reviewer (read-only review), scout (read-only exploration). Default: builder",
                },
                "per_task_instructions": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": (
                        "Optional per-task constraints, e.g. {\"TASK-001\": \"Only API layer; do not modify frontend\"}. "
                        "Use when tasks have non-obvious constraints."
                    ),
                },
            },
            "required": ["task_ids"],
        },
    )
    async def spawn_worker(args: dict[str, Any]) -> dict[str, Any]:
        result = await orchestrator._tool_spawn_worker(args)
        return {"content": [{"type": "text", "text": _format_result(result)}]}

    @tool(
        "list_workers",
        "List all active and completed workers with their current status, "
        "assigned tasks, file scopes, and runtime info.",
        {"type": "object", "properties": {}, "required": []},
    )
    async def list_workers(args: dict[str, Any]) -> dict[str, Any]:
        result = await orchestrator._tool_list_workers(args)
        return {"content": [{"type": "text", "text": _format_result(result)}]}

    @tool(
        "get_worker_updates",
        "Check the mail system for new messages from workers. "
        "Returns unread messages including status updates, task completions, "
        "errors, and questions. Messages are marked as read after retrieval.",
        {"type": "object", "properties": {}, "required": []},
    )
    async def get_worker_updates(args: dict[str, Any]) -> dict[str, Any]:
        result = await orchestrator._tool_get_worker_updates(args)
        return {"content": [{"type": "text", "text": _format_result(result)}]}

    @tool(
        "merge_worker",
        "Merge a completed worker's git branch back to the main branch "
        "using the 4-tier conflict resolver (clean -> auto -> AI -> reimagine). "
        "Only call this after the worker has completed all its tasks. "
        "Merge one worker at a time to minimize conflicts.",
        {
            "type": "object",
            "properties": {
                "worker_id": {
                    "type": "integer",
                    "description": "ID of the completed worker whose branch should be merged",
                },
            },
            "required": ["worker_id"],
        },
    )
    async def merge_worker(args: dict[str, Any]) -> dict[str, Any]:
        result = await orchestrator._tool_merge_worker(args)
        return {"content": [{"type": "text", "text": _format_result(result)}]}

    @tool(
        "terminate_worker",
        "Terminate a stuck or failed worker and release its assigned tasks "
        "back to the pending pool. Use this when a worker has been unresponsive "
        "for 5+ minutes or is in an error loop.",
        {
            "type": "object",
            "properties": {
                "worker_id": {
                    "type": "integer",
                    "description": "ID of the worker to terminate",
                },
                "reason": {
                    "type": "string",
                    "description": "Reason for termination (logged for diagnostics)",
                },
            },
            "required": ["worker_id"],
        },
    )
    async def terminate_worker(args: dict[str, Any]) -> dict[str, Any]:
        result = await orchestrator._tool_terminate_worker(args)
        return {"content": [{"type": "text", "text": _format_result(result)}]}

    @tool(
        "reassign_tasks",
        "Move tasks from one worker to another, or assign unassigned tasks "
        "to an existing worker. Useful when a worker finishes early or another "
        "is overloaded. Set to_worker_id=0 to leave tasks unassigned (pending).",
        {
            "type": "object",
            "properties": {
                "task_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Task IDs to reassign",
                },
                "to_worker_id": {
                    "type": "integer",
                    "description": "Target worker ID. Use 0 to return tasks to the unassigned pool.",
                },
            },
            "required": ["task_ids", "to_worker_id"],
        },
    )
    async def reassign_tasks(args: dict[str, Any]) -> dict[str, Any]:
        result = await orchestrator._tool_reassign_tasks(args)
        return {"content": [{"type": "text", "text": _format_result(result)}]}

    @tool(
        "get_task_status",
        "Get current status of all tasks from the task list, including "
        "counts by status, per-worker assignments, and the next actionable task.",
        {"type": "object", "properties": {}, "required": []},
    )
    async def get_task_status(args: dict[str, Any]) -> dict[str, Any]:
        result = await orchestrator._tool_get_task_status(args)
        return {"content": [{"type": "text", "text": _format_result(result)}]}

    @tool(
        "send_directive",
        "Send a steering message to a specific worker. The message is written "
        "to the worker's steering input file and picked up by its hooks. "
        "Use this to adjust worker behavior, provide guidance, or ask questions.",
        {
            "type": "object",
            "properties": {
                "worker_id": {
                    "type": "integer",
                    "description": "Target worker ID",
                },
                "message": {
                    "type": "string",
                    "description": "Directive message to send to the worker",
                },
            },
            "required": ["worker_id", "message"],
        },
    )
    async def send_directive(args: dict[str, Any]) -> dict[str, Any]:
        result = await orchestrator._tool_send_directive(args)
        return {"content": [{"type": "text", "text": _format_result(result)}]}

    @tool(
        "get_lessons",
        "Get errors from all workers and any synthesized lessons. "
        "Call this before spawning new workers to learn from mistakes.",
        {"type": "object", "properties": {}, "required": []},
    )
    async def get_lessons(args: dict[str, Any]) -> dict[str, Any]:
        result = await orchestrator._tool_get_lessons(args)
        return {"content": [{"type": "text", "text": _format_result(result)}]}

    @tool(
        "add_lesson",
        "Record an actionable lesson from worker errors. "
        "This lesson is auto-injected into future workers' context.",
        {
            "type": "object",
            "properties": {
                "lesson": {
                    "type": "string",
                    "description": "Actionable lesson for future workers (be specific and concrete)",
                },
                "applies_to": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "File patterns this lesson applies to (e.g. ['*.tsx', '*.ts']). If omitted, applies globally.",
                },
                "severity": {
                    "type": "string",
                    "enum": ["high", "medium", "low"],
                    "description": "Severity: high = must follow, medium = should follow, low = nice to know. Default: medium",
                },
                "source_errors": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Error IDs this lesson was derived from (e.g. ['err-001', 'err-003'])",
                },
            },
            "required": ["lesson"],
        },
    )
    async def add_lesson(args: dict[str, Any]) -> dict[str, Any]:
        result = await orchestrator._tool_add_lesson(args)
        return {"content": [{"type": "text", "text": _format_result(result)}]}

    @tool(
        "run_verification",
        "Run quality gates (tests, build, conflicts) on the main branch. "
        "Call after all merges and BEFORE signal_complete. "
        "Returns pass/fail for each gate with error details.",
        {"type": "object", "properties": {}, "required": []},
    )
    async def run_verification(args: dict[str, Any]) -> dict[str, Any]:
        result = await orchestrator._tool_run_verification(args)
        return {"content": [{"type": "text", "text": _format_result(result)}]}

    @tool(
        "signal_complete",
        "Signal that all work is done and the orchestrator should shut down. "
        "Call this ONLY when all tasks are completed AND all workers have been "
        "merged. Provide a summary of what was accomplished.",
        {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Completion summary describing what was accomplished",
                },
            },
            "required": ["summary"],
        },
    )
    async def signal_complete(args: dict[str, Any]) -> dict[str, Any]:
        result = await orchestrator._tool_signal_complete(args)
        return {"content": [{"type": "text", "text": _format_result(result)}]}

    @tool(
        "wait_seconds",
        "Wait for a specified number of seconds before continuing. "
        "Returns rich status: per-worker task list (each task's current status), "
        "recent audit log lines showing what the worker is doing, "
        "and a list of workers that finished and are ready to merge. "
        "This is your PRIMARY visibility tool — use it between monitoring checks.",
        {
            "type": "object",
            "properties": {
                "seconds": {
                    "type": "integer",
                    "description": "Number of seconds to wait (1-120). Recommended: 30",
                    "minimum": 1,
                    "maximum": 120,
                },
            },
            "required": ["seconds"],
        },
    )
    async def wait_seconds(args: dict[str, Any]) -> dict[str, Any]:
        result = await orchestrator._tool_wait_seconds(args)
        return {"content": [{"type": "text", "text": _format_result(result)}]}

    @tool(
        "analyze_stalled_worker",
        "Request AI triage analysis for a specific worker on demand. "
        "Use when a worker appears stuck or unresponsive. Returns a triage "
        "verdict (retry/extend/reassign/terminate) with reasoning and confidence.",
        {
            "type": "object",
            "properties": {
                "worker_id": {
                    "type": "integer",
                    "description": "Worker ID to analyze",
                },
            },
            "required": ["worker_id"],
        },
    )
    async def analyze_stalled_worker(args: dict[str, Any]) -> dict[str, Any]:
        worker_id = args.get("worker_id", 0)
        watchdog = getattr(orchestrator, "_watchdog", None)
        if not watchdog:
            return {"content": [{"type": "text", "text": _format_result({
                "error": "Watchdog not available",
            })}]}

        health = watchdog.workers.get(worker_id)
        if not health:
            return {"content": [{"type": "text", "text": _format_result({
                "error": f"Worker {worker_id} not found in watchdog",
            })}]}

        import asyncio
        triage_result = await watchdog._ai_triage_llm(health)
        return {"content": [{"type": "text", "text": _format_result({
            "worker_id": worker_id,
            "triage": triage_result,
        })}]}

    return create_sdk_mcp_server(
        "orchestrator_tools",
        version="1.0.0",
        tools=[
            spawn_worker,
            list_workers,
            get_worker_updates,
            merge_worker,
            terminate_worker,
            reassign_tasks,
            get_task_status,
            send_directive,
            get_lessons,
            add_lesson,
            run_verification,
            signal_complete,
            wait_seconds,
            analyze_stalled_worker,
        ],
    )


# Tool names for use in allowed_tools lists
ORCHESTRATOR_TOOL_NAMES = [
    "mcp__orchestrator_tools__spawn_worker",
    "mcp__orchestrator_tools__list_workers",
    "mcp__orchestrator_tools__get_worker_updates",
    "mcp__orchestrator_tools__merge_worker",
    "mcp__orchestrator_tools__terminate_worker",
    "mcp__orchestrator_tools__reassign_tasks",
    "mcp__orchestrator_tools__get_task_status",
    "mcp__orchestrator_tools__send_directive",
    "mcp__orchestrator_tools__get_lessons",
    "mcp__orchestrator_tools__add_lesson",
    "mcp__orchestrator_tools__run_verification",
    "mcp__orchestrator_tools__signal_complete",
    "mcp__orchestrator_tools__wait_seconds",
    "mcp__orchestrator_tools__analyze_stalled_worker",
]


def _format_result(result: dict) -> str:
    """Format a tool result dict as readable text for the agent."""
    import json
    return json.dumps(result, indent=2, ensure_ascii=False)
