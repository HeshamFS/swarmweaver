"use client";

import { useState, useCallback, useRef, useEffect, useMemo } from "react";
import { useWebSocket } from "./useWebSocket";
import {
  generateSpec,
  generatePlan,
  prepareProject,
} from "../utils/lightweightCalls";
import { useArchitectStream } from "./useArchitectStream";
import type { ArchitectPhase } from "./useArchitectStream";
import { usePlanStream } from "./usePlanStream";
import type { PlanPhase } from "./usePlanStream";
import { useWizardStream } from "./useWizardStream";
import type { WizardPhase } from "./useWizardStream";

// --- Phase mapping helpers (unified WizardPhase → existing separate phase types) ---

function _toArchitectPhase(wp: WizardPhase): ArchitectPhase {
  if (wp === "qa" || wp === "qa_questions" || wp === "qa_complete") return "idle";
  if (wp === "research") return "research";
  // Non-greenfield analysis phases also map to "research" to show tool events
  if (wp === "analyzing" || wp === "investigating" || wp === "auditing" || wp === "scanning") return "research";
  if (wp === "questions") return "questions";
  if (wp === "generating" || wp === "generating_strategy" || wp === "generating_report" || wp === "generating_security") return "generating";
  if (wp === "spec_complete" || wp === "strategy_complete" || wp === "report_complete" || wp === "security_complete") return "complete";
  if (wp === "error") return "error";
  return "idle";
}

function _toPlanPhase(wp: WizardPhase): PlanPhase {
  if (wp === "plan_analyzing") return "analyzing";
  if (wp === "plan_complete") return "complete";
  if (wp === "error") return "error";
  return "idle";
}

// --- Types ---

export type Mode = "greenfield" | "feature" | "refactor" | "fix" | "evolve" | "security";

export type AgentStatus = "idle" | "starting" | "running" | "completed" | "error";

export type WizardStep = "landing" | "qa" | "architect-review" | "strategy-review" | "report-review" | "plan-review" | "security-review" | "execute";

export interface Task {
  id: string;
  title: string;
  description?: string;
  category?: string;
  status: string;
  priority?: number;
  depends_on?: string[];
  acceptance_criteria?: string[];
  files_affected?: string[];
  notes?: string;
  completed_at?: string;
  verification_status?: string;
  verification_attempts?: number;
  last_verification_error?: string;
  external_id?: string;
  external_url?: string;
  external_source?: string;
}

export interface TaskData {
  metadata: { mode?: string; version?: string };
  tasks: Task[];
}

export interface ProjectInfo {
  name: string;
  path: string;
  has_tasks: boolean;
  mode: string | null;
  done: number;
  total: number;
  percentage: number;
  last_modified: string | null;
}

export interface PhaseModels {
  architect?: string;   // greenfield spec generation
  plan?: string;        // task list / planning
  code?: string;        // implementation loop
}

export interface RunConfig {
  mode: Mode;
  project_dir: string;
  task_input: string;
  spec?: string;
  idea?: string;
  model: string;
  phase_models?: PhaseModels;
  max_iterations?: number;
  no_resume: boolean;
  parallel?: number;
  smart_swarm?: boolean;
  budget?: number;
  max_hours?: number;
  approval_gates?: boolean;
  auto_pr?: boolean;
  worktree?: boolean;
  overrides?: { directive: string; value?: string | null; active: boolean }[];
  github_sync_pull?: boolean;
  github_sync_push?: boolean;
  monitor_enabled?: boolean;
  monitor_interval?: number;
}

export interface WorktreeInfo {
  run_id: string;
  branch: string;
  original_project_dir: string;
  worktree_path: string;
  files_changed: number;
  insertions: number;
  deletions: number;
  diff_stat: string;
}

export interface ApprovalRequestData {
  request_id: string;
  gate_type: string;
  summary: string;
  tasks_completed: string[];
  tasks_remaining: string[];
  git_diff_summary: string;
  timestamp: string;
}

export interface ProjectStatus {
  exists: boolean;
  has_tasks: boolean;
  resumable: boolean;
  mode: Mode | null;
  done: number;
  total: number;
  percentage: number;
  has_progress_notes: boolean;
  run_config?: {
    mode?: string;
    smart_swarm?: boolean;
    parallel?: number;
    max_workers?: number;
    budget?: number;
    max_hours?: number;
    phase_models?: PhaseModels;
    approval_gates?: boolean;
    overrides?: { directive: string; value?: string | null; active: boolean }[];
  } | null;
}

export interface AgentEvent {
  type: string;
  timestamp: string;
  data: Record<string, unknown>;
}

export interface SessionStats {
  tool_call_count: number;
  tool_counts: Record<string, number>;
  error_count: number;
  file_touches: Record<string, number>;
  current_phase: string;
  session_number: number;
  start_time: string;
  // Native mode additional fields (from SDK ResultMessage / token_update)
  total_cost_usd?: number;
  input_tokens?: number;
  output_tokens?: number;
  cache_read_tokens?: number;      // tokens served from prompt cache (shows caching efficiency)
  cache_creation_tokens?: number;  // tokens spent writing to cache
  duration_s?: number;
}

export interface SecurityFinding {
  id: string;
  severity: "critical" | "high" | "medium" | "low" | "info";
  category: string;
  title: string;
  description: string;
  file?: string;
  line?: number;
  recommendation: string;
  acceptance_criteria: string[];
}

export interface SecurityReport {
  metadata: {
    scan_date: string;
    focus_area: string;
    project_path?: string;
  };
  findings: SecurityFinding[];
  summary: Record<string, number>;
}

// --- localStorage project cache ---

const RECENT_PROJECTS_KEY = "swarmweaver-recent-projects";
const MAX_CACHED_PROJECTS = 10;

