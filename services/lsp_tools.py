"""
LSP Code Intelligence Tools
============================

Worker-facing MCP tools that provide language server protocol (LSP)
code intelligence capabilities to swarm workers.

Each worker receives scoped access — queries are restricted to the
worker's assigned file_scope patterns.  Attempting to query a file
outside scope returns an explicit error listing the allowed patterns.

The create_lsp_tool_server() function returns an McpSdkServerConfig
passed to ClaudeAgentOptions.mcp_servers when creating a worker's Engine.
"""

import json
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from claude_agent_sdk import tool, create_sdk_mcp_server


_OPERATIONS = [
    "definition",
    "references",
    "hover",
    "symbols",
    "diagnostics",
    "call_hierarchy",
    "completion",
    "rename_preview",
    "workspace_symbols",
    "implementation",
    "signature_help",
    "code_actions",
    "formatting",
]


def _is_in_scope(file_path: str, file_scope: list[str]) -> bool:
    """Check if file_path matches any of the worker's scope patterns."""
    for pattern in file_scope:
        if fnmatch(file_path, pattern):
            return True
    return False


def _make_error(msg: str) -> dict[str, Any]:
    """Return a standard MCP error response."""
    return {"content": [{"type": "text", "text": json.dumps({"error": msg}, indent=2)}]}


def _make_result(data: dict[str, Any]) -> dict[str, Any]:
    """Return a standard MCP success response."""
    return {"content": [{"type": "text", "text": json.dumps(data, indent=2)}]}


