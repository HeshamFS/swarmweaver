interface MergeInfo {
  worker_id: number;
  branch: string;
  tier?: number;
  tier_name?: string;
  details?: string;
  error?: string;
  files_conflicted?: string[];
}

interface MergeQueueEntry {
  id: string;
  worker_id: number;
  branch: string;
  status: "pending" | "merging" | "merged" | "failed" | "conflict";
  resolution_tier: number;
  created_at: string;
  resolved_at?: string;
  error?: string;
  files_changed?: number;
}

interface MergeQueueStats {
  total: number;
  pending: number;
  merged: number;
  failed: number;
}

interface ConflictPrediction {
  predicted_files: string[];
  confidence?: number;
}

interface MergerAgentStats {
  merges_completed: number;
  conflicts_resolved: number;
  average_tier: number;
  files_merged: number;
}

export interface SwarmMergesTabProps {
  mergeQueue: MergeQueueEntry[];
  mergeQueueStats: MergeQueueStats;
  mergeReport: { merged: MergeInfo[]; failed: MergeInfo[] };
  conflictPrediction: ConflictPrediction | null;
}

const TIER_LABELS: Record<number, { label: string; color: string }> = {
  1: { label: "Clean", color: "text-success" },
  2: { label: "Auto-resolve", color: "text-info" },
  3: { label: "AI-resolve", color: "text-warning" },
  4: { label: "Reimagine", color: "text-accent" },
  0: { label: "Failed", color: "text-error" },
};

