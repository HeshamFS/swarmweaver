"use client";

import { useState } from "react";

interface DiffViewerProps {
  diff: string;
  maxHeight?: string;
}

interface DiffFile {
  header: string;
  lines: { type: "add" | "remove" | "context" | "header"; text: string }[];
}

function parseDiff(diff: string): DiffFile[] {
  const files: DiffFile[] = [];
  let current: DiffFile | null = null;

  for (const line of diff.split("\n")) {
    if (line.startsWith("diff --git")) {
      if (current) files.push(current);
      // Extract filename from "diff --git a/foo b/foo"
      const parts = line.split(" b/");
      const filename = parts.length > 1 ? parts[1] : line;
      current = { header: filename, lines: [] };
    } else if (current) {
      if (line.startsWith("+++") || line.startsWith("---") || line.startsWith("@@")) {
        current.lines.push({ type: "header", text: line });
      } else if (line.startsWith("+")) {
        current.lines.push({ type: "add", text: line });
      } else if (line.startsWith("-")) {
        current.lines.push({ type: "remove", text: line });
      } else {
        current.lines.push({ type: "context", text: line });
      }
    }
  }
  if (current) files.push(current);
  return files;
}

const LINE_COLORS = {
  add: "text-success bg-success/5",
  remove: "text-error bg-error/5",
  context: "text-text-muted",
  header: "text-info bg-info/5 font-medium",
};

export function DiffViewer({ diff, maxHeight = "500px" }: DiffViewerProps) {
  const files = parseDiff(diff);
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  if (!diff.trim()) {
    return (
      <div className="flex items-center justify-center p-4 text-xs text-text-muted">
        No changes to display
      </div>
    );
  }

  const toggleFile = (header: string) => {
    setCollapsed((prev) => ({ ...prev, [header]: !prev[header] }));
  };

  const stats = files.reduce(
    (acc, f) => {
      for (const l of f.lines) {
        if (l.type === "add") acc.added++;
        if (l.type === "remove") acc.removed++;
      }
      return acc;
    },
    { added: 0, removed: 0 }
  );

  return (
    <div className="rounded-lg border border-border-subtle overflow-hidden">
      {/* Summary */}
      <div className="px-3 py-2 bg-surface-raised border-b border-border-subtle flex items-center justify-between">
        <span className="text-xs text-text-muted font-mono">
          {files.length} file{files.length !== 1 ? "s" : ""} changed
        </span>
        <div className="flex items-center gap-3 text-xs font-mono">
          <span className="text-success">+{stats.added}</span>
          <span className="text-error">-{stats.removed}</span>
        </div>
      </div>

      {/* File sections */}
      <div className="overflow-y-auto" style={{ maxHeight }}>
        {files.map((file, fi) => (
          <div key={fi} className="border-b border-border-subtle/50 last:border-b-0">
            {/* File header */}
            <button
              onClick={() => toggleFile(file.header)}
              className="w-full px-3 py-1.5 bg-surface-raised/50 flex items-center gap-2 hover:bg-surface-raised transition-colors text-left"
            >
              <span className="text-[10px] text-text-muted">
                {collapsed[file.header] ? "\u25B6" : "\u25BC"}
              </span>
              <span className="text-xs text-accent font-mono truncate">
                {file.header}
              </span>
              <span className="text-[10px] text-text-muted font-mono ml-auto">
                +{file.lines.filter((l) => l.type === "add").length}
                {" "}-{file.lines.filter((l) => l.type === "remove").length}
              </span>
            </button>

            {/* Lines */}
            {!collapsed[file.header] && (
              <div className="font-mono text-[11px] leading-5">
                {file.lines.map((line, li) => (
                  <div
                    key={li}
                    className={`px-3 ${LINE_COLORS[line.type]} whitespace-pre overflow-x-auto`}
                  >
                    {line.text}
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
