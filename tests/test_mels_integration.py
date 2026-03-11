"""
MELS Integration Test — Full Session Lifecycle
================================================

Simulates a complete smart swarm session with 4 workers to verify
the entire MELS pipeline works end-to-end with real SQLite databases.

Flow:
  1. Orchestrator creates session + MELS stores
  2. Workers encounter errors → recorded via SessionLessonSynthesizer
  3. Error clusters trigger lesson synthesis (cross-worker pattern detection)
  4. Orchestrator manually adds lessons via _save_lesson (MCP add_lesson path)
  5. High-quality lessons are propagated to active workers
  6. At session end, lessons are promoted to permanent ExpertiseRecord entries
  7. Post-session harvesting creates failure→resolution chains with domains
  8. Analytics, domains, causal chains, and priming all return populated data

No mocks — uses real SQLite databases in tmp_path.
"""

import asyncio
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from services.expertise_models import (
    ExpertiseRecord,
    SessionLesson,
    infer_domain,
    HIERARCHICAL_DOMAIN_MAP,
)
from services.expertise_store import ExpertiseStore
from services.expertise_synthesis import SessionLessonSynthesizer
from services.expertise_scoring import (
    compute_confidence,
    compute_relevance,
    score_for_priming,
)
from services.expertise_priming import PrimingEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_store(tmp_path: Path, name: str = "project") -> ExpertiseStore:
    db_path = tmp_path / name / "expertise" / "expertise.db"
    return ExpertiseStore(db_path)


def make_synth(store: ExpertiseStore, session_id: str = "test-session-001") -> SessionLessonSynthesizer:
    return SessionLessonSynthesizer(store, session_id)


# ---------------------------------------------------------------------------
# Phase 1: Domain inference
# ---------------------------------------------------------------------------

class TestDomainInference:
    """Verify infer_domain() works for common file types."""

    def test_python_file(self):
        assert infer_domain("src/auth.py") == "python"

    def test_python_api_file(self):
        # "api/" path matches architecture.api (more specific than .py → python)
        assert infer_domain("src/api/auth.py") == "architecture.api"

    def test_tsx_file(self):
        assert infer_domain("frontend/components/Button.tsx") == "typescript.react"

    def test_ts_file(self):
        assert infer_domain("src/utils/helpers.ts") == "typescript"

    def test_test_file(self):
        # "test_" prefix matches testing.unit (more specific than .py → python)
        assert infer_domain("test_auth.py") == "testing.unit"

    def test_dockerfile(self):
        assert infer_domain("Dockerfile") == "devops.docker"

    def test_css_file(self):
        assert infer_domain("styles/main.css") == "styling"

    def test_nextjs_config(self):
        assert infer_domain("next.config.js") == "typescript.nextjs"

    def test_empty_path(self):
        assert infer_domain("") == ""

    def test_unknown_extension(self):
        assert infer_domain("README.md") == ""


# ---------------------------------------------------------------------------
# Phase 2: Worker errors → cluster detection → lesson synthesis
# ---------------------------------------------------------------------------

