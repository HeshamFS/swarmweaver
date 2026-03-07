"""Budget and cost tracking endpoints."""

import json
from pathlib import Path

from fastapi import APIRouter, Query

from core.paths import get_paths
from api.models import BudgetUpdateRequest

router = APIRouter()


@router.get("/api/budget")
async def get_budget_status(
    path: str = Query(..., description="Project directory path"),
):
    """Get current budget status from budget_state.json."""
    state_file = get_paths(Path(path)).resolve_read("budget_state.json")
    if state_file.exists():
        try:
            json.loads(state_file.read_text(encoding="utf-8"))
            from state.budget import BudgetTracker
            tracker = BudgetTracker(Path(path))
            return tracker.get_status()
        except (json.JSONDecodeError, OSError, ImportError):
            pass
    return {
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "estimated_cost_usd": 0,
        "budget_limit_usd": 0,
        "budget_remaining_usd": None,
        "max_hours": 0,
        "elapsed_hours": 0,
        "consecutive_errors": 0,
        "session_count": 0,
        "model_usage": {},
        "exceeded": False,
        "exceeded_reason": "",
        "start_time": "",
    }


@router.post("/api/budget/update")
async def update_budget(req: BudgetUpdateRequest):
    """Update budget settings for a project."""
    try:
        from state.budget import BudgetTracker
        tracker = BudgetTracker(Path(req.path))
        if req.budget_limit_usd is not None:
            tracker.state.budget_limit_usd = req.budget_limit_usd
        if req.max_hours is not None:
            tracker.state.max_hours = req.max_hours
        if req.max_consecutive_errors is not None:
            tracker.state.max_consecutive_errors = req.max_consecutive_errors
        tracker.save()
        return {"status": "ok", "budget": tracker.get_status()}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/api/costs")
async def get_costs(
    path: str = Query(..., description="Project directory path"),
):
    """Get total project transcript costs."""
    try:
        from services.transcript_costs import TranscriptCostAnalyzer
        analyzer = TranscriptCostAnalyzer()
        result = analyzer.analyze_project_transcripts(Path(path))
        return result
    except Exception as e:
        return {"total_cost": 0, "error": str(e)}


@router.get("/api/costs/by-agent")
async def get_costs_by_agent(
    path: str = Query(..., description="Project directory path"),
):
    """Get cost breakdown by agent."""
    try:
        from services.transcript_costs import TranscriptCostAnalyzer
        analyzer = TranscriptCostAnalyzer()
        result = analyzer.analyze_project_transcripts(Path(path))
        return {"by_agent": result.get("by_agent", {}), "total_cost": result.get("total_cost", 0)}
    except Exception as e:
        return {"by_agent": {}, "total_cost": 0, "error": str(e)}


@router.get("/api/costs/by-model")
async def get_costs_by_model(
    path: str = Query(..., description="Project directory path"),
):
    """Get cost breakdown by model."""
    try:
        from services.transcript_costs import TranscriptCostAnalyzer
        analyzer = TranscriptCostAnalyzer()
        result = analyzer.analyze_project_transcripts(Path(path))
        return {"by_model": result.get("by_model", {}), "total_cost": result.get("total_cost", 0)}
    except Exception as e:
        return {"by_model": {}, "total_cost": 0, "error": str(e)}