export function SwarmMergesTab({
  mergeQueue,
  mergeQueueStats,
  mergeReport,
  conflictPrediction,
}: SwarmMergesTabProps) {
  // Derive merger agent stats from merge report
  const mergerStats: MergerAgentStats | null = (() => {
    const merged = mergeReport.merged || [];
    if (merged.length === 0 && (mergeReport.failed || []).length === 0) return null;
    const totalMerges = merged.length;
    const conflictsResolved = merged.filter((m) => m.tier && m.tier > 1).length;
    const avgTier = totalMerges > 0
      ? merged.reduce((sum, m) => sum + (m.tier || 1), 0) / totalMerges
      : 0;
    return {
      merges_completed: totalMerges,
      conflicts_resolved: conflictsResolved,
      average_tier: avgTier,
      files_merged: merged.reduce((sum, m) => {
        const details = m.details;
        if (typeof details === "string") {
          const match = details.match(/(\d+)\s+file/);
          return sum + (match ? parseInt(match[1], 10) : 0);
        }
        return sum;
      }, 0),
    };
  })();

  return (
    <div className="p-3 space-y-3">
      {/* Merger Agent summary */}
      {mergerStats && (
        <div className="rounded-lg border border-purple-400/30 bg-purple-400/5 p-2.5 mb-2">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-sm">{"\u{1F500}"}</span>
            <span className="text-[10px] font-semibold uppercase tracking-wider text-purple-400">
              Merger Agent
            </span>
          </div>
          <div className="flex items-center gap-4">
            <div className="text-center">
              <div className="text-sm font-mono font-bold text-text-primary">{mergerStats.merges_completed}</div>
              <div className="text-[9px] text-text-muted">merged</div>
            </div>
            <div className="text-center">
              <div className="text-sm font-mono font-bold text-text-primary">{mergerStats.conflicts_resolved}</div>
              <div className="text-[9px] text-text-muted">conflicts</div>
            </div>
            <div className="text-center">
              <div className="text-sm font-mono font-bold text-text-primary">
                {mergerStats.average_tier > 0 ? `T${mergerStats.average_tier.toFixed(1)}` : "-"}
              </div>
              <div className="text-[9px] text-text-muted">avg tier</div>
            </div>
            {mergerStats.files_merged > 0 && (
              <div className="text-center">
                <div className="text-sm font-mono font-bold text-text-primary">{mergerStats.files_merged}</div>
                <div className="text-[9px] text-text-muted">files</div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Stats summary */}
      {mergeQueueStats.total > 0 && (
        <div className="flex items-center gap-3 mb-2">
          <span className="text-xs text-text-muted font-mono">
            Queue: {mergeQueueStats.total}
          </span>
          {mergeQueueStats.pending > 0 && (
            <span className="text-[10px] font-mono text-warning">{mergeQueueStats.pending} pending</span>
          )}
          {mergeQueueStats.merged > 0 && (
            <span className="text-[10px] font-mono text-success">{mergeQueueStats.merged} merged</span>
          )}
          {mergeQueueStats.failed > 0 && (
            <span className="text-[10px] font-mono text-error">{mergeQueueStats.failed} failed</span>
          )}
        </div>
      )}

      {/* Tier legend */}
      <div className="flex flex-wrap gap-2 mb-3">
        {[1, 2, 3, 4].map((tier) => {
          const info = TIER_LABELS[tier];
          return (
            <span key={tier} className={`text-[10px] font-mono ${info.color}`}>
              T{tier}: {info.label}
            </span>
          );
        })}
      </div>

      {/* Conflict Prediction */}
      {conflictPrediction && conflictPrediction.predicted_files.length > 0 && (
        <div className="rounded-lg border border-warning/30 bg-warning/5 p-2.5 mb-2">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-warning block mb-1">
            Predicted Conflicts
          </span>
          <div className="flex flex-wrap gap-1">
            {conflictPrediction.predicted_files.map((file) => (
              <span
                key={file}
                className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-warning/10 text-warning border border-warning/20"
              >
                {file}
              </span>
            ))}
          </div>
          {conflictPrediction.confidence != null && (
            <span className="text-[9px] text-text-muted mt-1 block">
              Confidence: {(conflictPrediction.confidence * 100).toFixed(0)}%
            </span>
          )}
        </div>
      )}

      {/* Merge Queue entries (from API) */}
      {mergeQueue.length > 0 && (
        <div className="space-y-2">
          {mergeQueue.map((entry) => {
            const tierInfo = TIER_LABELS[entry.resolution_tier] || TIER_LABELS[0];
            const statusColors: Record<string, string> = {
              pending: "border-warning/30 bg-warning/5",
              merging: "border-accent/30 bg-accent/5",
              merged: "border-success/30 bg-success/5",
              failed: "border-error/30 bg-error/5",
              conflict: "border-error/30 bg-error/5",
            };
            const statusIcons: Record<string, string> = {
              pending: "\u23F3",
              merging: "\u21BB",
              merged: "\u2713",
              failed: "\u2717",
              conflict: "\u26A0",
            };
            return (
              <div
                key={entry.id}
                className={`rounded border px-3 py-2 ${statusColors[entry.status] || "border-border-subtle"}`}
              >
                <div className="flex items-center gap-2">
                  <span className="text-xs">{statusIcons[entry.status] || "\u2022"}</span>
                  <span className="text-xs font-mono text-text-primary">
                    {entry.branch || `Worker ${entry.worker_id}`}
                  </span>
                  <span
                    className={`text-[10px] font-mono px-1.5 py-0.5 rounded bg-surface ${tierInfo.color}`}
                  >
                    T{entry.resolution_tier}: {tierInfo.label}
                  </span>
                  <span className={`text-[10px] font-mono ml-auto ${
                    entry.status === "merged" ? "text-success" :
                    entry.status === "failed" || entry.status === "conflict" ? "text-error" :
                    "text-text-muted"
                  }`}>
                    {entry.status}
                  </span>
                </div>
                <div className="flex items-center gap-3 mt-1">
                  <span className="text-[9px] text-text-muted font-mono">
                    W{entry.worker_id}
                  </span>
                  {entry.files_changed != null && (
                    <span className="text-[9px] text-text-muted font-mono">
                      {entry.files_changed} files
                    </span>
                  )}
                  <span className="text-[9px] text-text-muted font-mono">
                    {new Date(entry.created_at).toLocaleTimeString()}
                  </span>
                  {entry.resolved_at && (
                    <span className="text-[9px] text-text-muted font-mono">
                      {"\u2192"} {new Date(entry.resolved_at).toLocaleTimeString()}
                    </span>
                  )}
                </div>
                {entry.error && (
                  <div className="text-[10px] text-error mt-1 font-mono">{entry.error}</div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Fallback: derive from worker states if no queue data */}
      {mergeQueue.length === 0 && (mergeReport.merged.length > 0 || mergeReport.failed.length > 0) && (
        <>
          {mergeReport.merged.length > 0 && (
            <div className="space-y-2">
              <div className="text-xs text-success font-medium">Merged</div>
              {mergeReport.merged.map((m, i) => (
                <div key={i} className="rounded border border-success/30 bg-success/5 px-3 py-2">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-success">{"\u2713"}</span>
                    <span className="text-xs font-mono text-text-primary">
                      {m.branch || `Worker ${m.worker_id}`}
                    </span>
                    {m.tier && (
                      <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded bg-surface ${TIER_LABELS[m.tier]?.color || ""}`}>
                        Tier {m.tier}: {m.tier_name || TIER_LABELS[m.tier]?.label}
                      </span>
                    )}
                  </div>
                  {m.details && <div className="text-[10px] text-text-muted mt-1">{typeof m.details === "string" ? m.details : JSON.stringify(m.details)}</div>}
                </div>
              ))}
            </div>
          )}
          {mergeReport.failed.length > 0 && (
            <div className="space-y-2">
              <div className="text-xs text-error font-medium">Failed</div>
              {mergeReport.failed.map((m, i) => (
                <div key={i} className="rounded border border-error/30 bg-error/5 px-3 py-2">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-error">{"\u2717"}</span>
                    <span className="text-xs font-mono text-text-primary">
                      {m.branch || `Worker ${m.worker_id}`}
                    </span>
                  </div>
                  {m.error && <div className="text-[10px] text-error mt-1">{m.error}</div>}
                  {m.files_conflicted && m.files_conflicted.length > 0 && (
                    <div className="text-[10px] text-text-muted mt-1">
                      Conflicted: {m.files_conflicted.join(", ")}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {mergeQueue.length === 0 && mergeReport.merged.length === 0 && mergeReport.failed.length === 0 && (
        <div className="flex items-center justify-center p-8">
          <span className="text-xs text-text-muted">
            No merge activity yet. Merges happen after all workers complete.
          </span>
        </div>
      )}
    </div>
  );
}
