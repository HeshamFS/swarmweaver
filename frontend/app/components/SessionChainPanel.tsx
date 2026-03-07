"use client";

import { useState, useEffect } from "react";

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

interface SessionChainPanelProps {
  projectDir: string;
  currentSessionId?: string;
}

function formatDuration(start: string, end: string | null): string {
  if (!end) return "running";
  const ms = new Date(end).getTime() - new Date(start).getTime();
  if (ms < 0) return "--";
  const sec = Math.floor(ms / 1000);
  if (sec < 60) return `${sec}s`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ${sec % 60}s`;
  const hr = Math.floor(min / 60);
  return `${hr}h ${min % 60}m`;
}

function formatCost(cost: number): string {
  if (cost < 0.01) return `$${cost.toFixed(4)}`;
  return `$${cost.toFixed(2)}`;
}

export function SessionChainPanel({ projectDir, currentSessionId }: SessionChainPanelProps) {
  const [sessions, setSessions] = useState<ChainSession[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!projectDir) return;
    const enc = encodeURIComponent(projectDir);

    const fetchChain = () => {
      fetch(`/api/session/chain?path=${enc}`)
        .then((r) => (r.ok ? r.json() : []))
        .then((data) => {
          if (Array.isArray(data)) {
            setSessions(data);
          }
          setLoading(false);
        })
        .catch(() => setLoading(false));
    };

    fetchChain();
    const interval = setInterval(fetchChain, 5000);
    return () => clearInterval(interval);
  }, [projectDir]);

  if (loading) {
    return (
      <div className="p-4 text-center text-text-muted text-xs font-mono">
        Loading chain...
      </div>
    );
  }

  if (sessions.length === 0) {
    return (
      <div className="p-4 text-center text-text-muted text-xs">
        No session chain data yet.
      </div>
    );
  }

  const totalCost = sessions.reduce((sum, s) => sum + (s.cost || 0), 0);
  const totalTasksDone = sessions.length > 0 ? sessions[sessions.length - 1].tasks_completed : 0;
  const totalTasksAll = sessions.length > 0 ? sessions[sessions.length - 1].tasks_total : 0;

  // Calculate total duration from first start to last end
  const firstStart = sessions[0]?.start_time;
  const lastEnd = sessions[sessions.length - 1]?.end_time;
  const totalDuration = firstStart ? formatDuration(firstStart, lastEnd) : "--";

  return (
    <div className="p-4 space-y-4">
      {/* Chain summary header */}
      <div className="flex items-center gap-3 text-xs">
        <span className="text-text-muted font-medium uppercase tracking-wider">Session Chain</span>
        <span className="font-mono text-text-secondary">{sessions.length} session{sessions.length !== 1 ? "s" : ""}</span>
        <span className="w-px h-3 bg-border-subtle" />
        <span className="font-mono text-text-secondary">{totalDuration}</span>
        <span className="w-px h-3 bg-border-subtle" />
        <span className="font-mono text-accent">{formatCost(totalCost)}</span>
      </div>

      {/* Timeline */}
      <div className="relative pl-6">
        {/* Vertical line */}
        <div className="absolute left-[9px] top-2 bottom-2 w-px bg-border-subtle" />

        <div className="space-y-0">
          {sessions.map((session, idx) => {
            const isCurrent = session.session_id === currentSessionId;
            const isLast = idx === sessions.length - 1;
            const isRunning = !session.end_time;

            return (
              <div key={session.session_id || idx}>
                {/* Session node */}
                <div className="relative flex items-start gap-3 py-2">
                  {/* Dot marker */}
                  <div
                    className={`absolute -left-6 top-3 w-[11px] h-[11px] rounded-full border-2 z-10 ${
                      isCurrent || (isLast && isRunning)
                        ? "border-accent bg-accent"
                        : "border-border-default bg-surface-raised"
                    }`}
                  />
                  {isRunning && (isLast || isCurrent) && (
                    <div className="absolute -left-6 top-3 w-[11px] h-[11px] rounded-full bg-accent animate-ping opacity-30" />
                  )}

                  {/* Session content */}
                  <div
                    className={`flex-1 rounded-lg border p-3 ${
                      isCurrent || (isLast && isRunning)
                        ? "border-accent/30 bg-accent/5"
                        : "border-border-subtle bg-surface"
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      {/* Sequence badge */}
                      <span
                        className={`text-[10px] font-bold font-mono px-1.5 py-0.5 rounded ${
                          isCurrent || (isLast && isRunning)
                            ? "bg-accent/15 text-accent"
                            : "bg-surface-raised text-text-muted"
                        }`}
                      >
                        S{session.sequence_number}
                      </span>

                      {/* Phase */}
                      {session.phase && (
                        <span className="text-[10px] font-mono text-text-secondary uppercase">
                          {session.phase}
                        </span>
                      )}

                      <div className="flex-1" />

                      {/* Duration */}
                      <span className="text-[10px] font-mono text-text-muted">
                        {formatDuration(session.start_time, session.end_time)}
                      </span>
                    </div>

                    {/* Stats row */}
                    <div className="flex items-center gap-3 text-[10px] font-mono text-text-muted">
                      {/* Tasks */}
                      <span>
                        {session.tasks_completed}/{session.tasks_total} tasks
                      </span>
                      {/* Cost */}
                      <span className="text-accent">
                        {formatCost(session.cost)}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Handoff marker between sessions */}
                {idx < sessions.length - 1 && session.checkpoint_summary && (
                  <div className="relative ml-1 pl-5 py-1">
                    <div className="text-[10px] text-text-muted italic leading-snug line-clamp-2">
                      {session.checkpoint_summary}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Chain totals footer */}
      <div className="flex items-center gap-4 pt-2 border-t border-border-subtle text-[10px] font-mono text-text-muted">
        <span>
          Progress: {totalTasksDone}/{totalTasksAll}
        </span>
        <div className="flex-1 h-1 bg-surface-raised rounded-full overflow-hidden">
          <div
            className="h-full rounded-full bg-accent transition-all duration-300"
            style={{ width: `${totalTasksAll > 0 ? (totalTasksDone / totalTasksAll) * 100 : 0}%` }}
          />
        </div>
        <span>{totalTasksAll > 0 ? Math.round((totalTasksDone / totalTasksAll) * 100) : 0}%</span>
      </div>
    </div>
  );
}
