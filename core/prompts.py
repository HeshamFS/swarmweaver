"""
Prompt Loading Utilities - Multi-Mode
======================================

Dynamic prompt building for multiple operation modes:
- greenfield: Build from spec
- feature: Add features to existing project
- refactor: Restructure or migrate codebase
- fix: Diagnose and fix bugs
- evolve: Open-ended improvement

Each mode has phases (analyze → plan → execute), and prompts are
assembled from shared templates + mode-specific templates.
"""

import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.paths import get_paths


PROJECT_ROOT = Path(__file__).parent.parent
PROMPTS_DIR = PROJECT_ROOT / "prompts"

# Phase definitions for each mode
# Each mode has an ordered list of phases.
# Phases marked with "*" are looping phases (repeat until tasks are done).
MODE_PHASES = {
    "greenfield": ["initialize", "code*"],
    "greenfield_from_idea": ["architect", "initialize", "code*"],
    "feature": ["analyze", "plan", "implement*"],
    "refactor": ["analyze", "plan", "migrate*"],
    "fix": ["investigate", "fix*"],
    "evolve": ["audit", "improve*"],
    "security": ["scan", "remediate*"],
}

# Map from (mode, phase) to prompt template file
PHASE_PROMPT_MAP = {
    # Greenfield mode
    ("greenfield", "architect"): "greenfield/architect.md",
    ("greenfield", "initialize"): "greenfield/initializer.md",
    ("greenfield", "code"): "greenfield/coding.md",
    # Greenfield swarm workers — use MCP tools instead of editing task_list.json
    ("greenfield_swarm", "architect"): "greenfield/architect.md",
    ("greenfield_swarm", "initialize"): "greenfield/initializer.md",
    ("greenfield_swarm", "code"): "greenfield/coding_swarm.md",
    # Greenfield from idea (same prompts, different phase sequence)
    ("greenfield_from_idea", "architect"): "greenfield/architect.md",
    ("greenfield_from_idea", "initialize"): "greenfield/initializer.md",
    ("greenfield_from_idea", "code"): "greenfield/coding.md",
    ("greenfield_from_idea_swarm", "architect"): "greenfield/architect.md",
    ("greenfield_from_idea_swarm", "initialize"): "greenfield/initializer.md",
    ("greenfield_from_idea_swarm", "code"): "greenfield/coding_swarm.md",
    # Feature mode
    ("feature", "analyze"): "feature/analyzer.md",
    ("feature", "plan"): "feature/planner.md",
    ("feature", "implement"): "feature/implementer.md",
    ("feature_swarm", "analyze"): "feature/analyzer.md",
    ("feature_swarm", "plan"): "feature/planner.md",
    ("feature_swarm", "implement"): "feature/implementer_swarm.md",
    # Refactor mode (no swarm variant yet — falls back to normal)
    ("refactor", "analyze"): "refactor/analyzer.md",
    ("refactor", "plan"): "refactor/planner.md",
    ("refactor", "migrate"): "refactor/migrator.md",
    # Fix mode
    ("fix", "investigate"): "fix/investigator.md",
    ("fix", "fix"): "fix/fixer.md",
    # Evolve mode
    ("evolve", "audit"): "evolve/auditor.md",
    ("evolve", "improve"): "evolve/improver.md",
    # Security mode
    ("security", "scan"): "security/scanner.md",
    ("security", "remediate"): "security/remediator.md",
}


def load_raw_prompt(relative_path: str) -> str:
    """Load a raw prompt template from a relative path under prompts/."""
    prompt_path = PROMPTS_DIR / relative_path
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt template not found: {prompt_path}")
    return prompt_path.read_text(encoding="utf-8")


def _load_shared_templates() -> dict[str, str]:
    """Load all shared template fragments."""
    shared = {}
    shared_dir = PROMPTS_DIR / "shared"
    if shared_dir.exists():
        for f in shared_dir.glob("*.md"):
            key = f"shared_{f.stem}"
            shared[key] = f.read_text(encoding="utf-8")
    return shared


