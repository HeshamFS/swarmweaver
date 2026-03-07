"use client";

import { useState, useMemo, useEffect, useCallback } from "react";
import type { TaskData, Task, AgentStatus } from "../hooks/useSwarmWeaver";
import { TaskGraph } from "./TaskGraph";

interface TaskGroup {
  id: string;
  name: string;
  task_ids: string[];
  status: string;
  worker_id?: number;
}

interface QualityGateInfo {
  passed: boolean;
  gates: { name: string; passed: boolean; detail: string }[];
}

interface TaskPanelProps {
  tasks: TaskData | null;
  status?: AgentStatus;
  currentPhase?: string;
  projectDir?: string;
  qualityGatesByWorker?: Record<number, QualityGateInfo>;
}

const STATUS_COLORS: Record<string, string> = {
  completed: "text-[var(--color-success)]",
  done: "text-[var(--color-success)]",
  in_progress: "text-[var(--color-accent)]",
  pending: "text-[var(--color-text-muted)]",
  blocked: "text-[var(--color-warning)]",
  failed: "text-[var(--color-error)]",
  skipped: "text-[var(--color-text-muted)]",
};

const STATUS_ICONS: Record<string, string> = {
  completed: "\u2713",
  done: "\u2713",
  in_progress: "\u25B6",
  pending: "\u25CB",
  blocked: "\u29B8",
  failed: "\u2717",
  skipped: "\u2015",
};

// Phase 2: Verification badge colors
const VERIFY_COLORS: Record<string, string> = {
  verified: "text-[var(--color-success)]",
  retrying: "text-[var(--color-warning)]",
  failed_verification: "text-[var(--color-error)]",
  unverified: "text-[var(--color-text-muted)]",
};

const VERIFY_ICONS: Record<string, string> = {
  verified: "\u2714",
  retrying: "\u21BB",
  failed_verification: "\u2717",
};

function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1 text-xs font-mono font-medium ${STATUS_COLORS[status] || "text-[var(--color-text-muted)]"}`}
      role="status"
      aria-label={`Task status: ${status}`}
    >
      <span aria-hidden="true">{STATUS_ICONS[status] || "\u25CB"}</span>
      {status}
    </span>
  );
}

function VerificationBadge({
  task,
  onClick,
  isExpanded,
}: {
  task: Task;
  onClick?: () => void;
  isExpanded?: boolean;
}) {
  const vStatus = task.verification_status;
  if (!vStatus || vStatus === "unverified") return null;

  const icon = VERIFY_ICONS[vStatus] || "";
  const color = VERIFY_COLORS[vStatus] || "text-[var(--color-text-muted)]";

  return (
    <span className="inline-flex flex-col items-end">
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          onClick?.();
        }}
        className={`inline-flex items-center text-[10px] font-mono ${color} hover:opacity-80 cursor-pointer`}
        aria-label={`Verification status: ${vStatus}${task.verification_attempts ? `, ${task.verification_attempts} attempt(s)` : ""}`}
        title={
          task.last_verification_error
            ? `Verification: ${task.last_verification_error}`
            : `Verification: ${vStatus}`
        }
      >
        <span aria-hidden="true">{icon}</span>
        {task.verification_attempts && task.verification_attempts > 0 && (
          <span className="ml-0.5">({task.verification_attempts})</span>
        )}
      </button>
      {isExpanded && task.last_verification_error && (
        <div className="mt-1 p-1.5 rounded-md bg-[var(--color-error)]/10 border border-[var(--color-error)]/20 text-[10px] text-[var(--color-error)] font-mono max-w-[240px] break-words">
          {task.last_verification_error}
        </div>
      )}
    </span>
  );
}

function ProgressBar({
  done,
  total,
}: {
  done: number;
  total: number;
}) {
  const pct = total > 0 ? (done / total) * 100 : 0;
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-2 rounded-full bg-[var(--color-surface-2)] overflow-hidden shadow-inner flex items-center p-[1px]">
        <div
          className="h-full rounded-full bg-gradient-to-r from-[var(--color-accent)] to-[#FF3366] transition-all duration-500 shadow-[0_0_8px_var(--color-accent-glow)]"
          style={{ width: `${Math.max(pct, 2)}%` }}
        />
      </div>
      <span className="text-xs text-[var(--color-text-secondary)] font-mono whitespace-nowrap font-medium">
        {done}/{total}
      </span>
    </div>
  );
}

function ExternalLinkBadge({ task }: { task: Task }) {
  if (!task.external_url) return null;
  return (
    <a
      href={task.external_url}
      target="_blank"
      rel="noopener noreferrer"
      onClick={(e) => e.stopPropagation()}
      className="inline-flex items-center text-[10px] text-[var(--color-text-muted)] hover:text-[var(--color-accent)] transition-colors ml-1"
      title={`GitHub Issue #${task.external_id || ""}`}
    >
      <svg className="w-3 h-3" viewBox="0 0 16 16" fill="currentColor">
        <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
      </svg>
    </a>
  );
}

