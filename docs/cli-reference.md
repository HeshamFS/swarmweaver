# CLI Reference

Full reference for the SwarmWeaver command-line interface.

See [getting-started.md](getting-started.md) for installation and first run. See [overview.md](overview.md) for mode descriptions.

## Installation

```bash
uv sync                 # install all deps + register swarmweaver CLI
swarmweaver --help      # list all commands
python -m cli --help    # alternative invocation
```

## Commands

### Core Operation Modes

```bash
swarmweaver greenfield  --project-dir DIR [--spec FILE]
swarmweaver feature     --project-dir DIR --description TEXT [--spec FILE]
swarmweaver refactor    --project-dir DIR --goal TEXT
swarmweaver fix         --project-dir DIR --issue TEXT
swarmweaver evolve      --project-dir DIR --goal TEXT
swarmweaver security    --project-dir DIR [--focus TEXT]
```

### Session Management

```bash
swarmweaver status      --project-dir DIR          # show task list and current phase
swarmweaver steer       --project-dir DIR TEXT     # send instruction to running session
swarmweaver logs        --project-dir DIR         # tail agent output log
```

### Worktree & Merge

```bash
swarmweaver merge       --project-dir DIR         # merge completed worktree branch
swarmweaver checkpoint  --project-dir DIR [--restore ID]  # list or restore checkpoints
```

### Project Initialization

```bash
swarmweaver init        --project-dir DIR        # bootstrap .swarmweaver/ scaffold
```

### MCP Server Management

Manage MCP (Model Context Protocol) servers that extend agent capabilities. Configured servers are automatically loaded into every agent session.

```bash
swarmweaver mcp list                              # list all configured MCP servers (built-in + user)
swarmweaver mcp add NAME --command "CMD"          # add a new MCP server
swarmweaver mcp remove NAME                       # remove an MCP server
swarmweaver mcp enable NAME                       # enable a disabled server
swarmweaver mcp disable NAME                      # disable a server without removing it
swarmweaver mcp test NAME                         # test server connectivity
```

Servers are stored in two config files that are merged at runtime:
- `~/.swarmweaver/mcp_servers.json` — global (applies to all projects)
- `.swarmweaver/mcp_servers.json` — project-level (overrides global for that project)

Two built-in servers (puppeteer, web_search) are always available. Use `swarmweaver mcp add` to register additional servers like databases, custom APIs, or specialized tools.

## Common Flags

| Flag | Description | Default |
|------|-------------|---------|
| `--project-dir` | Target project directory | Required |
| `--max-iterations` | Max agent sessions | Unlimited |
| `--model` | Claude model | `claude-sonnet-4-6` |
| `--parallel N` | Static swarm with N workers | 1 (single agent) |
| `--smart-swarm` | AI-orchestrated swarm (dynamic workers) | Off |
| `--worktree` | Run in isolated git worktree | Off |
| `--no-resume` | Start fresh, ignore saved session | Resume by default |
| `--interactive` | Prompt for steering after each phase | Off |
| `--json` | Output structured JSON instead of rich text | Off |
| `--server URL` | Delegate execution to a running SwarmWeaver server | Off |

## Output Modes

```bash
swarmweaver feature --project-dir ./app --description "..." --json          # machine-readable output
swarmweaver feature --project-dir ./app --description "..." --interactive   # pause between phases
```

## Connected Mode

Point the CLI at a running server instead of running locally:

```bash
export SWARMWEAVER_URL=http://my-server:8000
swarmweaver feature --project-dir ./app --description "Add search"
```

Or set it in `~/.swarmweaver/config.toml`:

```toml
[server]
url = "http://my-server:8000"

[defaults]
model = "claude-sonnet-4-6"
max_iterations = 10
```

See [configuration.md](configuration.md) for full config reference.

## Examples

```bash
# Greenfield: build from a spec file
swarmweaver greenfield --project-dir ./my_app --spec ./spec.txt

# Greenfield: use the built-in default spec
swarmweaver greenfield --project-dir ./my_app

# Feature: from description
swarmweaver feature --project-dir ./my_app \
  --description "Add a user settings page with dark mode and notifications"

# Feature: from spec file
swarmweaver feature --project-dir ./my_app --spec ./feature_spec.txt

# Refactor: language migration
swarmweaver refactor --project-dir ./my_app \
  --goal "Migrate from JavaScript to TypeScript with strict mode"

# Fix: targeted bug
swarmweaver fix --project-dir ./my_app \
  --issue "Login fails when email contains a plus sign — returns 400 on POST /api/auth/login"

# Worktree isolation (merge or discard on completion)
swarmweaver feature --project-dir ./my_app --description "Add OAuth2" --worktree

# Static swarm: 3 parallel workers
swarmweaver feature --project-dir ./my_app --description "Add dashboard" --parallel 3

# Smart Swarm: AI-orchestrated workers
swarmweaver feature --project-dir ./my_app --description "Add dashboard" --smart-swarm
```

