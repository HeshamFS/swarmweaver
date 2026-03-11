# Security Model

SwarmWeaver implements defense-in-depth security with three layers plus role-based capability enforcement, secret redaction, and interactive permission callbacks.

## Three-Layer Defense

### Layer 1: OS Sandbox

Bash commands run in an isolated environment via the Claude SDK sandbox:

```json
{"sandbox": {"enabled": true, "autoAllowBashIfSandboxed": true}}
```

### Layer 2: Filesystem Permissions

File operations restricted to the project directory via absolute path patterns:

```
Read(/absolute/path/project/**)
Write(/absolute/path/project/**)
Edit(/absolute/path/project/**)
Glob(/absolute/path/project/**)
Grep(/absolute/path/project/**)
```

### Layer 3: Bash Command Allowlist

The `bash_security_hook` (PreToolUse) validates every bash command against an allowlist of ~65 commands.

**Allowed command categories:**

| Category | Commands |
|----------|----------|
| File Inspection | ls, cat, head, tail, wc, grep, find, diff, stat, file, readlink, realpath |
| File Operations | cp, mv, mkdir, touch, rm, chmod, ln |
| Text Processing | sort, uniq, tr, sed, awk, cut, paste, tee, xargs |
| Python | python, python3, pip, pip3, uvicorn, pytest, alembic |
| Node.js | npm, npx, node, pnpm, yarn, next, vite, tsc |
| Version Control | git |
| Process Management | ps, lsof, sleep, pkill, kill |
| System Info | date, hostname, whoami, uname, id, df, du, free, ss, netstat |
| Shell Utilities | echo, printf, export, env, which, type, test, true, false |
| Archive | tar, zip, unzip, gzip, gunzip |
| HTTP | curl, wget |
| Scripts | sh, bash, init.sh, start-backend.sh, start-frontend.sh |
| LSP Servers | pyright-langserver, typescript-language-server, gopls, rust-analyzer, and 20 more |

### Special Command Validation

Commands requiring extra validation:

**`pkill`** — Only allowed for dev process names: node, npm, npx, vite, next, python, python3, uvicorn, gunicorn, pytest, alembic.

**`chmod`** — Only `+x` variants allowed (u+x, a+x, g+x, etc.). Flags like `-R` blocked.

**`rm`** — Catastrophic patterns blocked: `/`, `/usr`, `/home`, `~`, `$HOME`, `..`, `.`

**`git add`** — Broad adds (`git add .`, `git add -A`) require `.gitignore` coverage for dangerous paths: node_modules, .venv, __pycache__, dist, build, .next, .cache.

**Helper scripts** — Must be called with path prefix (`./init.sh`, not bare `init.sh`).

## Role-Based Capability Enforcement

The `capability_enforcement_hook` restricts what each agent role can do:

### Role Permissions

| Role | Write Files | Bash Mode | Git Push | Use Case |
|------|------------|-----------|----------|----------|
| **Scout** | Blocked (except findings files) | Read-only | Blocked | Exploration, spec writing |
| **Builder** | Within FILE_SCOPE only | Full (minus dangerous) | Blocked | Implementation |
| **Reviewer** | Blocked (except review files) | Read-only | Blocked | Code review |
| **Lead** | Blocked (except coordination files) | Git + read-only | Blocked | Task coordination |
| **Merger** | Blocked (except .swarm/ files) | Merge commands + tests | Blocked | Conflict resolution |
| **Orchestrator** | Blocked (except state files) | Read-only | Blocked | Worker management via MCP |

### Dangerous Bash Patterns

These patterns are blocked for non-read-only roles:

```
sed -i              # In-place file editing (use Edit tool)
echo ... >          # Overwrite redirect (use Write tool)
git push            # Push to remote
git reset --hard    # Destructive reset
git clean -f        # Delete untracked files
git checkout -- .   # Discard all changes
git rebase          # History rewrite
rm -rf              # Recursive force delete
pip install         # Package installation
npm install         # Package installation
```

### File Scope Enforcement

Builders can only write to files matching their assigned glob patterns. Checked via `fnmatch` in `capability_enforcement_hook`.

## Secret Sanitizer

`utils/sanitizer.py` redacts secrets from all output:

| Pattern | Replacement |
|---------|-------------|
| `sk-ant-...` | `***REDACTED_API_KEY***` |
| `ANTHROPIC_API_KEY=...` | `ANTHROPIC_API_KEY=***` |
| `Bearer ...` | `Bearer ***` |
| `ghp_...` | `***REDACTED_GH_TOKEN***` |
| `github_pat_...` | `***REDACTED_GH_PAT***` |
| `password...` | `password=***` |
| `sk-...` (20+ chars) | `***REDACTED_SK_KEY***` |
| `secret...` | `secret=***` |
| `token...` (10+ chars) | `token=***` |

Applied recursively to strings, dicts, and lists via `sanitize_dict()`.

## Permission Callbacks

For risky operations not covered by the allowlist, dynamic permission callbacks prompt the user:

1. Agent attempts risky tool call
2. `dynamic_permission_callback()` pushes `permission_request` WebSocket event
3. Frontend shows `PermissionModal` with tool name, input preview, risk badge
4. User clicks Allow / Deny / Always Allow
5. 120-second auto-deny timeout (safety valve)

Risk levels: low (routine), medium (file modifications), high (process/network operations).

## Security Settings Per Worktree

Each swarm worker gets a `claude_settings.json` in its worktree:

```json
{
  "sandbox": {"enabled": true, "autoAllowBashIfSandboxed": true},
  "permissions": {
    "defaultMode": "acceptEdits",
    "allow": [
      "Read(/project/path/**)",
      "Write(/project/path/**)",
      "Edit(/project/path/**)",
      "Bash(*)",
      "mcp__puppeteer__*",
      "mcp__web_search__*"
    ]
  }
}
```

Generated by `deploy_hooks_to_worktree()` in `hooks/capability_hooks.py`.

## Audit Logging

All tool executions are logged to `.swarmweaver/audit.log` by the `audit_log_hook` (PostToolUse), recording timestamp, tool name, input, agent role, result (success/blocked), and block reason.

## Security Scan Mode

The `security` operation mode provides automated vulnerability scanning with mandatory human review:

1. **Scanner** runs with isolated prompts (no shared templates) and an explicit blocklist
2. Results written to `.swarmweaver/security_report.json`
3. **Human reviews** findings in the Web UI
4. **Remediator** fixes only user-approved vulnerabilities

## Hook Execution Order (PreToolUse)

For bash commands, hooks execute in this order:

1. `steering_hook` — Check for human steering messages
2. `worker_scope_hook` — Block workers from direct task_list.json access
3. `bash_security_hook` — Validate against ALLOWED_COMMANDS
4. `protect_swarmweaver_backend_hook` — Prevent killing backend on port 8000
5. `port_config_hook` — Auto-fix port references
6. `environment_management_hook` — Auto-manage venv/node_modules
7. `server_management_hook` — Auto-manage server processes

## Testing

```bash
python tests/test_security.py   # 138 security hook test cases
```

---

[← Swarm](swarm.md) | [Configuration →](configuration.md)
