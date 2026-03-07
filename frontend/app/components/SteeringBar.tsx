"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import type { AgentStatus, Mode } from "../hooks/useSwarmWeaver";
import { MODE_ICONS } from "../utils/modeIcons";

export interface SwarmWorker {
  id: number;
  name: string;
}

interface SteeringBarProps {
  status: AgentStatus;
  onSend: (message: string, steeringType?: string) => void;
  onStop: () => void;
  onContinue?: () => void;
  selectedModel?: string;
  onModelChange?: (model: string) => void;
  mode?: Mode | null;
  onModeChange?: (mode: Mode) => void;
  className?: string;
  /** Active swarm workers for the agent switcher (@main, @worker-1, etc.) */
  swarmWorkers?: SwarmWorker[];
  /** Currently selected worker: null = main/orchestrator, number = worker id */
  selectedWorkerId?: number | null;
  onSelectWorker?: (workerId: number | null) => void;
}

type SteeringType = "instruction" | "suggestion" | "correction";

const STEERING_TYPES: { type: SteeringType; label: string; icon: React.ReactNode }[] = [
  {
    type: "instruction",
    label: "Instruction",
    icon: (
      <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M15.042 21.672L13.684 16.6m0 0l-2.51 2.225.569-9.47 5.227 7.917-3.286-.672z" />
      </svg>
    ),
  },
  {
    type: "suggestion",
    label: "Suggestion",
    icon: (
      <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M9.663 17h4.673M12 3v1m6.364 1.636-.707.707M21 12h-1M4 12H3m3.343-5.657-.707-.707m2.828 9.9a5 5 0 1 1 7.072 0l-.548.547A3.374 3.374 0 0 0 14 18.469V19a2 2 0 1 1-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
      </svg>
    ),
  },
  {
    type: "correction",
    label: "Correction",
    icon: (
      <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
        <path d="M12 9v4" /><path d="M12 17h.01" />
      </svg>
    ),
  },
];

const FALLBACK_MODELS = [
  { id: "claude-sonnet-4-6", label: "Sonnet 4.6" },
  { id: "claude-opus-4-6", label: "Opus 4.6" },
  { id: "claude-sonnet-4-5-20250929", label: "Sonnet 4.5" },
  { id: "claude-haiku-4-5-20251001", label: "Haiku 4.5" },
];

const MODE_LABELS: Record<string, string> = {
  greenfield: "Greenfield",
  feature: "Feature",
  refactor: "Refactor",
  fix: "Fix",
  evolve: "Evolve",
  security: "Security",
};

function getModelLabel(modelId: string | undefined, models: { id: string; label: string }[]): string | null {
  if (!modelId) return null;
  const model = models.find((m) => m.id === modelId);
  if (model) return model.label;
  if (modelId.includes("opus")) return "Opus";
  if (modelId.includes("sonnet")) return "Sonnet";
  if (modelId.includes("haiku")) return "Haiku";
  return modelId.split("-").pop() || modelId;
}

const MODES: Mode[] = ["greenfield", "feature", "refactor", "fix", "evolve", "security"];

