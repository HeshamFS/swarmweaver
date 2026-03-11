# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Reference

| Need | Command / Path |
|------|----------------|
| Install deps | `pip install -e .` or `uv sync` |
| Start dev stack | `npm run dev` |
| Run a mode | `swarmweaver feature --project-dir ./app --description "..."` |
| Auth | `.env` with `CLAUDE_CODE_OAUTH_TOKEN` or `ANTHROPIC_API_KEY` |
| Artifacts | `.swarmweaver/` (task_list.json, session_state.json, etc.) |
| Security tests | `python tests/test_security.py` |

### When to Edit What

| Change Type | Location |
|-------------|----------|
| Prompts (modes, roles) | `prompts/` |
| Hooks (security, capability, marathon) | `hooks/` |
| Agent loop, orchestrators | `core/` |
| State (tasks, sessions, budget) | `state/` |
| Mode capabilities | `features/` |
| API endpoints | `api/routers/` |
| Web UI | `frontend/app/components/` |

## Project Overview

This is an **Autonomous Coding Agent** (SwarmWeaver) - a Python harness that uses the Claude Agent SDK to run long-running autonomous coding sessions. It supports **six operation modes**:

| Mode | Use Case |
|------|----------|
| `greenfield` | Build a new project from a specification file |
| `feature` | Add features to an existing codebase |
| `refactor` | Restructure or migrate an existing codebase (e.g., JS to TS, C++ to Rust) |
| `fix` | Diagnose and fix bugs in an existing project |
| `evolve` | Open-ended improvement (add tests, make production-ready, improve performance) |
| `security` | Scan for vulnerabilities with human-in-the-loop review before remediation |

## Commands

```bash
# Install deps + register `swarmweaver` CLI
pip install -e .          # globally available
# or: uv sync            # installs inside .venv (use 'uv run swarmweaver' or activate .venv)

# Start Web UI (frontend + backend)
npm run dev

# Greenfield: Build new project from spec
swarmweaver greenfield --project-dir ./my_app --spec ./my_spec.txt

# Greenfield: Use built-in default spec
swarmweaver greenfield --project-dir ./my_app

# Feature: Add features to existing project
swarmweaver feature --project-dir ./existing_app --description "Add OAuth2 login"

# Feature: From spec file
swarmweaver feature --project-dir ./existing_app --spec ./feature_spec.txt

# Refactor: Migrate or restructure
swarmweaver refactor --project-dir ./existing_app --goal "Migrate from JavaScript to TypeScript"

# Fix: Diagnose and fix bugs
swarmweaver fix --project-dir ./existing_app --issue "Login fails with plus sign in email"

# Evolve: Improve codebase
swarmweaver evolve --project-dir ./existing_app --goal "Add unit tests for 80% coverage"

# Security: Scan and remediate vulnerabilities (human-in-the-loop)
swarmweaver security --project-dir ./existing_app --focus "Full security audit"

# Worktree mode: Run in isolated git worktree (changes can be merged or discarded)
swarmweaver feature --project-dir ./my_app --description "Add OAuth2" --worktree

# Multi-agent swarm mode (parallel workers)
swarmweaver feature --project-dir ./my_app --description "Add dashboard" --parallel 3

# Smart Swarm mode (AI-orchestrated dynamic workers)
swarmweaver feature --project-dir ./my_app --description "Add dashboard" --smart-swarm

# Common options (all modes)
swarmweaver feature --project-dir ./app --description "..." --max-iterations 5
swarmweaver feature --project-dir ./app --description "..." --model claude-sonnet-4-6
swarmweaver feature --project-dir ./app --description "..." --no-resume

# MCP server management
swarmweaver mcp list                              # list all configured MCP servers
swarmweaver mcp add NAME --command "CMD"          # add a new MCP server
swarmweaver mcp remove NAME                       # remove an MCP server
swarmweaver mcp enable NAME                       # enable a server
swarmweaver mcp disable NAME                      # disable a server
swarmweaver mcp test NAME                         # test server connectivity

# Watchdog health monitoring
swarmweaver watchdog status  -p DIR               # fleet score, worker states, circuit breaker
swarmweaver watchdog events  -p DIR               # recent watchdog events
swarmweaver watchdog config  -p DIR               # show or edit watchdog.yaml
swarmweaver watchdog triage  WORKER_ID -p DIR     # trigger AI triage
swarmweaver watchdog nudge   WORKER_ID -p DIR     # send nudge to a worker

# LSP code intelligence
swarmweaver lsp status       -p DIR               # show running language servers
swarmweaver lsp diagnostics  -p DIR [-s SEVERITY] [-f PATH] [-n LIMIT]
swarmweaver lsp servers      -p DIR               # list all 22 available server specs
swarmweaver lsp config       -p DIR [--set KEY=VALUE]
swarmweaver lsp restart      [SERVER_ID] -p DIR   # restart language servers

# Legacy shim (backward compatible — calls cli/main.py internally)
python autonomous_agent_demo.py feature --project-dir ./app --description "..."

# Run security hook tests
python tests/test_security.py
```

## Authentication

Set one of these environment variables (copy `.env.example` to `.env`):
- `CLAUDE_CODE_OAUTH_TOKEN` - For Claude Code Max subscription (run `claude setup-token` to generate)
- `ANTHROPIC_API_KEY` - For API usage

## Architecture

### Package Structure

