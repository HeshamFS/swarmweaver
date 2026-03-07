"use client";

import { useEffect, useState } from "react";
import { BrainCog } from "lucide-react";

interface ThinkingBarProps {
  agentName: string;
  label: string;
  active: boolean;
  elapsedSecs?: number;
  completedSecs?: number;
}

function formatDuration(secs: number): string {
  if (secs < 60) return `${secs}s`;
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return `${m}m ${s}s`;
}

export default function ThinkingBar({ agentName, label, active, elapsedSecs, completedSecs }: ThinkingBarProps) {
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => setTick((t) => t + 1), 150);
    return () => clearInterval(id);
  }, [active]);

  const barWidth = 36;
  const pos = tick % (barWidth * 2);
  const bar = Array.from({ length: barWidth }, (_, i) => {
    const dist = Math.abs(i - (pos < barWidth ? pos : barWidth * 2 - pos));
    return dist < 4 ? "\u2593" : "\u2591";
  }).join("");

  return (
    <div className={`border bg-[#121212] mb-2 font-mono transition-colors ${active ? "border-[var(--color-accent)]" : "border-[#333]"}`}>
      <div className="flex items-center gap-2 px-3 py-1">
        <BrainCog className={`w-3 h-3 shrink-0 ${active ? "text-[var(--color-accent)] animate-pulse" : "text-[#555]"}`} />
        <span className={`text-[10px] font-bold uppercase tracking-wider ${active ? "text-[var(--color-accent)]" : "text-[#555]"}`}>
          {agentName}
        </span>
        <span className={`text-[10px] ${active ? "text-[#888]" : "text-[#555]"}`}>
          {label}
        </span>
        {active && (
          <span className="text-[var(--color-accent)] tracking-widest text-[10px] ml-1">{bar}</span>
        )}
        {active && elapsedSecs != null && elapsedSecs > 0 && (
          <span className="text-[10px] text-[#666] ml-auto tabular-nums">
            {formatDuration(elapsedSecs)}
          </span>
        )}
        {!active && completedSecs != null && completedSecs > 0 && (
          <span className="text-[10px] text-[#555] ml-auto tabular-nums">
            {formatDuration(completedSecs)}
          </span>
        )}
        {!active && completedSecs == null && (
          <span className="text-[10px] text-[#555] ml-auto">{"\u2713"}</span>
        )}
      </div>
    </div>
  );
}
