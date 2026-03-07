"""Pydantic models shared across API routers."""

from typing import Optional
from pydantic import BaseModel

from core.models import DEFAULT_MODEL


class RunRequest(BaseModel):
    mode: str
    project_dir: str
    task_input: str = ""
    spec: Optional[str] = None
    model: str = DEFAULT_MODEL
    max_iterations: Optional[int] = None
    no_resume: bool = False
    parallel: int = 1
    overrides: Optional[list[dict]] = None
    runtime: str = "claude"


class ProjectInfo(BaseModel):
    name: str
    path: str
    has_tasks: bool
    mode: Optional[str] = None
    done: int = 0
    total: int = 0
    percentage: float = 0.0
    last_modified: Optional[str] = None


class NotificationConfigModel(BaseModel):
    enabled: bool = True
    webhook_url: str = ""
    slack_webhook: str = ""
    discord_webhook: str = ""
    notify_on: list[str] = ["task_completed", "all_tasks_done", "error", "agent_stuck"]


class CloneRequest(BaseModel):
    url: str
    target_dir: Optional[str] = None


class CheckpointRestoreRequest(BaseModel):
    path: str
    checkpoint_id: str


class BudgetUpdateRequest(BaseModel):
    path: str
    budget_limit_usd: Optional[float] = None
    max_hours: Optional[float] = None
    max_consecutive_errors: Optional[int] = None


class NudgeRequest(BaseModel):
    path: str
    message: str
    steering_type: str = "instruction"


class TerminateRequest(BaseModel):
    path: str


class QAOption(BaseModel):
    label: str
    description: str = ""


class QAQuestion(BaseModel):
    question: str
    options: list[QAOption]
    context: str = ""


class QARequest(BaseModel):
    mode: str
    task_input: str
    project_dir: str = ""


class QAResponse(BaseModel):
    questions: list[QAQuestion] = []
    skip_reason: str = ""


class ArchitectRequest(BaseModel):
    idea: str
    project_dir: str = ""
    model: str = DEFAULT_MODEL


class AnalyzeRequest(BaseModel):
    mode: str = "feature"
    task_input: str = ""
    project_dir: str
    model: str = DEFAULT_MODEL


class PlanRequest(BaseModel):
    mode: str = "greenfield"
    task_input: str = ""
    spec: Optional[str] = None
    codebase_profile: Optional[dict] = None
    model: str = DEFAULT_MODEL
    feedback: Optional[str] = None
    previous_tasks: Optional[dict] = None


class ScanRequest(BaseModel):
    task_input: str = ""
    project_dir: str
    model: str = DEFAULT_MODEL


class PrepareRequest(BaseModel):
    project_dir: str
    mode: str
    task_input: str = ""
    spec: Optional[str] = None
    task_list: Optional[dict] = None
    codebase_profile: Optional[dict] = None
    security_report: Optional[dict] = None


class ProjectSettingsBody(BaseModel):
    default_model: str = DEFAULT_MODEL
    default_parallel: int = 1
    use_worktree: bool = False
    approval_gates: bool = False
    budget_limit: Optional[float] = None


class GlobalSettingsBody(BaseModel):
    defaultModel: Optional[str] = None
    phaseModels: Optional[dict] = None
    useWorktree: Optional[bool] = None
    approvalGates: Optional[bool] = None
    autoPr: Optional[bool] = None
    budgetLimit: Optional[float] = None
    maxHours: Optional[float] = None
    defaultParallel: Optional[int] = None
    skipQA: Optional[bool] = None
    theme: Optional[str] = None
    defaultBrowsePath: Optional[str] = None


class ApiKeysBody(BaseModel):
    anthropic_api_key: Optional[str] = None
    claude_code_oauth_token: Optional[str] = None