```
swarmweaver/                  # Project root (SwarmWeaver)
├── cli/                        # CLI package — entry point: `swarmweaver` (pyproject.toml scripts)
│   ├── main.py                   # Typer app with all subcommands
│   ├── commands/                 # One module per subcommand (incl. mcp.py for MCP server management)
│   ├── client.py                 # HTTP client for connected mode (SWARMWEAVER_URL)
│   ├── config.py                 # ~/.swarmweaver/config.toml loader
│   ├── output.py                 # Rich / JSON output formatters
│   └── wizard.py                 # Interactive wizard flow
├── api/                        # FastAPI package — app factory, routers, WebSocket
│   ├── app.py                    # FastAPI app factory
│   ├── routers/                  # One router per domain (tasks, swarm, worktree, mcp, sessions, snapshots, …)
│   ├── websocket/                # WebSocket stream handlers
│   ├── helpers.py                # Shared request/response helpers
│   ├── models.py                 # Pydantic request/response models
│   └── state.py                  # App-level state (run registry, etc.)
├── autonomous_agent_demo.py   # Backward-compatible shim → cli/main.py
├── server.py                   # Backward-compatible shim → api/app.py
├── web_search_server.py        # MCP server (standalone)
├── core/                       # Agent loop, client, engine, orchestrator, merge, swarm, worktree
│   ├── agent.py                  # Multi-phase session loop with MELS expertise harvesting
│   ├── agent_roles.py            # Two-layer agent role system with overlay generation
│   ├── client.py                 # Claude SDK client with security, MCP, hooks
│   ├── engine.py                 # Execution engine (single-agent runs, SDK streaming)
│   ├── orchestrator.py          # SwarmOrchestrator (static N workers, worktree setup)
│   ├── smart_orchestrator.py     # SmartOrchestrator (AI-orchestrated dynamic workers)
│   ├── merge_resolver.py         # 4-tier merge conflict resolution (clean → auto → AI → reimagine)
│   ├── merge_queue.py            # SQLite merge queue for swarm branch merges
│   ├── orchestrator_tools.py     # MCP tools for SmartOrchestrator
│   ├── worker_tools.py           # MCP tools for swarm workers (task scope, report_to_orchestrator)
│   ├── paths.py                  # Centralized artifact paths (all under .swarmweaver/)
│   ├── prompts.py                # Dynamic prompt builder (shared + per-mode templates)
│   ├── swarm.py                  # Swarm + SmartSwarm (Engine, SwarmOrchestrator, SmartOrchestrator)
│   └── worktree.py               # Git worktree utilities (create/merge/discard/status)
├── hooks/                      # Security, management, marathon, capability hooks
│   ├── __init__.py               # Re-exports all hooks
│   ├── main_hooks.py             # Server/env/file mgmt, steering, audit, cleanup
│   ├── marathon_hooks.py         # Auto-commit, health, loop detection, stats, resources, heartbeat
│   ├── capability_hooks.py       # Role-based capability enforcement per agent type
│   ├── lsp_hooks.py              # Post-edit LSP diagnostics, cross-worker routing, watchdog signal
│   └── security.py               # Bash command allowlist validation
├── state/                      # Task list, sessions, processes, budget, mail, events
│   ├── task_list.py              # Universal task list with dependencies and verification
│   ├── session_state.py          # Session ID tracking and resumption
│   ├── sessions.py               # Persistent session DB (SessionStore + GlobalSessionIndex, SQLite WAL)
│   ├── snapshots.py              # Shadow git snapshot system (SnapshotManager, capture/diff/restore/revert)
│   ├── checkpoints.py            # File state checkpoints for rollback
│   ├── session_checkpoint.py     # Session chain entries with snapshot hashes
│   ├── process_registry.py       # Background process tracking (PID, port, type)
│   ├── agent_identity.py         # Agent identity store (name, role, success rate, CV)
│   ├── budget.py                 # Cost tracking and circuit breakers
│   ├── mail.py                   # Inter-agent MailStore (SQLite; typed payloads, attachments, analytics, dead letters)
│   └── events.py                 # EventStore (SQLite; tool calls, sessions, errors)
├── features/                   # Steering, approval, GitHub, plugins, spec workflow
│   ├── steering.py               # Interactive mid-session steering
│   ├── approval.py               # Task approval gates
│   ├── verification.py           # Self-healing test verification loop
│   ├── plugins.py                # Plugin system for custom hooks
│   ├── github_integration.py     # GitHub PR automation
│   ├── notifications.py          # Slack, Discord, generic webhook notifications
│   ├── context_primer.py         # Smart context injection (uses MELS PrimingEngine)
│   ├── spec_workflow.py          # Spec-driven task workflow (create/read/list)
│   └── task_tracker.py           # External task sync (GitHub Issues, Jira; abstract interface)
├── services/                   # Events, templates, ADR, replay, insights, timeline, costs, monitor, watchdog, MELS
│   ├── events.py                 # Structured event parser
│   ├── insights.py               # Session insight analyzer
│   ├── expertise_models.py       # MELS data models (10 record types, domain taxonomy, scoring)
│   ├── expertise_store.py        # MELS SQLite store (CRUD, search, governance, session lessons)
│   ├── expertise_scoring.py      # MELS confidence, decay, priming score
│   ├── expertise_priming.py      # MELS token-budget-aware priming engine
│   ├── expertise_synthesis.py    # MELS real-time session lesson synthesis
│   ├── expertise_migration.py    # MELS migration from legacy JSON formats
│   ├── templates.py              # Project template registry
│   ├── schemas.py                # Pydantic models for structured output
│   ├── subagents.py              # Subagent definitions (test-runner, reviewer, verifier, debugger)
│   ├── adr.py                    # Architecture Decision Record manager
│   ├── replay.py                 # Session replay via git commit history
│   ├── monitor.py                # Fleet health monitor
│   ├── watchdog.py               # SwarmWatchdog: 9-state machine, 7-signal health, AI triage, circuit breaker, SQLite event log
│   ├── timeline.py               # Cross-agent event timeline
│   ├── mcp_manager.py            # MCP server config store (two-level merge, CRUD, validate, test)
│   ├── lsp_client.py             # JSON-RPC 2.0 LSP client (14 operations, Content-Length framing)
│   ├── lsp_manager.py            # 22 built-in language servers, lifecycle, auto-detect/install
│   ├── lsp_intelligence.py       # Impact analysis, unused code, dependency graph, health score
│   ├── lsp_tools.py              # Worker MCP tools (lsp_query, lsp_diagnostics_summary)
│   ├── transcript_costs.py       # Transcript-based cost analysis
│   └── logger.py                 # Structured logging
├── utils/                      # API keys, progress, sanitizer, safe logging
│   ├── api_keys.py               # API key collection and validation
│   ├── progress.py               # Progress dashboard
│   ├── sanitizer.py              # Secret sanitizer (redacts API keys, tokens, passwords)
│   └── safe_logging.py           # Fire-and-forget logging
├── tests/                      # Test suite
├── scripts/                    # Standalone cleanup utilities
├── prompts/                    # Prompt templates (shared + per-mode + agent roles)
│   ├── shared/                   # Shared across all modes
│   ├── greenfield/               # Build from spec
│   ├── feature/                  # Add to existing codebase
│   ├── refactor/                 # Restructure/migrate
│   ├── fix/                      # Bug fixing
│   ├── evolve/                   # Improvement
│   ├── security/                 # Vulnerability scanning (isolated prompts)
│   └── agents/                   # Two-layer agent role definitions
│       ├── scout.md                # Read-only exploration
│       ├── builder.md              # Scoped implementation
│       ├── reviewer.md             # Code review (read-only)
│       ├── lead.md                 # Task coordination
│       └── orchestrator.md         # AI-orchestrated worker management (Smart Swarm)
├── templates/                  # Project templates + overlay template
│   └── overlay.md.tmpl           # Agent overlay prompt with placeholders
└── frontend/                   # Next.js 15 dashboard (command-center layout)
```