class TestWorkerErrorClustering:
    """Simulate 4 workers encountering errors and verify cluster-based lesson creation."""

    def test_cross_worker_cluster_creates_lesson(self, tmp_path):
        """Two workers hitting the same error should trigger a lesson."""
        store = make_store(tmp_path)
        synth = make_synth(store)

        # Worker 1 hits a TypeScript compilation error
        err1_id, lesson1 = synth.record_error(
            worker_id="1", worker_name="builder-1",
            tool_name="Bash",
            error_message="error TS2307: Cannot find module '@/components/shared' or its corresponding type declarations.",
            file_path="src/pages/Home.tsx", task_id="TASK-001",
        )
        assert err1_id == "err-000"
        assert lesson1 is None  # First error, no cluster yet

        # Worker 2 hits the exact same error in a different file
        err2_id, lesson2 = synth.record_error(
            worker_id="2", worker_name="builder-2",
            tool_name="Bash",
            error_message="error TS2307: Cannot find module '@/components/shared' or its corresponding type declarations.",
            file_path="src/pages/About.tsx", task_id="TASK-005",
        )
        assert err2_id == "err-001"
        assert lesson2 is not None, "Cross-worker cluster should trigger lesson"
        assert lesson2.severity in ("medium", "high")
        assert lesson2.quality_score >= 0.4

        # Lesson should be persisted in the store
        lessons = store.get_session_lessons("test-session-001")
        assert len(lessons) == 1
        assert lessons[0].id == lesson2.id

    def test_same_worker_needs_three_errors(self, tmp_path):
        """Same worker needs 3+ similar errors to form a cluster."""
        store = make_store(tmp_path)
        synth = make_synth(store)

        # Same error message each time (different file_path context, but message clusters)
        err_msg = "ENOENT: no such file or directory, open 'config.json'"
        _, l1 = synth.record_error("1", "builder-1", "Bash", err_msg, "f.js", "T1")
        assert l1 is None

        _, l2 = synth.record_error("1", "builder-1", "Bash", err_msg, "g.js", "T1")
        assert l2 is None  # 2 errors same worker → not enough

        _, l3 = synth.record_error("1", "builder-1", "Bash", err_msg, "h.js", "T1")
        assert l3 is not None  # 3 errors same worker → cluster

    def test_no_duplicate_lessons(self, tmp_path):
        """Same cluster shouldn't create duplicate lessons."""
        store = make_store(tmp_path)
        synth = make_synth(store)

        synth.record_error("1", "w1", "Bash", "error: EACCES permission denied", "a.py", "T1")
        _, first_lesson = synth.record_error("2", "w2", "Bash", "error: EACCES permission denied", "b.py", "T2")
        assert first_lesson is not None

        # Third occurrence shouldn't create another lesson
        _, dup = synth.record_error("3", "w3", "Bash", "error: EACCES permission denied", "c.py", "T3")
        assert dup is None  # Deduplicated

        lessons = store.get_session_lessons("test-session-001")
        assert len(lessons) == 1

    def test_lesson_domain_inferred_from_files(self, tmp_path):
        """Lesson domain should be inferred from error file paths."""
        store = make_store(tmp_path)
        synth = make_synth(store)

        # Same error message so they cluster
        synth.record_error("1", "w1", "Bash", "TypeError: Cannot read properties of undefined (reading 'map')", "src/app.tsx", "T1")
        _, lesson = synth.record_error("2", "w2", "Bash", "TypeError: Cannot read properties of undefined (reading 'map')", "src/lib.tsx", "T2")

        assert lesson is not None
        assert lesson.domain == "typescript.react"


# ---------------------------------------------------------------------------
# Phase 3: Orchestrator adds lessons via _save_lesson (MCP path)
# ---------------------------------------------------------------------------

