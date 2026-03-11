"use client";

import { useMemo } from "react";
import type { Task } from "../hooks/useSwarmWeaver";

interface TaskChecklistProps {
  tasks: Task[] | null;
  onTaskClick?: (taskId: string) => void;
  className?: string;
  expanded: boolean;
}

export function TaskChecklist({ tasks, onTaskClick, className = "", expanded }: TaskChecklistProps) {
  const taskList = useMemo(() => {
    const raw = tasks ?? [];
    // Deduplicate by task.id — keep last occurrence (most up-to-date status)
    const seen = new Map<string, Task>();
    for (const t of raw) {
      seen.set(t.id, t);
    }
    return Array.from(seen.values());
  }, [tasks]);

  if (taskList.length === 0) return null;
  if (!expanded) return null;

  return (
    <div className={`shrink-0 ${className}`}>
      {/* Expanded list only — strip is in StatusBar Bar 2 */}
      <div className="max-h-48 overflow-y-auto tui-scrollbar bg-[#0C0C0C] border-b border-[#222]">
        {taskList.map((task, i) => {
            const isActive = task.status === "in_progress";
            const isDone = task.status === "done" || task.status === "completed" || task.status === "verified";
            const isFailed = task.status === "failed" || task.status === "failed_verification";

            const statusGlyph = isDone ? "[\u2713]" : isActive ? "[\u25B6]" : isFailed ? "[\u2717]" : "[ ]";
            const statusColor = isDone ? "var(--color-success)" : isActive ? "var(--color-accent)" : isFailed ? "var(--color-error)" : "#555";

            return (
              <button
                key={task.id}
                onClick={() => onTaskClick?.(task.id)}
                data-task-circle
                className={`w-full flex items-center gap-3 px-6 py-2 text-left hover:bg-[#1A1A1A] transition-colors ${
                  isActive ? "bg-[var(--color-accent)]/5" : ""
                }`}
              >
                <span className="text-[12px] font-mono shrink-0" style={{ color: statusColor }}>
                  {statusGlyph}
                </span>
                <span className="text-[12px] font-mono text-[#555] w-6 shrink-0">
                  {i + 1}
                </span>
                <span className={`text-[13px] truncate font-mono ${
                  isActive
                    ? "text-[#E0E0E0] font-medium"
                    : isDone
                    ? "text-[#555] line-through"
                    : "text-[#888]"
                }`}>
                  {task.title}
                </span>
                {task.verification_status === "verified" && (
                  <span className="text-[9px] text-[var(--color-success)] ml-auto shrink-0 font-mono">verified</span>
                )}
                {task.verification_status === "failed_verification" && (
                  <span className="text-[9px] text-[var(--color-error)] ml-auto shrink-0 font-mono">failed</span>
                )}
              </button>
            );
          })}
      </div>
    </div>
  );
}
