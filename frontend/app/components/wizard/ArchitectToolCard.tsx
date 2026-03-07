"use client";

import { useState, useEffect, useRef } from "react";
import { BrainCog } from "lucide-react";
import type { ToolEvent } from "../../hooks/useArchitectStream";

const TOOL_LABELS: Record<string, string> = {
  WebSearch: "web-search",
  WebFetch: "web-fetch",
  Read: "read",
  Glob: "glob",
  Grep: "grep",
};

// Tool names that are internal SDK mechanics, not user-visible research
const HIDDEN_TOOLS = new Set(["StructuredOutput", "structured_output"]);

function extractDisplay(input: string): string {
  try {
    const parsed = JSON.parse(input);
    if (parsed.query) return parsed.query;
    if (parsed.url) return parsed.url;
    if (parsed.pattern) return parsed.pattern;
    if (parsed.file_path) return parsed.file_path;
  } catch {
    // Input still streaming (partial JSON)
  }
  return input;
}

interface ArchitectResearchPanelProps {
  tools: ToolEvent[];
  specApproved?: boolean;
  label?: string;
}

export default function ArchitectResearchPanel({ tools, specApproved, label }: ArchitectResearchPanelProps) {
  const visibleTools = tools.filter((t) => !HIDDEN_TOOLS.has(t.tool));
  const runningCount = visibleTools.filter((t) => t.status === "running").length;
  const doneCount = visibleTools.filter((t) => t.status === "done").length;
  const allDone = visibleTools.length > 0 && runningCount === 0;

  const [collapsed, setCollapsed] = useState(false);
  const autoCollapsedRef = useRef(false);
  useEffect(() => {
    if (allDone && !autoCollapsedRef.current) {
      autoCollapsedRef.current = true;
      // Small delay so user sees the final "done" state before collapsing
      const timer = setTimeout(() => setCollapsed(true), 600);
      return () => clearTimeout(timer);
    }
  }, [allDone]);

  // Collapse when spec is approved and we move to the plan step
  useEffect(() => {
    if (specApproved) {
      setCollapsed(true);
    }
  }, [specApproved]);

  return (
    <div className="border border-[#333] bg-[#121212] mb-3 font-mono">
      {/* Header — clickable to toggle */}
      <button
        type="button"
        onClick={() => setCollapsed((c) => !c)}
        className={`w-full flex items-center gap-3 px-4 py-2 bg-[#0C0C0C] text-left transition-colors hover:bg-[#141414] ${collapsed ? "" : "border-b border-[#222]"}`}
      >
        <span className={allDone ? "text-[#555]" : "text-[var(--color-accent)]"}>
          {allDone ? "\u2713" : "\u25A0"}
        </span>
        <span className={`text-xs font-bold uppercase tracking-wider ${allDone ? "text-[#555]" : "text-[#E0E0E0]"}`}>
          {label || "Research"}
        </span>
        <span className="text-[#555] text-xs ml-auto flex items-center gap-2">
          {runningCount > 0 && (
            <span className="text-[var(--color-accent)] animate-pulse">{runningCount} active</span>
          )}
          {doneCount > 0 && (
            <span>{doneCount} done</span>
          )}
          <span className="text-[#444] text-[10px] ml-1">{collapsed ? "\u25B6" : "\u25BC"}</span>
        </span>
      </button>

      {/* Tool entries — collapsible */}
      {!collapsed && (
        <div className="divide-y divide-[#1A1A1A]">
          {visibleTools.map((t) => {
            const label = TOOL_LABELS[t.tool] || t.tool.toLowerCase();
            const display = extractDisplay(t.input);
            const isRunning = t.status === "running";

            return (
              <div key={t.id} className="flex items-start gap-3 px-4 py-2">
                {/* Status indicator */}
                <span className="shrink-0 mt-0.5 w-3 text-center">
                  {isRunning ? (
                    <BrainCog className="w-3 h-3 text-[var(--color-accent)] animate-pulse shrink-0" />
                  ) : (
                    <span className="text-[#555] text-[10px]">{"\u2713"}</span>
                  )}
                </span>

                {/* Tool label */}
                <span className={`shrink-0 text-[10px] font-bold uppercase tracking-wider w-20 ${
                  isRunning ? "text-[var(--color-accent)]" : "text-[#555]"
                }`}>
                  {label}
                </span>

                {/* Input text */}
                <span className={`text-xs truncate min-w-0 flex-1 ${
                  isRunning ? "text-[#888]" : "text-[#555]"
                }`}>
                  {display || "\u2014"}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
