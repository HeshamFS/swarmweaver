"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import type { Mode, RunConfig, PhaseModels, ProjectInfo, ProjectStatus } from "../../hooks/useSwarmWeaver";
import type { GlobalSettings } from "../../hooks/useGlobalSettings";
import { OmnibarProjectSource, type SourceType } from "./OmnibarProjectSource";
import { OmnibarAdvancedPanel, type StackPreferences, type DispatchOverride } from "./OmnibarAdvancedPanel";
import { HelpCircle } from "lucide-react";
import { MODELS, PRESETS, type PresetType } from "../../utils/constants";
import { MODE_ICONS } from "../../utils/modeIcons";

const MODE_LABELS: Record<string, string> = {
  greenfield: "Greenfield",
  feature: "Feature",
  refactor: "Refactor",
  fix: "Fix",
  evolve: "Evolve",
  security: "Security",
};

const MODE_DESCRIPTIONS: Record<Mode, string> = {
  greenfield: "Build a new project from a specification file",
  feature: "Add features to an existing codebase",
  refactor: "Restructure or migrate (e.g., JS to TS, C++ to Rust)",
  fix: "Diagnose and fix bugs in an existing project",
  evolve: "Open-ended improvement (tests, production-ready, performance)",
  security: "Scan for vulnerabilities with human-in-the-loop review before remediation",
};

const MODES: Mode[] = ["greenfield", "feature", "refactor", "fix", "evolve", "security"];

interface OmnibarProps {
  isFocused?: boolean;
  projects: ProjectInfo[];
  fetchProjects: () => void;
  checkProjectStatus: (path: string) => Promise<ProjectStatus | null>;
  fetchProjectSettings?: (path: string) => Promise<Record<string, unknown> | null>;
  saveProjectSettings?: (path: string, settings: Record<string, unknown>) => Promise<void>;
  onRunDirect: (config: RunConfig) => void;
  onRunArchitectOnly: (config: RunConfig) => void;
  onRunPlanOnly: (config: RunConfig) => void;
  onRunScanOnly: (config: RunConfig) => void;
  onStartQA?: (config: RunConfig) => void;
  globalSettings?: GlobalSettings;
  onUpdateGlobalSettings?: (partial: Partial<GlobalSettings>) => void;
}

