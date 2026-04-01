"use client";

import { useState, useEffect } from "react";

interface ContextStatus {
  circuit_breaker_count: number;
  circuit_breaker_max: number;
  circuit_breaker_tripped: boolean;
  compact_count: number;
  total_tokens_saved: number;
  microcompact_enabled: boolean;
  session_memory_enabled: boolean;
  legacy_compact_enabled: boolean;
  microcompact_age_minutes: number;
  buffer_tokens: number;
}

interface ContextPanelProps {
  projectDir: string;
  inputTokens?: number;
  contextWindow?: number;
}

export function ContextPanel({ projectDir, inputTokens = 0, contextWindow = 200000 }: ContextPanelProps) {
  const [status, setStatus] = useState<ContextStatus | null>(null);

  useEffect(() => {
    if (!projectDir) return;
    const enc = encodeURIComponent(projectDir);
    const fetchStatus = () => {
      fetch(`/api/context/status?path=${enc}`)
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => { if (d) setStatus(d); })
        .catch(() => {});
    };
    fetchStatus();
    const interval = setInterval(fetchStatus, 10000);
    return () => clearInterval(interval);
  }, [projectDir]);

  const usagePct = contextWindow > 0 ? Math.min(100, (inputTokens / contextWindow) * 100) : 0;
  const usageColor = usagePct >= 80 ? "#EF4444" : usagePct >= 60 ? "#F59E0B" : "#10B981";
  const threshold = status ? contextWindow - (status.buffer_tokens + 20000) : 0;
  const thresholdPct = contextWindow > 0 ? (threshold / contextWindow) * 100 : 0;

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-2.5 border-b border-[#222] bg-[#0C0C0C] shrink-0">
        <span className="text-xs font-mono font-medium text-[#E0E0E0] uppercase tracking-wider">Context Health</span>
      </div>

      <div className="flex-1 overflow-y-auto min-h-0 px-4 py-3 space-y-4">
        {/* Usage bar */}
        <div>
          <div className="flex items-center justify-between text-[10px] font-mono mb-1">
            <span className="text-[#555]">Context Usage</span>
            <span style={{ color: usageColor }}>{usagePct.toFixed(1)}%</span>
          </div>
          <div className="relative h-3 rounded bg-[#1A1A1A] border border-[#333] overflow-hidden">
            <div className="h-full transition-all duration-500" style={{ width: `${usagePct}%`, backgroundColor: usageColor }} />
            {thresholdPct > 0 && (
              <div className="absolute top-0 bottom-0 w-px bg-[#EF4444]/50" style={{ left: `${thresholdPct}%` }}
                title={`Auto-compact threshold (${threshold.toLocaleString()} tokens)`} />
            )}
          </div>
          <div className="flex items-center justify-between text-[9px] font-mono mt-0.5">
            <span className="text-[#444]">{inputTokens.toLocaleString()} tokens</span>
            <span className="text-[#444]">{contextWindow.toLocaleString()} max</span>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 gap-2">
          <div className="bg-[#121212] border border-[#222] p-2 text-center">
            <div className="text-lg font-mono font-bold text-[#E0E0E0]">{status?.compact_count ?? 0}</div>
            <div className="text-[10px] font-mono text-[#555]">Compactions</div>
          </div>
          <div className="bg-[#121212] border border-[#222] p-2 text-center">
            <div className="text-lg font-mono font-bold text-[#E0E0E0]">
              {status?.total_tokens_saved ? `${(status.total_tokens_saved / 1000).toFixed(0)}K` : "0"}
            </div>
            <div className="text-[10px] font-mono text-[#555]">Tokens Saved</div>
          </div>
        </div>

        {/* Circuit breaker */}
        <div className="bg-[#121212] border border-[#222] p-2.5">
          <div className="flex items-center justify-between mb-1">
            <span className="text-[10px] font-mono text-[#555] uppercase tracking-wider">Circuit Breaker</span>
            <span className={`text-[10px] font-mono font-bold ${status?.circuit_breaker_tripped ? "text-[#EF4444]" : "text-[#10B981]"}`}>
              {status?.circuit_breaker_tripped ? "TRIPPED" : "OK"}
            </span>
          </div>
          <div className="flex items-center gap-1">
            {Array.from({ length: status?.circuit_breaker_max ?? 3 }).map((_, i) => (
              <div key={i} className={`h-1.5 flex-1 rounded ${i < (status?.circuit_breaker_count ?? 0) ? "bg-[#EF4444]" : "bg-[#333]"}`} />
            ))}
          </div>
          <div className="text-[9px] font-mono text-[#444] mt-1">
            {status?.circuit_breaker_count ?? 0} / {status?.circuit_breaker_max ?? 3} failures
          </div>
        </div>

        {/* Layers */}
        <div>
          <div className="text-[10px] font-mono text-[#555] uppercase tracking-wider mb-2">Compaction Layers</div>
          <div className="space-y-1.5">
            {[
              { key: "microcompact", label: "Microcompact", desc: `Strip tool results > ${status?.microcompact_age_minutes ?? 60}min`, enabled: status?.microcompact_enabled },
              { key: "session_memory", label: "Session Memory", desc: "Reuse MELS expertise as summary", enabled: status?.session_memory_enabled },
              { key: "legacy_compact", label: "Legacy Compact", desc: "9-section Claude summarization", enabled: status?.legacy_compact_enabled },
            ].map((layer) => (
              <div key={layer.key} className="flex items-center gap-2 px-2 py-1.5 bg-[#121212] border border-[#222]">
                <span className={`w-1.5 h-1.5 rounded-full ${layer.enabled ? "bg-[#10B981]" : "bg-[#555]"}`} />
                <div className="flex-1">
                  <div className="text-xs font-mono text-[#E0E0E0]">{layer.label}</div>
                  <div className="text-[9px] font-mono text-[#555]">{layer.desc}</div>
                </div>
                <span className="text-[9px] font-mono text-[#555]">{layer.enabled ? "ON" : "OFF"}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Config */}
        <div className="space-y-1">
          <div className="flex items-center justify-between text-[10px] font-mono">
            <span className="text-[#555]">Buffer</span>
            <span className="text-[#888]">{(status?.buffer_tokens ?? 13000).toLocaleString()} tokens</span>
          </div>
          <div className="flex items-center justify-between text-[10px] font-mono">
            <span className="text-[#555]">Microcompact age</span>
            <span className="text-[#888]">{status?.microcompact_age_minutes ?? 60} min</span>
          </div>
        </div>
      </div>
    </div>
  );
}
