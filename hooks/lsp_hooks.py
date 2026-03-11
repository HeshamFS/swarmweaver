"""
LSP Diagnostic Injection Hooks
==============================

PostToolUse hooks that inject LSP diagnostics into agent context after file
edits.  When a Write or Edit tool fires, the hook reads the file, notifies
the LSP manager, filters for errors/warnings, and returns them as a blocking
reason so the agent sees the diagnostics immediately.

All hooks follow the SDK callback signature:
    async def hook(input_data: dict, tool_use_id: str | None, context: Any) -> dict

ContextVar pattern mirrors hooks/main_hooks.py — per-asyncio-task isolation
with module-level fallback globals for non-swarm (single-worker) execution.
"""

import contextvars
import logging
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Per-asyncio-task context variables
# ---------------------------------------------------------------------------
# Each swarm worker runs as its own asyncio.Task and gets isolated LSP state.
# The module-level globals serve as fallback for non-swarm (single-worker)
# sessions where no per-task value has been set.
# ---------------------------------------------------------------------------

_lsp_manager_ctx: contextvars.ContextVar[Optional[Any]] = contextvars.ContextVar(
    "swarmweaver_lsp_manager", default=None
)
_lsp_worktree_ctx: contextvars.ContextVar[Optional[Path]] = contextvars.ContextVar(
    "swarmweaver_lsp_worktree", default=None
)
_pending_diag_times: contextvars.ContextVar[Optional[dict[str, float]]] = contextvars.ContextVar(
    "swarmweaver_pending_diag_times", default=None
)

# Watchdog: track tool call count and previous error count per task
_watchdog_call_count: contextvars.ContextVar[int] = contextvars.ContextVar(
    "swarmweaver_lsp_watchdog_calls", default=0
)
_watchdog_prev_error_count: contextvars.ContextVar[int] = contextvars.ContextVar(
    "swarmweaver_lsp_watchdog_prev_errors", default=0
)

# Module-level fallback globals (used when no per-task value is set)
_lsp_manager: Optional[Any] = None
_lsp_worktree: Optional[Path] = None
_pending_diag_times_global: Optional[dict[str, float]] = None


# ---------------------------------------------------------------------------
# Getters
# ---------------------------------------------------------------------------

def _get_lsp_manager() -> Optional[Any]:
    """Return the LSP manager for the current async task (or the global fallback)."""
    return _lsp_manager_ctx.get(_lsp_manager)


def _get_lsp_worktree() -> Optional[Path]:
    """Return the worktree root for the current async task (or the global fallback)."""
    return _lsp_worktree_ctx.get(_lsp_worktree)


def _get_pending_diag_times() -> dict[str, float]:
    """Return the per-file debounce timestamp dict (or the global fallback)."""
    ctx_val = _pending_diag_times.get(_pending_diag_times_global)
    if ctx_val is None:
        ctx_val = {}
        _pending_diag_times.set(ctx_val)
    return ctx_val


# ---------------------------------------------------------------------------
# Setter — called by Engine during worker setup
# ---------------------------------------------------------------------------

def set_lsp_context(manager: Any, worktree: Path) -> None:
    """Configure the LSP manager and worktree root (per-task and global fallback).

    Called by Engine during worker setup so that PostToolUse hooks can access
    the LSP manager for diagnostic injection.
    """
    global _lsp_manager, _lsp_worktree, _pending_diag_times_global
    _lsp_manager = manager
    _lsp_worktree = worktree
    _pending_diag_times_global = {}
    _lsp_manager_ctx.set(manager)
    _lsp_worktree_ctx.set(worktree)
    _pending_diag_times.set({})


# ---------------------------------------------------------------------------
# PostToolUse: diagnostic injection after Write / Edit
# ---------------------------------------------------------------------------

DEBOUNCE_MS = 150  # skip if <150ms since last edit to same file


