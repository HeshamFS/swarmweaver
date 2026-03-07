"use client";

import { useState } from "react";
import type { Mode, PhaseModels } from "../../hooks/useSwarmWeaver";
import type { GlobalSettings } from "../../hooks/useGlobalSettings";
import { MODELS } from "../../utils/constants";

const STACK_OPTIONS = {
  frontend: ["", "React", "Next.js", "Vue", "Svelte", "Angular", "Vanilla JS"],
  backend: ["", "FastAPI", "Express", "Django", "Flask", "Spring Boot", "Go", "Rust"],
  database: ["", "PostgreSQL", "MySQL", "MongoDB", "SQLite", "Redis", "Supabase"],
  styling: ["", "Tailwind CSS", "CSS Modules", "Styled Components", "Sass", "Material UI", "shadcn/ui"],
};

export interface StackPreferences {
  frontend: string;
  backend: string;
  database: string;
  styling: string;
}

export interface DispatchOverride {
  directive: string;
  value?: string | null;
  active: boolean;
}

interface OmnibarAdvancedPanelProps {
  isOpen: boolean;
  mode: Mode;
  model: string;
  onModelChange: (m: string) => void;
  phaseModels: PhaseModels;
  onPhaseModelsChange: (pm: PhaseModels) => void;
  parallel: number;
  onParallelChange: (n: number) => void;
  smartSwarm: boolean;
  onSmartSwarmChange: (v: boolean) => void;
  budget: string;
  onBudgetChange: (v: string) => void;
  maxHours: string;
  onMaxHoursChange: (v: string) => void;
  useWorktree: boolean;
  onWorktreeChange: (v: boolean) => void;
  reviewPlan: boolean;
  onReviewPlanChange: (v: boolean) => void;
  approvalGates: boolean;
  onApprovalGatesChange: (v: boolean) => void;
  autoPr: boolean;
  onAutoPrChange: (v: boolean) => void;
  freshStart: boolean;
  onFreshStartChange: (v: boolean) => void;
  /* Greenfield-specific */
  stack: StackPreferences;
  onStackChange: (stack: StackPreferences) => void;
  /* Dispatch overrides */
  overrides: DispatchOverride[];
  onOverridesChange: (overrides: DispatchOverride[]) => void;
  /* Global settings for inherited indicators */
  globalSettings?: GlobalSettings;
}

/* All options available for all modes — the backend accepts every flag regardless of mode */

