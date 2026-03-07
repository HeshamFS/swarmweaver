"""Central model registry for SwarmWeaver.

All model IDs are defined here. Import from this module instead of
hardcoding model strings anywhere else in the codebase.

Users can override the default via:
  - ~/.swarmweaver/config.toml   [cli] default_model = "..."
  - --model flag on any CLI command
  - Settings panel in the Web UI
"""

# ── User-facing default ───────────────────────────────────────────────────────
DEFAULT_MODEL = "claude-sonnet-4-6"
"""Default model for all six operation modes (single agent and swarm workers).
Override with --model or config.toml [cli] default_model.
"""

# ── Specialised role models ───────────────────────────────────────────────────
FAST_MODEL = "claude-haiku-4-5-20251001"
"""Lightweight tasks: QA question generation, quick wizard prompts.
Chosen for speed and low cost; not intended for long agent sessions.
"""

ORCHESTRATOR_MODEL = "claude-opus-4-6"
"""Smart Swarm orchestrator — plans tasks and manages coding workers.
Uses Opus because orchestration requires complex multi-step reasoning.
"""

WORKER_MODEL = "claude-sonnet-4-6"
"""Smart Swarm coding workers — implements tasks in isolated worktrees.
Matches DEFAULT_MODEL today; kept separate so each role is independently tunable.
"""

MERGE_MODEL = "claude-sonnet-4-5-20250929"
"""AI-assisted merge conflict resolution (tier 3/4 of the 4-tier resolver).
Pinned to a specific versioned model ID for deterministic merge behaviour.
"""

# ── Available model catalog (shown in UI and --help) ─────────────────────────
AVAILABLE_MODELS: list[dict] = [
    {
        "id": DEFAULT_MODEL,
        "name": "Claude Sonnet 4.6",
        "description": "Fast, capable model — recommended default",
    },
    {
        "id": ORCHESTRATOR_MODEL,
        "name": "Claude Opus 4.6",
        "description": "Most capable model — best for complex architectures and orchestration",
    },
    {
        "id": "claude-sonnet-4-5-20250929",
        "name": "Claude Sonnet 4.5",
        "description": "Previous generation — stable, well-tested",
    },
    {
        "id": FAST_MODEL,
        "name": "Claude Haiku 4.5",
        "description": "Fastest, most affordable — lightweight tasks",
    },
]
