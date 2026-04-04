# <img src="docs/images/app-icon.svg" alt="" width="32" height="32" style="vertical-align: middle" /> SwarmWeaver_

**Autonomous multi-mode coding agent** powered by the Claude Agent SDK.

<p align="center">
  <img src="docs/images/landing-screenshot.png" alt="SwarmWeaver landing page: New Project setup with project folder input, description textarea, Greenfield mode selector, and LAUNCH button" width="800" />
</p>
<p align="center"><em>The SwarmWeaver command center — describe what you want to build and launch.</em></p>

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white "Python 3.11 or newer")](https://www.python.org/downloads/)
[![Node 20+](https://img.shields.io/badge/node-20%2B-green?logo=node.js&logoColor=white "Node.js 20 or newer")](https://nodejs.org/)
[![License MIT](https://img.shields.io/badge/license-MIT-green "MIT License")](LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/HeshamFS/swarmweaver/ci.yml?branch=main "Build status")](https://github.com/HeshamFS/swarmweaver/actions)
[![Docker](https://img.shields.io/badge/docker-ready-blue?logo=docker&logoColor=white "Docker support")](https://github.com/HeshamFS/swarmweaver#docker)

Point it at a spec, a codebase, or a bug report — it works autonomously across unlimited sessions until the job is done. Built for long-running autonomous sessions with audit trails, approval gates, and cost controls.

## Key Features

- **Six operation modes** — greenfield, feature, refactor, fix, evolve, security
- **Web UI + CLI** — Omnibar command center, multi-session tabs, real-time terminal
- **Multi-agent swarm** — Static N workers or AI-orchestrated Smart Swarm with inter-agent mail
- **Git worktree isolation** — Run in isolated branches; merge or discard on completion
- **Session persistence** — SQLite-backed session database recording every session, agent turn, cost, and file change with cross-project indexing
- **Shadow git snapshots** — Commit-based capture before/after each agent turn with SQLite index, named bookmarks, preview-before-restore, per-file diff and surgical revert
- **MELS expertise system** — Cross-project learning with real-time intra-session lesson synthesis
- **Native LSP code intelligence** — 22 language servers with impact analysis and cross-worker diagnostics
- **Approval gates & verification** — Human-in-the-loop review, self-healing test loops
- **Enhanced watchdog** — 9-state health monitoring, AI triage, circuit breaker
- **MCP server integration** — User-configurable Model Context Protocol servers
- **Docker ready** — Single `docker-compose up` for the full stack

## How It Works

SwarmWeaver is a Python harness that runs Claude as a long-running autonomous coding agent. Unlike one-shot code generation, it works across **many sessions** with fresh context windows, persisting progress through a task list, git commits, and handoff notes.

**Choose your goal** — each maps to a mode:

| Your goal | Mode | Example |
|-----------|------|---------|
| Build from spec | `greenfield` | "Build me a SaaS dashboard from this spec" |
| Add new features | `feature` | "Add OAuth2 login with Google and GitHub" |
| Migrate or restructure | `refactor` | "Migrate from JavaScript to TypeScript" |
| Diagnose and fix bugs | `fix` | "Login fails when email has a plus sign" |
| Improve an existing app | `evolve` | "Add unit tests for 80% coverage" |
| Security vulnerability scan | `security` | "Full security audit of the API layer" |

Each mode follows a **phase-based execution** pattern with looping phases that repeat until all tasks are complete. See [docs/overview.md](docs/overview.md) for detailed phase sequences and cross-cutting capabilities, or jump to the [full system architecture diagram](docs/architecture.md#system-architecture) for a visual overview of every subsystem and how they connect.

## Prerequisites

- **Python 3.11+** — [python.org](https://www.python.org/downloads/)
- **Node 20+** — [nodejs.org](https://nodejs.org/)
- **uv** — Fast Python package manager ([install guide](https://docs.astral.sh/uv/getting-started/installation/))

## Quick Start

### Option 1: Web UI (Recommended)

```bash
# 1. Clone and install
git clone https://github.com/HeshamFS/swarmweaver.git
cd swarmweaver
./setup.sh                   # creates venv + installs Python deps (Unix/macOS)
# On Windows: use "uv sync" and "npm install" instead
npm install                  # installs root dev tooling

# 2. Configure authentication
cp .env.example .env
# Edit .env and set one of:
#   CLAUDE_CODE_OAUTH_TOKEN=your-token   (Claude Code Max — run 'claude setup-token')
#   ANTHROPIC_API_KEY=your-key           (API key from console.anthropic.com)

# 3. Start the full stack
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). Use the Omnibar to pick a mode, point it at a directory, and launch.

### Option 2: CLI

```bash
# Install (globally available)
pip install -e .

# Run any mode
swarmweaver --help
swarmweaver greenfield --project-dir ./my_app --spec ./my_spec.txt
swarmweaver feature   --project-dir ./my_app --description "Add OAuth2 login"
swarmweaver fix       --project-dir ./my_app --issue "Login fails with plus in email"
```

See [docs/cli-reference.md](docs/cli-reference.md) for the full command reference, flags, and examples.

### Option 3: Docker

```bash
cp .env.example .env   # set ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN
docker-compose up
# Web UI → http://localhost:3000   |   API → http://localhost:8000
```

## Authentication

Set one of these in your `.env` file:

| Variable | Purpose |
|----------|---------|
| `CLAUDE_CODE_OAUTH_TOKEN` | Claude Code Max subscription — run `claude setup-token` to generate |
| `ANTHROPIC_API_KEY` | API key from [console.anthropic.com](https://console.anthropic.com) |

Both options work for Web UI, CLI, and Docker. See [docs/configuration.md](docs/configuration.md) for all environment variables and config options.

## Development

```bash
# Full setup
git clone https://github.com/HeshamFS/swarmweaver.git && cd swarmweaver
./setup.sh && npm install

# Dev stack
npm run dev             # FastAPI on :8000 + Next.js on :3000

# Tests
pytest tests -q
```

## Documentation

**Getting Started:**
- [Overview](docs/overview.md) — Modes, phases, cross-cutting capabilities
- [Getting Started](docs/getting-started.md) — Installation, authentication, first run
- [CLI Reference](docs/cli-reference.md) — Commands, flags, examples
- [Web UI](docs/web-ui.md) — Dashboard capabilities and layout
- [Configuration](docs/configuration.md) — Environment variables, config files, project artifacts

**Core Systems:**
- [Architecture](docs/architecture.md) — Package map, execution flow
- [Swarm Orchestration](docs/swarm.md) — Static swarm, Smart Swarm, merge resolution, worker lifecycle
- [MELS Expertise System](docs/mels.md) — Cross-project learning, domain taxonomy, priming, lesson synthesis
- [Security Model](docs/security.md) — Bash allowlist, role-based capabilities, secret sanitizer

**Infrastructure:**
- [Session History & Snapshots](docs/session-history.md) — Persistent session database, shadow git snapshots
- [Watchdog Health Monitoring](docs/watchdog.md) — 9-state machine, AI triage, circuit breaker
- [Inter-Agent Mail](docs/mail.md) — Typed messages, attachments, dead letters, analytics
- [LSP Code Intelligence](docs/lsp.md) — 22 language servers, diagnostics, impact analysis

**Project:**
- [CLAUDE.md](CLAUDE.md) — Detailed architecture reference for AI coding assistants
- [AGENTS.md](AGENTS.md) — Concise agent context for AI tools
- [CONTRIBUTING.md](CONTRIBUTING.md) — Setup, code style, commit conventions, PR checklist
- [CHANGELOG.md](CHANGELOG.md) — Release history and notable changes

## Getting Help

- **GitHub Issues** — [Report bugs or request features](https://github.com/HeshamFS/swarmweaver/issues)
- **GitHub Discussions** — [Ask questions and share ideas](https://github.com/HeshamFS/swarmweaver/discussions)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, code style, commit conventions, and the PR checklist.

## License

[MIT](LICENSE) — Copyright (c) 2026 SwarmWeaver Contributors