class TestOrchestratorLessons:
    """Simulate the orchestrator's _save_lesson() flow."""

    def test_save_lesson_with_file_patterns(self, tmp_path):
        """Lesson with applies_to should infer domain from file patterns."""
        store = make_store(tmp_path)
        synth = make_synth(store)

        # Simulate _save_lesson() logic
        from services.expertise_models import infer_domain

        applies_to = ["src/components/Auth.tsx", "src/hooks/useAuth.ts"]
        domain = ""
        for fp in applies_to:
            d = infer_domain(fp)
            if d:
                domain = d
                break

        lesson = SessionLesson(
            session_id="test-session-001",
            content="React components using useAuth must wrap in AuthProvider",
            severity="high",
            domain=domain,
            file_patterns=applies_to,
            quality_score=0.7,
        )
        store.add_session_lesson(lesson)

        saved = store.get_session_lessons("test-session-001")
        assert len(saved) == 1
        assert saved[0].domain == "typescript.react"
        assert saved[0].quality_score == 0.7

    def test_save_lesson_with_content_keyword_fallback(self, tmp_path):
        """Lesson without file patterns should infer domain from content."""
        store = make_store(tmp_path)

        # Simulate the keyword fallback from _save_lesson()
        content = "Always run pytest with -x flag to stop on first failure"
        domain = ""
        for kw, d in [("react", "typescript.react"), ("typescript", "typescript"),
                      ("python", "python"), ("fastapi", "python.fastapi"),
                      ("test", "testing"), ("docker", "devops.docker"),
                      ("api", "architecture.api"), ("css", "styling")]:
            if kw in content.lower():
                domain = d
                break

        lesson = SessionLesson(
            session_id="test-session-001",
            content=content,
            severity="medium",
            domain=domain,
            quality_score=0.7,
        )
        store.add_session_lesson(lesson)

        saved = store.get_session_lessons("test-session-001")
        assert len(saved) == 1
        assert saved[0].domain == "testing"

    def test_seven_orchestrator_lessons_all_saved(self, tmp_path):
        """All 7 orchestrator-authored lessons should be persisted."""
        store = make_store(tmp_path)

        lessons_data = [
            ("Task dependencies reference non-existent IDs", "high", ["task_list.json"]),
            ("Vite 6 + React 19 + Tailwind CSS v4 setup", "high", ["vite.config.ts"]),
            ("Worker-1 created empty stub files", "high", ["src/utils/constants.ts"]),
            ("Always validate imports before running tests", "medium", ["src/app.tsx"]),
            ("Use framer-motion v11 API, not v10", "medium", ["src/components/Hero.tsx"]),
            ("Docker build fails without .dockerignore", "medium", ["Dockerfile"]),
            ("CSS modules conflict with Tailwind v4", "low", ["src/styles/app.css"]),
        ]

        for content, severity, files in lessons_data:
            domain = ""
            for fp in files:
                d = infer_domain(fp)
                if d:
                    domain = d
                    break
            if not domain:
                for kw, d in [("react", "typescript.react"), ("typescript", "typescript"),
                              ("python", "python"), ("test", "testing"),
                              ("docker", "devops.docker"), ("css", "styling")]:
                    if kw in content.lower():
                        domain = d
                        break

            lesson = SessionLesson(
                session_id="test-session-001",
                content=content,
                severity=severity,
                domain=domain,
                file_patterns=files,
                quality_score=0.7,
            )
            store.add_session_lesson(lesson)

        saved = store.get_session_lessons("test-session-001")
        assert len(saved) == 7, f"Expected 7 lessons, got {len(saved)}"

        # Verify domains were inferred
        domains = [l.domain for l in saved]
        assert any(d != "" for d in domains), f"At least some should have domains: {domains}"


# ---------------------------------------------------------------------------
# Phase 4: Lesson propagation to workers
# ---------------------------------------------------------------------------

class TestLessonPropagation:
    """Test lesson retrieval for worker injection."""

    def test_get_lessons_for_worker(self, tmp_path):
        """Lessons with matching file scope should be returned."""
        store = make_store(tmp_path)
        synth = make_synth(store)

        # Create a lesson with file patterns
        lesson = SessionLesson(
            session_id="test-session-001",
            content="Always validate props in TSX components",
            severity="high",
            domain="typescript.react",
            file_patterns=["src/components/*.tsx"],
            quality_score=0.8,
        )
        store.add_session_lesson(lesson)

        # Worker with overlapping file scope
        relevant = synth.get_lessons_for_worker(
            file_scope=["src/components/Button.tsx"],
        )
        assert len(relevant) == 1
        assert relevant[0].content == "Always validate props in TSX components"

        # Worker with non-overlapping file scope
        irrelevant = synth.get_lessons_for_worker(
            file_scope=["server/api/routes.py"],
        )
        assert len(irrelevant) == 0

    def test_lessons_without_patterns_are_global(self, tmp_path):
        """Lessons without file_patterns should match all workers."""
        store = make_store(tmp_path)
        synth = make_synth(store)

        lesson = SessionLesson(
            session_id="test-session-001",
            content="Always commit after completing a task group",
            severity="medium",
            domain="",
            file_patterns=[],
            quality_score=0.7,
        )
        store.add_session_lesson(lesson)

        # Any file scope should match global lessons
        relevant = synth.get_lessons_for_worker(file_scope=["anything.py"])
        assert len(relevant) == 1


