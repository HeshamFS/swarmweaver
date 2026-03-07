"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import { PanelRightOpen } from "lucide-react";
import type { Mode, AgentStatus, WorktreeInfo } from "../hooks/useSwarmWeaver";
import { MODE_ICONS, MODE_COLORS } from "../utils/modeIcons";

export interface TokenUsage {
  inputTokens: number;
  cachedTokens: number;
  outputTokens: number;
}

/** When set, the status bar shows worker-specific stats instead of global session stats */
export interface WorkerContext {
  /** Display label, e.g. "W1 builder" */
  label: string;
  /** Worker capability role */
  capability?: string;
  /** Worker's estimated cost */
  cost: number;
  /** Number of completed tasks */
  tasksDone: number;
  /** Total tasks (known) */
  tasksTotal: number;
  /** Worker status */
  workerStatus?: string;
  /** Number of files in scope */
  fileCount?: number;
  /** Elapsed time since worker spawned (e.g. "02:34") */
  elapsed?: string;
  /** Per-worker token breakdown (In, Cache, Out) for full display */
  tokenUsage?: TokenUsage;
}

interface StatusBarProps {
  mode: Mode | null;
  projectName: string;
  projectPath: string;
  currentPhase: string;
  cost: number;
  tasksDone: number;
  tasksTotal: number;
  elapsed: string;
  status: AgentStatus;
  agentCount?: number;
  tokenUsage?: TokenUsage;
  onBack: () => void;
  onReplay?: () => void;
  onPlugins?: () => void;
  onGitHub?: () => void;
  onHealth?: () => void;
  onNotifications?: () => void;
  onShortcuts?: () => void;
  worktreeInfo?: WorktreeInfo | null;
  onInspectWorktree?: () => void;
  onMergeWorktree?: () => void;
  onDiscardWorktree?: () => void;
  tasksExpanded?: boolean;
  onToggleTasksExpanded?: () => void;
  /** When set, override stats display to show per-worker data */
  workerContext?: WorkerContext | null;
  /** Open the detail drawer (tasks, observe, etc.) */
  onOpenDrawer?: () => void;
}

const MODE_LABELS: Record<string, string> = {
  greenfield: "Greenfield",
  feature: "Feature",
  refactor: "Refactor",
  fix: "Fix",
  evolve: "Evolve",
  security: "Security",
};

const STATUS_DOT_COLOR: Record<string, string> = {
  running: "var(--color-accent)",
  starting: "var(--color-warning)",
  completed: "var(--color-text-muted)",
  idle: "var(--color-text-muted)",
  error: "var(--color-error)",
};

const STATUS_LABEL: Record<string, string> = {
  running: "RUNNING",
  starting: "STARTING",
  completed: "DONE",
  idle: "IDLE",
  error: "ERROR",
};

