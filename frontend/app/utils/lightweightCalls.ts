/**
 * Lightweight pre-build API calls.
 *
 * These replace full agent sessions for planning phases (architect, analyze,
 * plan, scan). Each calls a `claude -p` subprocess on the backend, returning
 * structured results without booting MCP servers or git hooks.
 */

import type { TaskData } from "../hooks/useSwarmWeaver";

// --- Types ---

export interface GenerateSpecResult {
  spec: string;
}

export interface AnalyzeCodebaseResult {
  codebase_profile: Record<string, unknown>;
}

export interface GeneratePlanResult {
  task_list: TaskData;
}

export interface PrepareProjectResult {
  status: string;
  project_dir: string;
}

// --- Helpers ---

async function postJSON<T>(url: string, body: Record<string, unknown>): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  const data = await res.json();

  if (!res.ok) {
    throw new Error(data.error || data.detail || `Request failed (${res.status})`);
  }

  return data as T;
}

// --- API Wrappers ---

/**
 * Generate an app specification from an idea (greenfield architect phase).
 */
export async function generateSpec(
  idea: string,
  model: string = "claude-sonnet-4-6",
  projectDir: string = "",
): Promise<GenerateSpecResult> {
  return postJSON<GenerateSpecResult>("/api/architect/generate", {
    idea,
    model,
    project_dir: projectDir,
  });
}

/** @deprecated Analysis now happens inside the wizard WebSocket (streaming Turn 1) */
// export async function analyzeCodebase(...) — removed, use ws/wizard instead

/**
 * Generate a task list from a spec (greenfield) or codebase profile (feature/refactor).
 */
export async function generatePlan(
  mode: string,
  taskInput: string = "",
  spec?: string,
  codebaseProfile?: Record<string, unknown>,
  model: string = "claude-sonnet-4-6",
): Promise<GeneratePlanResult> {
  return postJSON<GeneratePlanResult>("/api/plan/generate", {
    mode,
    task_input: taskInput,
    spec: spec || undefined,
    codebase_profile: codebaseProfile || undefined,
    model,
  });
}

/** @deprecated Security scanning now happens inside the wizard WebSocket (streaming Turn 1) */
// export async function scanSecurity(...) — removed, use ws/wizard instead

/**
 * Write pre-build artifacts to disk so the full agent session skips planning.
 */
export async function prepareProject(opts: {
  projectDir: string;
  mode: string;
  taskInput?: string;
  spec?: string;
  taskList?: Record<string, unknown>;
  codebaseProfile?: Record<string, unknown>;
  securityReport?: Record<string, unknown>;
}): Promise<PrepareProjectResult> {
  return postJSON<PrepareProjectResult>("/api/project/prepare", {
    project_dir: opts.projectDir,
    mode: opts.mode,
    task_input: opts.taskInput || "",
    spec: opts.spec || undefined,
    task_list: opts.taskList || undefined,
    codebase_profile: opts.codebaseProfile || undefined,
    security_report: opts.securityReport || undefined,
  });
}