def create_lsp_tool_server(
    lsp_manager: Any,
    worker_id: int,
    file_scope: list[str],
    worktree_path: str | Path,
):
    """
    Create an in-process MCP server with LSP code intelligence tools for a worker.

    The server exposes two tools:
        lsp_query               — query LSP for definition, references, hover, etc.
        lsp_diagnostics_summary — aggregate diagnostics across all scoped files

    Args:
        lsp_manager:   LSPManager instance (typed as Any to avoid circular imports)
        worker_id:     Integer ID of this worker
        file_scope:    Glob patterns for files this worker is allowed to query
        worktree_path: Absolute path to the worker's worktree root
    """
    _worktree = Path(worktree_path)
    _scope = list(file_scope)

    # ── Tool 1: lsp_query ────────────────────────────────────────────

    @tool(
        "lsp_query",
        (
            "Query language server for code intelligence. Supports: "
            "definition, references, hover, symbols, diagnostics, "
            "call_hierarchy, completion, rename_preview, workspace_symbols, "
            "implementation, signature_help, code_actions, formatting."
        ),
        {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": _OPERATIONS,
                    "description": "LSP operation to perform",
                },
                "file_path": {
                    "type": "string",
                    "description": "File path relative to worktree root",
                },
                "line": {
                    "type": "integer",
                    "description": "0-based line number",
                },
                "character": {
                    "type": "integer",
                    "description": "0-based character offset",
                },
                "query": {
                    "type": "string",
                    "description": "Search query (for workspace_symbols)",
                },
                "new_name": {
                    "type": "string",
                    "description": "New name (for rename_preview)",
                },
            },
            "required": ["operation", "file_path"],
        },
    )
    async def lsp_query(args: dict[str, Any]) -> dict[str, Any]:
        operation = args.get("operation", "")
        file_path = args.get("file_path", "")
        line = args.get("line", 0)
        character = args.get("character", 0)
        query = args.get("query", "")
        new_name = args.get("new_name", "")

        # Validate operation
        if operation not in _OPERATIONS:
            return _make_error(
                f"Unknown operation {operation!r}. "
                f"Supported: {', '.join(_OPERATIONS)}"
            )

        # Scope check
        if not _is_in_scope(file_path, _scope):
            return _make_error(
                f"File {file_path!r} is outside worker-{worker_id}'s scope. "
                f"Allowed patterns: {_scope}"
            )

        # Resolve to absolute path and file URI
        abs_path = _worktree / file_path
        file_uri = abs_path.as_uri()

        try:
            # Dispatch to the appropriate LSP method
            if operation == "definition":
                result = await lsp_manager.get_definition(file_uri, line, character)
            elif operation == "references":
                result = await lsp_manager.get_references(file_uri, line, character)
            elif operation == "hover":
                result = await lsp_manager.get_hover(file_uri, line, character)
            elif operation == "symbols":
                result = await lsp_manager.get_document_symbols(file_uri)
            elif operation == "diagnostics":
                result = await lsp_manager.get_diagnostics(file_uri)
            elif operation == "call_hierarchy":
                result = await lsp_manager.get_call_hierarchy(file_uri, line, character)
            elif operation == "completion":
                result = await lsp_manager.get_completion(file_uri, line, character)
            elif operation == "rename_preview":
                if not new_name:
                    return _make_error("rename_preview requires 'new_name' parameter")
                result = await lsp_manager.get_rename_preview(file_uri, line, character, new_name)
            elif operation == "workspace_symbols":
                result = await lsp_manager.get_workspace_symbols(query or "")
            elif operation == "implementation":
                result = await lsp_manager.get_implementation(file_uri, line, character)
            elif operation == "signature_help":
                result = await lsp_manager.get_signature_help(file_uri, line, character)
            elif operation == "code_actions":
                result = await lsp_manager.get_code_actions(file_uri, line, character)
            elif operation == "formatting":
                result = await lsp_manager.get_formatting(file_uri)
            else:
                return _make_error(f"Unhandled operation: {operation}")

            return _make_result({
                "ok": True,
                "operation": operation,
                "file_path": file_path,
                "line": line,
                "character": character,
                "result": result,
            })

        except Exception as e:
            return _make_error(f"LSP {operation} failed for {file_path}: {e}")

    # ── Tool 2: lsp_diagnostics_summary ──────────────────────────────

    @tool(
        "lsp_diagnostics_summary",
        (
            "Get ALL errors and warnings across your assigned files. "
            "Returns aggregate counts and top errors with locations."
        ),
        {"type": "object", "properties": {}, "required": []},
    )
    async def lsp_diagnostics_summary(args: dict[str, Any]) -> dict[str, Any]:
        error_count = 0
        warning_count = 0
        info_count = 0
        all_diagnostics: list[dict[str, Any]] = []
        per_file: dict[str, dict[str, int]] = {}

        for pattern in _scope:
            # Expand glob pattern against worktree
            matched_files = sorted(_worktree.glob(pattern))
            for matched in matched_files:
                if not matched.is_file():
                    continue

                rel_path = str(matched.relative_to(_worktree))
                file_uri = matched.as_uri()

                try:
                    diagnostics = await lsp_manager.get_diagnostics(file_uri)
                except Exception:
                    continue

                if not diagnostics:
                    continue

                file_errors = 0
                file_warnings = 0
                file_info = 0

                items = diagnostics if isinstance(diagnostics, list) else []
                for diag in items:
                    severity = diag.get("severity", 4)
                    # LSP severity: 1=Error, 2=Warning, 3=Info, 4=Hint
                    if severity == 1:
                        error_count += 1
                        file_errors += 1
                    elif severity == 2:
                        warning_count += 1
                        file_warnings += 1
                    else:
                        info_count += 1
                        file_info += 1

                    all_diagnostics.append({
                        "file": rel_path,
                        "severity": severity,
                        "severity_label": {1: "error", 2: "warning", 3: "info", 4: "hint"}.get(severity, "unknown"),
                        "line": diag.get("range", {}).get("start", {}).get("line", 0),
                        "character": diag.get("range", {}).get("start", {}).get("character", 0),
                        "message": diag.get("message", ""),
                        "source": diag.get("source", ""),
                    })

                if file_errors or file_warnings or file_info:
                    per_file[rel_path] = {
                        "errors": file_errors,
                        "warnings": file_warnings,
                        "info": file_info,
                    }

        # Sort by severity (errors first), then file path
        all_diagnostics.sort(key=lambda d: (d["severity"], d["file"]))
        top_20 = all_diagnostics[:20]

        return _make_result({
            "ok": True,
            "worker_id": worker_id,
            "summary": {
                "error_count": error_count,
                "warning_count": warning_count,
                "info_count": info_count,
                "total": error_count + warning_count + info_count,
                "files_scanned": len(per_file),
            },
            "per_file": per_file,
            "top_diagnostics": top_20,
        })

    # ── Server ────────────────────────────────────────────────────────

    return create_sdk_mcp_server(
        "lsp_tools",
        version="1.0.0",
        tools=[lsp_query, lsp_diagnostics_summary],
    )


# Tool names for allowed_tools lists
LSP_TOOL_NAMES = [
    "mcp__lsp_tools__lsp_query",
    "mcp__lsp_tools__lsp_diagnostics_summary",
]
