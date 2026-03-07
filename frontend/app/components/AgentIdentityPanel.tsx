"use client";

import { useState, useEffect, useCallback, useMemo } from "react";

interface AgentIdentity {
  name: string;
  capability: string;
  created_at: string;
  sessions_completed: number;
  expertise_domains: string[];
  recent_tasks: { task_id: string; summary: string; completed_at: string }[];
  success_rate: number;
  total_tool_calls: number;
  domains_touched: Record<string, number>;
  tools_preferred?: { name: string; count: number; avg_duration_ms?: number }[];
  avg_session_duration_minutes?: number;
  typical_task_types?: string[];
  error_patterns?: { pattern: string; count: number; last_seen?: string }[];
  collaboration_history?: { partner: string; joint_sessions: number; success_rate: number }[];
}

const CAPABILITY_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  scout: { bg: "bg-warning/10", text: "text-warning", border: "border-warning/30" },
  builder: { bg: "bg-accent/10", text: "text-accent", border: "border-accent/30" },
  reviewer: { bg: "bg-info/10", text: "text-info", border: "border-info/30" },
  lead: { bg: "bg-[#bc8cff]/10", text: "text-[#bc8cff]", border: "border-[#bc8cff]/30" },
  coordinator: { bg: "bg-[#bc8cff]/10", text: "text-[#bc8cff]", border: "border-[#bc8cff]/30" },
  merger: { bg: "bg-purple-400/10", text: "text-purple-400", border: "border-purple-400/30" },
};

const CAPABILITY_AVATARS: Record<string, string> = {
  scout: "\u{1F50D}",
  builder: "\u{1F528}",
  reviewer: "\u{1F4CB}",
  lead: "\u{1F451}",
  coordinator: "\u{1F451}",
  merger: "\u{1F500}",
};

const DOMAIN_COLORS: Record<string, string> = {
  python: "bg-[#3572A5]/15 text-[#3572A5] border-[#3572A5]/30",
  typescript: "bg-[#3178c6]/15 text-[#3178c6] border-[#3178c6]/30",
  javascript: "bg-[#f1e05a]/15 text-[#f1e05a] border-[#f1e05a]/30",
  database: "bg-[#e38c00]/15 text-[#e38c00] border-[#e38c00]/30",
  testing: "bg-success/15 text-success border-success/30",
  frontend: "bg-info/15 text-info border-info/30",
  devops: "bg-warning/15 text-warning border-warning/30",
  security: "bg-error/15 text-error border-error/30",
};

const TASK_TYPE_COLORS: Record<string, string> = {
  API: "bg-accent/10 text-accent",
  Tests: "bg-success/10 text-success",
  Frontend: "bg-info/10 text-info",
  Backend: "bg-[#3572A5]/10 text-[#3572A5]",
  Config: "bg-warning/10 text-warning",
};

/* ------------------------------------------------------------------ */
/*  Section heading                                                    */
/* ------------------------------------------------------------------ */
function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <span className="text-[10px] font-mono text-text-muted uppercase tracking-wider">
      {children}
    </span>
  );
}

/* ------------------------------------------------------------------ */
/*  Metric cell for the performance grid                               */
/* ------------------------------------------------------------------ */
function MetricCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-border-subtle/30 bg-surface px-2 py-1.5">
      <div className="text-[9px] text-text-muted font-mono uppercase tracking-wider">{label}</div>
      <div className="text-xs font-mono text-text-primary">{value}</div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Agent Comparison Side-by-Side                                      */
