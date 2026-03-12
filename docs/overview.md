# SwarmWeaver Overview

SwarmWeaver is a Python harness that runs Claude as a long-running autonomous coding agent. Unlike one-shot code generation, SwarmWeaver works across **many sessions** with fresh context windows, persisting progress through a task list, git commits, and handoff notes. It can run for hours or days unattended.

## Six Operation Modes

Each mode covers a different phase of the codebase lifecycle:

| Mode | What It Does | Example |
|------|-------------|---------|
| `greenfield` | Builds a new project from a specification file | "Build me a SaaS dashboard from this spec" |
| `feature` | Adds features to an existing codebase | "Add OAuth2 login with Google and GitHub" |
| `refactor` | Restructures or migrates a codebase | "Migrate from JavaScript to TypeScript" |
| `fix` | Diagnoses and fixes bugs | "Login fails when email has a plus sign" |
| `evolve` | Improves a codebase toward a goal | "Add unit tests for 80% coverage" |
| `security` | Scans for vulnerabilities with human review | "Full security audit of the API layer" |

## Phase-Based Execution

Each mode follows a phase-based execution pattern:

```
greenfield:  initialize ──> code* ──> code* ──> ... ──> done
feature:     analyze ──> plan ──> implement* ──> implement* ──> ... ──> done
refactor:    analyze ──> plan ──> migrate* ──> migrate* ──> ... ──> done
fix:         investigate ──> fix* ──> fix* ──> ... ──> done
evolve:      audit ──> improve* ──> improve* ──> ... ──> done
security:    scan ──> [human review] ──> remediate* ──> ... ──> done

* = looping phase (repeats until all tasks are complete)
```

## Cross-Cutting Capabilities

All modes share these capabilities:

- **Approval gates** — Pause the agent for human review at key checkpoints
- **Worktree isolation** — Run in isolated git worktrees; merge or discard on completion
- **Verification loop** — Self-healing test verification
- **MELS expertise system** — Multi-Expertise Learning System with cross-project knowledge, real-time intra-session lesson synthesis, and token-budget-aware priming
- **4-tier merge resolution** — Clean → auto → AI → reimagine for swarm conflicts
- **Session persistence** — SQLite-backed session database with per-turn recording and cross-project indexing
- **Shadow git snapshots** — Commit-based capture before/after each agent turn with SQLite index, named bookmarks, preview-before-restore, per-file diff and surgical revert
- **Security allowlist** — Bash commands validated against an allowlist (~60+ commands)

## End-to-End Workflow

```mermaid
flowchart TB
    subgraph input [User Input]
        A[CLI swarmweaver feature ...]
        B[Web UI Omnibar]
    end
    subgraph routing [Routing]
        C[Mode: greenfield / feature / refactor / fix / evolve / security]
        D["Execution: Engine | Swarm | SmartSwarm"]
    end
    subgraph phases [Phase Loop]
        E[Analyze / Plan / Initialize]
        F[Implement / Code / Migrate / Fix]
        G[Verification]
    end
    subgraph persistence [Persistence]
        H[task_list.json]
        I[Git commits]
        J[claude-progress.txt]
    end
    subgraph output [Output]
        K[Working Code]
    end
    A --> C
    B --> C
    C --> D
    D --> E
    E --> F
    F --> G
    G -->|"tasks pending"| F
    G -->|"all done"| K
    F --> H
    F --> I
    F --> J
```

For the **complete system architecture diagram** — showing all subsystems (hooks, MELS, watchdog, LSP, mail, state persistence, frontend) and how they interconnect — see [architecture.md](architecture.md#system-architecture).

## Execution Paths

- **Single agent** — Default; one Claude session with phase loop
- **Static swarm** (`--parallel N`) — N workers in isolated worktrees, coordinated by SwarmOrchestrator
- **Smart swarm** (`--smart-swarm`) — AI-orchestrated dynamic workers via SmartOrchestrator

## Related Documentation

- [Getting Started](getting-started.md) — Installation and first run
- [Architecture](architecture.md) — Package map, execution flow
- [CLI Reference](cli-reference.md) — Commands and flags
- [Web UI](web-ui.md) — Dashboard capabilities
- [Swarm Orchestration](swarm.md) — Multi-agent swarm modes and merge resolution
- [MELS Expertise](mels.md) — Cross-project learning system
- [Security](security.md) — Bash allowlist, role capabilities, secret sanitizer
- [Session History & Snapshots](session-history.md) — Session database and shadow git snapshots
- [Watchdog](watchdog.md) — Health monitoring and AI triage
- [Mail System](mail.md) — Inter-agent messaging
- [LSP Code Intelligence](lsp.md) — Language server integration
- [Configuration](configuration.md) — Environment and config files

[← Back to docs index](README.md) | [Main README](../README.md)
