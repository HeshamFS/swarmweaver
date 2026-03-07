"""Wizard pre-build endpoints (QA, architect, analyze, plan, scan, prepare) and task sync."""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from core.models import FAST_MODEL

from core.paths import get_paths
from api.models import (
    QARequest, QAResponse, ArchitectRequest, AnalyzeRequest,
    PlanRequest, ScanRequest, PrepareRequest,
)
from api.helpers import (
    _lightweight_claude_call, _generate_qa_via_sdk,
    _normalize_qa_result, _parse_qa_response, _parse_json_response,
    _load_lightweight_prompt, _build_plan_prompt,
    QA_OUTPUT_SCHEMA,
)

router = APIRouter()


@router.post("/api/qa/generate")
async def generate_qa_questions(req: QARequest):
    """Generate clarifying questions before agent execution."""
    mode = req.mode.strip().lower()
    task_input = req.task_input.strip()

    if not task_input:
        return QAResponse(skip_reason="No task input provided").model_dump()

    mode_guidance = {
        "greenfield": (
            "This is a NEW PROJECT from scratch. Consider asking about:\n"
            "- Preferred tech stack (language, framework, database)\n"
            "- Architecture style (monolith, microservices, serverless)\n"
            "- Quality requirements (testing strategy, CI/CD, linting)\n"
            "- Deployment target (Docker, cloud provider, local only)\n"
            "- Authentication/authorization needs\n"
            "- Styling preferences (CSS framework, design system)"
        ),
        "feature": (
            "This is ADDING A FEATURE to an existing codebase. Consider asking about:\n"
            "- How it integrates with existing components\n"
            "- Testing expectations (unit, integration, e2e)\n"
            "- Whether to follow existing patterns or introduce new ones\n"
            "- UI/UX preferences if it has a frontend component\n"
            "- Backward compatibility requirements\n"
            "- Performance or scale considerations"
        ),
        "refactor": (
            "This is a REFACTORING/MIGRATION task. Consider asking about:\n"
            "- Migration strategy (big bang vs incremental)\n"
            "- Backward compatibility requirements\n"
            "- Whether to keep old code as fallback\n"
            "- Test coverage expectations post-refactor\n"
            "- Performance benchmarks to maintain\n"
            "- Dependencies that might break"
        ),
        "fix": (
            "This is a BUG FIX task. Consider asking about:\n"
            "- Steps to reproduce the bug\n"
            "- Urgency/severity level\n"
            "- Known workarounds in use\n"
            "- Whether a regression test is expected\n"
            "- Environment specifics (OS, browser, versions)\n"
            "- Related issues or recent changes that might be connected"
        ),
        "evolve": (
            "This is an IMPROVEMENT/EVOLUTION task. Consider asking about:\n"
            "- Priority order if multiple improvements mentioned\n"
            "- Scope boundaries (how far to go)\n"
            "- Success metrics or targets\n"
            "- Whether to prioritize performance, readability, or maintainability\n"
            "- Test coverage goals\n"
            "- Documentation expectations"
        ),
        "security": (
            "This is a SECURITY SCAN/AUDIT task. Consider asking about:\n"
            "- Compliance frameworks to target (OWASP, SOC2, HIPAA)\n"
            "- Scan scope (full codebase vs specific areas)\n"
            "- Remediation urgency (report only vs fix immediately)\n"
            "- Dependency audit preferences\n"
            "- Secrets/credentials handling review scope\n"
            "- Whether to include infrastructure config review"
        ),
    }

    guidance = mode_guidance.get(mode, (
        "Consider asking about priorities, scope, preferences, "
        "and any ambiguous aspects of the request."
    ))

    prompt = (
        "Analyze the user's request and generate clarifying questions "
        "before the agent starts working. The user wants to guide the agent "
        "with their preferences — always give them that opportunity.\n\n"
        f"MODE: {mode}\n"
        f"USER REQUEST: {task_input}\n"
        + (f"PROJECT DIRECTORY: {req.project_dir}\n" if req.project_dir else "")
        + f"\n{guidance}\n\n"
        "RULES:\n"
        "1. ALWAYS generate at least 2-3 clarifying questions. Even for simple "
        "requests, ask about preferences like tech stack, styling, testing "
        "approach, or project structure. The user values human-in-the-loop "
        "control. Only set skip_reason for trivially obvious one-line fixes "
        '(e.g. "Fix typo in README").\n'
        "2. Return 2-8 clarifying questions.\n"
        "3. Each question must have 2-5 options that cover the most likely answers.\n"
        "4. Questions should be ordered by importance.\n"
        '5. Include a brief "context" field explaining why each question matters.\n'
        "6. Do NOT ask obvious questions or about things already specified.\n"
        "7. For complex multi-part requests, consider asking about phasing.\n\n"
        "Return the result as structured JSON."
    )

    sdk_result = await _generate_qa_via_sdk(prompt)
    if sdk_result is not None:
        return _normalize_qa_result(sdk_result)

    try:
        response_text = await _lightweight_claude_call(
            prompt,
            model=FAST_MODEL,
            timeout_seconds=45,
            disable_tools=True,
            json_schema=QA_OUTPUT_SCHEMA,
        )
        return _parse_qa_response(response_text)

    except HTTPException:
        raise
    except FileNotFoundError:
        return QAResponse(skip_reason="claude CLI not found. Proceeding directly.").model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"QA generation failed: {str(e)}")


