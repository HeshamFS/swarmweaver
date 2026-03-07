"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";

// --- Types ---

interface ChainSession {
  session_id: string;
  chain_id: string;
  sequence_number: number;
  checkpoint_summary: string;
  start_time: string;
  end_time: string | null;
  phase: string | null;
  tasks_completed: number;
  tasks_total: number;
  cost: number;
}

interface CompletionSummaryProps {
  status: "completed" | "error";
  mode: string;
  tasksDone: number;
  tasksTotal: number;
  tasksFailed: number;
  filesChanged?: number;
  insertions?: number;
  deletions?: number;
  tokensUsed?: number;
  estimatedCost?: number;
  duration?: string;
  projectDir?: string;
  worktreeInfo?: {
    run_id: string;
    branch: string;
    files_changed: number;
  } | null;
  onMerge?: () => void;
  onDiscard?: () => void;
  onInspect?: () => void;
  onRunAgain?: () => void;
  onNewProject?: () => void;
  onViewReplay?: () => void;
  qualityGateStats?: {
    totalWorkers: number;
    passedFirstAttempt: number;
    reworkCount: number;
  };
  githubSync?: {
    issues_updated: number;
    tasks_synced: number;
    auto_pr_url?: string;
  } | null;
}

// --- Constants ---

const MODE_COLORS: Record<string, string> = {
  greenfield: "text-mode-greenfield",
  feature: "text-mode-feature",
  refactor: "text-mode-refactor",
  fix: "text-mode-fix",
  evolve: "text-mode-evolve",
  security: "text-[#06b6d4]",
};

const MODE_BG_COLORS: Record<string, string> = {
  greenfield: "bg-mode-greenfield",
  feature: "bg-mode-feature",
  refactor: "bg-mode-refactor",
  fix: "bg-mode-fix",
  evolve: "bg-mode-evolve",
  security: "bg-[#06b6d4]",
};

// --- Helpers ---

