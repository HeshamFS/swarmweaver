"use client";

import { useState, useEffect } from "react";

interface RunEntry {
  run_id: string;
  mode: string;
  status: string;
  started_at: string;
  completed_at?: string;
  agent_count?: number;
  tasks_completed?: number;
  tasks_total?: number;
  project_dir?: string;
}

interface ComparisonData {
  run1: Record<string, number>;
  run2: Record<string, number>;
  deltas: Record<string, number>;
  error?: string;
}

const MODE_COLORS: Record<string, string> = {
  greenfield: "text-[var(--color-mode-greenfield)]",
  feature: "text-[var(--color-mode-feature)]",
  refactor: "text-[var(--color-mode-refactor)]",
  fix: "text-[var(--color-mode-fix)]",
  evolve: "text-[var(--color-mode-evolve)]",
  security: "text-[var(--color-mode-security)]",
};

const STATUS_BADGES: Record<string, { label: string; className: string }> = {
  completed: { label: "Done", className: "text-success bg-success/10 border-success/30" },
  running: { label: "Running", className: "text-accent bg-accent/10 border-accent/30" },
  error: { label: "Error", className: "text-error bg-error/10 border-error/30" },
  stopped: { label: "Stopped", className: "text-warning bg-warning/10 border-warning/30" },
};

function DeltaChip({ label, value, unit, inverse }: { label: string; value: number; unit?: string; inverse?: boolean }) {
  const isPositive = inverse ? value < 0 : value > 0;
  const isNegative = inverse ? value > 0 : value < 0;
  const color = isPositive ? "text-success" : isNegative ? "text-error" : "text-text-muted";
  const sign = value > 0 ? "+" : "";
  const display = unit === "$" ? `${sign}$${Math.abs(value).toFixed(4)}` : `${sign}${value}${unit || ""}`;

  return (
    <div className="flex items-center justify-between py-1.5 px-2">
      <span className="text-[10px] text-text-secondary font-mono">{label}</span>
      <span className={`text-[11px] font-mono font-medium ${color}`}>{display}</span>
    </div>
  );
}

