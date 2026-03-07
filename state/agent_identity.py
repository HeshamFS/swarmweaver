"""
Agent Identity Persistence
=============================

Gives agents a persistent identity tracking sessions completed,
expertise domains, and recent task history. Enables agent learning
continuity across session boundaries.
"""

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class RecentTask:
    task_id: str
    summary: str
    completed_at: str


@dataclass
class AgentIdentity:
    """Persistent identity for a swarm worker agent."""
    name: str
    capability: str  # builder, reviewer, scout
    created_at: str
    sessions_completed: int = 0
    expertise_domains: list[str] = field(default_factory=list)
    recent_tasks: list[dict] = field(default_factory=list)  # [{task_id, summary, completed_at}]
    success_rate: float = 1.0
    total_tool_calls: int = 0
    domains_touched: dict = field(default_factory=dict)  # {domain: count}
    tools_preferred: list[dict] = field(default_factory=list)  # [{name, count, avg_duration_ms}]
    avg_session_duration_minutes: float = 0.0
    typical_task_types: list[str] = field(default_factory=list)  # ["API", "Tests", "Frontend"]
    error_patterns: list[dict] = field(default_factory=list)  # [{pattern, count, last_seen}]
    collaboration_history: list[dict] = field(default_factory=list)  # [{partner, joint_sessions, success_rate}]

    def to_dict(self) -> dict:
        return asdict(self)

    def add_task(self, task_id: str, summary: str) -> None:
        self.recent_tasks.append({
            "task_id": task_id,
            "summary": summary,
            "completed_at": datetime.now().isoformat(),
        })
        # Keep last 20 tasks
        if len(self.recent_tasks) > 20:
            self.recent_tasks = self.recent_tasks[-20:]

    def add_domain(self, domain: str) -> None:
        if domain and domain not in self.expertise_domains:
            self.expertise_domains.append(domain)

    def increment_sessions(self) -> None:
        self.sessions_completed += 1

    def get_context_section(self) -> str:
        """Format identity as context for prompt injection."""
        lines = [
            "## Agent Identity",
            f"**Name**: {self.name}",
            f"**Role**: {self.capability}",
            f"**Sessions completed**: {self.sessions_completed}",
        ]
        if self.expertise_domains:
            lines.append(f"**Expertise**: {', '.join(self.expertise_domains)}")
        if self.recent_tasks:
            lines.append(f"**Recent tasks**: {len(self.recent_tasks)} completed")
            for t in self.recent_tasks[-3:]:
                lines.append(f"  - {t.get('summary', t.get('task_id', ''))}")
        return "\n".join(lines) + "\n"

    def get_cv(self) -> str:
        """
        Human-readable agent resume with name, capability, sessions,
        domains, recent tasks, and success rate.

        Returns:
            Formatted multi-line string summarizing the agent's profile
        """
        lines = [
            f"# Agent CV: {self.name}",
            f"**Role**: {self.capability}",
            f"**Sessions**: {self.sessions_completed}",
            f"**Success Rate**: {self.success_rate:.0%}",
        ]

        if self.avg_session_duration_minutes:
            lines.append(f"**Avg Session**: {self.avg_session_duration_minutes:.0f} min")

        if self.typical_task_types:
            lines.append(f"**Specializations**: {', '.join(self.typical_task_types)}")

        if self.tools_preferred:
            top_tools = sorted(self.tools_preferred, key=lambda t: t.get('count', 0), reverse=True)[:5]
            lines.append(f"**Top Tools**: {', '.join(t['name'] for t in top_tools)}")

        if self.error_patterns:
            lines.append(f"**Known Issues**: {len(self.error_patterns)} recurring patterns")

        if self.collaboration_history:
            lines.append(f"**Collaborations**: {len(self.collaboration_history)} agents worked with")

        lines.append(f"**Tool Calls**: {self.total_tool_calls}")

        if self.expertise_domains:
            lines.append(f"**Expertise**: {', '.join(self.expertise_domains)}")

        if self.domains_touched:
            sorted_domains = sorted(
                self.domains_touched.items(),
                key=lambda x: x[1],
                reverse=True,
            )
            domain_strs = [f"{d} ({c})" for d, c in sorted_domains[:8]]
            lines.append(f"**Domains Touched**: {', '.join(domain_strs)}")

        if self.recent_tasks:
            lines.append(f"**Recent Tasks** ({len(self.recent_tasks)}):")
            for t in self.recent_tasks[-5:]:
                summary = t.get("summary", t.get("task_id", ""))
                completed = t.get("completed_at", "")[:10]
                lines.append(f"  - [{completed}] {summary}")

        return "\n".join(lines)


class AgentIdentityStore:
    """
    Manages persistent agent identities.

    Stored at: <project>/.swarmweaver/agents/<name>/identity.json
    """

    AGENTS_DIR = ".swarmweaver/agents"

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.agents_dir = project_dir / self.AGENTS_DIR

    def load(self, name: str) -> Optional[AgentIdentity]:
        filepath = self.agents_dir / name / "identity.json"
        if not filepath.exists():
            return None
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            return AgentIdentity(**data)
        except (json.JSONDecodeError, TypeError, KeyError):
            return None

    def save(self, identity: AgentIdentity) -> Path:
        agent_dir = self.agents_dir / identity.name
        agent_dir.mkdir(parents=True, exist_ok=True)
        filepath = agent_dir / "identity.json"
        filepath.write_text(
            json.dumps(identity.to_dict(), indent=2), encoding="utf-8"
        )
        return filepath

    def get_or_create(self, name: str, capability: str = "builder") -> AgentIdentity:
        existing = self.load(name)
        if existing:
            return existing
        identity = AgentIdentity(
            name=name,
            capability=capability,
            created_at=datetime.now().isoformat(),
        )
        self.save(identity)
        return identity

    def list_agents(self) -> list[AgentIdentity]:
        if not self.agents_dir.exists():
            return []
        results = []
        for d in self.agents_dir.iterdir():
            if d.is_dir():
                identity = self.load(d.name)
                if identity:
                    results.append(identity)
        return results

    def update_after_session(
        self,
        name: str,
        completed_tasks: list[dict],
        domains: list[str],
    ) -> AgentIdentity:
        identity = self.get_or_create(name)
        identity.increment_sessions()
        for task in completed_tasks:
            identity.add_task(
                task.get("id", ""),
                task.get("title", task.get("summary", "")),
            )
        for domain in domains:
            identity.add_domain(domain)
        self.save(identity)
        return identity
