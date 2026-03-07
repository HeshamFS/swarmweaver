"use client";

import type { PhaseMarkerItem } from "../../hooks/useActivityFeed";

interface PhaseMarkerBlockProps {
  item: PhaseMarkerItem;
}

export function PhaseMarkerBlock({ item }: PhaseMarkerBlockProps) {
  return (
    <div className="flex items-center justify-center my-6 relative">
      {/* Full-width line */}
      <div className="absolute left-0 right-0 h-px bg-[#222]" />

      {/* Phase badge */}
      <div className="flex items-center gap-2 px-4 py-1.5 bg-[#1A1A1A] border border-[#333] z-10">
        <span className="text-[var(--color-accent)]">{"\u26A1"}</span>
        <span className="text-[12px] font-mono font-medium text-[#E0E0E0] uppercase tracking-wider">
          {item.phase}
        </span>
        {item.sessionNumber != null && (
          <span className="text-[11px] text-[#555] font-mono">
            #{item.sessionNumber}
          </span>
        )}
      </div>
    </div>
  );
}
