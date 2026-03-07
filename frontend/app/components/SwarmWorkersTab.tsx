"use client";

import { useState, useEffect, useCallback } from "react";
import { TriagePanel, type TriageResult } from "./TriagePanel";
import { ConfirmModal } from "./ConfirmModal";

interface WorkerState {
  worker_id: number;
  worktree_path: string;
  branch_name: string;
  status: string;
  current_task: string | null;
  completed_tasks: string[];
  error: string | null;
  pid: number | null;
  depth: number;
  file_scope: string[];
  capability?: "scout" | "builder" | "reviewer" | "lead" | "coordinator" | "monitor" | "merger";
  parent_worker_id?: number;
  // Agent Identity (F14)
  sessions_completed?: number;
  expertise_domains?: string[];
  // Multi-runtime
  runtime?: string;
  // Quality gates
  quality_gate_report?: {
    worker_id: number;
    passed: boolean;
    gates: { name: string; passed: boolean; detail: string }[];
  } | null;
}

interface WatchdogWorkerHealth {
  worker_id: number;
  status: string;
  last_output_ago_seconds: number;
  escalation_level: number;
  warnings: string[];
  // Nudge/Triage Events (F12)
  nudge_events?: NudgeTriageEvent[];
}

interface NudgeTriageEvent {
  type: "nudge" | "triage";
  verdict?: "retry" | "extend" | "terminate";
  message?: string;
  timestamp?: string;
}

interface DispatchOverrideEntry {
  directive: string;
  value?: string | null;
  active: boolean;
}

export interface SwarmWorkersTabProps {
  workers: WorkerState[];
  numWorkers: number;
  maxDepth: number;
  healthData: Record<string, WatchdogWorkerHealth>;
  projectDir: string;
  workersView: "list" | "hierarchy";
  setWorkersView: (view: "list" | "hierarchy") => void;
  getWorkerOutput: (workerId: number) => string[];
  getWorkerRole: (worker: WorkerState) => string;
  overrides?: DispatchOverrideEntry[];
  swarmRuntime?: string;
  triageResults?: Record<number, TriageResult>;
  onTriageAccept?: (workerId: number, verdict: string) => void;
  onTriageOverride?: (workerId: number, action: string) => void;
}

const WORKER_STATUS_COLORS: Record<string, string> = {
  idle: "text-text-muted bg-surface border-border-subtle",
  working: "text-accent bg-accent/10 border-accent/30",
  completed: "text-success bg-success/10 border-success/30",
  error: "text-error bg-error/10 border-error/30",
  merging: "text-warning bg-warning/10 border-warning/30",
  rework: "text-orange-400 bg-orange-400/10 border-orange-400/30",
};

const WORKER_STATUS_ICONS: Record<string, string> = {
  idle: "\u25CB",
  working: "\u25B6",
  completed: "\u2713",
  error: "\u2717",
  merging: "\u21BB",
  rework: "\u21BA",
};

const ROLE_COLORS: Record<string, string> = {
  builder: "text-accent bg-accent/10 border-accent/30",
  reviewer: "text-info bg-info/10 border-info/30",
  scout: "text-warning bg-warning/10 border-warning/30",
  merger: "text-purple-400 bg-purple-400/10 border-purple-400/30",
};

const HEALTH_COLORS: Record<string, string> = {
  healthy: "bg-success",
  warning: "bg-warning",
  stalled: "bg-error animate-pulse",
  dead: "bg-error",
  terminated: "bg-text-muted",
};

const TRIAGE_VERDICT_COLORS: Record<string, string> = {
  retry: "text-accent bg-accent/10 border-accent/20",
  extend: "text-warning bg-warning/10 border-warning/20",
  terminate: "text-error bg-error/10 border-error/20",
};

const TRIAGE_VERDICT_ICONS: Record<string, string> = {
  retry: "\u21BB",
  extend: "\u23F0",
  terminate: "\u2718",
};

