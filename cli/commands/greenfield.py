"""Greenfield mode: Build a new project from a specification file or idea."""

from pathlib import Path
from typing import Optional

import typer

from cli.commands._common import (
    DEFAULT_MODEL,
    ProjectDir,
    Model,
    PhaseModels,
    MaxIterations,
    NoResume,
    CollectApiKeys,
    SkipApiKeys,
    Parallel,
    SmartSwarm,
    Overrides,
    Budget,
    MaxHours,
    ApprovalGates,
    AutoPr,
    Worktree,
    Interactive,
    JsonOutput,
    Server,
    get_task_input,
    run_agent,
)


def greenfield(
    project_dir: ProjectDir,
    spec: Optional[Path] = typer.Option(None, "--spec", help="Path to custom spec file (default: built-in app_spec.txt)"),
    idea: Optional[str] = typer.Option(None, "--idea", help="Brief idea for the app (triggers architect phase to generate spec via web search)"),
    model: Model = DEFAULT_MODEL,
    phase_models: PhaseModels = None,
    max_iterations: MaxIterations = None,
    no_resume: NoResume = False,
    collect_api_keys: CollectApiKeys = False,
    skip_api_keys: SkipApiKeys = False,
    parallel: Parallel = 1,
    smart_swarm: SmartSwarm = False,
    overrides: Overrides = None,
    budget: Budget = 0.0,
    max_hours: MaxHours = 0.0,
    approval_gates: ApprovalGates = False,
    auto_pr: AutoPr = False,
    worktree: Worktree = False,
    interactive: Interactive = False,
    json_output: JsonOutput = False,
    server: Server = None,
):
    """Build a new project from a specification file or a brief idea."""
    task_input = get_task_input("greenfield", spec=spec, idea=idea)
    run_agent(
        project_dir=project_dir,
        mode="greenfield",
        task_input=task_input,
        model=model,
        phase_models_json=phase_models,
        max_iterations=max_iterations,
        no_resume=no_resume,
        collect_api_keys=collect_api_keys,
        skip_api_keys=skip_api_keys,
        parallel=parallel,
        smart_swarm=smart_swarm,
        overrides_json=overrides,
        budget=budget,
        max_hours=max_hours,
        approval_gates=approval_gates,
        auto_pr=auto_pr,
        worktree=worktree,
        spec=spec,
        idea=idea,
        interactive=interactive,
        json_output=json_output,
        server=server,
    )