function formatTokens(n: number): string {
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(1)}B`;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

/** Abbreviate path for compact display: show last segment or .../last, max ~20 chars */
function abbreviatePath(path: string, maxLen = 20): string {
  if (!path || path.length <= maxLen) return path;
  const parts = path.replace(/\\/g, "/").split("/").filter(Boolean);
  const last = parts[parts.length - 1] || path;
  if (last.length >= maxLen) return last.slice(0, maxLen - 2) + "..";
  if (parts.length <= 1) return last;
  return "…/" + last;
}

export function StatusBar({
  mode,
  projectName,
  projectPath,
  currentPhase,
  cost,
  tasksDone,
  tasksTotal,
  elapsed,
  status,
  agentCount,
  tokenUsage,
  onBack,
  onReplay,
  onPlugins,
  onGitHub,
  onHealth,
  onNotifications,
  onShortcuts,
  worktreeInfo,
  onInspectWorktree,
  onMergeWorktree,
  onDiscardWorktree,
  tasksExpanded = false,
  onToggleTasksExpanded,
  workerContext,
  onOpenDrawer,
}: StatusBarProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [pathCopied, setPathCopied] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const isRunning = status === "running" || status === "starting";
  const modeLabel = mode ? MODE_LABELS[mode] || mode : "";
  const statusLabel = STATUS_LABEL[status] || status;
  const statusDotColor = STATUS_DOT_COLOR[status] || "var(--color-text-muted)";

  // Worker context overrides
  const effectiveTasksDone = workerContext ? workerContext.tasksDone : tasksDone;
  const effectiveTasksTotal = workerContext ? workerContext.tasksTotal : tasksTotal;
  const effectiveCost = workerContext ? workerContext.cost : cost;

  // Progress bar for bar 2
  const progressPct = effectiveTasksTotal > 0 ? effectiveTasksDone / effectiveTasksTotal : 0;
  const totalBlocks = 80;
  const filledBlocks = Math.round(progressPct * totalBlocks);
  const progressFilled = "\u2593".repeat(filledBlocks);
  const progressEmpty = "\u2591".repeat(totalBlocks - filledBlocks);

  useEffect(() => {
    if (!menuOpen) return;
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [menuOpen]);

  useEffect(() => {
    if (!menuOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenuOpen(false);
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [menuOpen]);

  const menuAction = useCallback((fn?: () => void) => {
    return () => {
      setMenuOpen(false);
      fn?.();
    };
  }, []);

  const copyPath = useCallback(async () => {
    const path = projectPath || projectName;
    if (!path) return;
    try {
      await navigator.clipboard.writeText(path);
      setPathCopied(true);
      setTimeout(() => setPathCopied(false), 1500);
    } catch {
      /* ignore */
    }
  }, [projectPath, projectName]);

  return (
    <div className="border-b border-[var(--color-border-subtle)] bg-[var(--color-surface-base)] flex flex-col w-full shrink-0 z-30 relative font-mono">
      {/* Bar 1: Left (mode+path) | Center (time+tokens+cost) | Right (status+actions) */}
      <div className="grid grid-cols-3 items-center px-5 h-10 text-sm border-b border-[var(--color-surface-2)]">
        {/* Left: back + mode/worker + path */}
        <div className="flex items-center gap-3 min-w-0">
          <button
            onClick={onBack}
            className="text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors shrink-0"
            title="Back to projects"
          >
            &lt;
          </button>

          {mode && MODE_ICONS[mode] ? (
            React.createElement(MODE_ICONS[mode], {
              size: 14,
              className: "shrink-0",
              style: { color: MODE_COLORS[mode] ?? "var(--color-accent)" },
            })
          ) : (
            <span className="text-[var(--color-accent)] shrink-0">{"\u2234"}</span>
          )}

          {workerContext ? (
            /* Worker view: show worker label badge */
            <span className="flex items-center gap-1.5 shrink-0">
              <span className="text-[var(--color-accent)] font-bold uppercase tracking-wider text-[11px]">
                {workerContext.label}
              </span>
              {workerContext.workerStatus && (
                <span className={`text-[9px] font-mono px-1 py-0.5 rounded uppercase tracking-wider ${
                  workerContext.workerStatus === "working"
                    ? "text-success bg-success/10"
                    : workerContext.workerStatus === "done"
                    ? "text-[var(--color-text-muted)] bg-[var(--color-surface-2)]"
                    : "text-warning bg-warning/10"
                }`}>
                  {workerContext.workerStatus}
                </span>
              )}
              {workerContext.fileCount != null && workerContext.fileCount > 0 && (
                <span className="text-[9px] font-mono text-[var(--color-text-muted)]" title="Files in scope">
                  {workerContext.fileCount}f
                </span>
              )}
            </span>
          ) : (
            /* Normal view: mode + compact path badge */
            <>
              <span className="text-[var(--color-text-primary)] font-bold shrink-0 uppercase tracking-wider">
                {modeLabel || "Agent"}
              </span>
              {(projectPath || projectName) && (
                <button
                  type="button"
                  onClick={copyPath}
                  className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono text-[var(--color-text-muted)] bg-[var(--color-surface-2)] border border-[var(--color-border-subtle)] shrink-0 max-w-[140px] truncate cursor-pointer hover:text-[var(--color-text-secondary)] hover:border-[var(--color-border-default)] transition-colors"
                  title={pathCopied ? "Copied!" : `Click to copy: ${projectPath || projectName}`}
                >
                  {pathCopied ? "Copied" : abbreviatePath(projectPath || projectName)}
                </button>
              )}
            </>
          )}
        </div>

        {/* Center: Time + tokens + cost  (or simplified worker view) */}
        {workerContext ? (
          /* Worker-specific center: elapsed + tokens (when available) + cost + tasks */
          <div className="flex items-center justify-center gap-4">
            {workerContext.elapsed && (
              <>
                <span className="text-[var(--color-text-secondary)]">
                  Time <span className="text-[var(--color-text-primary)] tabular-nums">{workerContext.elapsed}</span>
                </span>
                <span className="text-[var(--color-border-default)]">{"\u00B7"}</span>
              </>
            )}
            {workerContext.tokenUsage && (
              workerContext.tokenUsage.inputTokens + workerContext.tokenUsage.cachedTokens + workerContext.tokenUsage.outputTokens > 0 ? (
                <>
                  <span className="text-[var(--color-text-secondary)]">
                    In <span className="text-[var(--color-text-primary)] tabular-nums">{formatTokens(workerContext.tokenUsage.inputTokens)}</span>
                  </span>
                  <span className="text-[var(--color-text-secondary)]">
                    Cache <span className="text-[var(--color-text-primary)] tabular-nums">{formatTokens(workerContext.tokenUsage.cachedTokens)}</span>
                  </span>
                  <span className="text-[var(--color-text-secondary)]">
                    Out <span className="text-[var(--color-text-primary)] tabular-nums">{formatTokens(workerContext.tokenUsage.outputTokens)}</span>
                  </span>
                  <span className="text-[var(--color-border-default)]">{"\u00B7"}</span>
                </>
              ) : null
            )}
            <span className="text-[var(--color-text-secondary)]">
              Cost <span className="text-[var(--color-text-primary)]">${effectiveCost.toFixed(3)}</span>
            </span>
            {effectiveTasksTotal > 0 && (
              <>
                <span className="text-[var(--color-border-default)]">{"\u00B7"}</span>
                <span className="text-[var(--color-text-secondary)]">
                  Tasks{" "}
                  <span className="text-[var(--color-text-primary)] font-bold">{effectiveTasksDone}</span>
                  <span className="text-[var(--color-text-muted)]">/</span>
                  <span className="text-[var(--color-text-primary)]">{effectiveTasksTotal}</span>
                  <span className="text-[var(--color-text-muted)] ml-1.5">done</span>
                </span>
              </>
            )}
          </div>
        ) : (
          /* Normal session center: full token breakdown */
          <div className="flex items-center justify-center gap-4">
            <span className="text-[var(--color-text-secondary)]">
              Time <span className="text-[var(--color-text-primary)] tabular-nums">{elapsed || "00:00"}</span>
            </span>
            <span className="text-[var(--color-border-default)]">{"\u00B7"}</span>
            {/* Input = new non-cached tokens only */}
            <span
              className="text-[var(--color-text-secondary)]"
              title="New tokens sent this turn (not from cache) — billed at full rate"
            >
              In <span className={(tokenUsage?.inputTokens ?? 0) > 0 ? "text-[var(--color-accent)]" : "text-[var(--color-text-primary)]"}>{formatTokens(tokenUsage?.inputTokens ?? 0)}</span>
            </span>
            <span className="text-[var(--color-border-default)]">{"\u00B7"}</span>
            {/* Cached = tokens served from prompt cache (separate billing at 10% rate) */}
            <span
              className="text-[var(--color-text-secondary)]"
              title="Tokens served from prompt cache — billed at 10% of normal rate (conversation history, system prompt)"
            >
              Cache <span className={(tokenUsage?.cachedTokens ?? 0) > 0 ? "text-[var(--color-accent)]" : "text-[var(--color-text-primary)]"}>{formatTokens(tokenUsage?.cachedTokens ?? 0)}</span>
            </span>
            <span className="text-[var(--color-border-default)]">{"\u00B7"}</span>
            {/* Total = what the model actually sees this turn */}
            {((tokenUsage?.inputTokens ?? 0) > 0 || (tokenUsage?.cachedTokens ?? 0) > 0) && (
              <>
                <span
                  className="text-[var(--color-text-muted)]"
                  title="Total tokens the model processes this turn = In + Cache"
                >
                  ctx <span className="text-[var(--color-text-secondary)]">{formatTokens((tokenUsage?.inputTokens ?? 0) + (tokenUsage?.cachedTokens ?? 0))}</span>
                </span>
                <span className="text-[var(--color-border-default)]">{"\u00B7"}</span>
              </>
            )}
            <span className="text-[var(--color-text-secondary)]">
              Out <span className={(tokenUsage?.outputTokens ?? 0) > 0 ? "text-[var(--color-accent)]" : "text-[var(--color-text-primary)]"}>{formatTokens(tokenUsage?.outputTokens ?? 0)}</span>
            </span>
            <span className="text-[var(--color-border-default)]">{"\u00B7"}</span>
            <span className="text-[var(--color-text-secondary)]">
              Cost <span className={cost > 0.01 ? "text-[var(--color-accent)]" : "text-[var(--color-text-primary)]"}>${cost.toFixed(2)}</span>
            </span>
          </div>
        )}

        {/* Right: Worktree + Status + Menu */}
        <div className="flex items-center justify-end gap-4 shrink-0">
          {/* Worktree */}
          {worktreeInfo && (
            <div className="flex items-center gap-1 text-[var(--color-text-secondary)]">
              <span className="text-xs truncate max-w-[80px]" title={worktreeInfo.branch}>
                {worktreeInfo.branch}
              </span>
              {onInspectWorktree && (
                <button onClick={onInspectWorktree} className="hover:text-[var(--color-text-primary)] transition-colors" title="Inspect diff">?</button>
              )}
              {onMergeWorktree && (
                <button onClick={onMergeWorktree} className="hover:text-[var(--color-success)] transition-colors" title="Merge">{"\u2713"}</button>
              )}
              {onDiscardWorktree && (
                <button onClick={onDiscardWorktree} className="hover:text-[var(--color-error)] transition-colors" title="Discard">{"\u2717"}</button>
              )}
            </div>
          )}

          {/* Agent count */}
          {agentCount != null && agentCount > 1 && (
            <span className="text-[var(--color-text-muted)]">{agentCount} agents</span>
          )}

          {/* Status */}
          <div className="flex items-center gap-2">
            <span
              className={isRunning ? "animate-pulse" : ""}
              style={{ width: 7, height: 7, display: "inline-block", backgroundColor: statusDotColor, borderRadius: 0 }}
            />
            <span className={isRunning ? "text-[var(--color-accent)]" : "text-[var(--color-text-secondary)]"}>
              {statusLabel.toLowerCase()}
            </span>
          </div>

          {/* Drawer button — hints at opening the detail panel */}
          {onOpenDrawer && (
            <button
              onClick={onOpenDrawer}
              className="w-7 h-7 flex items-center justify-center text-[var(--color-text-muted)] hover:text-[var(--color-accent)] transition-colors shrink-0"
              title="Open details (tasks, observe, memory)"
            >
              <PanelRightOpen className="w-4 h-4" strokeWidth={2} />
            </button>
          )}

          {/* Actions */}
          <div className="flex items-center gap-3 text-[var(--color-text-muted)]">
            <div className="relative" ref={menuRef}>
              <button
                onClick={() => setMenuOpen((v) => !v)}
                className="hover:text-[var(--color-text-primary)] cursor-pointer transition-colors"
                title="More actions"
              >
                {"\u22EE"}
              </button>

              {menuOpen && (
                <div className="absolute right-0 top-full mt-1 w-52 border border-[var(--color-border-default)] bg-[var(--color-surface-2)] shadow-xl z-50 py-1">
                  {onReplay && (
                    <MenuItem label="Replay" onClick={menuAction(onReplay)} />
                  )}
                  {onPlugins && (
                    <MenuItem label="Plugins" onClick={menuAction(onPlugins)} />
                  )}
                  {onGitHub && (
                    <MenuItem label="GitHub" onClick={menuAction(onGitHub)} />
                  )}
                  {onHealth && (
                    <MenuItem label="Health" onClick={menuAction(onHealth)} />
                  )}
                  {onNotifications && (
                    <MenuItem label="Notifications" onClick={menuAction(onNotifications)} />
                  )}
                  {onShortcuts && (
                    <MenuItem label="Shortcuts" onClick={menuAction(onShortcuts)} />
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Bar 2: Status + Progress Bar + Task Count + Show all */}
      <div className="flex items-center px-5 h-8 text-sm gap-3">
        {/* Status dot + label (or worker label when in worker view) */}
        <div className="flex items-center gap-2 shrink-0">
          {workerContext ? (
            /* Worker view: show worker badge */
            <span className="text-[var(--color-accent)] font-bold text-[10px] uppercase tracking-wider">
              {workerContext.label}
            </span>
          ) : (
            <>
              <span
                className={isRunning ? "animate-pulse" : ""}
                style={{ width: 8, height: 8, display: "inline-block", backgroundColor: statusDotColor, borderRadius: 0 }}
              />
              <span className={isRunning ? "text-[var(--color-accent)] font-bold uppercase tracking-wider" : "text-[var(--color-text-primary)] font-bold uppercase tracking-wider"}>
                {statusLabel}
              </span>
            </>
          )}
        </div>

        {/* Task count */}
        {effectiveTasksTotal > 0 && (
          <span className="text-[var(--color-text-secondary)] shrink-0 tabular-nums">
            <span className="text-[var(--color-text-primary)] font-bold">{effectiveTasksDone}</span>
            <span className="text-[var(--color-text-muted)]">/</span>
            {effectiveTasksTotal}
          </span>
        )}

        {/* Big ASCII progress bar */}
        <div className="flex-1 overflow-hidden whitespace-nowrap leading-none">
          <span className="text-[var(--color-accent)] tracking-[0.12em] text-base">{progressFilled}</span>
          <span className="text-[var(--color-border-subtle)] tracking-[0.12em] text-base">{progressEmpty}</span>
        </div>

        {/* Show all / Hide */}
        {tasksTotal > 0 && onToggleTasksExpanded && (
          <button
            onClick={onToggleTasksExpanded}
            className="text-sm font-mono text-[var(--color-accent)] hover:text-[var(--color-accent-hover)] transition-colors shrink-0 whitespace-nowrap"
          >
            {tasksExpanded ? "[ Hide ]" : "[ Show all ]"}
          </button>
        )}
      </div>
    </div>
  );
}

/* ---- Helpers ---- */

function MenuItem({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="w-full flex items-center gap-3 px-4 py-2 text-xs font-mono text-[var(--color-text-secondary)] hover:bg-[var(--color-border-subtle)] hover:text-[var(--color-text-primary)] transition-colors"
    >
      {label}
    </button>
  );
}
