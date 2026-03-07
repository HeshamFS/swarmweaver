"use client";

import { useState, useEffect, useRef, useCallback } from "react";

interface CostData {
  total_cost: number;
  token_breakdown: {
    input: number;
    output: number;
    cache_read: number;
    cache_creation: number;
  };
}

interface AgentCost {
  agent: string;
  cost: number;
  tokens: number;
}

interface ModelCost {
  model: string;
  cost: number;
  tokens: number;
  percentage: number;
}

interface BudgetStatus {
  estimated_cost_usd: number;
  budget_limit_usd: number;
  max_hours: number;
  elapsed_hours: number;
}

interface CostSnapshot {
  timestamp: number;
  cost: number;
}

const MODEL_COLORS: Record<string, string> = {
  opus: "#bc8cff",
  sonnet: "#3B82F6",
  haiku: "#10B981",
};

function getBudgetColor(pct: number): string {
  if (pct >= 80) return "#EF4444";
  if (pct >= 50) return "#F59E0B";
  return "#10B981";
}

function CostSparkline({ data }: { data: CostSnapshot[] }) {
  if (data.length < 2) return null;
  const maxCost = Math.max(...data.map((d) => d.cost), 0.001);
  const w = 200;
  const h = 40;
  const points = data.map((d, i) => {
    const x = (i / (data.length - 1)) * w;
    const y = h - (d.cost / maxCost) * (h - 4) - 2;
    return `${x},${y}`;
  });
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-10" preserveAspectRatio="none">
      <polyline
        points={points.join(" ")}
        fill="none"
        stroke="#3B82F6"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      {data.length > 0 && (
        <circle
          cx={(data.length - 1) / (data.length - 1) * w}
          cy={h - (data[data.length - 1].cost / maxCost) * (h - 4) - 2}
          r="2.5"
          fill="#3B82F6"
        />
      )}
    </svg>
  );
}

