# Repository Guidelines

> **For AI tools:** AGENTS.md provides concise agent context. For detailed architecture, prompts, hooks, and API reference, see [CLAUDE.md](CLAUDE.md).

## Repository Purpose, Mission & Vision

- **Purpose:** SwarmWeaver is an autonomous engineering platform that turns specs and goals into code through a CLI and a web command center.
- **Mission:** Accelerate delivery while keeping humans in control through approval gates, verification loops, security allowlists, and auditability.
- **Vision:** A reliable long-running orchestrator for planning, building, verifying, and coordinating multi-agent software work.

## Entry Points

| Entry Point | Purpose |
|-------------|---------|
| `cli/main.py` | CLI package — Typer app with all subcommands (`swarmweaver` entry point) |
| `api/app.py` | FastAPI app factory — REST API and WebSocket handlers |
| `dev.mjs` | Dev launcher — runs `uv sync`, installs frontend deps, starts FastAPI + Next.js |
| `autonomous_agent_demo.py` | Legacy CLI shim → delegates to `cli/main.py` |
| `server.py` | Legacy API shim → delegates to `api/app.py` |

## Common Edit Hotspots

| Change Type | Primary Location |
|-------------|------------------|
| Prompts (per mode / agent role) | `prompts/` (shared/, greenfield/, feature/, refactor/, fix/, evolve/, security/, agents/) |
| Hooks (security, capability, marathon, heartbeat) | `hooks/` (security.py, capability_hooks.py, main_hooks.py, marathon_hooks.py) |
| Agent loop, orchestrators, merge | `core/` (agent.py, engine.py, orchestrator.py, smart_orchestrator.py, merge_resolver.py) |
| Watchdog health monitoring | `services/watchdog.py` (state machine, AI triage, circuit breaker, event store) |
| LSP code intelligence | `services/lsp_client.py`, `lsp_manager.py`, `lsp_intelligence.py`, `lsp_tools.py`, `hooks/lsp_hooks.py` |
| State persistence (tasks, sessions, budget) | `state/` (task_list.py, session_state.py, budget.py, mail.py, events.py) |
| Mode capabilities (steering, memory, verification) | `features/` (steering.py, memory.py, verification.py, approval.py) |
| API endpoints and models | `api/` (routers/, models.py, app.py) |
| Web UI components | `frontend/app/components/` |

## Project Structure & Module Organization

- `cli/` is the CLI package; `autonomous_agent_demo.py` is a backward-compatible shim.
- `api/` is the FastAPI package; `server.py` is a backward-compatible shim.
- Backend logic is split into `cli/` (CLI commands), `api/` (FastAPI), `core/` (orchestration), `features/` (mode capabilities), `services/` (helpers), `state/` (persistence), `hooks/` (policy), and `utils/`.
- `core/engine.py` — Execution engine (single-agent runs with SDK streaming).
- `core/orchestrator.py` — SwarmOrchestrator (static N workers, worktree setup).
- `core/smart_orchestrator.py` — SmartOrchestrator (AI-orchestrated dynamic workers).
- `core/merge_resolver.py` — 4-tier merge conflict resolution (clean → auto → AI → reimagine).
- `core/merge_queue.py` — SQLite FIFO merge queue for swarm branch merges.
- `services/watchdog.py` — SwarmWatchdog: 9-state machine, 6-signal health evaluation, AI triage, circuit breaker, heartbeat protocol, persistent SQLite event log.
- `frontend/` is a Next.js 15 app (`app/components`, `app/hooks`, `app/utils`).
- `prompts/` holds mode and role templates; `templates/` holds starter specs; `tests/` holds Python regression tests.

## Execution Paths

- **Single agent**: `Engine` runs one Claude SDK session with phase loop.
- **Static swarm** (`--parallel N`): `Swarm` + `SwarmOrchestrator` — N workers in isolated git worktrees.
- **Smart swarm** (`--smart-swarm`): `SmartSwarm` + `SmartOrchestrator` — AI decides worker count and task assignment; planning with single Engine, then dynamic worker spawning.

## Capabilities Summary

- Six operation modes: greenfield, feature, refactor, fix, evolve, security
- Git worktree isolation (merge or discard on completion)
- Multi-agent swarm (static N or AI-orchestrated Smart Swarm) with inter-agent mail coordination
- Enhanced watchdog health monitoring: 9-state forward-only state machine, 7-signal health evaluation (including LSP diagnostic trend), active heartbeat protocol, LLM-based AI triage with heuristic fallback, dependency-aware escalation, circuit breaker, per-worker resource monitoring, persistent SQLite event log, YAML-configurable thresholds (`swarmweaver watchdog` CLI)
- Native LSP code intelligence: 22 built-in language servers (auto-detect/install), per-worktree isolation, post-edit diagnostic injection, cross-worker diagnostic routing via mail, impact analysis, unused code detection, dependency graph, code health score, 13 REST endpoints, 5 CLI commands (`swarmweaver lsp`)
- Approval gates, verification loop, security allowlist
- Cross-project memory, budget tracking, cost analysis
- Inter-agent mail system: typed payloads, context injection, attachments, dead letter queue, analytics (`swarmweaver mail` CLI)
- User-configurable MCP servers (global + per-project) with built-in puppeteer and web search
- Chat wizard flow with streaming (QA, architect, plan, security review)
- 4-tier merge conflict resolution for swarm

## Build, Test, and Development Commands

- `uv sync` — create `.venv` and install all dependencies (makes `swarmweaver` CLI available).
- `swarmweaver --help` — list all CLI subcommands and flags.
- `./setup.sh` — install uv if missing, then run `uv sync` (Unix only).
- `npm run dev` — full local stack (dependency checks + FastAPI on `:8000` + Next.js on `:3000`).
- `npm run build` — build the frontend for production.
- `npm --prefix frontend run lint` — run frontend lint checks.
- `pytest tests -q` — run backend test suite.
- `pytest tests/test_watchdog_enhanced.py -v` — run watchdog health monitoring tests (60 tests).
- `pytest tests/test_lsp.py -v` — run LSP code intelligence tests (82 tests).
- `python tests/test_security.py` — run command-allowlist/security hook regression checks.

## Coding Style & Naming Conventions

- Python: 4-space indentation, `snake_case` modules/functions, `PascalCase` classes, and type hints on new or changed logic.
- React/TypeScript: `PascalCase` component files, hooks prefixed with `use`, and keep UI logic close to feature components.
- Prefer small, composable changes; extend existing `services/` and `utils/` before creating new abstractions.

## Testing Guidelines

- Use `pytest` for backend coverage and regressions.
- Follow naming patterns: files `tests/test_<area>.py`, functions `test_<behavior>()`.
- Add tests near affected areas (for example, `hooks/security.py` changes should update `tests/test_security.py`).

## Commit & Pull Request Guidelines

- Follow commit style used in history: `feat:`, `fix:`, `docs:` with imperative, specific summaries.
- Keep each commit scoped to one logical change.
- PRs should include purpose, key implementation notes, test commands/results, and screenshots for `frontend/` updates.

## Security, Configuration & Agent Context

- Copy `.env.example` to `.env`; never commit secrets.
- Respect `.gitignore` boundaries for generated artifacts (`generations/`, `logs/`, `venv/`, `node_modules/`, `.next/`).
- If command policy changes are needed, update `hooks/security.py` and include matching tests.
- Preserve human-in-the-loop behavior (approval gates, verification status, and security review paths) when implementing features.
