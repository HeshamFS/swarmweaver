"use client";

import { useState, useEffect, useRef } from "react";

interface TimelineEvent {
  timestamp: string;
  agent: string;
  type: string;
  summary: string;
  details?: string | Record<string, unknown>;
}

const EVENT_TYPE_ICONS: Record<string, string> = {
  tool_call: "\u{1F527}",
  file_created: "\u{1F4C4}",
  file_modified: "\u{270F}\uFE0F",
  test_passed: "\u2705",
  test_failed: "\u274C",
  error: "\u{1F6A8}",
  mail_sent: "\u{1F4E8}",
  mail_received: "\u{1F4EC}",
  status_change: "\u{1F504}",
  merge: "\u{1F500}",
  commit: "\u{1F4BE}",
  phase_change: "\u{1F3AF}",
  task_completed: "\u2705",
  worker_done: "\u{1F3C1}",
  dispatch: "\u{1F4E4}",
  escalation: "\u26A0\uFE0F",
  merge_success: "\u2705\u{1F500}",
  merge_failed: "\u274C\u{1F500}",
};

const ESCALATION_TYPES = new Set(["escalation"]);

const AGENT_COLORS = [
  "text-accent",
  "text-info",
  "text-success",
  "text-warning",
  "text-[#bc8cff]",
  "text-[#ff69b4]",
  "text-[#00ADD8]",
  "text-[#f1e05a]",
];

export function TimelinePanel({ projectDir }: { projectDir: string }) {
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [agentFilter, setAgentFilter] = useState<string>("");
  const [typeFilter, setTypeFilter] = useState<string>("");
  const [autoScroll, setAutoScroll] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);
  const agentColorMap = useRef<Record<string, string>>({});
  let colorIdx = 0;

  const getAgentColor = (agent: string): string => {
    if (!agentColorMap.current[agent]) {
      agentColorMap.current[agent] = AGENT_COLORS[colorIdx % AGENT_COLORS.length];
      colorIdx++;
    }
    return agentColorMap.current[agent];
  };

  useEffect(() => {
    if (!projectDir) return;
    setLoading(true);

    const fetchTimeline = () => {
      const params = new URLSearchParams({ path: projectDir, limit: "200" });
      if (agentFilter) params.set("agent", agentFilter);

      fetch(`/api/timeline?${params}`)
        .then((r) => (r.ok ? r.json() : { events: [] }))
        .then((data) => setEvents(data.events || []))
        .catch(() => {})
        .finally(() => setLoading(false));
    };

    fetchTimeline();
    const interval = setInterval(fetchTimeline, 5000);
    return () => clearInterval(interval);
  }, [projectDir, agentFilter]);

  // Auto-scroll
  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events, autoScroll]);

  const filteredEvents = typeFilter
    ? events.filter((e) => e.type === typeFilter)
    : events;

  // Get unique agents and types
  const agents = Array.from(new Set(events.map((e) => e.agent).filter(Boolean)));
  const types = Array.from(new Set(events.map((e) => e.type).filter(Boolean)));

  if (loading && events.length === 0) {
    return (
      <div className="flex items-center justify-center h-32 text-xs text-text-muted">
        Loading timeline...
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Filters */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border-subtle bg-surface-raised shrink-0">
        <select
          value={agentFilter}
          onChange={(e) => setAgentFilter(e.target.value)}
          className="rounded-md border border-border-subtle bg-surface px-2 py-0.5 text-[10px] font-mono text-text-primary"
        >
          <option value="">All agents</option>
          {agents.map((a) => (
            <option key={a} value={a}>{a}</option>
          ))}
        </select>
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="rounded-md border border-border-subtle bg-surface px-2 py-0.5 text-[10px] font-mono text-text-primary"
        >
          <option value="">All types</option>
          {types.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        <div className="flex-1" />
        <label className="flex items-center gap-1 text-[10px] text-text-muted cursor-pointer">
          <input
            type="checkbox"
            checked={autoScroll}
            onChange={(e) => setAutoScroll(e.target.checked)}
            className="rounded"
          />
          Auto-scroll
        </label>
        <span className="text-[10px] font-mono text-text-muted">{filteredEvents.length} events</span>
      </div>

      {/* Event list */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto min-h-0">
        {filteredEvents.length === 0 ? (
          <div className="flex items-center justify-center h-32 text-xs text-text-muted">
            No timeline events yet.
          </div>
        ) : (
          <div className="divide-y divide-border-subtle/30">
            {filteredEvents.map((evt, i) => {
              const icon = EVENT_TYPE_ICONS[evt.type] || "\u2022";
              const agentColor = getAgentColor(evt.agent);

              const isEscalation = ESCALATION_TYPES.has(evt.type);

              return (
                <div key={i} className={`flex items-start gap-2 px-3 py-1.5 hover:bg-surface-raised/30 transition-colors ${isEscalation ? "bg-warning/10 border-l-2 border-warning" : ""}`}>
                  {/* Timestamp */}
                  <span className="text-[9px] font-mono text-text-muted shrink-0 w-16 pt-0.5">
                    {new Date(evt.timestamp).toLocaleTimeString()}
                  </span>
                  {/* Agent lane marker */}
                  <span className={`text-[10px] font-mono shrink-0 w-12 truncate pt-0.5 ${agentColor}`}>
                    {evt.agent || "sys"}
                  </span>
                  {/* Icon */}
                  <span className="text-xs shrink-0 pt-0.5">{icon}</span>
                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <span className="text-xs text-text-secondary">{evt.summary}</span>
                    {evt.details && (
                      <p className="text-[10px] text-text-muted mt-0.5 truncate">
                        {typeof evt.details === "string" ? evt.details : JSON.stringify(evt.details)}
                      </p>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