### Multi-Phase Agent Pattern

Each mode follows a **phase-based execution** pattern:

| Mode | Phases | Description |
|------|--------|-------------|
| `greenfield` | `initialize` → `code*` | Create task list from spec, then code iteratively |
| `feature` | `analyze` → `plan` → `implement*` | Analyze codebase, plan tasks, implement iteratively |
| `refactor` | `analyze` → `plan` → `migrate*` | Analyze codebase, plan migration, execute incrementally |
| `fix` | `investigate` → `fix*` | Diagnose bug, fix iteratively |
| `evolve` | `audit` → `improve*` | Audit codebase, improve iteratively |
| `security` | `scan` → `remediate*` | Scan for vulnerabilities (human reviews report), then fix approved issues |

Phases marked with `*` are looping phases that repeat until all tasks are done.

Each session runs with a fresh context window. Progress persists through:
- `.swarmweaver/task_list.json` - Universal task list with rich status tracking
- `.swarmweaver/feature_list.json` - Legacy task list (backward compatible, auto-generated)
- `.swarmweaver/codebase_profile.json` - Analyzed project structure (for non-greenfield modes)
- `.swarmweaver/security_report.json` - Security scan findings (security mode, reviewed by user before remediation)
- `.swarmweaver/session_reflections.json` - Agent-written reflections, harvested into MELS expertise post-session
- `.swarmweaver/task_input.txt` - The user's feature/goal/issue description
- Git commits - Incremental progress snapshots
- `.swarmweaver/claude-progress.txt` - Session notes for context handoff

### Execution Flow

- **Single agent**: `Engine` runs one Claude SDK session with phase loop
- **Static swarm** (`--parallel N`): `Swarm` + `SwarmOrchestrator` — N workers in worktrees
- **Smart swarm** (`--smart-swarm`): `SmartSwarm` + `SmartOrchestrator` — AI decides worker count and task assignment

Decision logic in `main()` and server: `smart_swarm` → SmartSwarm; `parallel > 1` → Swarm; else → Engine.

### Core Components

