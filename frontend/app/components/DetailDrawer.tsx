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
import { SwarmPanel } from "./SwarmPanel";
import { LSPPanel } from "./LSPPanel";
import { SessionBrowserPanel } from "./SessionBrowserPanel";
import { SnapshotPanel } from "./SnapshotPanel";
import { CostPanel } from "./CostPanel";
import { TimelinePanel } from "./TimelinePanel";
import { ProcessPanel } from "./ProcessPanel";
import { SessionChainPanel } from "./SessionChainPanel";
import { RunHistoryPanel } from "./RunHistoryPanel";
import { SpecPanel } from "./SpecPanel";
import { TaskGroupPanel } from "./TaskGroupPanel";
import { InsightsPanel } from "./InsightsPanel";
import { AgentIdentityPanel } from "./AgentIdentityPanel";
import { AuditView } from "./AuditView";
import type { EventStoreResponse } from "./AuditView";
import { ProfileView } from "./ProfileView";
import type { CodebaseProfile } from "./ProfileView";
import { PermissionsPanel } from "./PermissionsPanel";
import { PlanView } from "./PlanView";
import { SkillPanel } from "./SkillPanel";
import { ContextPanel } from "./ContextPanel";
import { DreamPanel } from "./DreamPanel";
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
  /** Agent execution status (idle, running, completed, error) */
  status?: import("../hooks/useSwarmWeaver").AgentStatus;
  /** Plan mode: pending run config waiting for plan approval */
  pendingPlanConfig?: import("../hooks/useSwarmWeaver").RunConfig | null;
  /** Plan mode: called when user approves the plan */
  onPlanApprove?: () => void;
  /** Plan mode: called when user rejects the plan */
  onPlanReject?: () => void;
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

/* ---- Panel width constants ---- */
const MIN_WIDTH = 380;
const DEFAULT_WIDTH = 900;
const MAX_WIDTH = 900;

