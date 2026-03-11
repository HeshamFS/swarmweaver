# Session History & Shadow Git Snapshots

SwarmWeaver includes two complementary persistence systems that work together:

1. **Persistent Session Database** — SQLite-backed store recording every session, agent turn, and file change
2. **Shadow Git Snapshot System** — Separate git repo capturing full project state before/after each agent turn

## Session Database

### Overview

Every `Engine.run()` or `SmartOrchestrator.run()` invocation creates a persistent session record in `.swarmweaver/sessions.db`. The database tracks:

- Session lifecycle (running, completed, stopped, error, archived)
- Per-turn message records with token counts, cost, duration, and snapshot hashes
- File changes computed via `git diff` on session completion
- Cumulative cost tracking across all turns
- Multi-agent awareness (team sessions with per-worker messages)

A **cross-project index** at `~/.swarmweaver/sessions.db` aggregates session metadata from all projects for global analytics.

### Architecture

| Component | File | Purpose |
|-----------|------|---------|
| SessionStore | `state/sessions.py` | Project-local session database (SQLite WAL mode) |
| GlobalSessionIndex | `state/sessions.py` | Cross-project session index at `~/.swarmweaver/sessions.db` |
| Session History API | `api/routers/session_history.py` | 9 REST endpoints |
| SessionBrowserPanel | `frontend/app/components/SessionBrowserPanel.tsx` | Session list + detail view |

### Database Schema

Three tables in `.swarmweaver/sessions.db`:

- **sessions** — One row per run: mode, model, status, task progress, change summary (files added/modified/deleted, lines added/deleted), cumulative cost, timestamps, team metadata
- **messages** — One row per agent turn: agent name, phase, role, token counts, cost, model, duration, snapshot hashes (before/after)
- **file_changes** — One row per changed file: path, change type, additions, deletions

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/sessions` | List sessions (filters: status, mode, limit, offset) |
| GET | `/api/sessions/{id}` | Full session detail (session + messages + file_changes) |
| GET | `/api/sessions/{id}/messages` | Messages for a session |
| GET | `/api/sessions/{id}/files` | File change list |
| POST | `/api/sessions/{id}/archive` | Archive (soft-delete) |
| DELETE | `/api/sessions/{id}` | Delete session + all related data |
| GET | `/api/sessions/analytics` | Session analytics (total, avg cost, by mode/status) |
| GET | `/api/sessions/global` | Cross-project session list |
| POST | `/api/sessions/migrate` | Trigger chain-to-sessions migration |

### WebSocket Events

| Event | When | Data |
|-------|------|------|
| `session_db_created` | Session record created | `{session_id, mode, model}` |
| `session_db_updated` | After each turn is recorded | Session stats |
| `session_db_completed` | Session finishes | Change summary |

### Chain Migration

Existing `.swarmweaver/chains/*.json` files from the legacy chain system are automatically migrated to session records. Call `POST /api/sessions/migrate` or `SessionStore.migrate_from_chains()` to trigger migration manually. Migration is idempotent — duplicate entries are skipped.

---

## Shadow Git Snapshots

### Overview

A separate git repository at `~/.swarmweaver/snapshots/<project_hash>/` captures the full project state before and after each agent turn. This enables:

- **Rich diffs** between any two snapshots
- **Per-file revert** — surgically restore individual files from any snapshot
- **Full restore** — restore entire project state to a previous snapshot
- **Change visualization** — see exactly what each agent turn modified

The shadow repo is completely separate from the project's own git — it uses `GIT_DIR` and `GIT_WORK_TREE` environment variables to operate independently.

### Architecture

| Component | File | Purpose |
|-----------|------|---------|
| SnapshotManager | `state/snapshots.py` | Shadow git operations (capture, diff, restore, revert) |
| Snapshots API | `api/routers/snapshots.py` | 8 REST endpoints |
| SnapshotPanel | `frontend/app/components/SnapshotPanel.tsx` | Snapshot timeline + diff drawer + revert UI |

### How It Works

1. **Before each agent turn**: `SnapshotManager.capture()` runs `git add -A` + `git write-tree` in the shadow repo, recording a tree hash
2. **After each agent turn**: Another capture records the post-turn state
3. **On completion**: `SnapshotManager.cleanup()` removes old refs and runs garbage collection

Snapshot metadata is stored in `snapshot_index.json` inside the shadow repo directory.

### WSL2/Windows Hardening

The shadow repo lives at `~/.swarmweaver/snapshots/` (ext4 Linux filesystem), NOT on NTFS. Git operations on ext4 are 10-50x faster. Key git configs:

- `core.autocrlf=false` — no line-ending conversion
- `core.longpaths=true` — Windows path length support
- `core.fsmonitor=false` — disable inotify (broken on NTFS)
- `core.preloadindex=true` — faster index loading
- `gc.auto=0` — manual GC only

### Graceful Degradation

All snapshot operations fail silently:

- **Git not installed**: `is_available()` returns False, no snapshots taken
- **Capture fails**: Returns None, message recorded without snapshot hashes
- **Shadow repo corrupted**: Auto-reinitializes on next capture
- **Project not a git repo**: Shadow git works independently

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/snapshots` | List snapshots (filters: session_id, limit) |
| GET | `/api/snapshots/diff` | Diff between two snapshots (structured) |
| GET | `/api/snapshots/diff/file` | Single file diff (unified) |
| GET | `/api/snapshots/files` | Changed files between snapshots |
| POST | `/api/snapshots/revert` | Revert specific files from a snapshot |
| POST | `/api/snapshots/restore` | Full restore to a snapshot |
| POST | `/api/snapshots/cleanup` | Manual garbage collection |
| GET | `/api/snapshots/status` | Snapshot system status (available, repo size, count) |

### WebSocket Events

| Event | When | Data |
|-------|------|------|
| `snapshot_captured` | After pre/post capture | `{before, after, phase, iteration}` |

---

## Frontend

### Sessions Tab

The **Sessions** tab in the Observability panel provides a full session browser:

- **Session list** with mode badges, status dots, cost, duration, task progress
- **Filter bar** with mode chips and status filters
- **Session detail view** with three sub-tabs:
  - **Timeline** — Phase transitions and agent turns
  - **Messages** — Prompt/response pairs with token counts and cost
  - **Files** — Changed files with additions/deletions stats

### Snapshot Panel

The **Checkpoints** tab in the Observability panel includes a snapshot timeline:

- **Snapshot timeline** — Paired pre/post snapshots per iteration, grouped by phase
- **Compare button** — Opens diff drawer between pre and post snapshots
- **Diff drawer** — Slide-out panel with:
  - File list with additions/deletions stats
  - Expandable per-file unified diffs
  - Multi-select checkboxes for batch revert
  - Per-file and batch revert buttons
- **Status bar** — Snapshot count and repository size

---

## Testing

```bash
# Session database tests (21 tests)
pytest tests/test_sessions.py -v

# Snapshot system tests (17 tests)
pytest tests/test_snapshots.py -v
```

---

[← Architecture](architecture.md) | [Configuration →](configuration.md)
