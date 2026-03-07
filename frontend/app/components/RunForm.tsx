"use client";

import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import type { Mode, AgentStatus, RunConfig, ProjectStatus } from "../hooks/useSwarmWeaver";
import { getModeConfig } from "./ModeSelector";
import { FolderPicker } from "./FolderPicker";
import { TemplateGallery } from "./TemplateGallery";

// Approximate cost per task (input + output) by model, in USD
const MODEL_COST_ESTIMATES: Record<string, { perTaskLow: number; perTaskHigh: number }> = {
  "claude-opus-4-6":             { perTaskLow: 0.30, perTaskHigh: 0.90 },
  "claude-sonnet-4-6":           { perTaskLow: 0.06, perTaskHigh: 0.20 },
  "claude-sonnet-4-5-20250929":  { perTaskLow: 0.06, perTaskHigh: 0.20 },
  "claude-haiku-4-5-20251001":   { perTaskLow: 0.01, perTaskHigh: 0.04 },
};

interface RuntimeModel {
  id: string;
  name: string;
  description: string;
}

interface RuntimeInfo {
  name: string;
  description: string;
  available: boolean;
  models: RuntimeModel[];
}

interface RunFormProps {
  mode: Mode;
  status: AgentStatus;
  onRun: (config: RunConfig) => void;
  onStop: () => void;
  onReset: () => void;
  checkProjectStatus?: (path: string) => Promise<ProjectStatus | null>;
  onModeDetected?: (mode: Mode) => void;
}

