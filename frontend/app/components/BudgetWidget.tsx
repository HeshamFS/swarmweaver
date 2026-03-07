"use client";

import { useState, useEffect } from "react";

interface BudgetData {
  total_cost: number;
  budget_limit: number | null;
  tokens_used: number;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_creation_tokens: number;
  circuit_breaker_enabled: boolean;
  circuit_breaker_threshold: number | null;
}

export function BudgetWidget({ projectDir }: { projectDir: string }) {
  const [budget, setBudget] = useState<BudgetData | null>(null);
  const [loading, setLoading] = useState(true);
  const [showSettings, setShowSettings] = useState(false);
  const [newLimit, setNewLimit] = useState("");
  const [newCircuitBreaker, setNewCircuitBreaker] = useState("");

  useEffect(() => {
    if (!projectDir) return;
    setLoading(true);
    const enc = encodeURIComponent(projectDir);

    const poll = () => {
      fetch(`/api/budget?path=${enc}`)
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => {
          if (d) {
            setBudget(d);
            if (d.budget_limit != null) setNewLimit(String(d.budget_limit));
            if (d.circuit_breaker_threshold != null) setNewCircuitBreaker(String(d.circuit_breaker_threshold));
          }
        })
        .catch(() => {})
        .finally(() => setLoading(false));
    };

    poll();
    const interval = setInterval(poll, 15000);
    return () => clearInterval(interval);
  }, [projectDir]);

  const handleUpdateBudget = async () => {
    try {
      await fetch("/api/budget/update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          path: projectDir,
          budget_limit: newLimit ? parseFloat(newLimit) : null,
          circuit_breaker_threshold: newCircuitBreaker ? parseFloat(newCircuitBreaker) : null,
        }),
      });
      setShowSettings(false);
      // Refresh
      const enc = encodeURIComponent(projectDir);
      const res = await fetch(`/api/budget?path=${enc}`);
      if (res.ok) setBudget(await res.json());
    } catch {
      // Ignore
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-32 text-xs text-text-muted">
        Loading budget...
      </div>
    );
  }

  if (!budget) {
    return (
      <div className="flex items-center justify-center h-32 text-xs text-text-muted">
        No budget data available.
      </div>
    );
  }

  const totalCost = budget.total_cost ?? 0;
  const budgetLimit = budget.budget_limit ?? null;
  const budgetPercent = budgetLimit
    ? Math.min((totalCost / budgetLimit) * 100, 100)
    : 0;
  const isOverBudget = budgetLimit != null && totalCost >= budgetLimit;

  return (
    <div className="overflow-y-auto h-full p-3 space-y-4">
      {/* Cost display */}
      <div className="text-center">
        <div className={`text-2xl font-mono font-bold ${isOverBudget ? "text-error" : "text-text-primary"}`}>
          ${totalCost.toFixed(4)}
        </div>
        {budgetLimit != null && (
          <>
            <div className="text-xs text-text-muted font-mono mt-1">
              of ${budgetLimit.toFixed(2)} budget
            </div>
            <div className="mt-2 h-2 rounded-full bg-border-subtle overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${
                  budgetPercent > 90 ? "bg-error" : budgetPercent > 70 ? "bg-warning" : "bg-success"
                }`}
                style={{ width: `${budgetPercent}%` }}
              />
            </div>
          </>
        )}
      </div>

      {/* Token breakdown */}
      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-lg border border-border-subtle bg-surface p-2 text-center">
          <div className="text-xs font-mono text-text-primary">{(budget.input_tokens ?? 0).toLocaleString()}</div>
          <div className="text-[10px] text-text-muted">Input tokens</div>
        </div>
        <div className="rounded-lg border border-border-subtle bg-surface p-2 text-center">
          <div className="text-xs font-mono text-text-primary">{(budget.output_tokens ?? 0).toLocaleString()}</div>
          <div className="text-[10px] text-text-muted">Output tokens</div>
        </div>
        <div className="rounded-lg border border-border-subtle bg-surface p-2 text-center">
          <div className="text-xs font-mono text-text-primary">{(budget.cache_read_tokens ?? 0).toLocaleString()}</div>
          <div className="text-[10px] text-text-muted">Cache read</div>
        </div>
        <div className="rounded-lg border border-border-subtle bg-surface p-2 text-center">
          <div className="text-xs font-mono text-text-primary">{(budget.cache_creation_tokens ?? 0).toLocaleString()}</div>
          <div className="text-[10px] text-text-muted">Cache write</div>
        </div>
      </div>

      {/* Settings */}
      <button
        onClick={() => setShowSettings(!showSettings)}
        className="w-full text-xs font-mono text-accent hover:text-accent-hover transition-colors py-1"
      >
        {showSettings ? "Hide Settings" : "Budget Settings"}
      </button>

      {showSettings && (
        <div className="space-y-2 rounded-lg border border-border-subtle bg-surface p-3">
          <div>
            <label className="text-[10px] text-text-muted font-mono block mb-1">
              Budget Limit ($)
            </label>
            <input
              type="number"
              step="0.01"
              value={newLimit}
              onChange={(e) => setNewLimit(e.target.value)}
              placeholder="No limit"
              className="w-full rounded-md border border-border-subtle bg-surface-raised px-2 py-1 text-xs text-text-primary placeholder:text-text-muted"
            />
          </div>
          <div>
            <label className="text-[10px] text-text-muted font-mono block mb-1">
              Circuit Breaker Threshold ($)
            </label>
            <input
              type="number"
              step="0.01"
              value={newCircuitBreaker}
              onChange={(e) => setNewCircuitBreaker(e.target.value)}
              placeholder="No threshold"
              className="w-full rounded-md border border-border-subtle bg-surface-raised px-2 py-1 text-xs text-text-primary placeholder:text-text-muted"
            />
          </div>
          <button
            onClick={handleUpdateBudget}
            className="w-full rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-white hover:bg-accent-hover transition-colors"
          >
            Save
          </button>
        </div>
      )}
    </div>
  );
}
