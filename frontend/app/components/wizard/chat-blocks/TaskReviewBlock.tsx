"use client";

import { useState, useMemo } from "react";
import type { TaskData } from "../../../hooks/useSwarmWeaver";

interface TaskReviewBlockProps {
  isLoading: boolean;
  tasks: TaskData | null;
  onApprove: () => void;
  onBack: () => void;
  approved: boolean;
  onRegenerate?: (feedback: string) => void;
}

export default function TaskReviewBlock({ isLoading, tasks, onApprove, onBack, approved, onRegenerate }: TaskReviewBlockProps) {
  const [skipped, setSkipped] = useState<Set<number>>(new Set());
  const [expanded, setExpanded] = useState(true);
  const [showRegenInput, setShowRegenInput] = useState(false);
  const [regenFeedback, setRegenFeedback] = useState("");

  const hasTasks = tasks && tasks.tasks.length > 0;

  const stats = useMemo(() => {
    if (!tasks) return null;
    const total = tasks.tasks.length;
    const included = total - skipped.size;
    const categories = new Set(tasks.tasks.map((t) => t.category).filter(Boolean));
    const minSessions = Math.max(1, Math.ceil(included / 7));
    const maxSessions = Math.max(1, Math.ceil(included / 5));
    const est = minSessions === maxSessions ? `${minSessions}` : `${minSessions}-${maxSessions}`;
    return { total, included, categories: categories.size, est };
  }, [tasks, skipped]);

  const toggleSkip = (idx: number) => {
    setSkipped((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  const handleRegenerate = () => {
    if (!regenFeedback.trim() || !onRegenerate) return;
    setShowRegenInput(false);
    onRegenerate(regenFeedback.trim());
    setRegenFeedback("");
  };

  /** Action bar Regenerate click: submit if feedback exists, toggle input otherwise */
  const handleActionBarRegenerate = () => {
    if (showRegenInput && regenFeedback.trim()) {
      handleRegenerate();
    } else {
      setShowRegenInput(!showRegenInput);
    }
  };

  if (approved) {
    return (
      <div className="border border-[#222] bg-[#121212] mb-3 font-mono">
        <div className="flex items-center gap-3 px-4 py-2">
          <span className="text-[#555]">{"\u2713"}</span>
          <span className="text-[#555] text-xs font-bold uppercase tracking-wider">Tasks Approved</span>
          {stats && <span className="text-[#555] text-xs ml-auto">{stats.included} tasks</span>}
        </div>
      </div>
    );
  }

  if (isLoading && !hasTasks) {
    return null;
  }

  if (!hasTasks) {
    return (
      <div className="border border-[#333] bg-[#121212] mb-3 font-mono p-4">
        <span className="text-[#555] text-xs">No tasks generated yet.</span>
      </div>
    );
  }

  const groupedByCategory: Record<string, { task: typeof tasks.tasks[0]; idx: number }[]> = {};
  tasks.tasks.forEach((t, idx) => {
    const cat = t.category || "Uncategorized";
    if (!groupedByCategory[cat]) groupedByCategory[cat] = [];
    groupedByCategory[cat].push({ task: t, idx });
  });

  return (
    <div className="border border-[#333] bg-[#121212] mb-3 font-mono">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-[#222] bg-[#0C0C0C]">
        <span className="text-[var(--color-accent)]">{"\u25A0"}</span>
        <span className="text-[#E0E0E0] text-xs font-bold uppercase tracking-wider">Task List</span>
        {stats && (
          <div className="flex items-center gap-3 ml-auto text-[10px]">
            <span className="text-[#888]">{stats.included}/{stats.total} tasks</span>
            <span className="text-[#555]">|</span>
            <span className="text-[#555]">{stats.categories} categories</span>
            <span className="text-[#555]">|</span>
            <span className="text-[#555]">~{stats.est} sessions</span>
          </div>
        )}
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-[#555] hover:text-[#888] text-[10px] ml-2 transition-colors"
        >
          {expanded ? "\u25BC" : "\u25B6"}
        </button>
      </div>

      {/* Task list */}
      {expanded && (
        <div className="max-h-[400px] overflow-y-auto tui-scrollbar">
          {Object.entries(groupedByCategory).map(([category, items]) => (
            <div key={category}>
              <div className="px-4 py-1.5 border-b border-[#1A1A1A] bg-[#0C0C0C]">
                <span className="text-[#555] text-[10px] uppercase tracking-widest">{category}</span>
              </div>
              {items.map(({ task, idx }) => {
                const isSkipped = skipped.has(idx);
                return (
                  <div
                    key={idx}
                    className={`flex items-start gap-3 px-4 py-2 border-b border-[#1A1A1A] hover:bg-[#1A1A1A] transition-colors ${isSkipped ? "opacity-40" : ""}`}
                  >
                    <button
                      onClick={() => toggleSkip(idx)}
                      className={`text-xs font-bold shrink-0 mt-0.5 transition-colors ${
                        isSkipped ? "text-[#555]" : "text-[var(--color-accent)]"
                      }`}
                    >
                      {isSkipped ? "[ ]" : "[x]"}
                    </button>
                    <div className="min-w-0 flex-1">
                      <div className={`text-xs ${isSkipped ? "text-[#555] line-through" : "text-[#E0E0E0]"}`}>
                        {task.title}
                      </div>
                      {task.description && !isSkipped && (
                        <div className="text-[10px] text-[#555] mt-0.5 truncate">{task.description}</div>
                      )}
                    </div>
                    {task.priority !== undefined && (
                      <span className="text-[10px] text-[#555] shrink-0">P{task.priority}</span>
                    )}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      )}

      {/* Regenerate feedback input */}
      {showRegenInput && (
        <div className="px-4 py-3 border-t border-[#222] bg-[#0A0A0A]">
          <div className="flex items-center gap-2 border border-[#333] bg-[#121212] rounded px-3 py-2">
            <span className="text-[var(--color-accent)] text-xs shrink-0">&gt;</span>
            <input
              type="text"
              value={regenFeedback}
              onChange={(e) => setRegenFeedback(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") handleRegenerate(); if (e.key === "Escape") setShowRegenInput(false); }}
              placeholder="Describe what should change in the task list..."
              className="flex-1 bg-transparent text-[#E0E0E0] text-xs outline-none placeholder-[#555] font-mono"
              autoFocus
            />
            <button
              onClick={handleRegenerate}
              disabled={!regenFeedback.trim()}
              className="text-[10px] text-[var(--color-accent)] hover:text-[var(--color-accent-hover)] disabled:text-[#333] uppercase tracking-wider transition-colors font-bold shrink-0"
            >
              Submit
            </button>
          </div>
          <div className="text-[10px] text-[#444] mt-1 px-1">Press Enter to submit, Escape to cancel</div>
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center justify-between px-4 py-3 border-t border-[#222]">
        <button
          onClick={onBack}
          className="text-[10px] text-[#555] hover:text-[#888] uppercase tracking-wider transition-colors font-mono"
        >
          {"\u2190"} Back
        </button>
        <div className="flex items-center gap-3">
          {onRegenerate && (
            <button
              onClick={handleActionBarRegenerate}
              className={`text-[10px] uppercase tracking-wider transition-colors font-mono border px-3 py-1 ${
                showRegenInput && regenFeedback.trim()
                  ? "border-[var(--color-accent)] text-[var(--color-accent)] hover:bg-[var(--color-accent)] hover:text-[#0C0C0C]"
                  : "border-[#333] text-[#888] hover:text-[#E0E0E0] hover:border-[#555]"
              }`}
            >
              {showRegenInput && regenFeedback.trim() ? "Regenerate \u21BB" : "Regenerate"}
            </button>
          )}
          <button
            onClick={() => onApprove()}
            className="bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-[#0C0C0C] px-6 py-1.5 font-bold text-xs uppercase tracking-wider transition-colors font-mono"
          >
            Approve & Build {"\u2192"}
          </button>
        </div>
      </div>
    </div>
  );
}