export function RunForm({ mode, status, onRun, onStop, onReset, checkProjectStatus, onModeDetected }: RunFormProps) {
  const [projectDir, setProjectDir] = useState("");
  const [taskInput, setTaskInput] = useState("");
  const [model, setModel] = useState("claude-sonnet-4-6");
  const [maxIterations, setMaxIterations] = useState("");
  const [noResume, setNoResume] = useState(false);
  const [parallel, setParallel] = useState(1);
  const [budget, setBudget] = useState("");
  const [maxHours, setMaxHours] = useState("");
  const [approvalGates, setApprovalGates] = useState(false);
  const [autoPr, setAutoPr] = useState(false);
  const [monitorEnabled, setMonitorEnabled] = useState(true);
  const [monitorInterval, setMonitorInterval] = useState(60);
  const [githubSyncPull, setGithubSyncPull] = useState(false);
  const [githubSyncPush, setGithubSyncPush] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [showFolderPicker, setShowFolderPicker] = useState(false);
  const [showTemplates, setShowTemplates] = useState(false);
  const [activeTemplate, setActiveTemplate] = useState<string | null>(null);
  const [projectStatus, setProjectStatus] = useState<ProjectStatus | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Runtime state
  const [runtime, setRuntime] = useState("claude");
  const [runtimes, setRuntimes] = useState<RuntimeInfo[]>([]);

  // Fetch available runtimes on mount
  useEffect(() => {
    fetch("/api/runtimes")
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data?.runtimes) setRuntimes(data.runtimes);
      })
      .catch(() => {});
  }, []);

  // Get models for the currently selected runtime
  const runtimeModels = useMemo(() => {
    const rt = runtimes.find((r) => r.name === runtime);
    return rt?.models ?? [];
  }, [runtime, runtimes]);

  // Dispatch overrides state
  const [showOverrides, setShowOverrides] = useState(false);
  const [ovSkipReview, setOvSkipReview] = useState(false);
  const [ovFocusPerf, setOvFocusPerf] = useState(false);
  const [ovMinimalTests, setOvMinimalTests] = useState(false);
  const [ovMaxAgents, setOvMaxAgents] = useState("");
  const [ovCustomInstruction, setOvCustomInstruction] = useState("");
  const [ovPreset, setOvPreset] = useState<"speed_run" | "careful_mode" | "custom">("custom");

  const modeConfig = getModeConfig(mode);
  const isRunning = status === "running" || status === "starting";

  // Budget estimate based on model + task count heuristic
  const budgetEstimate = useMemo(() => {
    const taskEstimate = projectStatus?.total ?? 5; // default to 5 tasks
    const workers = parallel > 1 ? parallel : 1;
    const overheadFactor = workers > 1 ? 0.15 : 0; // swarm overhead
    const modelRates = MODEL_COST_ESTIMATES[model] ?? MODEL_COST_ESTIMATES["claude-sonnet-4-6"];
    const low = modelRates.perTaskLow * taskEstimate * (1 + overheadFactor);
    const high = modelRates.perTaskHigh * taskEstimate * (1 + overheadFactor);
    return { low, high, tasks: taskEstimate, workers };
  }, [model, parallel, projectStatus?.total]);

  // Check project status when project directory changes (debounced)
  const checkDir = useCallback(
    async (dir: string) => {
      if (!dir.trim() || !checkProjectStatus) {
        setProjectStatus(null);
        return;
      }
      const status = await checkProjectStatus(dir.trim());
      setProjectStatus(status);
      // Auto-detect mode from existing project
      if (status?.resumable && status.mode && onModeDetected) {
        onModeDetected(status.mode);
      }
    },
    [checkProjectStatus, onModeDetected]
  );

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => checkDir(projectDir), 400);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [projectDir, checkDir]);

  const applyPreset = (preset: "speed_run" | "careful_mode" | "custom") => {
    setOvPreset(preset);
    if (preset === "speed_run") {
      setOvSkipReview(true);
      setOvFocusPerf(false);
      setOvMinimalTests(true);
      setOvMaxAgents("10");
      setOvCustomInstruction("");
    } else if (preset === "careful_mode") {
      setOvSkipReview(false);
      setOvFocusPerf(false);
      setOvMinimalTests(false);
      setOvMaxAgents("2");
      setOvCustomInstruction("");
    } else {
      // custom - don't change anything
    }
  };

  const buildOverrides = () => {
    const overrides: { directive: string; value?: string | null; active: boolean }[] = [];
    if (ovSkipReview) overrides.push({ directive: "SKIP_REVIEW", active: true });
    if (ovFocusPerf) overrides.push({ directive: "FOCUS_PERFORMANCE", active: true });
    if (ovMinimalTests) overrides.push({ directive: "MINIMAL_TESTS", active: true });
    if (ovMaxAgents && parseInt(ovMaxAgents) > 0)
      overrides.push({ directive: "MAX_AGENTS", value: ovMaxAgents, active: true });
    if (ovCustomInstruction.trim())
      overrides.push({ directive: "CUSTOM_INSTRUCTION", value: ovCustomInstruction.trim(), active: true });
    return overrides.length > 0 ? overrides : undefined;
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!projectDir.trim()) return;

    // If greenfield mode with user-typed text (not a template/spec),
    // treat it as an "idea" to trigger the architect phase
    const isIdea = mode === "greenfield" && taskInput.trim() && !activeTemplate;

    onRun({
      mode,
      project_dir: projectDir.trim(),
      task_input: isIdea ? "" : taskInput.trim(),
      idea: isIdea ? taskInput.trim() : undefined,
      model,
      max_iterations: maxIterations ? parseInt(maxIterations) : undefined,
      no_resume: noResume,
      parallel: parallel > 1 ? parallel : undefined,
      budget: budget ? parseFloat(budget) : undefined,
      max_hours: maxHours ? parseFloat(maxHours) : undefined,
      approval_gates: approvalGates || undefined,
      auto_pr: autoPr || undefined,
      overrides: buildOverrides(),
      github_sync_pull: githubSyncPull || undefined,
      github_sync_push: githubSyncPush || undefined,
      monitor_enabled: parallel > 1 ? monitorEnabled : undefined,
      monitor_interval: parallel > 1 && monitorEnabled ? monitorInterval : undefined,
    });
  };

  const handleTemplateSelect = (specContent: string, templateName: string) => {
    setTaskInput(specContent);
    setActiveTemplate(templateName);
    setShowTemplates(false);
  };

  return (
    <>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          {/* Project directory with browse button */}
          <div>
            <label className="block text-xs text-text-secondary mb-1 font-medium">
              Project directory
            </label>
            <div className="flex gap-1.5">
              <input
                type="text"
                value={projectDir}
                onChange={(e) => setProjectDir(e.target.value)}
                placeholder="./my-app"
                disabled={isRunning}
                className="flex-1 rounded-md border border-border-subtle bg-surface-raised px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent transition-colors disabled:opacity-50"
              />
              <button
                type="button"
                onClick={() => setShowFolderPicker(true)}
                disabled={isRunning}
                className="rounded-md border border-border-subtle bg-surface-raised px-2.5 py-2 text-sm text-text-secondary hover:text-text-primary hover:border-border-default transition-colors disabled:opacity-50"
                title="Browse folders"
              >
                {"\u{1F4C2}"}
              </button>
            </div>
          </div>

          {/* Task input - varies by mode */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-xs text-text-secondary font-medium">
                {modeConfig.inputLabel}
              </label>
              {/* Template browser button - only in greenfield mode */}
              {mode === "greenfield" && !isRunning && (
                <button
                  type="button"
                  onClick={() => setShowTemplates(true)}
                  className="text-[10px] text-accent hover:text-accent-hover transition-colors font-medium"
                >
                  Browse Templates
                </button>
              )}
            </div>
            <div className="relative">
              <input
                type="text"
                value={
                  activeTemplate
                    ? `[${activeTemplate}] ${taskInput.substring(0, 50)}...`
                    : taskInput
                }
                onChange={(e) => {
                  setTaskInput(e.target.value);
                  setActiveTemplate(null);
                }}
                placeholder={modeConfig.inputPlaceholder}
                disabled={isRunning}
                className="w-full rounded-md border border-border-subtle bg-surface-raised px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent transition-colors disabled:opacity-50"
              />
              {activeTemplate && (
                <button
                  type="button"
                  onClick={() => {
                    setTaskInput("");
                    setActiveTemplate(null);
                  }}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary text-xs"
                >
                  {"\u2715"}
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Architect mode indicator */}
        {mode === "greenfield" && taskInput.trim() && !activeTemplate && (
          <div className="flex items-center gap-2 px-3 py-2 rounded-md border border-accent/30 bg-accent/5">
            <span className="text-accent text-sm">{"\u{1F3D7}"}</span>
            <div className="flex-1">
              <span className="text-sm text-text-primary font-medium">
                Architect mode
              </span>
              <span className="text-xs text-text-secondary ml-2">
                Agent will research latest tech via web search, design the full architecture, then build
              </span>
            </div>
            <span className="text-[10px] text-accent font-mono px-1.5 py-0.5 rounded border border-accent/30 bg-accent/10">
              architect {"\u2192"} init {"\u2192"} code
            </span>
          </div>
        )}

        {/* Advanced options toggle */}
        <button
          type="button"
          onClick={() => setShowAdvanced(!showAdvanced)}
          className="text-xs text-text-muted hover:text-text-secondary transition-colors"
        >
          {showAdvanced ? "\u25BC" : "\u25B6"} Advanced options
        </button>

        {showAdvanced && (
          <div className="grid grid-cols-4 gap-3 pt-1">
            {/* Runtime selector - subtle, only shown if multiple runtimes exist */}
            {runtimes.length > 1 && (
              <div>
                <label className="block text-xs text-text-secondary mb-1">
                  Runtime
                </label>
                <select
                  value={runtime}
                  onChange={(e) => {
                    setRuntime(e.target.value);
                    // Reset model to first available model of new runtime
                    const rt = runtimes.find((r) => r.name === e.target.value);
                    if (rt?.models?.length) setModel(rt.models[0].id);
                  }}
                  disabled={isRunning}
                  className="w-full rounded-md border border-border-subtle bg-surface-raised px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-accent transition-colors disabled:opacity-50"
                >
                  {runtimes.map((rt) => (
                    <option key={rt.name} value={rt.name} disabled={!rt.available}>
                      {rt.name.charAt(0).toUpperCase() + rt.name.slice(1)}{!rt.available ? " (unavailable)" : ""}
                    </option>
                  ))}
                </select>
              </div>
            )}
            <div>
              <label className="block text-xs text-text-secondary mb-1">
                Model
              </label>
              <select
                value={model}
                onChange={(e) => setModel(e.target.value)}
                disabled={isRunning}
                className="w-full rounded-md border border-border-subtle bg-surface-raised px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-accent transition-colors disabled:opacity-50"
              >
                {runtimeModels.length > 0 ? (
                  runtimeModels.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name}
                    </option>
                  ))
                ) : (
                  <>
                    <optgroup label="Claude 4.6">
                      <option value="claude-opus-4-6">Opus 4.6</option>
                      <option value="claude-sonnet-4-6">Sonnet 4.6</option>
                    </optgroup>
                    <optgroup label="Claude 4.5">
                      <option value="claude-sonnet-4-5-20250929">
                        Sonnet 4.5
                      </option>
                      <option value="claude-haiku-4-5-20251001">
                        Haiku 4.5
                      </option>
                    </optgroup>
                  </>
                )}
              </select>
            </div>
            <div>
              <label className="block text-xs text-text-secondary mb-1">
                Max iterations
              </label>
              <input
                type="number"
                value={maxIterations}
                onChange={(e) => setMaxIterations(e.target.value)}
                placeholder="Unlimited"
                min="1"
                disabled={isRunning}
                className="w-full rounded-md border border-border-subtle bg-surface-raised px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent transition-colors disabled:opacity-50"
              />
            </div>
            <div>
              <label className="block text-xs text-text-secondary mb-1">
                Parallel workers
              </label>
              <input
                type="number"
                value={parallel}
                onChange={(e) =>
                  setParallel(Math.max(1, Math.min(5, parseInt(e.target.value) || 1)))
                }
                min="1"
                max="5"
                disabled={isRunning}
                className="w-full rounded-md border border-border-subtle bg-surface-raised px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent transition-colors disabled:opacity-50"
              />
            </div>
            <div className="flex items-end pb-1">
              <label className="flex items-center gap-2 text-sm text-text-secondary cursor-pointer">
                <input
                  type="checkbox"
                  checked={noResume}
                  onChange={(e) => setNoResume(e.target.checked)}
                  disabled={isRunning}
                  className="rounded border-border-subtle accent-accent"
                />
                Fresh start
              </label>
            </div>

            {/* Row 2: Budget & feature flags */}
            <div>
              <label className="block text-xs text-text-secondary mb-1">
                Budget ($)
              </label>
              <input
                type="number"
                value={budget}
                onChange={(e) => setBudget(e.target.value)}
                placeholder="Unlimited"
                min="0.01"
                step="0.10"
                disabled={isRunning}
                className="w-full rounded-md border border-border-subtle bg-surface-raised px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent transition-colors disabled:opacity-50"
              />
            </div>
            <div>
              <label className="block text-xs text-text-secondary mb-1">
                Max hours
              </label>
              <input
                type="number"
                value={maxHours}
                onChange={(e) => setMaxHours(e.target.value)}
                placeholder="Unlimited"
                min="0.1"
                step="0.5"
                disabled={isRunning}
                className="w-full rounded-md border border-border-subtle bg-surface-raised px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent transition-colors disabled:opacity-50"
              />
            </div>
            <div className="flex items-end pb-1">
              <label className="flex items-center gap-2 text-sm text-text-secondary cursor-pointer">
                <input
                  type="checkbox"
                  checked={approvalGates}
                  onChange={(e) => setApprovalGates(e.target.checked)}
                  disabled={isRunning}
                  className="rounded border-border-subtle accent-accent"
                />
                Approval gates
              </label>
            </div>
            <div className="flex items-end pb-1">
              <label className="flex items-center gap-2 text-sm text-text-secondary cursor-pointer">
                <input
                  type="checkbox"
                  checked={autoPr}
                  onChange={(e) => setAutoPr(e.target.checked)}
                  disabled={isRunning}
                  className="rounded border-border-subtle accent-accent"
                />
                Auto-PR
              </label>
            </div>

          {/* Monitor daemon controls (only visible for swarm runs) */}
          {parallel > 1 && (
            <div className="col-span-4 mt-1 flex items-center gap-3 px-3 py-1.5 rounded-md border border-border-subtle bg-surface">
              <label className="flex items-center gap-2 text-xs text-text-secondary cursor-pointer">
                <input
                  type="checkbox"
                  checked={monitorEnabled}
                  onChange={(e) => setMonitorEnabled(e.target.checked)}
                  disabled={isRunning}
                  className="rounded border-border-subtle accent-accent"
                />
                Enable Monitor Daemon
              </label>
              {monitorEnabled && (
                <div className="flex items-center gap-1.5">
                  <label className="text-[10px] text-text-muted whitespace-nowrap">Interval:</label>
                  <input
                    type="range"
                    min="30"
                    max="300"
                    step="10"
                    value={monitorInterval}
                    onChange={(e) => setMonitorInterval(parseInt(e.target.value))}
                    disabled={isRunning}
                    className="w-20 accent-accent"
                  />
                  <span className="text-[10px] font-mono text-text-muted w-8 text-right">
                    {monitorInterval}s
                  </span>
                </div>
              )}
            </div>
          )}

          {/* Budget estimate */}
          <div className="col-span-4 mt-1 flex items-center gap-2 px-3 py-1.5 rounded-md border border-border-subtle bg-surface text-[11px] font-mono text-text-muted">
            <span className="text-text-secondary">Est:</span>
            <span>
              ${budgetEstimate.low.toFixed(2)} - ${budgetEstimate.high.toFixed(2)}
            </span>
            <span className="text-text-muted">
              for ~{budgetEstimate.tasks} tasks{budgetEstimate.workers > 1 ? ` with ${budgetEstimate.workers} workers` : ""}
            </span>
          </div>

          {/* Dispatch Overrides */}
          <div className="col-span-4 mt-1">
            <button
              type="button"
              onClick={() => setShowOverrides(!showOverrides)}
              className="text-xs text-text-muted hover:text-text-secondary transition-colors"
            >
              {showOverrides ? "\u25BC" : "\u25B6"} Dispatch Overrides
              {buildOverrides() && (
                <span className="ml-1.5 text-[10px] text-accent font-mono px-1 py-0.5 rounded border border-accent/30 bg-accent/10">
                  {buildOverrides()!.length} active
                </span>
              )}
            </button>

            {showOverrides && (
              <div className="mt-2 p-3 rounded-md border border-border-subtle bg-surface space-y-3">
                {/* Preset buttons */}
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-text-muted font-mono uppercase tracking-wider">Preset:</span>
                  {(["speed_run", "careful_mode", "custom"] as const).map((p) => (
                    <button
                      key={p}
                      type="button"
                      onClick={() => applyPreset(p)}
                      disabled={isRunning}
                      className={`text-[10px] font-mono px-2 py-1 rounded border transition-colors ${
                        ovPreset === p
                          ? "text-accent border-accent/30 bg-accent/10"
                          : "text-text-muted border-border-subtle hover:text-text-secondary"
                      } disabled:opacity-50`}
                    >
                      {p === "speed_run" ? "Speed Run" : p === "careful_mode" ? "Careful Mode" : "Custom"}
                    </button>
                  ))}
                </div>

                {/* Toggle switches */}
                <div className="grid grid-cols-3 gap-2">
                  <label className="flex items-center gap-2 text-xs text-text-secondary cursor-pointer">
                    <input
                      type="checkbox"
                      checked={ovSkipReview}
                      onChange={(e) => { setOvSkipReview(e.target.checked); setOvPreset("custom"); }}
                      disabled={isRunning}
                      className="rounded border-border-subtle accent-accent"
                    />
                    Skip Review
                  </label>
                  <label className="flex items-center gap-2 text-xs text-text-secondary cursor-pointer">
                    <input
                      type="checkbox"
                      checked={ovFocusPerf}
                      onChange={(e) => { setOvFocusPerf(e.target.checked); setOvPreset("custom"); }}
                      disabled={isRunning}
                      className="rounded border-border-subtle accent-accent"
                    />
                    Focus Performance
                  </label>
                  <label className="flex items-center gap-2 text-xs text-text-secondary cursor-pointer">
                    <input
                      type="checkbox"
                      checked={ovMinimalTests}
                      onChange={(e) => { setOvMinimalTests(e.target.checked); setOvPreset("custom"); }}
                      disabled={isRunning}
                      className="rounded border-border-subtle accent-accent"
                    />
                    Minimal Tests
                  </label>
                </div>

                {/* Max agents input */}
                <div className="flex items-center gap-2">
                  <label className="text-xs text-text-secondary whitespace-nowrap">Max Agents:</label>
                  <input
                    type="number"
                    value={ovMaxAgents}
                    onChange={(e) => { setOvMaxAgents(e.target.value); setOvPreset("custom"); }}
                    placeholder="Unlimited"
                    min="1"
                    max="10"
                    disabled={isRunning}
                    className="w-20 rounded-md border border-border-subtle bg-surface-raised px-2 py-1 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent transition-colors disabled:opacity-50"
                  />
                  <span className="text-[10px] text-text-muted">(1-10, empty = no limit)</span>
                </div>

                {/* Custom instruction */}
                <div>
                  <label className="block text-xs text-text-secondary mb-1">Custom Instruction</label>
                  <textarea
                    value={ovCustomInstruction}
                    onChange={(e) => { setOvCustomInstruction(e.target.value); setOvPreset("custom"); }}
                    placeholder="e.g., Prioritize security over speed..."
                    disabled={isRunning}
                    rows={2}
                    className="w-full rounded-md border border-border-subtle bg-surface-raised px-2 py-1.5 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent transition-colors disabled:opacity-50 resize-none"
                  />
                </div>
              </div>
            )}
          </div>

          {/* GitHub Integration */}
          <div className="col-span-4 mt-1">
            <span className="text-xs text-text-muted font-medium">GitHub Integration</span>
            <div className="mt-1.5 flex items-center gap-4">
              <label className="flex items-center gap-2 text-xs text-text-secondary cursor-pointer">
                <input
                  type="checkbox"
                  checked={githubSyncPull}
                  onChange={(e) => setGithubSyncPull(e.target.checked)}
                  disabled={isRunning}
                  className="rounded border-border-subtle accent-accent"
                />
                Import issues as tasks
              </label>
              <label className="flex items-center gap-2 text-xs text-text-secondary cursor-pointer">
                <input
                  type="checkbox"
                  checked={githubSyncPush}
                  onChange={(e) => setGithubSyncPush(e.target.checked)}
                  disabled={isRunning}
                  className="rounded border-border-subtle accent-accent"
                />
                Auto-push task status
              </label>
            </div>
          </div>
          </div>
        )}

        {/* Resume indicator */}
        {projectStatus?.resumable && !noResume && (
          <div className="flex items-center gap-2 px-3 py-2 rounded-md border border-accent/30 bg-accent/5">
            <span className="text-accent text-sm">&#x21BB;</span>
            <div className="flex-1">
              <span className="text-sm text-text-primary font-medium">
                Existing progress detected
              </span>
              <span className="text-xs text-text-secondary ml-2">
                {projectStatus.done}/{projectStatus.total} tasks completed ({projectStatus.percentage}%)
                {projectStatus.mode && ` \u2022 ${projectStatus.mode} mode`}
              </span>
            </div>
          </div>
        )}

        {/* Action buttons */}
        <div className="flex gap-2 pt-1">
          {!isRunning ? (
            <>
              <button
                type="submit"
                disabled={!projectDir.trim()}
                className="flex-1 rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {projectStatus?.resumable && !noResume
                  ? `Continue (${projectStatus.total - projectStatus.done} remaining)`
                  : mode === "greenfield" && taskInput.trim() && !activeTemplate
                    ? "Architect & Build"
                    : parallel > 1
                      ? `Run Swarm (${parallel} workers)`
                      : "Run Agent"}
              </button>
              {status === "completed" || status === "error" ? (
                <button
                  type="button"
                  onClick={onReset}
                  className="rounded-md border border-border-subtle px-4 py-2 text-sm text-text-secondary hover:border-border-default hover:text-text-primary transition-colors"
                >
                  Clear
                </button>
              ) : null}
            </>
          ) : (
            <button
              type="button"
              onClick={onStop}
              className="flex-1 rounded-md bg-error/20 border border-error/40 px-4 py-2 text-sm font-medium text-error hover:bg-error/30 transition-colors"
            >
              Stop Agent
            </button>
          )}
        </div>
      </form>

      {/* Folder picker modal */}
      {showFolderPicker && (
        <FolderPicker
          onSelect={(path) => {
            setProjectDir(path);
            setShowFolderPicker(false);
          }}
          onClose={() => setShowFolderPicker(false)}
        />
      )}

      {/* Template gallery modal */}
      {showTemplates && (
        <TemplateGallery
          onSelect={handleTemplateSelect}
          onClose={() => setShowTemplates(false)}
        />
      )}
    </>
  );
}
