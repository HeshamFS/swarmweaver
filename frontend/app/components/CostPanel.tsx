"use client";

import { useState, useEffect, useRef } from "react";

/* ── Types ── */

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
  real_cost_usd: number;
  budget_limit_usd: number;
  max_hours: number;
  elapsed_hours: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cache_read_tokens: number;
  total_cache_write_tokens: number;
  total_api_duration_ms: number;
  total_lines_added: number;
  total_lines_removed: number;
  web_search_count: number;
  cache_efficiency: number;
  cost_display: string;
  model_usage: Record<string, {
    input: number;
    output: number;
    cache_read: number;
    cache_write: number;
    api_calls: number;
    api_duration_ms: number;
  }>;
}

interface CostSnapshot {
  timestamp: number;
  cost: number;
}

/* ── Constants ── */

const MODEL_COLORS: Record<string, string> = {
  opus: "#bc8cff",
  sonnet: "#3B82F6",
  haiku: "#10B981",
};

const MODEL_PRICES: Record<string, { input: number; output: number; cacheRead: number; cacheWrite: number }> = {
  "claude-opus-4-6": { input: 15.0, output: 75.0, cacheRead: 1.5, cacheWrite: 18.75 },
  "claude-sonnet-4-6": { input: 3.0, output: 15.0, cacheRead: 0.3, cacheWrite: 3.75 },
  "claude-sonnet-4-5-20250929": { input: 3.0, output: 15.0, cacheRead: 0.3, cacheWrite: 3.75 },
  "claude-haiku-4-5-20251001": { input: 0.8, output: 4.0, cacheRead: 0.08, cacheWrite: 1.0 },
};

function getModelColorKey(model: string): string {
  if (model.includes("opus")) return "opus";
  if (model.includes("haiku")) return "haiku";
  return "sonnet";
}

function getModelColor(model: string): string {
  return MODEL_COLORS[getModelColorKey(model)] || "#6E7B8B";
}

function getModelLabel(model: string): string {
  if (model.includes("opus")) return "Opus";
  if (model.includes("haiku")) return "Haiku";
  if (model.includes("sonnet-4-6")) return "Sonnet 4.6";
  if (model.includes("sonnet-4-5")) return "Sonnet 4.5";
  return model.split("-").slice(-2).join(" ");
}

function getBudgetColor(pct: number): string {
  if (pct >= 80) return "#EF4444";
  if (pct >= 50) return "#F59E0B";
  return "#10B981";
}

function formatCost(cost: number): string {
  if (cost >= 0.50) return `$${cost.toFixed(2)}`;
  return `$${cost.toFixed(4)}`;
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toLocaleString();
}

function formatDuration(ms: number): string {
  const sec = Math.floor(ms / 1000);
  if (sec < 60) return `${sec}s`;
  const min = Math.floor(sec / 60);
  const remSec = sec % 60;
  if (min < 60) return `${min}m ${remSec}s`;
  const hr = Math.floor(min / 60);
  const remMin = min % 60;
  return `${hr}h ${remMin}m`;
}

/* ── Sparkline ── */

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
          cx={((data.length - 1) / (data.length - 1)) * w}
          cy={h - (data[data.length - 1].cost / maxCost) * (h - 4) - 2}
          r="2.5"
          fill="#3B82F6"
        />
      )}
    </svg>
  );
}

/* ── Cache Efficiency Ring ── */

function CacheRing({ efficiency }: { efficiency: number }) {
  const pct = Math.round(efficiency * 100);
  const circumference = 2 * Math.PI * 18;
  const dashoffset = circumference - (circumference * pct) / 100;
  const color = pct >= 50 ? "#10B981" : pct >= 20 ? "#F59E0B" : "#EF4444";

  return (
    <div className="flex items-center gap-2">
      <svg width="44" height="44" viewBox="0 0 44 44">
        <circle cx="22" cy="22" r="18" fill="none" stroke="var(--color-border-subtle)" strokeWidth="3" />
        <circle
          cx="22" cy="22" r="18"
          fill="none"
          stroke={color}
          strokeWidth="3"
          strokeDasharray={circumference}
          strokeDashoffset={dashoffset}
          strokeLinecap="round"
          transform="rotate(-90 22 22)"
        />
        <text x="22" y="22" textAnchor="middle" dominantBaseline="central" fill={color} fontSize="11" fontFamily="monospace" fontWeight="bold">
          {pct}%
        </text>
      </svg>
      <div>
        <div className="text-[10px] text-text-muted font-mono">Cache hit</div>
        <div className="text-[10px] text-text-muted font-mono">rate</div>
      </div>
    </div>
  );
}