| File | Purpose |
|------|---------|
| `cli/main.py` | CLI entry point — Typer app with all mode subcommands + `--worktree`, `--smart-swarm` |
| `api/app.py` | FastAPI app factory — 60+ REST endpoints + WebSocket |
| `autonomous_agent_demo.py` | Backward-compatible shim → `cli/main.py` |
| `server.py` | Backward-compatible shim → `api/app.py` |
| `core/paths.py` | Centralized artifact paths — all artifacts under `.swarmweaver/`, with legacy fallback |
| `core/agent.py` | Multi-phase agent session loop with MELS expertise harvesting |
| `core/engine.py` | Execution engine: single-agent runs with SDK streaming |
| `core/orchestrator.py` | SwarmOrchestrator: static N workers, worktree setup |
| `core/smart_orchestrator.py` | SmartOrchestrator: AI-orchestrated dynamic workers |
| `core/merge_resolver.py` | 4-tier merge conflict resolution (clean → auto → AI → reimagine) |
| `core/merge_queue.py` | SQLite FIFO merge queue at `.swarm/merge_queue.db` |
| `core/agent_roles.py` | Two-layer agent system: generates enhanced overlays with role definitions |
| `core/client.py` | Creates `ClaudeSDKClient` with security settings, MCP servers, and hooks |
| `core/prompts.py` | Dynamic prompt builder - assembles prompts from shared + mode-specific templates |
| `core/swarm.py` | Swarm + SmartSwarm (Engine, SwarmOrchestrator, SmartOrchestrator) |
| `core/worktree.py` | Git worktree utilities: create, merge, discard, status, diff, list |
| `state/task_list.py` | Universal task list system (replaces rigid feature_list.json) |
| `state/agent_identity.py` | Agent identity store with success rate, tool calls, domain expertise, CV |
| `state/checkpoints.py` | File state checkpoints for rollback |
| `utils/progress.py` | Enhanced progress dashboard with category breakdowns |
| `utils/sanitizer.py` | Secret sanitizer - redacts API keys, tokens, passwords from output |
| `utils/safe_logging.py` | Fire-and-forget logging that never crashes the agent |
| `hooks/security.py` | Bash command allowlist validation via `PreToolUse` hook |
| `hooks/capability_hooks.py` | Role-based capability enforcement (scout/builder/reviewer/lead) |
| `services/expertise_store.py` | MELS cross-project + project-local SQLite expertise stores |
| `services/expertise_priming.py` | MELS token-budget-aware priming engine for prompt injection |
| `services/expertise_synthesis.py` | MELS real-time session lesson synthesis from worker errors |
| `features/spec_workflow.py` | Spec-driven workflow: create/read/list specs per task |
| `services/monitor.py` | Fleet health monitor: agent health analysis, mail issues, recommendations |
| `services/timeline.py` | Cross-agent event timeline: merges events, mail, audit into one stream |
| `services/transcript_costs.py` | Transcript-based cost analysis: per-agent, per-model, with cache pricing |
| `services/insights.py` | Session insight analyzer: top tools, hot files, error frequency |
| `services/mcp_manager.py` | MCP server config store: two-level merge, CRUD, validate, test, import/export |
| `services/lsp_client.py` | JSON-RPC 2.0 LSP client over stdio: 14 operations, Content-Length framing |
| `services/lsp_manager.py` | 22 built-in language servers, lifecycle, auto-detect, auto-install, health loop |
| `services/lsp_intelligence.py` | Impact analysis, unused code detection, dependency graph, code health score |
| `services/lsp_tools.py` | Worker MCP tools: `lsp_query` (13 operations), `lsp_diagnostics_summary` |
| `state/sessions.py` | Persistent session DB: SessionStore (project-local) + GlobalSessionIndex (cross-project), SQLite WAL mode |
| `state/snapshots.py` | Shadow git snapshot system: SnapshotManager with capture, diff, restore, per-file revert; shadow repo at `~/.swarmweaver/snapshots/<hash>/` |
| `api/routers/session_history.py` | 9 REST endpoints for session history (list, detail, messages, files, archive, delete, analytics, global, migrate) |
| `api/routers/snapshots.py` | 8 REST endpoints for snapshots (list, diff, diff/file, files, revert, restore, cleanup, status) |
| `state/mail.py` | Inter-agent MailStore: typed payloads, context injection, attachments, dead letters, rate limiting, analytics |
| `web_search_server.py` | MCP server that wraps Claude's web search tool for agent use |

### Two-Layer Agent System

Agents are defined in `prompts/agents/` with five roles:

| Role | File | Capabilities | Restrictions |
|------|------|-------------|-------------|
| **Scout** | `prompts/agents/scout.md` | Read-only exploration, spec writing | No file modifications |
| **Builder** | `prompts/agents/builder.md` | Implementation within file scope | Scoped writes only, no git push |
| **Reviewer** | `prompts/agents/reviewer.md` | Code review, spec validation | No file modifications |
| **Lead** | `prompts/agents/lead.md` | Coordination, task splitting | No file writes, can git add/commit |
| **Orchestrator** | `prompts/agents/orchestrator.md` | AI-orchestrated worker management (Smart Swarm) | Dynamic spawn/manage via MCP tools |

Agent overlays are generated from `templates/overlay.md.tmpl` with placeholders:
`{{AGENT_NAME}}`, `{{TASK_IDS}}`, `{{FILE_SCOPE}}`, `{{BRANCH_NAME}}`, `{{WORKTREE_PATH}}`, `{{PARENT_AGENT}}`, `{{DEPTH}}`, `{{SPEC_PATH}}`, `{{EXPERTISE_CONTEXT}}`, `{{QUALITY_GATES}}`, `{{CONSTRAINTS}}`, `{{BASE_DEFINITION}}`

Capability enforcement is handled by `hooks/capability_hooks.py` which generates `.swarmweaver/claude_settings.json` per worker worktree.

### Agent Hierarchy (Swarm)

For **Swarm** (static N workers) with 3+ workers:
- `HierarchyManager` in `core/swarm.py` creates 1 Lead + N-1 Builders
- Maximum depth of 2 levels
- Stagger delay (2s) between worker spawns
- Lead handles task splitting within its scope

### Prompt Template Structure

```
prompts/
├── shared/              # Shared across all modes
│   ├── session_start.md   # Common orientation steps + {agent_memory} MELS expertise injection
│   ├── session_end.md     # Common cleanup steps + reflection saving (harvested into MELS)
│   └── verification.md    # Common verification steps
├── greenfield/          # Build from spec
│   ├── architect.md       # Architecture from idea (greenfield_from_idea mode)
│   ├── initializer.md    # Create task list from spec
│   └── coding.md         # Implement tasks
├── feature/             # Add to existing codebase
│   ├── analyzer.md       # Analyze codebase
│   ├── planner.md        # Plan feature tasks
│   └── implementer.md    # Implement features
├── refactor/            # Restructure/migrate
│   ├── analyzer.md       # Deep codebase analysis
│   ├── planner.md        # Plan safe migration steps
│   └── migrator.md       # Execute migration
├── fix/                 # Bug fixing
│   ├── investigator.md   # Reproduce and diagnose
│   └── fixer.md          # Fix and add regression tests
├── evolve/              # Improvement
│   ├── auditor.md        # Audit codebase
│   └── improver.md       # Implement improvements
├── security/            # Security scanning (isolated prompts, no shared templates)
│   ├── scanner.md         # Code-only vulnerability scan → .swarmweaver/security_report.json
│   ├── reporter.md        # Report formatting
│   └── remediator.md     # Fix approved vulnerabilities
├── agents/              # Two-layer agent role definitions
│   ├── scout.md           # Read-only exploration agent
│   ├── builder.md         # Implementation agent
│   ├── reviewer.md        # Code review agent
│   └── lead.md            # Coordination agent
├── initializer_prompt.md  # Legacy (still works)
├── coding_prompt.md       # Legacy (still works)
└── app_spec.txt           # Default spec for greenfield mode
```