const CAPABILITY_COLORS: Record<string, string> = {
  scout: "text-warning bg-warning/10 border-warning/30",
  builder: "text-accent bg-accent/10 border-accent/30",
  reviewer: "text-info bg-info/10 border-info/30",
  lead: "text-purple-400 bg-purple-400/10 border-purple-400/30",
  coordinator: "text-purple-400 bg-purple-400/10 border-purple-400/30",
  monitor: "text-text-muted bg-surface border-border-subtle",
  merger: "text-purple-400 bg-purple-400/10 border-purple-400/30",
};

const CAPABILITY_ICONS: Record<string, string> = {
  scout: "\u{1F50D}",      // magnifying glass (read-only)
  builder: "\u{1F527}",    // wrench
  reviewer: "\u{1F512}",   // lock (read-only)
  lead: "\u{1F451}",       // crown
  coordinator: "\u{1F451}",
  monitor: "\u{1F4CA}",    // chart
  merger: "\u{1F500}",     // shuffle (merge)
};

const RUNTIME_BORDER_COLORS: Record<string, string> = {
  claude: "border-accent/40",
  codex: "border-green-400/40",
  gemini: "border-blue-400/40",
  local: "border-yellow-400/40",
};

// Map file extensions to expertise domains (mirrors backend FILE_DOMAIN_MAP)
function inferDomainsFromScope(fileScope: string[]): string[] {
  const domainMap: Record<string, string> = {
    ".py": "python", ".ts": "typescript", ".tsx": "typescript",
    ".js": "javascript", ".jsx": "javascript", ".rs": "rust",
    ".go": "golang", ".java": "java", ".sql": "database",
    ".prisma": "database", ".css": "styling", ".scss": "styling",
    ".html": "frontend", ".vue": "frontend", ".svelte": "frontend",
    ".yml": "devops", ".yaml": "devops",
  };
  const domains = new Set<string>();
  for (const f of fileScope) {
    const lower = f.toLowerCase();
    for (const [ext, domain] of Object.entries(domainMap)) {
      if (lower.endsWith(ext)) domains.add(domain);
    }
    if (lower.includes("test") || lower.includes("spec") || lower.includes("__tests__")) {
      domains.add("testing");
    }
    if (lower.includes("dockerfile") || lower.includes("docker-compose") || lower.includes(".github")) {
      domains.add("devops");
    }
  }
  return Array.from(domains).sort();
}

const EXPERTISE_DOMAIN_COLORS: Record<string, string> = {
  python: "text-[#3572A5] border-[#3572A5]/30",
  typescript: "text-[#3178c6] border-[#3178c6]/30",
  javascript: "text-[#f1e05a] border-[#f1e05a]/30",
  rust: "text-[#dea584] border-[#dea584]/30",
  golang: "text-[#00ADD8] border-[#00ADD8]/30",
  database: "text-[#e38c00] border-[#e38c00]/30",
  testing: "text-success border-success/30",
  frontend: "text-info border-info/30",
  devops: "text-warning border-warning/30",
  styling: "text-[#ff69b4] border-[#ff69b4]/30",
};

