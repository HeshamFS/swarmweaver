"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import type { AgentEvent, SessionStats, AgentStatus } from "../hooks/useSwarmWeaver";
import { InsightsPanel } from "./InsightsPanel";
import { AgentIdentityPanel } from "./AgentIdentityPanel";
import { CheckpointPanel } from "./CheckpointPanel";
import { FilesView } from "./FilesView";
import { ErrorsView } from "./ErrorsView";
import { AuditView } from "./AuditView";
import type { EventStoreResponse, ToolStatEntry } from "./AuditView";
import { ProfileView } from "./ProfileView";
import type { CodebaseProfile } from "./ProfileView";

interface BudgetData {
  total_input_tokens: number;
  total_output_tokens: number;
  estimated_cost_usd: number;
  budget_limit_usd: number;
  max_hours: number;
  consecutive_errors: number;
  max_consecutive_errors: number;
  start_time: string;
}

interface ServerSessionStats {
  tool_call_count: number;
  tool_counts: Record<string, number>;
  error_count: number;
  file_touches: Record<string, number>;
}

interface ObservabilityPanelProps {
  events: AgentEvent[];
  sessionStats: SessionStats | null;
  projectDir?: string;
  status?: AgentStatus;
}

type TabId = "timeline" | "files" | "costs" | "errors" | "audit" | "profile" | "insights" | "agents" | "checkpoints";

const TABS: { id: TabId; label: string; icon: string }[] = [
  { id: "timeline", label: "Timeline", icon: "\u23F1" },
  { id: "files", label: "Files", icon: "\u{1F4C4}" },
  { id: "costs", label: "Costs", icon: "\u{1F4B0}" },
  { id: "errors", label: "Errors", icon: "\u26A0" },
  { id: "audit", label: "Audit", icon: "\u{1F50E}" },
  { id: "insights", label: "Insights", icon: "\u{1F4CA}" },
  { id: "agents", label: "Agents", icon: "\u{1F916}" },
  { id: "checkpoints", label: "Checkpts", icon: "\u23F1" },
  { id: "profile", label: "Profile", icon: "\u{1F4CB}" },
];

const EVENT_ICONS: Record<string, string> = {
  tool_call: "\u{1F527}",
  tool_result: "\u2705",
  error: "\u274C",
  file_touch: "\u{1F4DD}",
  phase_change: "\u{1F3AF}",
  verification: "\u{1F50D}",
  marathon: "\u{1F3C3}",
  blocked: "\u{1F6AB}",
  session_stat: "\u{1F4CA}",
};

const EVENT_COLORS: Record<string, string> = {
  tool_call: "text-accent",
  tool_result: "text-success",
  error: "text-error",
  file_touch: "text-text-secondary",
  phase_change: "text-warning",
  verification: "text-accent",
  marathon: "text-warning",
  blocked: "text-error",
};

const STEERING_PATTERN = /\[STEERING\]|\[DIRECTIVE FROM ORCHESTRATOR\]|Message from operator/i;

function isSteeringBlock(e: AgentEvent): boolean {
  if (e.type !== "tool_blocked" && e.type !== "blocked") return false;
  const msg = String((e as AgentEvent & { reason?: string }).reason ?? (e.data as { reason?: string })?.reason ?? "");
  return STEERING_PATTERN.test(msg);
}

// Cost estimation (per million tokens, approximate)
const MODEL_COSTS: Record<string, { input: number; output: number }> = {
  "claude-sonnet-4-6": { input: 3, output: 15 },
  "claude-sonnet-4-5-20250929": { input: 3, output: 15 },
  "claude-opus-4-6": { input: 15, output: 75 },
  "claude-haiku-4-5-20251001": { input: 0.8, output: 4 },
};

function formatTime(timestamp: string): string {
  try {
    const d = new Date(timestamp);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return "";
  }
}