export function CostPanel({ projectDir }: { projectDir: string }) {
  const [costData, setCostData] = useState<CostData | null>(null);
  const [agentCosts, setAgentCosts] = useState<AgentCost[]>([]);
  const [modelCosts, setModelCosts] = useState<ModelCost[]>([]);
  const [budgetStatus, setBudgetStatus] = useState<BudgetStatus | null>(null);
  const [taskCount, setTaskCount] = useState<number>(0);
  const [costHistory, setCostHistory] = useState<CostSnapshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [sortBy, setSortBy] = useState<"cost" | "tokens">("cost");
  const wsListenerRef = useRef(false);

  // Listen for budget_update WS events to build cost history
  useEffect(() => {
    if (wsListenerRef.current) return;
    wsListenerRef.current = true;

    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail?.type === "budget_update" && detail?.data?.estimated_cost_usd != null) {
        setCostHistory((prev) => {
          const next = [...prev, { timestamp: Date.now(), cost: detail.data.estimated_cost_usd }];
          return next.length > 100 ? next.slice(-100) : next;
        });
      }
    };
    window.addEventListener("swarmweaver_ws_event", handler);
    return () => {
      window.removeEventListener("swarmweaver_ws_event", handler);
      wsListenerRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (!projectDir) return;
    setLoading(true);
    const enc = encodeURIComponent(projectDir);

    Promise.all([
      fetch(`/api/costs?path=${enc}`).then((r) => (r.ok ? r.json() : null)).catch(() => null),
      fetch(`/api/costs/by-agent?path=${enc}`).then((r) => (r.ok ? r.json() : null)).catch(() => null),
      fetch(`/api/costs/by-model?path=${enc}`).then((r) => (r.ok ? r.json() : null)).catch(() => null),
      fetch(`/api/budget?path=${enc}`).then((r) => (r.ok ? r.json() : null)).catch(() => null),
      fetch(`/api/tasks?path=${enc}`).then((r) => (r.ok ? r.json() : null)).catch(() => null),
    ]).then(([total, byAgent, byModel, budget, tasks]) => {
      if (total) setCostData(total);
      if (byAgent) setAgentCosts(byAgent.agents || []);
      if (byModel) setModelCosts(byModel.models || []);
      if (budget) setBudgetStatus(budget);
      if (tasks) {
        const completed = Array.isArray(tasks) ? tasks.filter((t: { status?: string }) => t.status === "done").length : 0;
        setTaskCount(completed);
      }
    }).finally(() => setLoading(false));
  }, [projectDir]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-32 text-xs text-text-muted">
        Analyzing costs...
      </div>
    );
  }

  if (!costData) {
    return (
      <div className="flex items-center justify-center h-32 text-xs text-text-muted">
        No cost data available.
      </div>
    );
  }

  // Build conic gradient for model breakdown
  let gradientParts: string[] = [];
  let accPct = 0;
  for (const m of modelCosts) {
    const color = MODEL_COLORS[m.model] || "#6E7B8B";
    const start = accPct;
    const end = accPct + m.percentage;
    gradientParts.push(`${color} ${start}% ${end}%`);
    accPct = end;
  }
  if (accPct < 100) {
    gradientParts.push(`#21262D ${accPct}% 100%`);
  }
  const conicGradient = `conic-gradient(${gradientParts.join(", ")})`;

  const sortedAgents = [...agentCosts].sort((a, b) =>
    sortBy === "cost" ? b.cost - a.cost : b.tokens - a.tokens
  );

  const budgetLimit = budgetStatus?.budget_limit_usd ?? 0;
  const budgetSpent = budgetStatus?.estimated_cost_usd ?? costData?.total_cost ?? 0;
  const budgetPct = budgetLimit > 0 ? Math.min(100, (budgetSpent / budgetLimit) * 100) : 0;
  const costPerTask = taskCount > 0 ? budgetSpent / taskCount : 0;

  return (
    <div className="overflow-y-auto h-full p-3 space-y-4">
      {/* Total cost */}
      <div className="text-center">
        <div className="text-3xl font-mono font-bold text-text-primary">
          ${costData.total_cost.toFixed(4)}
        </div>
        <div className="text-xs text-text-muted mt-1">Total estimated cost</div>
      </div>

      {/* Budget Efficiency */}
      <div>
        <h3 className="text-[10px] font-mono text-text-muted uppercase tracking-wider mb-2">
          Budget Efficiency
        </h3>
        {budgetLimit > 0 ? (
          <div className="space-y-2">
            {/* Budget bar */}
            <div className="flex items-center justify-between text-[10px] font-mono">
              <span className="text-text-secondary">${budgetSpent.toFixed(2)} / ${budgetLimit.toFixed(2)}</span>
              <span style={{ color: getBudgetColor(budgetPct) }}>{budgetPct.toFixed(0)}%</span>
            </div>
            <div className="h-1.5 rounded-full bg-surface-raised overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{
                  width: `${budgetPct}%`,
                  backgroundColor: getBudgetColor(budgetPct),
                }}
              />
            </div>
          </div>
        ) : (
          <div className="text-[10px] text-text-muted font-mono">No budget limit</div>
        )}

        {/* Cost per task */}
        <div className="flex items-center justify-between mt-2 text-[10px] font-mono">
          <span className="text-text-muted">Cost/task</span>
          <span className="text-text-secondary">
            {taskCount > 0 ? `$${costPerTask.toFixed(4)} (${taskCount} done)` : "No tasks completed"}
          </span>
        </div>

        {/* Cost sparkline */}
        {costHistory.length >= 2 && (
          <div className="mt-2 rounded-md border border-border-subtle bg-surface p-1.5">
            <div className="text-[10px] font-mono text-text-muted mb-1">Cost over time</div>
            <CostSparkline data={costHistory} />
          </div>
        )}
      </div>

      {/* Token counts */}
      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-lg border border-border-subtle bg-surface p-2 text-center">
          <div className="text-sm font-mono text-text-primary">
            {(costData.token_breakdown?.input ?? 0).toLocaleString()}
          </div>
          <div className="text-[10px] text-text-muted">Input</div>
        </div>
        <div className="rounded-lg border border-border-subtle bg-surface p-2 text-center">
          <div className="text-sm font-mono text-text-primary">
            {(costData.token_breakdown?.output ?? 0).toLocaleString()}
          </div>
          <div className="text-[10px] text-text-muted">Output</div>
        </div>
      </div>

      {/* Model breakdown with pie chart */}
      {modelCosts.length > 0 && (
        <div>
          <h3 className="text-[10px] font-mono text-text-muted uppercase tracking-wider mb-2">
            By Model
          </h3>
          <div className="flex items-center gap-4">
            {/* Conic gradient pie */}
            <div
              className="w-16 h-16 rounded-full shrink-0"
              style={{ background: conicGradient }}
            />
            <div className="space-y-1">
              {modelCosts.map((m) => (
                <div key={m.model} className="flex items-center gap-2">
                  <span
                    className="w-2 h-2 rounded-full shrink-0"
                    style={{ backgroundColor: MODEL_COLORS[m.model] || "#6E7B8B" }}
                  />
                  <span className="text-xs font-mono text-text-primary w-14">{m.model}</span>
                  <span className="text-xs font-mono text-text-secondary">${m.cost.toFixed(4)}</span>
                  <span className="text-[10px] text-text-muted">({m.percentage.toFixed(1)}%)</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* By Runtime grouping */}
      {modelCosts.length > 0 && (() => {
        // Group model costs by runtime (derive from model name prefix)
        const runtimeMap: Record<string, { cost: number; tokens: number; models: string[] }> = {};
        for (const m of modelCosts) {
          // All current models are Claude; future runtimes will have different prefixes
          const rt = m.model.startsWith("claude") ? "Claude" : m.model.split("-")[0] || "Unknown";
          if (!runtimeMap[rt]) runtimeMap[rt] = { cost: 0, tokens: 0, models: [] };
          runtimeMap[rt].cost += m.cost;
          runtimeMap[rt].tokens += m.tokens;
          if (!runtimeMap[rt].models.includes(m.model)) runtimeMap[rt].models.push(m.model);
        }
        const entries = Object.entries(runtimeMap);
        // Only show section if there are multiple runtimes or for completeness
        return (
          <div>
            <h3 className="text-[10px] font-mono text-text-muted uppercase tracking-wider mb-2">
              By Runtime
            </h3>
            <div className="space-y-1">
              {entries.map(([rt, data]) => (
                <div key={rt} className="flex items-center justify-between rounded-md px-2 py-1 hover:bg-surface-raised/50">
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full shrink-0 bg-accent" />
                    <span className="text-xs font-mono text-text-primary">{rt}</span>
                    <span className="text-[10px] font-mono text-text-muted">
                      ({data.models.length} model{data.models.length !== 1 ? "s" : ""})
                    </span>
                  </div>
                  <span className="text-xs font-mono text-text-secondary">${data.cost.toFixed(4)}</span>
                </div>
              ))}
            </div>
          </div>
        );
      })()}

      {/* Per-agent table */}
      {agentCosts.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-[10px] font-mono text-text-muted uppercase tracking-wider">
              By Agent
            </h3>
            <div className="flex rounded-md border border-border-subtle overflow-hidden">
              <button
                onClick={() => setSortBy("cost")}
                className={`px-1.5 py-0.5 text-[10px] font-mono transition-colors ${
                  sortBy === "cost" ? "bg-accent/20 text-accent" : "text-text-muted"
                }`}
              >
                Cost
              </button>
              <button
                onClick={() => setSortBy("tokens")}
                className={`px-1.5 py-0.5 text-[10px] font-mono transition-colors ${
                  sortBy === "tokens" ? "bg-accent/20 text-accent" : "text-text-muted"
                }`}
              >
                Tokens
              </button>
            </div>
          </div>
          <div className="space-y-1">
            {sortedAgents.map((a) => (
              <div key={a.agent} className="flex items-center justify-between rounded-md px-2 py-1 hover:bg-surface-raised/50">
                <span className="text-xs font-mono text-text-primary">{a.agent}</span>
                <div className="flex items-center gap-3">
                  <span className="text-xs font-mono text-text-secondary">${a.cost.toFixed(4)}</span>
                  <span className="text-[10px] font-mono text-text-muted">{a.tokens.toLocaleString()} tok</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