/* ------------------------------------------------------------------ */
function AgentComparison({ a, b }: { a: AgentIdentity; b: AgentIdentity }) {
  const rows: { label: string; aVal: string; bVal: string }[] = [
    { label: "Role", aVal: a.capability, bVal: b.capability },
    { label: "Sessions", aVal: String(a.sessions_completed), bVal: String(b.sessions_completed) },
    { label: "Success Rate", aVal: `${Math.round(a.success_rate * 100)}%`, bVal: `${Math.round(b.success_rate * 100)}%` },
    { label: "Tool Calls", aVal: String(a.total_tool_calls), bVal: String(b.total_tool_calls) },
    {
      label: "Avg Session",
      aVal: a.avg_session_duration_minutes ? `${a.avg_session_duration_minutes.toFixed(0)} min` : "-",
      bVal: b.avg_session_duration_minutes ? `${b.avg_session_duration_minutes.toFixed(0)} min` : "-",
    },
    {
      label: "Top Tools",
      aVal: (a.tools_preferred ?? []).sort((x, y) => y.count - x.count).slice(0, 3).map(t => t.name).join(", ") || "-",
      bVal: (b.tools_preferred ?? []).sort((x, y) => y.count - x.count).slice(0, 3).map(t => t.name).join(", ") || "-",
    },
    {
      label: "Specializations",
      aVal: (a.typical_task_types ?? []).join(", ") || "-",
      bVal: (b.typical_task_types ?? []).join(", ") || "-",
    },
    {
      label: "Error Patterns",
      aVal: String(a.error_patterns?.length ?? 0),
      bVal: String(b.error_patterns?.length ?? 0),
    },
  ];

  return (
    <div className="mt-2 rounded border border-border-subtle bg-surface-raised overflow-hidden">
      <div className="grid grid-cols-3 text-[10px] font-mono border-b border-border-subtle/50">
        <div className="px-2 py-1 text-text-muted" />
        <div className="px-2 py-1 text-accent font-medium truncate">{a.name}</div>
        <div className="px-2 py-1 text-info font-medium truncate">{b.name}</div>
      </div>
      {rows.map((row) => (
        <div key={row.label} className="grid grid-cols-3 text-[10px] font-mono border-b border-border-subtle/20 last:border-b-0">
          <div className="px-2 py-1 text-text-muted">{row.label}</div>
          <div className="px-2 py-1 text-text-secondary">{row.aVal}</div>
          <div className="px-2 py-1 text-text-secondary">{row.bVal}</div>
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Individual Agent Card                                              */
/* ------------------------------------------------------------------ */
function AgentCard({
  agent,
  expanded,
  onToggle,
}: {
  agent: AgentIdentity;
  expanded: boolean;
  onToggle: () => void;
}) {
  const cap = CAPABILITY_COLORS[agent.capability] || CAPABILITY_COLORS.builder;
  const avatar = CAPABILITY_AVATARS[agent.capability] || "\u{1F916}";
  const successPct = Math.round((agent.success_rate ?? 1) * 100);

  const maxToolCount = useMemo(() => {
    if (!agent.tools_preferred?.length) return 1;
    return Math.max(...agent.tools_preferred.map(t => t.count), 1);
  }, [agent.tools_preferred]);

  return (
    <div className="rounded-lg border border-border-subtle bg-surface-raised overflow-hidden">
      {/* Overview Section (Header) - clickable to expand */}
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-3 px-3 py-2.5 border-b border-border-subtle/50 hover:bg-surface-hover/50 transition-colors text-left"
      >
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center text-base ${cap.bg} ${cap.border} border shrink-0`}>
          {avatar}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono font-medium text-text-primary">{agent.name}</span>
            <span className={`text-[10px] px-1.5 py-0.5 rounded border font-mono ${cap.bg} ${cap.text} ${cap.border}`}>
              {agent.capability}
            </span>
          </div>
          <span className="text-[10px] text-text-muted font-mono">
            {agent.sessions_completed} session{agent.sessions_completed !== 1 ? "s" : ""}
            {agent.total_tool_calls > 0 && ` | ${agent.total_tool_calls} tool calls`}
            {agent.avg_session_duration_minutes ? ` | ~${agent.avg_session_duration_minutes.toFixed(0)} min/session` : ""}
          </span>
        </div>
        {/* Success rate ring */}
        <div className="relative w-10 h-10 shrink-0" title={`Success rate: ${successPct}%`}>
          <svg viewBox="0 0 36 36" className="w-full h-full -rotate-90">
            <path
              d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
              fill="none"
              stroke="var(--color-border-subtle)"
              strokeWidth="3"
            />
            <path
              d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
              fill="none"
              stroke={successPct >= 80 ? "var(--color-success)" : successPct >= 50 ? "var(--color-warning)" : "var(--color-error)"}
              strokeWidth="3"
              strokeDasharray={`${successPct}, 100`}
            />
          </svg>
          <span className="absolute inset-0 flex items-center justify-center text-[9px] font-mono text-text-secondary">
            {successPct}%
          </span>
        </div>
        <span className="text-[10px] text-text-muted shrink-0">{expanded ? "\u25B2" : "\u25BC"}</span>
      </button>

      {/* Task Specialization pills */}
      {agent.typical_task_types && agent.typical_task_types.length > 0 && (
        <div className="px-3 py-1.5 flex flex-wrap gap-1 border-b border-border-subtle/30">
          {agent.typical_task_types.map((type) => (
            <span
              key={type}
              className={`px-2 py-0.5 rounded-full text-[10px] font-mono ${
                TASK_TYPE_COLORS[type] || "bg-surface-hover text-text-muted"
              }`}
            >
              {type}
            </span>
          ))}
        </div>
      )}

      {/* Expertise domain pills */}
      {agent.expertise_domains && agent.expertise_domains.length > 0 && (
        <div className="px-3 py-1.5 flex flex-wrap gap-1 border-b border-border-subtle/30">
          {agent.expertise_domains.map((domain) => (
            <span
              key={domain}
              className={`text-[10px] px-1.5 py-0.5 rounded border font-mono ${
                DOMAIN_COLORS[domain] || "bg-surface text-text-muted border-border-subtle"
              }`}
            >
              {domain}
              {agent.domains_touched?.[domain] != null && (
                <span className="ml-1 opacity-70">({agent.domains_touched[domain]})</span>
              )}
            </span>
          ))}
        </div>
      )}

      {/* Expanded detail sections */}
      {expanded && (
        <div className="px-3 py-2 space-y-3">
          {/* Performance Metrics grid */}
          <div className="space-y-1">
            <SectionHeading>Performance</SectionHeading>
            <div className="grid grid-cols-2 gap-2">
              <MetricCell label="Success Rate" value={`${successPct}%`} />
              <MetricCell
                label="Avg Session"
                value={agent.avg_session_duration_minutes ? `${agent.avg_session_duration_minutes.toFixed(0)} min` : "-"}
              />
              <MetricCell label="Total Tool Calls" value={String(agent.total_tool_calls)} />
              <MetricCell
                label="Tasks / Session"
                value={agent.sessions_completed > 0
                  ? (agent.recent_tasks.length / agent.sessions_completed).toFixed(1)
                  : "-"
                }
              />
            </div>
          </div>

          {/* Tools section: horizontal bar chart */}
          {agent.tools_preferred && agent.tools_preferred.length > 0 && (
            <div className="space-y-1">
              <SectionHeading>Top Tools</SectionHeading>
              <div className="space-y-1">
                {[...agent.tools_preferred]
                  .sort((a, b) => b.count - a.count)
                  .slice(0, 10)
                  .map((tool) => (
                    <div key={tool.name} className="flex items-center gap-2 text-[10px] font-mono">
                      <span className="w-20 text-text-muted truncate">{tool.name}</span>
                      <div className="flex-1 bg-surface-hover rounded h-3">
                        <div
                          className="bg-accent rounded h-3"
                          style={{ width: `${(tool.count / maxToolCount) * 100}%` }}
                        />
                      </div>
                      <span className="text-text-muted w-8 text-right">{tool.count}</span>
                    </div>
                  ))}
              </div>
            </div>
          )}

          {/* Error Patterns */}
          {agent.error_patterns && agent.error_patterns.length > 0 && (
            <div className="space-y-1">
              <SectionHeading>Error Patterns</SectionHeading>
              <div className="space-y-1">
                {[...agent.error_patterns]
                  .sort((a, b) => b.count - a.count)
                  .slice(0, 5)
                  .map((err) => (
                    <div key={err.pattern} className="flex justify-between text-[10px] font-mono gap-2">
                      <span className="text-error truncate">{err.pattern}</span>
                      <span className="text-text-muted shrink-0">{err.count}x</span>
                    </div>
                  ))}
              </div>
            </div>
          )}

          {/* Collaboration Graph */}
          {agent.collaboration_history && agent.collaboration_history.length > 0 && (
            <div className="space-y-1">
              <SectionHeading>Collaborations</SectionHeading>
              <div className="space-y-1">
                {agent.collaboration_history.map((collab) => (
                  <div key={collab.partner} className="flex items-center gap-2 text-[10px] font-mono">
                    <span className="text-text-primary">{collab.partner}</span>
                    <span className="text-text-muted">{collab.joint_sessions} session{collab.joint_sessions !== 1 ? "s" : ""}</span>
                    <span className={collab.success_rate > 0.7 ? "text-success" : "text-warning"}>
                      {(collab.success_rate * 100).toFixed(0)}%
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Recent tasks mini-timeline */}
          {agent.recent_tasks && agent.recent_tasks.length > 0 && (
            <div className="space-y-1">
              <SectionHeading>Recent Tasks</SectionHeading>
              {agent.recent_tasks.slice(0, 5).map((task) => (
                <div key={task.task_id} className="flex items-center gap-2 text-[10px]">
                  <span className="w-1 h-1 rounded-full bg-success shrink-0" />
                  <span className="font-mono text-text-muted shrink-0">{task.task_id}</span>
                  <span className="text-text-secondary truncate">{task.summary}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main panel                                                         */
/* ------------------------------------------------------------------ */
interface ProjectExpertiseSummary {
  total: number;
  domains: string[];
  byDomain: Record<string, number>;
}

export function AgentIdentityPanel({
  projectDir,
  status,
}: {
  projectDir: string;
  status?: string;
}) {
  const [agents, setAgents] = useState<AgentIdentity[]>([]);
  const [loading, setLoading] = useState(true);
  const [compareAgent, setCompareAgent] = useState<string | null>(null);
  const [expandedAgent, setExpandedAgent] = useState<string | null>(null);
  const [projExpertise, setProjExpertise] = useState<ProjectExpertiseSummary | null>(null);

  const fetchAgents = useCallback(async () => {
    if (!projectDir) return;
    try {
      const res = await fetch(`/api/agents?path=${encodeURIComponent(projectDir)}`);
      if (res.ok) {
        const data = await res.json();
        setAgents(data.agents || []);
      } else {
        setAgents([]);
      }
    } catch {
      setAgents([]);
    } finally {
      setLoading(false);
    }
  }, [projectDir]);

  // Fetch project expertise summary
  useEffect(() => {
    if (!projectDir) return;
    fetch(`/api/projects/expertise?path=${encodeURIComponent(projectDir)}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (!d) return;
        const entries = d.entries || [];
        const byDomain: Record<string, number> = {};
        for (const e of entries) {
          const dom = (e as { domain?: string }).domain || "general";
          byDomain[dom] = (byDomain[dom] || 0) + 1;
        }
        setProjExpertise({
          total: entries.length,
          domains: d.domains || [],
          byDomain,
        });
      })
      .catch(() => {});
  }, [projectDir]);

  // Initial fetch + poll while running
  useEffect(() => {
    fetchAgents();
    if (status === "running") {
      const interval = setInterval(fetchAgents, 10000);
      return () => clearInterval(interval);
    }
  }, [fetchAgents, status]);

  // Compute per-domain success correlation (must be above early returns)
  const domainCorrelation = useMemo(() => {
    if (!projExpertise || agents.length === 0) return null;
    const correlation: { domain: string; count: number; avgSuccess: number; agentCount: number }[] = [];
    for (const domain of projExpertise.domains) {
      const matchingAgents = agents.filter(
        (a) => a.expertise_domains?.includes(domain) || a.domains_touched?.[domain] != null
      );
      if (matchingAgents.length > 0) {
        const avgSuccess =
          matchingAgents.reduce((sum, a) => sum + (a.success_rate ?? 0), 0) / matchingAgents.length;
        correlation.push({
          domain,
          count: projExpertise.byDomain[domain] || 0,
          avgSuccess,
          agentCount: matchingAgents.length,
        });
      } else {
        correlation.push({
          domain,
          count: projExpertise.byDomain[domain] || 0,
          avgSuccess: -1,
          agentCount: 0,
        });
      }
    }
    return correlation.sort((a, b) => b.count - a.count);
  }, [projExpertise, agents]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-32 text-xs text-text-muted">
        Loading agents...
      </div>
    );
  }

  if (agents.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-32 gap-2">
        <span className="text-xs text-text-muted">
          No agent identities registered yet.
        </span>
        <span className="text-[10px] text-text-muted">
          {status === "running"
            ? "Agent identity will appear once the session starts..."
            : "Start an agent run to see identities here."}
        </span>
      </div>
    );
  }

  return (
    <div className="overflow-y-auto h-full p-3">
      {/* Project Expertise Summary */}
      {projExpertise && projExpertise.total > 0 && (
        <div className="mb-3 rounded-lg border border-border-subtle bg-surface-raised p-3 space-y-2">
          <div className="flex items-center justify-between">
            <SectionHeading>Project Expertise Loaded</SectionHeading>
            <span className="text-[10px] font-mono text-text-muted">
              {projExpertise.total} entr{projExpertise.total === 1 ? "y" : "ies"}
            </span>
          </div>
          {domainCorrelation && domainCorrelation.length > 0 && (
            <div className="space-y-1.5">
              {domainCorrelation.map((dc) => (
                <div key={dc.domain} className="flex items-center gap-2">
                  <span
                    className={`text-[10px] px-1.5 py-0.5 rounded border font-mono shrink-0 ${
                      DOMAIN_COLORS[dc.domain] || "bg-surface text-text-muted border-border-subtle"
                    }`}
                  >
                    {dc.domain}
                  </span>
                  <span className="text-[10px] font-mono text-text-muted">
                    {dc.count} entr{dc.count === 1 ? "y" : "ies"}
                  </span>
                  <div className="flex-1" />
                  {dc.agentCount > 0 ? (
                    <span
                      className={`text-[10px] font-mono ${
                        dc.avgSuccess >= 0.8
                          ? "text-success"
                          : dc.avgSuccess >= 0.5
                          ? "text-warning"
                          : "text-error"
                      }`}
                      title={`${dc.agentCount} agent(s) working in this domain`}
                    >
                      {Math.round(dc.avgSuccess * 100)}% success ({dc.agentCount} agent{dc.agentCount !== 1 ? "s" : ""})
                    </span>
                  ) : (
                    <span className="text-[10px] font-mono text-text-muted">no agents</span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Compare Agents toggle */}
      {agents.length >= 2 && (
        <div className="mb-3 flex items-center gap-2">
          <button
            onClick={() => setCompareAgent(compareAgent ? null : agents[0].name)}
            className="text-[10px] font-mono px-2 py-1 rounded border border-border-subtle hover:bg-surface-hover transition-colors"
          >
            {compareAgent ? "Hide Comparison" : "Compare Agents"}
          </button>
          {compareAgent && (
            <select
              value={compareAgent}
              onChange={(e) => setCompareAgent(e.target.value)}
              className="text-[10px] font-mono px-1 py-0.5 rounded border border-border-subtle bg-surface"
            >
              {agents.map((a) => (
                <option key={a.name} value={a.name}>{a.name}</option>
              ))}
            </select>
          )}
        </div>
      )}

      {/* Comparison table */}
      {compareAgent && agents.length >= 2 && (() => {
        const primary = agents.find(a => a.name === compareAgent);
        const secondary = agents.find(a => a.name !== compareAgent);
        if (primary && secondary) {
          return <AgentComparison a={primary} b={secondary} />;
        }
        return null;
      })()}

      <div className="grid grid-cols-1 gap-3 mt-2">
        {agents.map((agent) => (
          <AgentCard
            key={agent.name}
            agent={agent}
            expanded={expandedAgent === agent.name}
            onToggle={() => setExpandedAgent(expandedAgent === agent.name ? null : agent.name)}
          />
        ))}
      </div>
    </div>
  );
}
