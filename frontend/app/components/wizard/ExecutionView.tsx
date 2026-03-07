"use client";

import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { StatusBar, type TokenUsage, type WorkerContext } from "../StatusBar";
import { AgentContextBar, type ContextWorker } from "../AgentContextBar";
import { SteeringBar } from "../SteeringBar";
import type { SwarmWorker } from "../SteeringBar";
import { TaskChecklist } from "../TaskChecklist";
import { DetailDrawer } from "../DetailDrawer";
import { ActivityFeed } from "../ActivityFeed";
import { ApprovalGate } from "../ApprovalGate";
import { NotificationSettings } from "../NotificationSettings";
import ThinkingBar from "./ThinkingBar";
import type {
  AgentStatus,
  Mode,
  TaskData,
  RunConfig,
  AgentEvent,
  SessionStats,
  ApprovalRequestData,
  WorktreeInfo,
} from "../../hooks/useSwarmWeaver";

interface ExecutionViewProps {
  state: {
    status: AgentStatus;
    output: string[];
    tasks: TaskData | null;
    currentProject: string;
    selectedMode: Mode | null;
    setSelectedMode?: (mode: Mode) => void;
    events: AgentEvent[];
    sessionStats: SessionStats | null;
    approvalRequest: ApprovalRequestData | null;
    worktreeInfo: WorktreeInfo | null;
    wsConnected?: boolean;
    stop: () => void;
    run: (config: RunConfig) => void;
    sendSteering: (message: string, type?: string) => void;
    resolveApproval: (decision: string, feedback?: string) => void;
    mergeWorktree: () => void;
    discardWorktree: () => void;
    goBack: () => void;
    lastConfig?: RunConfig | null;
    workerTokenMap?: Record<number, { input: number; output: number; cacheRead: number; cacheCreation: number }>;
  };
}

/* ---- Elapsed time hook ---- */

function useElapsedTime(startTime: string | undefined, isRunning: boolean): string {
  const [elapsed, setElapsed] = useState("");
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!startTime || !isRunning) {
      if (!isRunning) setElapsed("");
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      return;
    }

    function update() {
      const start = new Date(startTime!).getTime();
      const diffSec = Math.max(0, Math.floor((Date.now() - start) / 1000));
      const h = Math.floor(diffSec / 3600);
      const m = Math.floor((diffSec % 3600) / 60);
      const s = diffSec % 60;
      setElapsed(
        h > 0
          ? `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`
          : `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`
      );
    }

    update();
    intervalRef.current = setInterval(update, 1000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [startTime, isRunning]);

  return elapsed;
}

/* ---- Main component ---- */

