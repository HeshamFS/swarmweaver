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
- Mail threads between agents with attachments (code snippets, diffs, error traces)
- Mail analytics mini-dashboard (total/unread counts, average response time, dead letters, top senders)
- Real-time mail push via WebSocket (`mail_received` events) — instant updates without polling
- Merge queue status
- Nudge and terminate buttons

### Watchdog Health Tab

The Swarm panel includes a **Health** tab (4th tab alongside Workers, Mail, Merges) with a dedicated watchdog dashboard:

- **Fleet Health Score** — 0-100 score with color gradient (green >70, yellow 40-70, red <40) and progress bar
- **Circuit Breaker Badge** — CLOSED (green), HALF_OPEN (yellow), OPEN (red)
- **Worker State Cards** — Per-worker card showing: state badge (9 states with distinct colors, animated pulse for STALLED/RECOVERING), role, current task, last activity time, tasks completed, escalation level, nudge count
- **Resource Bars** — Inline CPU% and Memory MB bars per worker (when available)
- **Quick Actions** — Nudge button (with 30s cooldown timer) and Terminate button (with confirm dialog)
- **Triage Cards** — When AI triage completes: verdict badge (RETRY/EXTEND/REASSIGN/TERMINATE), reasoning text, confidence bar (0-100%)
- **Escalation Timeline** — Chronological event stream with color-coded event types (state changes, nudges, triage, terminations, run completion)
- **Config Editor** — Collapsible form to view and edit all watchdog thresholds, with Save and Reset buttons

Real-time updates via WebSocket events: `watchdog_state_change`, `watchdog_nudge`, `watchdog_triage`, `watchdog_circuit_breaker`, `run_complete`.

### Observability Panel

Eleven sub-tabs for deep inspection:

| Sub-tab | Content |
|---------|---------|
| Timeline | Cross-agent event timeline |
| Files | Files touched during the run |
| Costs | Per-agent, per-model cost breakdown |
| Errors | Filtered error stream |
| Audit | Tool execution log |
| Insights | Session analytics (top tools, hot files) |
| Agents | Agent identity and success rates |
| Checkpoints | File state checkpoints + shadow git snapshot timeline (see below) |
| Sessions | Persistent session browser with full detail view (see below) |
| Profile | Session profiling data |
| Code Intel | LSP diagnostic dashboard (see below) |

### Sessions Tab

Browse all persistent session records with:

- **Session list** — Mode badges, status dots (running/completed/error/archived), cost, duration, task progress bar
- **Filter bar** — Filter by mode (chips) and status
- **Session detail view** — Click any session to see three sub-tabs:
  - **Timeline** — Phase transitions and agent turns
  - **Messages** — Prompt/response pairs with token counts and cost per turn
  - **Files** — Changed files with additions/deletions stats

Data from `/api/sessions` endpoints. Real-time updates via WebSocket events: `session_db_created`, `session_db_updated`, `session_db_completed`.

### Snapshot Panel

The Checkpoints tab includes a snapshot panel with two views (toggle between Timeline and Bookmarks):

**Timeline view:**
- **Snapshot pairs** — Pre/post snapshots per iteration, grouped by phase with color-coded badges
- **Compare button** — Opens a diff drawer between pre and post snapshots of any iteration
- **Bookmark button** — Pin a snapshot with a name and description; bookmarked snapshots show a star indicator
- **Restore button** — Opens a preview modal showing what would change, then confirm to restore
- **Diff drawer** — Slide-out panel with:
  - File list with additions/deletions stats and status indicators (A/M/D)
  - Expandable per-file unified diffs with syntax coloring
  - Multi-select checkboxes for batch file selection
  - Revert button to surgically restore selected files from a snapshot

**Bookmarks view:**
- **Bookmark list** — Named snapshots with descriptions, phase badges, tree hash, file counts
- **Restore button** — Preview and confirm restore to a bookmarked state
- **Remove button** — Delete a bookmark (the underlying snapshot is preserved)

**Status bar** — Snapshot count, bookmark count, and shadow repo size in MB. Auto-refreshes every 10 seconds while running.

Data from `/api/snapshots` endpoints (13 total). Real-time updates via WebSocket `snapshot_captured` event.

### Code Intel Tab (LSP)

The Code Intel tab in the Observability panel provides a full LSP diagnostic dashboard:

- **Code Health Bar** — Project-wide score (0–100) with green/amber/red gradient, per-language badges, and sparkline trend
- **Diagnostics Table** — Sortable/filterable by file, line, severity, message, source, worker. Severity badges: ERROR (red pulse), WARNING (amber), INFO (blue), HINT (gray)
- **LSP Servers** — Card per server showing language, status badge, file count, diagnostic count, with restart button
- **Per-Worker Diagnostics** — Mini card per worker with error/warning counts and cross-worker conflict indicators (swarm mode only)
- **Impact Visualization** — On-demand symbol search showing callers/callees tree with cross-worker edges

Worker cards in the Swarm panel also show inline diagnostic badges (errors/warnings) from LSP data.

Real-time updates via WebSocket events: `lsp.diagnostics_update`, `lsp.server_status`, `lsp.code_health`, `lsp.cross_worker_alert`, `lsp.merge_validation`.

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
- **Observe panel** — Timeline, Files, Costs, Errors, Audit, Insights, Agents, Checkpoints, Sessions, Profile, Code Intel
- **Floating action bar** — Steering input, stop button, progress

---

[← Documentation index](README.md) | [Configuration →](configuration.md)
