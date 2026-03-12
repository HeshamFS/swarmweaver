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
- **Named bookmarks** — pin important snapshots with names and descriptions, preserved from cleanup
- **Preview before restore** — see exactly what would change before committing
- **Commit history** — browse the linear snapshot chain with metadata

The shadow repo is completely separate from the project's own git — it uses `GIT_DIR` and `GIT_WORK_TREE` environment variables to operate independently.

### Architecture

| Component | File | Purpose |
|-----------|------|---------|
| SnapshotManager | `state/snapshots.py` | Shadow git operations (capture, diff, restore, revert, bookmarks) |
| Snapshots API | `api/routers/snapshots.py` | 13 REST endpoints |
| SnapshotPanel | `frontend/app/components/SnapshotPanel.tsx` | Timeline/bookmarks views + diff drawer + restore preview |

### How It Works

1. **Before each agent turn**: `SnapshotManager.capture()` runs `git add -A` + `git commit` in the shadow repo, creating a proper commit in a linear chain
2. **After each agent turn**: Another capture records the post-turn state as a new commit
3. **Metadata indexing**: Each capture is recorded in a SQLite database (`snapshots.db`, WAL mode) with tree hash, commit hash, label, session ID, phase, iteration, and file count
4. **On completion**: `SnapshotManager.cleanup()` removes old records (preserving bookmarked snapshots) and runs `git gc`

The commit-based approach gives a proper linear history browsable with standard git tooling, while the SQLite index provides fast querying by session, phase, or timestamp.

### Bookmarks

Named bookmarks pin important snapshots for easy reference and precision time-travel:

- `bookmark(tree_hash, name, description)` — creates a git tag (for GC protection) and SQLite record
- Bookmarked snapshots are **preserved during cleanup** — they survive `cleanup(max_age_days=0)`
- `list_bookmarks()`, `get_bookmark(name)`, `delete_bookmark(name)` for full CRUD
- Typical use: bookmark before a risky refactor, after a successful milestone, or at any point you might want to return to

### Preview Before Restore

`preview_restore(tree_hash)` shows exactly what files would change if you restored to a snapshot — the diff between current working state and the target. The frontend renders this in a confirmation modal before executing the restore.

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
| POST | `/api/snapshots/cleanup` | Manual garbage collection (preserves bookmarks) |
| GET | `/api/snapshots/status` | Snapshot system status (available, repo size, counts) |
| POST | `/api/snapshots/bookmark` | Create a named bookmark for a snapshot |
| GET | `/api/snapshots/bookmarks` | List all bookmarks with snapshot metadata |
| DELETE | `/api/snapshots/bookmark/{name}` | Delete a bookmark |
| GET | `/api/snapshots/preview-restore` | Preview what restore would change |
| GET | `/api/snapshots/history` | Git commit history with snapshot metadata |

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

The **Checkpoints** tab in the Observability panel includes a snapshot panel with two views:

**Timeline view:**
- **Snapshot pairs** — Pre/post snapshots per iteration, grouped by phase with color-coded badges
- **Compare button** — Opens diff drawer between pre and post snapshots
- **Bookmark button** — Pin a snapshot with a name and description (star icon)
- **Restore button** — Preview what would change, then confirm to restore
- **Diff drawer** — Slide-out panel with:
  - File list with additions/deletions stats
  - Expandable per-file unified diffs
  - Multi-select checkboxes for batch revert
  - Per-file and batch revert buttons

**Bookmarks view:**
- **Bookmark list** — Named snapshots with descriptions, phase badges, file counts
- **Restore button** — Preview and restore to a bookmarked state
- **Remove button** — Delete a bookmark (snapshot is preserved)

**Status bar** — Snapshot count, bookmark count, and repository size in MB

---

## Testing

```bash
# Session database tests (21 tests)
pytest tests/test_sessions.py -v

# Snapshot system tests (31 tests)
pytest tests/test_snapshots.py -v
```

---

[← Architecture](architecture.md) | [Configuration →](configuration.md)
