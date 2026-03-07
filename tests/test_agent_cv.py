"""
Test Agent CV Enhancement (state/agent_identity.py)
=====================================================

Tests enhanced AgentIdentity fields: tools_preferred,
avg_session_duration_minutes, typical_task_types, error_patterns,
collaboration_history.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from state.agent_identity import AgentIdentity, AgentIdentityStore


# ---------------------------------------------------------------------------
# AgentIdentity — new fields exist
# ---------------------------------------------------------------------------

def test_identity_has_tools_preferred():
    """AgentIdentity should have tools_preferred field."""
    agent = AgentIdentity(name="test", capability="builder", created_at="2026-01-01")
    assert hasattr(agent, "tools_preferred")
    assert isinstance(agent.tools_preferred, list)


def test_identity_has_avg_session_duration():
    """AgentIdentity should have avg_session_duration_minutes field."""
    agent = AgentIdentity(name="test", capability="builder", created_at="2026-01-01")
    assert hasattr(agent, "avg_session_duration_minutes")
    assert agent.avg_session_duration_minutes == 0.0


def test_identity_has_typical_task_types():
    """AgentIdentity should have typical_task_types field."""
    agent = AgentIdentity(name="test", capability="builder", created_at="2026-01-01")
    assert hasattr(agent, "typical_task_types")
    assert isinstance(agent.typical_task_types, list)


def test_identity_has_error_patterns():
    """AgentIdentity should have error_patterns field."""
    agent = AgentIdentity(name="test", capability="builder", created_at="2026-01-01")
    assert hasattr(agent, "error_patterns")
    assert isinstance(agent.error_patterns, list)


def test_identity_has_collaboration_history():
    """AgentIdentity should have collaboration_history field."""
    agent = AgentIdentity(name="test", capability="builder", created_at="2026-01-01")
    assert hasattr(agent, "collaboration_history")
    assert isinstance(agent.collaboration_history, list)


# ---------------------------------------------------------------------------
# AgentIdentity — CV generation
# ---------------------------------------------------------------------------

def test_get_cv_basic():
    """get_cv includes basic agent info."""
    agent = AgentIdentity(
        name="builder-1",
        capability="builder",
        created_at="2026-01-01",
        sessions_completed=5,
        success_rate=0.8,
    )
    cv = agent.get_cv()
    assert "builder-1" in cv
    assert "builder" in cv.lower()


def test_get_cv_with_enhanced_fields():
    """get_cv includes enhanced fields when populated."""
    agent = AgentIdentity(
        name="builder-1",
        capability="builder",
        created_at="2026-01-01",
        sessions_completed=10,
        success_rate=0.9,
        avg_session_duration_minutes=15.0,
        typical_task_types=["API", "Tests", "Frontend"],
        tools_preferred=[
            {"name": "Edit", "count": 50},
            {"name": "Bash", "count": 30},
        ],
        error_patterns=[
            {"pattern": "Import error", "count": 3},
        ],
        collaboration_history=[
            {"partner": "reviewer-1", "joint_sessions": 5, "success_rate": 0.8},
        ],
    )
    cv = agent.get_cv()
    assert "15" in cv  # avg session duration
    assert any(t in cv for t in ["API", "Tests", "Frontend"])


# ---------------------------------------------------------------------------
# AgentIdentity — task tracking
# ---------------------------------------------------------------------------

def test_add_task():
    """add_task adds to recent_tasks."""
    agent = AgentIdentity(name="test", capability="builder", created_at="2026-01-01")
    agent.add_task("task-1", "Implement login")
    assert len(agent.recent_tasks) == 1


def test_add_task_max_20():
    """add_task keeps only last 20 tasks."""
    agent = AgentIdentity(name="test", capability="builder", created_at="2026-01-01")
    for i in range(25):
        agent.add_task(f"task-{i}", f"Task {i}")
    assert len(agent.recent_tasks) <= 20


# ---------------------------------------------------------------------------
# AgentIdentity — domain tracking
# ---------------------------------------------------------------------------

def test_add_domain():
    """add_domain adds unique domains to expertise_domains."""
    agent = AgentIdentity(name="test", capability="builder", created_at="2026-01-01")
    agent.add_domain("python")
    agent.add_domain("python")  # duplicate, should not be added again
    agent.add_domain("testing")
    assert "python" in agent.expertise_domains
    assert "testing" in agent.expertise_domains
    assert len(agent.expertise_domains) == 2  # no duplicates


# ---------------------------------------------------------------------------
# AgentIdentityStore
# ---------------------------------------------------------------------------

def test_store_save_load(tmp_path):
    """Store can save and load agent identity."""
    store = AgentIdentityStore(tmp_path)
    agent = AgentIdentity(
        name="builder-1",
        capability="builder",
        created_at="2026-01-01",
        tools_preferred=[{"name": "Edit", "count": 10}],
        typical_task_types=["API"],
    )
    store.save(agent)

    loaded = store.load("builder-1")
    assert loaded is not None
    assert loaded.name == "builder-1"
    assert len(loaded.tools_preferred) == 1


def test_store_get_or_create(tmp_path):
    """get_or_create creates new identity if not found."""
    store = AgentIdentityStore(tmp_path)
    agent = store.get_or_create("new-agent", "scout")
    assert agent.name == "new-agent"
    assert agent.capability == "scout"


def test_store_list_agents(tmp_path):
    """list_agents returns all saved agents."""
    store = AgentIdentityStore(tmp_path)
    store.save(AgentIdentity(name="a1", capability="builder", created_at="2026-01-01"))
    store.save(AgentIdentity(name="a2", capability="reviewer", created_at="2026-01-01"))

    agents = store.list_agents()
    names = [a.name for a in agents]
    assert "a1" in names
    assert "a2" in names


def test_store_update_after_session(tmp_path):
    """update_after_session updates stats."""
    store = AgentIdentityStore(tmp_path)
    store.save(AgentIdentity(name="b1", capability="builder", created_at="2026-01-01"))

    agent = store.update_after_session(
        "b1",
        completed_tasks=[{"id": "t1", "title": "Task 1"}, {"id": "t2", "title": "Task 2"}],
        domains=["python"],
    )
    assert agent.sessions_completed >= 1
