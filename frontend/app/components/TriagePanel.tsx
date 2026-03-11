"use client";

import { useState } from "react";
import type { TriageResult } from "../hooks/useWebSocket";

export type { TriageResult };

export interface TriagePanelProps {
  triage: TriageResult;
  recentOutput?: string[];
  onAccept: () => void;
  onOverride: (action: string) => void;
}

const VERDICT_COLORS: Record<string, string> = {
  retry: "text-accent bg-accent/10 border-accent/30",
  terminate: "text-error bg-error/10 border-error/30",
  extend: "text-warning bg-warning/10 border-warning/30",
  escalate: "text-orange-400 bg-orange-400/10 border-orange-400/30",
  reassign: "text-purple-400 bg-purple-400/10 border-purple-400/30",
};

const VERDICT_LABELS: Record<string, string> = {
  retry: "Retry",
  terminate: "Terminate",
  extend: "Extend",
  escalate: "Escalate",
  reassign: "Reassign",
};

const OVERRIDE_OPTIONS = ["Retry", "Terminate", "Extend", "Ignore"];

export function TriagePanel({ triage, recentOutput, onAccept, onOverride }: TriagePanelProps) {
  const [showOverride, setShowOverride] = useState(false);

  return (
    <div className="mx-3 my-2 rounded-lg border border-border-subtle bg-surface/80 overflow-hidden">
      {/* Header with verdict badge */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border-subtle/50">
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-mono text-text-muted uppercase tracking-wider">
            AI Triage
          </span>
          <span
            className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded border ${
              VERDICT_COLORS[triage.verdict] || "text-text-muted bg-surface border-border-subtle"
            }`}
          >
            {VERDICT_LABELS[triage.verdict] || triage.verdict}
          </span>
        </div>
        <span className="text-[9px] font-mono text-text-muted">
          W{triage.worker_id}
        </span>
      </div>

      {/* Reasoning */}
      <div className="px-3 py-2">
        <p className="text-xs text-text-secondary font-mono leading-relaxed">
          {triage.reasoning}
        </p>
      </div>

      {/* Recommended action */}
      <div className="px-3 py-1.5 bg-surface-raised/50">
        <span className="text-[10px] text-text-muted font-mono">Recommended: </span>
        <span className="text-[10px] text-text-primary font-mono font-medium">
          {triage.recommended_action || "—"}
        </span>
      </div>

      {/* Recent output preview */}
      {recentOutput && recentOutput.length > 0 && (
        <div className="px-3 py-2 border-t border-border-subtle/30">
          <div className="text-[9px] text-text-muted font-mono uppercase tracking-wider mb-1">
            Recent Output
          </div>
          <div className="max-h-32 overflow-y-auto rounded bg-surface p-1.5">
            {recentOutput.slice(-20).map((line, i) => (
              <div
                key={i}
                className="text-[10px] text-text-muted font-mono truncate leading-relaxed"
              >
                {line}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Action buttons */}
      <div className="flex items-center gap-2 px-3 py-2 border-t border-border-subtle/30">
        <button
          onClick={onAccept}
          className="text-[10px] font-mono px-3 py-1 rounded border border-accent/30 text-accent bg-accent/10 hover:bg-accent/20 transition-colors"
        >
          Accept Recommendation
        </button>
        <button
          onClick={() => setShowOverride(!showOverride)}
          className="text-[10px] font-mono px-3 py-1 rounded border border-border-subtle text-text-muted hover:text-text-secondary hover:bg-surface-raised transition-colors"
        >
          Override
        </button>

        {/* Override dropdown */}
        {showOverride && (
          <div className="flex items-center gap-1 ml-1">
            {OVERRIDE_OPTIONS.map((opt) => (
              <button
                key={opt}
                onClick={() => {
                  onOverride(opt.toLowerCase());
                  setShowOverride(false);
                }}
                className="text-[10px] font-mono px-2 py-0.5 rounded border border-border-subtle text-text-secondary hover:text-text-primary hover:bg-surface-raised transition-colors"
              >
                {opt}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