function ComparisonModal({
  projectDir,
  run1,
  run2,
  onClose,
}: {
  projectDir: string;
  run1: RunEntry;
  run2: RunEntry;
  onClose: () => void;
}) {
  const [data, setData] = useState<ComparisonData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetch(
      `/api/runs/compare?path=${encodeURIComponent(projectDir)}&run1=${encodeURIComponent(run1.run_id)}&run2=${encodeURIComponent(run2.run_id)}`
    )
      .then((r) => r.json())
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [projectDir, run1.run_id, run2.run_id]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={onClose}>
      <div
        className="bg-[var(--color-surface-2)] border border-[var(--color-border-default)] rounded-xl shadow-2xl w-[480px] max-h-[80vh] overflow-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--color-border-subtle)]">
          <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">Run Comparison</h3>
          <button
            onClick={onClose}
            className="text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Run labels */}
        <div className="grid grid-cols-2 gap-2 px-4 py-3 border-b border-[var(--color-border-subtle)]">
          <div className="text-center">
            <div className="text-[10px] text-text-muted mb-0.5">Run A</div>
            <div className="text-[11px] font-mono text-text-primary">{run1.run_id.slice(0, 12)}</div>
            <div className="text-[9px] text-text-muted">{new Date(run1.started_at).toLocaleString()}</div>
          </div>
          <div className="text-center">
            <div className="text-[10px] text-text-muted mb-0.5">Run B</div>
            <div className="text-[11px] font-mono text-text-primary">{run2.run_id.slice(0, 12)}</div>
            <div className="text-[9px] text-text-muted">{new Date(run2.started_at).toLocaleString()}</div>
          </div>
        </div>

        {/* Content */}
        <div className="px-4 py-3">
          {loading ? (
            <div className="text-xs text-text-muted text-center py-6">Loading comparison...</div>
          ) : !data || data.error ? (
            <div className="text-xs text-error text-center py-6">{data?.error || "Failed to load comparison"}</div>
          ) : (
            <div className="space-y-0.5 divide-y divide-[var(--color-border-subtle)]">
              <DeltaChip label="Cost" value={data.deltas.cost_usd || 0} unit="$" inverse />
              <DeltaChip label="Duration" value={Math.round((data.deltas.duration_seconds || 0) / 60)} unit="m" inverse />
              <DeltaChip label="Tasks Completed" value={data.deltas.tasks_completed || 0} />
              <DeltaChip label="Errors" value={data.deltas.errors || 0} inverse />
              <DeltaChip label="Tool Calls" value={data.deltas.tool_calls || 0} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export function RunHistoryPanel({ projectDir }: { projectDir: string }) {
  const [runs, setRuns] = useState<RunEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [compareMode, setCompareMode] = useState(false);
  const [selectedRuns, setSelectedRuns] = useState<RunEntry[]>([]);
  const [showComparison, setShowComparison] = useState(false);

  useEffect(() => {
    if (!projectDir) return;
    setLoading(true);
    fetch(`/api/runs?path=${encodeURIComponent(projectDir)}`)
      .then((r) => (r.ok ? r.json() : { runs: [] }))
      .then((data) => setRuns(data.runs || []))
      .catch(() => setRuns([]))
      .finally(() => setLoading(false));
  }, [projectDir]);

  const toggleRunSelection = (run: RunEntry) => {
    setSelectedRuns((prev) => {
      const exists = prev.find((r) => r.run_id === run.run_id);
      if (exists) return prev.filter((r) => r.run_id !== run.run_id);
      if (prev.length >= 2) return [prev[1], run]; // Keep last + new
      return [...prev, run];
    });
  };

  const isSelected = (run: RunEntry) => selectedRuns.some((r) => r.run_id === run.run_id);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-32 text-xs text-text-muted">
        Loading run history...
      </div>
    );
  }

  if (runs.length === 0) {
    return (
      <div className="flex items-center justify-center h-32 text-xs text-text-muted">
        No runs recorded yet.
      </div>
    );
  }

  return (
    <div className="overflow-y-auto h-full">
      {/* Compare toolbar */}
      {runs.length >= 2 && (
        <div className="flex items-center justify-between px-3 py-2 border-b border-[var(--color-border-subtle)] bg-[var(--color-surface-1)]">
          <button
            onClick={() => {
              setCompareMode((v) => !v);
              setSelectedRuns([]);
            }}
            className={`text-[10px] font-mono px-2 py-1 rounded transition-colors ${
              compareMode
                ? "bg-[var(--color-accent)]/20 text-[var(--color-accent)] border border-[var(--color-accent)]/30"
                : "text-text-muted hover:text-text-secondary"
            }`}
          >
            {compareMode ? "Cancel" : "Compare"}
          </button>
          {compareMode && selectedRuns.length === 2 && (
            <button
              onClick={() => setShowComparison(true)}
              className="text-[10px] font-mono px-2 py-1 rounded bg-[var(--color-accent)] text-white hover:opacity-90 transition-opacity"
            >
              Compare Selected
            </button>
          )}
          {compareMode && selectedRuns.length < 2 && (
            <span className="text-[10px] text-text-muted">Select {2 - selectedRuns.length} more run(s)</span>
          )}
        </div>
      )}

      <div className="divide-y divide-border-subtle/50">
        {runs.map((run) => {
          const badge = STATUS_BADGES[run.status] || STATUS_BADGES.stopped;
          const selected = compareMode && isSelected(run);
          return (
            <div
              key={run.run_id}
              className={`px-3 py-2.5 transition-colors ${
                compareMode ? "cursor-pointer" : ""
              } ${selected ? "bg-[var(--color-accent)]/5 border-l-2 border-l-[var(--color-accent)]" : "hover:bg-surface-raised/50"}`}
              onClick={compareMode ? () => toggleRunSelection(run) : undefined}
            >
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  {compareMode && (
                    <div
                      className={`w-3.5 h-3.5 rounded border flex items-center justify-center shrink-0 ${
                        selected
                          ? "bg-[var(--color-accent)] border-[var(--color-accent)]"
                          : "border-[var(--color-border-default)]"
                      }`}
                    >
                      {selected && (
                        <svg className="w-2.5 h-2.5 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                          <path d="M5 13l4 4L19 7" />
                        </svg>
                      )}
                    </div>
                  )}
                  <span className={`text-xs font-mono font-medium ${MODE_COLORS[run.mode] || "text-text-primary"}`}>
                    {run.mode}
                  </span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded border font-mono ${badge.className}`}>
                    {badge.label}
                  </span>
                </div>
                {run.agent_count && run.agent_count > 1 && (
                  <span className="text-[10px] font-mono text-text-muted">
                    {run.agent_count}w
                  </span>
                )}
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-mono text-text-muted">
                  {new Date(run.started_at).toLocaleString()}
                </span>
                {run.tasks_total != null && run.tasks_total > 0 && (
                  <span className="text-[10px] font-mono text-text-secondary">
                    {run.tasks_completed ?? 0}/{run.tasks_total} tasks
                  </span>
                )}
              </div>
              {/* Progress bar */}
              {run.tasks_total != null && run.tasks_total > 0 && (
                <div className="mt-1.5 h-1 rounded-full bg-border-subtle overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${
                      run.status === "error" ? "bg-error" : run.status === "completed" ? "bg-success" : "bg-accent"
                    }`}
                    style={{ width: `${((run.tasks_completed ?? 0) / run.tasks_total) * 100}%` }}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Comparison modal */}
      {showComparison && selectedRuns.length === 2 && (
        <ComparisonModal
          projectDir={projectDir}
          run1={selectedRuns[0]}
          run2={selectedRuns[1]}
          onClose={() => setShowComparison(false)}
        />
      )}
    </div>
  );
}
