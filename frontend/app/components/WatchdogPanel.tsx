"use client";

import { useState, useEffect, useCallback } from "react";

// ── Types ────────────────────────────────────────────────────────

interface WatchdogWorkerState {
  worker_id: number;
  status: string;
  pid: number | null;
  role: string;
  last_output_ago_seconds: number;
  escalation_level: number;
  warnings: string[];
  assigned_task_ids: string[];
  completed_task_ids: string[];
  resource_usage: {
    cpu_percent?: number;
    memory_mb?: number;
    memory_percent?: number;
  };
  nudge_count: number;
  last_tool_time: number;
}

interface WatchdogEvent {
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

interface CircuitBreakerStatus {
  state: "closed" | "open" | "half_open";
  failure_rate: number;
  failures_in_window: number;
  successes_in_window: number;
}

interface TriageResultData {
  worker_id: number;
  verdict: "retry" | "terminate" | "extend" | "reassign";
  reasoning: string;
  confidence: number;
  recommended_action?: string;
  suggested_nudge_message?: string;
}

interface WatchdogConfig {
  enabled: boolean;
  check_interval_s: number;
  idle_threshold_s: number;
  stall_threshold_s: number;
  zombie_threshold_s: number;
  boot_grace_s: number;
  nudge_interval_s: number;
  max_nudge_attempts: number;
  ai_triage_enabled: boolean;
  triage_timeout_s: number;
  auto_reassign: boolean;
  circuit_breaker_enabled: boolean;
  max_failure_rate: number;
  circuit_breaker_window_s: number;
  persistent_roles: string[];
  [key: string]: unknown;
}

interface WatchdogPanelProps {
  projectDir: string;
  watchdogEvents?: WatchdogEvent[];
  circuitBreakerStatus?: CircuitBreakerStatus | null;
  triageResults?: Record<number, TriageResultData>;
}

// ── State badge colors ───────────────────────────────────────────

const STATE_COLORS: Record<string, string> = {
  booting: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  working: "bg-green-500/20 text-green-400 border-green-500/30",
  idle: "bg-gray-500/20 text-gray-400 border-gray-500/30",
  warning: "bg-amber-500/20 text-amber-400 border-amber-500/30",
  stalled: "bg-red-500/20 text-red-400 border-red-500/30 animate-pulse",
  recovering: "bg-cyan-500/20 text-cyan-400 border-cyan-500/30 animate-pulse",
  completed: "bg-green-500/20 text-green-400 border-green-500/30",
  zombie: "bg-purple-500/20 text-purple-400 border-purple-500/30",
  terminated: "bg-gray-500/20 text-gray-500 border-gray-500/30 line-through",
};

const CB_COLORS: Record<string, string> = {
  closed: "bg-green-500/20 text-green-400",
  half_open: "bg-amber-500/20 text-amber-400",
  open: "bg-red-500/20 text-red-400",
};

// ── Component ────────────────────────────────────────────────────

export function WatchdogPanel({
  projectDir,
  watchdogEvents: pushedEvents,
  circuitBreakerStatus: pushedCB,
  triageResults,
}: WatchdogPanelProps) {
  const [workers, setWorkers] = useState<Record<string, WatchdogWorkerState>>({});
  const [events, setEvents] = useState<WatchdogEvent[]>([]);
  const [circuitBreaker, setCircuitBreaker] = useState<CircuitBreakerStatus | null>(null);
  const [config, setConfig] = useState<WatchdogConfig | null>(null);
  const [showConfig, setShowConfig] = useState(false);
  const [fleetScore, setFleetScore] = useState(100);
  const [nudgeCooldowns, setNudgeCooldowns] = useState<Record<number, number>>({});

  // Fetch health data
  const fetchHealth = useCallback(async () => {
    try {
      const res = await fetch(`/api/swarm/health?path=${encodeURIComponent(projectDir)}`);
      const data = await res.json();
      if (data.workers) setWorkers(data.workers);
      if (data.circuit_breaker) setCircuitBreaker(data.circuit_breaker);
    } catch { /* ignore */ }
  }, [projectDir]);

  // Fetch events
  const fetchEvents = useCallback(async () => {
    try {
      const res = await fetch(`/api/watchdog/events?path=${encodeURIComponent(projectDir)}&limit=50`);
      const data = await res.json();
      if (data.events) setEvents(data.events);
    } catch { /* ignore */ }
  }, [projectDir]);

  // Fetch config (on mount)
  const fetchConfig = useCallback(async () => {
    try {
      const res = await fetch(`/api/watchdog/config?path=${encodeURIComponent(projectDir)}`);
      const data = await res.json();
      if (!data.error) setConfig(data);
    } catch { /* ignore */ }
  }, [projectDir]);

  // Poll
  useEffect(() => {
    if (!projectDir) return;
    fetchHealth();
    fetchEvents();
    fetchConfig();
    const interval = setInterval(() => {
      fetchHealth();
      fetchEvents();
    }, 10000);
    return () => clearInterval(interval);
  }, [projectDir, fetchHealth, fetchEvents, fetchConfig]);

  // Merge pushed events
  useEffect(() => {
    if (pushedEvents && pushedEvents.length > 0) {
      setEvents((prev) => {
        const combined = [...pushedEvents, ...prev];
        return combined.slice(0, 100);
      });
    }
  }, [pushedEvents]);

  useEffect(() => {
    if (pushedCB) setCircuitBreaker(pushedCB);
  }, [pushedCB]);

  // Calculate fleet score
  useEffect(() => {
    const workerList = Object.values(workers);
    if (workerList.length === 0) { setFleetScore(100); return; }
    let score = 100;
    for (const w of workerList) {
      if (w.status === "stalled") score -= 25;
      else if (w.status === "zombie") score -= 30;
      else if (w.status === "warning") score -= 10;
      else if (w.status === "terminated") score -= 5;
      else if (w.status === "idle") score -= 3;
    }
    setFleetScore(Math.max(0, Math.min(100, score)));
  }, [workers]);

  // Nudge cooldown timer
  useEffect(() => {
    const interval = setInterval(() => {
      setNudgeCooldowns((prev) => {
        const next: Record<number, number> = {};
        for (const [k, v] of Object.entries(prev)) {
          if (v > 0) next[Number(k)] = v - 1;
        }
        return next;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  const handleNudge = async (workerId: number) => {
    if (nudgeCooldowns[workerId] > 0) return;
    try {
      await fetch(`/api/swarm/workers/${workerId}/nudge`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: projectDir, message: "" }),
      });
      setNudgeCooldowns((prev) => ({ ...prev, [workerId]: 30 }));
    } catch { /* ignore */ }
  };

  const handleTerminate = async (workerId: number) => {
    if (!confirm(`Terminate worker ${workerId}?`)) return;
    try {
      await fetch(`/api/swarm/workers/${workerId}/terminate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: projectDir }),
      });
      fetchHealth();
    } catch { /* ignore */ }
  };

  const handleConfigSave = async () => {
    if (!config) return;
    try {
      await fetch(`/api/watchdog/config?path=${encodeURIComponent(projectDir)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });
    } catch { /* ignore */ }
  };

  const scoreColor = fleetScore > 70 ? "text-green-400" : fleetScore > 40 ? "text-amber-400" : "text-red-400";
  const scoreBg = fleetScore > 70 ? "bg-green-500" : fleetScore > 40 ? "bg-amber-500" : "bg-red-500";
  const workerList = Object.entries(workers);

  return (
    <div className="flex flex-col h-full overflow-hidden text-xs font-mono">
      {/* Fleet Health Score Bar */}
      <div className="px-3 py-2 border-b border-border-subtle bg-surface-raised flex items-center gap-3 shrink-0">
        <div className="flex items-center gap-2">
          <span className={`text-lg font-bold ${scoreColor}`}>{fleetScore}</span>
          <span className="text-text-muted text-[10px]">Fleet Score</span>
        </div>
        <div className="flex-1 h-1.5 rounded-full bg-border-subtle overflow-hidden">
          <div className={`h-full rounded-full transition-all duration-500 ${scoreBg}`} style={{ width: `${fleetScore}%` }} />
        </div>
        {/* Circuit Breaker Badge */}
        {circuitBreaker && (
          <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${CB_COLORS[circuitBreaker.state] || ""}`}>
            CB: {circuitBreaker.state.toUpperCase()}
          </span>
        )}
        <span className="text-text-muted">{workerList.length} workers</span>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-3">
        {/* Worker Cards */}
        {workerList.length > 0 && (
          <div>
            <div className="text-text-muted mb-1.5 uppercase tracking-wider text-[10px]">Workers</div>
            <div className="grid grid-cols-1 gap-1.5">
              {workerList.map(([wid, w]) => (
                <div key={wid} className="border border-border-subtle rounded p-2 bg-surface-raised">
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-1.5">
                      <span className="text-text-secondary font-medium">W{wid}</span>
                      <span className={`px-1.5 py-0.5 rounded border text-[10px] ${STATE_COLORS[w.status] || "bg-gray-500/20 text-gray-400"}`}>
                        {w.status}
                      </span>
                      <span className="text-text-muted text-[10px]">{w.role}</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => handleNudge(w.worker_id)}
                        disabled={nudgeCooldowns[w.worker_id] > 0}
                        className="px-1.5 py-0.5 rounded text-[10px] bg-amber-500/10 text-amber-400 hover:bg-amber-500/20 disabled:opacity-30"
                        title={nudgeCooldowns[w.worker_id] > 0 ? `Cooldown: ${nudgeCooldowns[w.worker_id]}s` : "Nudge worker"}
                      >
                        {nudgeCooldowns[w.worker_id] > 0 ? `${nudgeCooldowns[w.worker_id]}s` : "Nudge"}
                      </button>
                      <button
                        onClick={() => handleTerminate(w.worker_id)}
                        className="px-1.5 py-0.5 rounded text-[10px] bg-red-500/10 text-red-400 hover:bg-red-500/20"
                        title="Terminate worker"
                      >
                        Kill
                      </button>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 text-[10px] text-text-muted">
                    <span>Activity: {w.last_output_ago_seconds >= 0 ? `${w.last_output_ago_seconds}s ago` : "N/A"}</span>
                    <span>Tasks: {w.completed_task_ids?.length || 0}/{w.assigned_task_ids?.length || 0}</span>
                    <span>Esc: L{w.escalation_level}</span>
                    {w.nudge_count > 0 && <span>Nudges: {w.nudge_count}</span>}
                  </div>
                  {/* Resource bars */}
                  {w.resource_usage && (w.resource_usage.cpu_percent != null || w.resource_usage.memory_mb != null) && (
                    <div className="flex items-center gap-2 mt-1">
                      {w.resource_usage.cpu_percent != null && (
                        <div className="flex items-center gap-1 flex-1">
                          <span className="text-[9px] text-text-muted w-7">CPU</span>
                          <div className="flex-1 h-1 rounded-full bg-border-subtle overflow-hidden">
                            <div className="h-full rounded-full bg-accent" style={{ width: `${Math.min(w.resource_usage.cpu_percent, 100)}%` }} />
                          </div>
                          <span className="text-[9px] text-text-muted w-8">{w.resource_usage.cpu_percent}%</span>
                        </div>
                      )}
                      {w.resource_usage.memory_mb != null && (
                        <div className="flex items-center gap-1 flex-1">
                          <span className="text-[9px] text-text-muted w-7">MEM</span>
                          <span className="text-[9px] text-text-muted">{w.resource_usage.memory_mb}MB</span>
                        </div>
                      )}
                    </div>
                  )}
                  {/* Warnings */}
                  {w.warnings && w.warnings.length > 0 && (
                    <div className="mt-1 text-[10px] text-warning">{w.warnings[w.warnings.length - 1]}</div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Triage Cards */}
        {triageResults && Object.keys(triageResults).length > 0 && (
          <div>
            <div className="text-text-muted mb-1.5 uppercase tracking-wider text-[10px]">Triage Results</div>
            {Object.entries(triageResults).map(([wid, tr]) => {
              const verdictColor = { retry: "text-amber-400", extend: "text-cyan-400", reassign: "text-purple-400", terminate: "text-red-400" }[tr.verdict] || "text-text-secondary";
              return (
                <div key={wid} className="border border-border-subtle rounded p-2 bg-surface-raised mb-1.5">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-text-secondary">Worker {wid}</span>
                    <span className={`font-medium ${verdictColor}`}>{tr.verdict.toUpperCase()}</span>
                  </div>
                  <div className="text-[10px] text-text-muted">{tr.reasoning}</div>
                  {/* Confidence bar */}
                  <div className="flex items-center gap-1 mt-1">
                    <span className="text-[9px] text-text-muted">Confidence:</span>
                    <div className="flex-1 h-1 rounded-full bg-border-subtle overflow-hidden">
                      <div className="h-full rounded-full bg-accent" style={{ width: `${(tr.confidence || 0) * 100}%` }} />
                    </div>
                    <span className="text-[9px] text-text-muted">{((tr.confidence || 0) * 100).toFixed(0)}%</span>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Escalation Timeline */}
        {events.length > 0 && (
          <div>
            <div className="text-text-muted mb-1.5 uppercase tracking-wider text-[10px]">Event Timeline</div>
            <div className="space-y-0.5">
              {events.slice(0, 20).map((ev, i) => {
                const ts = ev.timestamp?.slice(11, 19) || "";
                const typeColor = ev.event_type === "state_change" ? "text-cyan-400"
                  : ev.event_type === "stalled" || ev.event_type === "terminated" ? "text-red-400"
                  : ev.event_type === "nudge" || ev.event_type === "watchdog_nudge" ? "text-amber-400"
                  : ev.event_type === "triage" || ev.event_type === "watchdog_triage" ? "text-purple-400"
                  : ev.event_type === "run_complete" ? "text-green-400"
                  : "text-text-muted";
                return (
                  <div key={ev.id || `${ev.timestamp}-${i}`} className="flex items-start gap-1.5 text-[10px]">
                    <span className="text-text-muted shrink-0">{ts}</span>
                    <span className={`shrink-0 ${typeColor}`}>{ev.event_type}</span>
                    {ev.worker_id >= 0 && <span className="text-text-muted shrink-0">W{ev.worker_id}</span>}
                    <span className="text-text-secondary truncate">{ev.message?.slice(0, 60)}</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Config Editor */}
        <div>
          <button
            onClick={() => setShowConfig(!showConfig)}
            className="text-text-muted uppercase tracking-wider text-[10px] hover:text-text-secondary"
          >
            {showConfig ? "▼" : "▶"} Configuration
          </button>
          {showConfig && config && (
            <div className="mt-1.5 border border-border-subtle rounded p-2 bg-surface-raised space-y-1.5">
              {Object.entries(config).filter(([k]) => k !== "persistent_roles").map(([key, value]) => (
                <div key={key} className="flex items-center gap-2">
                  <label className="text-[10px] text-text-muted w-36 shrink-0">{key}</label>
                  {typeof value === "boolean" ? (
                    <input
                      type="checkbox"
                      checked={value}
                      onChange={(e) => setConfig({ ...config, [key]: e.target.checked })}
                      className="h-3 w-3"
                    />
                  ) : (
                    <input
                      type={typeof value === "number" ? "number" : "text"}
                      value={String(value)}
                      onChange={(e) => {
                        const v = typeof value === "number" ? Number(e.target.value) : e.target.value;
                        setConfig({ ...config, [key]: v });
                      }}
                      className="flex-1 px-1.5 py-0.5 rounded text-[10px] bg-surface-base border border-border-subtle text-text-primary"
                    />
                  )}
                </div>
              ))}
              <div className="flex gap-2 pt-1">
                <button
                  onClick={handleConfigSave}
                  className="px-2 py-0.5 rounded text-[10px] bg-accent/20 text-accent hover:bg-accent/30"
                >
                  Save
                </button>
                <button
                  onClick={fetchConfig}
                  className="px-2 py-0.5 rounded text-[10px] bg-gray-500/10 text-text-muted hover:bg-gray-500/20"
                >
                  Reset
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Empty state */}
        {workerList.length === 0 && events.length === 0 && (
          <div className="flex-1 flex items-center justify-center p-4">
            <span className="text-text-muted">No watchdog data yet. Start a swarm session to see health monitoring.</span>
          </div>
        )}
      </div>
    </div>
  );
}
