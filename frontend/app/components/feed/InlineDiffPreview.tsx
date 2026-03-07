"use client";

import { useState } from "react";

interface DiffLine {
  type: "add" | "remove" | "context" | "header";
  text: string;
}

interface InlineDiffPreviewProps {
  diff: string;
  filePath?: string;
  collapsed: boolean;
  onToggle: () => void;
}

function parseDiffLines(diff: string): DiffLine[] {
  const lines: DiffLine[] = [];
  for (const line of diff.split("\n")) {
    if (line.startsWith("@@") || line.startsWith("---") || line.startsWith("+++")) {
      lines.push({ type: "header", text: line });
    } else if (line.startsWith("+")) {
      lines.push({ type: "add", text: line });
    } else if (line.startsWith("-")) {
      lines.push({ type: "remove", text: line });
    } else {
      lines.push({ type: "context", text: line });
    }
  }
  return lines;
}

const LINE_COLORS: Record<string, string> = {
  add: "bg-[var(--color-success)]/10 text-[var(--color-success)]",
  remove: "bg-[var(--color-error)]/10 text-[var(--color-error)]",
  context: "text-[#555]",
  header: "bg-[var(--color-info)]/5 text-[var(--color-info)] font-medium",
};

const MAX_LINES = 30;

export function InlineDiffPreview({ diff, filePath, collapsed, onToggle }: InlineDiffPreviewProps) {
  const [showAll, setShowAll] = useState(false);
  const lines = parseDiffLines(diff);
  const addCount = lines.filter((l) => l.type === "add").length;
  const removeCount = lines.filter((l) => l.type === "remove").length;
  const hasMore = lines.length > MAX_LINES;
  const visibleLines = showAll ? lines : lines.slice(0, MAX_LINES);
  const displayName = filePath?.split("/").pop() || "Diff";

  return (
    <div className="border border-[#222] bg-[#121212] mb-1 overflow-hidden hover:border-[#444] transition-colors">
      {/* Header */}
      <button
        onClick={onToggle}
        className="w-full px-4 py-3 flex items-center gap-3 text-left cursor-pointer group"
      >
        {/* Diff icon */}
        <span className="text-[var(--color-accent)] shrink-0 font-bold">{"\u00B1"}</span>

        <span className="text-xs text-[#E0E0E0] font-mono font-bold truncate flex-1">{displayName}</span>

        <div className="flex items-center gap-1.5 text-[10px] font-mono shrink-0">
          {addCount > 0 && <span className="text-[var(--color-success)]">+{addCount}</span>}
          {removeCount > 0 && <span className="text-[var(--color-error)]">-{removeCount}</span>}
        </div>

        <span className="text-[#555] group-hover:text-[#E0E0E0] transition-colors shrink-0">
          {collapsed ? "\u203A" : "\u2039"}
        </span>
      </button>

      {/* Diff content */}
      {!collapsed && (
        <div className="border-t border-[#222] font-mono text-[11px] leading-5 overflow-x-auto">
          {visibleLines.map((line, i) => (
            <div
              key={i}
              className={`px-3 whitespace-pre ${LINE_COLORS[line.type]}`}
            >
              {line.text}
            </div>
          ))}

          {hasMore && !showAll && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                setShowAll(true);
              }}
              className="w-full px-3 py-1.5 text-[10px] text-[var(--color-accent)] hover:text-[var(--color-accent-hover)] text-center border-t border-[#222] transition-colors font-mono"
            >
              Show {lines.length - MAX_LINES} more lines
            </button>
          )}
        </div>
      )}
    </div>
  );
}
