"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import type { Mode, RunConfig } from "../hooks/useSwarmWeaver";
import { MODE_ICONS } from "../utils/modeIcons";

const MODE_LABELS: Record<string, string> = {
  greenfield: "Greenfield",
  feature: "Feature",
  refactor: "Refactor",
  fix: "Fix",
  evolve: "Evolve",
  security: "Security",
};

const MODES: Mode[] = ["greenfield", "feature", "refactor", "fix", "evolve", "security"];

// Mode button styling: same as Omnibar (distinct icons, accent color for icons)
const MODE_BADGE: Record<string, string> = {
  greenfield: "bg-[var(--color-surface-1)] text-[var(--color-text-primary)] border-[var(--color-border-default)]",
  feature: "bg-[var(--color-surface-1)] text-[var(--color-text-primary)] border-[var(--color-border-default)]",
  refactor: "bg-[var(--color-surface-1)] text-[var(--color-text-primary)] border-[var(--color-border-default)]",
  fix: "bg-[var(--color-surface-1)] text-[var(--color-text-primary)] border-[var(--color-border-default)]",
  evolve: "bg-[var(--color-surface-1)] text-[var(--color-text-primary)] border-[var(--color-border-default)]",
  security: "bg-[var(--color-surface-1)] text-[var(--color-text-primary)] border-[var(--color-border-default)]",
};

const MODELS = [
  { id: "claude-opus-4-6", label: "Opus 4.6" },
  { id: "claude-sonnet-4-6", label: "Sonnet 4.6" },
  { id: "claude-sonnet-4-5-20250929", label: "Sonnet 4.5" },
  { id: "claude-haiku-4-5-20251001", label: "Haiku 4.5" },
];

interface FloatingActionBarProps {
  status: string;
  mode: string | null;
  currentProject: string;
  tasksDone: number;
  tasksTotal: number;
  currentPhase?: string;
  startedAt?: string;
  budgetUsed?: number;
  budgetLimit?: number;
  currentModel?: string;
  onStop: () => void;
  onSendSteering: (message: string, type?: string) => void;
  onRun: (config: RunConfig) => void;
  onModelChange?: (model: string) => void;
}

/* ── Duration timer hook ── */
function useElapsedTime(startedAt?: string, isRunning?: boolean): string {
  const [elapsed, setElapsed] = useState("");
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!startedAt || !isRunning) {
      setElapsed("");
      if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null; }
      return;
    }
    function update() {
      const start = new Date(startedAt!).getTime();
      const diffSec = Math.max(0, Math.floor((Date.now() - start) / 1000));
      const h = Math.floor(diffSec / 3600);
      const m = Math.floor((diffSec % 3600) / 60);
      const s = diffSec % 60;
      setElapsed(h > 0
        ? `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`
        : `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`);
    }
    update();
    intervalRef.current = setInterval(update, 1000);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [startedAt, isRunning]);
  return elapsed;
}

function budgetColor(used: number, limit: number): string {
  const pct = limit > 0 ? used / limit : 0;
  if (pct >= 0.8) return "text-error";
  if (pct >= 0.5) return "text-warning";
  return "text-text-secondary";
}

