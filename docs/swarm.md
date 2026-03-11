# Multi-Agent Swarm Orchestration

SwarmWeaver supports three execution modes: single-agent, static swarm, and AI-orchestrated smart swarm. This document covers the multi-agent swarm systems.

## Execution Modes

| Mode | Trigger | Components | Best For |
|------|---------|------------|----------|
| Single Agent | Default | `Engine` → Claude SDK | Small features, bug fixes |
| Static Swarm | `--parallel N` | `SwarmOrchestrator` → N workers | Medium features, known scope |
| Smart Swarm | `--smart-swarm` | `SmartOrchestrator` → dynamic workers | Large, complex features |

## Architecture

| Component | File | Purpose |
|-----------|------|---------|
| Swarm Entry | `core/swarm.py` | Swarm + SmartSwarm entry points |
| Static Orchestrator | `core/orchestrator.py` | N workers in worktrees with static task distribution |
| Smart Orchestrator | `core/smart_orchestrator.py` | AI-orchestrated dynamic workers |
| Merge Resolver | `core/merge_resolver.py` | 4-tier merge conflict resolution |
| Merge Queue | `core/merge_queue.py` | SQLite FIFO merge queue |
| Orchestrator Tools | `core/orchestrator_tools.py` | 10 MCP tools for SmartOrchestrator |
| Worker Tools | `core/worker_tools.py` | MCP tools for swarm workers |
| Partitioner | `services/partitioner.py` | Task partitioning strategies |
| Scope Enforcement | `hooks/scope_enforcement.py` | File scope validation |

## Static Swarm

### Workflow

1. **`setup_worktrees()`** — Create N git worktrees on branches `swarmweaver/worker-1`, etc.
2. **`distribute_tasks()`** — Partition tasks by file overlap; assign subsets to workers
3. **Workers run** — Each worker runs as an `Engine` instance in its worktree
4. **Merge** — Completed branches merged via merge queue
5. **`cleanup_worktrees()`** — Remove merged worktrees

### Agent Hierarchy

For 3+ workers, `HierarchyManager` creates a hierarchy:
- 1 **Lead** agent (coordination, task splitting)
- N-1 **Builder** agents (implementation within file scope)
- Maximum depth of 2 levels
- 2-second stagger delay between worker spawns

### File Scope Isolation

Each worker gets assigned file patterns (e.g., `['src/components/*.tsx', 'src/hooks/*.ts']`). The `capability_enforcement_hook` blocks writes outside a worker's scope.

## Smart Swarm

### How It Differs

| Aspect | Static Swarm | Smart Swarm |
|--------|-------------|-------------|
| Worker count | Fixed N | AI-determined (1-50) |
| Task assignment | Pre-partitioned | Dynamic, reassignable |
| Merge timing | After all complete | Progressive (on completion) |
| Rebalancing | None | Automatic work-stealing |
| Communication | Mail only | Mail + orchestrator polling |

### Orchestrator as AI Agent

The SmartOrchestrator runs as a Claude SDK session with 10 custom MCP tools. Every 30 seconds, it re-evaluates worker status and decides actions.

### Complexity Analysis

Before spawning workers, `TaskComplexityAnalyzer` scores tasks:
- Simple keywords (css, style, rename, docs) → 1 point
- Complex keywords (auth, database, refactor, deployment) → 5 points
- File count: 6+ files or 3+ dependencies → complex
- Recommended workers: complexity_score / 30 capacity points

### MCP Tools for Orchestrator

| Tool | Purpose |
|------|---------|
| `spawn_worker` | Create worktree, assign tasks, inject role overlay |
| `list_workers` | Status, role, tasks, file scope, tool calls per worker |
| `get_worker_updates` | Poll mail for worker messages |
| `merge_worker` | Invoke 4-tier merge resolver for a worker's branch |
| `terminate_worker` | Stop worker, release tasks back to pool |
| `reassign_tasks` | Move tasks between workers |
| `get_task_status` | Task counts by status, per-worker assignments |
| `send_directive` | Write steering message to worker |
| `get_lessons` | Error clusters from MELS synthesizer |
| `add_lesson` | Record lesson for future workers |

## Worker Lifecycle

### Spawning
1. Create git worktree at `.swarmweaver/swarm/worker-N`
2. Generate enhanced overlay from `templates/overlay.md.tmpl` with task scope, file scope, role
3. Create Engine instance with worker-specific context
4. Launch `asyncio.Task` running `engine.run()`
5. Stagger: 2-second delay between spawns

### Running
- Worker processes assigned tasks sequentially
- Sends heartbeat mail every 10 tool calls
- Posts task completion messages to orchestrator
- LSP diagnostics injected post-edit via hooks

