"use client";

import { useState, useEffect, useRef } from "react";
import MarkdownPreview from "../MarkdownPreview";

interface PlanAnalysisBlockProps {
  analysisText: string;
  isStreaming: boolean;
  hasTasks: boolean;
}

export default function PlanAnalysisBlock({ analysisText, isStreaming, hasTasks }: PlanAnalysisBlockProps) {
  const [collapsed, setCollapsed] = useState(false);
  const collapseTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Extract display text: everything before the first `{` (strip JSON from display)
  const jsonStart = analysisText.indexOf("{");
  let displayText = jsonStart > 0 ? analysisText.slice(0, jsonStart).trim() : analysisText.trim();

  // Strip common raw markdown prefixes the model may emit (e.g. "**Analysis:**")
  displayText = displayText.replace(/^\*{1,2}Analysis:?\*{1,2}\s*/i, "").trim();

  // Detect when JSON generation has started (analysis text is finalized)
  const jsonStarted = jsonStart > 0;

  // Auto-collapse 600ms after tasks arrive
  useEffect(() => {
    if (hasTasks && !collapsed) {
      collapseTimerRef.current = setTimeout(() => setCollapsed(true), 600);
    }
    return () => {
      if (collapseTimerRef.current) clearTimeout(collapseTimerRef.current);
    };
  }, [hasTasks, collapsed]);

  if (!displayText) return null;

  return (
    <div className="border border-[#333] bg-[#121212] mb-3 font-mono">
      {/* Header */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="flex items-center gap-3 px-4 py-2 w-full text-left border-b border-[#222] bg-[#0C0C0C] hover:bg-[#1A1A1A] transition-colors"
      >
        <span className={collapsed ? "text-[#555]" : "text-[var(--color-accent)]"}>
          {collapsed ? "\u2713" : "\u25A0"}
        </span>
        <span className={`text-xs font-bold uppercase tracking-wider ${collapsed ? "text-[#555]" : "text-[#E0E0E0]"}`}>
          Planner Analysis
        </span>
        {isStreaming && !jsonStarted && !collapsed && (
          <span className="text-[var(--color-accent)] text-[10px] animate-pulse uppercase tracking-wider">
            streaming
          </span>
        )}
        <span className="text-[#555] text-[10px] ml-auto">
          {collapsed ? "\u25B6" : "\u25BC"}
        </span>
      </button>

      {/* Content — rendered as markdown for proper formatting */}
      {!collapsed && (
        <div className="px-4 py-3 text-xs leading-relaxed">
          <MarkdownPreview>{displayText}</MarkdownPreview>
          {isStreaming && !jsonStarted && !hasTasks && (
            <span className="inline-block w-[2px] h-[14px] bg-[var(--color-accent)] ml-0.5 align-middle spec-cursor" />
          )}
        </div>
      )}
    </div>
  );
}
