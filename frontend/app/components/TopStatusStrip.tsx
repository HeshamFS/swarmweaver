"use client";

import { useState, useEffect } from "react";

interface TopStatusStripProps {
  projectDir: string;
  mode: string | null;
  status: string;
  sessionStats: { current_phase: string; session_number: number } | null;
  onChainClick?: () => void;
  escalationCount?: number;
  monitorFleetScore?: number | null;
  monitorActive?: boolean;
}

interface HealthData {
  overall: "pass" | "warn" | "fail";
  passed: number;
  warned: number;
  failed: number;
}

interface BudgetData {
  total_cost: number;
  budget_limit: number | null;
  estimated_cost_usd?: number;
  budget_limit_usd?: number;
  max_hours?: number;
  elapsed_hours?: number;
}

interface SwarmData {
  num_workers: number;
  workers: { status: string; capability?: string; runtime?: string }[];
  overrides?: { directive: string; value?: string | null; active: boolean }[];
  runtime?: string;
}

const HEALTH_DOT: Record<string, string> = {
  pass: "bg-success",
  warn: "bg-warning animate-pulse",
  fail: "bg-error animate-pulse",
};

export function TopStatusStrip({ projectDir, mode, status, sessionStats, onChainClick, escalationCount = 0, monitorFleetScore, monitorActive }: TopStatusStripProps) {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [budget, setBudget] = useState<BudgetData | null>(null);
  const [swarm, setSwarm] = useState<SwarmData | null>(null);
  const [chainLength, setChainLength] = useState(0);

  useEffect(() => {
    if (!projectDir) return;
    const enc = encodeURIComponent(projectDir);

    const poll = () => {
      fetch(`/api/doctor?path=${enc}`)
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => { if (d) setHealth(d); })
        .catch(() => {});

      fetch(`/api/budget?path=${enc}`)
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => { if (d) setBudget(d); })
        .catch(() => {});

      fetch(`/api/swarm/status?path=${enc}`)
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => { if (d && d.num_workers > 0) setSwarm(d); })
        .catch(() => {});

      fetch(`/api/session/chain?path=${enc}`)
        .then((r) => (r.ok ? r.json() : []))
        .then((d) => { if (Array.isArray(d)) setChainLength(d.length); })
        .catch(() => {});
    };

    poll();
    const interval = setInterval(poll, 10000);
    return () => clearInterval(interval);
  }, [projectDir]);

  const activeWorkers = swarm?.workers?.filter((w) => w.status === "working").length ?? 0;
  const stalledWorkers = swarm?.workers?.filter((w) => w.status === "stalled" || (w as Record<string, unknown>).health_status === "stalled").length ?? 0;
  const capBreakdown = swarm?.workers?.reduce((acc, w) => {
    const cap = (w as { capability?: string }).capability || "builder";
    acc[cap] = (acc[cap] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  return (
    <div className="flex items-center h-9 px-4 border-b border-border-subtle bg-surface-raised/80 backdrop-blur-sm gap-4 shrink-0 z-30">
      {/* Health dots + escalation indicator (uses monitor fleet score when available) */}
      <div className="flex items-center gap-1.5" title={
        monitorFleetScore != null
          ? `Fleet score: ${monitorFleetScore}/100`
          : health ? `${health.passed}P ${health.warned}W ${health.failed}F` : "Loading..."
      }>
        <span className={`w-2 h-2 rounded-full ${
          monitorFleetScore != null
            ? monitorFleetScore > 70 ? "bg-success" : monitorFleetScore > 40 ? "bg-warning animate-pulse" : "bg-error animate-pulse"
            : health ? HEALTH_DOT[health.overall] : "bg-text-muted"
        }`} />
        {health && (
          <span className="text-[10px] font-mono text-text-muted">
            {health.passed}
            {health.warned > 0 && <span className="text-warning">/{health.warned}</span>}
            {health.failed > 0 && <span className="text-error">/{health.failed}</span>}
          </span>
        )}
        {escalationCount > 0 && (
          <span className="flex items-center gap-0.5" title={`${escalationCount} unresolved escalation${escalationCount > 1 ? "s" : ""}`}>
            <span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse" />
            <span className="text-[10px] font-mono text-amber-400 font-medium">
              {escalationCount > 1 ? `(${escalationCount})` : ""}
            </span>
          </span>
        )}
      </div>

      <span className="w-px h-4 bg-border-subtle" />

      {/* Cost with budget progress */}
      <div className="flex flex-col justify-center gap-0.5">
        <div className="flex items-center gap-1">
          <span className="text-[10px] font-mono text-text-muted">$</span>
          <span className="text-xs font-mono text-text-secondary font-medium">
            {(budget?.estimated_cost_usd ?? budget?.total_cost ?? 0).toFixed(3)}
          </span>
          {(() => {
            const limit = budget?.budget_limit_usd ?? budget?.budget_limit ?? 0;
            return limit > 0 ? (
              <span className="text-[10px] font-mono text-text-muted" title={`Budget: $${limit.toFixed(2)}`}>
                / {limit.toFixed(2)}
              </span>
            ) : null;
          })()}
          {(() => {
            const maxH = budget?.max_hours ?? 0;
            const elapsed = budget?.elapsed_hours ?? 0;
            if (maxH <= 0) return null;
            const remaining = Math.max(0, maxH - elapsed);
            const hours = Math.floor(remaining);
            const mins = Math.round((remaining - hours) * 60);
            return (
              <span className="text-[10px] font-mono text-text-muted ml-1">
                {hours}h {mins}m left
              </span>
            );
          })()}
        </div>
        {(() => {
          const limit = budget?.budget_limit_usd ?? budget?.budget_limit ?? 0;
          if (limit <= 0) return null;
          const spent = budget?.estimated_cost_usd ?? budget?.total_cost ?? 0;
          const pct = Math.min(100, (spent / limit) * 100);
          const color = pct >= 80 ? "var(--color-error)" : pct >= 50 ? "var(--color-warning)" : "var(--color-accent)";
          return (
            <div className="w-full h-0.5 rounded-full bg-[var(--color-surface-base)] overflow-hidden" style={{ minWidth: 60 }}>
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{ width: `${pct}%`, backgroundColor: color }}
              />
            </div>
          );
        })()}
      </div>

      <span className="w-px h-4 bg-border-subtle" />

      {/* Agent count + capability breakdown */}
      {swarm && (
        <>
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] font-mono text-text-muted">Agents</span>
            <span className="text-xs font-mono text-text-secondary">
              {activeWorkers}/{swarm.num_workers}
            </span>
            {capBreakdown && Object.keys(capBreakdown).length > 1 && (
              <span className="text-[10px] font-mono text-text-muted">
                ({Object.entries(capBreakdown).map(([k, v]) => {
                  const abbr: Record<string, string> = { lead: "L", builder: "B", reviewer: "R", merger: "M", scout: "S", coordinator: "C", monitor: "Mo" };
                  return `${v}${abbr[k] || k[0].toUpperCase()}`;
                }).join(" ")})
              </span>
            )}
            {stalledWorkers > 0 && (
              <span
                className="text-[10px] font-mono text-amber-400 bg-amber-500/10 px-1.5 py-0.5 rounded animate-pulse"
                title={`${stalledWorkers} stalled worker${stalledWorkers > 1 ? "s" : ""} detected`}
              >
                {stalledWorkers} stalled
              </span>
            )}
          </div>
          {/* Multi-runtime indicator */}
          {(() => {
            const workerRuntimes = new Set(
              swarm.workers
                .map((w) => (w as { runtime?: string }).runtime)
                .filter(Boolean)
            );
            // Also consider swarm-level runtime
            if (swarm.runtime) workerRuntimes.add(swarm.runtime);
            if (workerRuntimes.size > 1) {
              return (
                <span
                  className="text-[10px] font-mono px-1.5 py-0.5 rounded border border-purple-400/30 text-purple-400 bg-purple-400/5"
                  title={`Runtimes: ${[...workerRuntimes].join(", ")}`}
                >
                  Multi-Runtime
                </span>
              );
            }
            return null;
          })()}
          <span className="w-px h-4 bg-border-subtle" />
        </>
      )}

      {/* Phase badge */}
      {sessionStats?.current_phase && (
        <div
          className="flex items-center gap-1.5 px-2 py-0.5 rounded-full border border-border-subtle bg-surface"
          style={{
            borderColor: mode ? `var(--color-mode-${mode})` : undefined,
            color: mode ? `var(--color-mode-${mode})` : undefined,
          }}
        >
          <span className="text-[10px] font-mono font-medium">
            {sessionStats.current_phase}
          </span>
          <span className="text-[10px] font-mono text-text-muted">
            S{sessionStats.session_number}
          </span>
        </div>
      )}

      {/* Overrides indicator */}
      {(() => {
        const activeOvs = swarm?.overrides?.filter((o) => o.active) ?? [];
        if (activeOvs.length === 0) return null;
        return (
          <div
            className="flex items-center gap-1 px-1.5 py-0.5 rounded-full border border-info/30 bg-info/5"
            title={activeOvs.map((o) => o.value ? `${o.directive}=${o.value}` : o.directive).join(", ")}
          >
            <svg className="w-3 h-3 text-info" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M2 4h12M4 8h8M6 12h4" strokeLinecap="round" />
            </svg>
            <span className="text-[10px] font-mono text-info">
              {activeOvs.length}
            </span>
          </div>
        );
      })()}

      {/* Chain position badge - only show when chain has > 1 session */}
      {chainLength > 1 && (
        <>
          <span className="w-px h-4 bg-border-subtle" />
          <button
            onClick={onChainClick}
            className="flex items-center gap-1 px-1.5 py-0.5 rounded border border-border-subtle bg-surface hover:bg-surface-raised transition-colors"
            title={`Session chain: ${chainLength} sessions`}
          >
            <svg className="w-3 h-3 text-text-muted" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M4 4v8M8 2v12M12 6v4" strokeLinecap="round" />
            </svg>
            <span className="text-[10px] font-mono font-bold text-accent">
              S{chainLength}
            </span>
          </button>
        </>
      )}

      {/* Spacer */}
      <div className="flex-1" />

      {/* Monitor daemon indicator */}
      {monitorActive && (
        <div className="flex items-center gap-1.5" title="Monitor daemon is active">
          <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
          <span className="text-[10px] font-mono text-cyan-400">Monitor</span>
          {monitorFleetScore != null && (
            <span
              className="text-[10px] font-mono font-bold"
              style={{
                color: monitorFleetScore > 70 ? "#10B981" : monitorFleetScore > 40 ? "#F59E0B" : "#EF4444",
              }}
            >
              {monitorFleetScore}
            </span>
          )}
        </div>
      )}

      {/* Running indicator */}
      {status === "running" && (
        <div className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-accent)] animate-pulse" />
          <span className="text-[10px] font-mono text-[var(--color-accent)]">Live</span>
        </div>
      )}
    </div>
  );
}