async def lsp_post_edit_hook(
    input_data: dict[str, Any],
    tool_use_id: Optional[str] = None,
    context: Any = None,
) -> dict[str, Any]:
    """PostToolUse hook that injects LSP diagnostics after Write/Edit.

    1. Only fires for tool_name == "Write" or "Edit".
    2. Extracts file_path from tool_input.
    3. Debounces: skips if <150ms since last edit to the same file.
    4. Reads the file content from disk.
    5. Notifies the LSP manager of the change.
    6. Filters diagnostics to severity 1 (Error) and 2 (Warning).
    7. If issues found, returns a blocking reason with formatted diagnostics.
    """
    tool_name = input_data.get("tool_name", "")
    if tool_name not in ("Write", "Edit"):
        return {}

    manager = _get_lsp_manager()
    if manager is None:
        return {}

    # Extract file_path from tool input
    tool_input = input_data.get("tool_input", {})
    file_path_str = tool_input.get("file_path", "")
    if not file_path_str:
        return {}

    file_path = Path(file_path_str)

    # Debounce: skip if <150ms since last edit to same file
    diag_times = _get_pending_diag_times()
    now = time.monotonic()
    last_time = diag_times.get(file_path_str, 0.0)
    if (now - last_time) * 1000 < DEBOUNCE_MS:
        return {}
    diag_times[file_path_str] = now

    try:
        # Read file content from disk
        if not file_path.exists():
            return {}
        content = file_path.read_text(encoding="utf-8", errors="replace")

        # Determine worker_id from context if available
        worker_id = None
        if context is not None:
            worker_id = getattr(context, "worker_id", None)

        # Pass the worktree root so notify_file_changed can lazy-spawn
        # an LSP server on first file write (critical for greenfield projects
        # where no files exist at worker-spawn time).
        worktree = _get_lsp_worktree()
        diagnostics = await manager.notify_file_changed(
            file_path_str, content, worker_id, root_path=worktree
        )

        if not diagnostics:
            return {}

        # Filter to Error (1) and Warning (2) severity
        filtered = [d for d in diagnostics if d.get("severity") in (1, 2)]
        if not filtered:
            return {}

        # Build injection string
        severity_map = {1: "ERROR", 2: "WARNING"}
        lines: list[str] = []
        for diag in filtered:
            sev = diag.get("severity", 0)
            sev_label = severity_map.get(sev, "ISSUE")
            source = f" ({diag.get('source')})" if diag.get("source") else ""
            line_num = diag.get("start_line", 0) + 1  # LSP uses 0-based lines
            lines.append(f"  {sev_label} line {line_num}: {diag.get('message', '')}{source}")

        injection = "\u26a0 LSP DIAGNOSTICS after edit:\n" + "\n".join(lines)
        return {"decision": "block", "reason": injection}

    except Exception:
        logger.debug("lsp_post_edit_hook failed for %s", file_path_str, exc_info=True)
        return {}


# ---------------------------------------------------------------------------
# PostToolUse: diagnostic watchdog (general, every 10 tool calls)
# ---------------------------------------------------------------------------

WATCHDOG_EVERY_N = 10  # check every 10 tool calls


async def lsp_diagnostic_watchdog_signal(
    input_data: dict[str, Any],
    tool_use_id: Optional[str] = None,
    context: Any = None,
) -> dict[str, Any]:
    """PostToolUse hook that periodically checks for rising LSP error counts.

    Runs on every tool call but only performs the diagnostic check every
    WATCHDOG_EVERY_N calls.  Never blocks -- just logs a warning if the error
    count is trending upward.
    """
    # Increment call counter
    counter = _watchdog_call_count.get(0) + 1
    _watchdog_call_count.set(counter)

    if counter % WATCHDOG_EVERY_N != 0:
        return {}

    manager = _get_lsp_manager()
    if manager is None:
        return {}

    try:
        # Get all current diagnostics with severity == 1 (Error)
        all_diagnostics = manager.get_all_diagnostics()
        current_error_count = sum(
            1 for d in all_diagnostics if d.get("severity") == 1
        )

        prev_error_count = _watchdog_prev_error_count.get(0)
        _watchdog_prev_error_count.set(current_error_count)

        if current_error_count > prev_error_count:
            delta = current_error_count - prev_error_count
            logger.warning(
                "[LSP WATCHDOG] Error count increased by %d (now %d total)",
                delta,
                current_error_count,
            )
    except Exception:
        logger.debug("lsp_diagnostic_watchdog_signal failed", exc_info=True)

    return {}


# ---------------------------------------------------------------------------
# Cross-worker diagnostic routing via mail
# ---------------------------------------------------------------------------


async def _route_cross_worker_diagnostics(
    diagnostics: list[Any],
    current_worker_id: str,
    mail_dir: Path,
    file_scope_map: dict[str, str],
) -> None:
    """Route diagnostics to other workers whose file scope is affected.

    For each diagnostic, checks whether the file belongs to another worker's
    scope (via file_scope_map: file_path -> worker_id).  If so, sends a mail
    alert to that worker via MailStore.

    Args:
        diagnostics: List of Diagnostic objects from the LSP.
        current_worker_id: ID of the worker that triggered the edit.
        mail_dir: Project directory for the MailStore.
        file_scope_map: Mapping of file paths to owning worker IDs.
    """
    # Lazy import to avoid circular imports
    from state.mail import MailStore, MessageType

    store = MailStore(mail_dir)

    for diag in diagnostics:
        # Resolve the file path from the diagnostic URI
        diag_path = diag.uri
        if diag_path.startswith("file://"):
            diag_path = diag_path[len("file://"):]

        # Look up the owning worker for this file
        owner_worker_id = file_scope_map.get(diag_path)
        if owner_worker_id is None or owner_worker_id == current_worker_id:
            continue

        # Send a mail alert to the owning worker
        try:
            store.send(
                sender=f"worker-{current_worker_id}",
                recipient=f"worker-{owner_worker_id}",
                msg_type=MessageType.DISPATCH.value,
                subject=f"LSP: {diag.severity_label} in your file",
                body=(
                    f"Edit caused {diag.severity_label} at line "
                    f"{diag.start_line + 1}: {diag.message}"
                ),
            )
        except Exception:
            logger.debug(
                "Failed to route diagnostic to worker-%s for %s",
                owner_worker_id,
                diag_path,
                exc_info=True,
            )