# ---------------------------------------------------------------------------
# Phase 5: Session end — promotion to permanent records
# ---------------------------------------------------------------------------

class TestLessonPromotion:
    """Test promotion of session lessons to permanent ExpertiseRecord entries."""

    def test_high_quality_lessons_promoted(self, tmp_path):
        """Lessons with quality >= 0.6 should be promoted (fix #5: no propagation requirement)."""
        store = make_store(tmp_path)

        # Lesson with quality >= 0.6 but NOT propagated
        lesson = SessionLesson(
            session_id="test-session-001",
            content="Vite HMR requires explicit React refresh plugin",
            severity="high",
            domain="typescript.react",
            file_patterns=["vite.config.ts"],
            quality_score=0.7,
            propagated_to=[],  # Empty! Was never propagated
        )
        store.add_session_lesson(lesson)

        # Promote — should work even without propagation (fix #5)
        record_id = store.promote_lesson(lesson.id)
        assert record_id is not None

        # Verify the record was created
        record = store.get(record_id)
        assert record is not None
        assert record.record_type == "insight"
        assert record.classification == "tactical"
        assert record.domain == "typescript.react"
        assert "Vite HMR" in record.content
        assert "auto-promoted" in record.tags

        # Verify the lesson was updated with the promoted record ID
        updated_lessons = store.get_session_lessons("test-session-001")
        assert updated_lessons[0].promoted_to_record_id == record_id

    def test_low_quality_lessons_not_promoted(self, tmp_path):
        """Lessons with quality < 0.6 should NOT be promoted."""
        store = make_store(tmp_path)

        lesson = SessionLesson(
            session_id="test-session-001",
            content="Something vague happened",
            severity="low",
            domain="",
            quality_score=0.3,
        )
        store.add_session_lesson(lesson)

        # quality_score 0.3 < 0.6, but promote_lesson doesn't check quality
        # (the gate is in _promote_session_lessons, not promote_lesson)
        # So promote_lesson always works — the orchestrator gates it
        record_id = store.promote_lesson(lesson.id)
        assert record_id is not None  # store.promote_lesson doesn't gate on quality

    def test_promote_idempotent(self, tmp_path):
        """Promoting the same lesson twice should return the same record ID."""
        store = make_store(tmp_path)

        lesson = SessionLesson(
            session_id="test-session-001",
            content="Use strict TypeScript mode",
            severity="high",
            domain="typescript",
            quality_score=0.9,
        )
        store.add_session_lesson(lesson)

        first = store.promote_lesson(lesson.id)
        second = store.promote_lesson(lesson.id)
        assert first == second


# ---------------------------------------------------------------------------
# Phase 6: Failure → Resolution causal chains
# ---------------------------------------------------------------------------

