"""Feature mode: Add features to an existing codebase."""

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


def feature(
    project_dir: ProjectDir,
    description: Optional[str] = typer.Option(None, "--description", help="Natural language description of the features to add"),
    spec: Optional[Path] = typer.Option(None, "--spec", help="Path to a feature specification file"),
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
    """Add features to an existing codebase."""
    if not description and not spec:
        raise typer.BadParameter("Either --description or --spec is required")
    if description and spec:
        raise typer.BadParameter("--description and --spec are mutually exclusive")

    task_input = get_task_input("feature", description=description, spec=spec)
    run_agent(
        project_dir=project_dir,
        mode="feature",
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
        interactive=interactive,
        json_output=json_output,
        server=server,
    )
