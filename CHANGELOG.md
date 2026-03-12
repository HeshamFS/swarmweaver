# Changelog

All notable changes to SwarmWeaver are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Enhanced
- **Shadow git snapshots**: Replaced fragile JSON index with SQLite database (WAL mode). Captures now create proper git commits in a linear chain instead of orphan tree objects. Added named bookmarks (preserved from cleanup), preview-before-restore, and commit history browsing. 13 REST endpoints (was 8). Frontend adds Timeline/Bookmarks view toggle, bookmark modal, and restore preview confirmation.

## [1.0.0] - 2026-03-06

Initial release of SwarmWeaver — an autonomous coding agent platform powered by the Claude Agent SDK.

### Added

- **Six operation modes**: greenfield (build from spec), feature (add to existing codebase), refactor (restructure/migrate), fix (diagnose and fix bugs), evolve (open-ended improvement), security (vulnerability scan with human-in-the-loop review)
- **Multi-agent swarm**: Static swarm (`--parallel N`) with N workers in isolated git worktrees coordinated by `SwarmOrchestrator`; Smart Swarm (`--smart-swarm`) with AI-orchestrated dynamic workers via `SmartOrchestrator`
- **4-tier merge conflict resolution**: clean → auto-resolve → AI-resolve → reimagine; SQLite merge queue for ordered branch merging
- **Role-based capability enforcement**: Scout, Builder, Reviewer, Lead, Orchestrator
- **Next.js 15 command-center dashboard**: Multi-session tabs, omnibar (idea → folder → mode → launch), real-time agent output, task panel with verification badges and dependency graph
- **9-tab observability panel**: Timeline, Files, Costs, Errors, Audit, Insights, Agents, Checkpoints, Profile
- **Swarm Panel**: Per-worker controls, mail threads, merge queue, nudge/terminate buttons
- **Security scan review**, approval gates, worktree merge/discard, session replay
- **Notifications**: Slack, Discord, browser push, generic webhooks
- **CLI package** (`cli/`): Installable via `uv sync`, entry point `swarmweaver`; all six modes, `status`, `steer`, `logs`, `merge`, `checkpoint`, `init`; `--interactive`, `--json`, `--server`; connected mode via `SWARMWEAVER_URL`; global config at `~/.swarmweaver/config.toml`
- **API package** (`api/`): FastAPI with 60+ REST endpoints, WebSocket (`/ws/run`, `/ws/architect`, `/ws/plan`, `/ws/wizard`); `server.py` backward-compatible shim
- **Autonomous hooks**: Server, environment, file, and port management; marathon hooks (auto-commit, health, loop detection, resource monitoring); bash allowlist (~60+ commands); secret sanitizer
- **MELS expertise system**: Multi-Expertise Learning System with cross-project + project-local SQLite stores; 10 record types; hierarchical domain taxonomy; confidence scoring with decay; real-time intra-session lesson synthesis; causal failure-resolution chains; token-budget-aware priming; 16 REST endpoints
- **Docker**: Multi-stage build, `docker-compose.yml` with volume mount and both auth methods

[Unreleased]: https://github.com/HeshamFS/swarmweaver/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/HeshamFS/swarmweaver/releases/tag/v1.0.0