export function OmnibarAdvancedPanel({
  isOpen,
  mode,
  model,
  onModelChange,
  phaseModels,
  onPhaseModelsChange,
  parallel,
  onParallelChange,
  smartSwarm,
  onSmartSwarmChange,
  budget,
  onBudgetChange,
  maxHours,
  onMaxHoursChange,
  useWorktree,
  onWorktreeChange,
  reviewPlan,
  onReviewPlanChange,
  approvalGates,
  onApprovalGatesChange,
  autoPr,
  onAutoPrChange,
  freshStart,
  onFreshStartChange,
  stack,
  onStackChange,
  overrides,
  onOverridesChange,
  globalSettings,
}: OmnibarAdvancedPanelProps) {
  const [showOverrides, setShowOverrides] = useState(false);
  const [ovCustomInstruction, setOvCustomInstruction] = useState("");

  const toggleOverride = (directive: string) => {
    const existing = overrides.find((o) => o.directive === directive);
    if (existing) {
      onOverridesChange(overrides.map((o) => o.directive === directive ? { ...o, active: !o.active } : o));
    } else {
      onOverridesChange([...overrides, { directive, active: true }]);
    }
  };

  const isActive = (directive: string) => overrides.find((o) => o.directive === directive)?.active ?? false;
  const activeCount = overrides.filter((o) => o.active).length;
  const selectClass = "bg-[#1A1A1A] text-[#E0E0E0] text-[11px] font-mono px-2 py-1.5 border border-[#333] focus:outline-none focus:border-[var(--color-accent)]";
  const inputClass = `${selectClass} w-16`;

  return (
    <div
      className="omnibar-advanced-panel border-t border-[#333] overflow-hidden"
      style={{ maxHeight: isOpen ? 500 : 0 }}
    >
      <div className="px-4 py-3 space-y-3 bg-[#121212]">
        {/* Header */}
        <div className="flex items-center gap-2">
          <span className="text-[#555] font-mono">{"\u2699"}</span>
          <span className="text-[11px] font-bold text-[#888] uppercase tracking-wider font-mono">
            Advanced Options
          </span>
        </div>

        {/* Greenfield: Stack Preferences */}
        {mode === "greenfield" && (
          <div>
            <div className="text-[10px] font-bold text-[#555] uppercase tracking-wider mb-2 font-mono">
              Stack Preferences <span className="font-normal normal-case">(optional)</span>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {(Object.keys(STACK_OPTIONS) as (keyof typeof STACK_OPTIONS)[]).map((key) => (
                <label key={key} className="block">
                  <span className="text-[10px] text-[#555] mb-0.5 block capitalize font-mono">{key}</span>
                  <select
                    value={stack[key]}
                    onChange={(e) => onStackChange({ ...stack, [key]: e.target.value })}
                    className={`${selectClass} w-full`}
                  >
                    {STACK_OPTIONS[key].map((opt) => (
                      <option key={opt} value={opt}>{opt || `Any`}</option>
                    ))}
                  </select>
                </label>
              ))}
            </div>
          </div>
        )}

        {/* Per-phase model selection */}
        <div>
          <div className="text-[10px] font-bold text-[#555] uppercase tracking-wider mb-2 font-mono">
            Model per Stage
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            {mode === "greenfield" ? (
              <>
                <Field label="Architect">
                  <select
                    value={phaseModels.architect || model}
                    onChange={(e) => onPhaseModelsChange({ ...phaseModels, architect: e.target.value })}
                    className={selectClass}
                  >
                    {MODELS.map((m) => (
                      <option key={m.id} value={m.id}>{m.label}</option>
                    ))}
                  </select>
                </Field>
                <Field label="Planning">
                  <select
                    value={phaseModels.plan || model}
                    onChange={(e) => onPhaseModelsChange({ ...phaseModels, plan: e.target.value })}
                    className={selectClass}
                  >
                    {MODELS.map((m) => (
                      <option key={m.id} value={m.id}>{m.label}</option>
                    ))}
                  </select>
                </Field>
                <Field label="Coding">
                  <select
                    value={phaseModels.code || model}
                    onChange={(e) => onPhaseModelsChange({ ...phaseModels, code: e.target.value })}
                    className={selectClass}
                  >
                    {MODELS.map((m) => (
                      <option key={m.id} value={m.id}>{m.label}</option>
                    ))}
                  </select>
                </Field>
              </>
            ) : (
              <>
                <Field label="Planning">
                  <select
                    value={phaseModels.plan || model}
                    onChange={(e) => onPhaseModelsChange({ ...phaseModels, plan: e.target.value })}
                    className={selectClass}
                  >
                    {MODELS.map((m) => (
                      <option key={m.id} value={m.id}>{m.label}</option>
                    ))}
                  </select>
                </Field>
                <Field label="Implementation">
                  <select
                    value={phaseModels.code || model}
                    onChange={(e) => onPhaseModelsChange({ ...phaseModels, code: e.target.value })}
                    className={selectClass}
                  >
                    {MODELS.map((m) => (
                      <option key={m.id} value={m.id}>{m.label}</option>
                    ))}
                  </select>
                </Field>
              </>
            )}
          </div>
        </div>

        {/* Row 1: Workers + Budget + Hours */}
        <div className="flex items-center gap-3 flex-wrap">
          <Field label={mode === "security" ? "Auditors" : "Workers"}>
            <select
              value={parallel}
              onChange={(e) => onParallelChange(Number(e.target.value))}
              className={`${selectClass} w-14`}
            >
              {[1, 2, 3, 4, 5].map((n) => (
                <option key={n} value={n}>{n}</option>
              ))}
            </select>
            <SettingsBadge isGlobal={globalSettings != null && parallel === (globalSettings.defaultParallel ?? 1)} />
          </Field>

          <Field label="Budget $">
            <input
              type="text"
              value={budget}
              onChange={(e) => onBudgetChange(e.target.value.replace(/[^0-9.]/g, ""))}
              placeholder="--"
              className={inputClass}
            />
            <SettingsBadge isGlobal={globalSettings != null && budget === (globalSettings.budgetLimit != null ? String(globalSettings.budgetLimit) : "")} />
          </Field>

          <Field label="Max hours">
            <input
              type="text"
              value={maxHours}
              onChange={(e) => onMaxHoursChange(e.target.value.replace(/[^0-9.]/g, ""))}
              placeholder="--"
              className={`${selectClass} w-14`}
            />
            <SettingsBadge isGlobal={globalSettings != null && maxHours === (globalSettings.maxHours != null ? String(globalSettings.maxHours) : "")} />
          </Field>
        </div>

        {/* Row 2: Toggles */}
        <div className="flex items-center gap-4 flex-wrap">
          <span className="flex items-center gap-0.5">
            <Checkbox checked={useWorktree} onChange={onWorktreeChange} label="Use worktree" hint="Isolate changes in a git branch" />
            <SettingsBadge isGlobal={globalSettings != null && useWorktree === (globalSettings.useWorktree ?? true)} />
          </span>
          <Checkbox
            checked={smartSwarm}
            onChange={onSmartSwarmChange}
            label="Smart Swarm"
            hint="AI orchestrator (Opus) dynamically manages Sonnet workers"
          />
          <Checkbox
            checked={reviewPlan}
            onChange={onReviewPlanChange}
            label="Review plan first"
            disabled={mode === "greenfield" || mode === "fix" || mode === "security"}
            hint={
              mode === "greenfield" ? "Greenfield includes spec + task list review"
                : mode === "fix" ? "Fix mode investigates and fixes directly"
                : mode === "security" ? "Security mode already includes scan review"
                : "Pause to review plan before building"
            }
          />
          <span className="flex items-center gap-0.5">
            <Checkbox checked={approvalGates} onChange={onApprovalGatesChange} label="Approval gates" hint="Pauses between build iterations for human review" />
            <SettingsBadge isGlobal={globalSettings != null && approvalGates === (globalSettings.approvalGates ?? false)} />
          </span>
          <span className="flex items-center gap-0.5">
            <Checkbox checked={autoPr} onChange={onAutoPrChange} label="Auto-create PR" hint="Open a pull request on completion" />
            <SettingsBadge isGlobal={globalSettings != null && autoPr === (globalSettings.autoPr ?? false)} />
          </span>
          <Checkbox checked={freshStart} onChange={onFreshStartChange} label="Fresh start" hint="Ignore previous progress" />
        </div>

        {/* Dispatch Overrides (collapsible) */}
        {(smartSwarm || parallel > 1) && (
          <div>
            <button
              type="button"
              onClick={() => setShowOverrides((v) => !v)}
              className="text-[11px] font-mono text-[#555] hover:text-[#888] transition-colors flex items-center gap-1.5"
            >
              <span>{showOverrides ? "\u25BC" : "\u25B6"}</span>
              Dispatch Overrides
              {activeCount > 0 && (
                <span className="text-[9px] text-[var(--color-accent)] font-mono px-1 py-0.5 border border-[var(--color-accent)]/30 bg-[var(--color-accent)]/10">
                  {activeCount} active
                </span>
              )}
            </button>

            {showOverrides && (
              <div className="mt-2 p-2 border border-[#333] bg-[#0C0C0C] space-y-2">
                <div className="flex items-center gap-3 flex-wrap">
                  <Checkbox checked={isActive("SKIP_REVIEW")} onChange={() => toggleOverride("SKIP_REVIEW")} label="Skip Review" />
                  <Checkbox checked={isActive("FOCUS_PERFORMANCE")} onChange={() => toggleOverride("FOCUS_PERFORMANCE")} label="Focus Performance" />
                  <Checkbox checked={isActive("MINIMAL_TESTS")} onChange={() => toggleOverride("MINIMAL_TESTS")} label="Minimal Tests" />
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-[#555] font-mono">Custom:</span>
                  <input
                    type="text"
                    value={ovCustomInstruction}
                    onChange={(e) => {
                      setOvCustomInstruction(e.target.value);
                      const filtered = overrides.filter((o) => o.directive !== "CUSTOM_INSTRUCTION");
                      if (e.target.value.trim()) {
                        onOverridesChange([...filtered, { directive: "CUSTOM_INSTRUCTION", value: e.target.value.trim(), active: true }]);
                      } else {
                        onOverridesChange(filtered);
                      }
                    }}
                    placeholder="e.g., Prioritize security..."
                    className={`${selectClass} flex-1`}
                  />
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex items-center gap-1.5 text-[11px] text-[#555] font-mono font-medium">
      {label}
      {children}
    </label>
  );
}

function SettingsBadge({ isGlobal }: { isGlobal: boolean }) {
  if (isGlobal) {
    return <span className="text-[9px] text-[#555] font-mono ml-1">(global)</span>;
  }
  return <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-warning)] inline-block ml-1" title="Overriding global default" />;
}

function Checkbox({ checked, onChange, label, hint, disabled }: { checked: boolean; onChange: (v: boolean) => void; label: string; hint?: string; disabled?: boolean }) {
  return (
    <label
      className={`flex items-center gap-1.5 text-[11px] font-mono select-none transition-colors ${
        disabled
          ? "text-[#555] opacity-50 cursor-not-allowed"
          : "text-[#888] cursor-pointer hover:text-[#E0E0E0]"
      }`}
      title={hint}
    >
      <span className={`font-bold ${!disabled && checked ? "text-[var(--color-accent)]" : "text-[#555]"}`}>
        {checked && !disabled ? "[x]" : "[ ]"}
      </span>
      <input
        type="checkbox"
        checked={checked && !disabled}
        onChange={(e) => { if (!disabled) onChange(e.target.checked); }}
        disabled={disabled}
        className="sr-only"
      />
      {label}
    </label>
  );
}