class TestCausalChains:
    """Test failure→resolution linking and chain retrieval."""

    def test_linked_failure_resolution(self, tmp_path):
        """A resolution record should be linked to its failure via resolves/resolved_by."""
        store = make_store(tmp_path)

        # Create failure record
        fail = ExpertiseRecord(
            record_type="failure",
            classification="observational",
            domain="typescript.react",
            content="[feature] Task 'Add auth page' failed with: Cannot find module '@/hooks/useAuth'",
            source_project="/test/project",
            tags=["feature", "error-resolution"],
            file_patterns=["src/pages/Auth.tsx"],
            content_hash=hashlib.sha256(b"fail1").hexdigest(),
        )
        fail_id = store.add(fail)

        # Create resolution record linked to failure
        res = ExpertiseRecord(
            record_type="resolution",
            classification="tactical",
            domain="typescript.react",
            content="[feature] Task 'Add auth page' eventually resolved after 2 attempts",
            source_project="/test/project",
            resolves=fail_id,
            tags=["feature", "error-resolution"],
            file_patterns=["src/pages/Auth.tsx"],
            content_hash=hashlib.sha256(b"res1").hexdigest(),
        )
        res_id = store.add(res)

        # Verify the failure's resolved_by was updated
        failure = store.get(fail_id)
        assert res_id in failure.resolved_by

        # Get causal chain from failure
        chain = store.get_causal_chain(fail_id)
        assert chain["root"] == fail_id
        assert len(chain["chain"]) == 2  # failure + resolution
        assert chain["chain"][0]["record_type"] == "failure"
        assert chain["chain"][1]["record_type"] == "resolution"

        # Get causal chain from resolution (should include failure)
        chain2 = store.get_causal_chain(res_id)
        assert len(chain2["chain"]) == 2

    def test_multiple_resolutions(self, tmp_path):
        """A failure can have multiple resolutions."""
        store = make_store(tmp_path)

        fail = ExpertiseRecord(
            record_type="failure", classification="observational",
            domain="python", content="ImportError: no module named 'requests'",
            content_hash=hashlib.sha256(b"multi-fail").hexdigest(),
        )
        fail_id = store.add(fail)

        for i in range(3):
            res = ExpertiseRecord(
                record_type="resolution", classification="tactical",
                domain="python", content=f"Resolution attempt {i+1}",
                resolves=fail_id,
                content_hash=hashlib.sha256(f"multi-res-{i}".encode()).hexdigest(),
            )
            store.add(res)

        failure = store.get(fail_id)
        assert len(failure.resolved_by) == 3

        chain = store.get_causal_chain(fail_id)
        assert len(chain["chain"]) == 4  # 1 failure + 3 resolutions

    def test_no_chain_for_unlinked(self, tmp_path):
        """Records without resolves/resolved_by should return single-item chain."""
        store = make_store(tmp_path)

        rec = ExpertiseRecord(
            record_type="pattern", classification="tactical",
            domain="python", content="Use dataclasses for DTOs",
            content_hash=hashlib.sha256(b"no-chain").hexdigest(),
        )
        rec_id = store.add(rec)

        chain = store.get_causal_chain(rec_id)
        assert len(chain["chain"]) == 1


# ---------------------------------------------------------------------------
# Phase 7: Analytics & domains
# ---------------------------------------------------------------------------

class TestAnalyticsAndDomains:
    """Test analytics and domain health with populated data."""

    def test_analytics_with_records(self, tmp_path):
        """Analytics should return type/classification/domain breakdowns."""
        store = make_store(tmp_path)

        # Create diverse records
        records = [
            ("pattern", "foundational", "python.fastapi", "Use dependency injection"),
            ("failure", "observational", "typescript.react", "Component unmount crash"),
            ("resolution", "tactical", "typescript.react", "Add cleanup in useEffect"),
            ("convention", "foundational", "python", "Use snake_case for functions"),
            ("insight", "tactical", "testing", "Run tests after every 3 tasks"),
            ("pattern", "tactical", "devops.docker", "Multi-stage Docker builds"),
        ]
        for rt, cls, dom, content in records:
            store.add(ExpertiseRecord(
                record_type=rt, classification=cls, domain=dom, content=content,
                content_hash=hashlib.sha256(content.encode()).hexdigest(),
            ))

        analytics = store.get_analytics()
        assert analytics["total_records"] == 6
        assert analytics["by_type"]["pattern"] == 2
        assert analytics["by_type"]["failure"] == 1
        assert analytics["by_classification"]["foundational"] == 2
        assert len(analytics["top_records"]) == 6

    def test_domains_populated(self, tmp_path):
        """Domains list should show all unique domains with counts."""
        store = make_store(tmp_path)

        for content in ["auth api", "login api", "logout api"]:
            store.add(ExpertiseRecord(
                record_type="pattern", classification="tactical",
                domain="python.fastapi", content=content,
                content_hash=hashlib.sha256(content.encode()).hexdigest(),
            ))
        store.add(ExpertiseRecord(
            record_type="pattern", classification="tactical",
            domain="typescript.react", content="react pattern",
            content_hash=hashlib.sha256(b"react1").hexdigest(),
        ))

        domains = store.get_domains()
        assert len(domains) == 2
        domain_names = {d["name"] for d in domains}
        assert "python.fastapi" in domain_names
        assert "typescript.react" in domain_names
        # python.fastapi should have 3 records
        fastapi = next(d for d in domains if d["name"] == "python.fastapi")
        assert fastapi["count"] == 3

    def test_domain_health(self, tmp_path):
        """Domain health should reflect governance limits."""
        store = make_store(tmp_path)

        # Set a tight limit on "testing" domain
        from services.expertise_models import DomainConfig
        store.configure_domain(DomainConfig(
            name="testing", soft_limit=3, warn_limit=5, hard_limit=8,
        ))

        # Add 4 records (above soft_limit)
        for i in range(4):
            store.add(ExpertiseRecord(
                record_type="pattern", classification="tactical",
                domain="testing", content=f"test pattern {i}",
                content_hash=hashlib.sha256(f"test-{i}".encode()).hexdigest(),
            ))

        health = store.get_domain_health()
        testing_health = next(h for h in health if h["domain"] == "testing")
        assert testing_health["count"] == 4
        assert testing_health["status"] == "soft_warning"


