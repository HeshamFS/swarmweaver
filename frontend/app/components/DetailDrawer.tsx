"use client";

import { useState, useEffect, useRef, useMemo, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type {
  TaskData,
  Task,
  AgentEvent,
  SessionStats,
  WorktreeInfo,
  ApprovalRequestData,
} from "../hooks/useSwarmWeaver";
import { DrawerSection } from "./drawer/DrawerSection";
import { TaskGraph } from "./TaskGraph";
import { MemoryPanel } from "./MemoryPanel";

export interface DetailDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  onToggle: () => void;
  tasks: TaskData | null;
  events: AgentEvent[];
  sessionStats: SessionStats | null;
  output: string[];
  worktreeInfo?: WorktreeInfo | null;
  projectPath: string;
  isSwarmMode: boolean;
  approvalRequest?: ApprovalRequestData | null;
  activeSection?: string | null;
  /** When set, Observe tab can scope costs/timeline to this worker (Phase 2: API support) */
  selectedWorkerId?: number | null;
}

/* ---- Status helpers ---- */

const TASK_STATUS_ICON: Record<string, string> = {
  done: "\u2713",
  completed: "\u2713",
  verified: "\u2714",
  in_progress: "\u25B6",
  pending: "\u25CB",
  failed: "\u2717",
  failed_verification: "\u2717",
  blocked: "\u29B8",
};

const TASK_STATUS_COLOR: Record<string, string> = {
  done: "var(--color-success)",
  completed: "var(--color-success)",
  verified: "var(--color-success)",
  in_progress: "var(--color-accent)",
  pending: "var(--color-text-muted)",
  failed: "var(--color-error)",
  failed_verification: "var(--color-error)",
  blocked: "var(--color-warning)",
};

const SEVERITY_COLOR: Record<string, string> = {
  critical: "var(--color-error)",
  error: "var(--color-error)",
  warning: "var(--color-warning)",
  info: "var(--color-info)",
};

/* ---- Utility ---- */

function formatTime(ts: string): string {
  try {
    const d = new Date(ts);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return ts;
  }
}

function apiUrl(endpoint: string, projectPath: string): string {
  return `/api/${endpoint}?path=${encodeURIComponent(projectPath)}`;
}

type ApiData = Record<string, unknown>;

// Type-safe accessors for API data (avoids TS errors with Record<string, unknown>)
function asNum(v: unknown, fallback = 0): number {
  return typeof v === "number" ? v : Number(v) || fallback;
}
function asStr(v: unknown, fallback = ""): string {
  return typeof v === "string" ? v : fallback;
}
function asArr(v: unknown): ApiData[] {
  return Array.isArray(v) ? v as ApiData[] : [];
}

