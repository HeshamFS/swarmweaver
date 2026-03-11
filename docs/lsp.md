# LSP Code Intelligence

SwarmWeaver integrates a Language Server Protocol (LSP) layer that provides agents with deep code understanding. The system manages 22 built-in language servers and delivers 13 LSP operations to workers via scoped MCP tools.

## Architecture

| Component | File | Purpose |
|-----------|------|---------|
| LSP Client | `services/lsp_client.py` | JSON-RPC 2.0 over stdio, Content-Length framing |
| LSP Manager | `services/lsp_manager.py` | Server lifecycle, auto-detect, auto-install |
| LSP Hooks | `hooks/lsp_hooks.py` | Post-edit diagnostic injection, cross-worker routing |
| LSP Tools | `services/lsp_tools.py` | Worker MCP tools (`lsp_query`, `lsp_diagnostics_summary`) |
| Code Intelligence | `services/lsp_intelligence.py` | Impact analysis, unused code, dependency graph, health score |
| REST API | `api/routers/lsp.py` | 15 REST endpoints |
| CLI | `cli/commands/lsp.py` | 5 CLI commands |
| Frontend | `frontend/app/components/LSPPanel.tsx` | Code Intel dashboard |

## 13 LSP Operations

| Operation | LSP Method | Purpose |
|-----------|-----------|---------|
| definition | textDocument/definition | Go-to-definition navigation |
| references | textDocument/references | Find all symbol references |
| hover | textDocument/hover | Documentation and type info |
| symbols | textDocument/documentSymbol | Code structure/outline |
| diagnostics | publishDiagnostics | Error/warning feedback |
| call_hierarchy | prepareCallHierarchy | Caller/callee graphs |
| completion | textDocument/completion | Code suggestions |
| rename_preview | textDocument/rename | Refactoring preview |
| workspace_symbols | workspace/symbol | Global symbol search |
| implementation | textDocument/implementation | Find implementations |
| signature_help | textDocument/signatureHelp | Function parameter hints |
| code_actions | textDocument/codeAction | Quick fixes and suggestions |
| formatting | textDocument/formatting | Auto-format document |

## 22 Built-In Language Servers

### Tier 1: Core
| Server | Language | Extensions |
|--------|----------|------------|
| typescript-language-server | TypeScript/JavaScript | .ts, .tsx, .js, .jsx |
| pyright | Python | .py, .pyi |
| gopls | Go | .go |
| rust-analyzer | Rust | .rs |

### Tier 2: Secondary
| Server | Language | Extensions |
|--------|----------|------------|
| clangd | C/C++ | .c, .cpp, .h, .hpp |
| jdtls | Java | .java |
| solargraph | Ruby | .rb, .rake |
| intelephense | PHP | .php |
| kotlin-language-server | Kotlin | .kt, .kts |
| sourcekit-lsp | Swift | .swift |

### Tier 3: Specialty
| Server | Language | Extensions |
|--------|----------|------------|
| zls | Zig | .zig |
| lua-language-server | Lua | .lua |
| elixir-ls | Elixir | .ex, .exs |
| gleam | Gleam | .gleam |
| deno | Deno TypeScript | .ts, .js |

### Tier 4: Config/Markup
| Server | Language | Extensions |
|--------|----------|------------|
| yaml-language-server | YAML | .yaml, .yml |
| bash-language-server | Shell | .sh, .bash, .zsh |
| docker-langserver | Dockerfile | Dockerfile |
| terraform-ls | Terraform | .tf, .tfvars |
| vscode-css-language-server | CSS | .css, .scss, .less |
| vscode-html-language-server | HTML | .html, .htm |
| vue-language-server | Vue | .vue |

Servers are auto-detected from project markers (e.g., `tsconfig.json` triggers TypeScript, `pyproject.toml` triggers Python) and lazily spawned on first file access.

## Post-Edit Diagnostic Injection

The `lsp_post_edit_hook` (PostToolUse) runs after every Write/Edit tool call:

1. **Debounce** — Skip if file was edited <150ms ago
2. **Notify LSP** — Send `didChange` to appropriate language server
3. **Wait for diagnostics** — Up to 3 seconds with 150ms debounce
4. **Filter** — Only Error and Warning severity
5. **Inject** — Format diagnostics and inject into agent context

