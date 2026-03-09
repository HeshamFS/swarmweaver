# Web UI

The SwarmWeaver web dashboard provides a visual command center for running and monitoring autonomous coding sessions.

Start with `npm run dev` and open [http://localhost:3000](http://localhost:3000).

## Key Capabilities

### Omnibar Command Center

Type an idea, pick a folder, choose a mode, and launch in one flow. The Omnibar is the primary entry point for starting new runs.

### Multi-Session Tabs

Run multiple projects in parallel. Each tab is fully independent with its own session, task list, and terminal output.

### Project Templates

Five built-in templates for greenfield mode:

- Next.js SaaS
- FastAPI CRUD
- CLI tool
- React dashboard
- Full-stack todo

### Folder Picker

Filesystem navigation with inline new folder creation. Point SwarmWeaver at any directory on your machine.

### Git Worktree Isolation

Toggle "Use worktree" in Advanced Options to run in an isolated git worktree. On completion, merge or discard changes without affecting your main branch.

### Real-Time Terminal

Stream agent output with inline steering. Send instructions to the running agent without stopping the session.

### Task Panel

Live task status with verification badges and dependency graph. See which tasks are done, pending, or blocked.

### Security Scan

Mandatory human review of findings before any fixes are applied. Security mode always requires approval before remediation.

### Approval Gates

Pause the agent for human review at key checkpoints. Approve or reject tasks before the agent proceeds.

### Swarm Panel

When using `--parallel` or `--smart-swarm`, the Swarm panel provides:

- Per-worker controls
- Mail threads between agents
- Merge queue status
- Nudge and terminate buttons

### Observability Panel

Nine sub-tabs for deep inspection:

| Sub-tab | Content |
|---------|---------|
| Timeline | Cross-agent event timeline |
| Files | Files touched during the run |
| Costs | Per-agent, per-model cost breakdown |
| Errors | Filtered error stream |
| Audit | Tool execution log |
| Insights | Session analytics (top tools, hot files) |
| Agents | Agent identity and success rates |
| Checkpoints | File state checkpoints for rollback |
| Profile | Session profiling data |

### Session Replay

Scrub through git commit history with task state snapshots. Replay how the codebase evolved over the session.

### MCP Server Management

The Settings panel includes an MCPPanel for managing MCP (Model Context Protocol) servers. From the Web UI you can:

- View all configured servers (built-in and user-added) with their status
- Add new MCP servers with command and arguments
- Enable or disable servers without removing them
- Test server connectivity
- Remove user-configured servers

Changes apply to all subsequent agent sessions. See [configuration.md](configuration.md) for details on the two-level config merge (global + project).

### Notifications

Configure Slack, Discord, browser push, or generic webhooks to receive alerts when runs complete or fail.

## Layout

The execution dashboard uses a command-center layout with resizable panels:

- **Top status strip** — Health dots, cost, agent count, phase badge
- **Activity sidebar** — Collapsible session list
- **Terminal** — Primary agent output
- **Inspector** — Tabbed: Tasks, ADRs, Notes
- **Observe panel** — Timeline, Files, Costs, Errors, Audit, Insights, Agents, Checkpoints, Profile
- **Floating action bar** — Steering input, stop button, progress

---

[← Documentation index](README.md) | [Configuration →](configuration.md)
