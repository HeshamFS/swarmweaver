# Inter-Agent Mail System

SwarmWeaver's mail system provides SQLite-backed messaging for swarm worker coordination. Workers, orchestrators, and the watchdog communicate through typed messages with protocol payloads, attachments, rate limiting, and analytics.

## Overview

| Feature | Details |
|---------|---------|
| Storage | `.swarmweaver/mail.db` (SQLite WAL mode) |
| Message types | 15 typed categories |
| Priorities | low, normal, high, urgent |
| Attachments | file_diff, code_snippet, task_list, error_trace (5KB max) |
| Rate limiting | 20 msgs/min for low/normal; high/urgent bypass |
| Dead letters | Failed messages preserved with failure reason |
| Context injection | Unread mail auto-injected into agent prompts |

## Message Types

| Type | Direction | Purpose |
|------|-----------|---------|
| `dispatch` | Orchestrator → Worker | Task assignment with file scope |
| `assign` | Orchestrator → Worker | Single task assignment |
| `directive` | Orchestrator → Worker | Guidance or steering |
| `task_reassigned` | Orchestrator → Worker | Task moved between workers |
| `worker_done` | Worker → Orchestrator | Task completion signal |
| `worker_progress` | Worker → Orchestrator | Periodic status update |
| `status` | Worker → Orchestrator | Current state report |
| `question` | Worker → Orchestrator | Question requiring answer |
| `result` | Worker → Orchestrator | Task result |
| `error` | Worker → Orchestrator | Error report |
| `merge_ready` | Worker → Orchestrator | Branch ready to merge |
| `merged` | System → Worker | Branch merged successfully |
| `merge_failed` | System → Worker | Merge failed with conflicts |
| `escalation` | Watchdog → Orchestrator | Stalled/dead worker alert |
| `health_check` | Watchdog → Worker | Periodic health check |

## Protocol Payloads

Messages carry typed payloads validated against schemas:

```python
# dispatch payload
{"task_ids": ["t1", "t2"], "file_scope": ["src/*.py"], "worktree_path": "...", "role": "builder"}

# worker_done payload
{"status": "success", "tasks_completed": 3, "branch": "swarmweaver/worker-1"}

# error payload
{"error_type": "ImportError", "stack_trace": "...", "tool_name": "Bash"}

# escalation payload
{"worker_id": "worker-3", "elapsed_seconds": 450, "escalation_level": 2}
```

Use `send_protocol()` for schema-validated sends (raises `ValueError` on missing required fields).

## Attachments

Messages can carry attachments (max 5KB each, truncated if oversized):

| Type | Content |
|------|---------|
| `file_diff` | Unified diff of file changes |
| `code_snippet` | Relevant code excerpt |
| `task_list` | Serialized task list JSON |
| `error_trace` | Full error stack trace |

## Context Injection

Agents receive unread mail automatically via the `mail_injection_hook` (PostToolUse, every 5 tool calls):

1. `format_for_injection(agent_name)` fetches unread messages
2. Formats as human-readable text with sender, type, priority, subject, body
3. Long threads (>5 messages) are auto-summarized
4. Formatted messages are marked as read
5. Returns empty string if no unread mail

## Escalation and Reminders

- **Urgent** messages escalate after 5 minutes if unread
- **High** messages escalate after 15 minutes if unread
- Max 3 reminders per original message (prefixed `[REMINDER x#]`)
- `check_escalations()` returns list of reminder message IDs

## Dead Letter Queue

Messages that fail rate limiting go to the dead letter queue:

- `get_dead_letters(limit=50)` — Retrieve dead-lettered messages with reason
- `retry_dead_letter(dl_id)` — Re-send a dead-lettered message

## Group Addressing

Broadcast to groups of workers:

- `@all` — All workers
- `@builders` — All builder-role workers
- `@reviewers` — All reviewer-role workers
- `@scouts` — All scout-role workers

`broadcast()` creates individual messages per recipient.

## Analytics

`get_analytics()` returns:
- Total and unread message counts
- Breakdown by message type
- Top 10 senders by volume
- Unread bottlenecks per recipient
- Average response time (threads with replies)
- Dead letter count

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/swarm/mail` | List messages (filters: recipient, type, unread) |
| POST | `/api/swarm/mail/read` | Mark messages read |
| GET | `/api/swarm/mail/analytics` | Mail analytics dashboard |

## CLI Commands

```bash
swarmweaver mail list   -p DIR [--unread] [-r RECIPIENT] [-t TYPE]
swarmweaver mail send   -p DIR --to NAME --subject TEXT [--body TEXT] [--type TYPE] [--priority LEVEL]
swarmweaver mail read   -p DIR MSG_ID                    # Mark single message read
swarmweaver mail read   -p DIR --all RECIPIENT           # Mark all read
swarmweaver mail thread -p DIR THREAD_ID                 # Show conversation thread
swarmweaver mail stats  -p DIR                           # Analytics
swarmweaver mail purge  -p DIR --days 7 --yes            # Delete old read messages
```

## WebSocket Events

| Event | When |
|-------|------|
| `mail_received` | New message sent (via `on_send` callback) |

## Frontend

The Swarm panel's **Mail** tab shows:
- Message list with type badges, priority indicators, read status
- Thread view for conversation chains
- Attachment rendering (diffs, code snippets, error traces)
- Analytics mini-dashboard (totals, top senders, response times, dead letters)
- Real-time updates via WebSocket `mail_received` events

## Testing

```bash
pytest tests/test_mail_expanded.py -v   # 59 tests
```

---

[← Watchdog](watchdog.md) | [LSP Code Intelligence →](lsp.md)
