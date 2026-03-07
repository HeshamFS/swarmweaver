# Getting Started

This guide covers prerequisites, installation, authentication, and your first run with SwarmWeaver.

## Prerequisites

- **Python 3.11+** — [python.org](https://www.python.org/downloads/)
- **Node 20+** — [nodejs.org](https://nodejs.org/)
- **uv** — Fast Python package manager ([install guide](https://docs.astral.sh/uv/getting-started/installation/))
- **npm** — Bundled with Node.js

## Installation

### Option 1: Web UI (Recommended)

```bash
# 1. Clone and install
git clone https://github.com/HeshamFS/swarmweaver.git
cd swarmweaver
./setup.sh                   # creates venv + installs Python deps (Unix/macOS)
# On Windows: use "uv sync" and "npm install" instead
npm install                  # installs root dev tooling

# 2. Configure authentication (see below)

# 3. Start the full stack
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). Use the Omnibar to pick a mode, point it at a directory, and launch.

### Option 2: CLI Only

```bash
# Install all deps and register the 'swarmweaver' command
uv sync

# Run any mode (after configuring auth)
swarmweaver greenfield --project-dir ./my_app --spec ./my_spec.txt
swarmweaver feature   --project-dir ./my_app --description "Add OAuth2 login"
swarmweaver fix       --project-dir ./my_app --issue "Login fails with plus in email"
swarmweaver evolve    --project-dir ./my_app --goal "Add 80% unit test coverage"
swarmweaver security  --project-dir ./my_app --description "Full security audit"
```

### Option 3: Docker

```bash
# Copy and configure auth
cp .env.example .env   # set ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN

# Start everything
docker-compose up

# Web UI → http://localhost:3000
# API    → http://localhost:8000
```

## Authentication

Copy `.env.example` to `.env` and set one of:

| Variable | Purpose |
|----------|---------|
| `CLAUDE_CODE_OAUTH_TOKEN` | Claude Code Max subscription — run `claude setup-token` to generate |
| `ANTHROPIC_API_KEY` | API key from [console.anthropic.com](https://console.anthropic.com) |

Both options work for Web UI, CLI, and Docker. The agent uses whichever is set.

## First Run

1. **Choose a mode** — See [Overview](overview.md) for mode descriptions.
2. **Point at a directory** — Use an existing project (for feature/refactor/fix/evolve/security) or a new folder (for greenfield).
3. **Provide input** — Description, goal, issue, or spec file depending on mode.
4. **Launch** — Web UI: click LAUNCH; CLI: run the command.

For greenfield, you can use the built-in default spec:

```bash
swarmweaver greenfield --project-dir ./my_app
```

For feature mode with a description:

```bash
swarmweaver feature --project-dir ./my_app --description "Add a user settings page with dark mode"
```

## Next Steps

- [CLI Reference](cli-reference.md) — Full command and flag reference
- [Web UI](web-ui.md) — Web interface capabilities
- [Configuration](configuration.md) — Environment variables and config files
- [Architecture](architecture.md) — Package structure and execution flow