function TimelineView({ events }: { events: AgentEvent[] }) {
  const relevant = events.filter(
    (e) => e.type !== "raw_output" && e.type !== "output"
  );
  const display = relevant.slice(-100).reverse();

  if (display.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <span className="text-sm text-text-muted">
          No events yet. Start an agent run to see the timeline.
        </span>
      </div>
    );
  }

  return (
    <div className="space-y-1 p-2">
      {display.map((event, i) => (
        <div
          key={i}
          className="flex items-start gap-2 px-2 py-1.5 rounded hover:bg-surface-raised/50 transition-colors"
        >
          <span className="text-sm">{EVENT_ICONS[event.type] || "\u25CB"}</span>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span
                className={`text-xs font-mono font-medium ${EVENT_COLORS[event.type] || "text-text-secondary"}`}
              >
                {event.type}
              </span>
              {event.data?.tool ? (
                <span className="text-[10px] text-text-muted bg-surface px-1.5 py-0.5 rounded border border-border-subtle">
                  {String(event.data.tool)}
                </span>
              ) : null}
            </div>
            {event.data?.message ? (
              <p className="text-xs text-text-muted mt-0.5 truncate">
                {String(event.data.message)}
              </p>
            ) : null}
            {event.data?.file ? (
              <p className="text-xs text-text-muted mt-0.5 font-mono truncate">
                {String(event.data.file)}
              </p>
            ) : null}
            {event.data?.phase ? (
              <p className="text-xs text-warning mt-0.5 font-medium">
                {String(event.data.phase)}
              </p>
            ) : null}
            {event.data?.reason ? (
              <p className="text-xs text-error mt-0.5 truncate">
                {String(event.data.reason)}
              </p>
            ) : null}
          </div>
          <span className="text-[10px] text-text-muted whitespace-nowrap">
            {formatTime(event.timestamp)}
          </span>
        </div>
      ))}
    </div>
  );
}


