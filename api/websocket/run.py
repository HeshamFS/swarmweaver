"""WebSocket handler for /ws/run — runs the agent and streams output."""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.models import DEFAULT_MODEL
from core.paths import get_paths
from core.engine import Engine
from features.notifications import NotificationManager
from utils.sanitizer import sanitize
from api.state import _running_engines

router = APIRouter()

# Max chars for tool_input and error in persisted records
_ERROR_LOG_INPUT_TRUNCATE = 2000
_ERROR_LOG_ERROR_TRUNCATE = 2000


async def _ws_run_native(
    websocket: WebSocket,
    config: dict,
    project_dir: str,
    original_project_dir: str,
    mode: str,
    task_input: str,
    model: str,
    max_iterations: Optional[int],
    no_resume: bool,
    parallel: int,
    worktree_enabled: bool,
    worktree_run_id: Optional[str],
) -> None:
    """Run the agent in-process using Engine with SDK event streaming.

    Events are streamed directly to the WebSocket — no subprocess, no regex parsing.
    """
    proc_key = f"native_{mode}_{original_project_dir}"

    # Open activity log for this run (truncate on new run; append on resume).
    # Logs all structured events so completed projects can be replayed.
    _activity_log_file = None
    try:
        _al_paths = get_paths(Path(original_project_dir))
        _al_paths.ensure_dir()
        # no_resume = True means a fresh run → truncate the old log
        _open_mode = "w" if no_resume else "a"
        _activity_log_file = open(_al_paths.activity_log, _open_mode, encoding="utf-8")
    except Exception:
        _activity_log_file = None

    # Event types that are too noisy or too large to persist
    _SKIP_LOG_TYPES = {"tool_input_delta", "output"}

    # Correlation map: tool_use_id -> {tool, input} for error logging
    _tool_context: dict[str, dict] = {}

    # Error log file (main project, append-only)
    _error_log_file = None
    try:
        _el_paths = get_paths(Path(original_project_dir))
        _el_paths.ensure_dir()
        _error_log_file = open(_el_paths.error_log, "a", encoding="utf-8")
    except Exception:
        _error_log_file = None

    def _write_error_record(record: dict) -> None:
        if not _error_log_file:
            return
        try:
            _error_log_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            _error_log_file.flush()
        except Exception:
            pass

    async def on_event(event: dict) -> None:
        """Forward engine events to WebSocket, sanitizing output, and persist to activity log."""
        etype = event.get("type", "")
        worker_id = event.get("worker_id")

        # Correlate tool context for error logging
        if etype == "tool_start":
            tid = event.get("id", "")
            if tid:
                _tool_context[tid] = {"tool": event.get("tool", ""), "input": ""}
        elif etype == "tool_input_complete":
            tid = event.get("id", "")
            if tid and tid in _tool_context:
                raw_input = event.get("input", "")
                if isinstance(raw_input, dict):
                    cmd = raw_input.get("command", "")
                    _tool_context[tid]["input"] = sanitize(str(cmd) if cmd else str(raw_input))[:_ERROR_LOG_INPUT_TRUNCATE]
                elif isinstance(raw_input, str):
                    try:
                        parsed = json.loads(raw_input)
                        if isinstance(parsed, dict) and "command" in parsed:
                            _tool_context[tid]["input"] = sanitize(str(parsed["command"]))[:_ERROR_LOG_INPUT_TRUNCATE]
                        else:
                            _tool_context[tid]["input"] = sanitize(raw_input)[:_ERROR_LOG_INPUT_TRUNCATE]
                    except (json.JSONDecodeError, TypeError):
                        _tool_context[tid]["input"] = sanitize(raw_input)[:_ERROR_LOG_INPUT_TRUNCATE]
                else:
                    _tool_context[tid]["input"] = sanitize(str(raw_input))[:_ERROR_LOG_INPUT_TRUNCATE]
        elif etype in ("tool_error", "tool_blocked"):
            tid = event.get("id", "")
            ctx = _tool_context.pop(tid, {})
            agent = f"worker-{worker_id}" if worker_id is not None else "orchestrator"
            err_msg = event.get("error", event.get("reason", "Unknown error"))
            err_msg = sanitize(str(err_msg))[:_ERROR_LOG_ERROR_TRUNCATE]
            tool_name = ctx.get("tool", "")
            # Steering blocks are directives, not errors — do not log to error_log
            _is_steering = (
                (etype == "tool_blocked" or etype == "tool_error")
                and (
                    "[STEERING]" in err_msg
                    or "[DIRECTIVE FROM ORCHESTRATOR]" in err_msg
                    or "Message from operator" in err_msg
                )
            )
            # User rejections (approval gate) are intentional, not system bugs
            _is_user_rejection = "The user doesn't want to proceed" in err_msg
            # get_my_tasks success content misclassified as error (contains JSON result)
            _is_get_my_tasks_success = (
                tool_name == "mcp__worker_tools__get_my_tasks"
                and ('"worker_id"' in err_msg or '"assigned_task_ids"' in err_msg)
            )
            if not (_is_steering or _is_user_rejection or _is_get_my_tasks_success):
                rec = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "agent": agent,
                    "event_type": etype,
                    "tool_name": tool_name,
                    "tool_input": ctx.get("input", ""),
                    "error": err_msg,
                    "tool_use_id": tid or "",
                }
                _write_error_record(rec)
        elif etype == "session_error":
            agent = f"worker-{worker_id}" if worker_id is not None else "orchestrator"
            data = event.get("data", {}) if isinstance(event.get("data"), dict) else {}
            err_msg = data.get("error", str(event.get("data", "Unknown session error")))
            err_msg = sanitize(str(err_msg))[:_ERROR_LOG_ERROR_TRUNCATE]
            rec = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "agent": agent,
                "event_type": "session_error",
                "tool_name": "",
                "tool_input": "",
                "error": err_msg,
                "tool_use_id": "",
            }
            _write_error_record(rec)

        try:
            # Sanitize any string data
            if "data" in event and isinstance(event["data"], str):
                event["data"] = sanitize(event["data"])
            elif "text" in event and isinstance(event["text"], str):
                event["text"] = sanitize(event["text"])
            elif "error" in event and isinstance(event["error"], str):
                event["error"] = sanitize(event["error"])
            await websocket.send_json(event)
        except (WebSocketDisconnect, RuntimeError):
            # Client disconnected
            pass

        # Persist to activity log (skip noisy delta events)
        if _activity_log_file and etype not in _SKIP_LOG_TYPES:
            try:
                import json as _json
                _activity_log_file.write(_json.dumps(event, ensure_ascii=False) + "\n")
                _activity_log_file.flush()
            except Exception:
                pass

    smart_swarm = config.get("smart_swarm", False)

    if smart_swarm:
        print(f"[ws/run] [SMART SWARM] Creating SmartSwarm: mode={mode}, project_dir={project_dir}", flush=True)
        from core.swarm import SmartSwarm
        engine = SmartSwarm(
            project_dir=project_dir,
            mode=mode,
            model=model,
            task_input=task_input,
            spec_file=config.get("spec"),
            max_iterations=max_iterations,
            resume=not no_resume,
            budget_limit=float(config.get("budget", 0) or 0),
            max_hours=float(config.get("max_hours", 0) or 0),
            max_workers=config.get("max_workers", 50),
            phase_models=config.get("phase_models"),
            on_event=on_event,
        )
    elif parallel > 1:
        print(f"[ws/run] [SWARM] Creating Swarm: mode={mode}, workers={parallel}, project_dir={project_dir}", flush=True)
        from core.swarm import Swarm
        engine = Swarm(
            project_dir=project_dir,
            mode=mode,
            model=model,
            num_workers=parallel,
            task_input=task_input,
            max_iterations=max_iterations,
            resume=not no_resume,
            budget_limit=float(config.get("budget", 0) or 0),
            max_hours=float(config.get("max_hours", 0) or 0),
            phase_models=config.get("phase_models"),
            overrides=config.get("overrides"),
            on_event=on_event,
        )
    else:
        print(f"[ws/run] [NATIVE] Creating Engine: mode={mode}, model={model}, project_dir={project_dir}", flush=True)
        print(f"[ws/run] [NATIVE] Options: budget={config.get('budget', 0)}, max_hours={config.get('max_hours', 0)}, approval_gates={config.get('approval_gates', False)}, resume={not no_resume}", flush=True)

        # Auto-init LSP for this project (not just Smart Swarm)
        _run_lsp_manager = None
        try:
            from api.state import get_lsp_manager, set_lsp_manager
            _run_lsp_manager = get_lsp_manager(original_project_dir)
            if not _run_lsp_manager:
                from services.lsp_manager import LSPManager, LSPConfig
                _lsp_cfg = LSPConfig.load(Path(original_project_dir))
                if _lsp_cfg.enabled:
                    _run_lsp_manager = LSPManager(
                        original_project_dir, _lsp_cfg, on_event=on_event,
                    )
                    set_lsp_manager(original_project_dir, _run_lsp_manager)
                    _run_lsp_manager.start_health_loop()
                    try:
                        _started = await _run_lsp_manager.auto_detect_and_start()
                        if _started:
                            print(f"[ws/run] LSP auto-started: {', '.join(_started)}", flush=True)
                    except Exception as _lsp_e:
                        print(f"[ws/run] LSP auto-detect failed: {_lsp_e}", flush=True)
        except Exception as _le:
            print(f"[ws/run] LSP init skipped: {_le}", flush=True)

        engine = Engine(
            project_dir=project_dir,
            mode=mode,
            model=model,
            task_input=task_input,
            spec_file=config.get("spec"),
            max_iterations=max_iterations,
            resume=not no_resume,
            budget_limit=float(config.get("budget", 0) or 0),
            max_hours=float(config.get("max_hours", 0) or 0),
            approval_gates=config.get("approval_gates", False),
            auto_pr=config.get("auto_pr", False),
            phase_models=config.get("phase_models"),
            on_event=on_event,
            lsp_manager=_run_lsp_manager,
        )

    _running_engines[proc_key] = engine

    async def _receive_steering():
        """Receive steering/approval/stop messages from WebSocket."""
        while True:
            try:
                raw = await websocket.receive_text()
                msg = json.loads(raw)
                msg_type = msg.get("type", "")

                if msg_type == "stop":
                    await engine.stop()
                    break
                elif msg_type == "steering":
                    steering_type = msg.get("steering_type", "instruction")
                    if steering_type == "model_change":
                        model_id = msg.get("message", "").strip()
                        if model_id:
                            _ws_paths = get_paths(Path(project_dir))
                            _ws_paths.ensure_dir()
                            _ws_paths.model_override.write_text(
                                json.dumps({"model": model_id})
                            )
                    else:
                        from features.steering import write_steering_message
                        write_steering_message(
                            Path(project_dir),
                            msg.get("message", ""),
                            steering_type,
                        )
                        # Wake up any sleeping wait_seconds() so the
                        # orchestrator sees the message without delay.
                        if hasattr(engine, "notify_steering"):
                            try:
                                engine.notify_steering()
                            except Exception:
                                pass
                elif msg_type == "approval_resolve":
                    from features.approval import resolve_approval as _resolve
                    _resolve(
                        Path(project_dir),
                        msg.get("decision", "approved"),
                        msg.get("feedback", ""),
                    )
            except (WebSocketDisconnect, RuntimeError):
                await engine.stop()
                break
            except Exception:
                continue

    # Run engine and steering receiver concurrently
    engine_task = asyncio.create_task(engine.run())
    receive_task = asyncio.create_task(_receive_steering())

    # Wait for engine to complete
    await engine_task
    receive_task.cancel()
    try:
        await receive_task
    except asyncio.CancelledError:
        pass

    # Close activity and error logs
    if _activity_log_file:
        try:
            _activity_log_file.close()
        except Exception:
            pass
    if _error_log_file:
        try:
            _error_log_file.close()
        except Exception:
            pass

    # Clean up
    _running_engines.pop(proc_key, None)

    # Send final worktree status
    if worktree_enabled and worktree_run_id:
        try:
            from core.worktree import get_worktree_status as _get_wt_status
            wt_status = _get_wt_status(Path(original_project_dir), worktree_run_id)
            await websocket.send_json({
                "type": "worktree_ready",
                "data": {
                    "run_id": worktree_run_id,
                    "branch": f"swarmweaver/{worktree_run_id}",
                    "original_project_dir": original_project_dir,
                    "worktree_path": project_dir,
                    "files_changed": wt_status.files_changed,
                    "insertions": wt_status.insertions,
                    "deletions": wt_status.deletions,
                    "diff_stat": wt_status.diff_stat,
                },
            })
        except Exception:
            pass

    # Browser notification
    try:
        await websocket.send_json({
            "type": "browser_notification",
            "data": {
                "title": "SwarmWeaver Complete",
                "body": f"Native agent finished ({mode} mode)",
                "event_type": "all_tasks_done",
            },
        })
    except Exception:
        pass

    # Webhook notifications
    try:
        mgr = NotificationManager(Path(project_dir))
        mgr.notify(
            "all_tasks_done",
            "SwarmWeaver Session Complete",
            f"Mode: {mode}\nProject: {project_dir}\nEngine: native",
        )
    except Exception:
        pass


