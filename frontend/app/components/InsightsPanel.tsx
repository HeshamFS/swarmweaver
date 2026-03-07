"use client";

import { useState, useEffect, useCallback } from "react";

interface ExpertiseEntry {
  id: string;
  content: string;
  category: string;
  domain: string;
  tags: string[];
  source_file: string;
  created_at: string;
  relevance_score: number;
}

interface InsightData {
  top_tools: { name: string; count: number }[];
  hot_files: { path: string; touches: number }[];
  error_frequency: { type: string; count: number }[];
  insights: { category: string; message: string; severity: string }[];
}

interface MemoryEffectiveness {
  total_memories: number;
  tracked_count: number;
  total_outcomes: number;
  success_count: number;
  success_rate: number;
}

const SEVERITY_COLORS: Record<string, string> = {
  info: "text-info bg-info/10 border-info/20",
  warning: "text-warning bg-warning/10 border-warning/20",
  error: "text-error bg-error/10 border-error/20",
  success: "text-success bg-success/10 border-success/20",
};

export function InsightsPanel({ projectDir, onSwitchToExpertise }: { projectDir: string; onSwitchToExpertise?: () => void }) {
  const [data, setData] = useState<InsightData | null>(null);
  const [loading, setLoading] = useState(true);
  const [memEffectiveness, setMemEffectiveness] = useState<MemoryEffectiveness | null>(null);
  const [expertise, setExpertise] = useState<ExpertiseEntry[]>([]);

  useEffect(() => {
    if (!projectDir) return;
    setLoading(true);
    fetch(`/api/insights?path=${encodeURIComponent(projectDir)}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (d) setData(d); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [projectDir]);

  const fetchExpertise = useCallback(() => {
    if (!projectDir) return;
    fetch(`/api/projects/expertise?path=${encodeURIComponent(projectDir)}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (d) setExpertise(d.entries || []); })
      .catch(() => {});
  }, [projectDir]);

  useEffect(() => {
    fetchExpertise();
  }, [fetchExpertise]);

  // Fetch memory effectiveness data
  useEffect(() => {
    fetch("/api/memory")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (!d?.memories) return;
        const memories = d.memories as {
          outcome_count?: number;
          success_count?: number;
        }[];
        const tracked = memories.filter((m) => (m.outcome_count ?? 0) > 0);
        let totalOutcomes = 0;
        let totalSuccess = 0;
        for (const m of tracked) {
          totalOutcomes += m.outcome_count ?? 0;
          totalSuccess += m.success_count ?? 0;
        }
        setMemEffectiveness({
          total_memories: memories.length,
          tracked_count: tracked.length,
          total_outcomes: totalOutcomes,
          success_count: totalSuccess,
          success_rate: totalOutcomes > 0 ? totalSuccess / totalOutcomes : 0,
        });
      })
      .catch(() => {});
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-32 text-xs text-text-muted">
        Analyzing session...
      </div>
    );
  }

  if (!data) {
    return (
      <div className="flex items-center justify-center h-32 text-xs text-text-muted">
        No insights available yet.
      </div>
    );
  }

  const maxToolCount = Math.max(...(data.top_tools?.map((t) => t.count) || [1]), 1);

  return (
    <div className="overflow-y-auto h-full p-3 space-y-4">
      {/* Memory Effectiveness */}
      {memEffectiveness && memEffectiveness.total_memories > 0 && (
        <div>
          <h3 className="text-[10px] font-mono text-text-muted uppercase tracking-wider mb-2">
            Memory Effectiveness
          </h3>
          <div className="rounded-lg border border-border-subtle bg-surface-raised p-3 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono text-text-muted">
                Total memories
              </span>
              <span className="text-xs font-mono text-text-primary">
                {memEffectiveness.total_memories}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono text-text-muted">
                Memories with outcomes
              </span>
              <span className="text-xs font-mono text-text-primary">
                {memEffectiveness.tracked_count}
              </span>
            </div>
            {memEffectiveness.total_outcomes > 0 && (
              <>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-mono text-text-muted">
                    Successful outcomes
                  </span>
                  <span
                    className={`text-xs font-mono font-medium ${
                      memEffectiveness.success_rate > 0.7
                        ? "text-success"
                        : memEffectiveness.success_rate >= 0.4
                        ? "text-warning"
                        : "text-error"
                    }`}
                  >
                    {Math.round(memEffectiveness.success_count)}/{memEffectiveness.total_outcomes}
                  </span>
                </div>
                <div className="space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-mono text-text-muted">
                      Success rate
                    </span>
                    <span
                      className={`text-[10px] font-mono font-medium ${
                        memEffectiveness.success_rate > 0.7
                          ? "text-success"
                          : memEffectiveness.success_rate >= 0.4
                          ? "text-warning"
                          : "text-error"
                      }`}
                    >
                      {Math.round(memEffectiveness.success_rate * 100)}%
                    </span>
                  </div>
                  <div className="h-2 w-full rounded-full bg-border-subtle overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${
                        memEffectiveness.success_rate > 0.7
                          ? "bg-success"
                          : memEffectiveness.success_rate >= 0.4
                          ? "bg-warning"
                          : "bg-error"
                      }`}
                      style={{ width: `${Math.max(memEffectiveness.success_rate * 100, 2)}%` }}
                    />
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* Top Tools */}
      {data.top_tools && data.top_tools.length > 0 && (
        <div>
          <h3 className="text-[10px] font-mono text-text-muted uppercase tracking-wider mb-2">
            Top Tools
          </h3>
          <div className="space-y-1.5">
            {data.top_tools.slice(0, 8).map((tool) => (
              <div key={tool.name} className="flex items-center gap-2">
                <span className="text-[10px] font-mono text-text-secondary w-20 truncate shrink-0">
                  {tool.name}
                </span>
                <div className="flex-1 h-3 rounded-full bg-border-subtle overflow-hidden">
                  <div
                    className="h-full rounded-full bg-accent/60"
                    style={{ width: `${(tool.count / maxToolCount) * 100}%` }}
                  />
                </div>
                <span className="text-[10px] font-mono text-text-muted w-8 text-right shrink-0">
                  {tool.count}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Hot Files */}
      {data.hot_files && data.hot_files.length > 0 && (
        <div>
          <h3 className="text-[10px] font-mono text-text-muted uppercase tracking-wider mb-2">
            Hot Files
          </h3>
          <div className="space-y-1">
            {data.hot_files.slice(0, 6).map((file) => (
              <div key={file.path} className="flex items-center justify-between">
                <span className="text-[10px] font-mono text-text-secondary truncate flex-1">
                  {file.path}
                </span>
                <span className="text-[10px] font-mono text-accent ml-2 shrink-0">
                  {file.touches}x
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Error Frequency */}
      {data.error_frequency && data.error_frequency.length > 0 && (
        <div>
          <h3 className="text-[10px] font-mono text-text-muted uppercase tracking-wider mb-2">
            Error Frequency
          </h3>
          <div className="space-y-1">
            {data.error_frequency.slice(0, 5).map((err) => (
              <div key={err.type} className="flex items-center justify-between">
                <span className="text-[10px] font-mono text-error truncate flex-1">
                  {err.type}
                </span>
                <span className="text-[10px] font-mono text-text-muted ml-2 shrink-0">
                  {err.count}x
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Insight Cards */}
      {data.insights && data.insights.length > 0 && (
        <div>
          <h3 className="text-[10px] font-mono text-text-muted uppercase tracking-wider mb-2">
            Insights
          </h3>
          <div className="space-y-2">
            {data.insights.map((insight, i) => (
              <div
                key={i}
                className={`rounded-lg border p-2.5 ${
                  SEVERITY_COLORS[insight.severity] || SEVERITY_COLORS.info
                }`}
              >
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-[10px] font-mono uppercase tracking-wider">
                    {insight.category}
                  </span>
                </div>
                <p className="text-xs leading-relaxed">{insight.message}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Harvested Expertise */}
      {expertise.length > 0 && (
        <div>
          <h3 className="text-[10px] font-mono text-text-muted uppercase tracking-wider mb-2">
            Harvested Expertise
          </h3>
          <div className="rounded-lg border border-border-subtle bg-surface-raised p-3 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono text-text-muted">
                Total entries
              </span>
              <span className="text-xs font-mono text-text-primary">
                {expertise.length}
              </span>
            </div>
            {/* Domain breakdown */}
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(
                expertise.reduce<Record<string, number>>((acc, e) => {
                  const d = e.domain || "general";
                  acc[d] = (acc[d] || 0) + 1;
                  return acc;
                }, {})
              )
                .sort(([, a], [, b]) => b - a)
                .map(([domain, count]) => (
                  <span
                    key={domain}
                    className="text-[10px] px-1.5 py-0.5 rounded bg-surface border border-border-subtle font-mono text-text-secondary"
                  >
                    {count} {domain}
                  </span>
                ))}
            </div>
            {onSwitchToExpertise && (
              <button
                onClick={onSwitchToExpertise}
                className="text-[10px] font-mono text-accent hover:text-accent-hover transition-colors"
              >
                View all in Project Expertise tab &rarr;
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
