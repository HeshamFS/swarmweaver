# Configuration

SwarmWeaver uses environment variables and an optional config file for authentication and defaults.

## Environment Variables

Copy `.env.example` to `.env` and set one of:

| Variable | Purpose |
|----------|---------|
| `ANTHROPIC_API_KEY` | Anthropic API key (from [console.anthropic.com](https://console.anthropic.com)) |
| `CLAUDE_CODE_OAUTH_TOKEN` | Claude Code Max OAuth token (run `claude setup-token` to generate) |
| `SWARMWEAVER_CORS_ORIGINS` | Allowed CORS origins for the API (e.g. `https://app.example.com`) |

**Authentication:** Set either `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN`. Both work for agent execution.

## User Config: ~/.swarmweaver/config.toml

Optional user-level config for CLI defaults and connected mode:

```toml
[server]
url = "http://my-server:8000"   # Delegate to a running SwarmWeaver server

[defaults]
model = "claude-sonnet-4-6"
max_iterations = 10
```

When `SWARMWEAVER_URL` is set (env) or `server.url` is set (config), the CLI delegates execution to that server instead of running locally.

## Project Artifacts: .swarmweaver/

Each target project gets a `.swarmweaver/` directory with session state and artifacts:

| File | Purpose |
|------|---------|
| `task_list.json` | Universal task list with status and verification |
| `feature_list.json` | Legacy task list (auto-generated) |
| `session_state.json` | Session ID tracking and resumption |
| `task_input.txt` | Feature/goal/issue description |
| `claude-progress.txt` | Session handoff notes |
| `codebase_profile.json` | Analyzed project structure (non-greenfield) |
| `security_report.json` | Security scan findings (security mode) |
| `session_reflections.json` | Agent reflections (harvested into memory) |
| `budget_state.json` | Cost tracking state |
| `audit.log` | Tool execution log |
| `agent_output.log` | Agent stdout capture |
| `claude_settings.json` | Security settings per worktree |
| `process_registry.json` | Tracked background processes |
| `checkpoints.json` | File state checkpoints for rollback |
| `steering_input.json` | Human-in-the-loop steering messages |
| `approval_pending.json` | Task approval gate state |

Delete `.swarmweaver/` to reset a project; SwarmWeaver will recreate it on the next run.

## Production Deployment

For production, run SwarmWeaver as a server:

| Variable | Purpose |
|----------|---------|
| `ANTHROPIC_API_KEY` | Anthropic API key (required for agent execution) |
| `CLAUDE_CODE_OAUTH_TOKEN` | Claude Code Max OAuth token (alternative to API key) |
| `SWARMWEAVER_CORS_ORIGINS` | Allowed CORS origins (e.g. `https://app.example.com`) |

- Ports: `3000` (Web UI), `8000` (API)
- Mount `./generations` for generated projects
- Health check: `GET /api/doctor`

---

[← Documentation index](README.md) | [CLI Reference →](cli-reference.md)