### Security Model (Defense in Depth)

Three layers configured in `core/client.py`:
1. **OS Sandbox** - Bash commands run in isolated environment
2. **Filesystem Permissions** - Operations restricted to project directory via `./**` patterns
3. **Bash Allowlist Hook** - See `hooks/security.py` ALLOWED_COMMANDS for full list (~60+ commands). Categories: file inspection (ls, cat, head, tail, wc, grep, find, diff, stat), file ops (cp, mv, mkdir, touch, rm, chmod, ln), text processing (sort, uniq, sed, awk, cut, tee), Python (python, pip, pytest, uvicorn), Node (npm, npx, node, next, vite), git, process mgmt (ps, lsof, pkill, kill), shell (echo, env, which, bash), archive (tar, zip), HTTP (curl, wget), scripts (init.sh, start-backend.sh).

Special validation for `pkill` (dev processes only), `chmod` (+x variants), `rm` (blocks catastrophic patterns), and `init.sh` execution.

Additionally:
- **Capability enforcement** (`hooks/capability_hooks.py`) - Role-based tool blocking per agent type
- **Secret sanitizer** (`utils/sanitizer.py`) - Redacts API keys, tokens, passwords from all output

### MCP Servers

SwarmWeaver ships with two built-in MCP servers and supports user-configurable servers via CLI, API, or Web UI:

**Built-in servers (always available):**
- **puppeteer** - Browser automation for UI testing (`npx puppeteer-mcp-server`)
- **web_search** - Web search via `web_search_server.py`

**User-configurable servers:**
- Managed via `swarmweaver mcp list|add|remove|enable|disable|test` (CLI), REST API, or MCPPanel in Web UI Settings
- Two-level config merge: `~/.swarmweaver/mcp_servers.json` (global, applies to all projects) + `.swarmweaver/mcp_servers.json` (project-level overrides)
- `services/mcp_manager.py` — `MCPConfigStore` handles CRUD, enable/disable, validate, test, import/export
- `core/client.py` loads all enabled MCP servers automatically into every agent session (single agent, swarm workers, and smart orchestrator)

### REST API (60+ Endpoints)

Key endpoint categories:

| Category | Key Endpoints |
|----------|--------------|
| Core | `POST /api/run`, `POST /api/stop`, `POST /api/steer` |
| Projects | `GET /api/projects`, `GET /api/project-status` |
| Tasks | `GET /api/tasks`, `GET /api/task-groups` |
| Runs | `GET /api/runs` |
| Spec | `GET/POST /api/spec`, `GET/POST /api/specs/{task_id}` |
| Worktree | `POST /api/worktree/merge`, `POST /api/worktree/discard`, `GET /api/worktree/diff` |
| Security | `GET /api/security-report`, `POST /api/security-report/approve` |
| Swarm | `GET /api/swarm/status`, `GET /api/swarm/merge-queue`, `POST /api/swarm/workers/{id}/nudge`, `POST /api/swarm/workers/{id}/terminate`, `GET /api/swarm/mail/analytics` |
| Budget | `GET /api/budget`, `POST /api/budget/update` |
| Costs | `GET /api/costs`, `GET /api/costs/by-agent`, `GET /api/costs/by-model` |
| Checkpoints | `GET /api/checkpoints`, `POST /api/checkpoints/restore` |
| Insights | `GET /api/insights` |
| Timeline | `GET /api/timeline` |
| Agents | `GET /api/agents`, `GET /api/agents/{name}`, `GET /api/subagents` |
| Expertise (MELS) | `GET/POST /api/expertise`, `GET/PUT/DELETE /api/expertise/{id}`, `POST /api/expertise/{id}/outcome`, `GET /api/expertise/search`, `GET /api/expertise/prime`, `GET /api/expertise/causal-chain/{id}`, `GET/POST /api/expertise/domains`, `GET /api/expertise/analytics`, `GET /api/expertise/session-lessons`, `POST /api/expertise/migrate`, `POST /api/expertise/prune`, `GET /api/expertise/export` |
| Project expertise | `GET/POST /api/projects/expertise`, `DELETE /api/projects/expertise/{id}` (delegates to MELS) |
| Task sync | `POST /api/tasks/sync`, `GET /api/tasks/sync/status` |
| Session chain | `GET /api/session/chain` |
| Settings | `GET/POST /api/settings`, `GET/POST /api/projects/settings` |
| QA/Architect/Plan/Scan | `POST /api/qa/generate`, `POST /api/architect/generate`, `POST /api/plan/generate`, `POST /api/scan/generate`, `POST /api/analyze/generate`, `POST /api/project/prepare` |
| Specs | `GET /api/specs`, `GET/POST /api/specs/{task_id}` |
| Watchdog | `GET /api/watchdog/events`, `GET /api/watchdog/config`, `PUT /api/watchdog/config` |
| Session History | `GET /api/sessions`, `GET /api/sessions/{id}`, `GET /api/sessions/{id}/messages`, `GET /api/sessions/{id}/files`, `POST /api/sessions/{id}/archive`, `DELETE /api/sessions/{id}`, `GET /api/sessions/analytics`, `GET /api/sessions/global`, `POST /api/sessions/migrate` |
| Snapshots | `GET /api/snapshots`, `GET /api/snapshots/diff`, `GET /api/snapshots/diff/file`, `GET /api/snapshots/files`, `POST /api/snapshots/revert`, `POST /api/snapshots/restore`, `POST /api/snapshots/cleanup`, `GET /api/snapshots/status` |
| Fleet | `GET /api/fleet/health` |
| MCP | `GET/POST/PUT/DELETE /api/mcp/servers`, `POST /api/mcp/servers/{name}/enable\|disable\|test`, `POST /api/mcp/servers/validate`, `GET /api/mcp/export`, `POST /api/mcp/import` |
| LSP | `GET /api/lsp/status`, `GET /api/lsp/diagnostics`, `POST /api/lsp/hover\|definition\|references\|symbols\|call-hierarchy`, `GET /api/lsp/servers`, `POST /api/lsp/servers/{id}/restart`, `GET/PUT /api/lsp/config`, `GET /api/lsp/impact-analysis`, `GET /api/lsp/code-health` |
| Health | `GET /api/doctor` |
| Files | `GET /api/browse`, `POST /api/mkdir` |
| WebSocket | `WS /ws/run`, `WS /ws/architect`, `WS /ws/plan`, `WS /ws/wizard` |