@router.websocket("/ws/run")
async def ws_run(websocket: WebSocket):
    """
    WebSocket endpoint that runs the agent and streams output in real-time.

    Client sends a JSON RunRequest to start. Server streams structured events
    (tool calls, file touches, errors) plus raw output.
    """
    await websocket.accept()
    print("[ws/run] Connection accepted, waiting for config...", flush=True)

    try:
        # Receive run configuration
        raw = await websocket.receive_text()
        config = json.loads(raw)
        print(f"[ws/run] Config received: mode={config.get('mode')}, project_dir={config.get('project_dir')}, smart_swarm={config.get('smart_swarm')}, parallel={config.get('parallel')}, worktree={config.get('worktree')}", flush=True)

        mode = config.get("mode", "greenfield")
        project_dir = config.get("project_dir", "")
        task_input = config.get("task_input", "")
        model = config.get("model", DEFAULT_MODEL)
        max_iterations = config.get("max_iterations")
        no_resume = config.get("no_resume", False)
        parallel = config.get("parallel", 1)

        if not project_dir:
            await websocket.send_json(
                {"type": "error", "data": "project_dir is required"}
            )
            await websocket.close()
            return

        # If all tasks are done and a new task_input is given, APPEND a new
        # pending task to the existing list. The agent will pick it up in the
        # implement phase and work on it. No deletion, no overwrite.
        if task_input and task_input not in ("", "Resume from checkpoint"):
            pd = Path(project_dir)
            _pd_paths = get_paths(pd)
            tl_file = _pd_paths.resolve_read("task_list.json")
            if tl_file.exists():
                try:
                    tl_data = json.loads(tl_file.read_text(encoding="utf-8"))
                    tasks = tl_data.get("tasks", []) if isinstance(tl_data, dict) else []
                    total = len(tasks)
                    done = sum(1 for t in tasks if isinstance(t, dict) and t.get("status") in ("done", "completed", "passed"))
                    if total > 0 and done >= total:
                        # All tasks complete — append a new pending task
                        next_id = f"TASK-{total + 1:03d}"
                        new_task = {
                            "id": next_id,
                            "title": task_input[:120],
                            "description": task_input,
                            "category": mode if mode != "greenfield" else "feature",
                            "status": "pending",
                            "priority": 1,
                            "depends_on": [],
                            "acceptance_criteria": [],
                            "files_affected": [],
                            "notes": "Added from chat — agent should break this down into sub-tasks if needed.",
                        }
                        if isinstance(tl_data, dict):
                            tl_data["tasks"].append(new_task)
                        else:
                            tl_data.append(new_task)
                        tl_file.write_text(json.dumps(tl_data, indent=2), encoding="utf-8")
                        await websocket.send_json({
                            "type": "output",
                            "data": f"[INFO] Appended new task {next_id}: {task_input[:80]}",
                        })
                except (json.JSONDecodeError, OSError, TypeError):
                    pass

        # Worktree isolation
        # Smart Swarm manages its own worker worktrees internally — skip top-level worktree
        smart_swarm = config.get("smart_swarm", False)
        worktree_enabled = config.get("worktree", False) and not smart_swarm
        worktree_run_id = None
        original_project_dir = project_dir  # preserve for merge/discard later

        if worktree_enabled:
            import secrets as _secrets
            import time as _time
            from core.worktree import create_worktree as _create_wt

            worktree_run_id = f"run-{int(_time.time())}-{_secrets.token_hex(3)}"
            try:
                wt_info = _create_wt(Path(project_dir), worktree_run_id)
                project_dir = wt_info.worktree_path  # redirect agent to worktree
                await websocket.send_json({
                    "type": "output",
                    "data": f"[WORKTREE] Agent working in isolated branch: {wt_info.branch_name}",
                })
                # Notify frontend immediately so task polling uses worktree path
                await websocket.send_json({
                    "type": "worktree_ready",
                    "data": {
                        "run_id": worktree_run_id,
                        "branch": wt_info.branch_name,
                        "original_project_dir": original_project_dir,
                        "worktree_path": wt_info.worktree_path,
                        "files_changed": 0,
                        "insertions": 0,
                        "deletions": 0,
                        "diff_stat": "",
                    },
                })
            except Exception as e:
                await websocket.send_json({
                    "type": "output",
                    "data": f"[WORKTREE] Failed to create worktree: {e}. Running in direct mode.",
                })
                await websocket.send_json({
                    "type": "warning",
                    "data": {
                        "title": "Worktree creation failed",
                        "body": f"Could not create isolated worktree: {e}. Running changes directly in the project directory.",
                    },
                })
                worktree_enabled = False
                worktree_run_id = None

        # --- Persist run config for resume ---
        # Save swarm/execution parameters so resuming the project restores
        # the correct mode (Swarm / SmartSwarm / single-agent).
        try:
            _cfg_paths = get_paths(Path(original_project_dir))
            _cfg_paths.ensure_dir()
            _run_config_data = {
                "mode": mode,
                "smart_swarm": smart_swarm,
                "parallel": parallel,
                "model": model,
                "max_workers": config.get("max_workers", 10),
                "budget": float(config.get("budget", 0) or 0),
                "max_hours": float(config.get("max_hours", 0) or 0),
                "phase_models": config.get("phase_models"),
                "approval_gates": config.get("approval_gates", False),
                "overrides": config.get("overrides"),
                "worktree": worktree_enabled,
            }
            _cfg_paths.run_config.write_text(
                json.dumps(_run_config_data, indent=2), encoding="utf-8"
            )
        except Exception:
            pass

        # --- Replay activity log for resume (restores chat history) ---
        if not no_resume:
            try:
                _replay_paths = get_paths(Path(original_project_dir))
                _replay_file = _replay_paths.activity_log
                if _replay_file.exists():
                    _replay_count = 0
                    with open(_replay_file, "r", encoding="utf-8") as _rf:
                        for _line in _rf:
                            _line = _line.strip()
                            if not _line:
                                continue
                            try:
                                _evt = json.loads(_line)
                                _evt["_replay"] = True
                                await websocket.send_json(_evt)
                                _replay_count += 1
                            except (json.JSONDecodeError, Exception):
                                continue
                    if _replay_count > 0:
                        await websocket.send_json({
                            "type": "replay_complete",
                            "data": {"events_replayed": _replay_count},
                        })
                        print(f"[ws/run] Replayed {_replay_count} events from activity log", flush=True)
            except Exception as _re:
                print(f"[ws/run] Activity log replay failed (non-fatal): {_re}", flush=True)

        # --- SDK execution path ---
        print(f"[ws/run] Running {mode} in-process via Engine (SDK streaming)", flush=True)
        await _ws_run_native(
            websocket, config, project_dir, original_project_dir,
            mode, task_input, model, max_iterations, no_resume, parallel,
            worktree_enabled, worktree_run_id,
        )

    except WebSocketDisconnect:
        print("[ws/run] CLIENT DISCONNECTED (WebSocketDisconnect)", flush=True)
    except json.JSONDecodeError:
        await websocket.send_json(
            {"type": "error", "data": "Invalid JSON in request"}
        )
    except Exception as e:
        import traceback
        print(f"[ws/run] UNHANDLED ERROR: {e}", flush=True)
        traceback.print_exc()
        try:
            await websocket.send_json({"type": "error", "data": str(e)})
        except Exception:
            pass