export function SwarmWorkersTab({
  workers,
  numWorkers,
  maxDepth,
  healthData,
  projectDir,
  workersView,
  setWorkersView,
  getWorkerOutput,
  getWorkerRole,
  overrides,
  swarmRuntime,
  triageResults,
  onTriageAccept,
  onTriageOverride,
}: SwarmWorkersTabProps) {
  const activeOverrides = overrides?.filter((o) => o.active) ?? [];

  // Nudge protocol state
  const [nudgeCooldowns, setNudgeCooldowns] = useState<Record<number, number>>({});
  const [nudgeInputOpen, setNudgeInputOpen] = useState<Record<number, boolean>>({});
  const [nudgeInputText, setNudgeInputText] = useState<Record<number, string>>({});
  const [toasts, setToasts] = useState<{ id: number; message: string; type: "success" | "error" }[]>([]);
  const [terminateConfirm, setTerminateConfirm] = useState<{ workerId: number; pid: number } | null>(null);

  // Tick cooldown countdown every second
  useEffect(() => {
    const interval = setInterval(() => {
      const now = Date.now();
      setNudgeCooldowns((prev) => {
        const next = { ...prev };
        let changed = false;
        for (const k of Object.keys(next)) {
          if (next[Number(k)] <= now) { delete next[Number(k)]; changed = true; }
        }
        return changed ? next : prev;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  // Auto-dismiss toasts after 4s
  useEffect(() => {
    if (toasts.length === 0) return;
    const timer = setTimeout(() => setToasts((prev) => prev.slice(1)), 4000);
    return () => clearTimeout(timer);
  }, [toasts]);

  const showToast = useCallback((msg: string, type: "success" | "error" = "success") => {
    setToasts((prev) => [...prev, { id: Date.now(), message: msg, type }]);
  }, []);

  const isOnCooldown = useCallback(
    (wid: number) => (nudgeCooldowns[wid] ?? 0) > Date.now(),
    [nudgeCooldowns],
  );

  const getCooldownSeconds = useCallback(
    (wid: number) => Math.max(0, Math.ceil(((nudgeCooldowns[wid] ?? 0) - Date.now()) / 1000)),
    [nudgeCooldowns],
  );

  const handleNudge = useCallback(async (wid: number, message: string = "") => {
    if (isOnCooldown(wid)) return;
    try {
      const res = await fetch(`/api/swarm/workers/${wid}/nudge`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: projectDir, message: message || "Please report progress.", steering_type: "instruction" }),
      });
      const data = await res.json();
      setNudgeCooldowns((prev) => ({ ...prev, [wid]: Date.now() + 30000 }));
      setNudgeInputOpen((prev) => ({ ...prev, [wid]: false }));
      setNudgeInputText((prev) => ({ ...prev, [wid]: "" }));
      if (data.success) {
        showToast(`Nudge sent to Worker ${wid} via ${data.method}`);
      } else {
        showToast(`Nudge failed for Worker ${wid} - no tmux pane or steering path found`, "error");
      }
    } catch {
      showToast(`Nudge failed for Worker ${wid} - network error`, "error");
    }
  }, [projectDir, isOnCooldown, showToast]);

  return (
    <>
    {/* Toast notifications */}
    {toasts.length > 0 && (
      <div className="fixed bottom-4 right-4 z-50 space-y-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`text-[11px] font-mono px-3 py-2 rounded-lg border shadow-lg ${
              t.type === "error" ? "bg-error/10 border-error/30 text-error" : "bg-success/10 border-success/30 text-success"
            }`}
          >
            {t.message}
          </div>
        ))}
      </div>
    )}
    <div className="p-3 space-y-3">
      {/* View toggle: List vs Hierarchy */}
      <div className="flex items-center gap-2 mb-1">
        <button
          onClick={() => setWorkersView("list")}
          className={`text-[10px] font-mono px-2 py-1 rounded border transition-colors ${
            workersView === "list"
              ? "text-accent border-accent/30 bg-accent/10"
              : "text-text-muted border-border-subtle hover:text-text-secondary"
          }`}
        >
          List
        </button>
        <button
          onClick={() => setWorkersView("hierarchy")}
          className={`text-[10px] font-mono px-2 py-1 rounded border transition-colors ${
            workersView === "hierarchy"
              ? "text-accent border-accent/30 bg-accent/10"
              : "text-text-muted border-border-subtle hover:text-text-secondary"
          }`}
        >
          Hierarchy
        </button>
      </div>

      {/* Hierarchy tree view */}
      {workersView === "hierarchy" && (() => {
        // Build parent-child tree
        const roots = workers.filter((w) => !w.parent_worker_id);
        const children = (parentId: number) =>
          workers.filter((w) => w.parent_worker_id === parentId);

        const renderNode = (worker: WorkerState, indent: number) => {
          const role = worker.capability || getWorkerRole(worker);
          const health = healthData[String(worker.worker_id)];
          const kids = children(worker.worker_id);
          return (
            <div key={worker.worker_id}>
              <div
                className="flex items-center gap-2 py-1.5 px-2 rounded hover:bg-surface-raised/50"
                style={{ paddingLeft: `${indent * 20 + 8}px` }}
              >
                {/* Tree connector */}
                {indent > 0 && (
                  <span className="text-border-subtle text-[10px]">{"\u2514"}</span>
                )}
                {/* Health dot */}
                {health && (
                  <span className={`w-2 h-2 rounded-full shrink-0 ${HEALTH_COLORS[health.status] || "bg-text-muted"}`} />
                )}
                {/* Capability icon */}
                <span className="text-xs" title={role}>
                  {CAPABILITY_ICONS[role] || "\u25CB"}
                </span>
                {/* Worker name */}
                <span className={`text-xs font-mono ${
                  WORKER_STATUS_COLORS[worker.status]?.split(" ")[0] || "text-text-primary"
                }`}>
                  W{worker.worker_id}
                </span>
                {/* Capability badge */}
                <span className={`text-[9px] font-mono px-1 py-0.5 rounded border ${
                  CAPABILITY_COLORS[role] || ROLE_COLORS[role] || ROLE_COLORS.builder
                }`}>
                  {role}
                </span>
                {/* Status */}
                <span className="text-[9px] text-text-muted font-mono">
                  {worker.status}
                </span>
                {/* Current task */}
                {worker.current_task && (
                  <span className="text-[9px] text-accent font-mono truncate max-w-[150px]" title={worker.current_task}>
                    {worker.current_task}
                  </span>
                )}
              </div>
              {kids.map((child) => renderNode(child, indent + 1))}
            </div>
          );
        };

        return (
          <div className="rounded-lg border border-border-subtle bg-surface-raised p-2">
            <div className="text-[10px] text-text-muted font-mono mb-2 uppercase tracking-wider">
              Agent Hierarchy (depth {maxDepth})
            </div>
            {roots.length > 0 ? (
              roots.map((w) => renderNode(w, 0))
            ) : (
              // If no parent info, show flat list as roots
              workers.map((w) => renderNode(w, 0))
            )}
          </div>
        );
      })()}

      {/* List view */}
      {workersView === "list" && workers.map((worker) => {
        const workerOutput = getWorkerOutput(worker.worker_id);
        const role = getWorkerRole(worker);
        const health = healthData[String(worker.worker_id)];
        const triage = triageResults?.[worker.worker_id];
        const isStalled = health?.status === "stalled";
        return (
          <div
            key={worker.worker_id}
            className={`rounded-lg border bg-surface-raised overflow-hidden ${
              isStalled ? "border-warning/50" : "border-border-subtle"
            }`}
          >
            {/* Worker header */}
            <div className="flex items-center justify-between px-3 py-2 border-b border-border-subtle/50 flex-wrap gap-y-1">
              <div className="flex items-center gap-2">
                {/* Health dot */}
                {health && (
                  <span
                    className={`w-2 h-2 rounded-full ${HEALTH_COLORS[health.status] || "bg-text-muted"}`}
                    role="status"
                    aria-label={`Worker ${worker.worker_id} health: ${health.status}`}
                    title={`Health: ${health.status}${health.last_output_ago_seconds >= 0 ? ` (${health.last_output_ago_seconds}s ago)` : ""}`}
                  />
                )}
                <span
                  className={`text-xs font-mono px-1.5 py-0.5 rounded border ${
                    WORKER_STATUS_COLORS[worker.status] || ""
                  }`}
                  aria-label={`Worker ${worker.worker_id} status: ${worker.status}`}
                >
                  {WORKER_STATUS_ICONS[worker.status] || "\u25CB"}{" "}
                  Worker {worker.worker_id}
                </span>
                {/* Role / Capability badge */}
                <span
                  className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${
                    (worker.capability ? CAPABILITY_COLORS[worker.capability] : null) || ROLE_COLORS[role] || ROLE_COLORS.builder
                  }`}
                >
                  {worker.capability || role}
                </span>
                {/* Runtime badge */}
                {(() => {
                  const rt = worker.runtime || swarmRuntime || "claude";
                  const borderColor = RUNTIME_BORDER_COLORS[rt] || "border-border-subtle";
                  return (
                    <span
                      className={`text-[9px] font-mono px-1 py-0.5 rounded border ${borderColor} text-text-muted bg-surface/50`}
                      title={`Runtime: ${rt}`}
                    >
                      {rt}
                    </span>
                  );
                })()}
                <span className="text-xs text-text-muted font-mono">
                  {worker.status}
                </span>
                {/* Dispatch override pills */}
                {activeOverrides.length > 0 && activeOverrides.map((ov) => (
                  <span
                    key={ov.directive}
                    className="text-[9px] font-mono px-1 py-0.5 rounded border text-info bg-info/10 border-info/20"
                    title={ov.value ? `${ov.directive} = ${ov.value}` : ov.directive}
                  >
                    {ov.directive.replace(/_/g, " ")}
                  </span>
                ))}
              </div>
              <div className="flex items-center gap-2">
                {/* Escalation level badge */}
                {health && health.escalation_level > 0 && (
                  <span
                    className={`text-[10px] font-mono px-1 py-0.5 rounded border ${
                      health.escalation_level >= 3
                        ? "text-error bg-error/10 border-error/20"
                        : health.escalation_level >= 2
                          ? "text-warning bg-warning/10 border-warning/20"
                          : "text-info bg-info/10 border-info/20"
                    }`}
                    title={`Escalation level: ${health.escalation_level}`}
                  >
                    E{health.escalation_level}
                  </span>
                )}
                {/* Stalled indicator (pulsing amber) */}
                {isStalled && (
                  <span
                    className="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded border text-warning bg-warning/10 border-warning/30 animate-pulse"
                    title="Worker is stalled - AI triage active"
                  >
                    STALLED
                  </span>
                )}
                {/* Stale indicator (only when not already stalled) */}
                {health && health.last_output_ago_seconds > 120 && worker.status === "working" && !isStalled && (
                  <span className="text-[10px] text-error font-mono animate-pulse" title="Worker stale (>120s since last output)">
                    STALE
                  </span>
                )}
                {worker.depth > 1 && (
                  <span className="text-[10px] text-text-muted font-mono" title="Worker depth">
                    d{worker.depth}
                  </span>
                )}
                {worker.pid && (
                  <span className="text-[10px] text-text-muted font-mono">
                    PID {worker.pid}
                  </span>
                )}
                {/* Nudge control group */}
                {worker.status === "working" && (
                  <div className="flex items-center gap-1">
                    {isOnCooldown(worker.worker_id) ? (
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded border border-border-subtle text-text-muted">
                        Cooling down... {getCooldownSeconds(worker.worker_id)}s
                      </span>
                    ) : (
                      <>
                        <button
                          onClick={() => handleNudge(worker.worker_id)}
                          className="text-[10px] font-mono px-1.5 py-0.5 rounded border border-info/30 text-info hover:bg-info/10 transition-colors"
                          title="Gentle nudge (empty Enter keystroke via tmux)"
                        >
                          Nudge
                        </button>
                        <button
                          onClick={() => setNudgeInputOpen((prev) => ({ ...prev, [worker.worker_id]: !prev[worker.worker_id] }))}
                          className={`text-[10px] font-mono px-1.5 py-0.5 rounded border transition-colors ${
                            nudgeInputOpen[worker.worker_id]
                              ? "border-accent/30 text-accent bg-accent/10"
                              : "border-info/30 text-info hover:bg-info/10"
                          }`}
                          title="Send a custom message nudge"
                        >
                          Msg
                        </button>
                      </>
                    )}
                  </div>
                )}
                {/* Terminate button */}
                {worker.status === "working" && worker.pid && (
                  <button
                    onClick={() => setTerminateConfirm({ workerId: worker.worker_id, pid: worker.pid! })}
                    className="text-[10px] font-mono px-1.5 py-0.5 rounded border border-error/30 text-error hover:bg-error/10 transition-colors"
                    title="Terminate this worker"
                  >
                    Kill
                  </button>
                )}
              </div>
            </div>

            {/* Message nudge input */}
            {nudgeInputOpen[worker.worker_id] && worker.status === "working" && !isOnCooldown(worker.worker_id) && (
              <div className="px-3 py-1.5 bg-info/5 border-b border-info/20 flex items-center gap-2">
                <input
                  type="text"
                  value={nudgeInputText[worker.worker_id] || ""}
                  onChange={(e) => setNudgeInputText((prev) => ({ ...prev, [worker.worker_id]: e.target.value }))}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && nudgeInputText[worker.worker_id]?.trim()) {
                      handleNudge(worker.worker_id, nudgeInputText[worker.worker_id].trim());
                    }
                  }}
                  placeholder="Custom nudge message..."
                  className="flex-1 text-[10px] font-mono bg-surface border border-border-subtle rounded px-2 py-1 text-text-primary placeholder:text-text-muted/50 focus:outline-none focus:border-info/50"
                />
                <button
                  onClick={() => {
                    if (nudgeInputText[worker.worker_id]?.trim()) {
                      handleNudge(worker.worker_id, nudgeInputText[worker.worker_id].trim());
                    }
                  }}
                  disabled={!nudgeInputText[worker.worker_id]?.trim()}
                  className="text-[10px] font-mono px-2 py-1 rounded border border-info/30 text-info hover:bg-info/10 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Send
                </button>
              </div>
            )}

            {/* AI Triage Panel - shown when triage result available for stalled worker */}
            {triage && isStalled && (
              <TriagePanel
                triage={triage}
                recentOutput={workerOutput}
                onAccept={() => onTriageAccept?.(worker.worker_id, triage.verdict)}
                onOverride={(action) => onTriageOverride?.(worker.worker_id, action)}
              />
            )}

            {/* Agent Identity (F14) */}
            {(worker.sessions_completed != null || (worker.expertise_domains && worker.expertise_domains.length > 0)) && (
              <div className="px-3 py-1 bg-accent/5 border-b border-border-subtle/30">
                <span className="text-[10px] text-text-secondary font-mono">
                  {worker.sessions_completed != null && (
                    <>{worker.sessions_completed} session{worker.sessions_completed !== 1 ? "s" : ""}</>
                  )}
                  {worker.sessions_completed != null && worker.expertise_domains && worker.expertise_domains.length > 0 && " | "}
                  {worker.expertise_domains && worker.expertise_domains.length > 0 && (
                    <>{worker.expertise_domains.join(", ")}</>
                  )}
                </span>
              </div>
            )}
            {/* Agent Identity fallback when data not yet available */}
            {worker.sessions_completed == null && (!worker.expertise_domains || worker.expertise_domains.length === 0) && worker.status === "working" && (
              <div className="px-3 py-1 bg-surface/30 border-b border-border-subtle/30">
                <span className="text-[10px] text-text-muted font-mono italic">
                  Identity: No data
                </span>
              </div>
            )}

            {/* File scope */}
            {worker.file_scope && worker.file_scope.length > 0 && (
              <div className="px-3 py-1.5 bg-surface/50 border-b border-border-subtle/30">
                <span className="text-[10px] text-text-muted font-mono">
                  Owns:{" "}
                  {worker.file_scope.length <= 3
                    ? worker.file_scope.join(", ")
                    : `${worker.file_scope.slice(0, 2).join(", ")} +${worker.file_scope.length - 2} more`}
                </span>
              </div>
            )}
            {/* Expertise Loaded badge */}
            {worker.file_scope && worker.file_scope.length > 0 && (() => {
              const loadedDomains = inferDomainsFromScope(worker.file_scope);
              if (loadedDomains.length === 0) return null;
              return (
                <div className="px-3 py-1 bg-accent/3 border-b border-border-subtle/30 flex items-center gap-1.5 flex-wrap">
                  <span className="text-[9px] text-text-muted font-mono uppercase tracking-wider shrink-0">
                    Expertise:
                  </span>
                  {loadedDomains.map((d) => (
                    <span
                      key={d}
                      className={`text-[9px] font-mono px-1 py-0.5 rounded border bg-surface/50 ${
                        EXPERTISE_DOMAIN_COLORS[d] || "text-text-muted border-border-subtle"
                      }`}
                      title={`Pre-loaded ${d} expertise from global memory + project knowledge base`}
                    >
                      {d}
                    </span>
                  ))}
                </div>
              );
            })()}

            {/* Current task / error */}
            {worker.current_task && (
              <div className="px-3 py-1.5 text-xs text-accent font-mono bg-accent/5">
                {"\u25B6"} {worker.current_task}
              </div>
            )}
            {worker.error && (
              <div className="px-3 py-1.5 text-xs text-error bg-error/5">
                {worker.error}
              </div>
            )}

            {/* Quality Gates */}
            {worker.quality_gate_report && (
              <div className={`px-3 py-2 border-t ${worker.quality_gate_report.passed ? "bg-success/5 border-success/20" : "bg-orange-400/5 border-orange-400/20"}`}>
                <div className="text-[10px] font-mono font-medium mb-1 uppercase tracking-wider text-text-muted">
                  Quality Gates
                </div>
                <div className="flex flex-wrap gap-2">
                  {worker.quality_gate_report.gates.map((gate) => {
                    const label = gate.name === "tests_pass" ? "Tests"
                      : gate.name === "no_uncommitted" ? "Clean"
                      : gate.name === "tasks_updated" ? "Tasks Updated"
                      : gate.name === "no_conflicts" ? "No Conflicts"
                      : gate.name;
                    return (
                      <span
                        key={gate.name}
                        className={`text-[10px] font-mono px-1.5 py-0.5 rounded border inline-flex items-center gap-1 ${
                          gate.passed
                            ? "text-success bg-success/10 border-success/20"
                            : "text-error bg-error/10 border-error/20"
                        }`}
                        title={gate.detail}
                      >
                        {gate.passed ? "\u2713" : "\u2717"} {label}
                      </span>
                    );
                  })}
                </div>
                {/* Show failed gate details */}
                {worker.quality_gate_report.gates.filter((g) => !g.passed).map((gate) => (
                  <div key={gate.name} className="mt-1 text-[10px] text-error font-mono truncate" title={gate.detail}>
                    {gate.detail}
                  </div>
                ))}
              </div>
            )}

            {/* Watchdog warnings + Nudge/Triage Events (F12) */}
            {health && health.warnings && health.warnings.length > 0 && (
              <div className="px-3 py-1.5 bg-warning/5 border-t border-warning/20">
                {health.warnings.slice(-3).map((warn, i) => (
                  <div key={i} className="text-[10px] text-warning font-mono">
                    {"\u26A0"} {warn}
                  </div>
                ))}
              </div>
            )}
            {/* Nudge/Triage Events (F12) */}
            {health && health.nudge_events && health.nudge_events.length > 0 && (
              <div className="px-3 py-1.5 bg-surface/50 border-t border-border-subtle/30 space-y-1">
                {health.nudge_events.slice(-3).map((evt, i) => (
                  <div key={i} className="flex items-center gap-1.5">
                    <span
                      className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${
                        evt.type === "triage" && evt.verdict
                          ? TRIAGE_VERDICT_COLORS[evt.verdict] || "text-text-muted bg-surface border-border-subtle"
                          : "text-info bg-info/10 border-info/20"
                      }`}
                    >
                      {evt.type === "triage" && evt.verdict
                        ? `${TRIAGE_VERDICT_ICONS[evt.verdict] || ""} ${evt.verdict}`
                        : "\u{1F4E2} nudge"}
                    </span>
                    {evt.message && (
                      <span className="text-[10px] text-text-muted font-mono truncate">
                        {evt.message}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
            {/* Nudge/Triage fallback when no events */}
            {health && (!health.nudge_events || health.nudge_events.length === 0) && health.escalation_level > 0 && (
              <div className="px-3 py-1 bg-surface/30 border-t border-border-subtle/30">
                <span className="text-[10px] text-text-muted font-mono italic">
                  Escalation level {health.escalation_level} - no triage events
                </span>
              </div>
            )}

            {/* Mini terminal */}
            {workerOutput.length > 0 && (
              <div className="px-3 py-2 max-h-24 overflow-y-auto">
                {workerOutput.map((line, i) => (
                  <div
                    key={i}
                    className="text-[10px] text-text-muted font-mono truncate leading-relaxed"
                  >
                    {line}
                  </div>
                ))}
              </div>
            )}

            {/* Capability enforcement display */}
            {worker.capability && (
              <div className="px-3 py-1 bg-surface/30 border-b border-border-subtle/30 flex items-center gap-2">
                <span className="text-xs" title={worker.capability}>
                  {CAPABILITY_ICONS[worker.capability] || "\u25CB"}
                </span>
                <span className={`text-[10px] font-mono px-1 py-0.5 rounded border ${
                  CAPABILITY_COLORS[worker.capability] || ""
                }`}>
                  {worker.capability}
                </span>
                {(worker.capability === "scout" || worker.capability === "reviewer") && (
                  <span className="text-[9px] text-text-muted font-mono italic">read-only</span>
                )}
                {worker.capability === "builder" && worker.file_scope && worker.file_scope.length > 0 && (
                  <span className="text-[9px] text-text-muted font-mono italic">
                    scoped to {worker.file_scope.length} file{worker.file_scope.length !== 1 ? "s" : ""}
                  </span>
                )}
                {worker.capability === "merger" && (
                  <span className="text-[9px] text-text-muted font-mono italic">
                    {worker.status === "working" ? "Waiting for merges" : worker.status === "merging" ? "Merging..." : "merge agent"}
                  </span>
                )}
              </div>
            )}

            {/* Completed tasks count */}
            {worker.completed_tasks && worker.completed_tasks.length > 0 && (
              <div className="px-3 py-1.5 border-t border-border-subtle/30 text-xs text-text-muted">
                {worker.completed_tasks.length} task
                {worker.completed_tasks.length !== 1 ? "s" : ""} completed
              </div>
            )}
          </div>
        );
      })}
    </div>

    <ConfirmModal
      open={!!terminateConfirm}
      title="Terminate worker"
      message={
        terminateConfirm
          ? `Terminate worker ${terminateConfirm.workerId} (PID ${terminateConfirm.pid})?`
          : ""
      }
      confirmLabel="Terminate"
      cancelLabel="Cancel"
      variant="danger"
      onConfirm={async () => {
        if (!terminateConfirm) return;
        const { workerId } = terminateConfirm;
        setTerminateConfirm(null);
        try {
          await fetch(`/api/swarm/workers/${workerId}/terminate?path=${encodeURIComponent(projectDir)}`, { method: "POST" });
        } catch {}
      }}
      onCancel={() => setTerminateConfirm(null)}
    />
    </>
  );
}