### Completion
1. Worker sends `worker_done` mail
2. Orchestrator calls `merge_worker` tool
3. 4-tier merge resolver processes branch
4. Quality gates validate merged code
5. Worker marked completed; tasks freed

### Termination
- Orchestrator calls `terminate_worker` with reason
- asyncio.Task cancelled, PID killed
- Tasks reassigned to pending pool or other workers

## Progressive Merge

In Smart Swarm, workers are merged **immediately on completion** (not waiting for all to finish):

1. Worker completes → branch merged via 4-tier resolver
2. **Work-stealing:** If remaining worker has 3+ more tasks than average, tasks redistributed
3. **Coordination requests:** Workers post needs to `.orchestrator/coordination_requests.json`
4. **Quality gates:** Post-merge validation (npm test, pytest, TypeScript, linters)

## 4-Tier Merge Resolution

When git merge produces conflicts, the resolver escalates through 4 tiers:

| Tier | Strategy | Cost | How It Works |
|------|----------|------|-------------|
| 1. Clean | Git merge | Free | Standard git merge — succeeds ~70% for non-overlapping scopes |
| 2. Auto-Resolve | Regex | Free | Parse conflict markers, keep incoming changes |
| 3. AI-Resolve | Claude CLI | ~1 API call | Send conflict to Claude for semantic merge |
| 4. Reimagine | Claude CLI | ~1 API call | Abort merge, get both versions, reimplement from scratch |

**History tracking:** Resolution tiers recorded in `merge_history.json`. If tier N has failed 3+ times on similar files, it's skipped in favor of N+1.

## Merge Queue

SQLite FIFO queue at `.swarm/merge_queue.db` ensures ordered, tracked merging:

| Status | Meaning |
|--------|---------|
| `pending` | Awaiting merge |
| `merging` | Merge in progress |
| `merged` | Successfully merged |
| `conflict` | Conflict detected, escalating |
| `failed` | All 4 tiers failed |

## Scope Enforcement

Workers are restricted to their assigned file scope:

- **Builder:** Write/Edit only within FILE_SCOPE (glob matching)
- **Scout/Reviewer:** Read-only (no writes)
- **Lead:** Coordination files only (task_list.json, swarm_plan.json)

Shared files (needed by multiple workers) are queued to `.orchestrator/shared_file_queue.json` for coordinated access.

## Quality Gates

Post-merge validations run automatically:

- `npm test` — JavaScript/TypeScript projects
- `pytest` — Python projects
- TypeScript compilation — Check for TS errors
- Linter validation — prettier/eslint if configured

On failure: merge flagged, orchestrator reviews or re-opens for fixes.

## Inter-Agent Communication

Workers communicate through the [mail system](mail.md):
- Typed messages with protocol payloads
- Attachments: file diffs, code snippets, error traces
- Orchestrator polls every 30 seconds
- Context injection: unread mail injected into agent prompts every 5 tool calls

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/swarm/status` | Orchestrator and worker status |
| GET | `/api/swarm/merge-queue` | Pending merges |
| POST | `/api/swarm/workers/{id}/nudge` | Send nudge message |
| POST | `/api/swarm/workers/{id}/terminate` | Terminate worker |
| GET | `/api/team/status` | SmartOrchestrator worker status |
| GET | `/api/team/partitions` | Task partitions |
| GET | `/api/team/scope-map` | File ownership map |
| GET | `/api/team/costs` | Per-agent cost tracking |

## CLI Usage

```bash
# Static swarm: 3 parallel workers
swarmweaver feature --project-dir ./app --description "Add dashboard" --parallel 3

# Smart swarm: AI-orchestrated
swarmweaver feature --project-dir ./app --description "Add dashboard" --smart-swarm

# Merge completed worktree
swarmweaver merge --project-dir ./app
```

## WebSocket Events

| Event | When |
|-------|------|
| `team_partition` | Task distribution across workers |
| `agent_spawned` | Worker launched |
| `agent_completed` | Worker finished |
| `agent_merged` | Branch merged |
| `rebalance` | Tasks redistributed |
| `team_complete` | All workers finished |
| `ws_quality_gate_result` | Post-merge validation result |

## Frontend

The **Swarm panel** provides 4 tabs:
- **Workers** — Per-worker cards with status, role, tasks, controls (nudge/terminate)
- **Mail** — Message threads with attachments and analytics
- **Merges** — Merge queue status and resolution history
- **Health** — Watchdog dashboard (see [watchdog.md](watchdog.md))

**Team mode UI** adds:
- `AgentSwitcher` — Tab bar for switching between agent outputs
- `MultiTerminalGrid` — CSS grid of terminals per agent
- Per-agent cost tracking in floating action bar

## Testing

```bash
pytest tests/test_orchestrator.py -v   # 74 tests
```

---

[← LSP](lsp.md) | [Security →](security.md)
