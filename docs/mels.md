# Multi-Expertise Learning System (MELS)

MELS is SwarmWeaver's unified knowledge engine — a typed, domain-hierarchical, governed expertise system with real-time intra-session learning. It replaces all previous learning infrastructure (AgentMemory, ProjectExpertise, lessons.json).

## Overview

MELS provides:

- **10 record types** for different kinds of knowledge (patterns, failures, resolutions, conventions, etc.)
- **Hierarchical domain taxonomy** (`python.fastapi` inherits from `python`)
- **Dual-store architecture** — cross-project + project-local SQLite databases
- **Real-time intra-session learning** from worker error clusters (Smart Swarm)
- **Token-budget-aware priming** for prompt injection (greedy knapsack algorithm)
- **Confidence scoring** with multi-signal decay
- **Causal chaining** — failure records linked to their resolutions

## Architecture

| Component | File | Purpose |
|-----------|------|---------|
| Data Models | `services/expertise_models.py` | 5 dataclasses, 10 record types, domain taxonomy |
| SQLite Store | `services/expertise_store.py` | CRUD, search, governance, session lessons |
| Scoring | `services/expertise_scoring.py` | Confidence, relevance decay, priming score |
| Priming Engine | `services/expertise_priming.py` | Token-budget-aware greedy knapsack selection |
| Lesson Synthesis | `services/expertise_synthesis.py` | Real-time error clustering and lesson generation |
| Migration | `services/expertise_migration.py` | Legacy JSON to SQLite migration |
| REST API | `api/routers/expertise.py` | 16 endpoints |
| Frontend | `frontend/app/components/ExpertisePanel.tsx` | 5-tab browser UI |

### Dual-Store System

| Store | Location | Scope |
|-------|----------|-------|
| Cross-project | `~/.swarmweaver/expertise/expertise.db` | Shared across all projects |
| Project-local | `.swarmweaver/expertise/expertise.db` | Project-specific knowledge |

Both use SQLite WAL mode with `busy_timeout=5000` for concurrent safety.

## Record Types

| Type | Purpose | Example |
|------|---------|---------|
| `convention` | Coding standards, naming rules | "Always use type hints in Python functions" |
| `pattern` | Reusable solution approach | "Use FastAPI Depends() for dependency injection" |
| `failure` | Something that went wrong | "ImportError on relative imports in submodules" |
| `resolution` | Fix for a specific failure (linked via `resolves`) | "Use absolute imports from project root" |
| `decision` | Architectural choice with rationale | "Use SQLite for state tracking to avoid external DB" |
| `reference` | Key file/API/resource pointer | "Main MCP tool registry: core/client.py:150" |
| `guide` | Step-by-step procedural knowledge | "Setup venv with activation steps" |
| `insight` | Cross-cutting observation | "Token overhead of expertise priming is ~300 tokens" |
| `antipattern` | What NOT to do | "Don't mutate agent_identity directly" |
| `heuristic` | Rule of thumb with confidence bounds | "If outcome_count >= 10, confidence is reliable" |

## Classifications and Shelf-Life

| Classification | Shelf Life | Decay Model | Use Case |
|---|---|---|---|
| `foundational` | Permanent | No decay (always 1.0) | Core patterns, conventions, decisions |
| `tactical` | 30 days | Linear decay to 0 | Session-specific solutions, workarounds |
| `observational` | 14 days | Exponential decay (half-life ~14d) | One-off observations, environment notes |

## Confidence Scoring

Multi-signal scoring (0.0 to 1.0):

- **50%** — Success rate: `success_count / outcome_count`
- **20%** — Recency: `exp(-0.03 * days_since_update)`
- **30%** — Confirmation density: `min(outcome_count / 10, 1.0)`

New records (no outcomes) start at 0.5 (neutral). Records with confidence < 0.1 and 5+ outcomes are eligible for pruning.

## Domain Taxonomy

Domains are hierarchical — `python.fastapi` inherits from `python`. Domains are auto-inferred from file patterns:

| File Pattern | Domain |
|---|---|
| `.py` | python |
| `fastapi`, `uvicorn` | python.fastapi |
| `django` | python.django |
| `pytest`, `test_` | python.testing / testing.unit |
| `.ts` | typescript |
| `.tsx` | typescript.react |
| `next.config` | typescript.nextjs |
| `.go` | go |
| `Dockerfile` | devops.docker |
| `.github/workflows` | devops.ci |
| `.sql` | database.sql |
| `api/`, `routes/` | architecture.api |

Domain matching is hierarchical: searching for `python` also returns `python.fastapi`, `python.django`, etc.

