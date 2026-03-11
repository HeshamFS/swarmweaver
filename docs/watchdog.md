# Watchdog Health Monitoring

The SwarmWeaver watchdog provides production-grade health monitoring for multi-agent swarm workers. It detects stalls, performs AI-powered triage, and prevents cascading failures.

## 3-Tier Architecture

| Tier | Component | Purpose |
|------|-----------|---------|
| **Tier 0** | Mechanical Daemon | Periodic health checks (every 30s), state transitions, nudges |
| **Tier 1** | AI Triage | Ephemeral Claude session analyzes stalled workers with 7 data sources |
| **Tier 2** | Monitor Agent | Orchestrator can request on-demand triage via MCP tool |

## 9-State Forward-Only State Machine

```
BOOTING → WORKING → IDLE → WARNING → STALLED → RECOVERING → COMPLETED
                                                    ↓
                                                TERMINATED
Any state → ZOMBIE (PID dead) → TERMINATED
```

| State | Description |
|-------|-------------|
| BOOTING | Just spawned, not yet producing output |
| WORKING | Active, producing output |
| IDLE | No activity for 120s (configurable) but not stalled |
| WARNING | Approaching stall threshold (70% of stall_threshold) |
| STALLED | No activity for 300s (configurable) |
| RECOVERING | Recovering from stall after nudge |
| COMPLETED | Task completed successfully |
| ZOMBIE | Process dead but not properly cleaned up |
| TERMINATED | Intentionally stopped |

Transitions are **forward-only** — states never move backward, except RECOVERING can re-enter STALLED on failure. Invalid transitions are rejected.

## 6-Signal Health Evaluation

The watchdog evaluates worker health using 6 independent signals (in priority order):

1. **asyncio.Task status** — Is the worker task still running?
2. **PID liveness** — Is the worker process alive? (via `psutil`)
3. **Output freshness** — Time since last stdout/stderr
4. **Tool call activity** — Time since last MCP tool call
5. **Git activity** — Recent commits in worker's worktree
6. **Heartbeat protocol** — Active heartbeat messages from worker via mail

The watchdog takes the **minimum effective elapsed time** across signals 3-6, so progress on any signal resets the timer.

## Circuit Breaker

Prevents cascading failures from draining budget:

| State | Behavior |
|-------|----------|
| **CLOSED** | Normal operation, spawning allowed |
| **OPEN** | >50% failure rate, spawning blocked |
| **HALF_OPEN** | Tentatively allow one spawn after 120s cooldown |

Parameters: `max_failure_rate=0.5`, sliding window of 600s.

## AI Triage

When a worker enters STALLED state, AI triage analyzes 7 context sources:

1. Worker ID and role
2. Assigned task IDs and completion status
3. Last 50 lines of output buffer
4. Recent tool call history with names and timing
5. Warning log entries (errors, loops, repeated messages)
6. Worker resource usage (CPU, memory via psutil)
7. Escalation history (previous nudges and triage calls)

### Verdicts

| Verdict | Meaning | Action |
|---------|---------|--------|
| `retry` | Worker might recover | Send nudge message |
| `extend` | Worker is slow but progressing | Extend timeout |
| `reassign` | Redistribute tasks | Move tasks to other workers |
| `terminate` | Worker is stuck | Kill worker process |

Each verdict includes: reasoning, recommended action, confidence (0-1), and suggested nudge message or tasks to reassign.

**Fallback heuristic triage** (when LLM unavailable): detects loops (>10min), persistent errors (3+ escalations), progress signals (commits/tests in output), stall duration.

## Escalation Levels

| Level | Action | Condition |
|-------|--------|-----------|
| 0 | Monitor | Worker detected as STALLED |
| 1 | Nudge | Send nudge message (max 3 attempts, 60s apart) |
| 2 | AI Triage | Run LLM analysis, execute verdict |
| 3 | Terminate | Kill worker, reassign tasks (if `auto_reassign=True`) |

Escalation is **dependency-aware** — workers blocking others are prioritized.

## Configuration

Located at `.swarmweaver/watchdog.yaml`, editable at runtime via API or CLI:

```yaml
enabled: true
check_interval_s: 30.0
idle_threshold_s: 120.0
stall_threshold_s: 300.0
zombie_threshold_s: 600.0
boot_grace_s: 60.0
nudge_interval_s: 60.0
max_nudge_attempts: 3
ai_triage_enabled: true
triage_timeout_s: 30.0
triage_context_lines: 50
triage_model: ""                  # empty = use WORKER_MODEL
auto_reassign: true
circuit_breaker_enabled: true
max_failure_rate: 0.5
circuit_breaker_window_s: 600.0
persistent_roles:
  - coordinator
  - monitor
```

Environment variable overrides use the `WATCHDOG_` prefix (e.g., `WATCHDOG_STALL_THRESHOLD_S=600`).

## Persistent Event Log

All state transitions, nudges, triage results, and terminations are recorded in `.swarmweaver/watchdog_events.db` (SQLite).

**Event types:** `state_transition`, `stall_detected`, `triage_triggered`, `triage_complete`, `nudge_sent`, `escalation`, `remediation`, `recovery`, `termination`

Each event records: timestamp, worker_id, event_type, escalation_level, state_before/after, triage_verdict, and rich metadata JSON.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/watchdog/events` | Event log (filters: worker_id, type, limit) |
| GET | `/api/watchdog/config` | Current configuration |
| PUT | `/api/watchdog/config` | Update configuration (merges) |

## CLI Commands

```bash
swarmweaver watchdog status  -p DIR                  # Fleet health, worker states, circuit breaker
swarmweaver watchdog events  -p DIR [--worker-id N] [--type TYPE] [--limit 20]
swarmweaver watchdog config  -p DIR [--set KEY=VALUE]
swarmweaver watchdog triage  WORKER_ID -p DIR        # Manual AI triage
swarmweaver watchdog nudge   WORKER_ID -p DIR [-m MSG]
```

## WebSocket Events

| Event | Data |
|-------|------|
| `watchdog_state_change` | Worker state transition |
| `watchdog_nudge` | Nudge sent to worker |
| `watchdog_triage` | AI triage result with verdict |
| `watchdog_circuit_breaker` | Circuit breaker state change |

## Frontend

The Swarm panel's **Health** tab displays:
- Fleet health score (0-100) with color gradient
- Circuit breaker badge (CLOSED/HALF_OPEN/OPEN)
- Per-worker state cards with role, tasks, last activity, nudge count
- Resource bars (CPU%, Memory MB)
- Quick actions (Nudge with 30s cooldown, Terminate with confirm)
- Triage cards with verdict badge, reasoning, confidence bar
- Escalation timeline (chronological event stream)
- Config editor (collapsible form)

## Testing

```bash
pytest tests/test_watchdog_enhanced.py -v   # 60 tests
```

---

[← Architecture](architecture.md) | [Mail System →](mail.md)