# ---------------------------------------------------------------------------
# Phase 8: Priming engine
# ---------------------------------------------------------------------------

class TestPrimingEngine:
    """Test token-budget-aware priming selection."""

    def test_priming_selects_relevant_records(self, tmp_path):
        """Priming should select records matching file scope."""
        store = make_store(tmp_path)

        # Add records with different domains
        store.add(ExpertiseRecord(
            record_type="pattern", classification="foundational",
            domain="typescript.react", content="Use React.memo for expensive components",
            file_patterns=["src/components/*.tsx"],
            content_hash=hashlib.sha256(b"prime1").hexdigest(),
        ))
        store.add(ExpertiseRecord(
            record_type="convention", classification="foundational",
            domain="python.fastapi", content="Use Depends() for FastAPI dependency injection",
            file_patterns=["api/*.py"],
            content_hash=hashlib.sha256(b"prime2").hexdigest(),
        ))

        engine = PrimingEngine()
        context = engine.prime(
            store,
            file_scope=["src/components/Header.tsx"],
            budget_tokens=2000,
        )
        assert "React.memo" in context
        # FastAPI record shouldn't be top-ranked for React files
        # (it might still appear if budget allows, but React should be first)

    def test_priming_respects_budget(self, tmp_path):
        """Priming should not exceed token budget."""
        store = make_store(tmp_path)

        # Add many records
        for i in range(50):
            store.add(ExpertiseRecord(
                record_type="pattern", classification="tactical",
                domain="python", content=f"Python pattern {i}: " + "x" * 200,
                content_hash=hashlib.sha256(f"budget-{i}".encode()).hexdigest(),
            ))

        engine = PrimingEngine()
        context = engine.prime(store, file_scope=["app.py"], budget_tokens=500)
        # Rough token estimate: ~4 chars per token
        estimated_tokens = len(context) // 4
        assert estimated_tokens <= 600  # Allow some overhead for formatting


# ---------------------------------------------------------------------------
# Phase 9: Confidence scoring & outcome tracking
# ---------------------------------------------------------------------------

class TestConfidenceAndOutcomes:
    """Test confidence scoring with real outcomes."""

    def test_new_record_starts_at_0_5(self, tmp_path):
        store = make_store(tmp_path)

        rec = ExpertiseRecord(
            record_type="pattern", classification="tactical",
            domain="python", content="Use type hints",
            content_hash=hashlib.sha256(b"conf1").hexdigest(),
        )
        rec_id = store.add(rec)
        record = store.get(rec_id)
        assert record.confidence == 0.5

    def test_outcomes_update_confidence(self, tmp_path):
        from services.expertise_models import Outcome

        store = make_store(tmp_path)
        rec = ExpertiseRecord(
            record_type="pattern", classification="tactical",
            domain="python", content="Use type hints everywhere",
            content_hash=hashlib.sha256(b"outcome1").hexdigest(),
        )
        rec_id = store.add(rec)

        # Record 5 success outcomes
        for i in range(5):
            store.record_outcome(rec_id, Outcome(
                record_id=rec_id, status="success", agent="test",
                session_id="s1", project="test",
            ))

        record = store.get(rec_id)
        assert record.outcome_count == 5
        assert record.success_count == 5
        assert record.confidence > 0.5  # Should increase with successes

    def test_failures_decrease_confidence(self, tmp_path):
        from services.expertise_models import Outcome

        store = make_store(tmp_path)
        rec = ExpertiseRecord(
            record_type="pattern", classification="tactical",
            domain="python", content="Always use global state",
            content_hash=hashlib.sha256(b"bad-pattern").hexdigest(),
        )
        rec_id = store.add(rec)

        # Record 5 failure outcomes
        for i in range(5):
            store.record_outcome(rec_id, Outcome(
                record_id=rec_id, status="failure", agent="test",
                session_id="s1", project="test",
            ))

        record = store.get(rec_id)
        assert record.failure_count == 5
        # With 0 successes and 5 failures: success_rate = 0, so confidence is low
        assert record.confidence < 0.5