function formatTokens(tokens: number): string {
  if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(1)}M`;
  if (tokens >= 1_000) return `${(tokens / 1_000).toFixed(0)}K`;
  return String(tokens);
}

// --- Sub-components ---

function ProgressRing({
  done,
  total,
  size = 48,
  strokeWidth = 4,
}: {
  done: number;
  total: number;
  size?: number;
  strokeWidth?: number;
}) {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const pct = total > 0 ? done / total : 0;
  const offset = circumference * (1 - pct);

  return (
    <svg width={size} height={size} className="flex-shrink-0">
      {/* Background ring */}
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke="var(--color-border-subtle)"
        strokeWidth={strokeWidth}
      />
      {/* Progress ring */}
      <motion.circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke={pct >= 1 ? "var(--color-success)" : "var(--color-accent)"}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={circumference}
        animate={{ strokeDashoffset: offset }}
        transition={{ duration: 1.2, ease: "easeOut", delay: 0.3 }}
        style={{
          transform: "rotate(-90deg)",
          transformOrigin: "center",
        }}
      />
      {/* Center text */}
      <text
        x={size / 2}
        y={size / 2}
        textAnchor="middle"
        dominantBaseline="central"
        className="text-[10px] font-mono font-bold"
        fill="var(--color-text-primary)"
      >
        {Math.round(pct * 100)}%
      </text>
    </svg>
  );
}

function StatCard({
  label,
  value,
  subValue,
  color,
  delay,
}: {
  label: string;
  value: string;
  subValue?: string;
  color?: string;
  delay: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay }}
      className="rounded-lg border border-border-subtle bg-surface-raised p-3"
    >
      <span className="text-[10px] text-text-muted uppercase tracking-wider font-medium block mb-1">
        {label}
      </span>
      <span
        className={`text-lg font-bold font-mono ${color || "text-text-primary"}`}
      >
        {value}
      </span>
      {subValue && (
        <span className="text-[10px] text-text-muted font-mono block mt-0.5">
          {subValue}
        </span>
      )}
    </motion.div>
  );
}

// --- Main Component ---

export function CompletionSummary({
  status,
  mode,
  tasksDone,
  tasksTotal,
  tasksFailed,
  filesChanged,
  insertions,
  deletions,
  tokensUsed,
  estimatedCost,
  duration,
  projectDir,
  worktreeInfo,
  onMerge,
  onDiscard,
  onInspect,
  onRunAgain,
  onNewProject,
  onViewReplay,
  qualityGateStats,
  githubSync,
}: CompletionSummaryProps) {
  const [discardConfirm, setDiscardConfirm] = useState(false);
  const [chainSessions, setChainSessions] = useState<ChainSession[]>([]);
  const isSuccess = status === "completed";
  const modeColor = MODE_COLORS[mode] || MODE_COLORS.greenfield;
  const modeBg = MODE_BG_COLORS[mode] || MODE_BG_COLORS.greenfield;

  // Fetch chain data
  useEffect(() => {
    if (!projectDir) return;
    const enc = encodeURIComponent(projectDir);
    fetch(`/api/session/chain?path=${enc}`)
      .then((r) => (r.ok ? r.json() : []))
      .then((data) => {
        if (Array.isArray(data)) setChainSessions(data);
      })
      .catch(() => {});
  }, [projectDir]);

  // Build file stats string
  const fileStatsStr = (() => {
    const parts: string[] = [];
    if (insertions != null) parts.push(`+${insertions}`);
    if (deletions != null) parts.push(`-${deletions}`);
    return parts.join(" / ");
  })();

  // Chain aggregate stats
  const chainTotalCost = chainSessions.reduce((sum, s) => sum + (s.cost || 0), 0);
  const chainTotalTasks = chainSessions.length > 0 ? chainSessions[chainSessions.length - 1].tasks_total : 0;
  const chainTasksDone = chainSessions.length > 0 ? chainSessions[chainSessions.length - 1].tasks_completed : 0;
  const chainFirstStart = chainSessions[0]?.start_time;
  const chainLastEnd = chainSessions[chainSessions.length - 1]?.end_time;
  const chainDuration = (() => {
    if (!chainFirstStart || !chainLastEnd) return null;
    const ms = new Date(chainLastEnd).getTime() - new Date(chainFirstStart).getTime();
    if (ms < 0) return null;
    const sec = Math.floor(ms / 1000);
    if (sec < 60) return `${sec}s`;
    const min = Math.floor(sec / 60);
    if (min < 60) return `${min}m`;
    const hr = Math.floor(min / 60);
    return `${hr}h ${min % 60}m`;
  })();

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
      className="w-full max-w-2xl mx-auto"
    >
      <div className="rounded-2xl border border-border-subtle bg-surface-raised shadow-2xl overflow-hidden">
        {/* ── Chain Summary (only when chain > 1 session) ── */}
        {chainSessions.length > 1 && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="px-6 pt-5 pb-3"
          >
            <div className="rounded-lg border border-accent/20 bg-accent/5 p-3">
              <div className="flex items-center gap-2 mb-2">
                <svg className="w-3.5 h-3.5 text-accent" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M4 4v8M8 2v12M12 6v4" strokeLinecap="round" />
                </svg>
                <span className="text-xs font-medium text-accent">
                  Session Chain: {chainSessions.length} sessions
                </span>
              </div>
              <div className="grid grid-cols-3 gap-3 text-center">
                <div>
                  <span className="text-[10px] text-text-muted uppercase tracking-wider block">Total Cost</span>
                  <span className="text-sm font-bold font-mono text-accent">${chainTotalCost.toFixed(2)}</span>
                </div>
                <div>
                  <span className="text-[10px] text-text-muted uppercase tracking-wider block">Total Duration</span>
                  <span className="text-sm font-bold font-mono text-text-primary">{chainDuration || "--"}</span>
                </div>
                <div>
                  <span className="text-[10px] text-text-muted uppercase tracking-wider block">Overall Progress</span>
                  <span className="text-sm font-bold font-mono text-text-primary">{chainTasksDone}/{chainTotalTasks}</span>
                </div>
              </div>
            </div>
          </motion.div>
        )}

        {/* ── Section 1: Success/Error Header ── */}
        <div className="px-8 pt-8 pb-6 text-center">
          {/* Animated icon */}
          <motion.div
            initial={{ scale: 0, rotate: -180 }}
            animate={{ scale: 1, rotate: 0 }}
            transition={{
              type: "spring",
              stiffness: 200,
              damping: 15,
              delay: 0.1,
            }}
            className="inline-flex items-center justify-center mb-4"
          >
            <div
              className={`w-16 h-16 rounded-full flex items-center justify-center ${
                isSuccess ? "bg-success/15" : "bg-error/15"
              }`}
            >
              {/* Progress ring around the icon */}
              <div className="relative">
                <ProgressRing
                  done={tasksDone}
                  total={tasksTotal}
                  size={56}
                  strokeWidth={3}
                />
                {/* Icon overlay centered in ring */}
                <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                  {/* The ring itself shows the percentage, icon is the ring */}
                </div>
              </div>
            </div>
          </motion.div>

          <motion.h2
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="text-xl font-bold text-text-primary"
          >
            {isSuccess ? "Session Complete" : "Session Failed"}
          </motion.h2>

          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.3 }}
            className="flex items-center justify-center gap-2 mt-2"
          >
            <span
              className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full text-white ${modeBg}`}
            >
              {mode}
            </span>
            {duration && (
              <span className="text-xs text-text-muted font-mono">
                {duration}
              </span>
            )}
          </motion.div>
        </div>

        {/* ── Section 2: Stats Grid (2x3) ── */}
        <div className="px-6 pb-6">
          <div className="grid grid-cols-3 gap-3">
            {/* Tasks */}
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.35 }}
              className="rounded-lg border border-border-subtle bg-surface p-3"
            >
              <span className="text-[10px] text-text-muted uppercase tracking-wider font-medium block mb-2">
                Tasks
              </span>
              <div className="flex items-center gap-2">
                <ProgressRing
                  done={tasksDone}
                  total={tasksTotal}
                  size={36}
                  strokeWidth={3}
                />
                <div>
                  <span className="text-sm font-bold text-text-primary font-mono block">
                    {tasksDone}/{tasksTotal}
                  </span>
                  <span className="text-[10px] text-text-muted">completed</span>
                </div>
              </div>
            </motion.div>

            {/* Files */}
            <StatCard
              label="Files"
              value={
                filesChanged != null ? `${filesChanged} files` : "--"
              }
              subValue={fileStatsStr || undefined}
              color={filesChanged ? "text-text-primary" : "text-text-muted"}
              delay={0.4}
            />

            {/* Duration */}
            <StatCard
              label="Duration"
              value={duration || "--"}
              delay={0.45}
            />

            {/* Cost */}
            <StatCard
              label="Cost"
              value={
                estimatedCost != null
                  ? `$${estimatedCost.toFixed(2)}`
                  : "--"
              }
              color={
                estimatedCost != null
                  ? "text-accent"
                  : "text-text-muted"
              }
              delay={0.5}
            />

            {/* Tokens */}
            <StatCard
              label="Tokens"
              value={
                tokensUsed != null
                  ? `${formatTokens(tokensUsed)} tokens`
                  : "--"
              }
              delay={0.55}
            />

            {/* Errors */}
            <StatCard
              label="Errors"
              value={`${tasksFailed} error${tasksFailed !== 1 ? "s" : ""}`}
              color={tasksFailed > 0 ? "text-error" : "text-success"}
              delay={0.6}
            />
          </div>
        </div>

        {/* ── Quality Gate Stats ── */}
        {qualityGateStats && qualityGateStats.totalWorkers > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.65 }}
            className="px-6 pb-4"
          >
            <div className="rounded-lg border border-border-subtle bg-surface p-3">
              <span className="text-[10px] text-text-muted uppercase tracking-wider font-medium block mb-2">
                Quality Gates
              </span>
              <div className="flex items-center gap-3">
                <span className={`text-sm font-bold font-mono ${
                  qualityGateStats.passedFirstAttempt === qualityGateStats.totalWorkers
                    ? "text-success"
                    : "text-warning"
                }`}>
                  {qualityGateStats.passedFirstAttempt}/{qualityGateStats.totalWorkers}
                </span>
                <span className="text-xs text-text-secondary">passed on first attempt</span>
              </div>
              {qualityGateStats.reworkCount > 0 && (
                <div className="mt-1 text-xs text-orange-400 font-mono">
                  {qualityGateStats.reworkCount} worker{qualityGateStats.reworkCount !== 1 ? "s" : ""} required rework
                </div>
              )}
            </div>
          </motion.div>
        )}

        {/* ── Section 3: Worktree Controls ── */}
        {worktreeInfo && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.65 }}
            className="px-6 pb-6"
          >
            <div className="rounded-lg border border-border-subtle bg-surface p-4">
              <div className="flex items-center gap-2 mb-3">
                <span className="text-xs text-text-muted font-medium uppercase tracking-wider">
                  Worktree
                </span>
                <span className="text-[10px] text-text-muted font-mono bg-surface-raised px-2 py-0.5 rounded border border-border-subtle">
                  {worktreeInfo.branch}
                </span>
              </div>
              <div className="flex items-center gap-2 mb-3 text-xs text-text-secondary font-mono">
                <span>{worktreeInfo.files_changed} files changed</span>
              </div>
              <div className="flex items-center gap-2">
                {onMerge && (
                  <button
                    onClick={onMerge}
                    className="flex-1 rounded-lg bg-success/80 px-4 py-2 text-sm font-medium text-white hover:bg-success transition-colors"
                  >
                    Merge Changes
                  </button>
                )}
                {onDiscard && (
                  <>
                    {discardConfirm ? (
                      <div className="flex-1 flex items-center gap-1">
                        <button
                          onClick={() => {
                            onDiscard();
                            setDiscardConfirm(false);
                          }}
                          className="flex-1 rounded-lg bg-error/80 px-3 py-2 text-xs font-medium text-white hover:bg-error transition-colors"
                        >
                          Confirm Discard
                        </button>
                        <button
                          onClick={() => setDiscardConfirm(false)}
                          className="rounded-lg border border-border-subtle px-3 py-2 text-xs text-text-muted hover:text-text-secondary transition-colors"
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={() => setDiscardConfirm(true)}
                        className="flex-1 rounded-lg border border-error/40 bg-error/10 px-4 py-2 text-sm font-medium text-error hover:bg-error/20 transition-colors"
                      >
                        Discard
                      </button>
                    )}
                  </>
                )}
                {onInspect && (
                  <button
                    onClick={onInspect}
                    className="rounded-lg border border-border-subtle px-4 py-2 text-sm font-medium text-text-secondary hover:text-text-primary hover:border-border-default transition-colors"
                  >
                    Inspect
                  </button>
                )}
              </div>
            </div>
          </motion.div>
        )}

        {/* ── GitHub Sync Summary ── */}
        {githubSync && (githubSync.issues_updated > 0 || githubSync.tasks_synced > 0 || githubSync.auto_pr_url) && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.68 }}
            className="px-6 pb-4"
          >
            <div className="rounded-lg border border-border-subtle bg-surface p-3">
              <span className="text-[10px] text-text-muted uppercase tracking-wider font-medium block mb-2">
                GitHub
              </span>
              <div className="flex items-center gap-4 text-xs text-text-secondary font-mono">
                {githubSync.issues_updated > 0 && (
                  <span>Issues updated: <span className="text-accent font-bold">{githubSync.issues_updated}</span></span>
                )}
                {githubSync.tasks_synced > 0 && (
                  <span>Tasks synced: <span className="text-accent font-bold">{githubSync.tasks_synced}</span></span>
                )}
                {githubSync.auto_pr_url && (
                  <a
                    href={githubSync.auto_pr_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-accent hover:underline"
                  >
                    View PR
                  </a>
                )}
              </div>
            </div>
          </motion.div>
        )}

        {/* ── Section 4: Next Actions ── */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.7 }}
          className="px-6 pb-6"
        >
          <div className="flex items-center gap-2 justify-center">
            {onRunAgain && (
              <button
                onClick={onRunAgain}
                className={`rounded-lg px-5 py-2 text-sm font-medium text-white ${modeBg} hover:opacity-90 transition-opacity`}
              >
                Run Again
              </button>
            )}
            {onNewProject && (
              <button
                onClick={onNewProject}
                className="rounded-lg border border-border-subtle px-5 py-2 text-sm font-medium text-text-secondary hover:text-text-primary hover:border-border-default transition-colors"
              >
                New Project
              </button>
            )}
            {onViewReplay && (
              <button
                onClick={onViewReplay}
                className="rounded-lg border border-border-subtle px-5 py-2 text-sm font-medium text-text-secondary hover:text-text-primary hover:border-border-default transition-colors"
              >
                View Replay
              </button>
            )}
          </div>
        </motion.div>
      </div>
    </motion.div>
  );
}