function loadCachedProjects(): ProjectInfo[] {
  try {
    if (typeof window === "undefined") return [];
    const raw = localStorage.getItem(RECENT_PROJECTS_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveCachedProjects(projects: ProjectInfo[]) {
  try {
    if (typeof window === "undefined") return;
    localStorage.setItem(
      RECENT_PROJECTS_KEY,
      JSON.stringify(projects.slice(0, MAX_CACHED_PROJECTS))
    );
  } catch {
    // Ignore quota errors
  }
}

// --- Hook ---

export function useSwarmWeaver(tabId: string = "default") {
  // Wizard navigation state
  const [wizardStep, setWizardStep] = useState<WizardStep>("landing");
  const [selectedMode, setSelectedMode] = useState<Mode | null>(null);
  const [cliMode, setCliMode] = useState(false);
  const [generatedSpec, setGeneratedSpec] = useState<string | null>(null);
  const [isLightweightLoading, setIsLightweightLoading] = useState(false);
  const [codebaseProfile, setCodebaseProfile] = useState<Record<string, unknown> | null>(null);
  const [securityReport, setSecurityReport] = useState<SecurityReport | null>(null);
  const [worktreeInfo, setWorktreeInfo] = useState<WorktreeInfo | null>(null);

  // Architect streaming (SDK WebSocket) — kept as fallback
  const architectStream = useArchitectStream();

  // Plan streaming (SDK WebSocket) — kept as fallback
  const planStream = usePlanStream();

  // Unified wizard streaming (single persistent ClaudeSDKClient)
  const wizardStream = useWizardStream();
  const [isPlanRegenerating, setIsPlanRegenerating] = useState(false);

  // Q&A answers from pre-execution setup
  const [qaAnswers, setQaAnswers] = useState<Record<string, string>>({});

  // Agent execution state
  const [status, setStatus] = useState<AgentStatus>("idle");
  const [projects, setProjects] = useState<ProjectInfo[]>([]);
  const [tasks, setTasks] = useState<TaskData | null>(null);
  const [currentProject, setCurrentProject] = useState<string>("");
  const [approvalRequest, setApprovalRequest] = useState<ApprovalRequestData | null>(null);
  const [toasts, setToasts] = useState<Array<{ id: string; type: "success" | "error" | "info" | "warning"; title: string; body?: string }>>([]);
  const taskPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // Tracks the effective working directory (worktree path if active, otherwise project_dir)
  const effectiveProjectDirRef = useRef<string>("");

  // Store last config for re-runs (approve after review)
  const lastConfigRef = useRef<RunConfig | null>(null);
  // Store original config with all flags for two-phase flows (architect→approve, plan→approve, scan→approve)
  const twoPhaseConfigRef = useRef<RunConfig | null>(null);

  // --- Progress Persistence (sessionStorage) ---
  const SESSION_KEY = `swarmweaver-session-${tabId}`;

  // Load cached projects from localStorage on mount (avoids SSR hydration mismatch)
  useEffect(() => {
    const cached = loadCachedProjects();
    if (cached.length > 0) setProjects(cached);
  }, []);

  // Save critical state to sessionStorage whenever it changes
  useEffect(() => {
    try {
      if (typeof window === "undefined") return;
      sessionStorage.setItem(
        SESSION_KEY,
        JSON.stringify({ wizardStep, selectedMode, currentProject, status })
      );
    } catch {
      // Ignore quota errors
    }
  }, [SESSION_KEY, wizardStep, selectedMode, currentProject, status]);

  // Restore state from sessionStorage on mount
  useEffect(() => {
    try {
      if (typeof window === "undefined") return;
      const raw = sessionStorage.getItem(SESSION_KEY);
      if (!raw) return;
      const saved = JSON.parse(raw) as {
        wizardStep?: WizardStep;
        selectedMode?: Mode | null;
        currentProject?: string;
        status?: AgentStatus;
      };
      if (saved.wizardStep) setWizardStep(saved.wizardStep);
      if (saved.selectedMode !== undefined) setSelectedMode(saved.selectedMode);
      if (saved.currentProject) setCurrentProject(saved.currentProject);

      // If the saved status was "running", check if the process is still active
      if (saved.status === "running" && saved.currentProject) {
        fetch("/api/status")
          .then((res) => res.json())
          .then((data) => {
            if (data.status === "running") {
              setStatus("running");
              // Backfill output from output-log
              fetch(
                `/api/output-log?path=${encodeURIComponent(saved.currentProject!)}&lines=200`
              )
                .then((res) => res.json())
                .then((logData) => {
                  const lines: string[] = logData.lines || [];
                  if (lines.length > 0) {
                    ws.setOutput(["--- Restored session output ---", ...lines, ""]);
                  }
                })
                .catch(() => {});
              // Also fetch current tasks
              if (saved.currentProject) {
                fetch(
                  `/api/tasks?path=${encodeURIComponent(saved.currentProject)}`
                )
                  .then((res) => res.json())
                  .then((data) => {
                    if (data.tasks) setTasks(data);
                  })
                  .catch(() => {});
              }
            }
          })
          .catch(() => {});
      }
    } catch {
      // Ignore parse errors
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // --- Wizard Navigation ---

  const goBack = useCallback(() => {
    if (wizardStep === "qa") {
      setWizardStep("landing");
      setSelectedMode(null);
    } else if (wizardStep === "plan-review" && selectedMode === "greenfield") {
      // Greenfield: plan-review → back to architect/spec review
      setWizardStep("architect-review");
    } else if (wizardStep === "architect-review") {
      // Go back to QA or landing
      setWizardStep("landing");
      setSelectedMode(null);
    } else if (wizardStep === "plan-review" || wizardStep === "security-review" || wizardStep === "execute") {
      setWizardStep("landing");
      setSelectedMode(null);
    }
  }, [wizardStep, selectedMode]);

  const goToExecute = useCallback(() => {
    setWizardStep("execute");
  }, []);

  const goToLanding = useCallback(() => {
    setWizardStep("landing");
    setSelectedMode(null);
    setGeneratedSpec(null);
    setIsLightweightLoading(false);
    setCodebaseProfile(null);
    setSecurityReport(null);
    setQaAnswers({});
  }, []);

  // --- Project & Task Fetching ---

  const checkProjectStatus = useCallback(
    async (projectPath: string): Promise<ProjectStatus | null> => {
      if (!projectPath.trim()) return null;
      try {
        const res = await fetch(
          `/api/project-status?path=${encodeURIComponent(projectPath)}`
        );
        const data = await res.json();
        return data as ProjectStatus;
      } catch {
        return null;
      }
    },
    []
  );

  const fetchProjects = useCallback(async () => {
    try {
      const res = await fetch("/api/projects");
      const data = await res.json();
      const apiProjects: ProjectInfo[] = data.projects || [];

      // Merge with cached projects (API takes precedence for matching paths)
      const cached = loadCachedProjects();
      const apiPaths = new Set(apiProjects.map((p: ProjectInfo) => p.path));
      const cachedOnly = cached.filter((p: ProjectInfo) => !apiPaths.has(p.path));

      // Refresh cached-only projects via individual status checks
      const refreshed = await Promise.all(
        cachedOnly.map(async (p) => {
          try {
            const statusRes = await fetch(
              `/api/project-status?path=${encodeURIComponent(p.path)}`
            );
            const st = await statusRes.json();
            if (st.exists && st.has_tasks) {
              return { ...p, done: st.done, total: st.total, percentage: st.percentage, mode: st.mode || p.mode };
            }
          } catch { /* ignore */ }
          return p;
        })
      );

      const merged = [...apiProjects, ...refreshed];
      setProjects(merged);
      saveCachedProjects(merged);
    } catch {
      // Backend not running — use cached projects
      const cached = loadCachedProjects();
      if (cached.length > 0) {
        setProjects(cached);
      }
    }
  }, []);

  const fetchTasks = useCallback(async (projectPath: string) => {
    if (!projectPath) return;
    try {
      const res = await fetch(
        `/api/tasks?path=${encodeURIComponent(projectPath)}`
      );
      if (!res.ok) {
        console.warn("[fetchTasks] HTTP error:", res.status, projectPath);
        return;
      }
      const data = await res.json();
      if (data.error) {
        console.warn("[fetchTasks] API error:", data.error, projectPath);
        return;
      }
      if (data.tasks) {
        setTasks(data);
      }
    } catch (err) {
      console.warn("[fetchTasks] Fetch failed:", err);
    }
  }, []);

  const fetchSpec = useCallback(async (projectPath: string): Promise<string | null> => {
    if (!projectPath) return null;
    try {
      const res = await fetch(
        `/api/spec?path=${encodeURIComponent(projectPath)}`
      );
      const data = await res.json();
      return data.spec || null;
    } catch {
      return null;
    }
  }, []);

  const saveSpec = useCallback(async (projectPath: string, spec: string) => {
    try {
      await fetch(`/api/spec?path=${encodeURIComponent(projectPath)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ spec }),
      });
    } catch {
      // Ignore
    }
  }, []);

  const fetchOutputLog = useCallback(async (projectPath: string): Promise<string[]> => {
    try {
      const res = await fetch(
        `/api/output-log?path=${encodeURIComponent(projectPath)}&lines=200`
      );
      const data = await res.json();
      return data.lines || [];
    } catch {
      return [];
    }
  }, []);

  const fetchActivityLog = useCallback(async (projectPath: string): Promise<AgentEvent[]> => {
    try {
      const res = await fetch(
        `/api/activity-log?path=${encodeURIComponent(projectPath)}&limit=10000`
      );
      if (!res.ok) return [];
      const data = await res.json();
      return (data.events || []) as AgentEvent[];
    } catch {
      return [];
    }
  }, []);

  // --- Project Settings (per-project defaults) ---

  const fetchProjectSettings = useCallback(async (projectPath: string) => {
    try {
      const res = await fetch(
        `/api/projects/settings?path=${encodeURIComponent(projectPath)}`
      );
      const data = await res.json();
      return data.settings || null;
    } catch {
      return null;
    }
  }, []);

  const saveProjectSettings = useCallback(
    async (
      projectPath: string,
      settings: {
        default_model?: string;
        default_parallel?: number;
        use_worktree?: boolean;
        approval_gates?: boolean;
        budget_limit?: number | null;
      }
    ) => {
      try {
        await fetch(`/api/projects/settings?path=${encodeURIComponent(projectPath)}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(settings),
        });
      } catch {
        // Ignore
      }
    },
    []
  );

  const deleteProjectSettings = useCallback(async (projectPath: string) => {
    try {
      await fetch(`/api/projects/settings?path=${encodeURIComponent(projectPath)}`, {
        method: "DELETE",
      });
    } catch {
      // Ignore
    }
  }, []);

  const fetchSecurityReport = useCallback(async (projectPath: string): Promise<SecurityReport | null> => {
    try {
      const res = await fetch(
        `/api/security-report?path=${encodeURIComponent(projectPath)}`
      );
      const data = await res.json();
      return data.report || null;
    } catch {
      return null;
    }
  }, []);

  const approveSecurityFindings = useCallback(
    async (projectPath: string, approvedIds: string[], ignoredReasons: Record<string, string>) => {
      try {
        await fetch(`/api/security-report/approve?path=${encodeURIComponent(projectPath)}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ approved_ids: approvedIds, ignored_reasons: ignoredReasons }),
        });
      } catch {
        // Ignore
      }
    },
    []
  );

  // --- Task Polling ---

  const startTaskPolling = useCallback(
    (projectPath: string) => {
      if (taskPollRef.current) clearInterval(taskPollRef.current);

      // Immediate first fetch
      fetchTasks(projectPath);

      // Consistent 3s polling while running — server also pushes task_list_ready
      // event as soon as task_list.json appears, so polling is just a fallback
      taskPollRef.current = setInterval(() => {
        fetchTasks(projectPath);
      }, 3000);
    },
    [fetchTasks]
  );

  const stopTaskPolling = useCallback(() => {
    if (taskPollRef.current) {
      clearInterval(taskPollRef.current);
      taskPollRef.current = null;
    }
  }, []);

  // --- Toasts ---

  const addToast = useCallback(
    (type: "success" | "error" | "info" | "warning", title: string, body?: string) => {
      const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2)}`;
      setToasts((prev) => [...prev.slice(-4), { id, type, title, body }]);
    },
    []
  );

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const showBrowserNotification = useCallback(
    (title: string, body: string) => {
      if ("Notification" in window && Notification.permission === "granted") {
        try {
          new Notification(title, { body, icon: "/favicon.ico" });
        } catch {
          // Ignore
        }
      }
    },
    []
  );

  // --- WebSocket (extracted to useWebSocket hook) ---

  const wsCallbacks = useMemo(() => ({
    onStatusRunning: (projectDir: string) => {
      setStatus("running");
      effectiveProjectDirRef.current = projectDir;
      startTaskPolling(projectDir);
    },
    onStatusCompleted: (projectDir: string) => {
      setStatus("completed");
      stopTaskPolling();
      // Fetch tasks from worktree path if active, otherwise main project
      const taskDir = effectiveProjectDirRef.current || projectDir;
      fetchTasks(taskDir);
      fetchProjects();
      // Delayed re-fetch to let disk state settle
      setTimeout(() => fetchProjects(), 1500);
    },
    onError: (message: string) => {
      setStatus("error");
      stopTaskPolling();
    },
    onWarning: (title: string, body: string) => {
      addToast("warning", title, body);
    },
    onBrowserNotification: (title: string, body: string, eventType?: string) => {
      showBrowserNotification(title, body);
      addToast(
        eventType === "error" ? "error" : "success",
        title,
        body
      );
    },
    onWorktreeReady: (info: WorktreeInfo) => {
      setWorktreeInfo(info);
      // Restart task polling using the worktree path where task_list.json lives
      if (info.worktree_path) {
        effectiveProjectDirRef.current = info.worktree_path;
        startTaskPolling(info.worktree_path);
      }
    },
    onApprovalRequest: (data: ApprovalRequestData) => {
      setApprovalRequest(data);
    },
    onTaskListReady: (data: TaskData) => {
      if (data.tasks) {
        setTasks(data);
      }
    },
    fetchTasks,
    fetchOutputLog,
    stopTaskPolling,
  }), [startTaskPolling, stopTaskPolling, fetchTasks, fetchProjects, fetchOutputLog, showBrowserNotification, addToast]);

  const ws = useWebSocket(wsCallbacks);

  // --- Agent Execution ---

  const run = useCallback(
    (config: RunConfig) => {
      if (!config.project_dir) {
        console.error("[run] config.project_dir is undefined!", config);
        return;
      }
      ws.close();

      lastConfigRef.current = config;
      ws.setOutput([]);
      ws.setEvents([]);
      ws.setSessionStats(null);
      setTasks(null);
      setStatus("starting");
      setCurrentProject(config.project_dir);

      // Cache project info for instant landing page display
      const projectName = config.project_dir.split("/").pop() || config.project_dir.split("\\").pop() || config.project_dir;
      const projectInfo: ProjectInfo = {
        name: projectName,
        path: config.project_dir,
        has_tasks: false,
        mode: config.mode,
        done: 0,
        total: 0,
        percentage: 0,
        last_modified: new Date().toISOString(),
      };
      const cached = loadCachedProjects();
      saveCachedProjects([
        projectInfo,
        ...cached.filter((p: ProjectInfo) => p.path !== config.project_dir),
      ]);

      ws.connect(config);
    },
    // ws.close/connect/setOutput/etc. are stable refs — don't depend on ws object
    // (ws object is recreated every render, which would make run unstable and
    //  cause the cleanup useEffect to close the WebSocket on every re-render)
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [ws.close, ws.connect, ws.setOutput, ws.setEvents, ws.setSessionStats]
  );

  // --- Wizard Run Helpers (Lightweight) ---
  // Each helper writes artifacts to disk immediately after generation
  // so the full agent session always finds them on disk.

  /** Run greenfield architect phase via unified wizard WS (with POST fallback) */
  const runArchitectOnly = useCallback(
    async (config: RunConfig) => {
      setSelectedMode(config.mode);
      setIsLightweightLoading(true);
      twoPhaseConfigRef.current = config;
      lastConfigRef.current = config;
      setCurrentProject(config.project_dir);

      const idea = config.idea || config.task_input || "";

      // Try unified wizard WebSocket (persistent ClaudeSDKClient)
      try {
        wizardStream.connect({
          mode: "greenfield",
          idea,
          task_input: config.task_input,
          model: config.model,
          project_dir: config.project_dir,
          phase_models: config.phase_models,
        });
      } catch {
        // WebSocket failed to even start — fall back to POST immediately
        console.warn("[runArchitectOnly] WebSocket connect failed, falling back to POST");
        const model = config.phase_models?.architect || config.model;
        try {
          const result = await generateSpec(idea, model, config.project_dir);
          setGeneratedSpec(result.spec);
          await prepareProject({
            projectDir: config.project_dir,
            mode: config.mode,
            taskInput: idea,
            spec: result.spec,
          });
        } catch (err) {
          console.error("[runArchitectOnly] POST fallback also failed:", err);
          addToast("error", "Architect failed", err instanceof Error ? err.message : "Unknown error");
        } finally {
          setIsLightweightLoading(false);
        }
      }
    },
    [addToast, wizardStream]
  );

  // When QA completes, transition wizardStep to the appropriate next phase
  useEffect(() => {
    if (wizardStream.phase === "qa_complete" && wizardStep === "qa") {
      const config = twoPhaseConfigRef.current || lastConfigRef.current;
      const mode = config?.mode || selectedMode;
      if (mode === "greenfield") {
        setWizardStep("architect-review");
      } else {
        setWizardStep("plan-review");
      }
    }
  }, [wizardStream.phase, wizardStep, selectedMode]);

  // Also transition when research starts (greenfield flow)
  useEffect(() => {
    if (wizardStream.phase === "research" && wizardStep === "qa") {
      setWizardStep("architect-review");
    }
  }, [wizardStream.phase, wizardStep]);

  // Transition when plan_analyzing starts (non-greenfield flow)
  // Accept intermediate review steps (report-review, strategy-review, security-review) for modes
  // where the backend sends plan_analyzing after an intermediate review (e.g., evolve: audit report
  // → acknowledge → questions → plan_analyzing).
  useEffect(() => {
    if (wizardStream.phase === "plan_analyzing" &&
        (wizardStep === "qa" || wizardStep === "report-review" || wizardStep === "strategy-review" || wizardStep === "security-review")) {
      setWizardStep("plan-review");
      setIsLightweightLoading(true);
    }
  }, [wizardStream.phase, wizardStep]);

  // Transition when analysis/investigation/audit/scan starts (non-greenfield modes)
  useEffect(() => {
    const analysisPhases: WizardPhase[] = ["analyzing", "investigating", "auditing", "scanning"];
    if (analysisPhases.includes(wizardStream.phase) && wizardStep === "qa") {
      setWizardStep("architect-review");
    }
  }, [wizardStream.phase, wizardStep]);

  // Transition to strategy-review when strategy completes (refactor mode)
  // Accept both "architect-review" (direct from QA skip) and "plan-review" (from QA → non-greenfield shortcut)
  useEffect(() => {
    if (wizardStream.phase === "strategy_complete" && (wizardStep === "architect-review" || wizardStep === "plan-review")) {
      setWizardStep("strategy-review");
      setIsLightweightLoading(false);
    }
  }, [wizardStream.phase, wizardStep]);

  // Transition to report-review when report completes (fix/evolve modes)
  // Accept both "architect-review" (direct from QA skip) and "plan-review" (from QA → non-greenfield shortcut)
  useEffect(() => {
    if (wizardStream.phase === "report_complete" && (wizardStep === "architect-review" || wizardStep === "plan-review")) {
      setWizardStep("report-review");
      setIsLightweightLoading(false);
    }
  }, [wizardStream.phase, wizardStep]);

  // Transition to security-review when security findings arrive (security mode)
  useEffect(() => {
    if (wizardStream.phase === "security_complete" && (wizardStep === "architect-review" || wizardStep === "plan-review" || wizardStep === "qa")) {
      setWizardStep("security-review");
      setIsLightweightLoading(false);
    }
  }, [wizardStream.phase, wizardStep]);

  // Transition to plan-review when questions phase starts after analysis (for follow-up questions)
  useEffect(() => {
    if (wizardStream.phase === "questions" && wizardStep === "architect-review") {
      // Stay in architect-review — questions render in the chat feed
    }
  }, [wizardStream.phase, wizardStep]);

  // Watch wizard stream for progressive spec updates (only during generating/spec_complete phases)
  useEffect(() => {
    if (wizardStream.specText && (wizardStream.phase === "generating" || wizardStream.phase === "spec_complete")) {
      setGeneratedSpec(wizardStream.specText);
    }
  }, [wizardStream.specText, wizardStream.phase]);

  // When spec generation completes via wizard stream, finalize
  useEffect(() => {
    if (wizardStream.phase === "spec_complete" && wizardStream.specText && isLightweightLoading && wizardStep === "architect-review") {
      const finalSpec = wizardStream.specText;
      setIsLightweightLoading(false);
      setGeneratedSpec(finalSpec);

      // Write spec to disk
      const config = twoPhaseConfigRef.current;
      if (config) {
        const idea = config.idea || config.task_input || "";
        prepareProject({
          projectDir: config.project_dir,
          mode: config.mode,
          taskInput: idea,
          spec: finalSpec,
        }).catch((err) => {
          console.error("[runArchitectOnly] Failed to write spec to disk:", err);
        });
      }
    }
  }, [wizardStream.phase, wizardStream.specText, isLightweightLoading, wizardStep]);

  // Handle wizard stream errors during architect phase — fall back to POST
  useEffect(() => {
    if (wizardStream.error && isLightweightLoading && wizardStep === "architect-review") {
      console.warn("[runArchitectOnly] Stream error, falling back to POST:", wizardStream.error);
      wizardStream.reset();

      const config = twoPhaseConfigRef.current;
      if (!config) {
        setIsLightweightLoading(false);
        return;
      }

      const idea = config.idea || config.task_input || "";
      const model = config.phase_models?.architect || config.model;

      generateSpec(idea, model, config.project_dir)
        .then(async (result) => {
          setGeneratedSpec(result.spec);
          await prepareProject({
            projectDir: config.project_dir,
            mode: config.mode,
            taskInput: idea,
            spec: result.spec,
          });
        })
        .catch((err) => {
          console.error("[runArchitectOnly] POST fallback also failed:", err);
          addToast("error", "Architect failed", err instanceof Error ? err.message : "Unknown error");
        })
        .finally(() => {
          setIsLightweightLoading(false);
        });
    }
  }, [wizardStream.error, wizardStream, isLightweightLoading, wizardStep, addToast]);

  // --- Wizard plan stream watchers ---

  // When tasks arrive from wizard stream, finalize immediately
  useEffect(() => {
    if (wizardStream.tasks && isLightweightLoading && wizardStep === "plan-review") {
      setTasks(wizardStream.tasks);
      setIsPlanRegenerating(false);
      setIsLightweightLoading(false);

      // Write tasks to disk
      const config = twoPhaseConfigRef.current;
      if (config) {
        const spec = generatedSpec || config.spec || undefined;
        prepareProject({
          projectDir: config.project_dir,
          mode: config.mode,
          taskInput: config.task_input,
          spec,
          taskList: wizardStream.tasks as unknown as Record<string, unknown>,
          codebaseProfile: codebaseProfile || undefined,
        }).catch((err) => {
          console.error("[wizardStream] Failed to write tasks to disk:", err);
        });
      }
    }
  }, [wizardStream.tasks, isLightweightLoading, wizardStep, generatedSpec, codebaseProfile]);

  // Handle wizard stream errors during plan phase — fall back to POST
  useEffect(() => {
    if (wizardStream.error && isLightweightLoading && wizardStep === "plan-review") {
      console.warn("[wizardStream] Plan stream error, falling back to POST:", wizardStream.error);
      wizardStream.reset();

      const config = twoPhaseConfigRef.current;
      if (!config) {
        setIsLightweightLoading(false);
        return;
      }

      const model = config.phase_models?.plan || config.model;
      const spec = generatedSpec || config.spec || undefined;

      generatePlan(config.mode, config.task_input, spec, codebaseProfile || undefined, model)
        .then(async (result) => {
          const taskList = result.task_list;
          setTasks(taskList);
          await prepareProject({
            projectDir: config.project_dir,
            mode: config.mode,
            taskInput: config.task_input,
            spec,
            taskList: taskList as unknown as Record<string, unknown>,
            codebaseProfile: codebaseProfile || undefined,
          });
        })
        .catch((err) => {
          console.error("[wizardStream] POST fallback also failed:", err);
          addToast("error", "Planning failed", err instanceof Error ? err.message : "Unknown error");
        })
        .finally(() => {
          setIsLightweightLoading(false);
        });
    }
  }, [wizardStream.error, wizardStream, isLightweightLoading, wizardStep, generatedSpec, codebaseProfile, addToast]);

  // Safety: clear isLightweightLoading if wizard WS closes without completing (stuck spinner prevention)
  // Exclude phases where isStreaming is temporarily false for expected user input pauses
  // (qa_questions: user filling QA form — isStreaming resumes on qa_complete).
  useEffect(() => {
    if (!wizardStream.isStreaming && isLightweightLoading && !wizardStream.error &&
        wizardStream.phase !== "qa_questions" &&
        (wizardStep === "qa" || wizardStep === "architect-review" || wizardStep === "plan-review" || wizardStep === "strategy-review" || wizardStep === "report-review" || wizardStep === "security-review")) {
      // WS closed without sending spec_complete/tasks/error — clear loading state
      const timer = setTimeout(() => setIsLightweightLoading(false), 500);
      return () => clearTimeout(timer);
    }
  }, [wizardStream.isStreaming, isLightweightLoading, wizardStream.error, wizardStep, wizardStream.phase]);

  /** Regenerate plan with user feedback — uses existing wizard WS (no subprocess spawn) */
  const regeneratePlan = useCallback(
    (feedback: string) => {
      setIsLightweightLoading(true);
      setIsPlanRegenerating(true);
      setTasks(null);

      // Send regeneration request on existing wizard WebSocket
      wizardStream.regenerate(feedback);
    },
    [wizardStream]
  );

  /** Run planning phase only via unified wizard WS (all non-greenfield modes).
   *  Analysis/investigation/audit/scan all happen inside the WS as streaming turns. */
  const runPlanOnly = useCallback(
    (config: RunConfig) => {
      setSelectedMode(config.mode);
      setIsLightweightLoading(true);
      twoPhaseConfigRef.current = config;
      lastConfigRef.current = config;
      setCurrentProject(config.project_dir);

      const model = config.phase_models?.plan || config.model;

      // Write task_input.txt to disk immediately so the agent can find it later
      prepareProject({
        projectDir: config.project_dir,
        mode: config.mode,
        taskInput: config.task_input,
      }).catch((err) => {
        console.error("[runPlanOnly] prepareProject failed:", err);
      });

      // Start wizard WS — analysis/investigation/audit/scan happens as Turn 1 inside the WS
      wizardStream.connect({
        mode: config.mode,
        task_input: config.task_input,
        model,
        project_dir: config.project_dir,
        phase_models: config.phase_models,
      });
    },
    [wizardStream]
  );

  /** Run security scan via wizard WS (security mode now uses the unified wizard flow) */
  const runScanOnly = useCallback(
    (config: RunConfig) => {
      // Security now goes through the same wizard WS as other modes
      runPlanOnly(config);
    },
    [runPlanOnly]
  );

  /** After user approves security findings, call existing approve endpoint and start remediation */
  const handleApproveSecurityFindings = useCallback(
    async (approvedIds: string[], ignoredReasons: Record<string, string>) => {
      const runConfig = twoPhaseConfigRef.current || lastConfigRef.current;
      const projectDir = runConfig?.project_dir;
      if (!projectDir) return;
      await approveSecurityFindings(projectDir, approvedIds, ignoredReasons);

      twoPhaseConfigRef.current = null;
      setSecurityReport(null);
      setWizardStep("execute");
      // Resume — agent picks up remediate* phase since scan is done + task_list.json exists
      if (runConfig) {
        run({
          ...runConfig,
          idea: undefined,
          max_iterations: undefined,
          no_resume: false,
        });
      }
    },
    [run, approveSecurityFindings]
  );

  /** Approve refactor migration strategy — backend continues to plan generation */
  const handleApproveStrategy = useCallback(() => {
    setWizardStep("plan-review");
    setIsLightweightLoading(true);
    wizardStream.approveStrategy();
  }, [wizardStream]);

  /** Regenerate refactor strategy with feedback */
  const handleRegenerateStrategy = useCallback(
    (feedback: string) => {
      setIsLightweightLoading(true);
      wizardStream.regenerateStrategy(feedback);
    },
    [wizardStream]
  );

  /** Acknowledge investigation/audit report — backend continues to next phase.
   *  Do NOT set wizardStep here — the report_complete effect would re-fire because
   *  acknowledgeReport() does not change the phase (unlike approveStrategy/approveFindings).
   *  Instead, the plan_analyzing transition effect handles the step change when the
   *  backend sends the plan_analyzing phase event. */
  const handleAcknowledgeReport = useCallback(() => {
    setIsLightweightLoading(true);
    wizardStream.acknowledgeReport();
  }, [wizardStream]);

  /** Approve selected security findings — backend generates remediation tasks */
  const handleApproveWizardFindings = useCallback(
    (approvedIds: string[], ignoredReasons: Record<string, string>) => {
      setWizardStep("plan-review");
      setIsLightweightLoading(true);
      wizardStream.approveFindings(approvedIds, ignoredReasons);
    },
    [wizardStream]
  );

  /** After approving greenfield spec, signal wizard WS to continue to plan phase.
   *  No new subprocess — the persistent ClaudeSDKClient already has full context. */
  const approveSpecAndInitialize = useCallback(
    async (config?: RunConfig) => {
      const runConfig = config || twoPhaseConfigRef.current || lastConfigRef.current;
      if (!runConfig) return;
      twoPhaseConfigRef.current = runConfig;
      setWizardStep("plan-review");
      setIsLightweightLoading(true);

      // Just send approve_spec on the existing wizard WS — backend continues to plan
      wizardStream.approveSpec();
    },
    [wizardStream]
  );

  /** After approving spec/plan, start the full build session.
   *  Artifacts are already on disk from the lightweight phases above. */
  const approveAndRun = useCallback(
    async (config?: RunConfig) => {
      // Guard: reject React synthetic events / non-RunConfig objects accidentally passed as config
      const validConfig =
        config && typeof config === "object" && "mode" in config && "project_dir" in config
          ? (config as RunConfig)
          : null;
      const runConfig = validConfig || twoPhaseConfigRef.current || lastConfigRef.current;
      // Clear ref AFTER extracting value (not before) so the fallback path can still use it
      const savedTaskInput = twoPhaseConfigRef.current?.task_input || lastConfigRef.current?.task_input || "";
      twoPhaseConfigRef.current = null;
      if (!runConfig || !runConfig.project_dir) {
        if (currentProject && selectedMode) {
          setGeneratedSpec(null);
          setWizardStep("execute");
          // Resolve model from project settings or server default — no hardcoded fallback
          let model = lastConfigRef.current?.model;
          if (!model) {
            try {
              const settings = await fetchProjectSettings(currentProject);
              if (settings?.default_model) model = settings.default_model;
            } catch {
              /* ignore */
            }
            if (!model) {
              try {
                const res = await fetch("/api/default-model");
                if (res.ok) {
                  const d = await res.json();
                  if (d?.default_model) model = d.default_model;
                }
              } catch {
                /* ignore */
              }
            }
          }
          run({
            mode: selectedMode,
            project_dir: currentProject,
            task_input: savedTaskInput || "Resume from checkpoint",
            model: model || "claude-sonnet-4-6", // final fallback only if all fetches fail
            no_resume: false,
          });
          return;
        }
        console.error("[approveAndRun] No config available");
        return;
      }

      // Safety net: re-write all artifacts to disk in case something was missed
      try {
        await prepareProject({
          projectDir: runConfig.project_dir,
          mode: runConfig.mode,
          taskInput: runConfig.task_input,
          spec: generatedSpec || runConfig.spec || undefined,
          taskList: tasks ? (tasks as unknown as Record<string, unknown>) : undefined,
          codebaseProfile: codebaseProfile || undefined,
        });
      } catch (err) {
        console.error("[approveAndRun] prepareProject failed:", err);
        // Not fatal — artifacts should already be on disk from lightweight phases
      }

      setGeneratedSpec(null);
      setCodebaseProfile(null);
      setWizardStep("execute");
      // Start full session — agent finds artifacts on disk and skips to building
      run({
        ...runConfig,
        idea: undefined,
        max_iterations: undefined,
        no_resume: false,
      });
    },
    [run, currentProject, selectedMode, generatedSpec, tasks, codebaseProfile, addToast, fetchProjectSettings]
  );

  /** Start execution directly (no review step) */
  const runDirect = useCallback(
    (config: RunConfig) => {
      setSelectedMode(config.mode);
      setWizardStep("execute");
      run(config);
    },
    [run]
  );

  /** Resume an existing project — restores UI state AND restarts the agent */
  const resumeProject = useCallback(
    async (project: ProjectInfo) => {
      const mode = (project.mode as Mode) || "greenfield";
      setCurrentProject(project.path);
      setSelectedMode(mode);
      setWizardStep("execute");
      fetchTasks(project.path);

      // Refresh status from disk
      const freshStatus = await checkProjectStatus(project.path);
      const updatedProject = freshStatus
        ? { ...project, done: freshStatus.done, total: freshStatus.total, percentage: freshStatus.percentage, last_modified: new Date().toISOString() }
        : { ...project, last_modified: new Date().toISOString() };

      // Update localStorage cache with this project at the top
      const cached = loadCachedProjects();
      saveCachedProjects([
        updatedProject,
        ...cached.filter((p: ProjectInfo) => p.path !== project.path),
      ]);

      // Load cached output from previous session
      const outputLines = await fetchOutputLog(project.path);
      if (outputLines.length > 0) {
        ws.setOutput(["--- Previous session output ---", ...outputLines, "--- End of previous session ---", ""]);
      }

      // Load and replay full activity feed from the persisted event log
      const historicalEvents = await fetchActivityLog(project.path);
      if (historicalEvents.length > 0) {
        ws.setEvents(historicalEvents);
      }

      // Read saved model from project settings, then server default — no hardcoded fallback
      let savedModel: string | undefined;
      try {
        const settings = await fetchProjectSettings(project.path);
        if (settings && typeof settings.default_model === "string") {
          savedModel = settings.default_model;
        }
      } catch {
        /* ignore */
      }
      if (!savedModel) {
        try {
          const res = await fetch("/api/default-model");
          if (res.ok) {
            const d = await res.json();
            if (d?.default_model) savedModel = d.default_model;
          }
        } catch {
          /* ignore */
        }
      }
      // Final fallback only when all fetches fail (e.g. offline)
      if (!savedModel) savedModel = "claude-sonnet-4-6";

      // Actually restart the agent from its checkpoint.
      // task_input must be non-empty to satisfy argparse required args.
      // With no_resume:false, the agent reads its real instructions from task_input.txt on disk.
      if (freshStatus && freshStatus.percentage < 100) {
        // Restore swarm settings from the persisted run_config so the resume
        // uses the same execution mode (SmartSwarm / Swarm / single-agent).
        const rc = freshStatus.run_config;
        run({
          mode,
          project_dir: project.path,
          task_input: "Resume from checkpoint",
          model: savedModel,
          no_resume: false,
          smart_swarm: rc?.smart_swarm ?? false,
          parallel: rc?.parallel ?? 1,
          ...(rc?.max_workers ? { max_workers: rc.max_workers } : {}),
          ...(rc?.budget ? { budget: rc.budget } : {}),
          ...(rc?.max_hours ? { max_hours: rc.max_hours } : {}),
          ...(rc?.phase_models ? { phase_models: rc.phase_models } : {}),
          ...(rc?.approval_gates ? { approval_gates: rc.approval_gates } : {}),
          ...(rc?.overrides ? { overrides: rc.overrides } : {}),
        });
      }
    },
    [fetchTasks, checkProjectStatus, fetchOutputLog, fetchActivityLog, fetchProjectSettings, run]
  );

  // --- Remove project from recent list ---

  const removeProject = useCallback((projectPath: string) => {
    const cached = loadCachedProjects().filter((p) => p.path !== projectPath);
    saveCachedProjects(cached);
    setProjects((prev) => prev.filter((p) => p.path !== projectPath));
  }, []);

  // --- Clear all projects from recent history ---

  const clearAllProjects = useCallback(() => {
    saveCachedProjects([]);
    setProjects([]);
  }, []);

  // --- Stop / Reset ---

  const stop = useCallback(async () => {
    try {
      await fetch("/api/stop", { method: "POST" });
    } catch {
      // Ignore
    }
    ws.close();
    setStatus("idle");
    stopTaskPolling();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stopTaskPolling, ws.close]);

  const reset = useCallback(() => {
    ws.setOutput([]);
    ws.setEvents([]);
    ws.setSessionStats(null);
    setStatus("idle");
    setTasks(null);
    setApprovalRequest(null);
    setGeneratedSpec(null);
    setIsLightweightLoading(false);
    setCodebaseProfile(null);
    setSecurityReport(null);
    setWorktreeInfo(null);
    setQaAnswers({});
    twoPhaseConfigRef.current = null;
    stopTaskPolling();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stopTaskPolling, ws.setOutput, ws.setEvents, ws.setSessionStats]);

  // --- Worktree merge/discard ---

  const mergeWorktree = useCallback(async () => {
    if (!worktreeInfo) return;
    try {
      const res = await fetch(
        `/api/worktree/merge?path=${encodeURIComponent(worktreeInfo.original_project_dir)}&run_id=${encodeURIComponent(worktreeInfo.run_id)}`,
        { method: "POST" }
      );
      const data = await res.json();
      if (data.status === "ok") {
        const tierLabel = data.resolution_tier_name ? ` (${data.resolution_tier_name})` : "";
        addToast("success", "Changes merged", `${data.files_changed || worktreeInfo.files_changed} files updated${tierLabel}`);
        setWorktreeInfo(null);
        // Refresh projects list to reflect merged changes
        fetchProjects();
      } else {
        const tierInfo = data.resolution_tier_name ? ` [tier: ${data.resolution_tier_name}]` : "";
        addToast("error", "Merge failed", (data.error || "Unknown error") + tierInfo);
      }
    } catch {
      addToast("error", "Merge failed", "Could not reach server");
    }
  }, [worktreeInfo, addToast, fetchProjects]);

  const discardWorktree = useCallback(async () => {
    if (!worktreeInfo) return;
    try {
      await fetch(
        `/api/worktree/discard?path=${encodeURIComponent(worktreeInfo.original_project_dir)}&run_id=${encodeURIComponent(worktreeInfo.run_id)}`,
        { method: "POST" }
      );
      addToast("info", "Changes discarded", "Worktree removed, original code untouched");
      setWorktreeInfo(null);
    } catch {
      addToast("error", "Discard failed", "Could not reach server");
    }
  }, [worktreeInfo, addToast]);

  // --- Steering & Approval ---

  const sendSteering = useCallback(
    (message: string, steeringType: string = "instruction") => {
      ws.send({
        type: "steering",
        message,
        steering_type: steeringType,
      });
      addToast("info", `Steering sent (${steeringType})`, message.slice(0, 60));
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [addToast, ws.send]
  );

  const resolveApproval = useCallback(
    (decision: string, feedback: string = "") => {
      ws.send({
        type: "approval_resolve",
        decision,
        feedback,
      });
      if (currentProject) {
        fetch(
          `/api/approval/resolve?path=${encodeURIComponent(currentProject)}&decision=${decision}&feedback=${encodeURIComponent(feedback)}`,
          { method: "POST" }
        ).catch(() => {});
      }
      setApprovalRequest(null);
      addToast(
        decision === "rejected" ? "error" : "success",
        `Approval: ${decision}`,
        feedback ? feedback.slice(0, 60) : undefined
      );
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [currentProject, addToast, ws.send]
  );

  // --- New Tier 1/2 Fetch Functions ---

  const fetchBudget = useCallback(async (projectPath: string) => {
    try {
      const res = await fetch(`/api/budget?path=${encodeURIComponent(projectPath)}`);
      return res.ok ? await res.json() : null;
    } catch { return null; }
  }, []);

  const fetchMergeQueue = useCallback(async (projectPath: string) => {
    try {
      const res = await fetch(`/api/swarm/merge-queue?path=${encodeURIComponent(projectPath)}`);
      return res.ok ? await res.json() : null;
    } catch { return null; }
  }, []);

  const fetchCheckpoints = useCallback(async (projectPath: string) => {
    try {
      const res = await fetch(`/api/checkpoints?path=${encodeURIComponent(projectPath)}`);
      return res.ok ? await res.json() : null;
    } catch { return null; }
  }, []);

  const fetchInsights = useCallback(async (projectPath: string) => {
    try {
      const res = await fetch(`/api/insights?path=${encodeURIComponent(projectPath)}`);
      return res.ok ? await res.json() : null;
    } catch { return null; }
  }, []);

  const fetchRunHistory = useCallback(async (projectPath: string) => {
    try {
      const res = await fetch(`/api/runs?path=${encodeURIComponent(projectPath)}`);
      return res.ok ? await res.json() : null;
    } catch { return null; }
  }, []);

  const fetchAgentIdentities = useCallback(async (projectPath: string) => {
    try {
      const res = await fetch(`/api/agents?path=${encodeURIComponent(projectPath)}`);
      return res.ok ? await res.json() : null;
    } catch { return null; }
  }, []);

  // --- Lifecycle ---

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  useEffect(() => {
    return () => {
      stopTaskPolling();
      ws.close();
    };
    // ws.close is stable (useCallback with [] deps) — using ws object here
    // would cause cleanup to fire on every render, killing the WebSocket
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stopTaskPolling, ws.close]);

  return {
    // Wizard
    wizardStep,
    setWizardStep,
    selectedMode,
    setSelectedMode,
    goBack,
    goToExecute,
    goToLanding,
    cliMode,
    setCliMode,
    generatedSpec,
    setGeneratedSpec,
    qaAnswers,
    setQaAnswers,
    // Wizard run helpers
    runArchitectOnly,
    runPlanOnly,
    runScanOnly,
    approveAndRun,
    approveSpecAndInitialize,
    handleApproveSecurityFindings,
    runDirect,
    resumeProject,
    removeProject,
    clearAllProjects,
    // Agent state
    status,
    output: ws.output,
    projects,
    tasks,
    currentProject,
    events: ws.events,
    sessionStats: ws.sessionStats,
    toasts,
    approvalRequest,
    securityReport,
    worktreeInfo,
    isLightweightLoading,
    setIsLightweightLoading,
    architectTools: wizardStream.tools,
    architectQuestions: wizardStream.questions,
    architectPhase: _toArchitectPhase(wizardStream.phase),
    sendArchitectAnswers: wizardStream.sendAnswers,
    planAnalysisText: wizardStream.analysisText,
    planPhase: _toPlanPhase(wizardStream.phase),
    isPlanRegenerating,
    regeneratePlan,
    wizardStream,
    // QA via wizard stream
    wizardQAQuestions: wizardStream.qaQuestions,
    sendWizardQAAnswers: wizardStream.sendQAAnswers,
    skipWizardQA: wizardStream.skipQA,
    wizardPhase: wizardStream.phase,
    codebaseProfile,
    // New mode-specific wizard state
    strategyText: wizardStream.strategyText,
    reportText: wizardStream.reportText,
    securityFindings: wizardStream.securityFindings,
    // New mode-specific wizard actions
    handleApproveStrategy,
    handleRegenerateStrategy,
    handleAcknowledgeReport,
    handleApproveWizardFindings,
    wsConnected: ws.wsConnected,
    // Actions
    run,
    stop,
    reset,
    fetchProjects,
    fetchTasks,
    fetchSpec,
    saveSpec,
    checkProjectStatus,
    addToast,
    dismissToast,
    sendSteering,
    resolveApproval,
    mergeWorktree,
    discardWorktree,
    // Tier 1/2 data fetchers
    fetchBudget,
    fetchMergeQueue,
    fetchCheckpoints,
    fetchInsights,
    fetchRunHistory,
    fetchAgentIdentities,
    // Project settings
    fetchProjectSettings,
    saveProjectSettings,
    deleteProjectSettings,
    // Quality gates
    qualityGates: ws.qualityGates,
    // AI Triage results
    triageResults: ws.triageResults,
    // Refs (read-only)
    lastConfig: lastConfigRef.current,
    // Per-worker real-time token tracking
    workerTokenMap: ws.workerTokenMap,
  };
}