### Generated Project Structure

All SwarmWeaver artifacts are consolidated under `.swarmweaver/` — delete it and the project is clean.

```
<project>/
├── .swarmweaver/                    # All SwarmWeaver artifacts (rm -rf to clean up)
│   ├── task_list.json               # Task list with rich status tracking and verification
│   ├── feature_list.json            # Legacy task list (auto-generated)
│   ├── codebase_profile.json        # Analyzed project structure (non-greenfield)
│   ├── security_report.json         # Security scan findings (security mode)
│   ├── session_reflections.json     # Agent reflections (harvested into MELS expertise post-session)
│   ├── task_input.txt               # The feature/goal/issue description
│   ├── app_spec.txt                 # Project specification (greenfield)
│   ├── claude-progress.txt          # Session handoff notes
│   ├── session_state.json           # Session ID tracking and resumption
│   ├── budget_state.json            # Cost tracking state
│   ├── audit.log                    # Tool execution log
│   ├── agent_output.log             # Agent stdout capture
│   ├── claude_settings.json         # Security settings
│   ├── process_registry.json        # Tracked background processes (auto-managed)
│   ├── checkpoints.json             # File state checkpoints for rollback
│   ├── steering_input.json          # Human-in-the-loop steering messages
│   ├── approval_pending.json        # Task approval gate state
│   ├── model_override.json          # Mid-session model switch
│   ├── architect_notes.md           # Architect phase notes
│   ├── transcript_archive.jsonl     # Transcript metadata
│   ├── specs/                       # Task specifications (spec-driven workflow)
│   ├── agents/                      # Agent identity store
│   ├── swarm/                       # Multi-agent swarm state
│   ├── worktrees/                   # Git worktrees for isolated runs
│   ├── runs/                        # Run history
│   ├── chains/                      # Session chain data
│   ├── mcp_servers.json              # Project-level MCP server config (merged with global)
│   ├── expertise/expertise.db        # MELS project-local expertise store (SQLite)
│   ├── mail.db                      # Inter-agent mail (typed payloads, attachments, dead letters, analytics)
│   ├── events.db                    # Structured event store
│   ├── watchdog.yaml                # Watchdog health monitor configuration
│   ├── watchdog_events.db           # Persistent watchdog event log (SQLite)
│   ├── sessions.db                 # Persistent session database (SQLite WAL; sessions, messages, file_changes)
│   └── lsp.yaml                    # LSP code intelligence configuration
├── init.sh                        # Environment setup script (greenfield, stays at root)
└── docs/adr/                      # Architecture Decision Records (stays at root)
```

**Legacy migration:** Projects with root-level artifacts are automatically migrated to `.swarmweaver/` on first access via `core/paths.py`'s `migrate_if_needed()`.

### Autonomous Process & Environment Management

The system includes **fully autonomous** hooks that make decisions automatically - the agent does NOT need to check or manage these manually:

#### Autonomous Hooks (in `hooks/main_hooks.py`)

| Hook | Autonomous Behavior |
|------|---------------------|
| `server_management_hook` | **Auto-blocks** duplicate servers, **auto-kills** conflicting processes, **auto-modifies** ports |
| `environment_management_hook` | **Auto-skips** redundant venv/npm installs, **auto-uses** existing venv for pip |
| `file_management_hook` | **Auto-redirects** test/debug scripts to `scripts/`, session notes to `docs/` |
| `port_config_hook` | **Auto-replaces** hardcoded zombie ports (8002) with configured backend port |
| `knowledge_injection_hook` | **Auto-suggests** relevant docs when working on EU AI Act, A2A, errors |
| `mail_injection_hook` | **Auto-injects** unread inter-agent mail into agent context (every 5 tool calls, PostToolUse) |
| `log_consolidation_hook` | **Auto-redirects** log files to standard names (logs/backend.log, logs/frontend.log) |
| `progress_file_management_hook` | **Auto-warns** when progress file exceeds 2000 lines, suggests archiving |
| `audit_log_hook` | **Auto-registers** background processes with PIDs and ports |
| `stop_hook` | **Auto-terminates** all tracked processes on session end |

#### Marathon Session Hooks (in `hooks/marathon_hooks.py`)

For long-running autonomous sessions (hours/days):