export function FloatingActionBar({
  status,
  mode,
  currentProject,
  tasksDone,
  tasksTotal,
  currentPhase,
  startedAt,
  budgetUsed,
  budgetLimit,
  currentModel,
  onStop,
  onSendSteering,
  onRun,
  onModelChange,
}: FloatingActionBarProps) {
  const isRunning = status === "running" || status === "starting";
  const isIdle = !isRunning;
  const elapsed = useElapsedTime(startedAt, isRunning);
  const progressPct = tasksTotal > 0 ? Math.round((tasksDone / tasksTotal) * 100) : 0;

  const [message, setMessage] = useState("");
  const [selectedMode, setSelectedMode] = useState<Mode>((mode as Mode) || "feature");
  const [selectedModel, setSelectedModel] = useState<string | undefined>(currentModel);
  const [showModeDropdown, setShowModeDropdown] = useState(false);
  const [showModelDropdown, setShowModelDropdown] = useState(false);
  const [projectFiles, setProjectFiles] = useState<string[]>([]);
  const [atQuery, setAtQuery] = useState<string | null>(null);
  const [selectedSuggestion, setSelectedSuggestion] = useState(0);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const modelDropdownRef = useRef<HTMLDivElement>(null);
  const suggestionsRef = useRef<HTMLDivElement>(null);

  /* Sync mode and model when parent changes */
  useEffect(() => {
    if (mode) setSelectedMode(mode as Mode);
  }, [mode]);
  useEffect(() => {
    if (currentModel) setSelectedModel(currentModel);
  }, [currentModel]);

  /* Fetch project files on mount for @file autocomplete */
  useEffect(() => {
    if (!currentProject) return;
    fetch(`/api/project-files?path=${encodeURIComponent(currentProject)}&limit=500`)
      .then((r) => r.ok ? r.json() : { files: [] })
      .then((d) => setProjectFiles(d.files || []))
      .catch(() => {});
  }, [currentProject]);

  /* Compute suggestions reactively from atQuery + projectFiles */
  const fileSuggestions = atQuery !== null
    ? projectFiles.filter((f) => f.toLowerCase().includes(atQuery.toLowerCase())).slice(0, 10)
    : [];
  const showFileSuggestions = fileSuggestions.length > 0;

  /* Close dropdowns on outside click */
  useEffect(() => {
    const h = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) setShowModeDropdown(false);
      if (modelDropdownRef.current && !modelDropdownRef.current.contains(e.target as Node)) setShowModelDropdown(false);
      if (suggestionsRef.current && !suggestionsRef.current.contains(e.target as Node)) setAtQuery(null);
    };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  /* Detect @mention in textarea */
  const handleMessageChange = useCallback((value: string) => {
    setMessage(value);
    // Use setTimeout so selectionStart is updated after React's synthetic event
    setTimeout(() => {
      const el = inputRef.current;
      if (!el) return;
      const cursor = el.selectionStart ?? value.length;
      const before = value.slice(0, cursor);
      const atMatch = before.match(/@([\w\-./\\]*)$/);
      if (atMatch) {
        setAtQuery(atMatch[1]);
        setSelectedSuggestion(0);
      } else {
        setAtQuery(null);
      }
    }, 0);
  }, []);

  /* Insert selected file suggestion */
  const insertSuggestion = useCallback((file: string) => {
    const el = inputRef.current;
    if (!el) return;
    const cursor = el.selectionStart ?? message.length;
    const before = message.slice(0, cursor);
    const after = message.slice(cursor);
    const atIndex = before.lastIndexOf("@");
    if (atIndex === -1) return;
    const newMsg = before.slice(0, atIndex) + "@" + file + " " + after;
    setMessage(newMsg);
    setAtQuery(null);
    el.focus();
    requestAnimationFrame(() => {
      const pos = atIndex + 1 + file.length + 1;
      el.setSelectionRange(pos, pos);
    });
  }, [message]);

  /* Ctrl+Q to stop */
  useEffect(() => {
    if (!isRunning) return;
    const h = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && (e.key === "q" || e.key === "Q")) { e.preventDefault(); onStop(); }
    };
    document.addEventListener("keydown", h);
    return () => document.removeEventListener("keydown", h);
  }, [isRunning, onStop]);

  const handleSend = async () => {
    const msg = message.trim();
    if (!msg) return;
    if (isRunning) {
      onSendSteering(msg, "instruction");
    } else {
      // Resolve model from selection or project settings — no hardcoded fallback
      let model = selectedModel;
      if (!model && currentProject) {
        try {
          const r = await fetch(`/api/projects/settings?path=${encodeURIComponent(currentProject)}`);
          if (r.ok) {
            const d = await r.json();
            if (d?.settings?.default_model) model = d.settings.default_model;
          }
        } catch {
          /* ignore */
        }
        if (!model) {
          try {
            const r = await fetch("/api/default-model");
            if (r.ok) {
              const d = await r.json();
              if (d?.default_model) model = d.default_model;
            }
          } catch {
            /* ignore */
          }
        }
      }
      onRun({
        mode: selectedMode,
        project_dir: currentProject,
        task_input: msg,
        idea: selectedMode === "greenfield" ? msg : undefined,
        model: model ?? "claude-sonnet-4-6", // fallback only when all fetches fail
        no_resume: false,
      });
    }
    setMessage("");
    inputRef.current?.focus();
  };

  return (
    <div className="shrink-0 border-t border-[var(--color-border-subtle)] bg-[var(--color-surface-base)]">
      {/* Top row: status indicators */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-[var(--color-border-subtle)]">
        {/* Mode dropdown */}
        <div className="relative" ref={dropdownRef}>
          <button
            onClick={() => setShowModeDropdown((v) => !v)}
            className={`text-[10px] font-mono font-medium px-2 py-0.5 border shrink-0 flex items-center gap-1.5 ${MODE_BADGE[selectedMode] || "text-[var(--color-text-muted)] border-[var(--color-border-default)] bg-[var(--color-surface-1)]"}`}
          >
            {MODE_ICONS[selectedMode] && React.createElement(MODE_ICONS[selectedMode], {
              size: 14,
              className: "shrink-0",
              style: { color: "var(--color-accent)" },
            })}
            {MODE_LABELS[selectedMode] || selectedMode}
            <svg className="w-2.5 h-2.5 opacity-50" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="m6 9 6 6 6-6" /></svg>
          </button>
          {showModeDropdown && (
            <div className="absolute bottom-full left-0 mb-1 w-36 border border-[var(--color-border-default)] bg-[var(--color-surface-2)] shadow-lg z-50 py-1">
              {MODES.map((m) => (
                <button
                  key={m}
                  onClick={() => { setSelectedMode(m); setShowModeDropdown(false); }}
                  className={`w-full text-left px-3 py-1.5 text-[11px] font-mono flex items-center gap-2 hover:bg-[var(--color-border-subtle)] transition-colors ${selectedMode === m ? "font-bold" : ""}`}
                  style={{ color: selectedMode === m ? "var(--color-accent)" : "var(--color-text-secondary)" }}
                >
                  {MODE_ICONS[m] && React.createElement(MODE_ICONS[m], {
                    size: 14,
                    className: "shrink-0",
                    style: { color: "var(--color-accent)" },
                  })}
                  {MODE_LABELS[m]}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Model dropdown */}
        <div className="relative" ref={modelDropdownRef}>
          <button
            onClick={() => setShowModelDropdown((v) => !v)}
            className="text-[10px] font-mono font-medium px-2 py-0.5 border shrink-0 flex items-center gap-1 bg-[var(--color-surface-1)] text-[var(--color-text-secondary)] border-[var(--color-border-default)] hover:text-[var(--color-text-primary)] transition-colors"
          >
            {MODELS.find((m) => m.id === selectedModel)?.label || selectedModel || "—"}
            <svg className="w-2.5 h-2.5 opacity-50" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="m6 9 6 6 6-6" /></svg>
          </button>
          {showModelDropdown && (
            <div className="absolute bottom-full left-0 mb-1 w-40 border border-[var(--color-border-default)] bg-[var(--color-surface-2)] shadow-lg z-50 py-1">
              {MODELS.map((m) => (
                <button
                  key={m.id}
                  onClick={() => {
                    setSelectedModel(m.id);
                    setShowModelDropdown(false);
                    if (onModelChange) onModelChange(m.id);
                    // If running, send model change via steering
                    if (isRunning) {
                      onSendSteering(m.id, "model_change");
                    }
                  }}
                  className={`w-full text-left px-3 py-1.5 text-[11px] font-mono flex items-center gap-2 hover:bg-[var(--color-border-subtle)] transition-colors ${selectedModel === m.id ? "font-medium text-[var(--color-text-primary)]" : "text-[var(--color-text-secondary)]"}`}
                >
                  {m.label}
                  {selectedModel === m.id && <span className="ml-auto text-[9px] text-[var(--color-accent)]">active</span>}
                </button>
              ))}
            </div>
          )}
        </div>

        <span className="text-[var(--color-border-default)]">|</span>

        {/* Running indicators */}
        {isRunning && elapsed && (
          <div className="flex items-center gap-1.5 shrink-0">
            <span className="w-1.5 h-1.5 bg-[var(--color-accent)]" />
            <span className="text-[11px] font-mono text-[var(--color-text-primary)] tabular-nums">{elapsed}</span>
          </div>
        )}

        {/* Status badge when idle */}
        {isIdle && (
          <span className={`text-[10px] font-mono font-medium px-2 py-0.5 border ${status === "completed" ? "border-[var(--color-success)] text-[var(--color-success)]" : status === "error" ? "border-[var(--color-error)] text-[var(--color-error)]" : "border-[var(--color-border-default)] text-[var(--color-text-muted)]"}`}>
            {status === "completed" ? "Completed" : status === "error" ? "Error" : "Ready"}
          </span>
        )}

        <span className="text-[var(--color-border-default)]">|</span>

        {/* Progress — ASCII bar */}
        {tasksTotal > 0 && (() => {
          const blocks = 10;
          const filled = Math.round((tasksDone / tasksTotal) * blocks);
          return (
            <div className="flex items-center gap-2 shrink-0 font-mono text-xs">
              <span className="text-[var(--color-accent)] tracking-widest">{"\u2593".repeat(filled)}</span>
              <span className="text-[var(--color-border-default)] tracking-widest">{"\u2591".repeat(blocks - filled)}</span>
              <span className="text-[var(--color-text-secondary)]">{tasksDone}/{tasksTotal}</span>
            </div>
          );
        })()}

        {/* Phase */}
        {isRunning && currentPhase && (
          <>
            <span className="text-[var(--color-border-default)]">|</span>
            <span className="text-[11px] text-[var(--color-text-secondary)] truncate max-w-[160px]">{currentPhase}</span>
          </>
        )}

        {/* Budget */}
        {budgetUsed != null && budgetLimit != null && budgetLimit > 0 && (
          <>
            <span className="text-[var(--color-border-default)]">|</span>
            <span className={`text-[11px] font-mono whitespace-nowrap ${budgetColor(budgetUsed, budgetLimit)}`}>
              ${budgetUsed.toFixed(2)} / ${budgetLimit.toFixed(2)}
            </span>
          </>
        )}
      </div>

      {/* Textarea row with @file autocomplete */}
      <div className="px-3 pt-3 pb-2 relative" ref={suggestionsRef}>
        <textarea
          ref={inputRef}
          value={message}
          onChange={(e) => handleMessageChange(e.target.value)}
          onKeyDown={(e) => {
            // Handle autocomplete navigation
            if (showFileSuggestions && fileSuggestions.length > 0) {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setSelectedSuggestion((s) => Math.min(s + 1, fileSuggestions.length - 1));
                return;
              }
              if (e.key === "ArrowUp") {
                e.preventDefault();
                setSelectedSuggestion((s) => Math.max(s - 1, 0));
                return;
              }
              if (e.key === "Tab" || (e.key === "Enter" && fileSuggestions[selectedSuggestion])) {
                e.preventDefault();
                insertSuggestion(fileSuggestions[selectedSuggestion]);
                return;
              }
              if (e.key === "Escape") {
                setAtQuery(null);
                return;
              }
            }
            if (e.key === "Enter" && !e.shiftKey && message.trim()) {
              e.preventDefault();
              handleSend();
            }
          }}
          placeholder={isRunning ? "Send message to agent... (type @ to mention files)" : "Describe next task... (type @ to mention files)"}
          rows={3}
          className="omnibar-textarea w-full bg-[var(--color-surface-1)] border border-[var(--color-border-default)] text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] py-2.5 px-4 focus:outline-none focus:border-[var(--color-accent)] resize-none font-mono"
        />

        {/* File autocomplete dropdown */}
        {showFileSuggestions && fileSuggestions.length > 0 && (
          <div className="absolute bottom-full left-3 right-3 mb-1 border border-[var(--color-border-default)] bg-[var(--color-surface-2)] shadow-lg z-50 max-h-48 overflow-y-auto py-1">
            <div className="px-3 py-1 text-[10px] text-[var(--color-text-muted)] font-mono font-medium uppercase tracking-wider border-b border-[var(--color-border-subtle)] mb-1">
              Files in project
            </div>
            {fileSuggestions.map((file, i) => (
              <button
                key={file}
                onClick={() => insertSuggestion(file)}
                className={`w-full text-left px-3 py-1.5 text-[12px] font-mono flex items-center gap-2 transition-colors ${i === selectedSuggestion ? "bg-[var(--color-border-subtle)] text-[var(--color-text-primary)]" : "text-[var(--color-text-secondary)] hover:bg-[var(--color-border-subtle)]"}`}
              >
                <span className="text-[var(--color-text-muted)] shrink-0">{"\u25A0"}</span>
                <span className="truncate">{file}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Actions row */}
      <div className="flex items-center justify-between px-3 pb-2.5">
        <span className="text-[10px] text-[var(--color-text-muted)] font-mono">
          <kbd className="font-mono bg-[var(--color-surface-2)] border border-[var(--color-border-default)] px-1 py-0.5 text-[9px]">Enter</kbd> {isRunning ? "send" : "launch"}
        </span>

        <div className="flex items-center gap-2">
          {isRunning ? (
            <>
              <button
                onClick={handleSend}
                disabled={!message.trim()}
                className="flex items-center gap-1.5 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] hover:shadow-[0_0_12px_var(--color-accent-glow)] px-3.5 py-1.5 text-xs font-bold text-[var(--color-surface-base)] transition-all disabled:opacity-30 shrink-0"
              >
                {"\u2192"} Steer
              </button>
              <button
                onClick={onStop}
                className="flex items-center gap-1.5 border border-[var(--color-error)] px-3.5 py-1.5 text-xs font-bold text-[var(--color-error)] hover:bg-[var(--color-error)] hover:text-[var(--color-surface-base)] transition-colors shrink-0"
              >
                Stop
                <kbd className="ml-0.5 text-[9px] opacity-60">^Q</kbd>
              </button>
            </>
          ) : (
            <button
              onClick={handleSend}
              disabled={!message.trim()}
              className="flex items-center gap-1.5 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] hover:shadow-[0_0_12px_var(--color-accent-glow)] px-4 py-1.5 text-xs font-bold text-[var(--color-surface-base)] transition-all disabled:opacity-30 shrink-0"
            >
              {"\u2192"} {tasksDone > 0 && tasksDone < tasksTotal ? "Continue" : "Start"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