## Token-Budget-Aware Priming

The `PrimingEngine` selects the most relevant records that fit within a token budget (default: 2000 tokens):

1. **Gather candidates** — Query by domains, file patterns, keywords
2. **Score each** — Composite of domain match (30%), file pattern match (30%), keyword relevance (20%), confidence (10%), recency (10%)
3. **Greedy knapsack** — Fill budget with highest-scoring records
4. **Format as markdown** — Grouped by domain with record type badges

Output is injected into agent prompts via the `{agent_memory}` placeholder in `prompts/shared/session_start.md`.

## Real-Time Lesson Synthesis (Smart Swarm)

In Smart Swarm mode, the `SessionLessonSynthesizer` watches for error patterns across workers:

1. **Error normalization** — Strip line numbers, hex addresses, UUIDs, timestamps
2. **Clustering** — 2+ similar errors across different workers (or 3+ from same worker) form a cluster
3. **Quality gating** — Lessons must score >= 0.4 (specificity + actionability) to be created
4. **Propagation** — Lessons with quality >= 0.6 are sent to active workers via steering messages
5. **Promotion** — At session end, high-quality lessons become permanent `ExpertiseRecord` entries

### WebSocket Events

| Event | When |
|-------|------|
| `expertise_lesson_created` | New lesson synthesized from error cluster |
| `expertise_lesson_propagated` | Lesson sent to active workers |
| `expertise_record_promoted` | Session lesson promoted to permanent record |

## Causal Chains

Failure records can be linked to resolution records:

- A `failure` record has a `resolves` field pointing to the failure it fixes
- A `resolution` record has a `resolved_by` list of records that resolve it
- `GET /api/expertise/causal-chain/{id}` returns the full chain

This enables pattern: agent encounters error → MELS returns both the failure record AND its known resolution.

## Integration Points

### Prompt Priming (every session)
`core/prompts.py` calls `PrimingEngine.prime()` to populate `{agent_memory}` with relevant expertise before each agent session.

### Post-Session Harvesting
`core/agent.py` reads `.swarmweaver/session_reflections.json` (written by the agent during `session_end.md`) and converts reflections to typed `ExpertiseRecord` entries with auto-inferred domains.

### Smart Swarm Synthesis
`core/smart_orchestrator.py` uses `SessionLessonSynthesizer` to detect cross-worker error clusters and propagate lessons in real-time.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/expertise` | List records (filters: domain, type, classification, query, limit) |
| POST | `/api/expertise` | Create new record |
| GET | `/api/expertise/{id}` | Get record by ID |
| PUT | `/api/expertise/{id}` | Update record fields |
| DELETE | `/api/expertise/{id}` | Archive (soft-delete) |
| POST | `/api/expertise/{id}/outcome` | Record outcome (success/failure/partial) |
| GET | `/api/expertise/search` | Full-text + domain + type search |
| GET | `/api/expertise/prime` | Get priming context for files/domains/budget |
| GET | `/api/expertise/causal-chain/{id}` | Get failure-to-resolution chain |
| GET | `/api/expertise/domains` | List domains with counts and governance |
| POST | `/api/expertise/domains` | Create/configure domain governance |
| GET | `/api/expertise/analytics` | Dashboard: top records, domain health, by type |
| GET | `/api/expertise/session-lessons` | Get lessons (by session or recent) |
| POST | `/api/expertise/migrate` | Trigger legacy JSON migration |
| POST | `/api/expertise/prune` | Remove expired/low-confidence records |
| GET | `/api/expertise/export` | Export all records as JSON |

All endpoints accept an optional `project_dir` query param to select the project-local store (default: cross-project).

## Domain Governance

Each domain has configurable limits:

| Limit | Default | Action |
|-------|---------|--------|
| Soft limit | 100 records | Warning logged |
| Warn limit | 150 records | Auto-compact triggered |
| Hard limit | 200 records | Oldest observational records pruned |

Configure via `POST /api/expertise/domains`.

## Frontend

The `ExpertisePanel.tsx` component (in the Observability panel) provides 5 tabs:

1. **Browser** — Search and filter records by domain, type, classification
2. **Causal Chains** — Visualize failure-to-resolution links
3. **Lessons** — Real-time lesson feed from active Smart Swarm sessions
4. **Analytics** — Domain health, record distribution, top records
5. **Priming Preview** — See what expertise would be injected for given files

## Testing

```bash
pytest tests/test_expertise.py -v          # 46 tests
pytest tests/test_mels_integration.py -v   # 34 integration tests
```

---

[← Architecture](architecture.md) | [Configuration →](configuration.md)