export function Omnibar({
  isFocused = false,
  projects,
  fetchProjects,
  checkProjectStatus,
  fetchProjectSettings,
  saveProjectSettings,
  onRunDirect,
  onRunArchitectOnly,
  onRunPlanOnly,
  onRunScanOnly,
  onStartQA,
  globalSettings,
  onUpdateGlobalSettings,
}: OmnibarProps) {
  /* ── Project source ── */
  const [sourceType, setSourceType] = useState<SourceType>("new");
  const [projectDir, setProjectDir] = useState("");
  const [cloneUrl, setCloneUrl] = useState("");

  /* ── Task ── */
  const [input, setInput] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);

  /* ── Mode ── */
  const [modeOverride, setModeOverride] = useState<Mode | null>(null);

  /* ── Advanced (initialized from globalSettings) ── */
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [activePreset, setActivePreset] = useState<PresetType>("standard");
  const [model, setModel] = useState(globalSettings?.defaultModel || "claude-sonnet-4-6");
  const [parallel, setParallel] = useState(globalSettings?.defaultParallel || 1);
  const [budget, setBudget] = useState(globalSettings?.budgetLimit != null ? String(globalSettings.budgetLimit) : "");
  const [maxHours, setMaxHours] = useState(globalSettings?.maxHours != null ? String(globalSettings.maxHours) : "");
  const [useWorktree, setUseWorktree] = useState(globalSettings?.useWorktree ?? true);
  const [smartSwarm, setSmartSwarm] = useState(true);
  const [reviewPlan, setReviewPlan] = useState(false);
  const [approvalGates, setApprovalGates] = useState(globalSettings?.approvalGates ?? false);
  const [autoPr, setAutoPr] = useState(globalSettings?.autoPr ?? false);
  const [freshStart, setFreshStart] = useState(false);

  /* ── Per-phase model selection ── */
  const [phaseModels, setPhaseModels] = useState<PhaseModels>(
    globalSettings?.phaseModels
      ? { architect: globalSettings.phaseModels.architect || undefined, plan: globalSettings.phaseModels.plan || undefined, code: globalSettings.phaseModels.code || undefined }
      : {}
  );

  /* ── Greenfield stack preferences ── */
  const [stack, setStack] = useState<StackPreferences>({ frontend: "", backend: "", database: "", styling: "" });

  /* ── Dispatch overrides ── */
  const [overrides, setOverrides] = useState<DispatchOverride[]>([]);

  /* ── Skip Q&A setup (synced to globalSettings when available) ── */
  const skipQA = globalSettings?.skipQA ?? false;
  const toggleSkipQA = useCallback(() => {
    if (onUpdateGlobalSettings) {
      onUpdateGlobalSettings({ skipQA: !skipQA });
    }
  }, [skipQA, onUpdateGlobalSettings]);

  /* ── Sync local state from globalSettings when they load/change ── */
  const globalSyncRef = useRef(false);
  useEffect(() => {
    if (!globalSettings) return;

    // Skip per-project overridable settings if project settings have already loaded
    if (projectDir.trim() && sourceType !== "new") return;
    setModel(globalSettings.defaultModel || "claude-sonnet-4-6");
    setParallel(globalSettings.defaultParallel || 1);
    setBudget(globalSettings.budgetLimit != null ? String(globalSettings.budgetLimit) : "");
    setMaxHours(globalSettings.maxHours != null ? String(globalSettings.maxHours) : "");
    setUseWorktree(globalSettings.useWorktree ?? true);
    setApprovalGates(globalSettings.approvalGates ?? false);
    setAutoPr(globalSettings.autoPr ?? false);
    const pm = globalSettings.phaseModels;
    if (pm) {
      setPhaseModels({
        architect: pm.architect || undefined,
        plan: pm.plan || undefined,
        code: pm.code || undefined,
      });
    }
    globalSyncRef.current = true;
  }, [globalSettings]); // eslint-disable-line react-hooks/exhaustive-deps

  /* ── Cloning state ── */
  const [isCloning, setIsCloning] = useState(false);
  const [cloneError, setCloneError] = useState("");

  /* ── Focus ── */
  useEffect(() => {
    if (isFocused && inputRef.current) inputRef.current.focus();
  }, [isFocused]);

  useEffect(() => { fetchProjects(); }, [fetchProjects]);

  /* Load saved project settings when project changes */
  useEffect(() => {
    if (!fetchProjectSettings || !projectDir.trim() || sourceType === "new") return;
    let cancelled = false;
    fetchProjectSettings(projectDir).then((settings) => {
      if (cancelled || !settings) return;
      if (settings.default_model && typeof settings.default_model === "string") setModel(settings.default_model as string);
      if (settings.phase_models && typeof settings.phase_models === "object") setPhaseModels(settings.phase_models as PhaseModels);
      if (typeof settings.default_parallel === "number") setParallel(settings.default_parallel as number);
      if (typeof settings.use_worktree === "boolean") setUseWorktree(settings.use_worktree as boolean);
      if (typeof settings.approval_gates === "boolean") setApprovalGates(settings.approval_gates as boolean);
      if (typeof settings.budget_limit === "number") setBudget(String(settings.budget_limit));
    });
    return () => { cancelled = true; };
  }, [projectDir, sourceType, fetchProjectSettings]);

  /* Auto-resize textarea — grow with content but keep a minimum height */
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.max(el.scrollHeight, 80)}px`;
  }, [input]);

  /* Preset application */
  const applyPreset = useCallback((p: PresetType) => {
    setActivePreset(p);
    const preset = PRESETS.find((x) => x.id === p)!;
    setModel(preset.model);
    setPhaseModels({});  // Reset per-phase overrides to use preset model
    setParallel(preset.parallel);
    setApprovalGates(preset.approvalGates);
    setReviewPlan(preset.reviewPlan);
  }, []);

  /* ── Mode auto-detection ── */
  const parseIntent = useCallback(
    (text: string): { mode: Mode; confidence: number } | null => {
      const t = text.toLowerCase();
      if (/\b(fix|bug|error|issue|crash)\b/.test(t)) return { mode: "fix", confidence: 0.9 };
      if (/\b(refactor|clean\s?up|migrate|restructure)\b/.test(t)) return { mode: "refactor", confidence: 0.9 };
      if (/\b(security|vulnerability|audit|harden)\b/.test(t)) return { mode: "security", confidence: 0.9 };
      if (/\b(test|optimize|performance|speed\s?up|evolve)\b/.test(t)) return { mode: "evolve", confidence: 0.8 };
      if (/\b(create\s+a?\s*new|start\s+a|build\s+a?\s*new|scaffold|greenfield)\b/.test(t)) return { mode: "greenfield", confidence: 0.9 };
      if (/\b(add|implement|feature|build)\b/.test(t)) return { mode: "feature", confidence: 0.7 };
      return null;
    }, []
  );

  const detectedIntent = input.trim().length > 3 ? parseIntent(input) : null;
  const hasInput = input.trim().length > 0;

  /* Resolve mode: override > auto-detect > default.
     Only block greenfield for auto-detected mode — if user explicitly picked it, trust them. */
  const rawMode: Mode = modeOverride || detectedIntent?.mode || "greenfield";
  const currentMode: Mode =
    !modeOverride && (sourceType === "clone" || sourceType === "existing") && rawMode === "greenfield"
      ? "feature"
      : rawMode;

  /* Auto-switch source type based on mode */
  useEffect(() => {
    if (currentMode === "greenfield" && sourceType === "existing") {
      setSourceType("new");
    } else if (currentMode !== "greenfield" && sourceType === "new" && !projectDir) {
      setSourceType("existing");
    }
  }, [currentMode, sourceType, projectDir]);

  const [showModeDropdown, setShowModeDropdown] = useState(false);
  const [helpOpenFor, setHelpOpenFor] = useState<Mode | null>(null);
  const modeDropdownRef = useRef<HTMLDivElement>(null);

  /* Close dropdown on outside click */
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (modeDropdownRef.current && !modeDropdownRef.current.contains(e.target as Node)) {
        setShowModeDropdown(false);
        setHelpOpenFor(null);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const clearOverride = () => setModeOverride(null);

  /* ── Launch ── */
  const handleLaunch = async () => {
    let dir = projectDir;

    // For clone, clone first
    if (sourceType === "clone" && cloneUrl.trim()) {
      setIsCloning(true);
      setCloneError("");
      try {
        const res = await fetch("/api/clone", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url: cloneUrl.trim(), target_dir: projectDir || undefined }),
        });
        const data = await res.json();
        if (!data.success) {
          setCloneError(data.error || "Clone failed");
          setIsCloning(false);
          return;
        }
        dir = data.path;
        setProjectDir(dir);
      } catch {
        setCloneError("Network error during clone");
        setIsCloning(false);
        return;
      }
      setIsCloning(false);
    }

    // Default dir for new greenfield projects
    if (sourceType === "new" && !dir) {
      const slug = input.trim().slice(0, 30).replace(/[^a-zA-Z0-9]+/g, "-").toLowerCase() || "new-project";
      dir = `./generations/${slug}`;
    }

    if (!dir && currentMode !== "greenfield") return;
    if (!hasInput && currentMode !== "security") return;

    // Build stack hint for greenfield
    let ideaText = input.trim();
    if (currentMode === "greenfield") {
      const stackParts: string[] = [];
      if (stack.frontend) stackParts.push(`Frontend: ${stack.frontend}`);
      if (stack.backend) stackParts.push(`Backend: ${stack.backend}`);
      if (stack.database) stackParts.push(`Database: ${stack.database}`);
      if (stack.styling) stackParts.push(`Styling: ${stack.styling}`);
      if (stackParts.length > 0) {
        ideaText += `\n\nPreferred stack:\n${stackParts.join("\n")}`;
      }
    }

    // Build phase_models only if any overrides are set
    const hasPhaseOverrides = phaseModels.architect || phaseModels.plan || phaseModels.code;
    const resolvedPhaseModels: PhaseModels | undefined = hasPhaseOverrides
      ? {
          architect: phaseModels.architect || model,
          plan: phaseModels.plan || model,
          code: phaseModels.code || model,
        }
      : undefined;

    const config: RunConfig = {
      mode: currentMode,
      project_dir: dir,
      task_input: input.trim() || (currentMode === "security" ? "Full security audit" : ""),
      idea: currentMode === "greenfield" ? ideaText : undefined,
      model,
      phase_models: resolvedPhaseModels,
      no_resume: freshStart,
      parallel: !smartSwarm && parallel > 1 ? parallel : undefined,
      smart_swarm: smartSwarm || undefined,
      budget: budget ? parseFloat(budget) : undefined,
      max_hours: maxHours ? parseFloat(maxHours) : undefined,
      approval_gates: approvalGates || undefined,
      auto_pr: autoPr || undefined,
      worktree: useWorktree || undefined,
      overrides: overrides.filter((o) => o.active).length > 0
        ? overrides.filter((o) => o.active)
        : undefined,
    };

    // Auto-save project settings for next time
    if (saveProjectSettings && dir) {
      saveProjectSettings(dir, {
        default_model: model,
        phase_models: resolvedPhaseModels || null,
        default_parallel: parallel,
        use_worktree: useWorktree,
        approval_gates: approvalGates,
        budget_limit: budget ? parseFloat(budget) : null,
      });
    }

    // All modes go through the wizard WS.
    // onStartQA sets wizardStep="qa" and starts the correct WS (architect for greenfield, plan for others).
    // Even when skipQA is true, we still route through onStartQA to properly initialize the wizard flow.
    if (onStartQA) {
      onStartQA(config);
      return;
    }

    // Fallback if onStartQA is somehow unavailable
    if (currentMode === "greenfield") {
      onRunArchitectOnly(config);
    } else {
      onRunPlanOnly(config);
    }
  };

  /* ── Keyboard ── */
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      handleLaunch();
    } else if (e.key === "Enter" && !e.shiftKey && hasInput) {
      e.preventDefault();
      handleLaunch();
    } else if (e.key === "Escape") {
      inputRef.current?.blur();
    }
  };

  const canLaunch = (hasInput || currentMode === "security") && !isCloning;

  return (
    <div className="relative w-full max-w-4xl mx-auto">
      <div className="bg-[#121212] border border-[#333] flex flex-col shadow-2xl relative">
        {/* Project source */}
        <OmnibarProjectSource
          sourceType={sourceType}
          onSourceTypeChange={setSourceType}
          projectDir={projectDir}
          onProjectDirChange={setProjectDir}
          cloneUrl={cloneUrl}
          onCloneUrlChange={setCloneUrl}
          projects={projects}
          checkProjectStatus={checkProjectStatus}
        />

        {/* Clone error */}
        {cloneError && (
          <div className="px-4 py-2 text-[12px] font-mono text-[var(--color-error)] bg-[var(--color-error)]/5 border-b border-[#222]">
            {cloneError}
          </div>
        )}

        {/* Textarea */}
        <div className="p-4 relative bg-[#121212] cursor-text" onClick={() => inputRef.current?.focus()}>
          <div className="absolute top-4 left-4 text-[var(--color-accent)] font-mono">&gt;</div>
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={currentMode === "security" ? "Describe focus area (optional)..." : "Describe what you want to build or change..."}
            rows={3}
            style={{ minHeight: 80 }}
            spellCheck={false}
            className="w-full bg-transparent text-[#E0E0E0] leading-relaxed resize-none focus:outline-none cursor-text pl-6 font-mono"
          />
        </div>

        {/* Toolbar */}
        <div className="p-4 border-t border-[#333] flex flex-wrap items-center justify-between bg-[#0C0C0C] text-xs gap-4">
          <div className="flex items-center flex-wrap gap-4 md:gap-6">
            {/* Mode dropdown */}
            <div className="relative" ref={modeDropdownRef}>
              <button
                onClick={() => setShowModeDropdown((v) => !v)}
                className="flex items-center gap-2 px-3 py-1.5 text-[#E0E0E0] font-mono border border-[#333] bg-[#1A1A1A] hover:border-[#555] transition-colors"
              >
                {MODE_ICONS[currentMode] && React.createElement(MODE_ICONS[currentMode], {
                  size: 14,
                  className: "shrink-0",
                  style: { color: "var(--color-accent)" },
                })}
                <span>{MODE_LABELS[currentMode]}</span>
                <span className="text-[#555] text-[10px]">{"\u25BC"}</span>
              </button>

              {showModeDropdown && (
                <div className="absolute bottom-full left-0 mb-1 flex z-50 gap-0">
                  <div className="w-44 border border-[#333] bg-[#1A1A1A] shadow-lg py-1 overflow-hidden">
                    {MODES.map((m) => (
                      <div
                        key={m}
                        className="flex items-center gap-0 group/row"
                      >
                        <button
                          onClick={() => {
                            setModeOverride(m);
                            if (m === "greenfield") setSourceType("new");
                            else if (sourceType === "new" && !projectDir) setSourceType("existing");
                            setShowModeDropdown(false);
                            setHelpOpenFor(null);
                          }}
                          className={`flex-1 min-w-0 text-left px-3 py-1.5 text-[11px] font-mono flex items-center gap-2 hover:bg-[#222] transition-colors ${currentMode === m ? "font-bold" : ""}`}
                          style={{ color: currentMode === m ? "var(--color-accent)" : "#888" }}
                        >
                          {MODE_ICONS[m] && React.createElement(MODE_ICONS[m], {
                            size: 14,
                            className: "shrink-0",
                            style: { color: "var(--color-accent)" },
                          })}
                          {MODE_LABELS[m]}
                        </button>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setHelpOpenFor((prev) => (prev === m ? null : m));
                          }}
                          className="shrink-0 p-1.5 text-[#555] hover:text-[var(--color-accent)] transition-colors"
                          title={`What does ${MODE_LABELS[m]} do?`}
                          aria-label={`Explain ${MODE_LABELS[m]} mode`}
                        >
                          <HelpCircle size={12} strokeWidth={2} />
                        </button>
                      </div>
                    ))}
                  </div>
                  {helpOpenFor && (
                    <div className="shrink-0 w-56 max-w-[calc(100vw-12rem)] border border-[#333] bg-[#1A1A1A] shadow-lg p-3 text-[11px] font-mono text-[#C0C0C0] leading-relaxed">
                      <div className="font-bold text-[var(--color-accent)] mb-1">{MODE_LABELS[helpOpenFor]}</div>
                      {MODE_DESCRIPTIONS[helpOpenFor]}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Preset buttons (TUI toggle style) */}
            <div className="flex items-center border border-[#333] bg-[#0C0C0C]">
              {PRESETS.map((p) => (
                <button
                  key={p.id}
                  onClick={() => applyPreset(p.id)}
                  className={`px-3 py-1.5 font-mono text-xs transition-colors border-r border-[#333] last:border-r-0 ${activePreset === p.id
                    ? "text-[#0C0C0C] bg-[#888] font-bold"
                    : "text-[#555] hover:text-[#888]"
                    }`}
                >
                  {activePreset === p.id ? `[ ${p.label} ]` : p.label}
                </button>
              ))}
            </div>

            {/* Skip Setup toggle */}
            {onStartQA && (
              <button
                onClick={toggleSkipQA}
                className="flex items-center gap-2 cursor-pointer group"
                title={skipQA ? "Q&A setup is skipped" : "Q&A setup is enabled — click to skip"}
              >
                <span className={`font-bold font-mono ${skipQA ? "text-[#555]" : "text-[var(--color-accent)]"} group-hover:text-[var(--color-accent)]`}>
                  {skipQA ? "[ ]" : "[x]"}
                </span>
                <span className={`font-mono text-xs ${skipQA ? "text-[#555]" : "text-[#888]"} group-hover:text-[#E0E0E0] transition-colors`}>
                  Setup
                </span>
              </button>
            )}
          </div>

          <div className="flex items-center gap-6">
            {/* Advanced toggle */}
            <button
              onClick={() => setShowAdvanced((v) => !v)}
              className="text-[#555] cursor-pointer hover:text-[#E0E0E0] flex items-center transition-colors font-mono text-xs"
            >
              {"\u2699"} {showAdvanced ? "Hide options" : "Advanced"} <span className="text-[10px] ml-2">{showAdvanced ? "\u25B2" : "\u25BC"}</span>
            </button>

            {/* Launch button */}
            <button
              onClick={handleLaunch}
              disabled={!canLaunch}
              className="bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-[#0C0C0C] px-8 py-2 font-bold font-mono flex items-center transition-colors uppercase tracking-widest shadow-[0_0_10px_var(--color-accent-glow)] disabled:opacity-20"
              title={isCloning ? "Cloning..." : "Launch (Enter)"}
            >
              {isCloning ? "Cloning..." : "Launch"} <span className="ml-3 font-normal">{"\u2192"}</span>
            </button>
          </div>
        </div>

        {/* Advanced panel */}
        <OmnibarAdvancedPanel
          isOpen={showAdvanced}
          mode={currentMode}
          model={model}
          onModelChange={setModel}
          phaseModels={phaseModels}
          onPhaseModelsChange={setPhaseModels}
          parallel={parallel}
          onParallelChange={setParallel}
          smartSwarm={smartSwarm}
          onSmartSwarmChange={setSmartSwarm}
          budget={budget}
          onBudgetChange={setBudget}
          maxHours={maxHours}
          onMaxHoursChange={setMaxHours}
          useWorktree={useWorktree}
          onWorktreeChange={setUseWorktree}
          reviewPlan={reviewPlan}
          onReviewPlanChange={setReviewPlan}
          approvalGates={approvalGates}
          onApprovalGatesChange={setApprovalGates}
          autoPr={autoPr}
          onAutoPrChange={setAutoPr}
          freshStart={freshStart}
          onFreshStartChange={setFreshStart}
          stack={stack}
          onStackChange={setStack}
          overrides={overrides}
          onOverridesChange={setOverrides}
          globalSettings={globalSettings}
        />
      </div>

      {/* Keyboard hints */}
      <div className="flex flex-wrap items-center justify-center gap-6 mt-6 text-[#555] text-xs uppercase tracking-wider font-mono">
        <div className="flex items-center">
          <span className="border border-[#333] px-2 py-0.5 mr-2 text-[#888] bg-[#121212]">{"\u21B5"}</span> launch
        </div>
        <div className="flex items-center">
          <span className="border border-[#333] px-2 py-0.5 mr-2 text-[#888] bg-[#121212]">{"\u21E7"} {"\u21B5"}</span> new line
        </div>
      </div>
    </div>
  );
}