function CostsView({
  stats,
  budgetData,
}: {
  stats: SessionStats | null;
  budgetData: BudgetData | null;
}) {
  const toolCalls = stats?.tool_call_count || 0;

  // Use real budget data if available, fallback to estimate
  const inputTokens = budgetData?.total_input_tokens || toolCalls * 500;
  const outputTokens = budgetData?.total_output_tokens || toolCalls * 200;
  const cost = budgetData?.estimated_cost_usd ||
    (inputTokens * 3 + outputTokens * 15) / 1_000_000;
  const budgetLimit = budgetData?.budget_limit_usd || 0;
  const budgetPct = budgetLimit > 0 ? Math.min((cost / budgetLimit) * 100, 100) : 0;

  return (
    <div className="p-4 space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-lg border border-border-subtle bg-surface-raised p-3">
          <span className="text-xs text-text-muted block">Tool Calls</span>
          <span className="text-2xl font-bold text-text-primary font-mono">
            {toolCalls}
          </span>
        </div>
        <div className="rounded-lg border border-border-subtle bg-surface-raised p-3">
          <span className="text-xs text-text-muted block">
            {budgetData ? "Cost" : "Est. Cost"}
          </span>
          <span className="text-2xl font-bold text-accent font-mono">
            ${cost.toFixed(2)}
          </span>
          {budgetLimit > 0 && (
            <span className="text-xs text-text-muted block mt-0.5">
              / ${budgetLimit.toFixed(2)} limit
            </span>
          )}
        </div>
      </div>

      {/* Budget progress bar */}
      {budgetLimit > 0 && (
        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs text-text-muted">Budget usage</span>
            <span className={`text-xs font-mono ${budgetPct > 80 ? "text-error" : "text-text-secondary"}`}>
              {budgetPct.toFixed(1)}%
            </span>
          </div>
          <div className="h-2 rounded-full bg-border-subtle overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                budgetPct > 80 ? "bg-error" : budgetPct > 50 ? "bg-warning" : "bg-accent"
              }`}
              style={{ width: `${budgetPct}%` }}
            />
          </div>
        </div>
      )}

      {/* Token breakdown */}
      {budgetData && (
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-lg border border-border-subtle bg-surface-raised p-3">
            <span className="text-xs text-text-muted block">Input Tokens</span>
            <span className="text-lg font-bold text-text-primary font-mono">
              {(inputTokens / 1000).toFixed(1)}k
            </span>
          </div>
          <div className="rounded-lg border border-border-subtle bg-surface-raised p-3">
            <span className="text-xs text-text-muted block">Output Tokens</span>
            <span className="text-lg font-bold text-text-primary font-mono">
              {(outputTokens / 1000).toFixed(1)}k
            </span>
          </div>
        </div>
      )}

      {/* Error streak */}
      {budgetData && budgetData.consecutive_errors > 0 && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-md border border-error/30 bg-error/5">
          <span className="text-xs text-error font-medium">
            Error streak: {budgetData.consecutive_errors}/{budgetData.max_consecutive_errors}
          </span>
        </div>
      )}

      {stats?.tool_counts && Object.keys(stats.tool_counts).length > 0 && (
        <div>
          <span className="text-xs text-text-muted font-medium uppercase tracking-wider block mb-2">
            Tool Breakdown
          </span>
          <div className="space-y-1">
            {Object.entries(stats.tool_counts)
              .sort(([, a], [, b]) => b - a)
              .map(([tool, count]) => (
                <div
                  key={tool}
                  className="flex items-center justify-between px-2 py-1"
                >
                  <span className="text-xs text-text-primary font-mono">
                    {tool}
                  </span>
                  <span className="text-xs text-text-muted font-mono">
                    {count}
                  </span>
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}



export function ObservabilityPanel({
  events,
  sessionStats,
  projectDir,
  status,
}: ObservabilityPanelProps) {
  const [activeTab, setActiveTab] = useState<TabId>("timeline");
  const [budgetData, setBudgetData] = useState<BudgetData | null>(null);
  const [serverStats, setServerStats] = useState<ServerSessionStats | null>(null);
  const [codebaseProfile, setCodebaseProfile] = useState<CodebaseProfile | null>(null);
  const [profileLoading, setProfileLoading] = useState(false);
  const [eventStoreData, setEventStoreData] = useState<EventStoreResponse | null>(null);
  const [toolStats, setToolStats] = useState<ToolStatEntry[]>([]);
  const [persistedErrors, setPersistedErrors] = useState<Array<{ timestamp: string; agent: string; event_type: string; tool_name: string; tool_input: string; error: string }>>([]);
  const auditFetched = useRef(false);
  const profileFetched = useRef(false);

  const fetchBudget = useCallback(async () => {
    if (!projectDir) return;
    try {
      const res = await fetch(`/api/budget?path=${encodeURIComponent(projectDir)}`);
      const data = await res.json();
      if (data.total_input_tokens !== undefined) {
        setBudgetData(data);
      }
    } catch {
      // Ignore
    }
  }, [projectDir]);


  // Fetch event store data (richer audit data from SQLite)
  const fetchEventStore = useCallback(async () => {
    if (!projectDir) return;
    try {
      const res = await fetch(`/api/events?path=${encodeURIComponent(projectDir)}&limit=200`);
      const data = await res.json();
      if (data.events && Array.isArray(data.events)) {
        setEventStoreData(data);
      }
    } catch {
      // Ignore — endpoint may not be available yet
    }
  }, [projectDir]);

  // Fetch tool statistics from event store
  const fetchToolStats = useCallback(async () => {
    if (!projectDir) return;
    try {
      const res = await fetch(`/api/events/tool-stats?path=${encodeURIComponent(projectDir)}`);
      const data = await res.json();
      if (Array.isArray(data)) {
        setToolStats(data);
      } else if (data.stats && Array.isArray(data.stats)) {
        setToolStats(data.stats);
      }
    } catch {
      // Ignore — endpoint may not be available yet
    }
  }, [projectDir]);

  // Fetch server-side session stats (merges with WebSocket sessionStats)
  const fetchServerStats = useCallback(async () => {
    if (!projectDir) return;
    try {
      const res = await fetch(`/api/session-stats?path=${encodeURIComponent(projectDir)}`);
      const data = await res.json();
      if (data.tool_call_count !== undefined) {
        setServerStats(data);
      }
    } catch {
      // Ignore
    }
  }, [projectDir]);

  // Fetch persisted errors (centralized error log)
  const fetchPersistedErrors = useCallback(async () => {
    if (!projectDir) return;
    try {
      const res = await fetch(`/api/errors?path=${encodeURIComponent(projectDir)}&limit=200`);
      const data = await res.json();
      if (data.errors && Array.isArray(data.errors)) {
        setPersistedErrors(data.errors);
      }
    } catch {
      // Ignore
    }
  }, [projectDir]);

  // Fetch codebase profile
  const fetchCodebaseProfile = useCallback(async () => {
    if (!projectDir) return;
    setProfileLoading(true);
    try {
      const res = await fetch(`/api/codebase-profile?path=${encodeURIComponent(projectDir)}`);
      const data = await res.json();
      if (data && typeof data === "object" && Object.keys(data).length > 0) {
        setCodebaseProfile(data);
      }
    } catch {
      // Ignore
    } finally {
      setProfileLoading(false);
    }
  }, [projectDir]);

  // Poll budget data every 5s while running
  useEffect(() => {
    if (status !== "running" || !projectDir) return;
    fetchBudget();
    const interval = setInterval(fetchBudget, 5000);
    return () => clearInterval(interval);
  }, [status, projectDir, fetchBudget]);

  // Fetch session stats on mount and poll while running
  useEffect(() => {
    if (!projectDir) return;
    fetchServerStats();
    if (status === "running") {
      const interval = setInterval(fetchServerStats, 8000);
      return () => clearInterval(interval);
    }
  }, [status, projectDir, fetchServerStats]);

  // Fetch event store when the audit tab is selected (lazy load), then poll while running
  useEffect(() => {
    if (activeTab === "audit" && projectDir) {
      if (!auditFetched.current) {
        fetchEventStore();
        fetchToolStats();
        auditFetched.current = true;
      }
      if (status === "running") {
        const interval = setInterval(() => {
          fetchEventStore();
          fetchToolStats();
        }, 6000);
        return () => clearInterval(interval);
      }
    }
  }, [activeTab, status, projectDir, fetchEventStore, fetchToolStats]);

  // Fetch persisted errors when errors tab is selected, poll while running
  useEffect(() => {
    if (activeTab === "errors" && projectDir) {
      fetchPersistedErrors();
      if (status === "running") {
        const interval = setInterval(fetchPersistedErrors, 6000);
        return () => clearInterval(interval);
      }
    }
  }, [activeTab, projectDir, status, fetchPersistedErrors]);

  // Fetch codebase profile when profile tab is selected (lazy load)
  useEffect(() => {
    if (activeTab === "profile" && projectDir && !profileFetched.current) {
      fetchCodebaseProfile();
      profileFetched.current = true;
    }
  }, [activeTab, projectDir, fetchCodebaseProfile]);

  // Reset fetch guards when projectDir changes
  useEffect(() => {
    auditFetched.current = false;
    profileFetched.current = false;
  }, [projectDir]);

  // Merge WebSocket sessionStats with server-side stats for the Costs view
  const mergedStats: SessionStats | null = (() => {
    if (!sessionStats && !serverStats) return null;
    const ws = sessionStats || { tool_call_count: 0, tool_counts: {}, error_count: 0, file_touches: {}, current_phase: "", session_number: 0, start_time: "" };
    const sv = serverStats || { tool_call_count: 0, tool_counts: {}, error_count: 0, file_touches: {} };
    // Prefer whichever has more tool calls (server stats are cumulative across sessions)
    const usePrimary = ws.tool_call_count >= sv.tool_call_count ? ws : sv;
    const useSecondary = usePrimary === ws ? sv : ws;
    // Merge tool_counts: take max of each tool
    const mergedToolCounts: Record<string, number> = { ...usePrimary.tool_counts };
    for (const [tool, count] of Object.entries(useSecondary.tool_counts)) {
      mergedToolCounts[tool] = Math.max(mergedToolCounts[tool] || 0, count);
    }
    // Merge file_touches: take max
    const mergedFileTouches: Record<string, number> = { ...((usePrimary as SessionStats).file_touches || {}) };
    for (const [file, count] of Object.entries(useSecondary.file_touches || {})) {
      mergedFileTouches[file] = Math.max(mergedFileTouches[file] || 0, count);
    }
    return {
      ...ws,
      tool_call_count: Math.max(ws.tool_call_count, sv.tool_call_count),
      tool_counts: mergedToolCounts,
      error_count: Math.max(ws.error_count, sv.error_count),
      file_touches: mergedFileTouches,
    };
  })();

  const STEERING_PATTERN = /\[STEERING\]|\[DIRECTIVE FROM ORCHESTRATOR\]|Message from operator/i;
  const isSteeringBlock = (e: AgentEvent) =>
    e.type === "tool_blocked" && STEERING_PATTERN.test(String((e as AgentEvent & { data?: { reason?: string; error?: string } }).data?.reason ?? (e as AgentEvent & { data?: { reason?: string; error?: string } }).data?.error ?? ""));
  const liveErrorCount = events.filter(
    (e) => {
      if (isSteeringBlock(e)) return false;
      return e.type === "error" || e.type === "blocked" || e.type === "tool_error" || e.type === "tool_blocked";
    }
  ).length;
  const persistedErrorCount = persistedErrors.filter((p) => !STEERING_PATTERN.test(p.error ?? "")).length;
  const errorCount = Math.max(liveErrorCount, persistedErrorCount);

  const auditErrorCount = eventStoreData?.stats?.errors ?? 0;

  return (
    <div className="flex flex-col h-full rounded-lg border border-border-subtle bg-surface overflow-hidden">
      {/* Header with tabs */}
      <div className="px-3 py-2 border-b border-border-subtle bg-surface-raised">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-text-muted font-mono">
            Observability
          </span>
          <span className="text-xs text-text-secondary font-mono">
            {mergedStats?.tool_call_count || sessionStats?.tool_call_count || 0} calls
            {mergedStats && mergedStats.error_count > 0 && (
              <span className="text-error ml-1">
                ({mergedStats.error_count} err)
              </span>
            )}
          </span>
        </div>
        <div className="flex gap-0.5 flex-wrap" role="tablist" aria-label="Observability panel tabs">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              role="tab"
              aria-selected={activeTab === tab.id}
              aria-label={`${tab.label} tab`}
              className={`flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] transition-colors ${
                activeTab === tab.id
                  ? "bg-accent/15 text-accent font-medium"
                  : "text-text-muted hover:text-text-secondary"
              }`}
            >
              <span aria-hidden="true">{tab.icon}</span>
              <span>{tab.label}</span>
              {tab.id === "errors" && errorCount > 0 && (
                <span className="text-[10px] bg-error/20 text-error px-1 rounded-full">
                  {errorCount}
                </span>
              )}
              {tab.id === "audit" && auditErrorCount > 0 && (
                <span className="text-[10px] bg-error/20 text-error px-1 rounded-full">
                  {auditErrorCount}
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {activeTab === "timeline" && <TimelineView events={events} />}
        {activeTab === "files" && <FilesView stats={mergedStats || sessionStats} />}
        {activeTab === "costs" && <CostsView stats={mergedStats || sessionStats} budgetData={budgetData} />}
        {activeTab === "errors" && <ErrorsView events={events} persistedErrors={persistedErrors} />}
        {activeTab === "audit" && <AuditView loading={!eventStoreData} events={events} eventStoreData={eventStoreData} toolStats={toolStats} />}
        {activeTab === "insights" && projectDir && <InsightsPanel projectDir={projectDir} />}
        {activeTab === "agents" && projectDir && <AgentIdentityPanel projectDir={projectDir} status={status} />}
        {activeTab === "checkpoints" && projectDir && <CheckpointPanel projectDir={projectDir} status={status} />}
        {activeTab === "profile" && <ProfileView profile={codebaseProfile} loading={profileLoading} />}
      </div>
    </div>
  );
}
