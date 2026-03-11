"use client";

import { useCallback, useRef, useState } from "react";
import type {
  AgentEvent,
  SessionStats,
  TaskData,
  WorktreeInfo,
  ApprovalRequestData,
  RunConfig,
} from "./useSwarmWeaver";

export interface UseWebSocketOptions {
  onStatusRunning: (projectDir: string) => void;
  onStatusCompleted: (projectDir: string) => void;
  onError: (message: string) => void;
  onWarning: (title: string, body: string) => void;
  onBrowserNotification: (title: string, body: string, eventType?: string) => void;
  onWorktreeReady: (info: WorktreeInfo) => void;
  onApprovalRequest: (data: ApprovalRequestData) => void;
  onTaskListReady: (data: TaskData) => void;
  fetchTasks: (projectPath: string) => void;
  fetchOutputLog: (projectPath: string) => Promise<string[]>;
  stopTaskPolling: () => void;
}

export interface QualityGateResult {
  name: string;
  passed: boolean;
  detail: string;
}

export interface QualityGateReport {
  worker_id: number;
  passed: boolean;
  gates: QualityGateResult[];
}

export interface TriageResult {
  worker_id: number;
  verdict: "retry" | "terminate" | "extend" | "escalate" | "reassign";
  reasoning: string;
  recommended_action?: string;
  suggested_nudge_message?: string;
  confidence?: number;
  timestamp?: string;
}

export interface MonitorHealthSummary {
  fleet_score: number;
  worker_statuses: Array<{
    worker_id: number;
    status: string;
    last_output_ago: number;
    escalation_level: number;
    warnings: string[];
  }>;
  actions_taken: Array<{
    type: string;
    worker_id?: number;
    reason: string;
  }>;
  check_number: number;
  timestamp: string;
}