### Inter-Agent Mail

Inspect and manage the inter-agent mail system used for swarm coordination. Messages are stored in `.swarmweaver/mail.db`.

```bash
swarmweaver mail list    -p DIR                   # list all messages (newest first)
swarmweaver mail list    -p DIR --unread           # only unread messages
swarmweaver mail list    -p DIR -r worker-1        # filter by recipient
swarmweaver mail list    -p DIR -t dispatch         # filter by message type
swarmweaver mail send    -p DIR --to worker-1 --subject "New task" --body "Handle API" --type dispatch --priority high
swarmweaver mail read    -p DIR MSG_ID              # mark single message as read
swarmweaver mail read    -p DIR --all worker-1      # mark all messages read for a recipient
swarmweaver mail thread  -p DIR THREAD_ID           # show conversation thread chronologically
swarmweaver mail stats   -p DIR                     # analytics: totals, top senders, unread bottlenecks, response times
swarmweaver mail purge   -p DIR --days 7 --yes      # delete read messages older than 7 days
```

Message types: `dispatch`, `worker_done`, `worker_progress`, `error`, `escalation`, `merged`, `merge_failed`, `directive`, `status`, `task_reassigned`, `assign`, `log`, `heartbeat`, `query`, `response`.

Priority levels: `low`, `normal`, `high`, `urgent`.

### Watchdog Health Monitoring

Monitor swarm worker health, view events, and manage the watchdog configuration.

```bash
# Fleet overview: health score, worker states, circuit breaker, recent events
swarmweaver watchdog status  -p DIR

# Query event log (state changes, nudges, triage, terminations)
swarmweaver watchdog events  -p DIR                   # last 20 events
swarmweaver watchdog events  -p DIR --worker-id 3     # events for worker 3
swarmweaver watchdog events  -p DIR --type triage      # only triage events
swarmweaver watchdog events  -p DIR --limit 50         # more events

# Show or edit watchdog configuration
swarmweaver watchdog config  -p DIR                   # show current config as JSON
swarmweaver watchdog config  -p DIR --set stall_threshold_s=600   # change a value

# On-demand AI triage for a specific worker
swarmweaver watchdog triage  WORKER_ID -p DIR

# Send a nudge to a stuck worker
swarmweaver watchdog nudge   WORKER_ID -p DIR
swarmweaver watchdog nudge   WORKER_ID -p DIR -m "Please check test failures"
```

Events are stored in `.swarmweaver/watchdog_events.db` (SQLite). Configuration is stored in `.swarmweaver/watchdog.yaml`.

### LSP Code Intelligence

Manage LSP language servers and inspect diagnostics. Requires an active or recent swarm session.

```bash
# Show running LSP servers and their status
swarmweaver lsp status  -p DIR

# View diagnostics (errors, warnings) across all files
swarmweaver lsp diagnostics  -p DIR                     # all diagnostics
swarmweaver lsp diagnostics  -p DIR -s error             # errors only
swarmweaver lsp diagnostics  -p DIR -f "src/api/**"      # filter by file pattern
swarmweaver lsp diagnostics  -p DIR -n 20                # limit to 20 entries

# List all 22 available language server specs
swarmweaver lsp servers  -p DIR

# View or edit LSP configuration
swarmweaver lsp config  -p DIR                           # show current config as JSON
swarmweaver lsp config  -p DIR --set auto_install=false  # change a setting

# Restart a specific language server
swarmweaver lsp restart  -p DIR                          # restart all servers
swarmweaver lsp restart  pyright -p DIR                  # restart specific server
```

Configuration is stored in `.swarmweaver/lsp.yaml`. See [configuration.md](configuration.md) for full reference.

## Legacy Invocation

For backward compatibility:

```bash
python autonomous_agent_demo.py feature --project-dir ./app --description "..."
```

This delegates to `cli/main.py` internally.

---

[← Documentation index](README.md) | [Configuration →](configuration.md)
