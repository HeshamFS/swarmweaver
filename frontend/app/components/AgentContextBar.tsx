"use client";

export interface ContextWorker {
  worker_id: number;
  name?: string;
  status?: string;
  capability?: string;
  current_task?: string | null;
  completed_tasks?: string[];
  assigned_task_ids?: string[];
  file_scope?: string[];
}

interface AgentContextBarProps {
  workers: ContextWorker[];
  selectedWorkerId: number | null;
  onSelectWorker: (id: number | null) => void;
  mainStatus?: string;
  mainLabel?: string;
}

const CAPABILITY_ICON: Record<string, string> = {
  scout: "⊙",
  builder: "⚒",
  reviewer: "◎",
  lead: "★",
  coordinator: "★",
  monitor: "◈",
  merger: "⇄",
};

const STATUS_DOT: Record<string, string> = {
  working: "bg-success animate-pulse",
  done: "bg-text-muted",
  completed: "bg-text-muted",
  stalled: "bg-warning animate-pulse",
  error: "bg-error animate-pulse",
  idle: "bg-[#333]",
};

export function AgentContextBar({
  workers,
  selectedWorkerId,
  onSelectWorker,
  mainStatus = "idle",
  mainLabel = "Orchestrator",
}: AgentContextBarProps) {
  if (workers.length === 0) return null;

  const mainDot =
    mainStatus === "running" || mainStatus === "starting"
      ? "bg-success animate-pulse"
      : "bg-[#333]";

  return (
    <div className="flex items-center h-7 px-3 gap-1.5 border-b border-[#1A1A1A] bg-[#080808] overflow-x-auto shrink-0 z-20">
      {/* Viewing label */}
      <span className="text-[9px] font-mono text-[#333] uppercase tracking-widest shrink-0 mr-1">
        View
      </span>

      {/* Main / Orchestrator button */}
      <button
        onClick={() => onSelectWorker(null)}
        className={`flex items-center gap-1.5 px-2 py-0.5 text-[10px] font-mono transition-colors whitespace-nowrap rounded ${
          selectedWorkerId === null
            ? "text-[var(--color-accent)] bg-[var(--color-accent)]/10 border border-[var(--color-accent)]/30"
            : "text-[#444] hover:text-[#888] hover:bg-[#1A1A1A] border border-transparent"
        }`}
        title="View main session / orchestrator"
      >
        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${mainDot}`} />
        <span className="font-medium">◇ {mainLabel}</span>
      </button>

      <span className="w-px h-3 bg-[#1A1A1A] shrink-0" />

      {/* Worker buttons */}
      {workers.map((w) => {
        const isActive = selectedWorkerId === w.worker_id;
        const dotClass = STATUS_DOT[w.status || "idle"] ?? "bg-[#333]";
        const icon = CAPABILITY_ICON[w.capability || "builder"] ?? "⚒";
        const doneCount = w.completed_tasks?.length ?? 0;
        const hasCurrentTask = !!w.current_task;
        const cap = w.capability || "builder";

        const capColor: Record<string, string> = {
          scout: "text-[#F59E0B]",
          builder: "text-[var(--color-accent)]",
          reviewer: "text-[#3B82F6]",
          lead: "text-purple-400",
          coordinator: "text-purple-400",
          monitor: "text-[#888]",
          merger: "text-purple-400",
        };
        const iconColor = isActive ? "" : (capColor[cap] ?? "text-[#555]");

        return (
          <button
            key={w.worker_id}
            onClick={() => onSelectWorker(w.worker_id)}
            className={`flex items-center gap-1 px-2 py-0.5 text-[10px] font-mono transition-colors whitespace-nowrap rounded ${
              isActive
                ? "text-[var(--color-accent)] bg-[var(--color-accent)]/10 border border-[var(--color-accent)]/30"
                : "text-[#444] hover:text-[#888] hover:bg-[#1A1A1A] border border-transparent"
            }`}
            title={`W${w.worker_id} ${cap} | ${w.current_task || "idle"} | ${doneCount} done | ${w.file_scope?.length ?? 0} files in scope`}
          >
            <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${dotClass}`} />
            <span className={isActive ? "" : iconColor}>{icon}</span>
            <span className="font-medium">{w.name || `worker-${w.worker_id}`}</span>
            {!isActive && (
              <span className="text-[#333] text-[9px]">{cap.slice(0, 3)}</span>
            )}
            {isActive && (
              <span className="text-[9px] opacity-70">{cap}</span>
            )}
            {hasCurrentTask && !isActive && (
              <span className="w-1 h-1 rounded-full bg-success/60 animate-pulse shrink-0" title="Task in progress" />
            )}
            {doneCount > 0 && (
              <span className={`text-[9px] ${isActive ? "text-[var(--color-success)]" : "text-[#444]"}`}>
                {doneCount}✓
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
