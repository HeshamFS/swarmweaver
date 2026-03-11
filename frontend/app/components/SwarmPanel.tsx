"use client";

import { useState, useEffect } from "react";
import type { TriageResult } from "../hooks/useWebSocket";
import { SwarmWorkersTab, type LspWorkerDiagnostics } from "./SwarmWorkersTab";
import { SwarmMailTab } from "./SwarmMailTab";
import { SwarmMergesTab } from "./SwarmMergesTab";
import { WatchdogPanel } from "./WatchdogPanel";

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
  // Merge info
  merge_tier?: string | number;
  // Quality gates
  quality_gate_report?: {
    worker_id: number;
    passed: boolean;
    gates: { name: string; passed: boolean; detail: string }[];
  } | null;
}

interface MailMessage {
  id: string;
  sender: string;
  recipient: string;
  msg_type: string;
  subject: string;
  body: string;
  priority: string;
  read: boolean;
  created_at: string;
  thread_id?: string;
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

interface MergeInfo {
  worker_id: number;
  branch: string;
  tier?: number;
  tier_name?: string;
  details?: string;
  error?: string;
  files_conflicted?: string[];
}

interface MergeQueueEntry {
  id: string;
  worker_id: number;
  branch: string;
  status: "pending" | "merging" | "merged" | "failed" | "conflict";
  resolution_tier: number;
  created_at: string;
  resolved_at?: string;
  error?: string;
  files_changed?: number;
}

interface MergeQueueStats {
  total: number;
  pending: number;
  merged: number;
  failed: number;
}

interface ConflictPrediction {
  predicted_files: string[];
  confidence?: number;
}

interface WatchdogEventData {
  id?: string;
  timestamp: string;
  event_type: string;
  worker_id: number;
  message: string;
  escalation_level?: number;
  state_before?: string;
  state_after?: string;
  triage_verdict?: string;
  metadata?: Record<string, unknown>;
}

interface CircuitBreakerStatusData {
  state: "closed" | "open" | "half_open";
  failure_rate: number;
  failures_in_window: number;
  successes_in_window: number;
}

interface SwarmPanelProps {
  projectDir: string;
  output: string[];
  triageResults?: Record<number, TriageResult>;
  mailVersion?: number;  // incremented on mail_received WS event for instant refresh
  watchdogEvents?: WatchdogEventData[];
  circuitBreakerStatus?: CircuitBreakerStatusData | null;
}

type SwarmTab = "workers" | "mail" | "merges" | "health";

export function SwarmPanel({ projectDir, output, triageResults, mailVersion, watchdogEvents, circuitBreakerStatus }: SwarmPanelProps) {
  const [workers, setWorkers] = useState<WorkerState[]>([]);
  const [numWorkers, setNumWorkers] = useState(0);
  const [maxDepth, setMaxDepth] = useState(2);
  const [swarmOverrides, setSwarmOverrides] = useState<{ directive: string; value?: string | null; active: boolean }[]>([]);
  const [swarmRuntime, setSwarmRuntime] = useState<string>("claude");
  const [mailMessages, setMailMessages] = useState<MailMessage[]>([]);
  const [mailStats, setMailStats] = useState<{ total: number; unread: number }>({ total: 0, unread: 0 });
  const [healthData, setHealthData] = useState<Record<string, WatchdogWorkerHealth>>({});
  const [mergeReport, setMergeReport] = useState<{ merged: MergeInfo[]; failed: MergeInfo[] }>({ merged: [], failed: [] });
  const [mergeQueue, setMergeQueue] = useState<MergeQueueEntry[]>([]);
  const [mergeQueueStats, setMergeQueueStats] = useState<MergeQueueStats>({ total: 0, pending: 0, merged: 0, failed: 0 });
  const [conflictPrediction, setConflictPrediction] = useState<ConflictPrediction | null>(null);
  const [lspWorkerDiagnostics, setLspWorkerDiagnostics] = useState<Record<number, LspWorkerDiagnostics>>({});
  const [activeTab, setActiveTab] = useState<SwarmTab>("workers");
  const [workersView, setWorkersView] = useState<"list" | "hierarchy">("list");

  // Poll swarm status, mail, health, merge queue, and LSP diagnostics
  useEffect(() => {
    if (!projectDir) return;
    const interval = setInterval(() => {
      fetchStatus();
      fetchMail();
      fetchHealth();
      fetchMergeQueue();
      fetchLspDiagnostics();
    }, 10000);
    fetchStatus();
    fetchMail();
    fetchHealth();
    fetchMergeQueue();
    fetchLspDiagnostics();
    return () => clearInterval(interval);
  }, [projectDir]);

  const fetchStatus = async () => {
    try {
      const res = await fetch(
        `/api/swarm/status?path=${encodeURIComponent(projectDir)}`
      );
      const data = await res.json();
      setWorkers(data.workers || []);
      setNumWorkers(data.num_workers || 0);
      setMaxDepth(data.max_depth || 2);
      setSwarmOverrides(data.overrides || []);
      setSwarmRuntime(data.runtime || "claude");
    } catch {
      // Ignore
    }
  };

  const fetchMail = async () => {
    try {
      const res = await fetch(
        `/api/swarm/mail?path=${encodeURIComponent(projectDir)}&limit=30`
      );
      const data = await res.json();
      setMailMessages(data.messages || []);
      setMailStats(data.stats || { total: 0, unread: 0 });
    } catch {
      // Ignore
    }
  };

  const fetchHealth = async () => {
    try {
      const res = await fetch(
        `/api/swarm/health?path=${encodeURIComponent(projectDir)}`
      );
      const data = await res.json();
      setHealthData(data.workers || {});
    } catch {
      // Ignore
    }
  };

  const fetchLspDiagnostics = async () => {
    try {
      const res = await fetch(
        `/api/lsp/diagnostics?path=${encodeURIComponent(projectDir)}`
      );
      const data = await res.json();
      const diagnostics: { uri: string; severity: number; worker_id?: number }[] = data.diagnostics || [];
      // Aggregate by worker: match file URIs against worker file_scope
      const perWorker: Record<number, LspWorkerDiagnostics> = {};
      for (const diag of diagnostics) {
        // If the API returns worker_id, use it directly
        if (diag.worker_id != null) {
          if (!perWorker[diag.worker_id]) perWorker[diag.worker_id] = { errors: 0, warnings: 0 };
          if (diag.severity === 1) perWorker[diag.worker_id].errors++;
          else if (diag.severity === 2) perWorker[diag.worker_id].warnings++;
          continue;
        }
        // Otherwise match against worker file_scope
        const diagPath = diag.uri?.replace(/^file:\/\//, "") || "";
        for (const w of workers) {
          if (!w.file_scope?.length) continue;
          const matches = w.file_scope.some((scope) => diagPath.includes(scope) || diagPath.endsWith(scope));
          if (matches) {
            if (!perWorker[w.worker_id]) perWorker[w.worker_id] = { errors: 0, warnings: 0 };
            if (diag.severity === 1) perWorker[w.worker_id].errors++;
            else if (diag.severity === 2) perWorker[w.worker_id].warnings++;
          }
        }
      }
      setLspWorkerDiagnostics(perWorker);
    } catch {
      // Ignore - LSP may not be active
    }
  };

  const fetchMergeQueue = async () => {
    try {
      const res = await fetch(
        `/api/swarm/merge-queue?path=${encodeURIComponent(projectDir)}`
      );
      const data = await res.json();
      setMergeQueue(data.entries || []);
      setMergeQueueStats(data.stats || { total: 0, pending: 0, merged: 0, failed: 0 });
    } catch {
      // Ignore - endpoint may not exist yet
    }
  };

  const markMailRead = async () => {
    try {
      await fetch(
        `/api/swarm/mail/read?path=${encodeURIComponent(projectDir)}&recipient=orchestrator`,
        { method: "POST" }
      );
      fetchMail();
    } catch {
      // Ignore
    }
  };

  // Instant mail refresh on WebSocket push (M2-1)
  useEffect(() => {
    if (mailVersion) fetchMail();
  }, [mailVersion]);

  // Filter output by worker prefix [W1], [W2], etc.
  const getWorkerOutput = (workerId: number): string[] => {
    const prefix = `[W${workerId}]`;
    return output
      .filter((line) => line.startsWith(prefix))
      .map((line) => line.substring(prefix.length).trim())
      .slice(-20);
  };

  // Derive merge info from worker states instead of parsing output lines
  useEffect(() => {
    const merged: MergeInfo[] = [];
    const failed: MergeInfo[] = [];
    for (const worker of workers) {
      if (worker.status === "merged") {
        // Worker was successfully merged by orchestrator
        const tierNum = typeof worker.merge_tier === "number"
          ? worker.merge_tier
          : typeof worker.merge_tier === "string"
            ? parseInt(worker.merge_tier, 10) || undefined
            : undefined;
        merged.push({
          worker_id: worker.worker_id,
          branch: worker.branch_name || `worker-${worker.worker_id}`,
          tier: tierNum,
          details: worker.completed_tasks?.length
            ? `${worker.completed_tasks.length} task(s) completed`
            : undefined,
        });
      } else if (worker.status === "completed") {
        // Worker finished but not yet merged — show as pending merge
        merged.push({
          worker_id: worker.worker_id,
          branch: worker.branch_name || `worker-${worker.worker_id}`,
          details: worker.completed_tasks?.length
            ? `${worker.completed_tasks.length} task(s) completed — awaiting merge`
            : "Awaiting merge",
        });
      } else if (worker.status === "error") {
        failed.push({
          worker_id: worker.worker_id,
          branch: worker.branch_name || `worker-${worker.worker_id}`,
          error: worker.error || "Unknown error",
        });
      }
    }
    if (merged.length > 0 || failed.length > 0) {
      setMergeReport({ merged, failed });
    }
  }, [workers]);

  // Derive conflict predictions from merge history and file scope overlap (F16)
  useEffect(() => {
    const predictedFiles: string[] = [];
    // From failed merges with conflicted files
    for (const fail of mergeReport.failed) {
      if (fail.files_conflicted) {
        for (const f of fail.files_conflicted) {
          if (!predictedFiles.includes(f)) predictedFiles.push(f);
        }
      }
    }
    // From file scope overlap between active workers
    const activeWorkers = workers.filter((w) => w.status === "working" || w.status === "merging");
    for (let i = 0; i < activeWorkers.length; i++) {
      for (let j = i + 1; j < activeWorkers.length; j++) {
        const scopeA = activeWorkers[i].file_scope || [];
        const scopeB = activeWorkers[j].file_scope || [];
        for (const f of scopeA) {
          if (scopeB.includes(f) && !predictedFiles.includes(f)) {
            predictedFiles.push(f);
          }
        }
      }
    }
    if (predictedFiles.length > 0) {
      setConflictPrediction({ predicted_files: predictedFiles });
    } else {
      setConflictPrediction(null);
    }
  }, [workers, mergeReport]);

  // Aggregate progress
  const totalCompleted = workers.reduce(
    (sum, w) => sum + (w.completed_tasks?.length || 0),
    0
  );
  const allDone = workers.every(
    (w) => w.status === "completed" || w.status === "error"
  );
  const hasErrors = workers.some((w) => w.status === "error");

  // Conflict detection from output
  const conflictLines = output.filter((l) => l.includes("[SWARM] Conflicts"));

  // Infer role from worker position
  const getWorkerRole = (worker: WorkerState): string => {
    if (numWorkers >= 3 && worker.worker_id === numWorkers) return "reviewer";
    return "builder";
  };

  if (workers.length === 0 && numWorkers === 0) {
    return (
      <div className="flex flex-col h-full">
        <div className="flex-1 flex items-center justify-center p-4">
          <span className="text-sm text-text-muted">
            Starting swarm workers...
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="px-3 py-2 border-b border-border-subtle bg-surface-raised shrink-0">
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-xs text-text-muted font-mono">
            Swarm: {numWorkers} workers | depth {maxDepth}
          </span>
          <span className="text-xs text-text-secondary font-mono">
            {totalCompleted} tasks done
          </span>
        </div>
        {/* Aggregate progress bar */}
        <div className="flex items-center gap-2">
          <div className="flex-1 h-1.5 rounded-full bg-border-subtle overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                hasErrors
                  ? "bg-error"
                  : allDone
                    ? "bg-success"
                    : "bg-accent"
              }`}
              style={{
                width: `${
                  numWorkers > 0
                    ? (workers.filter((w) => w.status === "completed").length /
                        numWorkers) *
                      100
                    : 0
                }%`,
              }}
            />
          </div>
          <span className="text-xs text-text-muted font-mono">
            {workers.filter((w) => w.status === "completed").length}/
            {numWorkers}
          </span>
        </div>
      </div>

      {/* Tab selector */}
      <div className="flex border-b border-border-subtle bg-surface-raised shrink-0" role="tablist" aria-label="Swarm panel tabs">
        {(["workers", "mail", "merges", "health"] as SwarmTab[]).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            role="tab"
            aria-selected={activeTab === tab}
            aria-label={`${tab === "mail" ? "Mail" : tab === "merges" ? "Merges" : tab === "health" ? "Health" : "Workers"} tab`}
            className={`flex-1 px-3 py-1.5 text-xs font-mono transition-colors relative ${
              activeTab === tab
                ? "text-text-primary"
                : "text-text-muted hover:text-text-secondary"
            }`}
          >
            {tab === "mail" ? (
              <span className="flex items-center justify-center gap-1">
                Mail
                {mailStats.unread > 0 && (
                  <span className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-accent text-[9px] text-white font-bold">
                    {mailStats.unread}
                  </span>
                )}
              </span>
            ) : tab === "merges" ? "Merges" : tab === "health" ? "Health" : "Workers"}
            {activeTab === tab && (
              <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-accent" />
            )}
          </button>
        ))}
      </div>

      {/* Conflict warning */}
      {conflictLines.length > 0 && (
        <div className="px-3 py-2 bg-warning/10 border-b border-warning/30">
          <span className="text-xs text-warning font-medium">
            {"\u26A0"} File conflicts detected between workers
          </span>
        </div>
      )}

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto">
        {activeTab === "workers" && (
          <SwarmWorkersTab
            workers={workers}
            numWorkers={numWorkers}
            maxDepth={maxDepth}
            healthData={healthData}
            projectDir={projectDir}
            workersView={workersView}
            setWorkersView={setWorkersView}
            getWorkerOutput={getWorkerOutput}
            getWorkerRole={getWorkerRole}
            overrides={swarmOverrides}
            swarmRuntime={swarmRuntime}
            triageResults={triageResults}
            lspWorkerDiagnostics={lspWorkerDiagnostics}
          />
        )}

        {activeTab === "mail" && (
          <SwarmMailTab
            mailMessages={mailMessages}
            mailStats={mailStats}
            markMailRead={markMailRead}
            projectDir={projectDir}
          />
        )}

        {activeTab === "merges" && (
          <SwarmMergesTab
            mergeQueue={mergeQueue}
            mergeQueueStats={mergeQueueStats}
            mergeReport={mergeReport}
            conflictPrediction={conflictPrediction}
          />
        )}

        {activeTab === "health" && (
          <WatchdogPanel
            projectDir={projectDir}
            watchdogEvents={watchdogEvents}
            circuitBreakerStatus={circuitBreakerStatus}
            triageResults={triageResults}
          />
        )}
      </div>
    </div>
  );
}
