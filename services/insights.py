"""
Session Insight Analysis
===========================

Automatically extracts learnings from completed agent sessions:
tool usage profiles, hot files, error patterns, and structured insights.
Records insights to the memory system as domain-scoped expertise.
"""

import json
from collections import Counter
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from features.memory import AgentMemory, FILE_DOMAIN_MAP


@dataclass
class SessionInsight:
    """A structured insight extracted from a session."""
    insight_type: str  # pattern, convention, failure, decision
    domain: str        # inferred from file paths
    content: str
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class InsightAnalysis:
    """Complete analysis of a session."""
    top_tools: list[dict]       # [{name, count, avg_duration_ms}]
    hot_files: list[dict]       # [{path, edit_count}] — files edited 3+ times
    error_frequency: int
    total_tool_calls: int
    insights: list[SessionInsight]

    def to_dict(self) -> dict:
        return asdict(self)


def infer_domain_from_path(filepath: str) -> str:
    """Infer expertise domain from a file path."""
    filepath_lower = filepath.lower()
    for pattern, domain in FILE_DOMAIN_MAP.items():
        if pattern in filepath_lower:
            return domain
    return ""


class SessionInsightAnalyzer:
    """
    Analyzes completed sessions to extract learnings.

    Usage:
        analyzer = SessionInsightAnalyzer(project_dir)
        analysis = analyzer.analyze_audit_log()
        count = analyzer.record_to_memory(analysis)
    """

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir

    def analyze_audit_log(self) -> InsightAnalysis:
        """Analyze audit.log to extract tool usage and file patterns."""
        from core.paths import get_paths
        audit_path = get_paths(self.project_dir).resolve_read("audit.log")
        if not audit_path.exists():
            return InsightAnalysis(
                top_tools=[], hot_files=[], error_frequency=0,
                total_tool_calls=0, insights=[],
            )

        tool_counts: Counter = Counter()
        file_edits: Counter = Counter()
        error_count = 0
        total_calls = 0

        try:
            for line in audit_path.read_text(encoding="utf-8", errors="replace").splitlines():
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    tool_name = entry.get("tool_name", "")
                    if tool_name:
                        tool_counts[tool_name] += 1
                        total_calls += 1

                    if entry.get("is_error"):
                        error_count += 1

                    # Track file edits
                    tool_input = entry.get("input", {})
                    if isinstance(tool_input, dict):
                        for key in ("file_path", "path", "filename"):
                            fpath = tool_input.get(key, "")
                            if fpath and isinstance(fpath, str) and tool_name in ("Edit", "Write", "NotebookEdit"):
                                try:
                                    rel = str(Path(fpath).relative_to(self.project_dir))
                                    file_edits[rel] += 1
                                except ValueError:
                                    file_edits[fpath] += 1
                except (json.JSONDecodeError, TypeError):
                    continue
        except OSError:
            pass

        # Top 5 tools
        top_tools = [
            {"name": name, "count": count}
            for name, count in tool_counts.most_common(5)
        ]

        # Hot files (edited 3+ times)
        hot_files = [
            {"path": path, "edit_count": count}
            for path, count in file_edits.most_common(20)
            if count >= 3
        ]

        # Generate insights
        insights = self._generate_insights(tool_counts, hot_files, error_count, total_calls)

        return InsightAnalysis(
            top_tools=top_tools,
            hot_files=hot_files,
            error_frequency=error_count,
            total_tool_calls=total_calls,
            insights=insights,
        )

    def _generate_insights(
        self,
        tool_counts: Counter,
        hot_files: list[dict],
        error_count: int,
        total_calls: int,
    ) -> list[SessionInsight]:
        """Generate structured insights from session data."""
        insights: list[SessionInsight] = []

        # Insight: High error rate
        if total_calls > 10 and error_count / total_calls > 0.15:
            insights.append(SessionInsight(
                insight_type="failure",
                domain="",
                content=f"High error rate: {error_count}/{total_calls} tool calls failed ({error_count/total_calls*100:.0f}%). Consider investigating common failure patterns.",
                tags=["auto-insight", "error-rate"],
            ))

        # Insight: Hot files indicate complexity
        for hf in hot_files[:3]:
            domain = infer_domain_from_path(hf["path"])
            insights.append(SessionInsight(
                insight_type="pattern",
                domain=domain,
                content=f"Hot file: {hf['path']} was edited {hf['edit_count']} times. This file may need refactoring to reduce modification frequency.",
                tags=["auto-insight", "hot-file"],
            ))

        # Insight: Heavy tool usage patterns
        if tool_counts.get("Bash", 0) > total_calls * 0.4:
            insights.append(SessionInsight(
                insight_type="convention",
                domain="devops",
                content="Heavy Bash usage detected. Consider whether dedicated tools (Read, Edit, Grep) would be more efficient.",
                tags=["auto-insight", "tool-usage"],
            ))

        return insights

    def record_to_memory(self, analysis: InsightAnalysis, project_source: str = "") -> int:
        """Record session insights to the memory system."""
        if not analysis.insights:
            return 0

        mem = AgentMemory()
        count = 0
        for insight in analysis.insights:
            category_map = {
                "pattern": "pattern",
                "convention": "pattern",
                "failure": "mistake",
                "decision": "solution",
            }
            mem.add(
                category=category_map.get(insight.insight_type, "pattern"),
                content=insight.content,
                tags=insight.tags,
                project_source=project_source or str(self.project_dir.name),
                domain=insight.domain,
                expertise_type=insight.insight_type,
            )
            count += 1
        return count

    def analyze_and_record(self, project_source: str = "") -> InsightAnalysis:
        """Convenience: analyze session and record insights to memory."""
        analysis = self.analyze_audit_log()
        if analysis.insights:
            self.record_to_memory(analysis, project_source)
        return analysis


