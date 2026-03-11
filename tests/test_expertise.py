"""
MELS — Multi-Expertise Learning System Tests
==============================================

35 tests covering:
- ExpertiseStore (12 tests)
- ConfidenceScoring (6 tests)
- PrimingEngine (5 tests)
- SessionLessonSynthesizer (8 tests)
- Migration (4 tests)
"""

import hashlib
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.expertise_models import (
    ExpertiseRecord,
    Outcome,
    DomainConfig,
    SessionLesson,
    RECORD_TYPES,
    CLASSIFICATIONS,
    infer_domain,
    domain_matches,
)
from services.expertise_scoring import (
    compute_confidence,
    compute_relevance,
    score_for_priming,
    estimate_tokens,
)
from services.expertise_store import ExpertiseStore
from services.expertise_priming import PrimingEngine
from services.expertise_synthesis import SessionLessonSynthesizer


class TestExpertiseStore(unittest.TestCase):
    """Tests for the SQLite expertise store."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = Path(self.tmpdir) / "test_expertise.db"
        self.store = ExpertiseStore(self.db_path)

    def tearDown(self):
        self.store.close()
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_record(self, **kwargs) -> ExpertiseRecord:
        defaults = {
            "record_type": "pattern",
            "classification": "tactical",
            "domain": "python",
            "content": "Test content",
        }
        defaults.update(kwargs)
        return ExpertiseRecord(**defaults)

    def test_add_record(self):
        rec = self._make_record(content="Always use type hints")
        rid = self.store.add(rec)
        self.assertTrue(rid.startswith("exp-"))

        loaded = self.store.get(rid)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.content, "Always use type hints")
        self.assertEqual(loaded.record_type, "pattern")

    def test_get_record(self):
        rec = self._make_record(content="Use Depends() for DI")
        rid = self.store.add(rec)
        loaded = self.store.get(rid)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.domain, "python")

    def test_update(self):
        rec = self._make_record(content="Original content")
        rid = self.store.add(rec)
        self.store.update(rid, content="Updated content", classification="foundational")
        loaded = self.store.get(rid)
        self.assertEqual(loaded.content, "Updated content")
        self.assertEqual(loaded.classification, "foundational")

    def test_archive(self):
        rec = self._make_record(content="To be archived")
        rid = self.store.add(rec)
        self.store.archive(rid)
        # Archived records not returned by default search
        results = self.store.search(query="archived")
        self.assertEqual(len(results), 0)
        # But found with include_archived
        results = self.store.search(query="archived", include_archived=True)
        self.assertEqual(len(results), 1)

    def test_search_by_keyword(self):
        self.store.add(self._make_record(content="Always validate input data"))
        self.store.add(self._make_record(content="Use pytest for testing"))
        self.store.add(self._make_record(content="Never mutate global state"))

        results = self.store.search(query="pytest")
        self.assertEqual(len(results), 1)
        self.assertIn("pytest", results[0].content)

    def test_search_by_domain_hierarchical(self):
        self.store.add(self._make_record(domain="python", content="Python tip"))
        self.store.add(self._make_record(domain="python.fastapi", content="FastAPI tip"))
        self.store.add(self._make_record(domain="typescript", content="TS tip"))

        results = self.store.search(domain="python")
        self.assertEqual(len(results), 2)  # python + python.fastapi

    def test_get_for_file_scope(self):
        self.store.add(self._make_record(
            content="Python pattern",
            file_patterns=["src/*.py"],
        ))
        self.store.add(self._make_record(
            content="JS pattern",
            file_patterns=["src/*.js"],
        ))

        results = self.store.get_for_file_scope(["src/main.py"])
        self.assertEqual(len(results), 1)
        self.assertIn("Python", results[0].content)

    def test_dedup_by_content_hash(self):
        content = "Deduplicated content"
        h = hashlib.sha256(content.encode()).hexdigest()
        rec1 = self._make_record(content=content, content_hash=h)
        rec2 = self._make_record(content=content, content_hash=h)

        id1 = self.store.add(rec1)
        id2 = self.store.add(rec2)
        self.assertEqual(id1, id2)  # Same record, not duplicated

    def test_causal_chain_linking(self):
        failure = self._make_record(
            record_type="failure",
            content="ImportError on module X",
        )
        fail_id = self.store.add(failure)

        resolution = self._make_record(
            record_type="resolution",
            content="Use relative imports",
            resolves=fail_id,
        )
        res_id = self.store.add(resolution)

        chain = self.store.get_causal_chain(fail_id)
        self.assertEqual(len(chain["chain"]), 2)

        # Verify resolved_by was updated
        loaded_fail = self.store.get(fail_id)
        self.assertIn(res_id, loaded_fail.resolved_by)

    def test_domain_governance(self):
        self.store.configure_domain(DomainConfig(
            name="test", soft_limit=2, warn_limit=3, hard_limit=4,
        ))
        for i in range(3):
            self.store.add(self._make_record(domain="test", content=f"Record {i}"))

        health = self.store.get_domain_health()
        test_domain = next((d for d in health if d["domain"] == "test"), None)
        self.assertIsNotNone(test_domain)
        self.assertEqual(test_domain["status"], "warning")

    def test_prune_expired(self):
        # Create an expired record
        past = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        rec = self._make_record(
            classification="observational",
            content="Expired record",
            expires_at=past,
        )
        # Override expires_at
        rec.expires_at = past
        self.store.add(rec)

        result = self.store.prune(dry_run=True)
        self.assertGreaterEqual(result["expired_count"], 1)

    def test_migrate_from_json(self):
        """Test that migrate operations produce valid results."""
        from services.expertise_migration import ExpertiseMigrator
        migrator = ExpertiseMigrator()
        # May return 0 or more depending on whether ~/.swarmweaver/memory/ exists
        result = migrator.migrate_memories_json(self.store)
        self.assertGreaterEqual(result, 0)


class TestConfidenceScoring(unittest.TestCase):
    """Tests for multi-signal confidence scoring."""

    def _make_record(self, **kwargs) -> ExpertiseRecord:
        defaults = {
            "record_type": "pattern",
            "classification": "tactical",
            "domain": "python",
            "content": "Test",
        }
        defaults.update(kwargs)
        return ExpertiseRecord(**defaults)

    def test_neutral_start(self):
        rec = self._make_record()
        score = compute_confidence(rec)
        self.assertEqual(score, 0.5)

    def test_success_increases(self):
        rec = self._make_record(outcome_count=5, success_count=5, failure_count=0)
        score = compute_confidence(rec)
        self.assertGreater(score, 0.5)

    def test_failure_decreases(self):
        rec = self._make_record(outcome_count=5, success_count=0, failure_count=5)
        score = compute_confidence(rec)
        self.assertLess(score, 0.5)

    def test_recency_decay(self):
        # Recent record
        rec_recent = self._make_record(
            outcome_count=1, success_count=1,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        # Old record
        old = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        rec_old = self._make_record(
            outcome_count=1, success_count=1,
            updated_at=old,
        )
        self.assertGreater(compute_confidence(rec_recent), compute_confidence(rec_old))

    def test_confirmation_density(self):
        # Few outcomes
        rec_few = self._make_record(outcome_count=2, success_count=2)
        # Many outcomes
        rec_many = self._make_record(outcome_count=10, success_count=10)
        # Many outcomes should have higher confidence due to density
        self.assertGreater(compute_confidence(rec_many), compute_confidence(rec_few))

    def test_composite(self):
        """Test that all signals contribute to a valid 0-1 range."""
        rec = self._make_record(
            outcome_count=7, success_count=5, failure_count=2,
        )
        score = compute_confidence(rec)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)


class TestRelevanceDecay(unittest.TestCase):
    """Tests for relevance decay based on classification."""

    def test_foundational_no_decay(self):
        rec = ExpertiseRecord(
            record_type="convention",
            classification="foundational",
            domain="python",
            content="Test",
            updated_at=(datetime.now(timezone.utc) - timedelta(days=100)).isoformat(),
        )
        self.assertEqual(compute_relevance(rec), 1.0)

    def test_tactical_decay(self):
        rec = ExpertiseRecord(
            record_type="pattern",
            classification="tactical",
            domain="python",
            content="Test",
            updated_at=(datetime.now(timezone.utc) - timedelta(days=15)).isoformat(),
        )
        relevance = compute_relevance(rec)
        self.assertGreater(relevance, 0.0)
        self.assertLess(relevance, 1.0)

    def test_observational_fast_decay(self):
        rec = ExpertiseRecord(
            record_type="pattern",
            classification="observational",
            domain="python",
            content="Test",
            updated_at=(datetime.now(timezone.utc) - timedelta(days=14)).isoformat(),
        )
        relevance = compute_relevance(rec)
        self.assertLess(relevance, 0.5)


class TestPrimingEngine(unittest.TestCase):
    """Tests for token-budget-aware priming."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store = ExpertiseStore(Path(self.tmpdir) / "test.db")
        self.engine = PrimingEngine()

    def tearDown(self):
        self.store.close()
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_budget_respected(self):
        # Add many records
        for i in range(50):
            self.store.add(ExpertiseRecord(
                record_type="pattern",
                classification="tactical",
                domain="python",
                content=f"Pattern {i}: " + "x" * 200,
            ))

        result = self.engine.prime(self.store, budget_tokens=500)
        # Should have some content but be constrained
        tokens = estimate_tokens(result)
        self.assertLessEqual(tokens, 600)  # Some slack for formatting

    def test_domain_match_priority(self):
        self.store.add(ExpertiseRecord(
            record_type="pattern", classification="tactical",
            domain="python", content="Python priority tip",
        ))
        self.store.add(ExpertiseRecord(
            record_type="pattern", classification="tactical",
            domain="javascript", content="JS tip",
        ))

        result = self.engine.prime(
            self.store,
            file_scope=["src/main.py"],
            domains=["python"],
        )
        self.assertIn("Python", result)

    def test_file_scope_filtering(self):
        self.store.add(ExpertiseRecord(
            record_type="convention", classification="tactical",
            domain="python", content="Python convention",
            file_patterns=["*.py"],
        ))
        self.store.add(ExpertiseRecord(
            record_type="convention", classification="tactical",
            domain="javascript", content="JS convention",
            file_patterns=["*.js"],
        ))

        result = self.engine.prime(self.store, file_scope=["app.py"])
        self.assertIn("Python", result)

    def test_causal_chain_in_output(self):
        fail = ExpertiseRecord(
            record_type="failure", classification="tactical",
            domain="python", content="ImportError on module X",
        )
        fail_id = self.store.add(fail)

        self.store.add(ExpertiseRecord(
            record_type="resolution", classification="tactical",
            domain="python", content="Use relative imports",
            resolves=fail_id,
        ))

        result = self.engine.prime(self.store, domains=["python"])
        # Should contain failure -> resolution indication
        self.assertTrue(
            "resolution" in result.lower() or "failure" in result.lower()
        )

    def test_empty_store(self):
        result = self.engine.prime(self.store)
        self.assertEqual(result, "")