/* ── Main Component ── */

export function CostPanel({ projectDir, liveBudget }: { projectDir: string; liveBudget?: object | null }) {
  const [costData, setCostData] = useState<CostData | null>(null);
  const [agentCosts, setAgentCosts] = useState<AgentCost[]>([]);
  const [modelCosts, setModelCosts] = useState<ModelCost[]>([]);
  const [budgetStatus, setBudgetStatus] = useState<BudgetStatus | null>(null);
  const [taskCount, setTaskCount] = useState<number>(0);
  const [costHistory, setCostHistory] = useState<CostSnapshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [sortBy, setSortBy] = useState<"cost" | "tokens">("cost");
  const [activeTab, setActiveTab] = useState<"overview" | "models" | "agents">("overview");

  // Accept live budget data from parent (DetailDrawer polls every 15s)
  useEffect(() => {
    if (liveBudget && (liveBudget as Record<string, unknown>).total_input_tokens !== undefined) {
      setBudgetStatus(liveBudget as unknown as BudgetStatus);
      setLoading(false);
    }
  }, [liveBudget]);

  // Listen for budget_update WS events (real-time during execution)
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail?.type === "budget_update" && detail?.data) {
        const d = detail.data;
        if (d.estimated_cost_usd != null) {
          setCostHistory((prev) => {
            const next = [...prev, { timestamp: Date.now(), cost: d.estimated_cost_usd }];
            return next.length > 100 ? next.slice(-100) : next;
          });
        }
        // Live-update budget status from WS event
        setBudgetStatus((prev) => prev ? { ...prev, ...d } : d);
        setLoading(false);
      }
    };
    window.addEventListener("swarmweaver_ws_event", handler);
    return () => window.removeEventListener("swarmweaver_ws_event", handler);
  }, []);

  // Fetch detailed cost data and poll every 10s
  useEffect(() => {
    if (!projectDir) return;
    let cancelled = false;

    const fetchAll = () => {
      const enc = encodeURIComponent(projectDir);
      Promise.all([
        fetch(`/api/costs?path=${enc}`).then((r) => (r.ok ? r.json() : null)).catch(() => null),
        fetch(`/api/costs/by-agent?path=${enc}`).then((r) => (r.ok ? r.json() : null)).catch(() => null),
        fetch(`/api/costs/by-model?path=${enc}`).then((r) => (r.ok ? r.json() : null)).catch(() => null),
        fetch(`/api/budget?path=${enc}`).then((r) => (r.ok ? r.json() : null)).catch(() => null),
        fetch(`/api/tasks?path=${enc}`).then((r) => (r.ok ? r.json() : null)).catch(() => null),
      ]).then(([total, byAgent, byModel, budget, tasks]) => {
        if (cancelled) return;
        if (total) setCostData(total);
        if (byAgent) setAgentCosts(byAgent.agents || []);
        if (byModel) setModelCosts(byModel.models || []);
        if (budget && budget.total_input_tokens !== undefined) setBudgetStatus(budget);
        if (tasks) {
          const completed = Array.isArray(tasks) ? tasks.filter((t: { status?: string }) => t.status === "done").length : 0;
          setTaskCount(completed);
        }
        setLoading(false);
      });
    };

    fetchAll();
    const interval = setInterval(fetchAll, 10000);
    return () => { cancelled = true; clearInterval(interval); };
  }, [projectDir]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-32 text-xs text-text-muted">
        Analyzing costs...
      </div>
    );
  }

  if (!costData && !budgetStatus) {
    return (
      <div className="flex items-center justify-center h-32 text-xs text-text-muted">
        No cost data available.
      </div>
    );
  }

  const totalCost = budgetStatus?.estimated_cost_usd ?? costData?.total_cost ?? 0;
  const realCost = budgetStatus?.real_cost_usd ?? 0;
  const displayCost = realCost > 0 ? realCost : totalCost;
  const budgetLimit = budgetStatus?.budget_limit_usd ?? 0;
  const budgetPct = budgetLimit > 0 ? Math.min(100, (displayCost / budgetLimit) * 100) : 0;
  const costPerTask = taskCount > 0 ? displayCost / taskCount : 0;
  const cacheEfficiency = budgetStatus?.cache_efficiency ?? 0;

  // Build conic gradient for model breakdown
  let gradientParts: string[] = [];
  let accPct = 0;
  for (const m of modelCosts) {
    const color = getModelColor(m.model);
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

  // Tab button styling
  const tabCls = (tab: string) =>
    `px-2 py-1 text-[10px] font-mono transition-colors ${
      activeTab === tab
        ? "bg-accent/20 text-accent border-b-2 border-accent"
        : "text-text-muted hover:text-text-secondary"
    }`;

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Tab bar */}
      <div className="flex items-center border-b border-border-subtle bg-surface-raised shrink-0">
        <button onClick={() => setActiveTab("overview")} className={tabCls("overview")}>Overview</button>
        <button onClick={() => setActiveTab("models")} className={tabCls("models")}>Models</button>
        <button onClick={() => setActiveTab("agents")} className={tabCls("agents")}>Agents</button>
      </div>

      <div className="flex-1 overflow-y-auto min-h-0 p-3 space-y-4">
        {/* ── OVERVIEW TAB ── */}
        {activeTab === "overview" && (
          <>
            {/* Total cost hero */}
            <div className="text-center">
              <div className="text-3xl font-mono font-bold text-text-primary">
                {formatCost(displayCost)}
              </div>
              <div className="text-xs text-text-muted mt-1">
                {realCost > 0 ? "Actual cost (SDK-reported)" : "Estimated cost"}
              </div>
              {realCost > 0 && totalCost > 0 && Math.abs(realCost - totalCost) > 0.001 && (
                <div className="text-[10px] text-text-muted mt-0.5">
                  Estimated: {formatCost(totalCost)}
                </div>
              )}
            </div>

            {/* Budget Efficiency */}
            {budgetLimit > 0 && (
              <div>
                <h3 className="text-[10px] font-mono text-text-muted uppercase tracking-wider mb-2">
                  Budget
                </h3>
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-[10px] font-mono">
                    <span className="text-text-secondary">{formatCost(displayCost)} / {formatCost(budgetLimit)}</span>
                    <span style={{ color: getBudgetColor(budgetPct) }}>{budgetPct.toFixed(0)}%</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-surface-raised overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all duration-500"
                      style={{ width: `${budgetPct}%`, backgroundColor: getBudgetColor(budgetPct) }}
                    />
                  </div>
                </div>
              </div>
            )}

            {/* Token breakdown (4-cell grid) */}
            <div>
              <h3 className="text-[10px] font-mono text-text-muted uppercase tracking-wider mb-2">
                Token Breakdown
              </h3>
              <div className="grid grid-cols-2 gap-2">
                <div className="rounded-lg border border-border-subtle bg-surface p-2 text-center">
                  <div className="text-sm font-mono text-text-primary">
                    {formatTokens(budgetStatus?.total_input_tokens ?? costData?.token_breakdown?.input ?? 0)}
                  </div>
                  <div className="text-[10px] text-text-muted">Input</div>
                </div>
                <div className="rounded-lg border border-border-subtle bg-surface p-2 text-center">
                  <div className="text-sm font-mono text-text-primary">
                    {formatTokens(budgetStatus?.total_output_tokens ?? costData?.token_breakdown?.output ?? 0)}
                  </div>
                  <div className="text-[10px] text-text-muted">Output</div>
                </div>
                <div className="rounded-lg border border-border-subtle bg-surface p-2 text-center">
                  <div className="text-sm font-mono text-info">
                    {formatTokens(budgetStatus?.total_cache_read_tokens ?? costData?.token_breakdown?.cache_read ?? 0)}
                  </div>
                  <div className="text-[10px] text-text-muted">Cache Read</div>
                </div>
                <div className="rounded-lg border border-border-subtle bg-surface p-2 text-center">
                  <div className="text-sm font-mono text-warning">
                    {formatTokens(budgetStatus?.total_cache_write_tokens ?? costData?.token_breakdown?.cache_creation ?? 0)}
                  </div>
                  <div className="text-[10px] text-text-muted">Cache Write</div>
                </div>
              </div>
            </div>

            {/* Cache efficiency + metrics row */}
            <div className="flex items-center gap-4">
              <CacheRing efficiency={cacheEfficiency} />
              <div className="flex-1 space-y-1.5">
                <div className="flex items-center justify-between text-[10px] font-mono">
                  <span className="text-text-muted">Cost/task</span>
                  <span className="text-text-secondary">
                    {taskCount > 0 ? `${formatCost(costPerTask)} (${taskCount} done)` : "—"}
                  </span>
                </div>
                <div className="flex items-center justify-between text-[10px] font-mono">
                  <span className="text-text-muted">API time</span>
                  <span className="text-text-secondary">
                    {budgetStatus?.total_api_duration_ms ? formatDuration(budgetStatus.total_api_duration_ms) : "—"}
                  </span>
                </div>
                <div className="flex items-center justify-between text-[10px] font-mono">
                  <span className="text-text-muted">Searches</span>
                  <span className="text-text-secondary">
                    {budgetStatus?.web_search_count ?? 0}
                  </span>
                </div>
              </div>
            </div>

            {/* Code changes */}
            {(budgetStatus?.total_lines_added ?? 0) + (budgetStatus?.total_lines_removed ?? 0) > 0 && (
              <div>
                <h3 className="text-[10px] font-mono text-text-muted uppercase tracking-wider mb-2">
                  Code Changes
                </h3>
                <div className="flex items-center gap-4">
                  <div className="flex items-center gap-1.5">
                    <span className="text-success text-sm font-mono font-bold">+{(budgetStatus?.total_lines_added ?? 0).toLocaleString()}</span>
                    <span className="text-[10px] text-text-muted">added</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="text-error text-sm font-mono font-bold">-{(budgetStatus?.total_lines_removed ?? 0).toLocaleString()}</span>
                    <span className="text-[10px] text-text-muted">removed</span>
                  </div>
                </div>
              </div>
            )}

            {/* Cost sparkline */}
            {costHistory.length >= 2 && (
              <div className="rounded-md border border-border-subtle bg-surface p-1.5">
                <div className="text-[10px] font-mono text-text-muted mb-1">Cost over time</div>
                <CostSparkline data={costHistory} />
              </div>
            )}
          </>
        )}

        {/* ── MODELS TAB ── */}
        {activeTab === "models" && (
          <>
            {/* Pie chart + legend */}
            {modelCosts.length > 0 && (
              <div className="flex items-center gap-4">
                <div
                  className="w-20 h-20 rounded-full shrink-0"
                  style={{ background: conicGradient }}
                />
                <div className="space-y-1.5">
                  {modelCosts.map((m) => (
                    <div key={m.model} className="flex items-center gap-2">
                      <span
                        className="w-2 h-2 rounded-full shrink-0"
                        style={{ backgroundColor: getModelColor(m.model) }}
                      />
                      <span className="text-xs font-mono text-text-primary">{getModelLabel(m.model)}</span>
                      <span className="text-xs font-mono text-text-secondary">{formatCost(m.cost)}</span>
                      <span className="text-[10px] text-text-muted">({m.percentage.toFixed(1)}%)</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Per-model detailed breakdown */}
            {budgetStatus?.model_usage && Object.keys(budgetStatus.model_usage).length > 0 && (
              <div className="space-y-3">
                <h3 className="text-[10px] font-mono text-text-muted uppercase tracking-wider">
                  Detailed Breakdown
                </h3>
                {Object.entries(budgetStatus.model_usage).map(([model, usage]) => {
                  const prices = MODEL_PRICES[model] || MODEL_PRICES["claude-sonnet-4-6"];
                  const inputCost = (usage.input * prices.input) / 1_000_000;
                  const outputCost = (usage.output * prices.output) / 1_000_000;
                  const cacheReadCost = (usage.cache_read * prices.cacheRead) / 1_000_000;
                  const cacheWriteCost = (usage.cache_write * prices.cacheWrite) / 1_000_000;
                  const modelTotal = inputCost + outputCost + cacheReadCost + cacheWriteCost;

                  return (
                    <div key={model} className="rounded-lg border border-border-subtle bg-surface p-2.5 space-y-2">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span
                            className="w-2 h-2 rounded-full"
                            style={{ backgroundColor: getModelColor(model) }}
                          />
                          <span className="text-xs font-mono font-medium text-text-primary">
                            {getModelLabel(model)}
                          </span>
                        </div>
                        <span className="text-xs font-mono text-text-primary font-bold">
                          {formatCost(modelTotal)}
                        </span>
                      </div>
                      <table className="w-full text-[10px] font-mono">
                        <tbody>
                          <tr className="border-b border-border-subtle/30">
                            <td className="py-0.5 text-text-muted">Input</td>
                            <td className="py-0.5 text-right text-text-secondary">{formatTokens(usage.input)}</td>
                            <td className="py-0.5 text-right text-text-muted w-16">{formatCost(inputCost)}</td>
                          </tr>
                          <tr className="border-b border-border-subtle/30">
                            <td className="py-0.5 text-text-muted">Output</td>
                            <td className="py-0.5 text-right text-text-secondary">{formatTokens(usage.output)}</td>
                            <td className="py-0.5 text-right text-text-muted w-16">{formatCost(outputCost)}</td>
                          </tr>
                          <tr className="border-b border-border-subtle/30">
                            <td className="py-0.5 text-info">Cache Read</td>
                            <td className="py-0.5 text-right text-text-secondary">{formatTokens(usage.cache_read)}</td>
                            <td className="py-0.5 text-right text-text-muted w-16">{formatCost(cacheReadCost)}</td>
                          </tr>
                          <tr>
                            <td className="py-0.5 text-warning">Cache Write</td>
                            <td className="py-0.5 text-right text-text-secondary">{formatTokens(usage.cache_write)}</td>
                            <td className="py-0.5 text-right text-text-muted w-16">{formatCost(cacheWriteCost)}</td>
                          </tr>
                        </tbody>
                      </table>
                      {usage.api_calls > 0 && (
                        <div className="flex items-center justify-between text-[10px] font-mono pt-1 border-t border-border-subtle/30">
                          <span className="text-text-muted">{usage.api_calls} API calls</span>
                          <span className="text-text-muted">{formatDuration(usage.api_duration_ms)}</span>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </>
        )}

        {/* ── AGENTS TAB ── */}
        {activeTab === "agents" && (
          <>
            {agentCosts.length > 0 ? (
              <div>
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-[10px] font-mono text-text-muted uppercase tracking-wider">
                    Cost by Agent
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
                  {sortedAgents.map((a) => {
                    const maxCost = Math.max(...agentCosts.map((x) => x.cost), 0.001);
                    const barPct = (a.cost / maxCost) * 100;
                    return (
                      <div key={a.agent} className="space-y-1">
                        <div className="flex items-center justify-between rounded-md px-2 py-1 hover:bg-surface-raised/50">
                          <span className="text-xs font-mono text-text-primary">{a.agent}</span>
                          <div className="flex items-center gap-3">
                            <span className="text-xs font-mono text-text-secondary">{formatCost(a.cost)}</span>
                            <span className="text-[10px] font-mono text-text-muted">{formatTokens(a.tokens)} tok</span>
                          </div>
                        </div>
                        <div className="h-1 rounded-full bg-surface-raised overflow-hidden mx-2">
                          <div
                            className="h-full rounded-full bg-accent/40 transition-all"
                            style={{ width: `${barPct}%` }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : (
              <div className="flex items-center justify-center h-20 text-xs text-text-muted">
                No agent cost data yet.
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
