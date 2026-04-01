"use client";

import { useState, useEffect, useRef } from "react";

interface ThinkingIndicatorProps {
  isThinking: boolean;
  thinkingTokens?: number;
  maxThinkingTokens?: number;
  currentPhase?: string;
}

export function ThinkingIndicator({
  isThinking,
  thinkingTokens = 0,
  maxThinkingTokens = 0,
  currentPhase,
}: ThinkingIndicatorProps) {
  const [dots, setDots] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const startRef = useRef<number>(0);

  // Animate dots
  useEffect(() => {
    if (!isThinking) { setDots(0); setElapsed(0); return; }
    startRef.current = Date.now();
    const interval = setInterval(() => {
      setDots((d) => (d + 1) % 4);
      setElapsed(Math.floor((Date.now() - startRef.current) / 1000));
    }, 500);
    return () => clearInterval(interval);
  }, [isThinking]);

  if (!isThinking) return null;

  const budgetPct = maxThinkingTokens > 0 ? Math.min(100, (thinkingTokens / maxThinkingTokens) * 100) : 0;
  const budgetColor = budgetPct >= 80 ? "#EF4444" : budgetPct >= 50 ? "#F59E0B" : "var(--color-accent)";

  return (
    <div className="flex items-center gap-3 px-3 py-1.5 rounded-md border border-accent/20 bg-accent/5 animate-pulse">
      {/* Thinking indicator */}
      <div className="flex items-center gap-1.5">
        <svg className="w-3.5 h-3.5 text-accent animate-spin" viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2" opacity="0.3" />
          <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
        <span className="text-[11px] font-mono text-accent">
          Thinking{".".repeat(dots)}
        </span>
      </div>

      {/* Phase label */}
      {currentPhase && (
        <>
          <span className="text-border-default">|</span>
          <span className="text-[10px] font-mono text-text-muted">{currentPhase}</span>
        </>
      )}

      {/* Timer */}
      <span className="text-[10px] font-mono text-text-muted tabular-nums">{elapsed}s</span>

      {/* Budget bar */}
      {maxThinkingTokens > 0 && (
        <div className="flex items-center gap-1.5 ml-auto">
          <div className="w-16 h-1 rounded-full bg-surface-raised overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-300"
              style={{ width: `${budgetPct}%`, backgroundColor: budgetColor }}
            />
          </div>
          <span className="text-[9px] font-mono text-text-muted">
            {thinkingTokens > 0 ? `${(thinkingTokens / 1000).toFixed(0)}K` : "0"}
            {maxThinkingTokens > 0 ? `/${(maxThinkingTokens / 1000).toFixed(0)}K` : ""}
          </span>
        </div>
      )}
    </div>
  );
}
