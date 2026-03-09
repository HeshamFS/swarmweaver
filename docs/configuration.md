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

## MCP Server Configuration

MCP (Model Context Protocol) servers extend agent capabilities with external tools. SwarmWeaver uses a **two-level config merge** so you can set global defaults and override per project.

### Config Files

| File | Scope | Purpose |
|------|-------|---------|
| `~/.swarmweaver/mcp_servers.json` | Global | Applies to all projects |
| `.swarmweaver/mcp_servers.json` | Project | Overrides global settings for this project |

Project-level entries override global entries with the same name. Both files use the same JSON format:

```json
{
  "servers": {
    "my-database": {
      "command": "npx",
      "args": ["my-db-mcp-server", "--connection", "postgresql://..."],
      "enabled": true
    }
  }
}
```

### Built-in Servers

Two servers are always available without configuration:
- **puppeteer** — Browser automation for UI testing (`npx puppeteer-mcp-server`)
- **web_search** — Web search via `web_search_server.py`

### Managing Servers

Servers can be managed three ways:
- **CLI**: `swarmweaver mcp list|add|remove|enable|disable|test`
- **REST API**: `GET/POST/PUT/DELETE /api/mcp/servers` plus enable, disable, test, validate, import, and export endpoints
- **Web UI**: MCPPanel in Settings

All enabled MCP servers are automatically loaded into every agent session — single agent, swarm workers, and smart orchestrator all get the same set of servers.

### Import / Export

Export your MCP server config for sharing or backup:
- **CLI/API**: `GET /api/mcp/export` returns the merged config; `POST /api/mcp/import` loads a config file

## Watchdog Configuration: watchdog.yaml

The watchdog health monitor is configured via `.swarmweaver/watchdog.yaml`. All values can also be set via environment variables prefixed with `WATCHDOG_`.

```yaml
# .swarmweaver/watchdog.yaml
enabled: true
check_interval_s: 30.0        # How often to check worker health
idle_threshold_s: 120.0        # Seconds of no output before IDLE
stall_threshold_s: 300.0       # Seconds of no output before STALLED
zombie_threshold_s: 600.0      # Seconds before considering worker a ZOMBIE
boot_grace_s: 60.0             # Grace period for newly spawned workers
nudge_interval_s: 60.0         # Minimum time between nudges
max_nudge_attempts: 3          # Max nudges before escalating to triage
ai_triage_enabled: true        # Use LLM for stall analysis
triage_timeout_s: 30.0         # Timeout for AI triage calls
triage_context_lines: 50       # Lines of output to include in triage context
triage_model: ""               # Model for triage (empty = use WORKER_MODEL)
auto_reassign: true            # Auto-reassign tasks from terminated workers
circuit_breaker_enabled: true  # Enable cascade failure prevention
max_failure_rate: 0.5          # Failure rate threshold to open circuit breaker
circuit_breaker_window_s: 600.0  # Sliding window for failure rate calculation
persistent_roles:              # Roles exempt from stall detection
  - coordinator
  - monitor
```

Environment variable overrides use the `WATCHDOG_` prefix:
```bash
WATCHDOG_STALL_THRESHOLD_S=600       # Override stall threshold
WATCHDOG_AI_TRIAGE_ENABLED=false     # Disable AI triage
WATCHDOG_MAX_FAILURE_RATE=0.3        # Stricter circuit breaker
```

Live editing via API: `PUT /api/watchdog/config` (merges with existing config).

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
| `mcp_servers.json` | Project-level MCP server config (merged with global) |
| `mail.db` | Inter-agent mail database (SQLite WAL mode) |
| `watchdog.yaml` | Watchdog health monitor configuration |
| `watchdog_events.db` | Persistent watchdog event log (SQLite) |

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
