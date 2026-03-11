# SwarmWeaver Documentation

This directory contains extended reference documentation for SwarmWeaver. For a quick overview, start with the [main README](../README.md).

## Documentation Index

### Getting Started

| Document | Description |
|----------|-------------|
| [Overview](overview.md) | What SwarmWeaver does, six modes, phase sequences, and cross-cutting capabilities |
| [Getting Started](getting-started.md) | Prerequisites, installation, authentication, and first run (Web UI, CLI, Docker) |
| [Architecture](architecture.md) | Package map, execution flow (single/swarm/smart-swarm), and security model |
| [CLI Reference](cli-reference.md) | All commands, flags, output modes, connected mode, and examples |
| [Web UI](web-ui.md) | Omnibar, tabs, panels, worktree toggle, observability, and notifications |
| [Configuration](configuration.md) | Environment variables, `~/.swarmweaver/config.toml`, and project settings |

### Core Systems

| Document | Description |
|----------|-------------|
| [Swarm Orchestration](swarm.md) | Static swarm, Smart Swarm, merge resolution, worker lifecycle, scope enforcement |
| [MELS Expertise System](mels.md) | Cross-project learning, 10 record types, domain taxonomy, priming, lesson synthesis |
| [Security Model](security.md) | Bash allowlist, role-based capabilities, secret sanitizer, permission callbacks |

### Infrastructure

| Document | Description |
|----------|-------------|
| [Session History & Snapshots](session-history.md) | Persistent session database, shadow git snapshots, per-file revert |
| [Watchdog Health Monitoring](watchdog.md) | 9-state machine, 7-signal health, AI triage, circuit breaker |
| [Inter-Agent Mail](mail.md) | Typed messages, attachments, dead letters, escalation, analytics |
| [LSP Code Intelligence](lsp.md) | 22 language servers, diagnostics, impact analysis, cross-worker routing |

## Other Resources

- [CONTRIBUTING.md](../CONTRIBUTING.md) — Setup, code style, commit conventions, PR checklist
- [CHANGELOG.md](../CHANGELOG.md) — Release history and notable changes
- [CLAUDE.md](../CLAUDE.md) — Detailed architecture reference for AI coding assistants
- [AGENTS.md](../AGENTS.md) — Concise agent context for AI tools