export interface WatchdogEvent {
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

export interface CircuitBreakerStatus {
  state: "closed" | "open" | "half_open";
  failure_rate: number;
  failures_in_window: number;
  successes_in_window: number;
}

export interface LspDiagnostic {
  uri: string;
  line: number;
  character: number;
  severity: number;
  severity_label: string;
  message: string;
  source: string | null;
  code: string | number | null;
}

export interface LspServerInfo {
  language_id: string;
  server_name: string;
  status: "stopped" | "starting" | "ready" | "degraded" | "crashed";
  pid: number | null;
  diagnostic_count: number;
  worker_id: number | null;
}

export interface LspCodeHealth {
  score: number;
  error_count: number;
  warning_count: number;
  by_language: Record<string, { score: number; errors: number; warnings: number }>;
}

export interface LspCrossWorkerAlert {
  source_worker_id: number;
  affected_worker_id: number;
  file_path: string;
  diagnostics: LspDiagnostic[];
  timestamp: string;
}

export interface UseWebSocketReturn {
  wsRef: React.MutableRefObject<WebSocket | null>;
  wsConnected: boolean;
  connect: (config: RunConfig) => void;
  close: () => void;
  send: (data: unknown) => void;
  setOutput: React.Dispatch<React.SetStateAction<string[]>>;
  setEvents: React.Dispatch<React.SetStateAction<AgentEvent[]>>;
  setSessionStats: React.Dispatch<React.SetStateAction<SessionStats | null>>;
  output: string[];
  events: AgentEvent[];
  sessionStats: SessionStats | null;
  qualityGates: Record<number, QualityGateReport>;
  triageResults: Record<number, TriageResult>;
  monitorHealth: MonitorHealthSummary | null;
  monitorTrend: number[];
  workerTokenMap: Record<number, { input: number; output: number; cacheRead: number; cacheCreation: number }>;
  watchdogEvents: WatchdogEvent[];
  circuitBreakerStatus: CircuitBreakerStatus | null;
  // LSP state
  lspDiagnostics: Record<string, LspDiagnostic[]>;
  lspServerStatus: Record<string, LspServerInfo>;
  lspCodeHealth: LspCodeHealth | null;
  lspCodeHealthTrend: number[];
  lspCrossWorkerAlerts: LspCrossWorkerAlert[];
}

/** Backend WS URL — direct to FastAPI on port 8000. */
const WS_URL = "ws://localhost:8000/ws/run";

export function useWebSocket(options: UseWebSocketOptions): UseWebSocketReturn {
  const {
    onStatusRunning,
    onStatusCompleted,
    onError,
    onWarning,
    onBrowserNotification,
    onWorktreeReady,
    onApprovalRequest,
    onTaskListReady,
    fetchTasks,
    fetchOutputLog,
    stopTaskPolling,
  } = options;

  const wsRef = useRef<WebSocket | null>(null);
  const [wsConnected, setWsConnected] = useState(false);
  const reconnectAttempts = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Track whether session ended normally — don't reconnect after completion/error
  const sessionEndedRef = useRef(false);

  const [output, setOutput] = useState<string[]>([]);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [sessionStats, setSessionStats] = useState<SessionStats | null>(null);
  const [qualityGates, setQualityGates] = useState<Record<number, QualityGateReport>>({});
  const [triageResults, setTriageResults] = useState<Record<number, TriageResult>>({});
  const [monitorHealth, setMonitorHealth] = useState<MonitorHealthSummary | null>(null);
  const [monitorTrend, setMonitorTrend] = useState<number[]>([]);
  // Per-worker token tracking (keyed by worker_id number)
  const [workerTokenMap, setWorkerTokenMap] = useState<Record<number, { input: number; output: number; cacheRead: number; cacheCreation: number }>>({});
  // Watchdog events
  const [watchdogEvents, setWatchdogEvents] = useState<WatchdogEvent[]>([]);
  const [circuitBreakerStatus, setCircuitBreakerStatus] = useState<CircuitBreakerStatus | null>(null);
  // LSP state
  const [lspDiagnostics, setLspDiagnostics] = useState<Record<string, LspDiagnostic[]>>({});
  const [lspServerStatus, setLspServerStatus] = useState<Record<string, LspServerInfo>>({});
  const [lspCodeHealth, setLspCodeHealth] = useState<LspCodeHealth | null>(null);
  const [lspCodeHealthTrend, setLspCodeHealthTrend] = useState<number[]>([]);
  const [lspCrossWorkerAlerts, setLspCrossWorkerAlerts] = useState<LspCrossWorkerAlert[]>([]);

  const close = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (wsRef.current) {
      // Null out handlers BEFORE closing to prevent the async onclose from
      // triggering reconnection logic that would overwrite a new connection
      wsRef.current.onopen = null;
      wsRef.current.onmessage = null;
      wsRef.current.onerror = null;
      wsRef.current.onclose = null;
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  const send = useCallback((data: unknown) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  const connect = useCallback(
    (config: RunConfig) => {
      // Kill any old connection / pending reconnect
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      if (wsRef.current) {
        // Null out handlers to prevent stale onclose from triggering reconnection
        wsRef.current.onopen = null;
        wsRef.current.onmessage = null;
        wsRef.current.onerror = null;
        wsRef.current.onclose = null;
        wsRef.current.close();
        wsRef.current = null;
      }
      reconnectAttempts.current = 0;
      sessionEndedRef.current = false;

      // Create WebSocket synchronously (matches original working pattern)
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        setWsConnected(true);
        reconnectAttempts.current = 0;
        ws.send(JSON.stringify(config));
      };

      ws.onmessage = (event: MessageEvent) => {
        try {
          const msg = JSON.parse(event.data);

          if (msg.type === "output") {
            const line = typeof msg.data === "string" ? msg.data : JSON.stringify(msg.data);
            setOutput((prev) => [...prev, line]);
          } else if (msg.type === "status") {
            if (msg.data === "running") {
              onStatusRunning(config.project_dir);
            } else if (msg.data === "completed" || msg.data === "stopped") {
              sessionEndedRef.current = true;
              onStatusCompleted(config.project_dir);
            }
          } else if (msg.type === "error") {
            sessionEndedRef.current = true;
            setOutput((prev) => [...prev, `ERROR: ${msg.data}`]);
            onError(msg.data);
          } else if (msg.type === "warning") {
            const warnData = msg.data || {};
            onWarning(warnData.title || "Warning", warnData.body || "");
          } else if (msg.type === "browser_notification") {
            const notifData = msg.data || {};
            onBrowserNotification(
              notifData.title || "SwarmWeaver",
              notifData.body || "",
              notifData.event_type
            );
          } else if (msg.type === "worktree_ready") {
            onWorktreeReady(msg.data as WorktreeInfo);
          } else if (msg.type === "task_list_ready" || msg.type === "task_list_update") {
            onTaskListReady(msg.data as TaskData);
          } else if (msg.type === "approval_request") {
            onApprovalRequest(msg.data as ApprovalRequestData);
          } else if (msg.type === "session_stat") {
            setSessionStats(msg.data as SessionStats);
          } else if (msg.type === "quality_gate_result") {
            const gateData = msg.data || msg;
            const workerId = gateData.worker_id as number;
            if (workerId != null) {
              setQualityGates((prev) => ({
                ...prev,
                [workerId]: {
                  worker_id: workerId,
                  passed: gateData.passed as boolean,
                  gates: (gateData.gates || []) as QualityGateResult[],
                },
              }));
            }
          } else if (msg.type === "triage_result") {
            const d = msg.data || msg;
            const workerId = d.worker_id as number;
            if (workerId != null) {
              setTriageResults((prev) => ({
                ...prev,
                [workerId]: {
                  worker_id: workerId,
                  verdict: d.verdict as TriageResult["verdict"],
                  reasoning: (d.reasoning as string) || "",
                  recommended_action: (d.recommended_action as string) || "",
                  timestamp: (msg.timestamp as string) || new Date().toISOString(),
                },
              }));
            }
          } else if (msg.type === "monitor_health_summary") {
            const d = msg.data || msg;
            const summary: MonitorHealthSummary = {
              fleet_score: (d.fleet_score as number) ?? 0,
              worker_statuses: (d.worker_statuses as MonitorHealthSummary["worker_statuses"]) ?? [],
              actions_taken: (d.actions_taken as MonitorHealthSummary["actions_taken"]) ?? [],
              check_number: (d.check_number as number) ?? 0,
              timestamp: (d.timestamp as string) || new Date().toISOString(),
            };
            setMonitorHealth(summary);
            setMonitorTrend((prev) => {
              const next = [...prev, summary.fleet_score];
              return next.length > 30 ? next.slice(-30) : next;
            });
          // --- Real-time token tracking (fires on every API turn during streaming) ---
          } else if (msg.type === "token_update") {
            const it = (msg.input_tokens as number) || 0;
            const ot = (msg.output_tokens as number) || 0;
            const crt = (msg.cache_read_tokens as number) || 0;
            const cct = (msg.cache_creation_tokens as number) || 0;
            const wid = msg.worker_id as number | undefined;

            if (wid != null) {
              // Worker token update — track per-worker
              setWorkerTokenMap((prev) => ({
                ...prev,
                [wid]: {
                  input: Math.max(it, prev[wid]?.input ?? 0),
                  output: Math.max(ot, prev[wid]?.output ?? 0),
                  cacheRead: Math.max(crt, prev[wid]?.cacheRead ?? 0),
                  cacheCreation: Math.max(cct, prev[wid]?.cacheCreation ?? 0),
                },
              }));
            }

            // Always update global sessionStats (aggregate total across all agents)
            setSessionStats((prev) => {
              const defaults = { tool_call_count: 0, tool_counts: {}, error_count: 0, file_touches: {}, current_phase: "", session_number: 0, start_time: new Date().toISOString() };
              if (wid != null) {
                // For worker events: sum up all worker tokens + orchestrator tokens
                // We'll compute the global total from workerTokenMap in a moment,
                // but also keep updating so the display stays live
                return {
                  ...(prev ?? defaults),
                  input_tokens: Math.max(it, prev?.input_tokens ?? 0),
                  output_tokens: Math.max(ot, prev?.output_tokens ?? 0),
                  cache_read_tokens: Math.max(crt, prev?.cache_read_tokens ?? 0),
                  cache_creation_tokens: Math.max(cct, prev?.cache_creation_tokens ?? 0),
                } as SessionStats;
              }
              return {
                ...(prev ?? defaults),
                input_tokens: Math.max(it, prev?.input_tokens ?? 0),
                output_tokens: Math.max(ot, prev?.output_tokens ?? 0),
                cache_read_tokens: Math.max(crt, prev?.cache_read_tokens ?? 0),
                cache_creation_tokens: Math.max(cct, prev?.cache_creation_tokens ?? 0),
              } as SessionStats;
            });

          // --- Native SDK tool lifecycle events ---
          } else if (msg.type === "tool_start" || msg.type === "tool_done" || msg.type === "tool_input_delta" || msg.type === "tool_input_complete" || msg.type === "tool_result" || msg.type === "tool_error" || msg.type === "tool_blocked") {
            // Tool lifecycle events from native engine
            setEvents((prev) => {
              const next = [...prev, { type: msg.type, timestamp: msg.timestamp || new Date().toISOString(), data: msg } as AgentEvent];
              return next;
            });
          } else if (msg.type === "text_delta") {
            // Token-level text streaming from native engine
            const text = msg.text as string || "";
            if (text) {
              // Buffer text and flush complete lines to output
              setOutput((prev) => {
                const last = prev.length > 0 ? prev[prev.length - 1] : "";
                // If text contains newlines, split into lines
                if (text.includes("\n")) {
                  const parts = text.split("\n");
                  const updatedLast = last + parts[0];
                  const newLines = parts.slice(1);
                  const result = [...prev.slice(0, -1), updatedLast, ...newLines];
                  return result.length > 2000 ? result.slice(-2000) : result;
                }
                // Append to last line
                return [...prev.slice(0, -1), last + text];
              });
              // Also push to events for Native Activity Feed
              setEvents((prev) => [
                ...prev,
                { type: "text_delta", timestamp: msg.timestamp || new Date().toISOString(), data: msg } as AgentEvent,
              ]);
            }
          } else if (msg.type === "session_result") {
            // Real SDK cost data from native engine
            const data = msg.data || msg;
            setSessionStats((prev) => ({
              tool_call_count: prev?.tool_call_count || 0,
              tool_counts: prev?.tool_counts || {},
              error_count: prev?.error_count || 0,
              file_touches: prev?.file_touches || {},
              current_phase: (data.phase as string) || prev?.current_phase || "",
              session_number: (data.session as number) || prev?.session_number || 0,
              start_time: prev?.start_time || new Date().toISOString(),
              ...(data.total_cost_usd != null ? { total_cost_usd: data.total_cost_usd as number } : {}),
              ...(data.input_tokens != null ? { input_tokens: data.input_tokens as number } : {}),
              ...(data.output_tokens != null ? { output_tokens: data.output_tokens as number } : {}),
              ...(data.cache_read_tokens != null ? { cache_read_tokens: data.cache_read_tokens as number } : {}),
              ...(data.cache_creation_tokens != null ? { cache_creation_tokens: data.cache_creation_tokens as number } : {}),
              ...(data.duration_s != null ? { duration_s: data.duration_s as number } : {}),
            } as SessionStats));
          } else if (msg.type === "session_start") {
            // Capture start_time for the timer immediately
            const data = (msg.data || {}) as Record<string, unknown>;
            const backendStartTime = (data.start_time as string) || new Date().toISOString();
            setSessionStats((prev) => ({
              ...(prev ?? { tool_call_count: 0, tool_counts: {}, error_count: 0, file_touches: {}, current_phase: "", session_number: 0, start_time: backendStartTime }),
              start_time: prev?.start_time || backendStartTime,
              current_phase: (data.phase as string) || prev?.current_phase || "",
              session_number: (data.session as number) || prev?.session_number || 0,
            } as SessionStats));
            setEvents((prev) => [...prev, { type: msg.type, timestamp: msg.timestamp || new Date().toISOString(), data: data } as AgentEvent]);
          } else if (msg.type === "phase_change" || msg.type === "phase_complete" || msg.type === "phase_skipped" || msg.type === "verification" || msg.type === "approval_resolved" || msg.type === "budget_exceeded" || msg.type === "max_iterations_reached" || msg.type === "github_pr") {
            // Lifecycle events from native engine
            setEvents((prev) => {
              const next = [...prev, { type: msg.type, timestamp: msg.timestamp || new Date().toISOString(), data: msg.data || {} } as AgentEvent];
              return next;
            });
          } else if (msg.type === "engine_error") {
            // SDK-level errors (ProcessError, CLIConnectionError, etc.)
            const errData = msg.data || {};
            const errMsg = (errData.error as string) || "Engine error";
            setOutput((prev) => [...prev, `[ENGINE ERROR] ${errMsg}`]);
            setEvents((prev) => [
              ...prev,
              { type: "error", timestamp: msg.timestamp || new Date().toISOString(), data: errData } as AgentEvent,
            ]);
          } else if (msg.type === "session_error") {
            const errData = msg.data || {};
            setOutput((prev) => [...prev, `[SESSION ERROR] ${errData.error || "Unknown error"}`]);
          } else if (msg.type === "context_budget_warning") {
            // Context window approaching limit — warn the user
            const d = msg.data || {};
            const tokens = (d.input_tokens as number) || 0;
            onWarning("Context Budget Warning", `Input tokens: ${tokens.toLocaleString()} — approaching context limit. Agent has been instructed to be concise.`);
          } else if (msg.type === "budget_stop_broadcast") {
            // Swarm budget exhausted — all workers halting
            const d = msg.data || {};
            const reason = (d.reason as string) || "Budget exhausted";
            onWarning("Budget Stop", reason);
            setOutput((prev) => [...prev, `[BUDGET STOP] ${reason}`]);
          } else if (msg.type === "thinking_block") {
            // Extended thinking content from adaptive thinking (Phase 7A)
            setEvents((prev) => [
              ...prev,
              { type: "thinking_block", timestamp: msg.timestamp || new Date().toISOString(), data: msg.data || {} } as AgentEvent,
            ]);
          } else if (msg.type === "thinking_delta") {
            // Streaming thinking tokens — push to events for activity feed
            setEvents((prev) => [
              ...prev,
              { type: "thinking_delta", timestamp: msg.timestamp || new Date().toISOString(), data: { text: msg.data } } as AgentEvent,
            ]);
          } else if (msg.type === "worker_heartbeat") {
            // Worker health pulse from SmartOrchestrator
            setEvents((prev) => [
              ...prev,
              { type: "worker_heartbeat", timestamp: msg.timestamp || new Date().toISOString(), data: msg.data || {} } as AgentEvent,
            ]);
          } else if (msg.type === "worker_spawned" || msg.type === "worker_merged" || msg.type === "worker_terminated" || msg.type === "worker_error") {
            // Swarm worker lifecycle events
            if (msg.type === "worker_error") {
              const d = msg.data || {};
              setOutput((prev) => [...prev, `[WORKER ERROR] worker-${d.worker_id}: ${(d.error as string) || "Unknown"}`]);
            }
            setEvents((prev) => [
              ...prev,
              { type: msg.type, timestamp: msg.timestamp || new Date().toISOString(), data: msg.data || {} } as AgentEvent,
            ]);
          } else if (msg.type === "swarm_status") {
            // Swarm phase transitions (setup/running/merging)
            setEvents((prev) => [
              ...prev,
              { type: "swarm_status", timestamp: msg.timestamp || new Date().toISOString(), data: msg.data || {} } as AgentEvent,
            ]);
          } else if (msg.type === "worker_status") {
            // Individual worker lifecycle — does NOT affect session status.
            // Only the orchestrator's own "status" event ends the run.
            const wid = msg.worker_id as number;
            const wdata = (msg.data as string) || "";
            if (wid != null) {
              setOutput((prev) => [
                ...prev,
                `[Worker ${wid}] status: ${wdata}`,
              ]);
            }
          } else if (msg.type === "quality_gate_report") {
            // Quality gate report (backend emits "quality_gate_report", not "quality_gate_result")
            const gateData = msg.data || msg;
            const workerId = gateData.worker_id as number;
            if (workerId != null) {
              setQualityGates((prev) => ({
                ...prev,
                [workerId]: {
                  worker_id: workerId,
                  passed: gateData.passed as boolean,
                  gates: (gateData.gates || []) as QualityGateResult[],
                },
              }));
            }
          } else if (msg.type === "merge_error") {
            // Swarm merge failure
            const d = msg.data || {};
            setOutput((prev) => [...prev, `[MERGE ERROR] ${(d.error as string) || "Unknown merge error"}`]);
            setEvents((prev) => [
              ...prev,
              { type: "merge", timestamp: msg.timestamp || new Date().toISOString(), data: d } as AgentEvent,
            ]);
          } else if (msg.type === "mcp_servers") {
            // MCP server status — push to events for DetailDrawer's Processes panel
            setEvents((prev) => [
              ...prev,
              { type: "mcp_servers", timestamp: msg.timestamp || new Date().toISOString(), data: { servers: msg.servers } } as AgentEvent,
            ]);
          } else if (msg.type === "budget_update" || msg.type === "agent_health" || msg.type === "dispatch_event" || msg.type === "escalation_event" || msg.type === "merge_event") {
            // budget_update: also update sessionStats so cost displays immediately
            if (msg.type === "budget_update") {
              const d = msg.data || {};
              const realCost = (d.real_cost_usd as number) || 0;
              const estCost = (d.estimated_cost_usd as number) || 0;
              const cost = realCost || estCost;
              if (cost > 0) {
                setSessionStats((prev) => ({
                  ...(prev ?? { tool_call_count: 0, tool_counts: {}, error_count: 0, file_touches: {}, current_phase: "", session_number: 0, start_time: new Date().toISOString() }),
                  total_cost_usd: cost,
                } as SessionStats));
              }
            }
            const eventType = msg.type === "dispatch_event" ? "dispatch"
              : msg.type === "escalation_event" ? "escalation"
              : msg.type === "merge_event" ? "merge"
              : msg.type;
            setEvents((prev) => {
              const next = [...prev, { type: eventType, timestamp: msg.timestamp || new Date().toISOString(), data: msg.data } as AgentEvent];
              return next;
            });
          // --- Watchdog events (W4-3) ---
          } else if (msg.type === "watchdog_state_change") {
            const d = msg.data || msg;
            setWatchdogEvents((prev) => {
              const ev: WatchdogEvent = {
                timestamp: (msg.timestamp as string) || new Date().toISOString(),
                event_type: "state_change",
                worker_id: d.worker_id as number,
                message: `${d.old_state} → ${d.new_state}: ${d.reason || ""}`,
                state_before: d.old_state as string,
                state_after: d.new_state as string,
              };
              const next = [ev, ...prev];
              return next.length > 100 ? next.slice(0, 100) : next;
            });
          } else if (msg.type === "watchdog_nudge") {
            const d = msg.data || msg;
            setWatchdogEvents((prev) => {
              const ev: WatchdogEvent = {
                timestamp: (msg.timestamp as string) || new Date().toISOString(),
                event_type: "nudge",
                worker_id: d.worker_id as number,
                message: `Nudge via ${d.method}: ${d.message || ""}`,
              };
              return [ev, ...prev].slice(0, 100);
            });
          } else if (msg.type === "watchdog_triage") {
            const d = msg.data || msg;
            const workerId = d.worker_id as number;
            if (workerId != null) {
              setTriageResults((prev) => ({
                ...prev,
                [workerId]: {
                  worker_id: workerId,
                  verdict: d.verdict as TriageResult["verdict"],
                  reasoning: (d.reasoning as string) || "",
                  recommended_action: "",
                  timestamp: (msg.timestamp as string) || new Date().toISOString(),
                },
              }));
            }
            setWatchdogEvents((prev) => {
              const ev: WatchdogEvent = {
                timestamp: (msg.timestamp as string) || new Date().toISOString(),
                event_type: "triage",
                worker_id: d.worker_id as number,
                message: `Verdict: ${d.verdict} (confidence: ${((d.confidence as number) || 0) * 100}%)`,
                triage_verdict: d.verdict as string,
              };
              return [ev, ...prev].slice(0, 100);
            });
          } else if (msg.type === "watchdog_circuit_breaker") {
            const d = msg.data || msg;
            setCircuitBreakerStatus({
              state: d.state as CircuitBreakerStatus["state"],
              failure_rate: (d.failure_rate as number) || 0,
              failures_in_window: (d.failures_in_window as number) || 0,
              successes_in_window: (d.successes_in_window as number) || 0,
            });
          } else if (msg.type === "run_complete") {
            const d = msg.data || msg;
            const completed = (d.completed as number) || 0;
            const failed = (d.failed as number) || 0;
            const total = (d.total as number) || 0;
            onBrowserNotification(
              "Swarm Complete",
              `${completed}/${total} workers succeeded, ${failed} failed`,
              "run_complete"
            );
            setWatchdogEvents((prev) => {
              const ev: WatchdogEvent = {
                timestamp: (msg.timestamp as string) || new Date().toISOString(),
                event_type: "run_complete",
                worker_id: -1,
                message: `Run complete: ${completed}/${total} succeeded, ${failed} failed`,
              };
              return [ev, ...prev].slice(0, 100);
            });
          } else if (msg.type === "lsp.diagnostics_update") {
            const d = msg.data || msg;
            const filePath = (d.file_path as string) || "";
            const diags = (d.diagnostics as LspDiagnostic[]) || [];
            setLspDiagnostics((prev) => ({ ...prev, [filePath]: diags }));
          } else if (msg.type === "lsp.server_status") {
            const d = msg.data || msg;
            const serverId = `${d.language_id || ""}:${d.pid || ""}`;
            setLspServerStatus((prev) => ({
              ...prev,
              [serverId]: d as unknown as LspServerInfo,
            }));
          } else if (msg.type === "lsp.code_health") {
            const d = (msg.data || msg) as unknown as LspCodeHealth;
            setLspCodeHealth(d);
            setLspCodeHealthTrend((prev) => [...prev.slice(-19), d.score]);
          } else if (msg.type === "lsp.cross_worker_alert") {
            const d = (msg.data || msg) as unknown as LspCrossWorkerAlert;
            d.timestamp = (msg.timestamp as string) || new Date().toISOString();
            setLspCrossWorkerAlerts((prev) => [d, ...prev].slice(0, 50));
          } else if (msg.type === "expertise_lesson_propagated" || msg.type === "expertise_record_promoted" || msg.type === "expertise_lesson_created") {
            // MELS expertise events — push to events feed for observability
            const d = msg.data || msg;
            setEvents((prev) => [
              ...prev,
              {
                type: msg.type,
                timestamp: (msg.timestamp as string) || new Date().toISOString(),
                data: d as Record<string, unknown>,
              } as AgentEvent,
            ]);
            // Also surface as output for terminal visibility
            const label = msg.type === "expertise_lesson_propagated"
              ? `[MELS] Lesson propagated to worker-${d.worker_id}: ${(d.content as string || "").slice(0, 80)}`
              : msg.type === "expertise_record_promoted"
              ? `[MELS] Lesson ${d.lesson_id} promoted to permanent record ${d.record_id}`
              : `[MELS] New lesson: ${(d.content as string || "").slice(0, 100)}`;
            setOutput((prev) => [...prev, label]);
          } else if (msg.type === "lsp.merge_validation") {
            const d = msg.data || msg;
            setEvents((prev) => [
              ...prev,
              {
                type: "lsp.merge_validation",
                timestamp: (msg.timestamp as string) || new Date().toISOString(),
                data: d as Record<string, unknown>,
              } as AgentEvent,
            ]);
          } else if (msg.type && msg.timestamp && msg.type !== "output" && msg.type !== "status") {
            const safeData: Record<string, unknown> = {};
            if (msg.data && typeof msg.data === "object") {
              for (const [k, v] of Object.entries(msg.data as Record<string, unknown>)) {
                safeData[k] = (v !== null && typeof v === "object") ? JSON.stringify(v) : v;
              }
            }
            setEvents((prev) => {
              const next = [...prev, { type: msg.type, timestamp: msg.timestamp, data: msg.data && typeof msg.data === "object" ? safeData : (msg.data || {}) } as AgentEvent];
              return next;
            });
          }
        } catch {
          const raw = typeof event.data === "string" ? event.data : JSON.stringify(event.data);
          setOutput((prev) => [...prev, raw]);
        }
      };

      ws.onerror = () => {
        setWsConnected(false);
        if (reconnectAttempts.current >= 10) {
          onError("WebSocket connection failed. Is the backend running?");
          setOutput((prev) => [...prev, "WebSocket connection failed. Is the backend running?"]);
          stopTaskPolling();
        }
      };

      ws.onclose = () => {
        setWsConnected(false);
        // Don't reconnect if session ended normally (completed/error)
        if (sessionEndedRef.current) return;
        if (reconnectAttempts.current < 10) {
          const delay = Math.min(1000 * Math.pow(2, reconnectAttempts.current), 30000);
          reconnectAttempts.current += 1;
          setOutput((prev) => [
            ...prev,
            `WebSocket disconnected. Reconnecting in ${Math.round(delay / 1000)}s (attempt ${reconnectAttempts.current}/10)...`,
          ]);
          reconnectTimerRef.current = setTimeout(() => {
            const rws = new WebSocket(WS_URL);
            wsRef.current = rws;
            rws.onopen = () => {
              reconnectAttempts.current = 0;
              setWsConnected(true);
              setOutput((prev) => [...prev, "WebSocket reconnected."]);
              if (config.project_dir) {
                fetchTasks(config.project_dir);
                fetchOutputLog(config.project_dir).then((lines) => {
                  if (lines.length > 0) {
                    setOutput((prev) => [...prev, "--- Backfilled output ---", ...lines.slice(-50), "--- End backfill ---"]);
                  }
                });
              }
            };
            rws.onmessage = ws.onmessage;
            rws.onerror = ws.onerror;
            rws.onclose = ws.onclose;
          }, delay);
        } else {
          stopTaskPolling();
        }
      };
    },
    [
      onStatusRunning,
      onStatusCompleted,
      onError,
      onWarning,
      onBrowserNotification,
      onWorktreeReady,
      onApprovalRequest,
      onTaskListReady,
      fetchTasks,
      fetchOutputLog,
      stopTaskPolling,
    ]
  );

  return {
    wsRef,
    wsConnected,
    connect,
    close,
    send,
    setOutput,
    setEvents,
    setSessionStats,
    output,
    events,
    sessionStats,
    qualityGates,
    triageResults,
    monitorHealth,
    monitorTrend,
    workerTokenMap,
    watchdogEvents,
    circuitBreakerStatus,
    // LSP
    lspDiagnostics,
    lspServerStatus,
    lspCodeHealth,
    lspCodeHealthTrend,
    lspCrossWorkerAlerts,
  };
}