export function ExecutionView({ state }: ExecutionViewProps) {
  const {
    status,
    output,
    tasks,
    currentProject,
    selectedMode,
    setSelectedMode,
    events,
    sessionStats,
    approvalRequest,
    worktreeInfo,
    wsConnected,
    stop,
    run,
    sendSteering,
    resolveApproval,
    mergeWorktree,
    discardWorktree,
    goBack,
    lastConfig,
  } = state;

  // Model comes from run config (Omnibar selection) — no hardcoded fallback
  const [selectedModel, setSelectedModel] = useState<string | undefined>(lastConfig?.model);
  useEffect(() => {
    if (lastConfig?.model) setSelectedModel(lastConfig.model);
  }, [lastConfig?.model]);
  // When lastConfig has no model (e.g. before run), fetch from project settings (user's saved choice)
  useEffect(() => {
    if (lastConfig?.model) return;
    if (!currentProject) return;
    let cancelled = false;
    fetch(`/api/projects/settings?path=${encodeURIComponent(currentProject)}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (cancelled) return;
        const model = d?.settings?.default_model;
        if (model && typeof model === "string") setSelectedModel(model);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [currentProject, lastConfig?.model]);

  const isRunning = status === "running" || status === "starting";
  const elapsed = useElapsedTime(sessionStats?.start_time, isRunning);

  // Drawer state
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerSection, setDrawerSection] = useState<string | null>(null);
  const [tasksExpanded, setTasksExpanded] = useState(false);


  // Shortcuts modal
  const [shortcutsOpen, setShortcutsOpen] = useState(false);

  // Notifications modal
  const [showNotifications, setShowNotifications] = useState(false);

  // Health modal
  const [healthOpen, setHealthOpen] = useState(false);
  const [healthData, setHealthData] = useState<Record<string, unknown> | null>(null);
  const [healthLoading, setHealthLoading] = useState(false);

  const fetchHealth = useCallback(() => {
    setHealthLoading(true);
    setHealthOpen(true);
    const url = currentProject
      ? `/api/doctor?path=${encodeURIComponent(currentProject)}`
      : "/api/doctor";
    fetch(url)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (d) setHealthData(d); })
      .catch(() => setHealthData({ overall: "fail", checks: [], error: "Could not reach backend" }))
      .finally(() => setHealthLoading(false));
  }, [currentProject]);

  // Cost + token tracking — real-time from WS events, fallback to sessionStats
  const { cost, wsTokenUsage } = useMemo(() => {
    // Cost: prefer real_cost_usd from budget_update, then sessionStats cumulative
    const budgetEvents = events.filter((e) => e.type === "budget_update");
    const latestBudget = budgetEvents[budgetEvents.length - 1];
    const costVal = latestBudget
      ? ((latestBudget.data.real_cost_usd as number) || (latestBudget.data.estimated_cost_usd as number) || (latestBudget.data.total_cost as number) || 0)
      : (sessionStats?.total_cost_usd ?? 0);

    // Tokens: prefer sessionStats (updated in real-time by token_update events)
    // then fall back to budget_update totals (updated at session end)
    const stInput = sessionStats?.input_tokens ?? 0;
    const stOutput = sessionStats?.output_tokens ?? 0;
    const stCacheRead = sessionStats?.cache_read_tokens ?? 0;
    if (stInput > 0 || stOutput > 0 || stCacheRead > 0) {
      return {
        cost: costVal,
        wsTokenUsage: {
          inputTokens: stInput,
          outputTokens: stOutput,
          cachedTokens: stCacheRead,
        },
      };
    }
    if (latestBudget) {
      return {
        cost: costVal,
        wsTokenUsage: {
          inputTokens: (latestBudget.data.total_input_tokens as number) ?? 0,
          outputTokens: (latestBudget.data.total_output_tokens as number) ?? 0,
          cachedTokens: 0,
        },
      };
    }
    return { cost: costVal, wsTokenUsage: null };
  }, [events, sessionStats]);

  // Poll /api/costs for detailed token breakdown (includes cache tokens)
  const [costsApi, setCostsApi] = useState<{ input: number; cached: number; output: number } | null>(null);
  useEffect(() => {
    if (!currentProject) return;
    let cancelled = false;
    const poll = () => {
      fetch(`/api/costs?path=${encodeURIComponent(currentProject)}`)
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => {
          if (!cancelled && d?.token_breakdown) {
            setCostsApi({
              input: d.token_breakdown.input_tokens ?? 0,
              cached: d.token_breakdown.cache_read_tokens ?? 0,
              output: d.token_breakdown.output_tokens ?? 0,
            });
          }
        })
        .catch(() => {});
    };
    poll();
    const id = setInterval(poll, 12000);
    return () => { cancelled = true; clearInterval(id); };
  }, [currentProject]);

  const tokenUsage: TokenUsage = useMemo(() => {
    // costsApi (polled from /api/costs) — keep each field separate
    if (costsApi && (costsApi.input > 0 || costsApi.output > 0)) {
      return { inputTokens: costsApi.input, cachedTokens: costsApi.cached, outputTokens: costsApi.output };
    }
    // wsTokenUsage: real-time from token_update events — includes cache_read tokens
    if (wsTokenUsage && (wsTokenUsage.inputTokens > 0 || wsTokenUsage.outputTokens > 0 || (wsTokenUsage.cachedTokens ?? 0) > 0)) {
      return {
        inputTokens: wsTokenUsage.inputTokens,
        cachedTokens: wsTokenUsage.cachedTokens ?? 0,
        outputTokens: wsTokenUsage.outputTokens,
      };
    }
    return { inputTokens: 0, cachedTokens: 0, outputTokens: 0 };
  }, [costsApi, wsTokenUsage]);

  // Task counts
  const taskList = tasks?.tasks ?? [];
  const tasksDone = taskList.filter(
    (t) => t.status === "done" || t.status === "completed" || t.status === "verified"
  ).length;
  const tasksTotal = taskList.length;

  // Smart swarm: track active workers from worker_spawned events
  const swarmWorkers = useMemo<SwarmWorker[]>(() => {
    return events
      .filter((e) => e.type === "worker_spawned")
      .map((e) => ({
        id: e.data.worker_id as number,
        name: (e.data.name as string) || `worker-${e.data.worker_id}`,
      }))
      // deduplicate by id
      .filter((w, idx, arr) => arr.findIndex((x) => x.id === w.id) === idx);
  }, [events]);

  // Selected agent: null = main/orchestrator (default), number = specific worker
  const [selectedWorkerId, setSelectedWorkerId] = useState<number | null>(null);

  // Worker spawn timestamps (worker_id -> ISO timestamp) for per-worker elapsed time
  const workerSpawnTimes = useMemo<Record<number, string>>(() => {
    const map: Record<number, string> = {};
    for (const ev of events) {
      if (ev.type === "worker_spawned") {
        const wId = ev.data.worker_id as number;
        if (!(wId in map)) map[wId] = ev.timestamp;
      }
    }
    return map;
  }, [events]);

  // Per-worker elapsed time — updates every second for the selected worker
  const selectedWorkerSpawnTime = selectedWorkerId !== null ? workerSpawnTimes[selectedWorkerId] : undefined;
  const workerElapsed = useElapsedTime(selectedWorkerSpawnTime, isRunning);

  // Full worker states from swarm API (for AgentContextBar + workerContext)
  const [workerDetailStates, setWorkerDetailStates] = useState<ContextWorker[]>([]);
  const [workerCostsByName, setWorkerCostsByName] = useState<Record<string, number>>({});
  const [costsByAgent, setCostsByAgent] = useState<Record<string, { cost: number; input_tokens?: number; output_tokens?: number; cache_read_tokens?: number }>>({});

  // Per-worker real-time token tracking from WebSocket
  const workerTokenMap = state.workerTokenMap ?? {};

  useEffect(() => {
    if (!currentProject || swarmWorkers.length === 0) return;
    let cancelled = false;
    const enc = encodeURIComponent(currentProject);

    const poll = () => {
      fetch(`/api/swarm/status?path=${enc}`)
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => {
          if (cancelled || !d?.workers) return;
          setWorkerDetailStates(
            d.workers.map((w: Record<string, unknown>) => ({
              worker_id: w.worker_id as number,
              name: (w.name as string) || `worker-${w.worker_id}`,
              status: w.status as string,
              capability: w.capability as string | undefined,
              current_task: w.current_task as string | null,
              completed_tasks: (w.completed_tasks as string[]) || [],
              assigned_task_ids: (w.assigned_task_ids as string[]) || [],
              file_scope: (w.file_scope as string[]) || [],
            }))
          );
        })
        .catch(() => {});

      fetch(`/api/costs/by-agent?path=${enc}`)
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => {
          if (cancelled || !d?.by_agent) return;
          const costMap: Record<string, number> = {};
          const agentMap: Record<string, { cost: number; input_tokens?: number; output_tokens?: number; cache_read_tokens?: number }> = {};
          for (const [name, info] of Object.entries(d.by_agent)) {
            const a = info as { cost?: number; total_cost?: number; input_tokens?: number; output_tokens?: number; cache_read_tokens?: number };
            const c = a.cost ?? a.total_cost ?? 0;
            costMap[name] = c;
            agentMap[name] = {
              cost: c,
              input_tokens: a.input_tokens,
              output_tokens: a.output_tokens,
              cache_read_tokens: a.cache_read_tokens,
            };
          }
          setWorkerCostsByName(costMap);
          setCostsByAgent(agentMap);
        })
        .catch(() => {});
    };

    poll();
    const id = setInterval(poll, 5000);
    return () => { cancelled = true; clearInterval(id); };
  }, [currentProject, swarmWorkers.length]);

  // Task list scoped to selected worker (or full when orchestrator)
  const effectiveTasks = useMemo(() => {
    if (!tasks) return null;
    if (selectedWorkerId === null) return tasks;
    const w = workerDetailStates.find((x) => x.worker_id === selectedWorkerId);
    const ids = new Set(w?.assigned_task_ids ?? []);
    if (ids.size === 0) return tasks;
    const filtered = (tasks.tasks ?? []).filter((t) => ids.has(t.id));
    return { ...tasks, tasks: filtered };
  }, [tasks, selectedWorkerId, workerDetailStates]);

  const effectiveTaskList = effectiveTasks?.tasks ?? [];
  const tasksDoneForView = effectiveTaskList.filter(
    (t) => t.status === "done" || t.status === "completed" || t.status === "verified"
  ).length;
  const tasksTotalForView = effectiveTaskList.length;

  // Derive worker context for the selected worker (overrides StatusBar stats)
  const workerContext = useMemo<WorkerContext | null>(() => {
    if (selectedWorkerId === null) return null;
    const w = workerDetailStates.find((x) => x.worker_id === selectedWorkerId);
    if (!w) return null;
    const workerName = w.name || `worker-${selectedWorkerId}`;
    const agentCosts = costsByAgent[workerName];
    const cap = w.capability || "builder";
    const assignedIds = new Set(w.assigned_task_ids ?? []);
    const doneCount = assignedIds.size > 0
      ? effectiveTaskList.filter((t) => t.status === "done" || t.status === "completed" || t.status === "verified").length
      : (w.completed_tasks?.length ?? 0);
    const totalKnown = assignedIds.size > 0 ? assignedIds.size : doneCount + (w.current_task ? 1 : 0);
    // Prefer real-time token tracking from WebSocket, fall back to polled API data
    const liveTokens = workerTokenMap[selectedWorkerId];
    const tokenUsage = liveTokens
      ? {
          inputTokens: liveTokens.input,
          cachedTokens: liveTokens.cacheRead,
          outputTokens: liveTokens.output,
        }
      : agentCosts && (agentCosts.input_tokens ?? agentCosts.output_tokens ?? agentCosts.cache_read_tokens) != null
        ? {
            inputTokens: agentCosts.input_tokens ?? 0,
            cachedTokens: agentCosts.cache_read_tokens ?? 0,
            outputTokens: agentCosts.output_tokens ?? 0,
          }
        : undefined;
    // Estimate cost from live tokens if API cost not available yet
    // Sonnet pricing: $3/M input, $0.30/M cache_read, $15/M output
    const liveCost = liveTokens
      ? (liveTokens.input / 1_000_000) * 3 + (liveTokens.cacheRead / 1_000_000) * 0.3 + (liveTokens.output / 1_000_000) * 15
      : 0;
    const workerCost = workerCostsByName[workerName] || liveCost;
    return {
      label: workerName,
      capability: cap,
      cost: workerCost,
      tasksDone: doneCount,
      tasksTotal: totalKnown,
      workerStatus: w.status,
      fileCount: w.file_scope?.length ?? 0,
      elapsed: workerElapsed || undefined,
      tokenUsage,
    };
  }, [selectedWorkerId, workerDetailStates, workerCostsByName, costsByAgent, workerElapsed, effectiveTaskList, workerTokenMap]);

  // Agent count (from latest swarm events)
  const agentCount = useMemo(() => {
    const healthEvents = events.filter((e) => e.type === "agent_health");
    if (healthEvents.length === 0) return undefined;
    const agentNames = new Set(
      healthEvents.map((e) => (e.data.agent_name as string) || (e.data.worker_id as string))
    );
    return agentNames.size > 1 ? agentNames.size : undefined;
  }, [events]);

  const isSwarmMode = (agentCount ?? 0) > 1;

  // Extended thinking state — active when thinking_delta/thinking_block arrives, cleared on next tool_start/text_delta
  const isThinking = useMemo(() => {
    if (!isRunning) return false;
    // Check last few events — thinking is active if the most recent non-token event is thinking
    for (let i = events.length - 1; i >= Math.max(0, events.length - 10); i--) {
      const t = events[i].type;
      if (t === "thinking_block" || t === "thinking_delta") return true;
      if (t === "tool_start" || t === "text_delta" || t === "tool_done") return false;
    }
    return false;
  }, [events, isRunning]);

  // Project name from path
  const projectName = currentProject ? currentProject.split("/").filter(Boolean).pop() || currentProject : "Project";

  // Auto-open drawer on approval request
  const prevApprovalRef = useRef<string | null>(null);
  useEffect(() => {
    if (approvalRequest && approvalRequest.request_id !== prevApprovalRef.current) {
      prevApprovalRef.current = approvalRequest.request_id;
      setDrawerSection("tasks");
      setDrawerOpen(true);
    }
  }, [approvalRequest]);

  // Auto-open drawer on error events
  const prevErrorCountRef = useRef(0);
  useEffect(() => {
    const errorCount = events.filter(
      (e) => e.type === "error" || e.type === "tool_error"
    ).length;
    if (errorCount > prevErrorCountRef.current && errorCount > 0) {
      setDrawerSection("errors");
      setDrawerOpen(true);
    }
    prevErrorCountRef.current = errorCount;
  }, [events]);

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Ctrl+. → toggle drawer
      if ((e.ctrlKey || e.metaKey) && e.key === ".") {
        e.preventDefault();
        setDrawerOpen((v) => !v);
        return;
      }
      // Escape → close drawer or modal
      if (e.key === "Escape") {
        if (drawerOpen) {
          setDrawerOpen(false);
          return;
        }
      }
    };

    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [drawerOpen]);

  // Drawer callbacks
  const openDrawerSection = useCallback((section: string) => {
    setDrawerSection(section);
    setDrawerOpen(true);
  }, []);

  const handleContinue = useCallback(() => {
    if (lastConfig) {
      run({
        ...lastConfig,
        mode: selectedMode ?? lastConfig.mode,
        model: selectedModel ?? lastConfig.model,
        no_resume: false,
        task_input: "",
      });
    }
  }, [lastConfig, run, selectedMode, selectedModel]);

  return (
    <div className="flex flex-col h-full w-full bg-[var(--color-surface-base)] relative">
      {/* StatusBar — full width, outside container */}
      <StatusBar
        mode={selectedMode}
        projectName={projectName}
        projectPath={currentProject}
        currentPhase={sessionStats?.current_phase || ""}
        cost={cost}
        tasksDone={tasksDoneForView}
        tasksTotal={tasksTotalForView}
        elapsed={elapsed}
        status={status}
        agentCount={agentCount}
        tokenUsage={tokenUsage}
        onBack={goBack}
        worktreeInfo={worktreeInfo}
        onInspectWorktree={worktreeInfo ? () => openDrawerSection("files") : undefined}
        onMergeWorktree={worktreeInfo ? mergeWorktree : undefined}
        onDiscardWorktree={worktreeInfo ? discardWorktree : undefined}
        onHealth={fetchHealth}
        onNotifications={() => setShowNotifications(true)}
        onShortcuts={() => setShortcutsOpen(true)}
        tasksExpanded={tasksExpanded}
        onToggleTasksExpanded={() => setTasksExpanded((v) => !v)}
        workerContext={workerContext}
        onOpenDrawer={() => setDrawerOpen(true)}
      />

      {/* Agent context bar — shows worker selector when swarm is running */}
      <AgentContextBar
        workers={workerDetailStates.length > 0 ? workerDetailStates : swarmWorkers.map((w) => ({ worker_id: w.id, name: w.name }))}
        selectedWorkerId={selectedWorkerId}
        onSelectWorker={setSelectedWorkerId}
        mainStatus={status}
      />

      {/* TaskChecklist — expanded list only, shown when [Show all] clicked */}
      {tasksTotalForView > 0 && (
        <TaskChecklist
          tasks={effectiveTaskList}
          expanded={tasksExpanded}
          onTaskClick={() => {
            setDrawerSection("tasks");
            setDrawerOpen(true);
          }}
        />
      )}

      {/* Scrollable main area with bottom padding for floating input */}
      <div className="flex-1 overflow-y-auto tui-scrollbar pb-48 relative">
        <div className="max-w-6xl mx-auto w-full">
          <ActivityFeed
            output={output}
            events={events}
            className="h-full"
            filterWorkerId={swarmWorkers.length > 0 ? selectedWorkerId : undefined}
          />
        </div>
      </div>

      {/* SteeringBar — absolute bottom with gradient fade */}
      <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-[var(--color-surface-base)] via-[var(--color-surface-base)] to-transparent pt-12 pb-6 px-6 z-20">
        <div className="max-w-6xl mx-auto w-full">
          {/* Extended thinking indicator — above steering wheel */}
          {isThinking && (
            <ThinkingBar
              agentName={selectedWorkerId != null ? `Worker ${selectedWorkerId}` : "Agent"}
              label="Extended thinking..."
              active={true}
            />
          )}
          <SteeringBar
            status={status}
            onSend={sendSteering}
            onStop={stop}
            onContinue={lastConfig ? handleContinue : undefined}
            selectedModel={selectedModel}
            onModelChange={setSelectedModel}
            mode={selectedMode}
            onModeChange={setSelectedMode}
            swarmWorkers={swarmWorkers.length > 0 ? swarmWorkers : undefined}
            selectedWorkerId={selectedWorkerId}
            onSelectWorker={setSelectedWorkerId}
          />
        </div>
      </div>

      {/* Approval Gate modal */}
      {approvalRequest && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="w-full max-w-lg">
            <ApprovalGate
              request={approvalRequest}
              onResolve={resolveApproval}
            />
          </div>
        </div>
      )}

      {/* DetailDrawer */}
      <DetailDrawer
        isOpen={drawerOpen}
        onClose={() => {
          setDrawerOpen(false);
          setDrawerSection(null);
        }}
        onToggle={() => setDrawerOpen((v) => !v)}
        tasks={effectiveTasks ?? tasks}
        events={events}
        selectedWorkerId={selectedWorkerId}
        sessionStats={sessionStats}
        output={output}
        worktreeInfo={worktreeInfo}
        projectPath={currentProject}
        isSwarmMode={isSwarmMode}
        approvalRequest={approvalRequest}
        activeSection={drawerSection}
      />

      {/* Notification settings modal */}
      {showNotifications && (
        <NotificationSettings
          projectDir={currentProject}
          onClose={() => setShowNotifications(false)}
        />
      )}

      {/* Shortcuts modal */}
      {shortcutsOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setShortcutsOpen(false)}>
          <div
            className="w-full max-w-md bg-[var(--color-surface-base)] border border-[var(--color-border-default)] shadow-2xl font-mono"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--color-border-subtle)] bg-[var(--color-surface-1)]">
              <div className="flex items-center gap-2">
                <span className="text-[var(--color-accent)] text-xs">{"\u2328"}</span>
                <span className="text-xs text-[var(--color-text-primary)] font-bold uppercase tracking-wider">Keyboard Shortcuts</span>
              </div>
              <button
                onClick={() => setShortcutsOpen(false)}
                className="w-6 h-6 flex items-center justify-center hover:bg-[var(--color-surface-2)] transition-colors text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
              >
                {"\u2717"}
              </button>
            </div>
            <div className="p-4 space-y-2">
              <ShortcutRow keys="Ctrl + ." desc="Toggle detail drawer" />
              <ShortcutRow keys="Escape" desc="Close drawer / modal" />
              <ShortcutRow keys="Ctrl + Enter" desc="Send steering message" />
              <div className="border-t border-[var(--color-border-subtle)] my-3" />
              <div className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wider mb-2">Landing Page</div>
              <ShortcutRow keys="Enter" desc="Launch agent" />
              <ShortcutRow keys="Shift + Enter" desc="New line in text area" />
            </div>
          </div>
        </div>
      )}

      {/* Health modal */}
      {healthOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setHealthOpen(false)}>
          <div
            className="w-full max-w-lg bg-[var(--color-surface-base)] border border-[var(--color-border-default)] shadow-2xl font-mono max-h-[70vh] flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--color-border-subtle)] bg-[var(--color-surface-1)] shrink-0">
              <div className="flex items-center gap-2">
                <span className="text-[var(--color-accent)] text-xs">{"\u2665"}</span>
                <span className="text-xs text-[var(--color-text-primary)] font-bold uppercase tracking-wider">System Health</span>
                {healthData && (
                  <span className={`text-[10px] px-1.5 py-0.5 border ${
                    healthData.overall === "pass" ? "border-green-700 text-green-400 bg-green-900/20" :
                    healthData.overall === "warn" ? "border-yellow-700 text-yellow-400 bg-yellow-900/20" :
                    "border-red-700 text-red-400 bg-red-900/20"
                  }`}>
                    {typeof healthData.overall === "string" ? healthData.overall.toUpperCase() : "UNKNOWN"}
                  </span>
                )}
              </div>
              <button
                onClick={() => setHealthOpen(false)}
                className="w-6 h-6 flex items-center justify-center hover:bg-[var(--color-surface-2)] transition-colors text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
              >
                {"\u2717"}
              </button>
            </div>
            <div className="flex-1 overflow-y-auto tui-scrollbar p-4 space-y-2">
              {healthLoading && <p className="text-xs text-[var(--color-text-muted)]">Running health checks...</p>}
              {!!healthData?.error && (
                <p className="text-xs text-[var(--color-error)]">{String(healthData.error)}</p>
              )}
              {healthData && Array.isArray(healthData.checks) && healthData.checks.length > 0 && (
                <>
                  <div className="flex items-center gap-4 text-[10px] text-[var(--color-text-muted)] mb-2">
                    <span className="text-green-400">{Number(healthData.passed) || 0} passed</span>
                    {(Number(healthData.warned) || 0) > 0 && <span className="text-yellow-400">{Number(healthData.warned)} warned</span>}
                    {(Number(healthData.failed) || 0) > 0 && <span className="text-red-400">{Number(healthData.failed)} failed</span>}
                  </div>
                  {(healthData.checks as Record<string, unknown>[]).map((check: Record<string, unknown>, i: number) => (
                    <div key={i} className="p-2 bg-[var(--color-surface-1)] border border-[var(--color-border-subtle)]">
                      <div className="flex items-center gap-2">
                        <span className={`text-xs ${
                          check.status === "pass" ? "text-green-400" :
                          check.status === "warn" ? "text-yellow-400" :
                          "text-red-400"
                        }`}>
                          {check.status === "pass" ? "\u2713" : check.status === "warn" ? "!" : "\u2717"}
                        </span>
                        <span className="text-xs text-[var(--color-text-primary)] flex-1">{String(check.name || check.check || "")}</span>
                        {!!check.category && (
                          <span className="text-[10px] text-[var(--color-text-muted)] px-1 py-0.5 border border-[var(--color-border-default)] bg-[var(--color-surface-2)]">{String(check.category)}</span>
                        )}
                      </div>
                      {!!check.message && <p className="text-[10px] text-[var(--color-text-secondary)] mt-1 pl-5">{String(check.message)}</p>}
                    </div>
                  ))}
                </>
              )}
              {healthData && (!Array.isArray(healthData.checks) || healthData.checks.length === 0) && !healthData.error && (
                <p className="text-xs text-[var(--color-text-muted)]">No health checks available</p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ---- Shortcut row helper ---- */

function ShortcutRow({ keys, desc }: { keys: string; desc: string }) {
  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-xs text-[var(--color-text-secondary)]">{desc}</span>
      <div className="flex items-center gap-1">
        {keys.split(" + ").map((k, i) => (
          <span key={i}>
            {i > 0 && <span className="text-[var(--color-text-muted)] text-[10px] mx-0.5">+</span>}
            <span className="text-[10px] text-[var(--color-text-secondary)] bg-[var(--color-surface-1)] border border-[var(--color-border-default)] px-2 py-0.5">{k}</span>
          </span>
        ))}
      </div>
    </div>
  );
}