function useApiPoll(endpoint: string, projectPath: string, isOpen: boolean, intervalMs = 10000) {
  const [data, setData] = useState<ApiData | null>(null);
  const [loading, setLoading] = useState(false);

  const doFetch = useCallback(() => {
    if (!projectPath) return;
    setLoading(true);
    fetch(apiUrl(endpoint, projectPath))
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (d) setData(d); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [endpoint, projectPath]);

  useEffect(() => {
    if (!isOpen || !projectPath) return;
    doFetch();
    const id = setInterval(doFetch, intervalMs);
    return () => clearInterval(id);
  }, [isOpen, projectPath, doFetch, intervalMs]);

  return { data, loading, refetch: doFetch };
}

/* ---- Main Component ---- */

export function DetailDrawer({
  isOpen,
  onClose,
  onToggle,
  tasks,
  events,
  sessionStats,
  output,
  worktreeInfo,
  projectPath,
  isSwarmMode,
  approvalRequest,
  activeSection,
  selectedWorkerId,
}: DetailDrawerProps) {
  const drawerRef = useRef<HTMLDivElement>(null);

  // REST API polling for enriched data
  const { data: budgetData } = useApiPoll("budget", projectPath, isOpen, 8000);
  const { data: costsData } = useApiPoll("costs", projectPath, isOpen, 15000);
  const { data: costsByModel } = useApiPoll("costs/by-model", projectPath, isOpen, 15000);
  // Checkpoints = git commit history (session-history endpoint)
  const { data: checkpointsData } = useApiPoll("session-history", projectPath, isOpen, 15000);
  const { data: insightsData } = useApiPoll("insights", projectPath, isOpen, 12000);
  const { data: timelineData } = useApiPoll("timeline", projectPath, isOpen, 8000);
  const { data: processesData } = useApiPoll("processes", projectPath, isOpen, 10000);
  const { data: sessionStatsApi } = useApiPoll("session-stats", projectPath, isOpen, 10000);
  const { data: agentsData } = useApiPoll("agents", projectPath, isOpen, 15000);
  const { data: reflectionsData } = useApiPoll("reflections", projectPath, isOpen, 20000);
  const { data: auditTimelineData } = useApiPoll("audit-timeline", projectPath, isOpen, 12000);
  const { data: sessionChainData } = useApiPoll("session/chain", projectPath, isOpen, 12000);
  const { data: swarmMailData } = useApiPoll("swarm/mail", projectPath, isOpen && isSwarmMode, 15000);

  // Worktree diff (only when worktree exists)
  const [worktreeDiffData, setWorktreeDiffData] = useState<{ diff: string; status?: { files_changed?: number } } | null>(null);
  useEffect(() => {
    if (!isOpen || !projectPath || !worktreeInfo?.run_id) return;
    const params = new URLSearchParams({ path: projectPath, run_id: worktreeInfo.run_id });
    fetch(`/api/worktree/diff?${params}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (d) setWorktreeDiffData(d); })
      .catch(() => {});
    const id = setInterval(() => {
      fetch(`/api/worktree/diff?${params}`)
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => { if (d) setWorktreeDiffData(d); })
        .catch(() => {});
    }, 12000);
    return () => clearInterval(id);
  }, [isOpen, projectPath, worktreeInfo?.run_id]);

  // Graph modal (full-size task dependency graph)
  const [graphModalOpen, setGraphModalOpen] = useState(false);

  // Tabbed drawer: tasks | observe | memory | docs | swarm
  const sectionToTab: Record<string, "tasks" | "observe" | "memory" | "docs" | "swarm"> = {
    tasks: "tasks",
    files: "observe",
    costs: "observe",
    agents: "observe",
    timeline: "observe",
    errors: "observe",
    audit: "observe",
    profile: "observe",
    processes: "observe",
    memory: "memory",
    insights: "memory",
    reflections: "memory",
    adrs: "docs",
    checkpoints: "docs",
    mail: "swarm",
    merges: "swarm",
  };
  const [activeDrawerTab, setActiveDrawerTab] = useState<"tasks" | "observe" | "memory" | "docs" | "swarm">("tasks");
  useEffect(() => {
    if (activeSection && sectionToTab[activeSection]) {
      setActiveDrawerTab(sectionToTab[activeSection]);
    }
  }, [activeSection]);

  // Lazy-loaded panels
  const [adrData, setAdrData] = useState<{ adrs: { id: string; title: string; status: string; date: string }[] } | null>(null);
  // Git reset state
  const [resettingTo, setResettingTo] = useState<string | null>(null);

  const fetchADRs = useCallback(() => {
    if (adrData || !projectPath) return;
    fetch(apiUrl("adrs", projectPath))
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (d) setAdrData(d); })
      .catch(() => {});
  }, [adrData, projectPath]);

  // Git reset to a commit checkpoint
  const handleGitReset = useCallback(async (sha: string) => {
    if (!projectPath) return;
    if (!window.confirm(`Reset project to commit ${sha.slice(0, 8)}?\n\nThis will hard-reset all uncommitted changes.`)) return;
    setResettingTo(sha);
    try {
      const res = await fetch("/api/git/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: projectPath, sha }),
      });
      const data = await res.json();
      if (data.status !== "ok") {
        alert(`Reset failed: ${data.error || "Unknown error"}`);
      }
    } catch {
      alert("Reset request failed");
    } finally {
      setResettingTo(null);
    }
  }, [projectPath]);

  // Derived data from tasks prop
  const taskList = useMemo(() => tasks?.tasks ?? [], [tasks]);
  const doneTasks = useMemo(() => taskList.filter((t) => t.status === "done" || t.status === "completed" || t.status === "verified"), [taskList]);
  const failedTasks = useMemo(() => taskList.filter((t) => t.status === "failed" || t.status === "failed_verification"), [taskList]);

  // Merge file touches from WS sessionStats + REST API + audit-timeline + worktree diff
  const fileTouches = useMemo(() => {
    const touches: Record<string, number> = { ...(sessionStats?.file_touches ?? sessionStatsApi?.file_touches ?? {}) };
    // From audit-timeline: extract file paths from tool_input, input, or tool_input_preview
    const entries = (auditTimelineData?.entries ?? []) as ApiData[];
    for (const entry of entries) {
      let fp = "";
      const ti = entry.tool_input ?? entry.input;
      if (ti && typeof ti === "object" && !Array.isArray(ti)) {
        const tio = ti as ApiData;
        fp = asStr(tio.file_path ?? tio.path ?? tio.filename);
      } else if (typeof entry.tool_input_preview === "string") {
        const m = entry.tool_input_preview.match(/(?:file_path|path|filename)["']?\s*[:=]\s*["']?([^"'\s,}]+)/);
        if (m) fp = m[1].trim();
      }
      if (fp && asStr(entry.tool_name ?? entry.tool) in { Write: 1, Edit: 1, Read: 1, NotebookEdit: 1 }) {
        touches[fp] = (touches[fp] ?? 0) + 1;
      }
    }
    // From worktree diff: parse "diff --git a/path b/path"
    const diff = worktreeDiffData?.diff ?? "";
    if (diff) {
      const seen = new Set<string>();
      for (const line of diff.split("\n")) {
        const m = line.match(/^diff --git a\/(.+?) b\/\1$/);
        if (m) {
          const p = m[1];
          if (!seen.has(p)) {
            seen.add(p);
            touches[p] = (touches[p] ?? 0) + 1;
          }
        }
      }
    }
    return Object.entries(touches).sort(([, a], [, b]) => b - a);
  }, [sessionStats, sessionStatsApi, auditTimelineData, worktreeDiffData]);

  // In native mode, tool_start events are in events[]. Count them directly.
  const nativeToolCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const e of events) {
      if (e.type === "tool_start") {
        // tool name is at e.data.tool (flat event from native engine)
        const t = (e.data?.tool as string) || "Unknown";
        counts[t] = (counts[t] ?? 0) + 1;
      }
    }
    return counts;
  }, [events]);

  const nativeToolCallCount = useMemo(
    () => events.filter((e) => e.type === "tool_start").length,
    [events]
  );

  const nativeErrorCount = useMemo(
    () => events.filter((e) => e.type === "tool_error" || e.type === "error" || e.type === "session_error").length,
    [events]
  );

  // Merge tool counts: WS sessionStats → REST session-stats API → live native events
  const mergedToolCounts = useMemo(() => {
    if (sessionStats?.tool_counts && Object.keys(sessionStats.tool_counts).length > 0) return sessionStats.tool_counts;
    if (sessionStatsApi?.tool_counts && Object.keys(sessionStatsApi.tool_counts).length > 0) return sessionStatsApi.tool_counts;
    return nativeToolCounts;
  }, [sessionStats, sessionStatsApi, nativeToolCounts]);

  // MCP servers from native engine events (emitted once at session start)
  const mcpServers = useMemo(() => {
    const ev = events.filter((e) => e.type === "mcp_servers");
    if (ev.length === 0) return [];
    const last = ev[ev.length - 1];
    return (last.data?.servers as ApiData[]) || [];
  }, [events]);

  // Fall back through: live WS → REST API → native event count → insights
  const mergedToolCallCount: number =
    (sessionStats?.tool_call_count ?? 0) > 0 ? sessionStats!.tool_call_count :
    asNum(sessionStatsApi?.tool_call_count) > 0 ? asNum(sessionStatsApi?.tool_call_count) :
    nativeToolCallCount > 0 ? nativeToolCallCount :
    asNum(insightsData?.total_tool_calls);

  const mergedErrorCount: number =
    (sessionStats?.error_count ?? 0) > 0 ? sessionStats!.error_count :
    asNum(sessionStatsApi?.error_count) > 0 ? asNum(sessionStatsApi?.error_count) :
    nativeErrorCount;

  // Insights: prefer REST API data, fall back to computed from sessionStats
  // API returns [{name, count}] or [{path, edit_count}]; Object.entries gives [k,v] tuples
  const topTools = useMemo(() => {
    if (insightsData && insightsData.top_tools && Array.isArray(insightsData.top_tools) && insightsData.top_tools.length > 0) return insightsData.top_tools;
    if (!mergedToolCounts || Object.keys(mergedToolCounts).length === 0) return [];
    return Object.entries(mergedToolCounts)
      .sort(([, a], [, b]) => (b as number) - (a as number))
      .slice(0, 8)
      .map(([name, count]) => [name, count]);
  }, [insightsData, mergedToolCounts]);

  const hotFiles = useMemo(() => {
    if (insightsData && insightsData.hot_files && Array.isArray(insightsData.hot_files) && insightsData.hot_files.length > 0) return insightsData.hot_files;
    return Array.isArray(fileTouches) ? fileTouches.slice(0, 8) : [];
  }, [insightsData, fileTouches]);

  // Events-based derived data
  const errorEvents = useMemo(
    () => events.filter((e) =>
      e.type === "error" ||
      e.type === "blocked" ||
      e.type === "tool_error"
    ).slice(-30),
    [events]
  );

  const auditEvents = useMemo(
    () => events.filter((e) =>
      e.type === "tool_call" ||
      e.type === "tool_result" ||
      e.type === "file_touch"
    ).slice(-100),
    [events]
  );

  // Merge audit events with audit-timeline when events are sparse
  const mergedAuditEntries = useMemo(() => {
    if (auditEvents.length >= 20) return auditEvents;
    const apiEntries = (auditTimelineData?.entries ?? []) as ApiData[];
    if (apiEntries.length === 0) return auditEvents;
    const fromApi = apiEntries.slice(-80).map((e: ApiData) => {
      let file = "";
      const ti = e.tool_input ?? e.input;
      if (ti && typeof ti === "object" && !Array.isArray(ti)) {
        const tio = ti as ApiData;
        file = asStr(tio.file_path ?? tio.path ?? tio.filename);
      } else if (typeof e.tool_input_preview === "string") {
        const m = e.tool_input_preview.match(/(?:file_path|path|filename)["']?\s*[:=]\s*["']?([^"'\s,}]+)/);
        if (m) file = m[1].trim();
      }
      return {
        timestamp: (e.timestamp ?? "") as string,
        data: {
          tool: (e.tool_name ?? e.tool ?? "audit") as string,
          file,
          result: (e.is_error ? "error" : "ok") as string,
        },
      };
    });
    const combined = [...auditEvents, ...fromApi];
    combined.sort((a, b) => (a.timestamp || "").localeCompare(b.timestamp || ""));
    return combined.slice(-100);
  }, [auditEvents, auditTimelineData]);

  const agentHealthEvents = useMemo(
    () => events.filter((e) => e.type === "agent_health"),
    [events]
  );

  const dispatchEvents = useMemo(
    () => events.filter((e) =>
      e.type === "dispatch" ||
      e.type === "escalation" ||
      e.type === "swarm_dispatch" ||
      e.type === "worker_message"
    ),
    [events]
  );

  const mergeEvents = useMemo(
    () => events.filter((e) =>
      e.type === "merge" ||
      e.type === "swarm_merge" ||
      e.type === "merge_complete"
    ),
    [events]
  );

  // Close on Escape
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [isOpen, onClose]);

  return (
    <>
      {/* Overlay */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 bg-black/40 z-40"
            onClick={onClose}
          />
        )}
      </AnimatePresence>

      {/* Handle on left edge (always visible when closed) */}
      {!isOpen && (
        <button
          onClick={onToggle}
          className="fixed right-0 top-1/2 -translate-y-1/2 z-50 w-5 h-12 bg-[#1A1A1A] border border-r-0 border-[#333] flex items-center justify-center hover:bg-[#222] transition-colors"
          title="Open detail drawer"
        >
          <span className="text-[#555] text-xs">&lt;</span>
        </button>
      )}

      {/* Drawer panel */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            ref={drawerRef}
            initial={{ x: 420 }}
            animate={{ x: 0 }}
            exit={{ x: 420 }}
            transition={{ type: "spring", damping: 30, stiffness: 300 }}
            className="fixed right-0 top-[4.5rem] bottom-16 w-[420px] max-w-[90vw] z-50 bg-[#0C0C0C] border-l border-[#333] flex flex-col shadow-2xl"
          >
            {/* Header */}
            <div className="flex items-center gap-2 px-4 py-3 border-b border-[#222] shrink-0 bg-[#0C0C0C]">
              <span className="text-[var(--color-accent)] text-xs">■</span>
              <h2 className="text-sm font-mono font-bold text-[#E0E0E0] tracking-wider uppercase flex-1">Details</h2>
              {worktreeInfo && (
                <span className="text-[10px] font-mono text-[#555] truncate max-w-[120px]">
                  {worktreeInfo.branch}
                </span>
              )}
              <button
                onClick={onClose}
                className="w-6 h-6 flex items-center justify-center hover:bg-[#1A1A1A] transition-colors text-[#555] hover:text-[#E0E0E0]"
                title="Close drawer"
              >
                {"\u2717"}
              </button>
            </div>

            {/* Tab bar */}
            <div className="flex gap-0.5 px-3 py-2 border-b border-[#222] bg-[#0C0C0C] shrink-0 overflow-x-auto">
              {(
                [
                  { key: "tasks", label: "Tasks", icon: "\u2611" },
                  { key: "observe", label: "Observe", icon: "\u25C6" },
                  { key: "memory", label: "Memory", icon: "\u2261" },
                  { key: "docs", label: "Docs", icon: "\u2234" },
                  ...(isSwarmMode ? [{ key: "swarm", label: "Swarm", icon: "\u2302" }] : []),
                ] as const
              ).map(({ key, label, icon }) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setActiveDrawerTab(key as typeof activeDrawerTab)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 text-[10px] font-mono font-bold uppercase tracking-wider rounded transition-colors shrink-0 ${
                    activeDrawerTab === key
                      ? "bg-[var(--color-accent)]/20 text-[var(--color-accent)] border border-[var(--color-accent)]/50"
                      : "text-[#555] hover:text-[#888] hover:bg-[#1A1A1A] border border-transparent"
                  }`}
                >
                  <span>{icon}</span>
                  {label}
                </button>
              ))}
            </div>

            {/* Scrollable sections (filtered by active tab) */}
            <div className="flex-1 overflow-y-auto tui-scrollbar">
              {/* ── Tasks tab ── */}
              {activeDrawerTab === "tasks" && (
              <DrawerSection
                title="Tasks"
                icon={<span className="text-xs font-mono">{"\u2611"}</span>}
                count={taskList.length}
                hasNotification={failedTasks.length > 0}
                forceOpen={activeSection === "tasks" ? true : undefined}
              >
                {taskList.length === 0 ? (
                  <p className="text-xs font-mono text-[#555]">No tasks yet</p>
                ) : (
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between gap-2 mb-2 flex-wrap">
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] font-mono text-[var(--color-success)]">{doneTasks.length} done</span>
                        {failedTasks.length > 0 && (
                          <span className="text-[10px] font-mono text-[var(--color-error)]">{failedTasks.length} failed</span>
                        )}
                        <span className="text-[10px] font-mono text-[#555]">{taskList.length} total</span>
                      </div>
                      <button
                        type="button"
                        onClick={() => setGraphModalOpen(true)}
                        className="text-[10px] font-mono px-2 py-1 rounded border border-[#333] bg-[#1A1A1A] hover:bg-[#222] hover:border-[var(--color-accent)]/50 text-[#888] hover:text-[var(--color-accent)] transition-colors"
                        title="View task dependency graph"
                      >
                        Graph
                      </button>
                    </div>
                    {taskList.map((task) => (
                      <TaskRow key={task.id} task={task} />
                    ))}
                  </div>
                )}
              </DrawerSection>
              )}

              {/* ── Observe tab ── */}
              {activeDrawerTab === "observe" && (
              <>
              <DrawerSection
                title="Files Changed"
                icon={<span className="text-xs font-mono">{"\u25A0"}</span>}
                count={fileTouches.length || (worktreeInfo?.files_changed ?? 0)}
                forceOpen={activeSection === "files" ? true : undefined}
              >
                {fileTouches.length > 0 ? (
                  <div className="space-y-1">
                    {fileTouches.map(([file, count]) => (
                      <div key={file as string} className="flex items-center gap-2 py-0.5">
                        <span className="text-[10px] font-mono text-[var(--color-accent)] w-6 text-right shrink-0">{count as number}</span>
                        <span className="text-xs font-mono text-[#888] truncate">{file as string}</span>
                      </div>
                    ))}
                  </div>
                ) : worktreeInfo ? (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between text-xs font-mono">
                      <span className="text-[#555]">Files changed</span>
                      <span className="text-[#E0E0E0]">{worktreeInfo.files_changed ?? 0}</span>
                    </div>
                    <div className="flex items-center justify-between text-xs font-mono">
                      <span className="text-[#555]">Insertions</span>
                      <span className="text-[var(--color-success)]">+{worktreeInfo.insertions ?? 0}</span>
                    </div>
                    <div className="flex items-center justify-between text-xs font-mono">
                      <span className="text-[#555]">Deletions</span>
                      <span className="text-[var(--color-error)]">-{worktreeInfo.deletions ?? 0}</span>
                    </div>
                    <p className="text-[10px] font-mono text-[#555]">Use Inspect diff for full file list</p>
                  </div>
                ) : (
                  <p className="text-xs font-mono text-[#555]">No file changes recorded</p>
                )}
              </DrawerSection>

              <DrawerSection
                title="Costs"
                icon={<span className="text-xs font-mono">$</span>}
                forceOpen={activeSection === "costs" ? true : undefined}
              >
                {budgetData || costsData ? (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-mono text-[#555]">Total Cost</span>
                      <span className="text-sm font-mono font-bold text-[#E0E0E0]">
                        ${Number(budgetData?.estimated_cost_usd ?? costsData?.total_cost ?? 0).toFixed(4)}
                      </span>
                    </div>
                    {budgetData && asNum(budgetData.budget_limit_usd) > 0 && (
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-mono text-[#555]">Budget Limit</span>
                        <span className="text-xs font-mono text-[#888]">
                          ${asNum(budgetData.budget_limit_usd).toFixed(2)}
                        </span>
                      </div>
                    )}
                    {budgetData && asNum(budgetData.total_input_tokens) > 0 && (
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-mono text-[#555]">Tokens (in/out)</span>
                        <span className="text-xs font-mono text-[#888]">
                          {asNum(budgetData.total_input_tokens).toLocaleString()} / {asNum(budgetData.total_output_tokens).toLocaleString()}
                        </span>
                      </div>
                    )}
                    {budgetData && asNum(budgetData.session_count) > 0 && (
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-mono text-[#555]">Sessions</span>
                        <span className="text-xs font-mono text-[#888]">{asNum(budgetData.session_count)}</span>
                      </div>
                    )}
                    {budgetData && asNum(budgetData.elapsed_hours) > 0 && (
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-mono text-[#555]">Runtime</span>
                        <span className="text-xs font-mono text-[#888]">{asNum(budgetData.elapsed_hours).toFixed(1)}h</span>
                      </div>
                    )}
                    {!!(costsByModel?.by_model) && typeof costsByModel.by_model === "object" && Object.keys(costsByModel.by_model as object).length > 0 && (
                      <div className="mt-2 pt-2 border-t border-[#222]">
                        <span className="text-[10px] font-mono text-[#555] uppercase tracking-wider">By Model</span>
                        <div className="mt-1 space-y-1">
                          {Object.entries(costsByModel.by_model as Record<string, unknown>).map(([model, cost]) => (
                            <div key={model} className="flex items-center justify-between">
                              <span className="text-[10px] font-mono text-[#888] truncate flex-1">{model}</span>
                              <span className="text-[10px] font-mono text-[var(--color-accent)] ml-2">${asNum(cost).toFixed(4)}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="text-xs font-mono text-[#555]">No cost data yet</p>
                )}
              </DrawerSection>

              {/* 4. Agents */}
              <DrawerSection
                title="Agents"
                icon={<span className="text-xs font-mono">{"\u2302"}</span>}
                count={asArr(agentsData?.agents).length + agentHealthEvents.length}
                forceOpen={activeSection === "agents" ? true : undefined}
              >
                {/* Agent identities from REST API */}
                {asArr(agentsData?.agents).length > 0 ? (
                  <div className="space-y-2">
                    {asArr(agentsData?.agents).map((agent: ApiData, i: number) => {
                      const dotColor =
                        agent.status === "active" || agent.status === "healthy" ? "var(--color-success)" :
                        agent.status === "idle" ? "var(--color-warning)" :
                        "var(--color-text-muted)";
                      return (
                        <div key={asStr(agent.name) || i} className="p-2 bg-[#121212] border border-[#222]">
                          <div className="flex items-center gap-2">
                            <span className="w-2 h-2 shrink-0" style={{ backgroundColor: dotColor }} />
                            <span className="text-xs font-mono font-bold text-[#E0E0E0]">{asStr(agent.name) || `Agent ${i + 1}`}</span>
                            {!!agent.role && (
                              <span className="text-[10px] font-mono text-[#555] px-1 py-0.5 border border-[#333] bg-[#1A1A1A]">{asStr(agent.role)}</span>
                            )}
                          </div>
                          {agent.success_rate != null && (
                            <div className="flex items-center gap-3 mt-1 text-[10px] font-mono text-[#555]">
                              <span>Success: <span className="text-[#888]">{(asNum(agent.success_rate) * 100).toFixed(0)}%</span></span>
                              {agent.total_tool_calls != null && <span>Tools: <span className="text-[#888]">{asNum(agent.total_tool_calls)}</span></span>}
                              {asArr(agent.domains).length > 0 && <span>Domains: <span className="text-[var(--color-accent)]">{(agent.domains as string[]).join(", ")}</span></span>}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ) : agentHealthEvents.length > 0 ? (
                  <div className="space-y-2">
                    {agentHealthEvents.slice(-10).map((evt, i) => {
                      const d = evt.data as Record<string, unknown>;
                      const name = (d.agent_name as string) || (d.worker_id != null ? `Worker ${d.worker_id}` : `Agent ${i + 1}`);
                      const healthStatus = (d.health_status as string) || (d.status as string) || "unknown";
                      const role = (d.capability as string) || (d.role as string) || "builder";
                      const dotColor =
                        healthStatus === "healthy" || healthStatus === "working" ? "var(--color-success)" :
                        healthStatus === "stalled" ? "var(--color-warning)" :
                        healthStatus === "error" || healthStatus === "failed" ? "var(--color-error)" :
                        "var(--color-text-muted)";
                      return (
                        <div key={`${evt.timestamp}-${i}`} className="p-2 bg-[#121212] border border-[#222]">
                          <div className="flex items-center gap-2">
                            <span className="w-2 h-2 shrink-0" style={{ backgroundColor: dotColor }} />
                            <span className="text-xs font-mono font-bold text-[#E0E0E0]">{name}</span>
                            <span className="text-[10px] font-mono text-[#555] px-1 py-0.5 border border-[#333] bg-[#1A1A1A]">{role}</span>
                          </div>
                          <div className="flex items-center gap-2 mt-1 text-[10px] font-mono text-[#555]">
                            <span>{healthStatus}</span>
                            {d.tool_calls != null && <span>{String(d.tool_calls)} tool calls</span>}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : isSwarmMode && asArr(swarmMailData?.messages).length > 0 ? (
                  <div className="space-y-2">
                    <h4 className="text-[10px] font-mono text-[#555] uppercase tracking-wider mb-1">Swarm Mail</h4>
                    {asArr(swarmMailData?.messages).slice(0, 8).map((msg: ApiData, i: number) => (
                      <div key={asStr(msg.id) || i} className="p-2 bg-[#121212] border border-[#222] text-[10px] font-mono">
                        <div className="flex items-center gap-2 text-[#888]">
                          <span>{asStr(msg.sender, "?")}</span>
                          <span>→</span>
                          <span>{asStr(msg.recipient, "?")}</span>
                          {!!msg.msg_type && <span className="text-[var(--color-accent)]">[{asStr(msg.msg_type)}]</span>}
                        </div>
                        <p className="text-[#888] mt-0.5 truncate">{asStr(msg.body ?? msg.content ?? msg.message).slice(0, 80)}</p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs font-mono text-[#555]">No agent data available</p>
                )}
                {isSwarmMode && asArr(swarmMailData?.messages).length > 0 && (asArr(agentsData?.agents).length > 0 || agentHealthEvents.length > 0) && (
                  <div className="mt-3 pt-3 border-t border-[#222] space-y-2">
                    <h4 className="text-[10px] font-mono text-[#555] uppercase tracking-wider mb-1">Swarm Mail</h4>
                    {asArr(swarmMailData?.messages).slice(0, 5).map((msg: ApiData, i: number) => (
                      <div key={`mail-${asStr(msg.id) || i}`} className="p-2 bg-[#121212] border border-[#222] text-[10px] font-mono">
                        <div className="flex items-center gap-2 text-[#888]">
                          <span>{asStr(msg.sender, "?")}</span>
                          <span>→</span>
                          <span>{asStr(msg.recipient, "?")}</span>
                        </div>
                        <p className="text-[#888] mt-0.5 truncate">{asStr(msg.body ?? msg.content ?? msg.message).slice(0, 60)}</p>
                      </div>
                    ))}
                  </div>
                )}
              </DrawerSection>

              {/* 5. Timeline */}
              <DrawerSection
                title="Timeline"
                icon={<span className="text-xs font-mono">{"\u25C6"}</span>}
                count={asArr(timelineData?.events).length}
                forceOpen={activeSection === "timeline" ? true : undefined}
              >
                {asArr(timelineData?.events).length > 0 ? (
                  <div className="space-y-1.5 max-h-72 overflow-y-auto tui-scrollbar">
                    {asArr(timelineData?.events).slice(-40).map((evt: ApiData, i: number) => (
                      <div key={`tl-${i}`} className="flex items-start gap-2 py-1">
                        <span className="text-[10px] font-mono text-[#555] shrink-0 w-16 tabular-nums">
                          {formatTime(asStr(evt.timestamp))}
                        </span>
                        <span className="text-[10px] font-mono text-[var(--color-accent)] shrink-0 w-20 truncate">{asStr(evt.type || evt.event_type)}</span>
                        <span className="text-xs font-mono text-[#888] truncate flex-1">
                          {asStr(evt.summary || evt.message || evt.phase || evt.agent_name) || JSON.stringify(evt.data ?? evt).slice(0, 80)}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs font-mono text-[#555]">No timeline events</p>
                )}
              </DrawerSection>

              {/* 6. Errors */}
              <DrawerSection
                title="Errors"
                icon={<span className="text-xs font-mono text-[var(--color-error)]">!</span>}
                count={errorEvents.length}
                hasNotification={errorEvents.length > 0}
                forceOpen={activeSection === "errors" ? true : undefined}
              >
                {errorEvents.length === 0 ? (
                  <p className="text-xs font-mono text-[#555]">No errors</p>
                ) : (
                  <div className="space-y-2 max-h-64 overflow-y-auto tui-scrollbar">
                    {errorEvents.map((evt, i) => {
                      const severity = (evt.data.severity as string) || (evt.type === "blocked" ? "warning" : "error");
                      const msg = (evt.data.message as string) || (evt.data.error as string) || (evt.data.reason as string) || (evt.data.feedback as string) || JSON.stringify(evt.data);
                      return (
                        <div key={`${evt.timestamp}-${i}`} className="p-2 bg-[#121212] border border-[#222] border-l-2" style={{ borderLeftColor: SEVERITY_COLOR[severity] || SEVERITY_COLOR.error }}>
                          <div className="flex items-center gap-2 mb-1">
                            <span className="text-[10px] font-mono font-medium" style={{ color: SEVERITY_COLOR[severity] || SEVERITY_COLOR.error }}>
                              {severity.toUpperCase()}
                            </span>
                            <span className="text-[10px] font-mono text-[#555]">{formatTime(evt.timestamp)}</span>
                          </div>
                          <p className="text-xs font-mono text-[#888] break-words">{typeof msg === "string" ? msg.slice(0, 300) : String(msg).slice(0, 300)}</p>
                        </div>
                      );
                    })}
                  </div>
                )}
              </DrawerSection>

              {/* Observe tab continues: Audit, Profile, Processes — close before Memory */}
              <DrawerSection
                title="Audit"
                icon={<span className="text-xs font-mono">{"\u2630"}</span>}
                count={mergedAuditEntries.length}
                forceOpen={activeSection === "audit" ? true : undefined}
              >
                {mergedAuditEntries.length === 0 ? (
                  <p className="text-xs font-mono text-[#555]">No audit entries</p>
                ) : (
                  <div className="space-y-0.5 max-h-64 overflow-y-auto tui-scrollbar font-mono text-[10px]">
                    {mergedAuditEntries.slice(-50).map((evt, i) => {
                      const d = evt.data as Record<string, unknown> | undefined;
                      const tool = (d?.tool as string) || (d?.name as string) || ("type" in evt ? (evt as AgentEvent).type : "audit");
                      const file = (d?.file as string) || "";
                      const result = (d?.result as string) || (d?.status as string) || "";
                      return (
                        <div key={`${evt.timestamp}-${i}`} className="flex items-start gap-2 py-0.5 text-[#888]">
                          <span className="text-[#555] shrink-0 w-16 tabular-nums">{formatTime(evt.timestamp)}</span>
                          <span className="text-[var(--color-accent)] shrink-0 max-w-[100px] truncate">{tool}</span>
                          {file && <span className="text-[#555] truncate flex-1">{file}</span>}
                          {result && !file && <span className="text-[#555] truncate flex-1">{String(result).slice(0, 60)}</span>}
                        </div>
                      );
                    })}
                  </div>
                )}
              </DrawerSection>

              <DrawerSection
                title="Profile"
                icon={<span className="text-xs font-mono">{"\u2318"}</span>}
                forceOpen={activeSection === "profile" ? true : undefined}
              >
                {mergedToolCallCount > 0 ? (
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-mono text-[#555]">Tool Calls</span>
                      <span className="text-xs font-mono text-[#E0E0E0] font-bold">{mergedToolCallCount}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-mono text-[#555]">Files Touched</span>
                      <span className="text-xs font-mono text-[#888]">{fileTouches.length}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-mono text-[#555]">Unique Tools</span>
                      <span className="text-xs font-mono text-[#888]">{Object.keys(mergedToolCounts).length}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-mono text-[#555]">Errors</span>
                      <span className={`text-xs font-mono ${mergedErrorCount > 0 ? "text-[var(--color-error)]" : "text-[var(--color-success)]"}`}>
                        {mergedErrorCount}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-mono text-[#555]">Error Rate</span>
                      <span className={`text-xs font-mono ${mergedErrorCount > 0 ? "text-[var(--color-warning)]" : "text-[var(--color-success)]"}`}>
                        {mergedToolCallCount > 0 ? ((mergedErrorCount / mergedToolCallCount) * 100).toFixed(1) : "0.0"}%
                      </span>
                    </div>
                    {sessionStats?.current_phase && (
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-mono text-[#555]">Phase</span>
                        <span className="text-xs font-mono text-[var(--color-accent)]">{sessionStats.current_phase}</span>
                      </div>
                    )}
                    {Array.isArray(sessionChainData) && sessionChainData.length > 1 && (
                      <div className="flex items-center justify-between pt-2 border-t border-[#222]">
                        <span className="text-xs font-mono text-[#555]">Session Chain</span>
                        <span className="text-xs font-mono text-[var(--color-accent)]">{sessionChainData.length} sessions</span>
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="text-xs font-mono text-[#555]">No profile data yet</p>
                )}
              </DrawerSection>

              <DrawerSection
                title="Processes"
                icon={<span className="text-xs font-mono">{"\u2699"}</span>}
                count={asArr(processesData?.processes).length}
                forceOpen={activeSection === "processes" ? true : undefined}
              >
                {asArr(processesData?.processes).length > 0 ? (
                  <div className="space-y-2 max-h-64 overflow-y-auto tui-scrollbar">
                    {asArr(processesData?.processes).map((proc: ApiData, i: number) => (
                      <div key={i} className="p-2 bg-[#121212] border border-[#222]">
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] font-mono text-[var(--color-success)] w-2 h-2 rounded-full bg-current shrink-0" />
                          <span className="text-xs font-mono text-[#E0E0E0]">{asStr(proc.type) || asStr(proc.command) || "Process"}</span>
                          {proc.port != null && <span className="text-[10px] font-mono text-[#555]">:{String(proc.port)}</span>}
                          {proc.pid != null && <span className="text-[10px] font-mono text-[#555] ml-auto">PID {String(proc.pid)}</span>}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : mcpServers.length > 0 ? (
                  <div className="space-y-2">
                    <p className="text-[10px] font-mono text-[#555] uppercase tracking-wider mb-1">MCP Servers</p>
                    {mcpServers.map((s: ApiData, i: number) => (
                      <div key={i} className="p-2 bg-[#121212] border border-[#222]">
                        <span className="text-xs font-mono text-[#E0E0E0]">{asStr(s.name) || asStr(s.id) || `Server ${i + 1}`}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs font-mono text-[#555]">No tracked processes</p>
                )}
              </DrawerSection>
              </>
              )}

              {/* ── Memory & Insights tab ── */}
              {activeDrawerTab === "memory" && (
              <>
              <DrawerSection
                title="Memory"
                icon={<span className="text-xs font-mono">{"\u2261"}</span>}
                defaultOpen={false}
              >
                <div className="min-h-[320px] -mx-2 -mb-2">
                  <MemoryPanel projectDir={projectPath} />
                </div>
              </DrawerSection>

              <DrawerSection
                title="Insights"
                icon={<span className="text-xs font-mono">{"\u2605"}</span>}
                forceOpen={activeSection === "insights" ? true : undefined}
              >
                {(topTools?.length ?? 0) > 0 || (hotFiles?.length ?? 0) > 0 ? (
                  <div className="space-y-2">
                    {(topTools?.length ?? 0) > 0 && (
                      <div>
                        <span className="text-[10px] font-mono text-[#555] uppercase tracking-wider block mb-1">Top Tools</span>
                        <div className="space-y-0.5">
                          {(topTools ?? []).slice(0, 8).map((entry, i) => {
                            const name = Array.isArray(entry) ? entry[0] : (entry?.name ?? (entry as ApiData)?.tool ?? "");
                            const count = Array.isArray(entry) ? entry[1] : (entry?.count ?? (entry as ApiData)?.touches ?? 0);
                            return (
                              <div key={name || i} className="flex justify-between text-[10px] font-mono">
                                <span className="text-[#888] truncate">{name}</span>
                                <span className="text-[var(--color-accent)] shrink-0 ml-2">{String(count)}</span>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}
                    {(hotFiles?.length ?? 0) > 0 && (
                      <div className="pt-2 border-t border-[#222]">
                        <span className="text-[10px] font-mono text-[#555] uppercase tracking-wider block mb-1">Hot Files</span>
                        <div className="space-y-0.5 max-h-32 overflow-y-auto tui-scrollbar">
                          {(hotFiles ?? []).slice(0, 8).map((entry, i) => {
                            const file = Array.isArray(entry) ? entry[0] : (entry?.path ?? (entry as ApiData)?.name ?? "");
                            const count = Array.isArray(entry) ? entry[1] : (entry?.edit_count ?? (entry as ApiData)?.touches ?? (entry as ApiData)?.count ?? 0);
                            return (
                              <div key={(file as string) || i} className="flex justify-between text-[10px] font-mono gap-2">
                                <span className="text-[#888] truncate">{file as string}</span>
                                <span className="text-[var(--color-accent)] shrink-0">{String(count)}</span>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="text-xs font-mono text-[#555]">No insights yet</p>
                )}
              </DrawerSection>

              <DrawerSection
                title="Reflections"
                icon={<span className="text-xs font-mono">{"\u270E"}</span>}
                count={asArr(reflectionsData?.reflections).length || undefined}
                forceOpen={activeSection === "reflections" ? true : undefined}
              >
                {asArr(reflectionsData?.reflections).length > 0 ? (
                  <div className="space-y-2 max-h-64 overflow-y-auto tui-scrollbar">
                    {asArr(reflectionsData?.reflections).slice(-10).map((r: ApiData, i: number) => {
                      const rContent = asStr(r.content ?? r.text);
                      return (
                      <div key={i} className="p-2 bg-[#121212] border border-[#222] border-l-2 border-l-[var(--color-accent)]/50">
                        <div className="flex items-center gap-1.5 mb-0.5">
                          <span className="text-[10px] font-mono text-[var(--color-accent)]">{asStr(r.category, "reflection")}</span>
                          {!!r.timestamp && <span className="text-[10px] font-mono text-[#555]">{formatTime(asStr(r.timestamp))}</span>}
                        </div>
                        <p className="text-xs font-mono text-[#888] leading-relaxed">{rContent.slice(0, 200)}{rContent.length > 200 ? "…" : ""}</p>
                      </div>
                      );
                    })}
                  </div>
                ) : (
                  <p className="text-xs font-mono text-[#555]">No reflections yet</p>
                )}
              </DrawerSection>
              </>
              )}

              {/* ── Docs tab ── */}
              {activeDrawerTab === "docs" && (
              <>
              <DrawerSection
                title="ADRs"
                icon={<span className="text-xs font-mono">{"\u2234"}</span>}
                count={adrData?.adrs?.length}
                onExpand={fetchADRs}
                forceOpen={activeSection === "adrs" ? true : undefined}
              >
                {adrData === null ? (
                  <p className="text-xs font-mono text-[#555]">Expand to load ADRs...</p>
                ) : !adrData.adrs || adrData.adrs.length === 0 ? (
                  <p className="text-xs font-mono text-[#555]">No architecture decision records</p>
                ) : (
                  <div className="space-y-1.5 max-h-64 overflow-y-auto tui-scrollbar">
                    {adrData.adrs.map((adr) => (
                      <div key={adr.id} className="flex items-center gap-2 p-2 bg-[#121212] border border-[#222] border-l-2 border-l-[var(--color-accent)]">
                        <span className="text-[10px] font-mono text-[#555] shrink-0">{adr.id}</span>
                        <span className="text-xs font-mono text-[#E0E0E0] flex-1 truncate">{adr.title}</span>
                        <span className={`text-[10px] font-mono shrink-0 ${
                          adr.status === "accepted" ? "text-[var(--color-success)]" :
                          adr.status === "deprecated" ? "text-[var(--color-error)]" :
                          "text-[#555]"
                        }`}>
                          {adr.status}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </DrawerSection>

              <DrawerSection
                title="Checkpoints"
                icon={<span className="text-xs font-mono">{"\u2691"}</span>}
                count={asArr(checkpointsData?.timeline).length || undefined}
                forceOpen={activeSection === "checkpoints" ? true : undefined}
              >
                {asArr(checkpointsData?.timeline).length > 0 ? (
                  <div className="space-y-1.5 max-h-80 overflow-y-auto tui-scrollbar">
                    {asArr(checkpointsData?.timeline).map((commit: ApiData, i: number) => {
                      const sha = (commit.sha as string) || "";
                      const shortSha = sha.slice(0, 8);
                      const message = (commit.message as string) || "commit";
                      const ts = (commit.timestamp as string) || "";
                      const filesChanged = (commit.files_changed as number) || 0;
                      const insertions = (commit.insertions as number) || 0;
                      const deletions = (commit.deletions as number) || 0;
                      const isResetting = resettingTo === sha;
                      return (
                        <div key={sha || i} className="p-2 bg-[#121212] border border-[#222] border-l-2 border-l-[var(--color-accent)]/40">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="text-[10px] font-mono text-[var(--color-accent)] shrink-0 bg-[var(--color-accent)]/10 px-1.5 py-0.5">
                              {shortSha}
                            </span>
                            <span className="text-xs font-mono text-[#E0E0E0] truncate flex-1">{message}</span>
                            {i > 0 && (
                              <button
                                onClick={() => handleGitReset(sha)}
                                disabled={!!resettingTo}
                                className="text-[10px] font-mono px-2 py-0.5 border border-[var(--color-warning)]/30 text-[var(--color-warning)] hover:bg-[var(--color-warning)]/10 transition-colors disabled:opacity-40 shrink-0"
                              >
                                {isResetting ? "..." : "Revert"}
                              </button>
                            )}
                          </div>
                          <div className="flex items-center gap-3 text-[10px] font-mono text-[#555]">
                            {ts && <span>{formatTime(ts)}</span>}
                            {filesChanged > 0 && <span>{filesChanged} file{filesChanged !== 1 ? "s" : ""}</span>}
                            {insertions > 0 && <span className="text-[var(--color-success)]">+{insertions}</span>}
                            {deletions > 0 && <span className="text-[var(--color-error)]">−{deletions}</span>}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <p className="text-xs font-mono text-[#555]">
                    No commits yet — checkpoints appear here as the agent makes git commits
                  </p>
                )}
              </DrawerSection>
              </>
              )}

              {/* ── Swarm tab (conditional) ── */}
              {activeDrawerTab === "swarm" && isSwarmMode && (
              <>
              <DrawerSection
                  title="Swarm Mail"
                  icon={<span className="text-xs font-mono">{"\u2709"}</span>}
                  count={dispatchEvents.length}
                  forceOpen={activeSection === "mail" ? true : undefined}
                >
                  {dispatchEvents.length === 0 ? (
                    <p className="text-xs font-mono text-[#555]">No dispatch messages</p>
                  ) : (
                    <div className="space-y-1.5 max-h-64 overflow-y-auto tui-scrollbar">
                      {dispatchEvents.slice(-20).map((evt, i) => {
                        const d = evt.data as Record<string, unknown>;
                        const from = (d.from as string) || (d.sender as string) || "system";
                        const to = (d.to as string) || (d.recipient as string) || "all";
                        const msg = (d.message as string) || (d.content as string) || JSON.stringify(d).slice(0, 120);
                        return (
                          <div key={`${evt.timestamp}-${i}`} className="p-2 bg-[#121212] border border-[#222]">
                            <div className="flex items-center gap-1.5 mb-0.5">
                              <span className="text-[10px] font-mono text-[var(--color-accent)]">{from}</span>
                              <span className="text-[#555] text-xs">{"\u2192"}</span>
                              <span className="text-[10px] font-mono text-[#888]">{to}</span>
                              <span className="text-[10px] font-mono text-[#555] ml-auto">{formatTime(evt.timestamp)}</span>
                            </div>
                            <p className="text-xs font-mono text-[#888] break-words">{typeof msg === "string" ? msg.slice(0, 200) : String(msg).slice(0, 200)}</p>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </DrawerSection>

              <DrawerSection
                  title="Merge Queue"
                  icon={<span className="text-xs font-mono">{"\u2387"}</span>}
                  count={mergeEvents.length}
                  forceOpen={activeSection === "merges" ? true : undefined}
                >
                  {mergeEvents.length === 0 ? (
                    <p className="text-xs font-mono text-[#555]">No merge activity</p>
                  ) : (
                    <div className="space-y-1.5 max-h-64 overflow-y-auto tui-scrollbar">
                      {mergeEvents.map((evt, i) => {
                        const d = evt.data as Record<string, unknown>;
                        const branch = (d.branch as string) || (d.source_branch as string) || "unknown";
                        const mergeStatus = (d.status as string) || (d.result as string) || evt.type;
                        const files = (d.files_changed as number) ?? (d.files as number) ?? 0;
                        const statusColor =
                          mergeStatus === "success" || mergeStatus === "merge_complete" ? "var(--color-success)" :
                          mergeStatus === "conflict" ? "var(--color-error)" :
                          mergeStatus === "pending" ? "var(--color-warning)" :
                          "var(--color-text-muted)";
                        return (
                          <div key={`${evt.timestamp}-${i}`} className="flex items-start gap-2 p-2 bg-[#121212] border border-[#222]">
                            <span className="w-2 h-2 mt-1 shrink-0" style={{ backgroundColor: statusColor }} />
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-1.5">
                                <span className="text-xs font-mono text-[#E0E0E0] truncate">{branch}</span>
                                <span className="text-[10px] font-mono text-[#555] ml-auto shrink-0">{formatTime(evt.timestamp)}</span>
                              </div>
                              <div className="flex items-center gap-2 mt-0.5">
                                <span className="text-[10px]" style={{ color: statusColor }}>{mergeStatus}</span>
                                {files > 0 && <span className="text-[10px] font-mono text-[#555]">{files} files</span>}
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </DrawerSection>
              </>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Task Graph full-size modal */}
      {graphModalOpen && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 backdrop-blur-sm"
          onClick={() => setGraphModalOpen(false)}
        >
          <div
            className="bg-[#0C0C0C] border border-[#333] rounded-lg shadow-2xl w-[95vw] h-[85vh] max-w-[1200px] max-h-[900px] flex flex-col overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-4 py-3 border-b border-[#222] shrink-0">
              <h2 className="text-sm font-mono font-bold text-[#E0E0E0] tracking-wider">
                Task Dependency Graph
              </h2>
              <button
                onClick={() => setGraphModalOpen(false)}
                className="w-8 h-8 flex items-center justify-center hover:bg-[#1A1A1A] transition-colors text-[#555] hover:text-[#E0E0E0] rounded"
                title="Close"
              >
                {"\u2717"}
              </button>
            </div>
            <div className="flex-1 min-h-0 overflow-auto p-4">
              <TaskGraph tasks={taskList} />
            </div>
          </div>
        </div>
      )}
    </>
  );
}

/* ---- Sub-components ---- */

function TaskRow({ task }: { task: Task }) {
  const [expanded, setExpanded] = useState(false);
  const statusIcon = TASK_STATUS_ICON[task.status] || TASK_STATUS_ICON.pending;
  const statusColor = TASK_STATUS_COLOR[task.status] || TASK_STATUS_COLOR.pending;

  return (
    <div className="bg-[#121212] border border-[#222] overflow-hidden">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-start gap-2 p-2 text-left hover:bg-[#1A1A1A] transition-colors"
      >
        <span className="text-xs font-mono shrink-0 mt-0.5" style={{ color: statusColor }}>{statusIcon}</span>
        <div className="flex-1 min-w-0">
          <span className="text-xs font-mono text-[#E0E0E0] block">{task.title}</span>
          {task.verification_status && task.verification_status !== "unverified" && (
            <span className={`text-[10px] font-mono ${
              task.verification_status === "verified" ? "text-[var(--color-success)]" :
              task.verification_status === "failed_verification" ? "text-[var(--color-error)]" :
              "text-[var(--color-warning)]"
            }`}>
              {task.verification_status}
              {task.verification_attempts != null && task.verification_attempts > 1 && ` (${task.verification_attempts} attempts)`}
            </span>
          )}
        </div>
        <span className="text-[#555] text-xs shrink-0 mt-0.5">
          {expanded ? "\u25BC" : "\u25B6"}
        </span>
      </button>

      {expanded && (
        <div className="px-2 pb-2 space-y-1.5 border-t border-[#222]">
          {task.description && (
            <p className="text-[11px] text-[#888] pt-1.5 font-mono">{task.description}</p>
          )}
          {task.acceptance_criteria && task.acceptance_criteria.length > 0 && (
            <div className="pt-1">
              <span className="text-[10px] font-mono font-medium text-[#555] uppercase tracking-wider">Acceptance Criteria</span>
              <ul className="mt-0.5 space-y-0.5">
                {task.acceptance_criteria.map((ac, i) => (
                  <li key={i} className="text-[11px] text-[#888] flex items-start gap-1 font-mono">
                    <span className="text-[#555] shrink-0">{"\u00B7"}</span>
                    <span>{ac}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {task.files_affected && task.files_affected.length > 0 && (
            <div className="pt-1">
              <span className="text-[10px] font-mono font-medium text-[#555] uppercase tracking-wider">Files</span>
              <div className="mt-0.5 flex flex-wrap gap-1">
                {task.files_affected.map((f) => (
                  <span key={f} className="text-[10px] font-mono text-[#888] bg-[#1A1A1A] border border-[#333] px-1.5 py-0.5">{f}</span>
                ))}
              </div>
            </div>
          )}
          {task.depends_on && task.depends_on.length > 0 && (
            <div className="flex items-center gap-1 pt-1">
              <span className="text-[10px] font-mono text-[#555]">Depends on:</span>
              {task.depends_on.map((dep) => (
                <span key={dep} className="text-[10px] font-mono text-[var(--color-warning)]">{dep}</span>
              ))}
            </div>
          )}
          {task.last_verification_error && (
            <div className="pt-1 p-1.5 bg-[var(--color-error)]/5 border border-[var(--color-error)]/20">
              <span className="text-[10px] font-mono text-[var(--color-error)]">{task.last_verification_error}</span>
            </div>
          )}
          {task.notes && (
            <p className="text-[10px] font-mono text-[#555] italic pt-1">{task.notes}</p>
          )}
        </div>
      )}
    </div>
  );
}
