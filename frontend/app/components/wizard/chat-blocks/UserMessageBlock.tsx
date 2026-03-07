"use client";

import { BrainCog } from "lucide-react";

interface UserMessageBlockProps {
  text: string;
  mode: string;
  projectDir?: string;
  elapsedSecs?: number;
  isLoading?: boolean;
}

const MODE_LABELS: Record<string, string> = {
  greenfield: "Greenfield",
  feature: "Feature",
  refactor: "Refactor",
  fix: "Fix",
  evolve: "Evolve",
  security: "Security",
};

function formatDuration(secs: number): string {
  if (secs < 60) return `${secs}s`;
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return `${m}m ${s}s`;
}

export default function UserMessageBlock({ text, mode, projectDir, elapsedSecs, isLoading }: UserMessageBlockProps) {
  return (
    <div className="border border-[#222] bg-[#121212] mb-3 font-mono">
      <div className="flex items-center gap-3 px-4 py-2 border-b border-[#222] bg-[#0C0C0C]">
        <span className="text-[var(--color-accent)] text-xs">{"\u25B6"}</span>
        <span className="text-[#E0E0E0] text-xs font-bold uppercase tracking-wider">You</span>
        <span className="text-[#333] text-xs">|</span>
        <span className="text-[var(--color-accent)] text-[10px] uppercase tracking-wider">
          {MODE_LABELS[mode] || mode}
        </span>
        {projectDir && (
          <>
            <span className="text-[#333] text-xs">|</span>
            <span className="text-[#555] text-[10px] truncate max-w-[300px]">{projectDir}</span>
          </>
        )}
        <div className="flex-1" />
        {elapsedSecs != null && elapsedSecs > 0 && (
          <span className={`text-[11px] tabular-nums ${isLoading ? "text-[var(--color-accent)]" : "text-[#555]"}`}>
            {isLoading && <BrainCog className="w-3 h-3 animate-pulse mr-1 inline-block shrink-0" />}
            {formatDuration(elapsedSecs)}
          </span>
        )}
      </div>
      <div className="p-4">
        <div className="text-[#E0E0E0] text-sm leading-relaxed whitespace-pre-wrap">{text}</div>
      </div>
    </div>
  );
}