def build_prompt(
    mode: str,
    phase: str,
    task_input: str = "",
    task_input_short: str = "",
    project_dir: Optional[Path] = None,
    use_worker_tools: bool = False,
) -> str:
    """
    Build a prompt for the given mode and phase.

    Args:
        mode: Operation mode (greenfield, feature, refactor, fix, evolve)
        phase: Current phase (e.g., "analyze", "plan", "implement")
        task_input: The user's task description/spec/goal (injected into prompt)
        task_input_short: Short version for metadata fields
        project_dir: Project directory (for path references)
        use_worker_tools: If True, use swarm-specific prompts (MCP workflow) for
            execution phases when a variant exists (greenfield/feature).

    Returns:
        Assembled prompt string
    """
    # Strip the loop marker from phase name
    clean_phase = phase.rstrip("*")

    # When swarm worker: prefer swarm template for execution phases
    lookup_mode = mode
    if use_worker_tools:
        swarm_mode = f"{mode}_swarm" if not mode.endswith("_swarm") else mode
        if (swarm_mode, clean_phase) in PHASE_PROMPT_MAP:
            lookup_mode = swarm_mode

    # Look up the template file
    key = (lookup_mode, clean_phase)
    if key not in PHASE_PROMPT_MAP:
        raise ValueError(f"No prompt template for mode={lookup_mode}, phase={clean_phase}")

    template_path = PHASE_PROMPT_MAP[key]
    template = load_raw_prompt(template_path)

    # Load shared templates
    shared = _load_shared_templates()

    # Build context for template substitution
    context = {
        **shared,
        "task_input": task_input or "(No task input provided)",
        "task_input_short": task_input_short or task_input[:80] if task_input else "",
        "timestamp": datetime.now().isoformat(),
        "current_date": datetime.now().strftime("%B %d, %Y"),
        "project_dir": str(project_dir) if project_dir else ".",
        "context_prime": "",   # Populated by agent.py with ContextPrimer
        "agent_memory": "",    # Populated via MELS PrimingEngine
    }

    # Load expertise context via MELS
    if project_dir:
        try:
            from services.expertise_priming import PrimingEngine
            from services.expertise_store import get_cross_project_store
            engine = PrimingEngine()
            store = get_cross_project_store()
            memory_context = engine.prime(
                store, file_scope=[], domains=None,
                task_description=task_input or "",
            )
            if memory_context:
                context["agent_memory"] = memory_context
        except Exception:
            pass

    # Load plugin prompt fragments if available
    if project_dir:
        try:
            from features.plugins import PluginLoader
            loader = PluginLoader(project_dir=project_dir)
            loader.load_config()
            fragments = loader.get_prompt_fragments(mode=mode, phase=clean_phase)
            if fragments:
                context["plugin_prompts"] = "\n\n".join(fragments)
        except Exception:
            pass

    # Substitute placeholders
    # Use a safe approach: only replace known {placeholders}
    prompt = template
    for key, value in context.items():
        placeholder = "{" + key + "}"
        prompt = prompt.replace(placeholder, value)

    # Append plugin prompts if any
    plugin_prompts = context.get("plugin_prompts", "")
    if plugin_prompts:
        prompt += f"\n\n{plugin_prompts}"

    return prompt


def get_phases(mode: str) -> list[str]:
    """
    Get the ordered list of phases for a mode.

    Returns phase names. Phases ending with '*' are looping phases.
    """
    if mode not in MODE_PHASES:
        raise ValueError(f"Unknown mode: {mode}. Valid modes: {list(MODE_PHASES.keys())}")
    return MODE_PHASES[mode]


def is_looping_phase(phase: str) -> bool:
    """Check if a phase is a looping phase (repeats until tasks done)."""
    return phase.endswith("*")


def get_available_modes() -> list[str]:
    """Return list of all available operation modes."""
    return list(MODE_PHASES.keys())


def copy_spec_to_project(project_dir: Path, spec_file: Optional[Path] = None) -> None:
    """
    Copy a spec file into the project directory for the agent to read.

    Args:
        project_dir: Target project directory
        spec_file: Custom spec file path. If None, uses the default app_spec.txt.
    """
    if spec_file:
        # Custom spec provided
        spec_source = Path(spec_file)
        if not spec_source.exists():
            raise FileNotFoundError(f"Spec file not found: {spec_file}")
    else:
        # Default spec
        spec_source = PROMPTS_DIR / "app_spec.txt"
        if not spec_source.exists():
            print("No default app_spec.txt found. Skipping spec copy.")
            return

    paths = get_paths(project_dir)
    paths.ensure_dir()
    spec_dest = paths.app_spec
    if not spec_dest.exists():
        shutil.copy(spec_source, spec_dest)
        print(f"Copied spec to project: {spec_source.name} -> .swarmweaver/app_spec.txt")

    # Also copy the docs folder for reference documentation
    copy_docs_to_project(project_dir)


def copy_docs_to_project(project_dir: Path) -> None:
    """Copy the docs folder into the project directory for the agent to read."""
    docs_source = PROJECT_ROOT / "docs"
    docs_dest = project_dir / "docs"

    if not docs_source.exists():
        return

    # Create docs directory if it doesn't exist
    docs_dest.mkdir(parents=True, exist_ok=True)

    # Copy each file in the docs folder
    copied_count = 0
    for doc_file in docs_source.iterdir():
        if doc_file.is_file():
            dest_file = docs_dest / doc_file.name
            if not dest_file.exists():
                shutil.copy(doc_file, dest_file)
                copied_count += 1

    if copied_count > 0:
        print(f"Copied {copied_count} documentation files to project docs/ folder")


def write_task_input(project_dir: Path, task_input: str) -> None:
    """
    Write the task input (description/goal/issue) to the project directory
    so the agent can read it.
    """
    paths = get_paths(project_dir)
    paths.ensure_dir()
    task_input_file = paths.task_input
    task_input_file.write_text(task_input, encoding="utf-8")
    print(f"Wrote task input to {task_input_file}")