/* ---- Tab type ---- */
type DrawerTab = "tasks" | "monitor" | "costs" | "code" | "sessions" | "expertise" | "swarm" | "insights" | "agents" | "audit" | "context" | "dreams" | "permissions" | "plan" | "skills" | "memory";

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
  status,
  pendingPlanConfig,
  onPlanApprove,
  onPlanReject,
}: DetailDrawerProps) {
  const drawerRef = useRef<HTMLDivElement>(null);

  // Tab state
  const [activeDrawerTab, setActiveDrawerTab] = useState<DrawerTab>("tasks");

  // Resizable width
  const [panelWidth, setPanelWidth] = useState(DEFAULT_WIDTH);
  const isResizing = useRef(false);
  const startX = useRef(0);
  const startWidth = useRef(DEFAULT_WIDTH);

  const handleResizeStart = useCallback((e: React.MouseEvent) => {
    isResizing.current = true;
    startX.current = e.clientX;
    startWidth.current = panelWidth;
    e.preventDefault();
  }, [panelWidth]);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizing.current) return;
      const delta = startX.current - e.clientX;
      const newWidth = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, startWidth.current + delta));
      setPanelWidth(newWidth);
    };
    const handleMouseUp = () => { isResizing.current = false; };
    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, []);

  const toggleWideMode = useCallback(() => {
    setPanelWidth((w) => w >= MAX_WIDTH ? DEFAULT_WIDTH : MAX_WIDTH);
  }, []);

  // Tab-conditional polling flags
  const isMonitorTab = isOpen && activeDrawerTab === "monitor";
  const isCodeTab = isOpen && activeDrawerTab === "code";
  const isSessionsTab = isOpen && activeDrawerTab === "sessions";
  const isAuditTab = isOpen && activeDrawerTab === "audit";

  // Budget is shared (status strip uses it) — poll always when open
  const { data: budgetData } = useApiPoll("budget", projectPath, isOpen, 15000);

  // Monitor tab polls
  const { data: insightsData } = useApiPoll("insights", projectPath, isMonitorTab, 15000);
  const { data: sessionStatsApi } = useApiPoll("session-stats", projectPath, isMonitorTab, 15000);
  const { data: agentsData } = useApiPoll("agents", projectPath, isMonitorTab, 15000);
  const { data: auditTimelineData } = useApiPoll("audit-timeline", projectPath, isMonitorTab, 15000);

  // Code tab polls
  const { data: checkpointsData } = useApiPoll("session-history", projectPath, isCodeTab, 15000);
  const { data: lspStatusData } = useApiPoll("lsp/status", projectPath, isCodeTab, 10000);
  const { data: lspDiagData } = useApiPoll("lsp/diagnostics", projectPath, isCodeTab, 10000);
  const { data: lspHealthData } = useApiPoll("lsp/code-health", projectPath, isCodeTab, 10000);
  const { data: lspStatsData } = useApiPoll("lsp/stats", projectPath, isCodeTab, 10000);

  // Sessions tab polls
  const { data: sessionChainData } = useApiPoll("session/chain", projectPath, isSessionsTab, 15000);
  const { data: reflectionsData } = useApiPoll("reflections", projectPath, isSessionsTab, 20000);

  // Audit tab polls
  const { data: eventStoreApiData } = useApiPoll("events", projectPath, isAuditTab, 10000);
  const { data: toolStatsData } = useApiPoll("events/tool-stats", projectPath, isAuditTab, 10000);

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

  // Section-to-tab mapping for deep-linking via activeSection prop
  const sectionToTab: Record<string, DrawerTab> = {
    tasks: "tasks",
    "task-groups": "tasks",
    spec: "tasks",
    timeline: "monitor",
    errors: "monitor",
    agents: "agents",
    processes: "monitor",
    audit: "audit",
    profile: "monitor",
    insights: "insights",
    permissions: "permissions",
    plan: "plan",
    skills: "skills",
    context: "context",
    costs: "costs",
    budget: "costs",
    "run-history": "costs",
    files: "code",
    checkpoints: "code",
    snapshots: "code",
    "code-intel": "code",
    adrs: "code",
    sessions: "sessions",
    "session-chain": "sessions",
    reflections: "sessions",
    "expertise-records": "expertise",
    "expertise-causal": "expertise",
    "expertise-lessons": "expertise",
    "expertise-analytics": "expertise",
    dreams: "dreams",
    memory: "memory",
    mail: "swarm",
    merges: "swarm",
  };
  useEffect(() => {
    if (activeSection && sectionToTab[activeSection]) {
      setActiveDrawerTab(sectionToTab[activeSection]);
    }
  }, [activeSection]);

  // Lazy-loaded panels
  const [adrData, setAdrData] = useState<{ adrs: { id: string; title: string; status: string; date: string }[] } | null>(null);
  // Git reset state
  const [resettingTo, setResettingTo] = useState<string | null>(null);

  // Expertise state
  const [expertiseRecords, setExpertiseRecords] = useState<ApiData[]>([]);
  const [expertiseDomains, setExpertiseDomains] = useState<ApiData[]>([]);
  const [expertiseAnalytics, setExpertiseAnalytics] = useState<ApiData | null>(null);
  const [expertiseLoading, setExpertiseLoading] = useState(false);
  const [expertiseCausalChain, setExpertiseCausalChain] = useState<ApiData | null>(null);
  const [expertiseLessons, setExpertiseLessons] = useState<ApiData[]>([]);

  const isExpertiseTab = isOpen && activeDrawerTab === "expertise";

  const fetchExpertiseRecords = useCallback(() => {
    if (!isExpertiseTab) return;
    setExpertiseLoading(true);
    const params = new URLSearchParams();
    if (projectPath) params.set("project_dir", projectPath);
    fetch(`/api/expertise?${params}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (d) setExpertiseRecords(asArr(d.records)); })
      .catch(() => {})
      .finally(() => setExpertiseLoading(false));
  }, [isExpertiseTab, projectPath]);

  const fetchExpertiseDomains = useCallback(() => {
    if (!isExpertiseTab) return;
    const params = new URLSearchParams();
    if (projectPath) params.set("project_dir", projectPath);
    fetch(`/api/expertise/domains?${params}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (d) setExpertiseDomains(asArr(d.domains)); })
      .catch(() => {});
  }, [isExpertiseTab, projectPath]);

  const fetchExpertiseAnalytics = useCallback(() => {
    if (!isExpertiseTab) return;
    const params = new URLSearchParams();
    if (projectPath) params.set("project_dir", projectPath);
    fetch(`/api/expertise/analytics?${params}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (d) setExpertiseAnalytics(d as ApiData); })
      .catch(() => {});
  }, [isExpertiseTab, projectPath]);

  const fetchExpertiseLessons = useCallback(() => {
    if (!isExpertiseTab) return;
    const params = new URLSearchParams();
    if (projectPath) params.set("project_dir", projectPath);
    fetch(`/api/expertise/session-lessons?${params}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (d) setExpertiseLessons(asArr(d.lessons)); })
      .catch(() => {});
  }, [isExpertiseTab, projectPath]);

  const loadExpertiseCausalChain = useCallback((recordId: string) => {
    const params = new URLSearchParams();
    if (projectPath) params.set("project_dir", projectPath);
    fetch(`/api/expertise/causal-chain/${recordId}?${params}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (d) setExpertiseCausalChain(d as ApiData); })
      .catch(() => {});
  }, [projectPath]);

  useEffect(() => {
    if (!isExpertiseTab) return;
    fetchExpertiseRecords();
    fetchExpertiseDomains();
    fetchExpertiseAnalytics();
    fetchExpertiseLessons();
    const interval = setInterval(() => {
      fetchExpertiseRecords();
      fetchExpertiseDomains();
      fetchExpertiseAnalytics();
      fetchExpertiseLessons();
    }, 15000);
    return () => clearInterval(interval);
  }, [isExpertiseTab, fetchExpertiseRecords, fetchExpertiseDomains, fetchExpertiseAnalytics, fetchExpertiseLessons]);

  // Re-fetch lessons when a new expertise WS event arrives (so API data stays current)
  const expertiseEventCount = useMemo(
    () => events.filter((e) => e.type === "expertise_lesson_created").length,
    [events]
  );
  useEffect(() => {
    if (expertiseEventCount > 0) fetchExpertiseLessons();
  }, [expertiseEventCount, fetchExpertiseLessons]);

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

  // File touches: priority chain picks ONE source to avoid double-counting
  // Priority 1: sessionStats.file_touches (real-time WS)
  // Priority 2: sessionStatsApi.file_touches (REST fallback)
  // Priority 3: auditTimelineData (event-based)
  // Priority 4: worktreeDiffData (git diff)
  const fileTouches = useMemo(() => {
    // Priority 1: real-time WS data
    if (sessionStats?.file_touches && Object.keys(sessionStats.file_touches).length > 0) {
      return Object.entries(sessionStats.file_touches).sort(([, a], [, b]) => b - a);
    }
    // Priority 2: REST API fallback
    if (sessionStatsApi?.file_touches && Object.keys(sessionStatsApi.file_touches as Record<string, number>).length > 0) {
      return Object.entries(sessionStatsApi.file_touches as Record<string, number>).sort(([, a], [, b]) => b - a);
    }
    // Priority 3: audit timeline events
    const entries = (auditTimelineData?.entries ?? []) as ApiData[];
    if (entries.length > 0) {
      const touches: Record<string, number> = {};
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
      if (Object.keys(touches).length > 0) {
        return Object.entries(touches).sort(([, a], [, b]) => b - a);
      }
    }
    // Priority 4: worktree diff
    const diff = worktreeDiffData?.diff ?? "";
    if (diff) {
      const touches: Record<string, number> = {};
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
      if (Object.keys(touches).length > 0) {
        return Object.entries(touches).sort(([, a], [, b]) => b - a);
      }
    }
    return [];
  }, [sessionStats, sessionStatsApi, auditTimelineData, worktreeDiffData]);

  // In native mode, tool_start events are in events[]. Count them directly.
  const nativeToolCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const e of events) {
      if (e.type === "tool_start") {
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

  // Merge tool counts: WS sessionStats -> REST session-stats API -> live native events
  const mergedToolCounts = useMemo(() => {
    if (sessionStats?.tool_counts && Object.keys(sessionStats.tool_counts).length > 0) return sessionStats.tool_counts;
    if (sessionStatsApi?.tool_counts && Object.keys(sessionStatsApi.tool_counts).length > 0) return sessionStatsApi.tool_counts;
    return nativeToolCounts;
  }, [sessionStats, sessionStatsApi, nativeToolCounts]);

  // LSP data transformations (API responses -> LSPPanel prop shapes)
  type LspDiag = { uri: string; line: number; character: number; end_line: number; end_character: number; severity: number; severity_label: string; message: string; source: string | null; code: string | number | null };
  type LspServer = { language_id: string; server_name: string; status: "stopped" | "starting" | "ready" | "degraded" | "crashed"; root_uri: string; pid: number | null; started_at: string; restart_count: number; open_files: number; diagnostic_count: number; worker_id: number | null };
  type LspHealth = { score: number; error_count: number; warning_count: number; info_count: number; hint_count: number; by_language: Record<string, { score: number; errors: number; warnings: number }> };

  const lspDiagnostics = useMemo((): Record<string, LspDiag[]> => {
    if (!lspDiagData) return {};
    const diags = lspDiagData.diagnostics;
    if (Array.isArray(diags)) {
      const grouped: Record<string, LspDiag[]> = {};
      for (const d of diags as ApiData[]) {
        const uri = asStr(d.uri || d.file_path || d.file);
        if (!grouped[uri]) grouped[uri] = [];
        grouped[uri].push({
          uri,
          line: asNum(d.line),
          character: asNum(d.character || d.col || d.start_char),
          end_line: asNum(d.end_line || d.line),
          end_character: asNum(d.end_character || d.end_col || d.end_char),
          severity: asNum(d.severity, 1),
          severity_label: asStr(d.severity_label || (asNum(d.severity) === 1 ? "Error" : asNum(d.severity) === 2 ? "Warning" : "Info")),
          message: asStr(d.message),
          source: (d.source as string) ?? null,
          code: (d.code as string | number) ?? null,
        });
      }
      return grouped;
    }
    if (typeof diags === "object" && diags != null) return diags as Record<string, LspDiag[]>;
    return {};
  }, [lspDiagData]);

  const lspServerStatus = useMemo((): Record<string, LspServer> => {
    if (!lspStatusData) return {};
    const servers = lspStatusData.servers;
    if (Array.isArray(servers)) {
      const map: Record<string, LspServer> = {};
      for (const s of servers as ApiData[]) {
        const id = asStr(s.id || s.server_name || s.language_id);
        map[id] = {
          language_id: asStr(s.language_id),
          server_name: asStr(s.server_name || s.name),
          status: asStr(s.status, "stopped") as LspServer["status"],
          root_uri: asStr(s.root_uri || s.root_path),
          pid: s.pid != null ? asNum(s.pid) : null,
          started_at: asStr(s.started_at),
          restart_count: asNum(s.restart_count),
          open_files: asNum(s.open_files || s.file_count),
          diagnostic_count: asNum(s.diagnostic_count || s.diag_count),
          worker_id: s.worker_id != null ? asNum(s.worker_id) : null,
        };
      }
      return map;
    }
    if (typeof servers === "object" && servers != null) return servers as Record<string, LspServer>;
    return {};
  }, [lspStatusData]);

  const lspCodeHealth = useMemo((): LspHealth | null => {
    if (!lspHealthData) return null;
    return {
      score: asNum(lspHealthData.score, 100),
      error_count: asNum(lspHealthData.error_count),
      warning_count: asNum(lspHealthData.warning_count),
      info_count: asNum(lspHealthData.info_count),
      hint_count: asNum(lspHealthData.hint_count),
      by_language: (lspHealthData.by_language as Record<string, { score: number; errors: number; warnings: number }>) ?? {},
    };
  }, [lspHealthData]);

  const [lspCodeHealthTrend, setLspCodeHealthTrend] = useState<number[]>([]);
  useEffect(() => {
    if (lspCodeHealth) {
      setLspCodeHealthTrend((prev) => {
        const next = [...prev, lspCodeHealth.score];
        return next.length > 30 ? next.slice(-30) : next;
      });
    }
  }, [lspCodeHealth]);

  // Fall back through: live WS -> REST API -> native event count -> insights
  const mergedToolCallCount: number =
    (sessionStats?.tool_call_count ?? 0) > 0 ? sessionStats!.tool_call_count :
    asNum(sessionStatsApi?.tool_call_count) > 0 ? asNum(sessionStatsApi?.tool_call_count) :
    nativeToolCallCount > 0 ? nativeToolCallCount :
    asNum(insightsData?.total_tool_calls);

  const dataSource = (sessionStats?.tool_call_count ?? 0) > 0 ? "live" :
    asNum(sessionStatsApi?.tool_call_count) > 0 ? "api" :
    nativeToolCallCount > 0 ? "events" :
    asNum(insightsData?.total_tool_calls) > 0 ? "insights" : "none";

  const mergedErrorCount: number =
    (sessionStats?.error_count ?? 0) > 0 ? sessionStats!.error_count :
    asNum(sessionStatsApi?.error_count) > 0 ? asNum(sessionStatsApi?.error_count) :
    nativeErrorCount;

  // Insights: prefer REST API data, fall back to computed from sessionStats
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

  // Close on Escape
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [isOpen, onClose]);

  // Grouped tab definitions (2-level hierarchy)
  type TabGroup = { key: string; label: string; icon: string; tabs: { key: DrawerTab; label: string }[] };
  const tabGroups: TabGroup[] = [
    {
      key: "tasks", label: "Tasks", icon: "\u2611",
      tabs: [
        { key: "tasks", label: "Tasks" },
        { key: "plan", label: "Plan" },
      ],
    },
    {
      key: "observe", label: "Observe", icon: "\u25C6",
      tabs: [
        { key: "monitor", label: "Timeline" },
        { key: "costs", label: "Costs" },
        { key: "agents", label: "Agents" },
        { key: "insights", label: "Insights" },
        { key: "audit", label: "Audit" },
        { key: "context", label: "Context" },
      ],
    },
    {
      key: "tools", label: "Tools", icon: "\u2726",
      tabs: [
        { key: "skills", label: "Skills" },
        { key: "code", label: "Code" },
        { key: "permissions", label: "Perms" },
      ],
    },
    {
      key: "knowledge", label: "Knowledge", icon: "\u2261",
      tabs: [
        { key: "memory", label: "Memory" },
        { key: "expertise", label: "Expertise" },
        { key: "dreams", label: "Dreams" },
        { key: "sessions", label: "Sessions" },
      ],
    },
    ...(isSwarmMode ? [{
      key: "swarm", label: "Swarm", icon: "\u2302",
      tabs: [{ key: "swarm" as DrawerTab, label: "Swarm" }],
    }] : []),
  ];

  // Find which group the active tab belongs to
  const activeGroup = tabGroups.find((g) => g.tabs.some((t) => t.key === activeDrawerTab)) || tabGroups[0];
  const [selectedGroup, setSelectedGroup] = useState(activeGroup?.key || "tasks");

  // When active tab changes externally (e.g., from command palette), sync the group
  const currentGroup = tabGroups.find((g) => g.tabs.some((t) => t.key === activeDrawerTab));
  if (currentGroup && currentGroup.key !== selectedGroup) {
    setSelectedGroup(currentGroup.key);
  }

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
            className="fixed inset-0 bg-black/30 z-40"
            onClick={onClose}
          />
        )}
      </AnimatePresence>

      {/* Handle on left edge (always visible when closed) */}
      {!isOpen && (
        <button
          onClick={onToggle}
          className="fixed right-0 top-1/2 -translate-y-1/2 z-50 w-5 h-12 bg-[#1A1A1A] border border-r-0 border-[#333] flex items-center justify-center hover:bg-[#222] transition-colors"
          title="Open command panel"
        >
          <span className="text-[#555] text-xs">&lt;</span>
        </button>
      )}

      {/* Panel */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            ref={drawerRef}
            initial={{ x: panelWidth }}
            animate={{ x: 0 }}
            exit={{ x: panelWidth }}
            transition={{ type: "spring", damping: 30, stiffness: 300 }}
            className="fixed right-0 top-[4.5rem] bottom-16 max-w-[90vw] z-50 bg-[#0C0C0C] border-l border-[#333] flex flex-col shadow-2xl"
            style={{ width: panelWidth }}
          >
            {/* Resize handle */}
            <div
              className="absolute left-0 top-0 bottom-0 w-1.5 cursor-col-resize hover:bg-[var(--color-accent)]/30 active:bg-[var(--color-accent)]/50 transition-colors z-10"
              onMouseDown={handleResizeStart}
              title="Drag to resize"
            />

            {/* Header */}
            <div className="flex items-center gap-2 px-4 py-2.5 border-b border-[#222] shrink-0 bg-[#0C0C0C]">
              <span className="text-[var(--color-accent)] text-xs">{"\u25A0"}</span>
              <h2 className="text-sm font-mono font-bold text-[#E0E0E0] tracking-wider uppercase flex-1">Command Panel</h2>
              {worktreeInfo && (
                <span className="text-[10px] font-mono text-[#555] truncate max-w-[120px]">
                  {worktreeInfo.branch}
                </span>
              )}
              <button
                onClick={toggleWideMode}
                className="w-6 h-6 flex items-center justify-center hover:bg-[#1A1A1A] transition-colors text-[#555] hover:text-[#E0E0E0]"
                title={panelWidth >= MAX_WIDTH ? "Collapse panel" : "Expand panel"}
              >
                {panelWidth >= MAX_WIDTH ? "\u25B6\u25C0" : "\u25C0\u25B6"}
              </button>
              <button
                onClick={onClose}
                className="w-6 h-6 flex items-center justify-center hover:bg-[#1A1A1A] transition-colors text-[#555] hover:text-[#E0E0E0]"
                title="Close panel"
              >
                {"\u2717"}
              </button>
            </div>

            {/* Top-level group bar */}
            <div className="flex gap-0.5 px-2 py-1.5 border-b border-[#222] bg-[#0C0C0C] shrink-0">
              {tabGroups.map((group) => {
                const isActive = group.key === selectedGroup;
                return (
                  <button
                    key={group.key}
                    type="button"
                    onClick={() => {
                      setSelectedGroup(group.key);
                      // Switch to first tab in the group if current tab isn't in it
                      if (!group.tabs.some((t) => t.key === activeDrawerTab)) {
                        setActiveDrawerTab(group.tabs[0].key);
                      }
                    }}
                    className={`flex items-center gap-1 px-2.5 py-1.5 text-[10px] font-mono font-bold uppercase tracking-wider transition-colors shrink-0 ${
                      isActive
                        ? "bg-[var(--color-accent)]/15 text-[var(--color-accent)] border-b-2 border-[var(--color-accent)]"
                        : "text-[#555] hover:text-[#888] hover:bg-[#1A1A1A]"
                    }`}
                  >
                    <span>{group.icon}</span>
                    {group.label}
                  </button>
                );
              })}
            </div>

            {/* Sub-tab bar (only if group has >1 tab) */}
            {(() => {
              const group = tabGroups.find((g) => g.key === selectedGroup);
              if (!group || group.tabs.length <= 1) return null;
              return (
                <div className="flex gap-0.5 px-3 py-1 border-b border-[#222] bg-[#0C0C0C]/80 shrink-0">
                  {group.tabs.map(({ key, label }) => (
                    <button
                      key={key}
                      type="button"
                      onClick={() => setActiveDrawerTab(key)}
                      className={`px-2 py-0.5 text-[9px] font-mono font-medium uppercase tracking-wider transition-colors ${
                        activeDrawerTab === key
                          ? "text-[var(--color-accent)] bg-[var(--color-accent)]/10"
                          : "text-[#555] hover:text-[#888]"
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              );
            })()}

            {/* Scrollable sections (filtered by active tab) */}
            <div className="flex-1 overflow-y-auto tui-scrollbar">

              {/* ═══════════════════ Tasks tab ═══════════════════ */}
              {activeDrawerTab === "tasks" && (
              <>
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

              <DrawerSection
                title="Task Groups"
                icon={<span className="text-xs font-mono">{"\u2630"}</span>}
                forceOpen={activeSection === "task-groups" ? true : undefined}
              >
                <div className="min-h-[120px]">
                  <TaskGroupPanel projectDir={projectPath} />
                </div>
              </DrawerSection>

              <DrawerSection
                title="Specifications"
                icon={<span className="text-xs font-mono">{"\u2234"}</span>}
                forceOpen={activeSection === "spec" ? true : undefined}
              >
                <div className="min-h-[120px]">
                  <SpecPanel projectDir={projectPath} />
                </div>
              </DrawerSection>
              </>
              )}

              {/* ═══════════════════ Monitor tab ═══════════════════ */}
              {activeDrawerTab === "monitor" && (
              <>
              <DrawerSection
                title="Timeline"
                icon={<span className="text-xs font-mono">{"\u25C6"}</span>}
                defaultOpen={true}
                forceOpen={activeSection === "timeline" ? true : undefined}
              >
                <div className="min-h-[200px]">
                  <TimelinePanel projectDir={projectPath} />
                </div>
              </DrawerSection>

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
                      const d = evt.data || {};
                      const severity = (d.severity as string) || (evt.type === "blocked" ? "warning" : "error");
                      const msg = (d.message as string) || (d.error as string) || (d.reason as string) || (d.feedback as string) || JSON.stringify(d);
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

              <DrawerSection
                title="Processes"
                icon={<span className="text-xs font-mono">{"\u2699"}</span>}
                forceOpen={activeSection === "processes" ? true : undefined}
              >
                <div className="min-h-[100px]">
                  <ProcessPanel projectDir={projectPath} />
                </div>
              </DrawerSection>

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
                ) : isSwarmMode ? (
                  <p className="text-xs font-mono text-[#555]">See the Swarm tab for worker details and mail</p>
                ) : (
                  <p className="text-xs font-mono text-[#555]">No agent data available</p>
                )}
              </DrawerSection>

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
                title={`Profile (${dataSource})`}
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
                title="Insights"
                icon={<span className="text-xs font-mono">{"\u25C8"}</span>}
              >
                <button
                  onClick={() => setActiveDrawerTab("insights")}
                  className="text-[10px] font-mono text-[var(--color-accent)] hover:underline"
                >
                  Open full Insights panel {"\u2192"}
                </button>
              </DrawerSection>
              </>
              )}

              {/* ═══════════════════ Costs tab ═══════════════════ */}
              {activeDrawerTab === "costs" && (
              <>
              <DrawerSection
                title="Budget"
                icon={<span className="text-xs font-mono">$</span>}
                defaultOpen={true}
                forceOpen={activeSection === "budget" ? true : undefined}
              >
                {budgetData ? (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-mono text-[#555]">Total Cost</span>
                      <span className="text-sm font-mono font-bold text-[#E0E0E0]">
                        {String(budgetData?.cost_display || `$${Number(budgetData?.estimated_cost_usd ?? 0).toFixed(4)}`)}
                      </span>
                    </div>
                    {asNum(budgetData.budget_limit_usd) > 0 && (
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-mono text-[#555]">Budget Limit</span>
                        <span className="text-xs font-mono text-[#888]">
                          ${asNum(budgetData.budget_limit_usd).toFixed(2)}
                        </span>
                      </div>
                    )}
                    {asNum(budgetData.total_input_tokens) > 0 && (
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-mono text-[#555]">Tokens (in/out)</span>
                        <span className="text-xs font-mono text-[#888]">
                          {asNum(budgetData.total_input_tokens).toLocaleString()} / {asNum(budgetData.total_output_tokens).toLocaleString()}
                        </span>
                      </div>
                    )}
                    {asNum(budgetData.total_cache_read_tokens) > 0 && (
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-mono text-[#555]">Cache (read/write)</span>
                        <span className="text-xs font-mono text-[#3B82F6]">
                          {asNum(budgetData.total_cache_read_tokens).toLocaleString()} / {asNum(budgetData.total_cache_write_tokens).toLocaleString()}
                        </span>
                      </div>
                    )}
                    {asNum(budgetData.cache_efficiency) > 0 && (
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-mono text-[#555]">Cache Efficiency</span>
                        <span className="text-xs font-mono text-[#10B981]">
                          {(asNum(budgetData.cache_efficiency) * 100).toFixed(1)}%
                        </span>
                      </div>
                    )}
                    {asNum(budgetData.session_count) > 0 && (
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-mono text-[#555]">Sessions</span>
                        <span className="text-xs font-mono text-[#888]">{asNum(budgetData.session_count)}</span>
                      </div>
                    )}
                    {asNum(budgetData.elapsed_hours) > 0 && (
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-mono text-[#555]">Runtime</span>
                        <span className="text-xs font-mono text-[#888]">{asNum(budgetData.elapsed_hours).toFixed(1)}h</span>
                      </div>
                    )}
                    {(asNum(budgetData.total_lines_added) > 0 || asNum(budgetData.total_lines_removed) > 0) && (
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-mono text-[#555]">Code Changes</span>
                        <span className="text-xs font-mono">
                          <span className="text-[#10B981]">+{asNum(budgetData.total_lines_added).toLocaleString()}</span>
                          {" / "}
                          <span className="text-[#EF4444]">-{asNum(budgetData.total_lines_removed).toLocaleString()}</span>
                        </span>
                      </div>
                    )}
                    {asNum(budgetData.web_search_count) > 0 && (
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-mono text-[#555]">Web Searches</span>
                        <span className="text-xs font-mono text-[#888]">{asNum(budgetData.web_search_count)}</span>
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="text-xs font-mono text-[#555]">No budget data yet</p>
                )}
              </DrawerSection>

              <DrawerSection
                title="Cost Breakdown"
                icon={<span className="text-xs font-mono">{"\u2261"}</span>}
                forceOpen={activeSection === "costs" ? true : undefined}
              >
                <div className="min-h-[200px]">
                  <CostPanel projectDir={projectPath} liveBudget={budgetData} />
                </div>
              </DrawerSection>

              <DrawerSection
                title="Run History"
                icon={<span className="text-xs font-mono">{"\u25A3"}</span>}
                forceOpen={activeSection === "run-history" ? true : undefined}
              >
                <div className="min-h-[150px]">
                  <RunHistoryPanel projectDir={projectPath} />
                </div>
              </DrawerSection>
              </>
              )}

              {/* ═══════════════════ Code tab ═══════════════════ */}
              {activeDrawerTab === "code" && (
              <>
              <DrawerSection
                title="Files Changed"
                icon={<span className="text-xs font-mono">{"\u25A0"}</span>}
                count={fileTouches.length || (worktreeInfo?.files_changed ?? 0)}
                defaultOpen={true}
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
                title="Code Intel"
                icon={<span className="text-xs font-mono">{"\u2726"}</span>}
                count={(() => { const n = Object.values(lspDiagnostics).reduce((sum, arr) => sum + arr.length, 0); return n > 0 ? n : undefined; })()}
                forceOpen={activeSection === "code-intel" ? true : undefined}
              >
                <div className="min-h-[280px] -mx-2 -mb-2">
                  <LSPPanel
                    diagnostics={lspDiagnostics}
                    serverStatus={lspServerStatus}
                    codeHealth={lspCodeHealth}
                    codeHealthTrend={lspCodeHealthTrend}
                    crossWorkerAlerts={[]}
                    projectDir={projectPath || ""}
                    isTeamMode={isSwarmMode}
                    workerCount={0}
                    stats={lspStatsData as any ?? undefined}
                  />
                </div>
              </DrawerSection>

              <DrawerSection
                title="Snapshots"
                icon={<span className="text-xs font-mono">{"\u25A3"}</span>}
                forceOpen={activeSection === "snapshots" ? true : undefined}
              >
                <div className="min-h-[150px]">
                  <SnapshotPanel projectDir={projectPath} status={undefined} />
                </div>
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
                            {deletions > 0 && <span className="text-[var(--color-error)]">{"\u2212"}{deletions}</span>}
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
              </>
              )}

              {/* ═══════════════════ Sessions tab ═══════════════════ */}
              {activeDrawerTab === "sessions" && (
              <>
              <DrawerSection
                title="Session Browser"
                icon={<span className="text-xs font-mono">{"\u25A3"}</span>}
                defaultOpen={true}
                forceOpen={activeSection === "sessions" ? true : undefined}
              >
                <div className="min-h-[200px]">
                  <SessionBrowserPanel projectDir={projectPath} />
                </div>
              </DrawerSection>

              <DrawerSection
                title="Session Chain"
                icon={<span className="text-xs font-mono">{"\u2192"}</span>}
                forceOpen={activeSection === "session-chain" ? true : undefined}
              >
                <div className="min-h-[150px]">
                  <SessionChainPanel projectDir={projectPath} />
                </div>
              </DrawerSection>

              <DrawerSection
                title="Reflections"
                icon={<span className="text-xs font-mono">{"\u270E"}</span>}
                count={asArr(reflectionsData?.reflections).length || undefined}
                forceOpen={activeSection === "reflections" ? true : undefined}
              >
                {asArr(reflectionsData?.reflections).length > 0 ? (
                  <div className="space-y-2 max-h-64 overflow-y-auto tui-scrollbar">
                    {asArr(reflectionsData?.reflections).length > 30 && (
                      <div className="text-[9px] font-mono text-[#444] mb-1">
                        Showing last 30 of {asArr(reflectionsData?.reflections).length}
                      </div>
                    )}
                    {asArr(reflectionsData?.reflections).slice(-30).map((r: ApiData, i: number) => {
                      const rContent = asStr(r.content ?? r.text);
                      return (
                      <div key={i} className="p-2 bg-[#121212] border border-[#222] border-l-2 border-l-[var(--color-accent)]/50">
                        <div className="flex items-center gap-1.5 mb-0.5">
                          <span className="text-[10px] font-mono text-[var(--color-accent)]">{asStr(r.category, "reflection")}</span>
                          {!!r.timestamp && <span className="text-[10px] font-mono text-[#555]">{formatTime(asStr(r.timestamp))}</span>}
                        </div>
                        <p className="text-xs font-mono text-[#888] leading-relaxed">{rContent.slice(0, 200)}{rContent.length > 200 ? "\u2026" : ""}</p>
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

              {/* ═══════════════════ Memory tab ═══════════════════ */}
              {activeDrawerTab === "memory" && projectPath && (
                <div className="p-0 h-full">
                  <MemoryPanel projectDir={projectPath} />
                </div>
              )}

              {/* ═══════════════════ Expertise tab ═══════════════════ */}
              {activeDrawerTab === "expertise" && (
              <>
              <DrawerSection
                title="Records"
                icon={<span className="text-xs font-mono">{"\u2261"}</span>}
                count={expertiseRecords.length || undefined}
                defaultOpen={true}
                forceOpen={activeSection === "expertise-records" ? true : undefined}
              >
                {expertiseLoading ? (
                  <p className="text-xs font-mono text-[#555]">Loading...</p>
                ) : expertiseRecords.length > 0 ? (
                  <div className="space-y-1.5 max-h-80 overflow-y-auto tui-scrollbar">
                    {expertiseRecords.map((r: ApiData) => {
                      const id = asStr(r.id);
                      const recordType = asStr(r.record_type);
                      const content = asStr(r.content);
                      const domain = asStr(r.domain);
                      const confidence = asNum(r.confidence);
                      const classification = asStr(r.classification);
                      const resolvedBy = asArr(r.resolved_by as unknown as ApiData[]);
                      const resolves = asStr(r.resolves as unknown as string);
                      const tags = Array.isArray(r.tags) ? r.tags as string[] : [];
                      const typeColor = recordType === "failure" || recordType === "antipattern"
                        ? "var(--color-error)"
                        : recordType === "resolution" || recordType === "pattern"
                        ? "var(--color-success)"
                        : recordType === "convention" || recordType === "decision"
                        ? "var(--color-accent)"
                        : recordType === "heuristic" || recordType === "guide"
                        ? "var(--color-warning)"
                        : "#888";
                      return (
                        <div key={id} className="p-2 bg-[#121212] border border-[#222] border-l-2" style={{ borderLeftColor: typeColor }}>
                          <div className="flex items-center gap-2 mb-0.5">
                            <span className="text-[10px] font-mono px-1.5 py-0.5 border" style={{ color: typeColor, borderColor: typeColor + "50", backgroundColor: typeColor + "10" }}>
                              {recordType}
                            </span>
                            <span className="text-[10px] font-mono text-[#555]">{classification}</span>
                            <span className="ml-auto flex items-center gap-1">
                              <span className="text-[10px] font-mono text-[#555]">{(confidence * 100).toFixed(0)}%</span>
                              <span className="w-10 h-1 bg-[#222] rounded-full overflow-hidden inline-block">
                                <span className={`h-full block rounded-full ${confidence >= 0.7 ? "bg-[var(--color-success)]" : confidence >= 0.4 ? "bg-[var(--color-warning)]" : "bg-[var(--color-error)]"}`} style={{ width: `${confidence * 100}%` }} />
                              </span>
                            </span>
                          </div>
                          <p className="text-xs font-mono text-[#E0E0E0] leading-relaxed">{content.slice(0, 200)}{content.length > 200 ? "\u2026" : ""}</p>
                          <div className="flex items-center gap-2 mt-0.5 text-[10px] font-mono text-[#555]">
                            {domain && <span className="text-[var(--color-accent)]">{domain}</span>}
                            {resolvedBy.length > 0 && <span className="text-[var(--color-success)]">(resolved)</span>}
                            {resolves && <span className="text-[var(--color-info)]">(fixes)</span>}
                            {tags.length > 0 && <span>{tags.slice(0, 3).join(", ")}</span>}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <p className="text-xs font-mono text-[#555]">No expertise records yet</p>
                )}
              </DrawerSection>

              <DrawerSection
                title="Causal Chains"
                icon={<span className="text-xs font-mono">{"\u2192"}</span>}
                count={expertiseRecords.filter((r) => asStr(r.record_type) === "failure").length || undefined}
                forceOpen={activeSection === "expertise-causal" ? true : undefined}
              >
                {(() => {
                  const failures = expertiseRecords.filter((r) => asStr(r.record_type) === "failure");
                  if (failures.length === 0) {
                    return <p className="text-xs font-mono text-[#555]">No failure records — causal chains link failures to resolutions</p>;
                  }
                  return (
                    <div className="space-y-1.5 max-h-64 overflow-y-auto tui-scrollbar">
                      {failures.map((f) => {
                        const fId = asStr(f.id);
                        const fContent = asStr(f.content);
                        const resolvedBy = asArr(f.resolved_by as unknown as ApiData[]);
                        const chainData = expertiseCausalChain && asStr(expertiseCausalChain.root) === fId ? asArr(expertiseCausalChain.chain) : [];
                        return (
                          <div key={fId} className="p-2 bg-[#121212] border border-[#222] border-l-2 border-l-[var(--color-error)]">
                            <div
                              className="flex items-center gap-2 cursor-pointer"
                              onClick={() => loadExpertiseCausalChain(fId)}
                            >
                              <span className="text-[var(--color-error)] text-xs font-mono shrink-0">!</span>
                              <span className="text-xs font-mono text-[#E0E0E0] flex-1 truncate">{fContent}</span>
                              {resolvedBy.length > 0 ? (
                                <span className="text-[var(--color-success)] text-[10px] font-mono shrink-0">{resolvedBy.length} fix(es)</span>
                              ) : (
                                <span className="text-[var(--color-error)] text-[10px] font-mono shrink-0">unresolved</span>
                              )}
                            </div>
                            {chainData.length > 1 && (
                              <div className="mt-1.5 ml-4 border-l-2 border-[var(--color-success)]/30 pl-2 space-y-1">
                                {chainData.slice(1).map((cr) => (
                                  <div key={asStr(cr.id)} className="text-xs font-mono text-[var(--color-success)] flex items-center gap-1">
                                    <span className="text-[10px]">{"\u2713"}</span>
                                    <span className="truncate">{asStr(cr.content)}</span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  );
                })()}
              </DrawerSection>

              <DrawerSection
                title="Session Lessons"
                icon={<span className="text-xs font-mono">{"\u26A1"}</span>}
                count={expertiseLessons.length || events.filter((e) => e.type.startsWith("expertise_")).length || undefined}
                onExpand={fetchExpertiseLessons}
                forceOpen={activeSection === "expertise-lessons" ? true : undefined}
              >
                {(() => {
                  // Merge API-fetched lessons + real-time WS events
                  const lessonEvents = events.filter(
                    (e) => e.type === "expertise_lesson_created" || e.type === "expertise_lesson_propagated" || e.type === "expertise_record_promoted"
                  );
                  // Build deduplicated list: API lessons first, then WS-only events
                  const apiLessonIds = new Set(expertiseLessons.map((l) => String(l.id || "")));
                  const wsOnlyEvents = lessonEvents.filter((ev) => !apiLessonIds.has(String(ev.data?.lesson_id || "")));

                  if (expertiseLessons.length === 0 && wsOnlyEvents.length === 0) {
                    return <p className="text-xs font-mono text-[#555]">No session lessons yet — lessons appear during swarm mode when workers encounter similar errors</p>;
                  }
                  const severityColor: Record<string, string> = {
                    critical: "var(--color-error)",
                    high: "var(--color-warning)",
                    medium: "var(--color-accent)",
                    low: "var(--color-text-muted)",
                  };
                  return (
                    <div className="space-y-1.5 max-h-64 overflow-y-auto tui-scrollbar">
                      {/* API-fetched lessons (persistent) */}
                      {expertiseLessons.map((lesson, i) => {
                        const sev = String(lesson.severity || "low");
                        const sevColor = severityColor[sev] || "var(--color-text-muted)";
                        const score = Number(lesson.quality_score || 0);
                        const propagated = Array.isArray(lesson.propagated_to) ? lesson.propagated_to : [];
                        return (
                          <div key={`api-${String(lesson.id || i)}`} className="p-2 bg-[#121212] border border-[#222] border-l-2" style={{ borderLeftColor: sevColor }}>
                            <div className="flex items-center gap-2">
                              <span className="text-[10px] font-mono px-1.5 py-0.5 border" style={{ color: sevColor, borderColor: sevColor + "50", backgroundColor: sevColor + "10" }}>
                                {sev.toUpperCase()}
                              </span>
                              {Boolean(lesson.promoted_to_record_id) && (
                                <span className="text-[10px] font-mono px-1.5 py-0.5 border" style={{ color: "var(--color-success)", borderColor: "var(--color-success)" + "50" }}>
                                  PROMOTED
                                </span>
                              )}
                              <span className="text-xs font-mono text-[#E0E0E0] flex-1 truncate">
                                {String(lesson.content || "")}
                              </span>
                            </div>
                            <div className="text-[10px] font-mono text-[#555] mt-0.5 flex gap-2">
                              {Boolean(lesson.domain) && <span>domain: {String(lesson.domain)}</span>}
                              <span>quality: {score.toFixed(2)}</span>
                              {propagated.length > 0 && <span>sent to {propagated.length} worker(s)</span>}
                              {Boolean(lesson.created_at) && <span>{String(lesson.created_at).slice(0, 19)}</span>}
                            </div>
                          </div>
                        );
                      })}
                      {/* WS-only events (real-time, not yet in API) */}
                      {wsOnlyEvents.map((ev, i) => {
                        const label = ev.type === "expertise_lesson_propagated" ? "PROP" : ev.type === "expertise_record_promoted" ? "PERM" : "NEW";
                        const labelColor = ev.type === "expertise_record_promoted"
                          ? "var(--color-success)"
                          : ev.type === "expertise_lesson_propagated"
                          ? "var(--color-info)"
                          : "var(--color-warning)";
                        return (
                          <div key={`ws-${i}`} className="p-2 bg-[#121212] border border-[#222] border-l-2" style={{ borderLeftColor: labelColor }}>
                            <div className="flex items-center gap-2">
                              <span className="text-[10px] font-mono px-1.5 py-0.5 border" style={{ color: labelColor, borderColor: labelColor + "50", backgroundColor: labelColor + "10" }}>
                                {label}
                              </span>
                              <span className="text-xs font-mono text-[#E0E0E0] flex-1 truncate">
                                {(ev.data?.content as string) || (ev.data?.lesson_id as string) || ""}
                              </span>
                            </div>
                            <div className="text-[10px] font-mono text-[#555] mt-0.5">
                              {formatTime(ev.timestamp)}
                              {ev.data?.worker_id != null && ` | worker-${String(ev.data.worker_id)}`}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  );
                })()}
              </DrawerSection>

              <DrawerSection
                title="Analytics"
                icon={<span className="text-xs font-mono">{"\u2606"}</span>}
                onExpand={fetchExpertiseAnalytics}
                forceOpen={activeSection === "expertise-analytics" ? true : undefined}
              >
                {expertiseAnalytics ? (
                  (() => {
                    const totalRecords = asNum(expertiseAnalytics.total_records);
                    const byType: Record<string, number> = (expertiseAnalytics.by_type as Record<string, number>) || {};
                    const domainHealth = asArr(expertiseAnalytics.domain_health);
                    const topRecords = asArr(expertiseAnalytics.top_records);
                    const typeEntries = Object.entries(byType);
                    return (
                  <div className="space-y-3">
                    <div className="flex gap-3">
                      <div className="flex items-center justify-between flex-1">
                        <span className="text-xs font-mono text-[#555]">Total Records</span>
                        <span className="text-sm font-mono font-bold text-[#E0E0E0]">{totalRecords}</span>
                      </div>
                      <div className="flex items-center justify-between flex-1">
                        <span className="text-xs font-mono text-[#555]">Types</span>
                        <span className="text-sm font-mono font-bold text-[#E0E0E0]">{typeEntries.length}</span>
                      </div>
                      <div className="flex items-center justify-between flex-1">
                        <span className="text-xs font-mono text-[#555]">Domains</span>
                        <span className="text-sm font-mono font-bold text-[#E0E0E0]">{domainHealth.length}</span>
                      </div>
                    </div>
                    {typeEntries.length > 0 && (
                      <div>
                        <span className="text-[10px] font-mono text-[#555] uppercase tracking-wider block mb-1">By Type</span>
                        <div className="space-y-0.5">
                          {typeEntries.map(([type, count]) => (
                            <div key={type} className="flex justify-between text-[10px] font-mono">
                              <span className="text-[#888]">{type}</span>
                              <span className="text-[var(--color-accent)] shrink-0 ml-2">{String(count)}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                    {domainHealth.length > 0 && (
                      <div className="pt-2 border-t border-[#222]">
                        <span className="text-[10px] font-mono text-[#555] uppercase tracking-wider block mb-1">Domain Health</span>
                        <div className="space-y-0.5">
                          {domainHealth.map((d: ApiData) => (
                            <div key={asStr(d.domain)} className="flex justify-between text-[10px] font-mono">
                              <span className="text-[#888]">{asStr(d.domain)}</span>
                              <span className={`shrink-0 ml-2 ${
                                asStr(d.status) === "critical" ? "text-[var(--color-error)]" :
                                asStr(d.status) === "warning" ? "text-[var(--color-warning)]" :
                                "text-[#555]"
                              }`}>
                                {asNum(d.count)} ({asStr(d.status)})
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                    {topRecords.length > 0 && (
                      <div className="pt-2 border-t border-[#222]">
                        <span className="text-[10px] font-mono text-[#555] uppercase tracking-wider block mb-1">Top by Confidence</span>
                        <div className="space-y-0.5">
                          {topRecords.map((tr: ApiData) => (
                            <div key={asStr(tr.id)} className="flex items-center gap-2 text-[10px] font-mono">
                              <span className="text-[var(--color-accent)] shrink-0">{(asNum(tr.confidence) * 100).toFixed(0)}%</span>
                              <span className="text-[#888] truncate flex-1">{asStr(tr.content)}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                    );
                  })()
                ) : (
                  <p className="text-xs font-mono text-[#555]">Expand to load analytics...</p>
                )}
              </DrawerSection>

              <DrawerSection
                title="Domains"
                icon={<span className="text-xs font-mono">{"\u2302"}</span>}
                count={expertiseDomains.length || undefined}
              >
                {expertiseDomains.length > 0 ? (
                  <div className="space-y-0.5">
                    {expertiseDomains.map((d: ApiData) => (
                      <div key={asStr(d.name)} className="flex justify-between text-[10px] font-mono py-0.5">
                        <span className="text-[var(--color-accent)]">{asStr(d.name)}</span>
                        <span className="text-[#555]">{asNum(d.count)} records</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs font-mono text-[#555]">No domains configured</p>
                )}
              </DrawerSection>
              </>
              )}

              {/* ═══════════════════ Insights tab ═══════════════════ */}
              {activeDrawerTab === "insights" && projectPath && (
                <div className="p-0 h-full">
                  <InsightsPanel projectDir={projectPath} />
                </div>
              )}

              {/* ═══════════════════ Agents tab ═══════════════════ */}
              {activeDrawerTab === "agents" && projectPath && (
                <div className="p-0 h-full">
                  <AgentIdentityPanel projectDir={projectPath} status={status} />
                </div>
              )}

              {/* ═══════════════════ Audit tab ═══════════════════ */}
              {activeDrawerTab === "audit" && (
                <div className="p-0 h-full">
                  <AuditView loading={false} events={events} eventStoreData={eventStoreApiData as EventStoreResponse | null} toolStats={Array.isArray(toolStatsData?.tool_stats) ? toolStatsData.tool_stats : Array.isArray(toolStatsData) ? toolStatsData : []} />
                </div>
              )}

              {/* ═══════════════════ Context tab ═══════════════════ */}
              {activeDrawerTab === "context" && (
                <div className="p-0 h-full">
                  <ContextPanel projectDir={projectPath} />
                </div>
              )}

              {/* ═══════════════════ Dreams tab ═══════════════════ */}
              {activeDrawerTab === "dreams" && projectPath && (
                <div className="p-0 h-full">
                  <DreamPanel projectDir={projectPath} />
                </div>
              )}

              {/* ═══════════════════ Permissions tab ═══════════════════ */}
              {activeDrawerTab === "permissions" && projectPath && (
                <div className="p-0 h-full">
                  <PermissionsPanel projectDir={projectPath} />
                </div>
              )}

              {/* ═══════════════════ Plan tab ═══════════════════ */}
              {activeDrawerTab === "plan" && (projectPath || pendingPlanConfig?.project_dir) && (
                <div className="p-0 h-full">
                  <PlanView
                    projectDir={projectPath || pendingPlanConfig?.project_dir || ""}
                    mode={pendingPlanConfig?.mode || "feature"}
                    taskInput={pendingPlanConfig?.task_input || ""}
                    model={pendingPlanConfig?.model || "claude-sonnet-4-6"}
                    onApprove={onPlanApprove || (() => {})}
                    onReject={onPlanReject || (() => {})}
                    onModify={() => {}}
                  />
                </div>
              )}

              {/* ═══════════════════ Skills tab ═══════════════════ */}
              {activeDrawerTab === "skills" && (
                <div className="p-0 h-full">
                  <SkillPanel projectDir={projectPath} />
                </div>
              )}

              {/* ═══════════════════ Swarm tab (conditional) ═══════════════════ */}
              {activeDrawerTab === "swarm" && isSwarmMode && (
                <SwarmPanel
                  projectDir={projectPath}
                  output={output}
                />
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