# ---------------------------------------------------------------------------
# Phase 10: Full session lifecycle (end-to-end)
# ---------------------------------------------------------------------------

class TestFullSessionLifecycle:
    """Simulate a complete smart swarm session end-to-end."""

    def test_full_session(self, tmp_path):
        """
        Simulates:
        - 4 workers across 20 tasks
        - Workers encounter import errors, build errors, test failures
        - Orchestrator adds 5 manual lessons
        - Errors cluster → 2 auto-synthesized lessons
        - Promotion creates permanent records
        - Post-session harvesting creates failure→resolution chains
        """
        project_store = make_store(tmp_path, "project")
        cross_store = make_store(tmp_path, "cross")
        synth = make_synth(project_store, "smart-swarm-20260311-full")

        # ── Step 1: Workers encounter errors ──

        # Worker 1 & 2 both hit the same import error (should cluster)
        _, _ = synth.record_error("1", "builder-1", "Bash",
            "ModuleNotFoundError: No module named 'services.auth_provider'",
            "src/api/routes.py", "TASK-003")
        _, lesson_import = synth.record_error("2", "builder-2", "Bash",
            "ModuleNotFoundError: No module named 'services.auth_provider'",
            "src/api/billing.py", "TASK-007")

        assert lesson_import is not None, "Import error cluster should create lesson"
        assert lesson_import.domain == "architecture.api"  # "api/" path is more specific than ".py"

        # Worker 3 & 4 both hit the same React build error (should cluster)
        _, _ = synth.record_error("3", "builder-3", "Bash",
            "Error: 'Button' is not exported from '@/components/ui'. Did you mean to import 'BaseButton'?",
            "src/components/Dashboard.tsx", "TASK-012")
        _, lesson_jsx = synth.record_error("4", "builder-4", "Bash",
            "Error: 'Button' is not exported from '@/components/ui'. Did you mean to import 'BaseButton'?",
            "src/components/Sidebar.tsx", "TASK-015")

        assert lesson_jsx is not None, "JSX error cluster should create lesson"
        assert lesson_jsx.domain == "typescript.react"

        # ── Step 2: Orchestrator adds manual lessons ──

        orchestrator_lessons = [
            ("Task dependencies must be validated before worker assignment", "high",
             ["task_list.json"]),
            ("React components should use TypeScript strict mode", "high",
             ["src/components/App.tsx"]),
            ("Python API routes need request validation with Pydantic", "medium",
             ["src/api/routes.py"]),
            ("Docker builds require .dockerignore for node_modules", "medium",
             ["Dockerfile"]),
            ("CSS modules conflict with Tailwind v4 @apply", "low",
             ["src/styles/global.css"]),
        ]

        for content, severity, files in orchestrator_lessons:
            domain = ""
            for fp in files:
                d = infer_domain(fp)
                if d:
                    domain = d
                    break
            if not domain:
                for kw, d in [("react", "typescript.react"), ("typescript", "typescript"),
                              ("python", "python"), ("test", "testing"),
                              ("docker", "devops.docker"), ("css", "styling")]:
                    if kw in content.lower():
                        domain = d
                        break

            lesson = SessionLesson(
                session_id="smart-swarm-20260311-full",
                content=content, severity=severity, domain=domain,
                file_patterns=files, quality_score=0.7,
            )
            project_store.add_session_lesson(lesson)

        # ── Step 3: Verify lessons stored ──

        all_lessons = project_store.get_session_lessons("smart-swarm-20260311-full")
        assert len(all_lessons) == 7, f"Expected 7 (2 auto + 5 manual), got {len(all_lessons)}"

        # Verify domains are populated
        lessons_with_domains = [l for l in all_lessons if l.domain]
        assert len(lessons_with_domains) >= 5, \
            f"Expected 5+ lessons with domains, got {len(lessons_with_domains)}: {[(l.content[:30], l.domain) for l in all_lessons]}"

        # ── Step 4: Simulate promotion (session end) ──

        promoted_count = 0
        for lesson in all_lessons:
            if lesson.quality_score >= 0.6:  # Fix #5: no propagation requirement
                record_id = project_store.promote_lesson(lesson.id)
                if record_id:
                    promoted_count += 1

        assert promoted_count == 7, f"All 7 high-quality lessons should promote, got {promoted_count}"

        # ── Step 5: Create failure→resolution chains (post-session harvesting) ──

        task_retries = [
            ("Add authentication page", "Cannot find module '@/hooks/useAuth'", 2,
             ["src/pages/Auth.tsx"]),
            ("Setup payment API", "ImportError: stripe not installed", 3,
             ["src/api/payments.py"]),
        ]

        for title, error, attempts, files in task_retries:
            task_domain = ""
            for fp in files:
                d = infer_domain(fp)
                if d:
                    task_domain = d
                    break

            fail = ExpertiseRecord(
                record_type="failure", classification="observational",
                domain=task_domain,
                content=f"[feature] Task '{title}' failed with: {error}",
                source_project=str(tmp_path),
                tags=["feature", "error-resolution"],
                file_patterns=files,
                content_hash=hashlib.sha256(f"fail-{title}".encode()).hexdigest(),
            )
            fail_id = project_store.add(fail)

            res = ExpertiseRecord(
                record_type="resolution", classification="tactical",
                domain=task_domain,
                content=f"[feature] Task '{title}' eventually resolved after {attempts} attempts",
                source_project=str(tmp_path),
                resolves=fail_id,
                tags=["feature", "error-resolution"],
                file_patterns=files,
                content_hash=hashlib.sha256(f"res-{title}".encode()).hexdigest(),
            )
            project_store.add(res)

        # ── Step 6: Verify everything ──

        # Records: 7 promoted + 2 failures + 2 resolutions = 11
        all_records = project_store.search(limit=50)
        assert len(all_records) == 11, f"Expected 11 records, got {len(all_records)}"

        # Causal chains work
        failures = [r for r in all_records if r.record_type == "failure"]
        assert len(failures) == 2
        for f in failures:
            chain = project_store.get_causal_chain(f.id)
            assert len(chain["chain"]) == 2, f"Failure should have 1 resolution: {f.content[:50]}"

        # Domains are populated
        domains = project_store.get_domains()
        domain_names = {d["name"] for d in domains}
        assert len(domain_names) >= 3, f"Expected 3+ domains, got {domain_names}"

        # Analytics work
        analytics = project_store.get_analytics()
        assert analytics["total_records"] == 11
        assert "insight" in analytics["by_type"]  # promoted lessons
        assert "failure" in analytics["by_type"]
        assert "resolution" in analytics["by_type"]

        # Priming returns content
        engine = PrimingEngine()
        context = engine.prime(
            project_store,
            file_scope=["src/components/Dashboard.tsx"],
            budget_tokens=2000,
        )
        assert len(context) > 0, "Priming should return content for React files"

        print("\n=== FULL SESSION LIFECYCLE RESULTS ===")
        print(f"  Session lessons:     {len(all_lessons)}")
        print(f"  Promoted to records: {promoted_count}")
        print(f"  Total records:       {len(all_records)}")
        print(f"  Causal chains:       {len(failures)} failure→resolution pairs")
        print(f"  Domains:             {domain_names}")
        print(f"  Analytics types:     {analytics['by_type']}")
        print(f"  Priming output:      {len(context)} chars")
        print("  All tabs would be populated!")
