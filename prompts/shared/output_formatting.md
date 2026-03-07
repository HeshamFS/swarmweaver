# Output Formatting Guide

When writing status updates, analysis, progress reports, or any text that appears in the dashboard Activity feed, follow these conventions for clear, structured output.

## Markdown Conventions

- **Headers**: Use `##` for main sections, `###` for subsections. Headers help users scan quickly.
- **Tables**: Use markdown tables for structured data. Always include a header row and separator row:

  | Column A | Column B |
  |----------|----------|
  | value 1  | value 2  |

- **Bullet lists**: Use `- ` for bullet points. Keep items concise.
- **Progress**: Format as `**Task**: X/Y done` or use tables for multi-worker status.
- **Code**: Use `` `inline code` `` for file names, commands, identifiers. Use triple-backtick fences for multiline code blocks.

## Icon Shortcodes

Use `:shortcode:` to insert icons. Do **not** use raw emojis — use these shortcodes instead.

| Shortcode | Use case |
|-----------|----------|
| `:check:` | Success, done, completed |
| `:x:` | Error, failed, blocked |
| `:alert:` | Warning, attention needed |
| `:zap:` | Fast, active |
| `:rocket:` | Launched, spawned |
| `:merge:` | Merged, combined |
| `:task:` | Task, work item |
| `:list:` | List, checklist |
| `:table:` | Table, grid |
| `:bot:` | Orchestrator, AI |
| `:users:` | Workers, team |
| `:clock:` | Time, waiting |
| `:circle:` | Pending, in progress |
| `:square:` | Section, block |

**Examples:**
- `:check: TASK-001 done` — task completed
- `:rocket: Spawned worker-3` — worker launched
- `:alert: Build failed` — warning

## Tables

- Always include header row and separator row (`|---|---|`)
- Keep columns aligned for readability
- Use tables for: worker status, task progress, dependency chains

## Reports and Summaries

When sending progress or completion reports (e.g. via `report_to_orchestrator`, or in status updates):

- Use **##** for section headers (e.g. `## Phase 1 Complete`)
- Use **- ** for bullet lists of deliverables
- Use **markdown tables** for task summaries:

  | TASK | DELIVERABLE |
  |------|-------------|
  | TASK-001 | Description |
  | TASK-002 | Description |

- Keep lines under ~80 chars when possible to avoid mid-word breaks in narrow displays

## Avoid

- Long unformatted paragraphs
- Raw emojis (🤖 🚀 ✅ ⛔) — use `:shortcode:` instead
- Dense walls of text — break into sections with headers and lists
- Generic status like `:zap: CODE` or `:code:` alone — use specific info (e.g. `:zap: worker-2 on TASK-005` or `:rocket: Spawned worker-2`)