| Hook | Purpose |
|------|---------|
| `auto_commit_hook` | **Auto-commits** git every 15 minutes + after test completions |
| `health_monitor_hook` | **Auto-checks** if servers are still running (every 20 tool calls) |
| `loop_detection_hook` | **Auto-detects** when agent is stuck repeating same operations |
| `session_stats_hook` | **Auto-reports** stats every 100 tool calls (duration, errors) |
| `resource_monitor_hook` | **Auto-warns** on low disk space (<5GB) |
| `heartbeat_hook` | **Auto-sends** heartbeat to watchdog every 60s via mail (PostToolUse) |

#### Capability Enforcement Hooks (in `hooks/capability_hooks.py`)

Role-based sandboxing for swarm agents:

| Role | Write/Edit Allowed | Bash Access | Git Push |
|------|-------------------|-------------|----------|
| **Scout** | Blocked | Read-only commands only | Blocked |
| **Builder** | Within file scope only | Full access | Blocked |
| **Reviewer** | Blocked | Read-only commands only | Blocked |
| **Lead** | Blocked | Full access | Blocked |

Dangerous bash patterns detected and blocked: `sed -i`, `echo >`, `git push`, `git reset --hard`, etc.

**Example outputs:**
```
[MARATHON] Auto-committed: feat: Mark test as passing...
[MARATHON] SESSION STATS: 500 tool calls, 2.5 hours, 12 errors
[MARATHON] LOOP DETECTION: Repeating same 2 operation(s)
[MARATHON] LOW DISK SPACE: 2.3 GB remaining
```

#### Server Management (Fully Automatic)

The `server_management_hook` makes these decisions automatically:

1. **Same server type already running?** → BLOCK command, notify agent to reuse existing
2. **Port taken by different process type?** → AUTO-KILL old process, allow new one
3. **Port taken by untracked process?** → AUTO-MODIFY command to use next available port
4. **Port is free?** → Allow command, register the new process

#### Environment Management (Fully Automatic)

The `environment_management_hook` makes these decisions automatically:

1. **Creating venv that exists?** → BLOCK, no need to recreate
2. **Running npm install with node_modules populated?** → BLOCK, skip install
3. **Running pip install without venv activation?** → AUTO-MODIFY to use venv Python

#### Process Registry (`state/process_registry.py`)

Tracks all background processes with:
- PID, port, command, process type
- Start timestamp
- Alive/dead status

**Manual cleanup utility** (for debugging only):
```bash
python scripts/cleanup_processes.py ./generations/my_project --status     # View processes
python scripts/cleanup_processes.py ./generations/my_project --terminate  # Kill all
```

#### Agent Guidelines

The agent does NOT need to:
- Check if servers are running before starting
- Check if venv/node_modules exist before installing
- Manually manage ports or kill processes
- Track background process PIDs
- Organize scripts into directories
- Remember which port the backend is on

The hooks handle ALL of this automatically. The agent should just run commands normally.

### Git Worktree Isolation

The `--worktree` flag (CLI) or "Use worktree" toggle (Web UI) runs the agent in an isolated git worktree.

**How it works:**
1. A worktree is created at `<project>/.swarmweaver/worktrees/<run-id>/` on branch `swarmweaver/<run-id>`
2. The agent is redirected to the worktree directory (agent-unaware — it runs exactly as before)
3. On completion, the user gets merge/discard options

**Key files:**
- `core/worktree.py` — Standalone utilities: `create_worktree()`, `merge_worktree()`, `discard_worktree()`, `get_worktree_status()`, `get_worktree_diff()`, `list_worktrees()`
- `api/routers/` — REST endpoints: `POST /api/worktree/merge`, `POST /api/worktree/discard`, `GET /api/worktree/diff`, `GET /api/worktree/status`

### Merge Resolver & Merge Queue

When swarm workers produce merge conflicts, `core/merge_resolver.py` escalates through 4 tiers: **CLEAN** (git merge succeeds) → **AUTO_RESOLVE** (parse conflict markers, keep incoming) → **AI_RESOLVE** (Claude semantic merge) → **REIMAGINE** (abort, reimplement from both versions). History in `.swarmweaver/merge_history.json`.

`core/merge_queue.py` provides a SQLite FIFO queue at `.swarm/merge_queue.db` for ordered, tracked merging of worker branches. Statuses: `pending`, `merging`, `merged`, `conflict`, `failed`.

### Security Scan Mode

The `security` mode provides vulnerability scanning with human-in-the-loop review before any fixes are applied.

**Key design decisions:**
- Scanner prompt is **isolated from shared templates** — does not use `{shared_session_start}` or `{shared_session_end}`
- Scanner has an explicit **blocklist**: will not read `.swarmweaver/task_list.json`, `.swarmweaver/feature_list.json`, `.swarmweaver/claude-progress.txt`, or other project management artifacts
- Human review step is mandatory — the agent cannot proceed to remediation without user approval

### Multi-Expertise Learning System (MELS)

MELS is the unified knowledge engine that replaces all previous learning infrastructure (AgentMemory, ProjectExpertise, lessons.json). It provides typed, domain-hierarchical, governed expertise with real-time intra-session learning.

**Architecture:**
- **Cross-project store:** `~/.swarmweaver/expertise/expertise.db` (SQLite WAL) — knowledge shared across all projects
- **Project-local store:** `.swarmweaver/expertise/expertise.db` — project-specific knowledge
- **10 record types:** convention, pattern, failure, decision, reference, guide, resolution, insight, antipattern, heuristic
- **3 classifications:** foundational (permanent), tactical (30d shelf life), observational (14d shelf life)
- **Hierarchical domains:** `python.fastapi` inherits from `python`, auto-inferred from file paths

**How it works:**
1. `{agent_memory}` placeholder in `session_start.md` injects MELS-primed expertise via `PrimingEngine`
2. `session_end.md` instructs the agent to write reflections to `.swarmweaver/session_reflections.json`
3. Post-session harvester in `core/agent.py` reads reflections and stores as typed `ExpertiseRecord` entries
4. Auto-saves success/failure patterns with confidence scoring and decay