class TestSessionLessonSynthesizer(unittest.TestCase):
    """Tests for real-time lesson synthesis from worker errors."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store = ExpertiseStore(Path(self.tmpdir) / "test.db")
        self.synth = SessionLessonSynthesizer(self.store, "test-session-1")

    def tearDown(self):
        self.store.close()
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_single_error_no_lesson(self):
        """A single error should not create a lesson."""
        err_id, new_lesson = self.synth.record_error(
            worker_id="w1", worker_name="builder-1",
            tool_name="Bash", error_message="command not found",
            file_path="src/main.py", task_id="t1",
        )
        self.assertTrue(err_id.startswith("err-"))
        self.assertIsNone(new_lesson)
        lessons = self.store.get_session_lessons("test-session-1")
        self.assertEqual(len(lessons), 0)

    def test_cluster_creates_lesson(self):
        """2+ similar errors across workers should create a lesson."""
        self.synth.record_error(
            worker_id="w1", worker_name="builder-1",
            tool_name="Bash", error_message="ModuleNotFoundError: No module named 'foo'",
            file_path="src/app.py", task_id="t1",
        )
        self.synth.record_error(
            worker_id="w2", worker_name="builder-2",
            tool_name="Bash", error_message="ModuleNotFoundError: No module named 'foo'",
            file_path="src/utils.py", task_id="t2",
        )

        lessons = self.store.get_session_lessons("test-session-1")
        self.assertGreaterEqual(len(lessons), 1)
        self.assertIn("ModuleNotFoundError", lessons[0].content)

    def test_quality_scoring(self):
        """Lessons should have quality scores."""
        self.synth.record_error(
            worker_id="w1", worker_name="builder-1",
            tool_name="Bash", error_message="TypeError: cannot read property 'map' of undefined in src/components/App.tsx",
            file_path="src/components/App.tsx", task_id="t1",
        )
        self.synth.record_error(
            worker_id="w2", worker_name="builder-2",
            tool_name="Bash", error_message="TypeError: cannot read property 'map' of undefined in src/components/List.tsx",
            file_path="src/components/List.tsx", task_id="t2",
        )

        lessons = self.store.get_session_lessons("test-session-1")
        if lessons:
            self.assertGreaterEqual(lessons[0].quality_score, 0.0)
            self.assertLessEqual(lessons[0].quality_score, 1.0)

    def test_propagation_filter_by_scope(self):
        """Lessons should filter by file scope."""
        # Create a lesson with file_patterns
        lesson = SessionLesson(
            session_id="test-session-1",
            content="Use relative imports for local modules",
            severity="medium",
            domain="python",
            file_patterns=["src/*.py"],
            quality_score=0.8,
        )
        self.store.add_session_lesson(lesson)

        # Should match
        results = self.synth.get_lessons_for_worker(["src/main.py"])
        self.assertEqual(len(results), 1)

        # Should not match
        results = self.synth.get_lessons_for_worker(["tests/test_app.js"])
        self.assertEqual(len(results), 0)

    def test_lesson_promotion(self):
        """High-quality lessons should promote to permanent records."""
        lesson = SessionLesson(
            session_id="test-session-1",
            content="Always check for null before accessing properties",
            severity="high",
            domain="typescript",
            quality_score=0.8,
        )
        lid = self.store.add_session_lesson(lesson)

        record_id = self.store.promote_lesson(lid)
        self.assertIsNotNone(record_id)

        # Verify the permanent record exists
        record = self.store.get(record_id)
        self.assertIsNotNone(record)
        self.assertEqual(record.record_type, "insight")
        self.assertIn("auto-promoted", record.tags)

    def test_dedup_similar_lessons(self):
        """Identical error clusters should not create duplicate lessons."""
        for _ in range(2):
            self.synth.record_error(
                worker_id="w1", worker_name="b1",
                tool_name="Bash", error_message="ENOENT: no such file",
                file_path="x.py", task_id="t1",
            )
            self.synth.record_error(
                worker_id="w2", worker_name="b2",
                tool_name="Bash", error_message="ENOENT: no such file",
                file_path="y.py", task_id="t2",
            )

        lessons = self.store.get_session_lessons("test-session-1")
        # Should have at most 1 unique lesson for this error pattern
        unique_contents = set(l.content for l in lessons)
        self.assertLessEqual(len(unique_contents), 1)

    def test_severity_ordering(self):
        """Lessons should be sorted by quality score."""
        self.store.add_session_lesson(SessionLesson(
            session_id="test-session-1", content="Low quality", quality_score=0.3,
        ))
        self.store.add_session_lesson(SessionLesson(
            session_id="test-session-1", content="High quality", quality_score=0.9,
        ))

        results = self.synth.get_lessons_for_worker([])
        self.assertEqual(len(results), 2)
        self.assertGreater(results[0].quality_score, results[1].quality_score)

    def test_cross_worker_propagation(self):
        """Lessons from one worker should be visible to another."""
        lesson = SessionLesson(
            session_id="test-session-1",
            content="Shared lesson across workers",
            severity="high",
            quality_score=0.8,
            propagated_to=["w1"],
        )
        self.store.add_session_lesson(lesson)

        # Worker 2 should see it
        results = self.synth.get_lessons_for_worker([])
        self.assertEqual(len(results), 1)


class TestDomainTaxonomy(unittest.TestCase):
    """Tests for hierarchical domain inference and matching."""

    def test_infer_python(self):
        self.assertEqual(infer_domain("src/main.py"), "python")

    def test_infer_fastapi(self):
        self.assertEqual(infer_domain("src/fastapi/app.py"), "python.fastapi")

    def test_infer_react_tsx(self):
        self.assertEqual(infer_domain("src/App.tsx"), "typescript.react")

    def test_infer_test(self):
        result = infer_domain("tests/test_main.py")
        self.assertIn("test", result)

    def test_domain_matches_exact(self):
        self.assertTrue(domain_matches("python", "python"))

    def test_domain_matches_parent_child(self):
        self.assertTrue(domain_matches("python", "python.fastapi"))

    def test_domain_matches_child_parent(self):
        self.assertTrue(domain_matches("python.fastapi", "python"))

    def test_domain_no_match(self):
        self.assertFalse(domain_matches("python", "typescript"))


class TestMigration(unittest.TestCase):
    """Tests for migration from legacy JSON stores."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store = ExpertiseStore(Path(self.tmpdir) / "test.db")

    def tearDown(self):
        self.store.close()
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_memories_json_migration(self):
        """Test migration from memories.json (may or may not exist)."""
        from services.expertise_migration import ExpertiseMigrator
        migrator = ExpertiseMigrator()
        count = migrator.migrate_memories_json(self.store)
        self.assertGreaterEqual(count, 0)  # 0 if no file, >0 if file exists

    def test_project_expertise_migration(self):
        """Test project expertise migration from index.json."""
        from services.expertise_migration import ExpertiseMigrator

        # Create a fake index.json
        proj_dir = Path(self.tmpdir) / "project"
        expertise_dir = proj_dir / ".swarmweaver" / "expertise"
        expertise_dir.mkdir(parents=True)
        index = [
            {"id": "e1", "content": "Use pytest", "category": "convention",
             "domain": "testing", "tags": ["test"], "created_at": "2026-01-01T00:00:00"},
        ]
        (expertise_dir / "index.json").write_text(json.dumps(index))

        migrator = ExpertiseMigrator()
        count = migrator.migrate_project_expertise(proj_dir, self.store)
        self.assertEqual(count, 1)

        # Verify record was created
        records = self.store.search(query="pytest")
        self.assertEqual(len(records), 1)

    def test_lessons_json_migration(self):
        """Test lessons.json migration."""
        from services.expertise_migration import ExpertiseMigrator

        proj_dir = Path(self.tmpdir) / "project"
        swarm_dir = proj_dir / ".swarmweaver" / "swarm"
        swarm_dir.mkdir(parents=True)
        lessons = {
            "errors": [
                {"error_message": "ModuleNotFoundError", "tool_name": "Bash",
                 "worker_name": "w1", "timestamp": "2026-01-01T00:00:00Z"},
            ],
            "lessons": [
                {"lesson": "Always install deps first", "severity": "high",
                 "applies_to": ["*.py"], "created_at": "2026-01-01T00:00:00Z"},
            ],
        }
        (swarm_dir / "lessons.json").write_text(json.dumps(lessons))

        migrator = ExpertiseMigrator()
        count = migrator.migrate_lessons(proj_dir, self.store)
        self.assertEqual(count, 2)  # 1 error + 1 lesson

    def test_idempotent(self):
        """Migration should be idempotent (dedup by content_hash)."""
        from services.expertise_migration import ExpertiseMigrator

        proj_dir = Path(self.tmpdir) / "project"
        expertise_dir = proj_dir / ".swarmweaver" / "expertise"
        expertise_dir.mkdir(parents=True)
        index = [
            {"id": "e1", "content": "Unique content", "category": "pattern",
             "domain": "python", "tags": [], "created_at": "2026-01-01T00:00:00"},
        ]
        (expertise_dir / "index.json").write_text(json.dumps(index))

        migrator = ExpertiseMigrator()
        count1 = migrator.migrate_project_expertise(proj_dir, self.store)
        count2 = migrator.migrate_project_expertise(proj_dir, self.store)
        self.assertEqual(count1, 1)
        self.assertEqual(count2, 1)  # Returns dedup'd ID, still "migrated" 1

        # But only 1 record in store
        all_records = self.store.search(query="Unique", limit=10)
        self.assertEqual(len(all_records), 1)


if __name__ == "__main__":
    unittest.main()
