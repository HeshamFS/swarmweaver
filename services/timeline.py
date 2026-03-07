"""
Cross-Agent Timeline
======================

Merges events from EventStore, MailStore, and audit logs into a single
chronological stream for the observability dashboard.
"""

import json
from pathlib import Path
from typing import Optional


class CrossAgentTimeline:
    """
    Unified timeline that merges events from multiple sources:
      - EventStore (SQLite) — tool calls, sessions, errors
      - MailStore (SQLite) — inter-agent messages
      - Audit log (NDJSON) — raw tool call audit trail

    Each merged event: {timestamp, agent, type, summary, details}
    """

    def get_timeline(
        self,
        project_dir: Path,
        since: Optional[str] = None,
        limit: int = 200,
        agent_filter: Optional[str] = None,
    ) -> list[dict]:
        """
        Merge events from all sources into a single chronological stream.

        Args:
            project_dir: Project root directory.
            since: ISO timestamp — only return events after this time.
            limit: Maximum number of events to return.
            agent_filter: Only include events from this agent name.

        Returns:
            List of dicts sorted newest-first:
            [{timestamp, agent, type, summary, details}, ...]
        """
        merged: list[dict] = []

        # --- Source 1: EventStore ---
        merged.extend(self._load_event_store(project_dir, since, agent_filter))

        # --- Source 2: MailStore ---
        merged.extend(self._load_mail_store(project_dir, since, agent_filter))

        # --- Source 3: Audit log (NDJSON) ---
        merged.extend(self._load_audit_log(project_dir, since, agent_filter))

        # Sort by timestamp descending (newest first)
        merged.sort(key=lambda e: e.get("timestamp", ""), reverse=True)

        return merged[:limit]

    def get_timeline_stats(self, project_dir: Path) -> dict:
        """
        Summary statistics across all timeline sources.

        Returns:
            {total_events, events_by_type, events_by_agent, time_range}
        """
        all_events = self.get_timeline(project_dir, limit=10000)

        by_type: dict[str, int] = {}
        by_agent: dict[str, int] = {}
        timestamps: list[str] = []

        for ev in all_events:
            t = ev.get("type", "unknown")
            a = ev.get("agent", "unknown")
            by_type[t] = by_type.get(t, 0) + 1
            by_agent[a] = by_agent.get(a, 0) + 1
            if ev.get("timestamp"):
                timestamps.append(ev["timestamp"])

        time_range = {}
        if timestamps:
            time_range = {"earliest": min(timestamps), "latest": max(timestamps)}

        return {
            "total_events": len(all_events),
            "events_by_type": by_type,
            "events_by_agent": by_agent,
            "time_range": time_range,
        }

    # ------------------------------------------------------------------
    # Private source loaders
    # ------------------------------------------------------------------

    def _load_event_store(
        self,
        project_dir: Path,
        since: Optional[str],
        agent_filter: Optional[str],
    ) -> list[dict]:
        results: list[dict] = []
        try:
            from state.events import EventStore

            store = EventStore(project_dir)
            if not store.db_path.exists():
                return results
            store.initialize()
            records = store.query(
                agent_name=agent_filter,
                since=since,
                limit=500,
            )
            for r in records:
                results.append({
                    "timestamp": r.created_at,
                    "agent": r.agent_name or "orchestrator",
                    "type": r.event_type,
                    "summary": f"{r.event_type}: {r.tool_name}" if r.tool_name else r.event_type,
                    "details": r.data,
                    "source": "event_store",
                })
            store.close()
        except Exception:
            pass
        return results

    def _load_mail_store(
        self,
        project_dir: Path,
        since: Optional[str],
        agent_filter: Optional[str],
    ) -> list[dict]:
        results: list[dict] = []
        try:
            from state.mail import MailStore

            store = MailStore(project_dir)
            if not store.db_path.exists():
                return results
            store.initialize()
            messages = store.get_messages(
                sender=agent_filter,
                limit=500,
            )
            for m in messages:
                if since and m.created_at < since:
                    continue
                results.append({
                    "timestamp": m.created_at,
                    "agent": m.sender,
                    "type": f"mail:{m.msg_type}",
                    "summary": m.subject,
                    "details": {
                        "recipient": m.recipient,
                        "body": m.body[:300] if m.body else "",
                        "priority": m.priority,
                    },
                    "source": "mail_store",
                })
            store.close()
        except Exception:
            pass
        return results

    def _load_audit_log(
        self,
        project_dir: Path,
        since: Optional[str],
        agent_filter: Optional[str],
    ) -> list[dict]:
        results: list[dict] = []
        from core.paths import get_paths
        audit_path = get_paths(project_dir).resolve_read("audit.log")
        if not audit_path.exists():
            return results
        try:
            for line in audit_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                ts = entry.get("timestamp", "")
                if since and ts < since:
                    continue

                agent = entry.get("agent_name", "orchestrator")
                if agent_filter and agent != agent_filter:
                    continue

                tool = entry.get("tool_name", "")
                results.append({
                    "timestamp": ts,
                    "agent": agent,
                    "type": "audit:" + ("error" if entry.get("is_error") else "tool_call"),
                    "summary": f"audit: {tool}" if tool else "audit entry",
                    "details": {
                        k: v for k, v in entry.items()
                        if k not in ("timestamp", "agent_name")
                    },
                    "source": "audit_log",
                })
        except OSError:
            pass
        return results