**Real-time intra-session learning (Smart Swarm):**
- `SessionLessonSynthesizer` records worker errors, detects clusters (2+ similar across workers)
- Synthesized lessons are quality-gated (specificity + actionability >= 0.4)
- High-quality lessons are propagated to active workers mid-session via steering messages
- At session end, high-quality lessons are promoted to permanent `ExpertiseRecord` entries

**Key components:**
- `services/expertise_models.py` — Data models, domain taxonomy, record types
- `services/expertise_store.py` — SQLite store (CRUD, search, governance, session lessons)
- `services/expertise_scoring.py` — Multi-signal confidence (success rate + recency + confirmation density)
- `services/expertise_priming.py` — Token-budget-aware greedy knapsack selection for prompt injection
- `services/expertise_synthesis.py` — Real-time lesson synthesis from worker error clusters
- `api/routers/expertise.py` — 16 REST endpoints for the full expertise lifecycle

**Confidence scoring:** 50% success rate + 20% recency decay + 30% confirmation density. New records start at 0.5.

**Priming:** `GET /api/expertise/prime?files=src/app.py&budget=2000` returns formatted expertise blocks

**Causal chains:** Failure records can be linked to resolution records via `resolves`/`resolved_by` fields

**WebSocket events:** `expertise_lesson_created`, `expertise_lesson_propagated`, `expertise_record_promoted`

### Multi-Session Tabbed UI

The frontend supports running multiple projects in parallel via a tabbed interface:

- `SessionSidebar.tsx` — Left sidebar: session list with mode icons, status indicators, New Session, Settings; collapsible
- `TabBar.tsx` — Compact horizontal tab strip with mode accent colors, status dots, close buttons, and "+" button
- `SessionTab.tsx` — Extracted wizard body per tab, each with its own independent `useSwarmWeaver()` hook instance
- `page.tsx` — Slim TabManager: manages `tabs[]` and `activeTabId`, renders all tabs (background tabs stay mounted via `display: none`)

### Frontend Component Architecture

The web UI uses a wizard-step pattern:

```
Landing → Configure → [Review] → Execute
  │          │           │          │
  │   GreenfieldSetup    │    ExecutionDashboard
  │   FeatureSetup       │      (TopStatusStrip + Activity + Terminal + Inspector)
  │   RefactorSetup   PlanReview
  │   FixSetup        ArchitectReview
  │   EvolveSetup     SecurityReportReview
  │   SecuritySetup
  │
  LandingStep (Omnibar command center + recent projects)
```

All setup forms include a "Use worktree" toggle in their Advanced Options section.

#### Execution Dashboard Layout

The execution dashboard uses a **command-center layout** with resizable panels:

```
+------------------------------------------------------------------+
| TopStatusStrip: health dots | $cost | agent count | phase badge   |
+------------------------------------------------------------------+
| Activity  |                                  | Inspector (tabbed) |
| Sidebar   |         Terminal                 | Tasks | Observe    |
| (collaps) |         (primary)                | ADRs | Memory     |
|           |                                  | Notes              |
+-----------+----------------------------------+--------------------+
| FloatingActionBar (steering input, stop, progress)               |
+------------------------------------------------------------------+
```

#### Observe Panel Sub-tabs (11 total)

| Sub-tab | Component | Data Source |
|---------|-----------|-------------|
| Timeline | `TimelinePanel.tsx` | `/api/timeline` + WS `timeline_event` |
| Files | Built-in | Parsed from agent output |
| Costs | `CostPanel.tsx` | `/api/costs`, `/api/costs/by-agent`, `/api/costs/by-model` |
| Errors | Built-in | Filtered from event stream |
| Audit | Built-in | `.swarmweaver/audit.log` |
| Insights | `InsightsPanel.tsx` | `/api/insights` |
| Agents | `AgentIdentityPanel.tsx` | `/api/agents` |
| Checkpoints | `CheckpointPanel.tsx` + `SnapshotPanel.tsx` | `/api/checkpoints` + `/api/snapshots` |
| Sessions | `SessionBrowserPanel.tsx` | `/api/sessions` + WS `session_db_*` |
| Profile | Built-in | Session profiling data |
| Code Intel | `LSPPanel.tsx` | `/api/lsp/*` + WS `lsp.*` |

#### Persistent Session Database

`state/sessions.py` provides SQLite-backed session persistence (WAL mode, `busy_timeout=5000`):

- **SessionStore** (project-local at `.swarmweaver/sessions.db`) — records sessions, per-turn messages with tokens/cost/snapshots, file changes via `git diff`, cumulative analytics
- **GlobalSessionIndex** (cross-project at `~/.swarmweaver/sessions.db`) — aggregated session metadata for global analytics

Wired into:
- `core/engine.py` — 5 insertion points: init, session creation, per-turn message recording, completion with change summary, error handling
- `core/smart_orchestrator.py` — team session creation, per-worker message recording via `session_result` event, completion

WebSocket events: `session_db_created`, `session_db_updated`, `session_db_completed`

#### Shadow Git Snapshot System

`state/snapshots.py` provides a shadow git repository at `~/.swarmweaver/snapshots/<project_hash>/` (ext4, NOT NTFS):

- **Pre/post capture** before and after each agent turn via `git write-tree`
- **Structured diffs** between any two snapshots
- **Per-file revert** and full restore
- **Graceful degradation** — all operations fail silently, returning None/False

Wired into `core/engine.py` with pre-turn and post-turn capture points. Snapshot hashes are stored in `ChainEntry` (`state/session_checkpoint.py`) and message records.

WebSocket events: `snapshot_captured`
