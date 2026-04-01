"use client";

import { useState, useEffect, useCallback } from "react";

interface GateStatus {
  threshold_hours?: number;
  hours_since_last?: number;
  passed?: boolean;
  threshold?: number;
  current?: number;
  locked?: boolean;
}

interface DreamStatus {
  enabled: boolean;
  time_gate: GateStatus;
  session_gate: GateStatus;
  lock_gate: GateStatus;
  last_run: string;
  history: Array<{
    timestamp: string;
    existing_records: number;
    new_learnings: number;
    consolidated: number;
    pruned: number;
    duration_seconds: number;
    stages_completed: string[];
    error?: string;
  }>;
}

interface DreamPanelProps {
  projectDir: string;
}

export function DreamPanel({ projectDir }: DreamPanelProps) {
  const [status, setStatus] = useState<DreamStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);
  const [triggerResult, setTriggerResult] = useState<string | null>(null);

  const fetchStatus = useCallback(() => {
    if (!projectDir) return;
    fetch(`/api/dream/status?path=${encodeURIComponent(projectDir)}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (d?.gates) setStatus(d.gates); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [projectDir]);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 15000);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  const handleTrigger = async () => {
    setTriggering(true);
    setTriggerResult(null);
    try {
      const res = await fetch(
        `http://localhost:8000/api/dream/trigger?path=${encodeURIComponent(projectDir)}`,
        { method: "POST" }
      );
      const data = await res.json();
      if (data.result) {
        setTriggerResult(
          `Done: ${data.result.consolidated} consolidated, ${data.result.pruned} pruned (${data.result.duration_seconds}s)`
        );
        fetchStatus();
      }
    } catch {
      setTriggerResult("Failed to trigger");
    }
    setTriggering(false);
    setTimeout(() => setTriggerResult(null), 5000);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-32">
        <span className="text-xs font-mono text-[#555]">Loading dream status...</span>
      </div>
    );
  }

  const gateItems = [
    {
      label: "Feature",
      passed: status?.enabled ?? false,
      detail: status?.enabled ? "Enabled" : "Disabled",
    },
    {
      label: "Time Gate",
      passed: status?.time_gate?.passed ?? false,
      detail: `${status?.time_gate?.hours_since_last ?? 0}h / ${status?.time_gate?.threshold_hours ?? 24}h`,
    },
    {
      label: "Sessions",
      passed: status?.session_gate?.passed ?? false,
      detail: `${status?.session_gate?.current ?? 0} / ${status?.session_gate?.threshold ?? 5}`,
    },
    {
      label: "Lock",
      passed: !(status?.lock_gate?.locked ?? false),
      detail: status?.lock_gate?.locked ? "Locked" : "Available",
    },
  ];

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-2.5 border-b border-[#222] bg-[#0C0C0C] shrink-0 flex items-center justify-between">
        <span className="text-xs font-mono font-medium text-[#E0E0E0] uppercase tracking-wider">Memory Consolidation</span>
        <button
          onClick={handleTrigger}
          disabled={triggering}
          className="text-[10px] font-mono font-bold px-2 py-0.5 bg-[var(--color-accent)] text-[#0C0C0C] hover:brightness-110 disabled:opacity-50"
        >
          {triggering ? "Running..." : "Trigger Now"}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto min-h-0 px-4 py-3 space-y-4">
        {triggerResult && (
          <div className={`text-[10px] font-mono p-2 border ${triggerResult.startsWith("Done") ? "text-[#10B981] border-[#10B981]/30 bg-[#10B981]/10" : "text-[#EF4444] border-[#EF4444]/30 bg-[#EF4444]/10"}`}>
            {triggerResult}
          </div>
        )}

        {/* Gates */}
        <div>
          <div className="text-[10px] font-mono text-[#555] uppercase tracking-wider mb-2">Trigger Gates</div>
          <div className="space-y-1">
            {gateItems.map((gate) => (
              <div key={gate.label} className="flex items-center gap-2 px-2 py-1.5 bg-[#121212] border border-[#222]">
                <span className={`w-2 h-2 rounded-full ${gate.passed ? "bg-[#10B981]" : "bg-[#EF4444]"}`} />
                <span className="text-xs font-mono text-[#E0E0E0] flex-1">{gate.label}</span>
                <span className="text-[10px] font-mono text-[#555]">{gate.detail}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Last run */}
        {status?.last_run && (
          <div className="flex items-center justify-between text-[10px] font-mono">
            <span className="text-[#555]">Last run</span>
            <span className="text-[#888]">{new Date(status.last_run).toLocaleString()}</span>
          </div>
        )}

        {/* History */}
        {status?.history && status.history.length > 0 && (
          <div>
            <div className="text-[10px] font-mono text-[#555] uppercase tracking-wider mb-2">History</div>
            <div className="space-y-1">
              {[...status.history].reverse().map((run, i) => (
                <div key={i} className="px-2 py-1.5 bg-[#121212] border border-[#222]">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-mono text-[#888]">
                      {new Date(run.timestamp).toLocaleDateString()}
                    </span>
                    <span className="text-[10px] font-mono text-[#555]">{run.duration_seconds}s</span>
                  </div>
                  <div className="flex items-center gap-3 mt-0.5">
                    <span className="text-[9px] font-mono text-[#10B981]">+{run.consolidated} new</span>
                    <span className="text-[9px] font-mono text-[#EF4444]">-{run.pruned} pruned</span>
                    <span className="text-[9px] font-mono text-[#555]">{run.new_learnings} learnings</span>
                  </div>
                  {run.error && (
                    <div className="text-[9px] font-mono text-[#EF4444] mt-0.5">{run.error}</div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