@router.post("/api/architect/generate")
async def generate_architect_spec(req: ArchitectRequest):
    """Generate an app specification from an idea."""
    if not req.idea.strip():
        raise HTTPException(status_code=400, detail="Idea is required.")

    template = _load_lightweight_prompt("architect")
    current_date = datetime.now().strftime("%Y-%m-%d")
    prompt = template.replace("{task_input}", req.idea.strip()).replace("{current_date}", current_date)

    response_text = await _lightweight_claude_call(
        prompt, model=req.model, timeout_seconds=300
    )
    return {"spec": response_text}


@router.post("/api/analyze/generate")
async def generate_codebase_analysis(req: AnalyzeRequest):
    """Analyze an existing codebase and return a codebase profile JSON."""
    project_dir = req.project_dir.strip()
    if not project_dir or not Path(project_dir).is_dir():
        raise HTTPException(status_code=400, detail="Valid project_dir is required.")

    template = _load_lightweight_prompt("analyzer")
    prompt = template.replace("{task_input}", req.task_input.strip())

    response_text = await _lightweight_claude_call(
        prompt, model=req.model, cwd=project_dir, timeout_seconds=300
    )
    return {"codebase_profile": _parse_json_response(response_text)}


@router.post("/api/plan/generate")
async def generate_plan(req: PlanRequest):
    """Generate a task list from a spec or codebase profile."""
    prompt = _build_plan_prompt(
        mode=req.mode,
        task_input=req.task_input,
        spec=req.spec,
        codebase_profile=req.codebase_profile,
        feedback=req.feedback,
        previous_tasks=req.previous_tasks,
    )

    response_text = await _lightweight_claude_call(
        prompt, model=req.model, timeout_seconds=300
    )
    return {"task_list": _parse_json_response(response_text)}


@router.post("/api/scan/generate")
async def generate_security_scan(req: ScanRequest):
    """Run a security scan on a codebase and return findings."""
    project_dir = req.project_dir.strip()
    if not project_dir or not Path(project_dir).is_dir():
        raise HTTPException(status_code=400, detail="Valid project_dir is required.")

    template = _load_lightweight_prompt("scanner")
    current_date = datetime.now().strftime("%Y-%m-%d")
    prompt = template.replace("{task_input}", req.task_input.strip()).replace("{current_date}", current_date)

    response_text = await _lightweight_claude_call(
        prompt, model=req.model, cwd=project_dir, timeout_seconds=300
    )
    return {"security_report": _parse_json_response(response_text)}


@router.post("/api/project/prepare")
async def prepare_project(req: PrepareRequest):
    """Write pre-build artifacts to disk so the agent session can skip planning phases."""
    project_dir = Path(req.project_dir.strip())
    if not project_dir.name:
        raise HTTPException(status_code=400, detail="project_dir is required.")

    project_dir.mkdir(parents=True, exist_ok=True)

    paths = get_paths(project_dir)
    paths.ensure_dir()

    if req.task_input:
        paths.task_input.write_text(req.task_input, encoding="utf-8")

    if req.spec:
        paths.app_spec.write_text(req.spec, encoding="utf-8")

    if req.task_list:
        paths.task_list.write_text(
            json.dumps(req.task_list, indent=2), encoding="utf-8"
        )

    if req.codebase_profile:
        paths.codebase_profile.write_text(
            json.dumps(req.codebase_profile, indent=2), encoding="utf-8"
        )

    if req.security_report:
        paths.security_report.write_text(
            json.dumps(req.security_report, indent=2), encoding="utf-8"
        )

    # Git init + initial commit for greenfield projects
    if req.mode == "greenfield" and not (project_dir / ".git").exists():
        git_init = await asyncio.create_subprocess_exec(
            "git", "init",
            cwd=str(project_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await git_init.communicate()

        git_add = await asyncio.create_subprocess_exec(
            "git", "add", "-A",
            cwd=str(project_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await git_add.communicate()

        git_commit = await asyncio.create_subprocess_exec(
            "git", "commit", "-m", "Initial project setup (pre-build artifacts)",
            "--allow-empty",
            cwd=str(project_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await git_commit.communicate()

    return {"status": "ok", "project_dir": str(project_dir)}


@router.post("/api/tasks/sync")
async def sync_tasks(path: str, direction: str = "pull"):
    """Sync tasks with external tracker (GitHub Issues)."""
    from features.task_tracker import SyncManager, SyncStatus
    manager = SyncManager(Path(path))

    if not manager.tracker.is_available():
        raise HTTPException(status_code=400, detail="GitHub CLI not available or not authenticated")

    if direction == "pull":
        result = manager.sync_pull()
    elif direction == "push":
        result = manager.sync_push()
    elif direction == "bidirectional":
        pull_result = manager.sync_pull()
        push_result = manager.sync_push()
        result = SyncStatus(
            direction="bidirectional",
            tasks_pulled=pull_result.tasks_pulled,
            tasks_pushed=push_result.tasks_pushed,
            errors=pull_result.errors + push_result.errors,
            last_synced=datetime.now(timezone.utc).isoformat(),
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid direction")

    return result.to_dict()


@router.get("/api/tasks/sync/status")
async def get_sync_status(path: str):
    """Get current sync status."""
    from features.task_tracker import SyncManager
    manager = SyncManager(Path(path))
    return manager.get_status().to_dict()
