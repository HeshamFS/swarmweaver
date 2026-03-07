"use client";

import { useState, useEffect } from "react";

interface StatusStripProps {
  projectDir: string;
  activeDrawerTab: string | null;
  onDrawerTabChange: (tab: string | null) => void;
  drawerTabs: { key: string; label: string; icon: string }[];
}

interface HealthStatus {
  overall: "pass" | "warn" | "fail";
  passed: number;
  warned: number;
  failed: number;
}

interface BudgetInfo {
  total_cost: number;
  budget_limit: number | null;
  tokens_used: number;
}

interface SwarmInfo {
  num_workers: number;
  workers: { status: string }[];
}

const HEALTH_DOT: Record<string, string> = {
  pass: "bg-success",
  warn: "bg-warning animate-pulse",
  fail: "bg-error animate-pulse",
};

export function StatusStrip({
  projectDir,
  activeDrawerTab,
  onDrawerTabChange,
  drawerTabs,
}: StatusStripProps) {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [budget, setBudget] = useState<BudgetInfo | null>(null);
  const [swarm, setSwarm] = useState<SwarmInfo | null>(null);

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
        .then((d) => { if (d) setSwarm(d); })
        .catch(() => {});
    };

    poll();
    const interval = setInterval(poll, 10000);
    return () => clearInterval(interval);
  }, [projectDir]);

  const activeWorkers = swarm?.workers?.filter((w) => w.status === "working").length ?? 0;

  return (
    <div className="flex items-center h-8 px-3 border-t border-b border-border-subtle bg-surface-raised/60 backdrop-blur-sm gap-3 shrink-0 z-10">
      {/* Health dot */}
      <div className="flex items-center gap-1.5" title={health ? `Health: ${health.overall}` : "Health: unknown"}>
        <span className={`w-2 h-2 rounded-full ${health ? HEALTH_DOT[health.overall] : "bg-text-muted"}`} />
        <span className="text-[10px] font-mono text-text-muted">
          {health ? health.overall : "--"}
        </span>
      </div>

      {/* Separator */}
      <span className="w-px h-3 bg-border-subtle" />

      {/* Cost */}
      <div className="flex items-center gap-1" title={budget ? `Budget: $${(budget.total_cost ?? 0).toFixed(4)}` : "Cost: unknown"}>
        <span className="text-[10px] font-mono text-text-muted">$</span>
        <span className="text-[10px] font-mono text-text-secondary">
          {(budget?.total_cost ?? 0).toFixed(3)}
        </span>
        {budget?.budget_limit != null && budget.budget_limit > 0 && (
          <span className="text-[10px] font-mono text-text-muted">
            / ${(budget.budget_limit ?? 0).toFixed(2)}
          </span>
        )}
      </div>

      {/* Separator */}
      <span className="w-px h-3 bg-border-subtle" />

      {/* Agent count */}
      {swarm && swarm.num_workers > 0 && (
        <>
          <div className="flex items-center gap-1" title={`${swarm.num_workers} workers, ${activeWorkers} active`}>
            <span className="text-[10px] font-mono text-text-muted">Agents:</span>
            <span className="text-[10px] font-mono text-text-secondary">
              {activeWorkers}/{swarm.num_workers}
            </span>
          </div>
          <span className="w-px h-3 bg-border-subtle" />
        </>
      )}

      {/* Spacer */}
      <div className="flex-1" />

      {/* Drawer tab icons */}
      <div className="flex items-center gap-0.5">
        {drawerTabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => onDrawerTabChange(activeDrawerTab === tab.key ? null : tab.key)}
            className={`px-1.5 py-0.5 text-[10px] font-mono rounded transition-colors ${
              activeDrawerTab === tab.key
                ? "text-accent bg-accent/15"
                : "text-text-muted hover:text-text-secondary hover:bg-surface-overlay/50"
            }`}
            title={tab.label}
          >
            {tab.icon}
          </button>
        ))}
      </div>
    </div>
  );
}
