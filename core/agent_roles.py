"""
Two-Layer Agent Definitions
==============================

Layer 1 (Base): Markdown files in prompts/agents/ define HOW (workflow, constraints).
Layer 2 (Overlay): Per-task CLAUDE.md generated at spawn time defines WHAT (task, scope).

The overlay is written to each worker's worktree so the agent picks it up
automatically via Claude Code's CLAUDE.md convention.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional


# Available roles and their base definition files
AGENT_ROLES = {
    "builder": "prompts/agents/builder.md",
    "reviewer": "prompts/agents/reviewer.md",
    "scout": "prompts/agents/scout.md",
    "lead": "prompts/agents/lead.md",
    "merger": "prompts/agents/merger.md",
    "orchestrator": "prompts/agents/orchestrator.md",
}

# Path to the overlay template (relative to repo root)
OVERLAY_TEMPLATE_PATH = "templates/overlay.md.tmpl"

# Default role for workers
DEFAULT_ROLE = "builder"


def load_base_definition(role: str) -> str:
    """
    Load the base (Layer 1) definition for an agent role.

    Args:
        role: Agent role name (builder, reviewer, scout)

    Returns:
        Markdown content of the role definition
    """
    if role not in AGENT_ROLES:
        role = DEFAULT_ROLE

    # Resolve relative to the repo root (parent of core/)
    base_path = Path(__file__).parent.parent / AGENT_ROLES[role]

    if base_path.exists():
        return base_path.read_text(encoding="utf-8")

    return f"# {role.title()} Agent\n\nNo base definition found.\n"


def generate_overlay(
    role: str,
    worker_id: int,
    task_ids: list[str],
    file_scope: list[str],
    branch_name: str,
    mode: str = "feature",
    task_input: str = "",
    task_instructions: dict[str, str] | None = None,
    lessons_context: str = "",
) -> str:
    """
    Generate a per-task overlay (Layer 2) for a worker.

    Combines the role's base definition with task-specific context:
    task IDs, file scope, branch, and mode.

    Args:
        role: Agent role (builder, reviewer, scout)
        worker_id: Worker identifier
        task_ids: List of assigned task IDs
        file_scope: Files this worker is allowed to modify
        branch_name: Git branch the worker is on
        mode: Operation mode (feature, fix, etc.)
        task_input: User's task description

    Returns:
        Full CLAUDE.md content (base + overlay)
    """
    base = load_base_definition(role)

    overlay_sections = [
        base,
        "",
        "---",
        "",
        "# Task Assignment (Auto-Generated)",
        "",
        f"**Worker:** worker-{worker_id}",
        f"**Role:** {role}",
        f"**Mode:** {mode}",
        f"**Branch:** {branch_name}",
        f"**Generated:** {datetime.now().isoformat()}",
        "",
    ]

    if task_input:
        overlay_sections.extend([
            "## Objective",
            "",
            task_input,
            "",
        ])

    if task_ids:
        overlay_sections.extend([
            "## Assigned Tasks",
            "",
            f"You are responsible for EXACTLY {len(task_ids)} task(s):",
            "",
        ])
        for tid in task_ids:
            overlay_sections.append(f"- `{tid}`")
        instructions = task_instructions or {}
        if instructions:
            overlay_sections.extend(["", "**Per-task constraints:**"])
            for tid, instr in instructions.items():
                if tid in task_ids:
                    overlay_sections.append(f"- `{tid}`: {instr}")
            overlay_sections.append("")
        overlay_sections.extend([
            "",
            "## Task Management — REQUIRED WORKFLOW",
            "",
            "You have MCP tools that enforce your task scope. USE THEM:",
            "",
            "**Sequence (ONE task at a time):** `get_my_tasks` → for each task: `start_task` → implement "
            "→ `complete_task` → `git commit` → next.",
            "",
            "You MUST NOT edit files for more than one task at a time.",
            "",
            "1. **At session start:** Call `mcp__worker_tools__get_my_tasks` to see your tasks.",
            "   - Do NOT read `.swarmweaver/task_list.json` directly — it has ALL tasks for",
            "     ALL workers and will mislead you into working outside your scope.",
            "2. **Before touching any file:** Call `mcp__worker_tools__start_task` with the task ID.",
            "3. **After finishing a task:** Call `mcp__worker_tools__complete_task` before moving on.",
            "4. **If a task is blocked:** Call `mcp__worker_tools__report_blocker` and optionally "
            "`report_to_orchestrator(blocker, ...)` — then move on.",
            "5. **When all your tasks are done:** STOP. Do not pick up unassigned tasks.",
            "",
            "**Communication:** When blocked, call `report_to_orchestrator(blocker, ...)`. "
            "When you complete a task, you may call `report_to_orchestrator(progress, ...)` "
            "for an immediate update to the orchestrator.",
            "",
            "**Directives:** When a tool is blocked with a [DIRECTIVE FROM ORCHESTRATOR] message, "
            "treat it as a new instruction (not a rejection). Call "
            "`report_to_orchestrator(progress, 'Directive received', 'Acknowledged: <brief summary>')` "
            "immediately, then follow the directive.",
            "",
            "**STRICT TASK SCOPE — THESE ARE HARD RULES:**",
            "",
            "- Process ONLY the task IDs listed above.",
            "- `start_task` / `complete_task` will return an error if you reference any other task ID.",
            "- Do NOT add new tasks or modify `.swarmweaver/task_list.json` directly.",
            "- Do NOT pick up tasks assigned to other workers.",
            "- When all tasks above are marked `done`, your job is complete. Stop.",
            "",
        ])

    if file_scope:
        overlay_sections.extend([
            "## File Scope — HARD LIMIT",
            "",
            "You may ONLY create or modify files in this list:",
            "",
        ])
        for f in file_scope:
            overlay_sections.append(f"- `{f}`")
        overlay_sections.extend([
            "",
            "**DO NOT create, write, or edit ANY file outside this list.**",
            "Even if a task description mentions other files — if they are not in your scope,",
            "skip them and note it in the task's `blocker_reason`.",
            "Other workers are responsible for their own files.",
            "",
        ])
    else:
        overlay_sections.extend([
            "## File Scope",
            "",
            "No specific file scope assigned. Modify only files needed by your assigned tasks.",
            "Do NOT create files for tasks you are not assigned to.",
            "",
        ])

    if lessons_context:
        overlay_sections.extend([
            "## Lessons from Previous Workers",
            "",
            lessons_context,
            "",
        ])

    # Append output formatting guide for structured dashboard output
    output_formatting_path = Path(__file__).parent.parent / "prompts" / "shared" / "output_formatting.md"
    if output_formatting_path.exists():
        overlay_sections.extend([
            "",
            "---",
            "",
            output_formatting_path.read_text(encoding="utf-8"),
        ])

    return "\n".join(overlay_sections)


def write_overlay_to_worktree(
    worktree_path: Path,
    role: str,
    worker_id: int,
    task_ids: list[str],
    file_scope: list[str],
    branch_name: str,
    mode: str = "feature",
    task_input: str = "",
    task_instructions: dict[str, str] | None = None,
    lessons_context: str = "",
) -> Path:
    """
    Generate and write a CLAUDE.md overlay to a worker's worktree.

    Args:
        worktree_path: Path to the worker's worktree directory
        role: Agent role
        worker_id: Worker identifier
        task_ids: Assigned task IDs
        file_scope: Allowed files
        branch_name: Git branch
        mode: Operation mode
        task_input: User's task description
        task_instructions: Optional per-task constraints

    Returns:
        Path to the written CLAUDE.md file
    """
    content = generate_overlay(
        role=role,
        worker_id=worker_id,
        task_ids=task_ids,
        file_scope=file_scope,
        branch_name=branch_name,
        mode=mode,
        task_input=task_input,
        task_instructions=task_instructions,
        lessons_context=lessons_context,
    )

    claude_md = worktree_path / "CLAUDE.md"
    claude_md.write_text(content, encoding="utf-8")
    return claude_md


def assign_role(worker_id: int, task_ids: list[str], total_workers: int) -> str:
    """
    Assign a role to a worker based on its position and task count.

    Heuristic:
    - If total_workers >= 4: second-to-last worker becomes reviewer,
      last worker becomes merger
    - If total_workers >= 3: last worker becomes reviewer
    - All other workers are builders
    - Single worker: builder

    Args:
        worker_id: Worker identifier
        task_ids: Tasks assigned to this worker
        total_workers: Total number of workers in the swarm

    Returns:
        Role name (builder, reviewer, scout, merger)
    """
    if total_workers >= 4 and worker_id == total_workers - 1:
        return "reviewer"
    if total_workers >= 4 and worker_id == total_workers:
        return "merger"
    if total_workers >= 3 and worker_id == total_workers:
        return "reviewer"
    return "builder"


def _load_overlay_template() -> str:
    """Load the overlay template from templates/overlay.md.tmpl."""
    template_path = Path(__file__).parent.parent / OVERLAY_TEMPLATE_PATH
    if template_path.exists():
        return template_path.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Overlay template not found at {template_path}")


def _get_budget_context(project_dir: str) -> str:
    """Read current budget state and format as a human-readable string."""
    try:
        from state.budget import BudgetTracker
        tracker = BudgetTracker(Path(project_dir))
        status = tracker.get_status()
        spent = status.get("estimated_cost_usd", 0)
        limit = status.get("budget_limit_usd", 0)
        elapsed = status.get("elapsed_hours", 0)
        max_h = status.get("max_hours", 0)

        parts = []
        if limit > 0:
            pct = (spent / limit * 100) if limit else 0
            parts.append(f"Spent ${spent:.2f} of ${limit:.2f} ({pct:.0f}%)")
        else:
            parts.append(f"Spent ${spent:.2f} (no budget limit set)")

        if max_h > 0:
            parts.append(f"{elapsed:.1f}h of {max_h:.1f}h elapsed")
        elif elapsed > 0:
            parts.append(f"{elapsed:.1f}h elapsed")

        return " | ".join(parts)
    except Exception:
        return "Budget information unavailable."


def generate_enhanced_overlay(
    role: str,
    agent_name: str,
    task_ids: list[str],
    file_scope: list[str],
    branch_name: str,
    worktree_path: str,
    parent_agent: str = "operator",
    depth: int = 0,
    spec_path: str = "",
    expertise_context: str = "",
    quality_gates: list[str] | None = None,
    constraints: list[str] | None = None,
    budget_context: str = "",
    dispatch_overrides: str = "",
    lessons_context: str = "",
) -> str:
    """
    Generate an enhanced overlay using the template system.

    Loads the Markdown template from templates/overlay.md.tmpl, injects the
    base role definition from prompts/agents/{role}.md, and fills all
    placeholders with task-specific context.

    Args:
        role: Agent role (builder, reviewer, scout, lead)
        agent_name: Unique name for this agent instance (e.g., "builder-1")
        task_ids: List of assigned task IDs
        file_scope: Files/globs this agent may modify
        branch_name: Git branch the agent works on
        worktree_path: Filesystem path to the agent's worktree
        parent_agent: Name of the parent/coordinating agent
        depth: Nesting depth in the agent hierarchy (0 = top-level)
        spec_path: Path to the specification document (if any)
        expertise_context: Domain-specific context to inject
        quality_gates: List of quality gate descriptions
        constraints: Additional constraints beyond role defaults
        budget_context: Pre-formatted budget state string

    Returns:
        Fully rendered CLAUDE.md content ready to write to the worktree
    """
    template = _load_overlay_template()
    base_definition = load_base_definition(role)

    # Format task IDs as a bullet list
    if task_ids:
        task_ids_str = "\n".join(f"- `{tid}`" for tid in task_ids)
    else:
        task_ids_str = "No specific tasks assigned."

    # Format file scope as a bullet list
    if file_scope:
        file_scope_str = "\n".join(f"- `{f}`" for f in file_scope)
    else:
        file_scope_str = "No specific file scope assigned. You may modify files as needed for your tasks."

    # Format quality gates
    if quality_gates:
        quality_gates_str = "\n".join(f"- {gate}" for gate in quality_gates)
    else:
        quality_gates_str = "- All relevant tests pass\n- No lint errors\n- Code follows project conventions"

    # Format constraints
    if constraints:
        constraints_str = "\n".join(f"- {c}" for c in constraints)
    else:
        constraints_str = "No additional constraints beyond the role defaults above."

    # Resolve budget context from project dir if not explicitly provided
    if not budget_context:
        budget_context = _get_budget_context(worktree_path)

    # Enrich expertise_context with MELS priming engine (project-local store)
    try:
        from services.expertise_priming import PrimingEngine
        from services.expertise_store import get_project_store
        project_dir = Path(worktree_path)
        engine = PrimingEngine()
        proj_store = get_project_store(project_dir)
        primed = engine.prime(
            proj_store,
            file_scope=file_scope or [],
            domains=None,
            task_description=task_description if 'task_description' in dir() else "",
            budget_tokens=1500,
        )
        if primed:
            if expertise_context:
                expertise_context = expertise_context + "\n\n" + primed
            else:
                expertise_context = primed
    except Exception:
        pass  # Non-fatal: MELS priming not available

    # Fill all placeholders
    rendered = template
    rendered = rendered.replace("{{AGENT_NAME}}", agent_name)
    rendered = rendered.replace("{{TASK_IDS}}", task_ids_str)
    rendered = rendered.replace("{{FILE_SCOPE}}", file_scope_str)
    rendered = rendered.replace("{{BRANCH_NAME}}", branch_name)
    rendered = rendered.replace("{{WORKTREE_PATH}}", worktree_path)
    rendered = rendered.replace("{{PARENT_AGENT}}", parent_agent)
    rendered = rendered.replace("{{DEPTH}}", str(depth))
    rendered = rendered.replace("{{SPEC_PATH}}", spec_path or "No spec file assigned.")
    rendered = rendered.replace("{{EXPERTISE_CONTEXT}}", expertise_context or "No additional expertise context.")
    rendered = rendered.replace("{{QUALITY_GATES}}", quality_gates_str)
    rendered = rendered.replace("{{CONSTRAINTS}}", constraints_str)
    rendered = rendered.replace("{{BUDGET_CONTEXT}}", budget_context)
    rendered = rendered.replace("{{DISPATCH_OVERRIDES}}", dispatch_overrides or "No dispatch overrides active.")
    rendered = rendered.replace("{{LESSONS_CONTEXT}}", lessons_context or "No lessons yet — you are the first worker.")
    rendered = rendered.replace("{{BASE_DEFINITION}}", base_definition)

    # Output formatting guide for structured dashboard output
    output_formatting_path = Path(__file__).parent.parent / "prompts" / "shared" / "output_formatting.md"
    output_formatting = ""
    if output_formatting_path.exists():
        output_formatting = "\n\n---\n\n" + output_formatting_path.read_text(encoding="utf-8")
    rendered = rendered.replace("{{OUTPUT_FORMATTING}}", output_formatting)

    return rendered


def write_enhanced_overlay_to_worktree(
    worktree_path: Path,
    role: str,
    agent_name: str,
    task_ids: list[str],
    file_scope: list[str],
    branch_name: str,
    parent_agent: str = "operator",
    depth: int = 0,
    spec_path: str = "",
    expertise_context: str = "",
    quality_gates: list[str] | None = None,
    constraints: list[str] | None = None,
    budget_context: str = "",
    dispatch_overrides: str = "",
    lessons_context: str = "",
) -> Path:
    """
    Generate an enhanced overlay and write it to {worktree}/.claude/CLAUDE.md.

    Also deploys capability enforcement hooks alongside the overlay.

    Args:
        worktree_path: Path to the worker's worktree directory
        role: Agent role
        agent_name: Unique agent name
        task_ids: Assigned task IDs
        file_scope: Allowed file patterns
        branch_name: Git branch
        parent_agent: Parent agent name
        depth: Hierarchy depth
        spec_path: Spec document path
        expertise_context: Domain context
        quality_gates: Quality gate descriptions
        constraints: Additional constraints
        budget_context: Pre-formatted budget state string
        dispatch_overrides: Pre-formatted dispatch overrides text

    Returns:
        Path to the written CLAUDE.md file
    """
    content = generate_enhanced_overlay(
        role=role,
        agent_name=agent_name,
        task_ids=task_ids,
        file_scope=file_scope,
        branch_name=branch_name,
        worktree_path=str(worktree_path),
        parent_agent=parent_agent,
        depth=depth,
        spec_path=spec_path,
        expertise_context=expertise_context,
        quality_gates=quality_gates,
        constraints=constraints,
        budget_context=budget_context,
        dispatch_overrides=dispatch_overrides,
        lessons_context=lessons_context,
    )

    # Write to {worktree}/.claude/CLAUDE.md
    claude_dir = worktree_path / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)

    claude_md = claude_dir / "CLAUDE.md"
    claude_md.write_text(content, encoding="utf-8")

    # Deploy capability hooks alongside the overlay
    try:
        from hooks.capability_hooks import deploy_hooks_to_worktree
        deploy_hooks_to_worktree(worktree_path, role, file_scope)
    except ImportError:
        pass  # capability_hooks not available yet

    return claude_md
