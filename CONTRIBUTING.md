# Contributing to SwarmWeaver

Thank you for your interest in contributing! This guide covers everything you need to get started.

## Before You Start

- **Prerequisites:** Python 3.11+, Node 20+, [uv](https://docs.astral.sh/uv/) (Python package manager), npm
- **Context:** Read [AGENTS.md](AGENTS.md) for the codebase summary used by AI tools
- **Reference:** Check [docs/](docs/) for detailed documentation (e.g. [docs/architecture.md](docs/architecture.md) for code layout)

## Ways to Contribute

- **Code** — Fix bugs, add features, improve tests
- **Documentation** — Improve README, docs, or inline comments
- **Issues** — Report bugs or suggest features
- **Triage** — Help categorize and reproduce reported issues

## Quick Setup

```bash
# 1. Clone the repository
git clone https://github.com/HeshamFS/swarmweaver.git
cd swarmweaver

# 2. Install all dependencies (creates .venv, registers swarmweaver CLI)
uv sync

# 3. Install frontend dependencies
npm install

# 4. Start the full dev stack (backend + frontend)
npm run dev
```

**Windows users:** `./setup.sh` is Unix-only. Use `uv sync` and `npm install` directly; `dev.mjs` and all CLI commands work on Windows.

The web UI will be available at http://localhost:3000 and the API at http://localhost:8000.

## Branch Workflow

1. Create a new branch from `main`:
   ```bash
   git checkout main
   git pull origin main
   git checkout -b fix/short-description   # or feat/add-oauth, docs/update-readme
   ```
2. Use descriptive branch names: `fix/`, `feat/`, `docs/`, `refactor/`, `test/`
3. Keep changes scoped to one logical unit per branch

## Where Code Lives

| Package | Purpose |
|---------|---------|
| `cli/` | CLI package — `swarmweaver` entry point, commands, output formatting |
| `api/` | FastAPI package — REST endpoints, WebSocket, routers |
| `core/` | Agent loop, orchestrators, merge resolver, worktree utilities |
| `features/` | Mode capabilities — steering, approval, memory, verification, plugins |
| `services/` | Shared helpers — events, insights, costs, ADR, replay, timeline |
| `state/` | Persistence — task list, sessions, budget, mail, events, checkpoints |
| `hooks/` | Policy enforcement — security allowlist, capability enforcement, marathon hooks |
| `utils/` | Utilities — progress dashboard, sanitizer, safe logging |
| `prompts/` | Prompt templates per mode and agent role |
| `templates/` | Project starter specs and overlay template |
| `frontend/` | Next.js 15 web dashboard |
| `tests/` | Python test suite |

## Running Tests

```bash
# Backend tests
pytest tests -q

# Security hook regression (138 test cases)
python tests/test_security.py

# Frontend lint
npm --prefix frontend run lint
```

All tests must pass before submitting a PR.

## Commit Style

Follow the commit convention already in the git history:

```
feat: add OAuth2 login with Google and GitHub
fix: handle plus signs in email addresses during auth
docs: update CLI reference with new status command
refactor: extract merge logic into merge_resolver module
test: add regression cases for security hook allowlist
```

Rules:
- Use a prefix: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`
- Write the subject in imperative mood ("add", not "added" or "adds")
- Keep the subject line under 72 characters
- Scope each commit to one logical change

## Pull Request Checklist

Before opening a PR, confirm:

- [ ] All backend tests pass (`pytest tests -q`)
- [ ] Frontend lints cleanly (`npm --prefix frontend run lint`)
- [ ] No secrets or credentials in any committed file
- [ ] Relevant documentation updated (README, AGENTS.md, or inline comments)
- [ ] New hooks or security changes include matching tests in `tests/test_security.py`
- [ ] Frontend changes include screenshots in the PR description

## Code Style

**Python:** 4-space indentation, `snake_case` for modules and functions, `PascalCase` for classes, type hints on new or changed logic.

**TypeScript/React:** `PascalCase` component files, hooks prefixed with `use`, keep UI logic close to the component it belongs to.

**General:** Prefer small, composable changes. Extend existing `services/` and `utils/` before creating new abstractions.

## Getting Help

- Open a [GitHub Issue](https://github.com/HeshamFS/swarmweaver/issues) for bugs or feature requests
- Check [docs/](docs/) for detailed reference documentation (e.g. [docs/architecture.md](docs/architecture.md) for package structure)
- See [AGENTS.md](AGENTS.md) for the codebase summary used by AI tools
