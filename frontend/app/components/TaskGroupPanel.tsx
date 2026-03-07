"use client";

import { useState, useEffect } from "react";

interface TaskGroupEntry {
  group_id: string;
  name: string;
  description?: string;
  tasks: {
    id: string;
    title: string;
    status: string;
  }[];
  dependencies?: string[];
  progress: number;
}

const STATUS_DOT: Record<string, string> = {
  done: "bg-success",
  completed: "bg-success",
  passed: "bg-success",
  in_progress: "bg-accent animate-pulse",
  pending: "bg-text-muted",
  blocked: "bg-warning",
  failed: "bg-error",
  error: "bg-error",
  skipped: "bg-text-muted/50",
};

export function TaskGroupPanel({ projectDir }: { projectDir: string }) {
  const [groups, setGroups] = useState<TaskGroupEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedGroup, setExpandedGroup] = useState<string | null>(null);

  useEffect(() => {
    if (!projectDir) return;
    setLoading(true);
    fetch(`/api/task-groups?path=${encodeURIComponent(projectDir)}`)
      .then((r) => (r.ok ? r.json() : { groups: [] }))
      .then((data) => setGroups(data.groups || []))
      .catch(() => setGroups([]))
      .finally(() => setLoading(false));
  }, [projectDir]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-32 text-xs text-text-muted">
        Loading task groups...
      </div>
    );
  }

  if (groups.length === 0) {
    return (
      <div className="flex items-center justify-center h-32 text-xs text-text-muted">
        No task groups defined.
      </div>
    );
  }

  return (
    <div className="overflow-y-auto h-full p-3 space-y-2">
      {groups.map((group) => {
        const isExpanded = expandedGroup === group.group_id;
        const doneTasks = group.tasks.filter(
          (t) => t.status === "done" || t.status === "completed" || t.status === "passed"
        ).length;
        const progress = group.tasks.length > 0 ? (doneTasks / group.tasks.length) * 100 : 0;

        return (
          <div
            key={group.group_id}
            className="rounded-lg border border-border-subtle bg-surface-raised overflow-hidden"
          >
            {/* Group header */}
            <button
              onClick={() => setExpandedGroup(isExpanded ? null : group.group_id)}
              className="w-full px-3 py-2 flex items-center justify-between hover:bg-surface-overlay/30 transition-colors"
            >
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-text-muted transition-transform" style={{ transform: isExpanded ? "rotate(90deg)" : "rotate(0)" }}>
                  {"\u25B6"}
                </span>
                <span className="text-xs font-mono font-medium text-text-primary">
                  {group.name}
                </span>
                <span className="text-[10px] font-mono text-text-muted">
                  {doneTasks}/{group.tasks.length}
                </span>
              </div>
              {group.dependencies && group.dependencies.length > 0 && (
                <span className="text-[10px] text-text-muted font-mono">
                  deps: {group.dependencies.join(", ")}
                </span>
              )}
            </button>

            {/* Progress bar */}
            <div className="px-3 pb-2">
              <div className="h-1 rounded-full bg-border-subtle overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${
                    progress === 100 ? "bg-success" : "bg-accent"
                  }`}
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>

            {/* Expanded task list */}
            {isExpanded && (
              <div className="border-t border-border-subtle/50 divide-y divide-border-subtle/30">
                {group.description && (
                  <div className="px-3 py-1.5 text-[10px] text-text-muted">
                    {group.description}
                  </div>
                )}
                {group.tasks.map((task) => (
                  <div key={task.id} className="px-3 py-1.5 flex items-center gap-2">
                    <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${STATUS_DOT[task.status] || "bg-text-muted"}`} />
                    <span className="text-[10px] font-mono text-text-muted shrink-0">{task.id}</span>
                    <span className="text-xs text-text-secondary truncate">{task.title}</span>
                    <span className="text-[10px] font-mono text-text-muted ml-auto shrink-0">{task.status}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