export function SteeringBar({
  status,
  onSend,
  onStop,
  onContinue,
  selectedModel,
  onModelChange,
  mode,
  onModeChange,
  className = "",
  swarmWorkers,
  selectedWorkerId,
  onSelectWorker,
}: SteeringBarProps) {
  const isRunning = status === "running" || status === "starting";
  const [message, setMessage] = useState("");
  const [steeringType, setSteeringType] = useState<SteeringType>("instruction");
  const [focused, setFocused] = useState(false);
  const [showChips, setShowChips] = useState(false);
  const [models, setModels] = useState<{ id: string; label: string }[]>(FALLBACK_MODELS);
  const [showModeDropdown, setShowModeDropdown] = useState(false);
  const [showModelDropdown, setShowModelDropdown] = useState(false);
  const modeRef = useRef<HTMLDivElement>(null);
  const modelRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    fetch("/api/runtimes")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        const rt = d?.runtimes?.find((x: { available?: boolean }) => x.available);
        const list = rt?.models ?? [];
        if (list.length > 0) {
          setModels(list.map((m: { id: string; name: string }) => ({ id: m.id, label: m.name || m.id })));
        }
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    const h = (e: MouseEvent) => {
      if (modeRef.current && !modeRef.current.contains(e.target as Node)) setShowModeDropdown(false);
      if (modelRef.current && !modelRef.current.contains(e.target as Node)) setShowModelDropdown(false);
    };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  const modelLabel = getModelLabel(selectedModel, models);

  // Auto-resize textarea (1-3 lines)
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const lineHeight = 24;
    const maxHeight = lineHeight * 3 + 24;
    el.style.height = `${Math.min(el.scrollHeight, maxHeight)}px`;
  }, [message]);

  // Show chips when focused and idle
  useEffect(() => {
    if (focused && !isRunning) {
      setShowChips(true);
    } else if (!focused) {
      // Delay hide so clicks on chips register
      const t = setTimeout(() => setShowChips(false), 200);
      return () => clearTimeout(t);
    }
  }, [focused, isRunning]);

  const handleSend = useCallback(() => {
    const msg = message.trim();
    if (!msg) return;
    onSend(msg, steeringType);
    setMessage("");
    textareaRef.current?.focus();
  }, [message, steeringType, onSend]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && message.trim()) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend, message]
  );

  return (
    <div className={`relative ${className}`}>
      {/* Context badges — mode and model dropdowns */}
      <div className="flex justify-between items-end mb-3 px-1">
        <div className="flex items-center gap-3">
          {/* Mode dropdown */}
          {mode && (
            <div className="relative" ref={modeRef}>
              <button
                onClick={() => onModeChange && setShowModeDropdown((v) => !v)}
                className={`border border-[var(--color-border-default)] px-3 py-1.5 text-xs font-mono uppercase tracking-wider bg-[var(--color-surface-1)] text-[var(--color-text-primary)] flex items-center gap-2 ${
                  onModeChange ? "cursor-pointer hover:border-[var(--color-text-muted)]" : "cursor-default"
                }`}
              >
                {MODE_ICONS[mode] && React.createElement(MODE_ICONS[mode], {
                  size: 14,
                  className: "shrink-0",
                  style: { color: "var(--color-accent)" },
                })}
                {MODE_LABELS[mode] || mode}
                {onModeChange && <span className="text-[var(--color-text-muted)]">{"\u25BC"}</span>}
              </button>
              {showModeDropdown && onModeChange && (
                <div className="absolute bottom-full left-0 mb-1 w-40 border border-[var(--color-border-default)] bg-[var(--color-surface-2)] shadow-lg z-50 py-1">
                  {MODES.map((m) => (
                    <button
                      key={m}
                      onClick={() => { onModeChange(m); setShowModeDropdown(false); }}
                      className={`w-full text-left px-3 py-2 text-sm font-mono flex items-center gap-2 hover:bg-[var(--color-border-subtle)] transition-colors ${mode === m ? "font-bold" : ""}`}
                      style={{ color: mode === m ? "var(--color-accent)" : "var(--color-text-secondary)" }}
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
          )}
          {/* Model dropdown */}
          {modelLabel && (
            <div className="relative" ref={modelRef}>
              <button
                onClick={() => onModelChange && setShowModelDropdown((v) => !v)}
                className={`border px-3 py-1.5 text-xs font-mono uppercase tracking-wider bg-[var(--color-surface-base)] text-[var(--color-text-secondary)] border-[var(--color-border-default)] flex items-center gap-1.5 ${
                  onModelChange ? "cursor-pointer hover:text-[var(--color-text-primary)] hover:border-[var(--color-text-muted)]" : "cursor-default"
                }`}
              >
                {modelLabel}
                {onModelChange && <span className="text-[var(--color-text-muted)]">{"\u25BC"}</span>}
              </button>
              {showModelDropdown && onModelChange && (
                <div className="absolute bottom-full left-0 mb-1 w-44 border border-[var(--color-border-default)] bg-[var(--color-surface-2)] shadow-lg z-50 py-1">
                  {models.map((m) => (
                    <button
                      key={m.id}
                      onClick={() => {
                        onModelChange(m.id);
                        setShowModelDropdown(false);
                        if (isRunning) onSend(m.id, "model_change");
                      }}
                      className={`w-full text-left px-3 py-2 text-sm font-mono flex items-center gap-2 hover:bg-[var(--color-border-subtle)] transition-colors ${selectedModel === m.id ? "font-bold text-[var(--color-text-primary)]" : "text-[var(--color-text-secondary)]"}`}
                    >
                      {m.label}
                      {selectedModel === m.id && <span className="ml-auto text-xs text-[var(--color-accent)]">active</span>}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
          {/* Agent switcher — @main @worker-1 @worker-2 chips (smart swarm only) */}
          {swarmWorkers && swarmWorkers.length > 0 && onSelectWorker && (
            <div className="flex items-center gap-1 ml-1 border-l border-[var(--color-border-default)] pl-3">
              <button
                onClick={() => onSelectWorker(null)}
                className={`px-2 py-1 text-[10px] font-mono transition-colors rounded-sm ${
                  selectedWorkerId === null || selectedWorkerId === undefined
                    ? "bg-[var(--color-accent)]/20 text-[var(--color-accent)] border border-[var(--color-accent)]/40"
                    : "text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] border border-transparent"
                }`}
                title="Show orchestrator output"
              >
                @main
              </button>
              {swarmWorkers.map((w) => (
                <button
                  key={w.id}
                  onClick={() => onSelectWorker(w.id)}
                  className={`px-2 py-1 text-[10px] font-mono transition-colors rounded-sm ${
                    selectedWorkerId === w.id
                      ? "bg-blue-500/20 text-blue-400 border border-blue-500/40"
                      : "text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] border border-transparent"
                  }`}
                  title={`Show ${w.name} output`}
                >
                  @{w.name}
                </button>
              ))}
            </div>
          )}
          {/* Steering type toggle (only when running) */}
          {isRunning && (
            <div className="flex items-center gap-1.5 ml-1">
              {STEERING_TYPES.map((st) => (
                <button
                  key={st.type}
                  onClick={() => setSteeringType(st.type)}
                  className={`p-1.5 transition-colors ${
                    steeringType === st.type
                      ? "text-[var(--color-accent)]"
                      : "text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]"
                  }`}
                  title={st.label}
                >
                  {st.icon}
                </button>
              ))}
            </div>
          )}
        </div>
        <span className="text-[var(--color-text-muted)] text-xs font-mono">
          <span className="text-[var(--color-text-secondary)]">Ctrl+Enter</span> to send
        </span>
      </div>

      {/* Input box */}
      <div className="relative flex items-center w-full bg-[var(--color-surface-1)] border border-[var(--color-border-default)] focus-within:border-[var(--color-accent)] transition-colors shadow-2xl">
        <textarea
          ref={textareaRef}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          placeholder={isRunning ? "Steer the agent..." : "What should the agent do next?"}
          rows={1}
          className="w-full bg-transparent text-[var(--color-text-primary)] p-5 pr-44 outline-none placeholder-[var(--color-text-muted)] font-mono text-base resize-none"
          style={{ minHeight: "56px", maxHeight: "140px" }}
        />

        {/* Action buttons (flush right) */}
        <div className="absolute right-3 top-2.5 bottom-2.5 flex items-center gap-2">
          {isRunning ? (
            <>
              <button
                onClick={handleSend}
                disabled={!message.trim()}
                className="px-5 h-full bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] hover:shadow-[0_0_12px_var(--color-accent-glow)] text-[var(--color-surface-base)] font-bold flex items-center transition-colors disabled:opacity-30 text-sm"
              >
                {"\u2192"} Send
              </button>
              <button
                onClick={onStop}
                className="px-4 h-full border border-[var(--color-error)] text-[var(--color-error)] hover:bg-[var(--color-error)] hover:text-[var(--color-surface-base)] font-bold flex items-center transition-colors text-sm"
              >
                Stop
              </button>
            </>
          ) : (
            <button
              onClick={() => {
                if (message.trim()) {
                  handleSend();
                } else if (onContinue) {
                  onContinue();
                }
              }}
              disabled={!message.trim() && !onContinue}
              className="px-6 h-full bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] hover:shadow-[0_0_12px_var(--color-accent-glow)] text-[var(--color-surface-base)] font-bold flex items-center transition-colors disabled:opacity-30 text-sm"
            >
              {"\u2192"} {message.trim() ? "Send" : "Continue"}
            </button>
          )}
        </div>
      </div>

      {/* Model chips (shown on focus when idle) */}
      {showChips && !isRunning && (
        <div className="mt-3 flex items-center gap-2 flex-wrap px-1">
          {models.map((m) => (
            <button
              key={m.id}
              onClick={() => onModelChange?.(m.id)}
              className={`text-xs font-mono px-3 py-1.5 border transition-colors ${
                selectedModel === m.id
                  ? "border-[var(--color-accent)] text-[var(--color-accent)] bg-[var(--color-accent)]/10"
                  : "border-[var(--color-border-default)] text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] hover:border-[var(--color-border-subtle)]"
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