type ViewMode = "list" | "graph";

export function TaskPanel({ tasks, status, currentPhase, projectDir, qualityGatesByWorker }: TaskPanelProps) {
  const [viewMode, setViewMode] = useState<ViewMode>("list");
  const [taskSearch, setTaskSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [expandedTask, setExpandedTask] = useState<string | null>(null);
  const [verificationDetailTask, setVerificationDetailTask] = useState<string | null>(null);
  const [taskGroups, setTaskGroups] = useState<TaskGroup[]>([]);
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());

  // Sync state
  const [syncStatus, setSyncStatus] = useState<{ last_synced: string; direction: string; tasks_pulled: number; tasks_pushed: number; errors: string[]; in_progress: boolean } | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [showSyncMenu, setShowSyncMenu] = useState(false);

  const isAgentRunning = status === "running" || status === "starting";

  // Fetch task groups (F15)
  const fetchTaskGroups = useCallback(async () => {
    if (!projectDir) return;
    try {
      const res = await fetch(`/api/task-groups?path=${encodeURIComponent(projectDir)}`);
      const data = await res.json();
      if (data.groups && Array.isArray(data.groups)) {
        setTaskGroups(data.groups);
      }
    } catch {
      // Ignore — endpoint may not be available yet
    }
  }, [projectDir]);

  useEffect(() => {
    if (projectDir) {
      fetchTaskGroups();
      if (status === "running") {
        const interval = setInterval(fetchTaskGroups, 8000);
        return () => clearInterval(interval);
      }
    }
  }, [projectDir, status, fetchTaskGroups]);

  const toggleGroup = (groupId: string) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(groupId)) {
        next.delete(groupId);
      } else {
        next.add(groupId);
      }
      return next;
    });
  };

  // Fetch sync status
  useEffect(() => {
    if (!projectDir) return;
    fetch(`/api/tasks/sync/status?path=${encodeURIComponent(projectDir)}`)
      .then((r) => r.ok ? r.json() : null)
      .then((data) => { if (data) setSyncStatus(data); })
      .catch(() => {});
  }, [projectDir]);

  const handleSync = useCallback(async (direction: string) => {
    if (!projectDir || syncing) return;
    setSyncing(true);
    setShowSyncMenu(false);
    try {
      const res = await fetch(`/api/tasks/sync?path=${encodeURIComponent(projectDir)}&direction=${direction}`, { method: "POST" });
      const data = await res.json();
      if (res.ok) {
        setSyncStatus(data);
      }
    } catch {
      // ignore
    } finally {
      setSyncing(false);
    }
  }, [projectDir, syncing]);

  const allTasks = tasks?.tasks || [];
  const done = allTasks.filter((t: Task) => t.status === "completed" || t.status === "done").length;
  const total = allTasks.length;

  // Verification summary counts (Wave 2.6) — hooks must be before any early return
  const verifySummary = useMemo(() => {
    let verified = 0;
    let retrying = 0;
    let failedVerification = 0;
    for (const t of allTasks) {
      if (t.verification_status === "verified") verified++;
      else if (t.verification_status === "retrying") retrying++;
      else if (t.verification_status === "failed_verification") failedVerification++;
    }
    return { verified, retrying, failedVerification };
  }, [allTasks]);

  // Filter tasks by search and status (Wave 3.2)
  const filteredTasks = useMemo(() => {
    let result = allTasks;

    // Status filter
    if (statusFilter !== "all") {
      const statusMap: Record<string, string[]> = {
        pending: ["pending"],
        in_progress: ["in_progress"],
        done: ["completed", "done"],
        failed: ["failed"],
      };
      const matchStatuses = statusMap[statusFilter] || [statusFilter];
      result = result.filter((t: Task) => matchStatuses.includes(t.status));
    }

    // Search filter
    if (taskSearch.trim()) {
      const q = taskSearch.trim().toLowerCase();
      result = result.filter(
        (t: Task) =>
          t.title.toLowerCase().includes(q) ||
          (t.id && t.id.toLowerCase().includes(q))
      );
    }

    return result;
  }, [allTasks, statusFilter, taskSearch]);

  if (total === 0) {
    return (
      <div className="flex flex-col h-full rounded-2xl border border-[var(--color-border-subtle)] bg-[var(--color-surface-glass)] backdrop-blur-2xl shadow-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-[var(--color-border-subtle)] bg-[var(--color-surface-1)]/40 backdrop-blur-md">
          <span className="text-sm text-[var(--color-text-primary)] font-bold tracking-wide">Tasks</span>
        </div>
        <div className="flex-1 flex flex-col items-center justify-center p-6 gap-4">
          {isAgentRunning ? (
            <>
              <svg className="w-8 h-8 animate-spin text-[var(--color-accent)] drop-shadow-[0_0_8px_var(--color-accent-glow)]" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <span className="text-sm text-[var(--color-text-primary)] font-medium">
                Creating task list...
              </span>
              {currentPhase && (
                <span className="text-xs text-[var(--color-text-muted)] font-mono px-3 py-1 bg-[var(--color-surface-2)] rounded-full border border-[var(--color-border-subtle)]">
                  Phase: {currentPhase}
                </span>
              )}
              <div className="w-48 h-1.5 rounded-full bg-[var(--color-surface-2)] overflow-hidden mt-2 p-[1px]">
                <div className="h-full bg-gradient-to-r from-[var(--color-accent)] to-[#FF3366] rounded-full shimmer" style={{ width: "60%" }} />
              </div>
            </>
          ) : (
            <div className="text-center">
              <span className="text-sm text-[var(--color-text-muted)]">
                No tasks yet. Start an agent run to generate tasks.
              </span>
            </div>
          )}
        </div>
      </div>
    );
  }

  // Group filtered tasks by category
  const byCategory: Record<string, Task[]> = {};
  for (const task of filteredTasks) {
    const cat = task.category || "general";
    if (!byCategory[cat]) byCategory[cat] = [];
    byCategory[cat].push(task);
  }

  // Status summary (from all tasks, not filtered)
  const statusCounts: Record<string, number> = {};
  for (const t of allTasks) {
    statusCounts[t.status] = (statusCounts[t.status] || 0) + 1;
  }

  const STATUS_FILTER_OPTIONS = [
    { key: "all", label: "All" },
    { key: "pending", label: "Pending" },
    { key: "in_progress", label: "In Progress" },
    { key: "done", label: "Done" },
    { key: "failed", label: "Failed" },
  ];

  return (
    <div className="flex flex-col h-full rounded-2xl border border-[var(--color-border-subtle)] bg-[var(--color-surface-glass)] backdrop-blur-2xl shadow-xl overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-[var(--color-border-subtle)] bg-[var(--color-surface-1)]/40 backdrop-blur-md">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-sm text-[var(--color-text-primary)] font-bold tracking-wide">Tasks</span>
            <div className="flex rounded-md border border-[var(--color-border-subtle)] overflow-hidden bg-[var(--color-surface-2)]/50 p-0.5" role="tablist" aria-label="Task view mode">
              <button
                onClick={() => setViewMode("list")}
                role="tab"
                aria-selected={viewMode === "list"}
                aria-label="List view"
                className={`px-2 py-1 text-[10px] font-bold uppercase tracking-wider transition-all rounded-sm ${viewMode === "list"
                    ? "bg-[var(--color-surface-1)] text-[var(--color-accent)] shadow-sm"
                    : "text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
                  }`}
              >
                List
              </button>
              <button
                onClick={() => setViewMode("graph")}
                role="tab"
                aria-selected={viewMode === "graph"}
                aria-label="Graph view"
                className={`px-2 py-1 text-[10px] font-bold uppercase tracking-wider transition-all rounded-sm ${viewMode === "graph"
                    ? "bg-[var(--color-surface-1)] text-[var(--color-accent)] shadow-sm"
                    : "text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
                  }`}
              >
                Graph
              </button>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {/* Sync button with dropdown */}
            <div className="relative">
              <button
                type="button"
                onClick={() => setShowSyncMenu(!showSyncMenu)}
                disabled={syncing}
                className={`text-[10px] font-medium px-2 py-1 rounded-md border transition-all ${
                  syncing
                    ? "text-[var(--color-accent)] border-[var(--color-accent)]/30 bg-[var(--color-accent)]/10 animate-pulse"
                    : "text-[var(--color-text-muted)] border-[var(--color-border-subtle)] hover:text-[var(--color-text-primary)] hover:border-[var(--color-border-default)]"
                }`}
                title={syncStatus?.last_synced ? `Last synced: ${new Date(syncStatus.last_synced).toLocaleString()}` : "Never synced"}
              >
                {syncing ? "Syncing..." : "Sync"}
              </button>
              {showSyncMenu && !syncing && (
                <div className="absolute right-0 top-full mt-1 z-20 w-44 rounded-lg border border-[var(--color-border-subtle)] bg-[var(--color-surface-1)] shadow-xl overflow-hidden">
                  <button
                    onClick={() => handleSync("pull")}
                    className="w-full text-left px-3 py-2 text-xs text-[var(--color-text-primary)] hover:bg-[var(--color-surface-2)] transition-colors"
                  >
                    Sync from GitHub
                  </button>
                  <button
                    onClick={() => handleSync("push")}
                    className="w-full text-left px-3 py-2 text-xs text-[var(--color-text-primary)] hover:bg-[var(--color-surface-2)] transition-colors"
                  >
                    Push to GitHub
                  </button>
                  <button
                    onClick={() => handleSync("bidirectional")}
                    className="w-full text-left px-3 py-2 text-xs text-[var(--color-text-primary)] hover:bg-[var(--color-surface-2)] transition-colors border-t border-[var(--color-border-subtle)]"
                  >
                    Two-way Sync
                  </button>
                  {syncStatus?.last_synced && (
                    <div className="px-3 py-1.5 text-[10px] text-[var(--color-text-muted)] border-t border-[var(--color-border-subtle)] bg-[var(--color-surface-2)]/50">
                      Last: {new Date(syncStatus.last_synced).toLocaleTimeString()}
                    </div>
                  )}
                </div>
              )}
            </div>
            <span className="text-xs text-[var(--color-accent)] font-bold tracking-wider">
              {Math.round((done / total) * 100)}%
            </span>
          </div>
        </div>
        <div className="mt-1.5">
          <ProgressBar done={done} total={total} />
        </div>
        {/* Status chips */}
        <div className="flex flex-wrap gap-2 mt-3">
          {Object.entries(statusCounts).map(([st, count]) => (
            <span
              key={st}
              className={`text-xs font-mono font-medium px-2 py-0.5 rounded-md border border-[var(--color-border-subtle)] bg-[var(--color-surface-2)]/50 ${STATUS_COLORS[st] || "text-[var(--color-text-muted)]"}`}
            >
              <span className="font-bold opacity-80">{count}</span> {st}
            </span>
          ))}
        </div>

        {/* Verification summary (Wave 2.6) */}
        {(verifySummary.verified > 0 || verifySummary.retrying > 0 || verifySummary.failedVerification > 0) && (
          <div className="flex items-center gap-3 mt-2 text-[10px] font-bold uppercase tracking-wider bg-[var(--color-surface-2)]/30 p-1.5 rounded-lg border border-[var(--color-border-subtle)] w-fit">
            <span className="text-[var(--color-success)] flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-[var(--color-success)]"></span> {verifySummary.verified} verified</span>
            <span className="text-[var(--color-warning)] flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-[var(--color-warning)]"></span> {verifySummary.retrying} retrying</span>
            <span className="text-[var(--color-error)] flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-[var(--color-error)]"></span> {verifySummary.failedVerification} failed</span>
          </div>
        )}

        {/* Search input (Wave 3.2) */}
        <div className="mt-3 relative">
          <input
            type="text"
            value={taskSearch}
            onChange={(e) => setTaskSearch(e.target.value)}
            placeholder="Search tasks..."
            className="w-full pl-8 pr-3 py-2 text-sm rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-surface-2)]/60 backdrop-blur-md text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] focus:outline-none focus:border-[var(--color-accent)] focus:ring-1 focus:ring-[var(--color-accent)] transition-all"
          />
          <svg className="w-4 h-4 text-[var(--color-text-muted)] absolute left-3 top-1/2 -translate-y-1/2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </div>

        {/* Filter pills (Wave 3.2) */}
        <div className="flex flex-wrap gap-1.5 mt-2.5">
          {STATUS_FILTER_OPTIONS.map((opt) => (
            <button
              key={opt.key}
              onClick={() => setStatusFilter(opt.key)}
              className={`px-3 py-1 text-[11px] font-medium rounded-full border transition-all duration-300 ${statusFilter === opt.key
                  ? "bg-[var(--color-accent)]/10 text-[var(--color-accent)] border-[var(--color-accent)]/30 shadow-[0_0_10px_var(--color-accent-glow)]"
                  : "text-[var(--color-text-muted)] border-[var(--color-border-subtle)] hover:text-[var(--color-text-primary)] hover:border-[var(--color-border-default)] hover:bg-[var(--color-surface-2)]"
                }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* Task list or graph */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {viewMode === "graph" ? (
          <TaskGraph tasks={allTasks} />
        ) : taskGroups.length > 0 ? (
          /* Group-based display (F15) */
          <>
            {taskGroups.map((group) => {
              const groupTasks = allTasks.filter((t: Task) => group.task_ids.includes(t.id));
              const groupDone = groupTasks.filter((t: Task) => t.status === "completed" || t.status === "done").length;
              const isCollapsed = collapsedGroups.has(group.id);

              return (
                <div key={group.id}>
                  {/* Group header */}
                  <div
                    onClick={() => toggleGroup(group.id)}
                    className="sticky top-0 z-10 px-4 py-3 bg-[var(--color-surface-1)]/80 backdrop-blur-xl border-b border-[var(--color-border-subtle)] cursor-pointer hover:bg-[var(--color-surface-2)]/80 transition-colors shadow-sm"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <span className={`text-xs text-[var(--color-text-muted)] transition-transform duration-300 ${isCollapsed ? "" : "rotate-90"}`}>
                          &#9656;
                        </span>
                        <span className="text-sm font-bold text-[var(--color-text-primary)]">
                          {group.name}
                        </span>
                        <span
                          className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-md border ${group.status === "completed"
                              ? "text-[var(--color-success)] bg-[var(--color-success)]/10 border-[var(--color-success)]/30"
                              : group.status === "active"
                                ? "text-[var(--color-accent)] bg-[var(--color-accent)]/10 border-[var(--color-accent)]/30 shadow-[0_0_8px_var(--color-accent-glow)]"
                                : "text-[var(--color-text-muted)] bg-[var(--color-surface-2)] border-[var(--color-border-subtle)]"
                            }`}
                        >
                          {group.status}
                        </span>
                        {group.worker_id != null && (
                          <span className="text-[10px] text-[var(--color-text-muted)] font-mono bg-[var(--color-surface-3)] px-1.5 py-0.5 rounded">
                            W{group.worker_id}
                          </span>
                        )}
                        {/* Quality gate badge for this worker's group */}
                        {group.worker_id != null && qualityGatesByWorker?.[group.worker_id] && (
                          <span
                            className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${
                              qualityGatesByWorker[group.worker_id].passed
                                ? "text-[var(--color-success)] bg-[var(--color-success)]/10 border-[var(--color-success)]/30"
                                : "text-orange-400 bg-orange-400/10 border-orange-400/30"
                            }`}
                          >
                            {qualityGatesByWorker[group.worker_id].passed ? "\u2714 Verified" : "\u21BA Under Review"}
                          </span>
                        )}
                      </div>
                      <span className="text-xs text-[var(--color-text-muted)] font-mono font-medium">
                        {groupDone}/{groupTasks.length}
                      </span>
                    </div>
                    {/* Group progress bar */}
                    <div className="mt-2">
                      <div className="h-1.5 rounded-full bg-[var(--color-surface-3)] overflow-hidden flex p-[1px]">
                        <div
                          className={`h-full rounded-full transition-all duration-500 shadow-sm ${groupDone === groupTasks.length && groupTasks.length > 0
                              ? "bg-[var(--color-success)] shadow-[0_0_8px_var(--color-success)]"
                              : "bg-gradient-to-r from-[var(--color-accent)] to-[#FF3366] shadow-[0_0_8px_var(--color-accent-glow)]"
                            }`}
                          style={{ width: `${Math.max(groupTasks.length > 0 ? (groupDone / groupTasks.length) * 100 : 0, 2)}%` }}
                        />
                      </div>
                    </div>
                  </div>
                  {/* Group tasks */}
                  {!isCollapsed && groupTasks.map((task: Task) => {
                    const isExpanded = expandedTask === task.id;
                    const isVerifyExpanded = verificationDetailTask === task.id;
                    const isRetrying = task.verification_status === "retrying";
                    return (
                      <div key={task.id}>
                        <div
                          onClick={() => setExpandedTask(isExpanded ? null : task.id)}
                          className={`px-4 py-3 border-b border-[var(--color-border-subtle)]/50 hover:bg-[var(--color-surface-2)]/40 transition-all cursor-pointer ${task.status === "completed" || task.status === "done" ? "opacity-60 grayscale-[20%]" : ""
                            } ${isRetrying ? "ring-1 ring-[var(--color-warning)]/60 animate-pulse bg-[var(--color-warning)]/5" : ""}`}
                        >
                          <div className="flex items-start gap-3">
                            <StatusBadge status={task.status} />
                            <div className="flex-1 min-w-0 flex flex-col justify-center">
                              <div className="text-sm font-medium text-[var(--color-text-primary)] truncate flex items-center">
                                {task.title}
                                <ExternalLinkBadge task={task} />
                              </div>
                              {task.id && (
                                <span className="text-[10px] text-[var(--color-text-muted)] font-mono mt-0.5">
                                  {task.id}
                                </span>
                              )}
                            </div>
                            <div className="flex items-center gap-2 mt-0.5">
                              <VerificationBadge
                                task={task}
                                onClick={() =>
                                  setVerificationDetailTask(
                                    isVerifyExpanded ? null : task.id
                                  )
                                }
                                isExpanded={isVerifyExpanded}
                              />
                              {task.priority && (
                                <span className="text-[10px] text-[var(--color-text-muted)] font-mono px-1.5 py-0.5 rounded border border-[var(--color-border-subtle)] bg-[var(--color-surface-2)]">
                                  P{task.priority}
                                </span>
                              )}
                              <span className={`text-[10px] text-[var(--color-text-muted)] transition-transform duration-300 ${isExpanded ? "rotate-90" : ""}`}>
                                &#9656;
                              </span>
                            </div>
                          </div>
                        </div>
                        {isExpanded && (
                          <div className="px-5 py-4 bg-[var(--color-surface-1)]/30 border-b border-[var(--color-border-subtle)]/50 text-xs space-y-3 shadow-inner">
                            {task.description && (
                              <div>
                                <span className="text-[var(--color-text-muted)] font-bold uppercase tracking-wider text-[10px] block mb-1">Description</span>
                                <p className="text-[var(--color-text-secondary)] whitespace-pre-wrap leading-relaxed bg-[var(--color-surface-2)]/30 p-2 rounded-md border border-[var(--color-border-subtle)]/50">{task.description}</p>
                              </div>
                            )}
                            {task.acceptance_criteria && task.acceptance_criteria.length > 0 && (
                              <div>
                                <span className="text-[var(--color-text-muted)] font-bold uppercase tracking-wider text-[10px] block mb-1">Acceptance Criteria</span>
                                <ul className="list-disc list-inside text-[var(--color-text-secondary)] space-y-1 bg-[var(--color-surface-2)]/30 p-2 rounded-md border border-[var(--color-border-subtle)]/50">
                                  {task.acceptance_criteria.map((ac, i) => (
                                    <li key={i}>{ac}</li>
                                  ))}
                                </ul>
                              </div>
                            )}
                            {task.files_affected && task.files_affected.length > 0 && (
                              <div>
                                <span className="text-[var(--color-text-muted)] font-bold uppercase tracking-wider text-[10px] block mb-1">Files Affected</span>
                                <div className="flex flex-wrap gap-1.5">
                                  {task.files_affected.map((f, i) => (
                                    <code key={i} className="px-2 py-0.5 rounded-md bg-[var(--color-surface-3)] text-[var(--color-text-secondary)] text-[10px] font-mono border border-[var(--color-border-subtle)] shadow-sm">
                                      {f}
                                    </code>
                                  ))}
                                </div>
                              </div>
                            )}
                            {task.notes && (
                              <div>
                                <span className="text-[var(--color-text-muted)] font-bold uppercase tracking-wider text-[10px] block mb-1">Notes</span>
                                <p className="text-[var(--color-text-secondary)] whitespace-pre-wrap italic bg-[var(--color-warning)]/5 text-[var(--color-warning)] p-2 rounded-md border border-[var(--color-warning)]/20">{task.notes}</p>
                              </div>
                            )}
                            {task.depends_on && task.depends_on.length > 0 && (
                              <div>
                                <span className="text-[var(--color-text-muted)] font-bold uppercase tracking-wider text-[10px] block mb-1">Dependencies</span>
                                <div className="flex flex-wrap gap-1.5">
                                  {task.depends_on.map((dep) => (
                                    <span key={dep} className="px-2 py-0.5 rounded-md bg-[var(--color-surface-2)] text-[var(--color-text-muted)] text-[10px] font-mono border border-[var(--color-border-subtle)]">
                                      {dep}
                                    </span>
                                  ))}
                                </div>
                              </div>
                            )}
                            {task.completed_at && (
                              <div>
                                <span className="text-[var(--color-text-muted)] font-bold uppercase tracking-wider text-[10px] block mb-1">Completed</span>
                                <span className="text-[var(--color-success)] font-mono font-medium">{task.completed_at}</span>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              );
            })}
            {/* Show ungrouped tasks (tasks not in any group) */}
            {(() => {
              const allGroupedIds = new Set(taskGroups.flatMap((g) => g.task_ids));
              const ungrouped = filteredTasks.filter((t: Task) => !allGroupedIds.has(t.id));
              if (ungrouped.length === 0) return null;
              const ungroupedByCategory: Record<string, Task[]> = {};
              for (const task of ungrouped) {
                const cat = task.category || "general";
                if (!ungroupedByCategory[cat]) ungroupedByCategory[cat] = [];
                ungroupedByCategory[cat].push(task);
              }
              return Object.entries(ungroupedByCategory)
                .sort(([a], [b]) => a.localeCompare(b))
                .map(([category, catTasks]) => {
                  const catDone = catTasks.filter(
                    (t: Task) => t.status === "completed" || t.status === "done"
                  ).length;
                  return (
                    <div key={`ungrouped-${category}`}>
                      <div className="sticky top-0 px-3 py-1.5 bg-surface-raised/80 backdrop-blur-sm border-b border-border-subtle">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-medium text-text-secondary uppercase tracking-wider">
                            {category}
                          </span>
                          <span className="text-xs text-text-muted font-mono">
                            {catDone}/{catTasks.length}
                          </span>
                        </div>
                      </div>
                      {catTasks.map((task: Task) => {
                        const isExpanded = expandedTask === task.id;
                        const isVerifyExpanded = verificationDetailTask === task.id;
                        const isRetrying = task.verification_status === "retrying";
                        return (
                          <div key={task.id}>
                            <div
                              onClick={() => setExpandedTask(isExpanded ? null : task.id)}
                              className={`px-3 py-2 border-b border-border-subtle/50 hover:bg-surface-raised/50 transition-colors cursor-pointer ${task.status === "completed" || task.status === "done" ? "opacity-60" : ""
                                } ${isRetrying ? "ring-1 ring-warning/60 animate-pulse" : ""}`}
                            >
                              <div className="flex items-start gap-2">
                                <StatusBadge status={task.status} />
                                <div className="flex-1 min-w-0">
                                  <div className="text-sm text-text-primary truncate flex items-center">
                                    {task.title}
                                    <ExternalLinkBadge task={task} />
                                  </div>
                                  {task.id && (
                                    <span className="text-xs text-text-muted font-mono">
                                      {task.id}
                                    </span>
                                  )}
                                </div>
                                <div className="flex items-center gap-1.5">
                                  <VerificationBadge
                                    task={task}
                                    onClick={() =>
                                      setVerificationDetailTask(
                                        isVerifyExpanded ? null : task.id
                                      )
                                    }
                                    isExpanded={isVerifyExpanded}
                                  />
                                  {task.priority && (
                                    <span className="text-xs text-text-muted font-mono">
                                      P{task.priority}
                                    </span>
                                  )}
                                  <span className={`text-[10px] text-text-muted transition-transform ${isExpanded ? "rotate-90" : ""}`}>
                                    &#9656;
                                  </span>
                                </div>
                              </div>
                            </div>
                            {isExpanded && (
                              <div className="px-4 py-2.5 bg-surface-raised/30 border-b border-border-subtle/50 text-xs space-y-2">
                                {task.description && (
                                  <div>
                                    <span className="text-text-muted font-mono block mb-0.5">Description</span>
                                    <p className="text-text-secondary whitespace-pre-wrap">{task.description}</p>
                                  </div>
                                )}
                                {task.acceptance_criteria && task.acceptance_criteria.length > 0 && (
                                  <div>
                                    <span className="text-text-muted font-mono block mb-0.5">Acceptance Criteria</span>
                                    <ul className="list-disc list-inside text-text-secondary space-y-0.5">
                                      {task.acceptance_criteria.map((ac, i) => (
                                        <li key={i}>{ac}</li>
                                      ))}
                                    </ul>
                                  </div>
                                )}
                                {task.files_affected && task.files_affected.length > 0 && (
                                  <div>
                                    <span className="text-text-muted font-mono block mb-0.5">Files Affected</span>
                                    <div className="flex flex-wrap gap-1">
                                      {task.files_affected.map((f, i) => (
                                        <code key={i} className="px-1.5 py-0.5 rounded bg-surface text-text-secondary text-[10px] font-mono border border-border-subtle">
                                          {f}
                                        </code>
                                      ))}
                                    </div>
                                  </div>
                                )}
                                {task.notes && (
                                  <div>
                                    <span className="text-text-muted font-mono block mb-0.5">Notes</span>
                                    <p className="text-text-secondary whitespace-pre-wrap">{task.notes}</p>
                                  </div>
                                )}
                                {task.depends_on && task.depends_on.length > 0 && (
                                  <div>
                                    <span className="text-text-muted font-mono block mb-0.5">Dependencies</span>
                                    <div className="flex flex-wrap gap-1">
                                      {task.depends_on.map((dep) => (
                                        <span key={dep} className="px-1.5 py-0.5 rounded bg-surface text-text-muted text-[10px] font-mono border border-border-subtle">
                                          {dep}
                                        </span>
                                      ))}
                                    </div>
                                  </div>
                                )}
                                {task.completed_at && (
                                  <div>
                                    <span className="text-text-muted font-mono block mb-0.5">Completed</span>
                                    <span className="text-text-secondary font-mono">{task.completed_at}</span>
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  );
                });
            })()}
          </>
        ) : Object.entries(byCategory)
          .sort(([a], [b]) => a.localeCompare(b))
          .map(([category, catTasks]) => {
            const catDone = catTasks.filter(
              (t: Task) => t.status === "completed" || t.status === "done"
            ).length;
            return (
              <div key={category}>
                {/* Category header */}
                <div className="sticky top-0 px-3 py-1.5 bg-surface-raised/80 backdrop-blur-sm border-b border-border-subtle">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-text-secondary uppercase tracking-wider">
                      {category}
                    </span>
                    <span className="text-xs text-text-muted font-mono">
                      {catDone}/{catTasks.length}
                    </span>
                  </div>
                </div>
                {/* Tasks in category */}
                {catTasks.map((task: Task) => {
                  const isExpanded = expandedTask === task.id;
                  const isVerifyExpanded = verificationDetailTask === task.id;
                  const isRetrying = task.verification_status === "retrying";
                  return (
                    <div key={task.id}>
                      <div
                        onClick={() => setExpandedTask(isExpanded ? null : task.id)}
                        className={`px-3 py-2 border-b border-border-subtle/50 hover:bg-surface-raised/50 transition-colors cursor-pointer ${task.status === "completed" || task.status === "done" ? "opacity-60" : ""
                          } ${isRetrying ? "ring-1 ring-warning/60 animate-pulse" : ""}`}
                      >
                        <div className="flex items-start gap-2">
                          <StatusBadge status={task.status} />
                          <div className="flex-1 min-w-0">
                            <div className="text-sm text-text-primary truncate flex items-center">
                              {task.title}
                              <ExternalLinkBadge task={task} />
                            </div>
                            {task.id && (
                              <span className="text-xs text-text-muted font-mono">
                                {task.id}
                              </span>
                            )}
                          </div>
                          <div className="flex items-center gap-1.5">
                            <VerificationBadge
                              task={task}
                              onClick={() =>
                                setVerificationDetailTask(
                                  isVerifyExpanded ? null : task.id
                                )
                              }
                              isExpanded={isVerifyExpanded}
                            />
                            {task.priority && (
                              <span className="text-xs text-text-muted font-mono">
                                P{task.priority}
                              </span>
                            )}
                            <span className={`text-[10px] text-text-muted transition-transform ${isExpanded ? "rotate-90" : ""}`}>
                              &#9656;
                            </span>
                          </div>
                        </div>
                      </div>

                      {/* Expanded detail section (Wave 3.3) */}
                      {isExpanded && (
                        <div className="px-4 py-2.5 bg-surface-raised/30 border-b border-border-subtle/50 text-xs space-y-2">
                          {task.description && (
                            <div>
                              <span className="text-text-muted font-mono block mb-0.5">Description</span>
                              <p className="text-text-secondary whitespace-pre-wrap">{task.description}</p>
                            </div>
                          )}
                          {task.acceptance_criteria && task.acceptance_criteria.length > 0 && (
                            <div>
                              <span className="text-text-muted font-mono block mb-0.5">Acceptance Criteria</span>
                              <ul className="list-disc list-inside text-text-secondary space-y-0.5">
                                {task.acceptance_criteria.map((ac, i) => (
                                  <li key={i}>{ac}</li>
                                ))}
                              </ul>
                            </div>
                          )}
                          {task.files_affected && task.files_affected.length > 0 && (
                            <div>
                              <span className="text-text-muted font-mono block mb-0.5">Files Affected</span>
                              <div className="flex flex-wrap gap-1">
                                {task.files_affected.map((f, i) => (
                                  <code key={i} className="px-1.5 py-0.5 rounded bg-surface text-text-secondary text-[10px] font-mono border border-border-subtle">
                                    {f}
                                  </code>
                                ))}
                              </div>
                            </div>
                          )}
                          {task.notes && (
                            <div>
                              <span className="text-text-muted font-mono block mb-0.5">Notes</span>
                              <p className="text-text-secondary whitespace-pre-wrap">{task.notes}</p>
                            </div>
                          )}
                          {task.depends_on && task.depends_on.length > 0 && (
                            <div>
                              <span className="text-text-muted font-mono block mb-0.5">Dependencies</span>
                              <div className="flex flex-wrap gap-1">
                                {task.depends_on.map((dep) => (
                                  <span key={dep} className="px-1.5 py-0.5 rounded bg-surface text-text-muted text-[10px] font-mono border border-border-subtle">
                                    {dep}
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}
                          {task.completed_at && (
                            <div>
                              <span className="text-text-muted font-mono block mb-0.5">Completed</span>
                              <span className="text-text-secondary font-mono">{task.completed_at}</span>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            );
          })}
      </div>
    </div>
  );
}