def enrich_identity_from_insights(
    identity: "AgentIdentity",
    analysis: InsightAnalysis,
    session_duration_minutes: float = 0,
) -> "AgentIdentity":
    """Enrich agent identity with insights from a completed session.

    Updates tools_preferred, avg_session_duration_minutes, typical_task_types,
    and error_patterns based on the session analysis.

    Args:
        identity: The agent identity to enrich (modified in place and returned).
        analysis: The insight analysis from the completed session.
        session_duration_minutes: Duration of the session in minutes.

    Returns:
        The enriched AgentIdentity.
    """
    # Update tools_preferred from top_tools
    if analysis.top_tools:
        existing_tools = {t['name']: t for t in identity.tools_preferred}
        for tool in analysis.top_tools:
            name = tool.get('name', '')
            if not name:
                continue
            if name in existing_tools:
                existing_tools[name]['count'] = existing_tools[name].get('count', 0) + tool.get('count', 0)
            else:
                existing_tools[name] = {
                    'name': name,
                    'count': tool.get('count', 0),
                    'avg_duration_ms': tool.get('avg_duration_ms', 0),
                }
        identity.tools_preferred = list(existing_tools.values())

    # Update avg session duration (running average)
    if session_duration_minutes > 0:
        n = identity.sessions_completed or 1
        identity.avg_session_duration_minutes = (
            (identity.avg_session_duration_minutes * (n - 1) + session_duration_minutes) / n
        )

    # Extract typical task types from hot files
    if analysis.hot_files:
        task_types = set(identity.typical_task_types)
        for f in analysis.hot_files:
            path = f.get('path', '')
            if 'test' in path.lower():
                task_types.add('Tests')
            elif 'api' in path.lower() or 'route' in path.lower() or 'server' in path.lower():
                task_types.add('API')
            elif any(ext in path for ext in ['.tsx', '.jsx', '.css', '.html']):
                task_types.add('Frontend')
            elif any(ext in path for ext in ['.py', '.rs', '.go', '.java']):
                task_types.add('Backend')
            elif 'config' in path.lower() or '.json' in path or '.yaml' in path:
                task_types.add('Config')
        identity.typical_task_types = list(task_types)[:10]

    # Error patterns from analysis
    if analysis.error_frequency > 0:
        for insight in analysis.insights:
            if insight.insight_type == 'failure':
                existing = next(
                    (p for p in identity.error_patterns if p.get('pattern') == insight.content),
                    None,
                )
                if existing:
                    existing['count'] = existing.get('count', 0) + 1
                    existing['last_seen'] = datetime.now(timezone.utc).isoformat()
                else:
                    identity.error_patterns.append({
                        'pattern': insight.content,
                        'count': 1,
                        'last_seen': datetime.now(timezone.utc).isoformat(),
                    })

    return identity
