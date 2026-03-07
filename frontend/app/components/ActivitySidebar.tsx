"use client";

import { useState, useRef, useEffect, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";

// --- Types ---

interface ActivityEvent {
  type: string;
  timestamp: string;
  data: Record<string, unknown>;
}

interface ActivitySidebarProps {
  status: string;
  mode: string | null;
  events: ActivityEvent[];
  currentPhase?: string;
  approvalRequest?: { summary: string; gate_type: string } | null;
  onStop: () => void;
  onSteer: (message: string, type: string) => void;
  onResolveApproval: (decision: string, feedback?: string) => void;
}

// --- Constants ---

const MODE_COLORS: Record<string, string> = {
  greenfield: "bg-mode-greenfield",
  feature: "bg-mode-feature",
  refactor: "bg-mode-refactor",
  fix: "bg-mode-fix",
  evolve: "bg-mode-evolve",
  security: "bg-[#06b6d4]",
};

const MODE_BORDER_COLORS: Record<string, string> = {
  greenfield: "border-mode-greenfield",
  feature: "border-mode-feature",
  refactor: "border-mode-refactor",
  fix: "border-mode-fix",
  evolve: "border-mode-evolve",
  security: "border-[#06b6d4]",
};

const MODE_TEXT_COLORS: Record<string, string> = {
  greenfield: "text-mode-greenfield",
  feature: "text-mode-feature",
  refactor: "text-mode-refactor",
  fix: "text-mode-fix",
  evolve: "text-mode-evolve",
  security: "text-[#06b6d4]",
};

const CARD_TYPES = {
  tool_call: {
    icon: "\u{1F527}",
    borderColor: "border-l-accent",
    label: (data: Record<string, unknown>) => {
      const tool = String(data.tool || data.tool_name || "tool");
      const file = data.file ? String(data.file) : null;
      const input = data.input_preview || data.tool_input_preview;
      if (file) return `${tool} ${file}`;
      if (input) return `${tool} ${String(input).slice(0, 40)}`;
      return tool;
    },
  },
  tool_result: {
    icon: "\u2705",
    borderColor: "border-l-success",
    label: (data: Record<string, unknown>) => {
      const tool = String(data.tool || "result");
      return `Done: ${tool}`;
    },
  },
  file_touch: {
    icon: "\u{1F4DD}",
    borderColor: "border-l-success",
    label: (data: Record<string, unknown>) => {
      const file = String(data.file || data.path || "file");
      const name = file.split("/").pop() || file;
      return `Modified ${name}`;
    },
  },
  phase_change: {
    icon: "\u{1F3AF}",
    borderColor: "border-l-warning",
    label: (data: Record<string, unknown>) => {
      return `Phase: ${String(data.phase || data.new_phase || "unknown")}`;
    },
  },
  error: {
    icon: "\u274C",
    borderColor: "border-l-error",
    label: (data: Record<string, unknown>) => {
      const msg = String(data.message || data.reason || data.error || "Error");
      return msg.length > 60 ? msg.slice(0, 57) + "..." : msg;
    },
  },
  blocked: {
    icon: "\u{1F6AB}",
    borderColor: "border-l-error",
    label: (data: Record<string, unknown>) => {
      return String(data.message || data.reason || "Blocked");
    },
  },
  verification: {
    icon: "\u{1F50D}",
    borderColor: "border-l-success",
    label: (data: Record<string, unknown>) => {
      const task = data.task_id || data.task || "";
      return `Verified: ${String(task)}`;
    },
  },
  marathon: {
    icon: "\u{1F3C3}",
    borderColor: "border-l-warning",
    label: (data: Record<string, unknown>) => {
      return String(data.message || "Marathon event");
    },
  },
  session_stat: {
    icon: "\u{1F4CA}",
    borderColor: "border-l-accent",
    label: (data: Record<string, unknown>) => {
      return String(data.message || "Session stats");
    },
  },
  dispatch: {
    icon: "\u{1F4E4}",
    borderColor: "border-l-blue-400",
    label: (data: Record<string, unknown>) => {
      const target = data.target || data.agent || data.worker || "";
      const task = data.task_id || data.task || "";
      if (target && task) return `Dispatch ${task} to ${target}`;
      if (target) return `Dispatched to ${target}`;
      return String(data.message || "Task dispatched");
    },
  },
  merge: {
    icon: "\u{1F500}",
    borderColor: "border-l-success",
    label: (data: Record<string, unknown>) => {
      const success = data.success !== false && data.status !== "failed";
      const branch = data.branch || data.worker || "";
      if (success) return `Merged${branch ? `: ${branch}` : ""}`;
      return `Merge failed${branch ? `: ${branch}` : ""}`;
    },
  },
  escalation: {
    icon: "\u26A0\uFE0F",
    borderColor: "border-l-warning",
    label: (data: Record<string, unknown>) => {
      return String(data.message || data.reason || "Escalation raised");
    },
  },
};

const FILTERED_TYPES = new Set(["raw_output", "output", "status"]);

const MAX_VISIBLE_EVENTS = 50;

// --- Helpers ---

function formatTime(timestamp: string): string {
  try {
    const d = new Date(timestamp);
    return d.toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return "";
  }
}

function getDurationBadge(data: Record<string, unknown>): string | null {
  const ms = data.duration_ms || data.duration;
  if (ms == null) return null;
  const num = Number(ms);
  if (isNaN(num) || num <= 0) return null;
  if (num < 1000) return `${Math.round(num)}ms`;
  return `${(num / 1000).toFixed(1)}s`;
}

function getFileStats(data: Record<string, unknown>): {
  insertions: number;
  deletions: number;
} | null {
  const ins = data.insertions ?? data.lines_added;
  const del = data.deletions ?? data.lines_removed;
  if (ins == null && del == null) return null;
  return { insertions: Number(ins) || 0, deletions: Number(del) || 0 };
}

// --- Component ---

export function ActivitySidebar({
  status,
  mode,
  events,
  currentPhase,
  approvalRequest,
  onStop,
  onSteer,
  onResolveApproval,
}: ActivitySidebarProps) {
  const [steerMessage, setSteerMessage] = useState("");
  const [expandedError, setExpandedError] = useState<number | null>(null);
  const feedRef = useRef<HTMLDivElement>(null);
  const isRunning = status === "running" || status === "starting";

  // Filter events for display
  const displayEvents = useMemo(() => {
    return events
      .filter((e) => !FILTERED_TYPES.has(e.type))
      .slice(-MAX_VISIBLE_EVENTS);
  }, [events]);

  // Auto-scroll to bottom when new events arrive
  useEffect(() => {
    if (feedRef.current) {
      const el = feedRef.current;
      // Only auto-scroll if user is near the bottom
      const isNearBottom =
        el.scrollHeight - el.scrollTop - el.clientHeight < 80;
      if (isNearBottom) {
        requestAnimationFrame(() => {
          el.scrollTop = el.scrollHeight;
        });
      }
    }
  }, [displayEvents.length]);

  const handleSteerSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const msg = steerMessage.trim();
    if (!msg) return;
    onSteer(msg, "instruction");
    setSteerMessage("");
  };

  const modeKey = mode || "greenfield";
  const modeBg = MODE_COLORS[modeKey] || MODE_COLORS.greenfield;
  const modeBorder = MODE_BORDER_COLORS[modeKey] || MODE_BORDER_COLORS.greenfield;
  const modeText = MODE_TEXT_COLORS[modeKey] || MODE_TEXT_COLORS.greenfield;

  return (
    <div className="flex flex-col h-full bg-[var(--color-surface-glass)] backdrop-blur-xl border-l border-[var(--color-border-subtle)] overflow-hidden shadow-inner relative z-10">
      {/* ── Section 1: Agent Status Header ── */}
      <div className="px-3 py-2.5 border-b border-[var(--color-border-subtle)] bg-[var(--color-surface-1)]/40 backdrop-blur-md flex-shrink-0">
        <div className="flex items-center gap-2">
          {/* Mode badge */}
          <span
            className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full text-white ${modeBg}`}
          >
            {modeKey}
          </span>

          {/* Status dot */}
          <span className="flex items-center gap-1 ml-auto">
            <span
              className={`w-2 h-2 rounded-full flex-shrink-0 ${isRunning
                ? "bg-success animate-pulse-dot"
                : status === "completed"
                  ? "bg-success"
                  : status === "error"
                    ? "bg-error"
                    : "bg-text-muted"
                }`}
            />
            <span className="text-[10px] text-text-muted font-mono">
              {status}
            </span>
          </span>
        </div>

        {/* Current phase */}
        {currentPhase && (
          <div className="mt-1.5 flex items-center gap-1.5">
            <span className={`text-[10px] ${modeText} font-mono`}>
              {"\u{1F3AF}"} {currentPhase}
            </span>
          </div>
        )}

        {/* Stop is handled by the FloatingActionBar */}
      </div>

      {/* ── Section 2: Activity Feed ── */}
      <div
        ref={feedRef}
        className="flex-1 overflow-y-auto min-h-0 px-1.5 py-1.5 space-y-1"
      >
        {displayEvents.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <span className="text-[10px] text-text-muted">
              {isRunning
                ? "Waiting for events..."
                : "No activity yet."}
            </span>
          </div>
        ) : (
          <AnimatePresence initial={false}>
            {displayEvents.map((event, i) => {
              const globalIndex = events.length - displayEvents.length + i;
              const cardConfig =
                CARD_TYPES[event.type as keyof typeof CARD_TYPES] || null;

              if (!cardConfig) {
                // Fallback card for unknown event types
                return (
                  <motion.div
                    key={`evt-${globalIndex}`}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0 }}
                    transition={{ type: "spring", stiffness: 300, damping: 25 }}
                    className="rounded-lg border border-[var(--color-border-subtle)] bg-[var(--color-surface-2)]/50 backdrop-blur-sm px-3 py-2 border-l-2 border-l-[var(--color-text-muted)] shadow-sm"
                  >
                    <div className="flex items-center gap-1.5">
                      <span className="text-[10px]">{"\u25CB"}</span>
                      <span className="text-[10px] text-text-muted font-mono truncate flex-1">
                        {event.type}
                        {event.data?.message
                          ? `: ${String(event.data.message).slice(0, 40)}`
                          : ""}
                      </span>
                      <span className="text-[9px] text-text-muted whitespace-nowrap">
                        {formatTime(event.timestamp)}
                      </span>
                    </div>
                  </motion.div>
                );
              }

              const label = cardConfig.label(event.data);
              const duration = getDurationBadge(event.data);
              const fileStats =
                event.type === "file_touch"
                  ? getFileStats(event.data)
                  : null;
              const isErrorType =
                event.type === "error" || event.type === "blocked";
              const isExpanded = expandedError === globalIndex;
              const fullMessage = isErrorType
                ? String(
                  event.data.message ||
                  event.data.reason ||
                  event.data.error ||
                  ""
                )
                : "";

              return (
                <motion.div
                  key={`evt-${globalIndex}`}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{ type: "spring", stiffness: 300, damping: 25 }}
                  className={`rounded-lg border border-[var(--color-border-subtle)] bg-[var(--color-surface-2)]/50 backdrop-blur-sm px-3 py-2 border-l-2 flex-shrink-0 ${cardConfig.borderColor} shadow-sm transition-all hover:bg-[var(--color-surface-3)]/60 ${isErrorType ? "cursor-pointer" : ""
                    }`}
                  onClick={
                    isErrorType
                      ? () =>
                        setExpandedError(isExpanded ? null : globalIndex)
                      : undefined
                  }
                >
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] flex-shrink-0">
                      {cardConfig.icon}
                    </span>
                    <span className="text-[10px] text-text-primary font-mono truncate flex-1 min-w-0">
                      {label}
                    </span>
                    <div className="flex items-center gap-1 flex-shrink-0">
                      {/* File stats */}
                      {fileStats && (
                        <span className="text-[9px] font-mono">
                          <span className="text-success">
                            +{fileStats.insertions}
                          </span>
                          <span className="text-text-muted">, </span>
                          <span className="text-error">
                            -{fileStats.deletions}
                          </span>
                        </span>
                      )}
                      {/* Duration badge */}
                      {duration && (
                        <span className="text-[9px] text-text-muted font-mono bg-surface px-1 py-px rounded">
                          {duration}
                        </span>
                      )}
                      {/* Timestamp */}
                      <span className="text-[9px] text-text-muted whitespace-nowrap">
                        {formatTime(event.timestamp)}
                      </span>
                    </div>
                  </div>

                  {/* Expanded error message */}
                  {isErrorType && isExpanded && fullMessage && (
                    <div className="mt-1.5 px-1 py-1 rounded bg-error/5 border border-error/15">
                      <p className="text-[10px] text-error font-mono break-words whitespace-pre-wrap">
                        {fullMessage}
                      </p>
                    </div>
                  )}
                </motion.div>
              );
            })}
          </AnimatePresence>
        )}
      </div>

      {/* ── Section 3: Quick Approval ── */}
      <AnimatePresence>
        {approvalRequest && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ type: "spring", stiffness: 300, damping: 30 }}
            className="flex-shrink-0 border-t border-[var(--color-border-subtle)] overflow-hidden"
          >
            <div className={`px-3 py-2.5 bg-[var(--color-surface-1)]/60 backdrop-blur-md border-l-2 ${modeBorder}`}>
              <div className="flex items-center gap-1.5 mb-1.5">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-warning">
                  Approval Required
                </span>
                <span className="text-[9px] text-text-muted font-mono">
                  {approvalRequest.gate_type}
                </span>
              </div>
              <p className="text-[10px] text-text-secondary mb-2 line-clamp-2">
                {approvalRequest.summary}
              </p>
              <div className="flex items-center gap-1.5">
                <button
                  onClick={() => onResolveApproval("approved")}
                  className="flex-1 rounded border border-success/40 bg-success/15 px-2 py-1 text-[10px] font-medium text-success hover:bg-success/25 transition-colors"
                >
                  Approve
                </button>
                <button
                  onClick={() => onResolveApproval("rejected")}
                  className="flex-1 rounded border border-error/40 bg-error/15 px-2 py-1 text-[10px] font-medium text-error hover:bg-error/25 transition-colors"
                >
                  Reject
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Steering is handled by the FloatingActionBar */}
    </div>
  );
}