This gives agents immediate feedback on syntax errors, type errors, and warnings right after editing a file.

## Cross-Worker Diagnostic Routing

When worker A's edit causes diagnostics in files owned by worker B:

1. Check file_scope_map (file_path → worker_id)
2. Route diagnostic alert to the owning worker via mail
3. Format: "LSP: {severity} in your file — Edit caused {severity} at line N: {message}"

## Code Intelligence Features

### Impact Analysis
Analyzes how changing a symbol affects the codebase:
- Gathers all references via `find_references` + `call_hierarchy`
- Counts cross-file references as risk metric
- Risk levels: low (<5 refs), medium (5-20), high (>20 or >5 cross-file)

### Unused Code Detection
Scans workspace symbols and identifies those with zero external references (skipping private symbols).

### Dependency Graph
Maps import/call relationships between files using Union-Find clustering to identify connected components.

### Code Health Score
Project-wide score (0-100): start at 100, -5 per error, -1 per warning, +10 bonus for zero errors. Includes per-language breakdown.

## Per-Worktree Isolation

Each swarm worker gets independent LSP server instances tagged with `worker_id`. This ensures one worker's edits don't interfere with another's diagnostic state.

## Configuration

Located at `.swarmweaver/lsp.yaml`:

```yaml
enabled: true
auto_install: true
auto_detect: true
max_servers_per_worktree: 3
health_check_interval_s: 30.0
request_timeout_s: 10.0
diagnostics_debounce_ms: 150
diagnostics_timeout_s: 3.0
max_diagnostics_per_file: 50
disabled_servers: []
server_overrides:
  pyright:
    settings:
      python.analysis.typeCheckingMode: "basic"
custom_servers: []
```

Environment overrides: `SWARMWEAVER_LSP_*` prefix. See [configuration.md](configuration.md) for full reference.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/lsp/status` | Server status, PID, file count, diagnostics |
| GET | `/api/lsp/diagnostics` | Aggregated diagnostics (filterable) |
| POST | `/api/lsp/hover` | Hover info at position |
| POST | `/api/lsp/definition` | Go-to-definition |
| POST | `/api/lsp/references` | Find all references |
| POST | `/api/lsp/symbols` | Document/workspace symbols |
| POST | `/api/lsp/call-hierarchy` | Incoming/outgoing calls |
| GET | `/api/lsp/servers` | List all 22 server specs |
| POST | `/api/lsp/servers/{id}/restart` | Restart specific server |
| GET | `/api/lsp/config` | Load configuration |
| PUT | `/api/lsp/config` | Update configuration |
| GET | `/api/lsp/impact-analysis` | Cross-file impact for symbol |
| GET | `/api/lsp/stats` | Diagnostic statistics |
| GET | `/api/lsp/code-health` | Project-wide health score |

## CLI Commands

```bash
swarmweaver lsp status       -p DIR                     # Show running servers
swarmweaver lsp diagnostics  -p DIR [-s SEVERITY] [-f PATH] [-n LIMIT]
swarmweaver lsp servers      -p DIR                     # List all 22 server specs
swarmweaver lsp config       -p DIR [--set KEY=VALUE]
swarmweaver lsp restart      [SERVER_ID] -p DIR
```

## WebSocket Events

| Event | Data |
|-------|------|
| `lsp.diagnostics_update` | Batch diagnostic updates |
| `lsp.server_status` | Server start/stop/crash |
| `lsp.code_health` | Health score update |
| `lsp.cross_worker_alert` | Cross-worker diagnostic routing |
| `lsp.merge_validation` | Post-merge diagnostic results |

## Frontend

The **Code Intel** tab in the Observability panel shows:
- Code health bar (0-100) with per-language badges and sparkline trend
- Diagnostics table (sortable/filterable by file, severity, worker)
- LSP server cards with status, file count, restart button
- Per-worker diagnostic mini-cards (swarm mode)
- Impact visualization with caller/callee tree

## Testing

```bash
pytest tests/test_lsp.py -v   # 82 tests
```

---

[← Mail System](mail.md) | [Swarm Orchestration →](swarm.md)
