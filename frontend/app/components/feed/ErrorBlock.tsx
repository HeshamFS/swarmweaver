"use client";

import type { ErrorItem } from "../../hooks/useActivityFeed";

const SEVERITY_CONFIG: Record<string, { label: string; color: string; borderColor: string; bgColor: string }> = {
  error: {
    label: "ERROR",
    color: "text-[var(--color-error)]",
    borderColor: "border-l-[var(--color-error)]",
    bgColor: "bg-[var(--color-error)]/5",
  },
  warning: {
    label: "WARN",
    color: "text-[var(--color-warning)]",
    borderColor: "border-l-[var(--color-warning)]",
    bgColor: "bg-[var(--color-warning)]/5",
  },
  blocked: {
    label: "BLOCKED",
    color: "text-[var(--color-warning)]",
    borderColor: "border-l-[var(--color-warning)]",
    bgColor: "bg-[var(--color-warning)]/5",
  },
  directive: {
    label: "DIRECTIVE",
    color: "text-[var(--color-accent)]",
    borderColor: "border-l-[var(--color-accent)]",
    bgColor: "bg-[var(--color-accent)]/5",
  },
};

const STEERING_PATTERN = /\[STEERING\]|\[DIRECTIVE FROM ORCHESTRATOR\]|Message from operator/i;

interface ErrorBlockProps {
  item: ErrorItem;
  collapsed: boolean;
  onToggle: () => void;
}

export function ErrorBlock({ item, collapsed, onToggle }: ErrorBlockProps) {
  const isSteering = item.severity === "blocked" && STEERING_PATTERN.test(item.message);
  const config = isSteering ? SEVERITY_CONFIG.directive : (SEVERITY_CONFIG[item.severity] || SEVERITY_CONFIG.error);

  return (
    <div className={`border border-[#222] bg-[#121212] mb-1 overflow-hidden border-l-[3px] ${config.borderColor} ${config.bgColor}`}>
      <button
        onClick={onToggle}
        className="w-full px-4 py-3 flex items-center gap-3 text-left cursor-pointer group"
      >
        {/* Error/directive indicator */}
        <span className={`font-mono font-bold shrink-0 ${config.color}`}>{isSteering ? "\u2139" : "!"}</span>

        {/* Severity badge */}
        <span className={`text-[11px] px-2 py-0.5 font-mono font-medium shrink-0 ${config.color} border border-current/20`}>
          {config.label}
        </span>

        {/* Error message */}
        <span className="text-[13px] text-[#E0E0E0] truncate flex-1 font-mono">
          {item.message.length > 100 ? item.message.slice(0, 97) + "..." : item.message}
        </span>

        {/* Chevron */}
        <span className="text-[#555] group-hover:text-[#E0E0E0] transition-colors shrink-0">
          {collapsed ? "\u203A" : "\u2039"}
        </span>
      </button>

      {/* Expanded: full error message + recovery hint */}
      {!collapsed && (
        <div className="border-t border-[#222] px-4 py-3">
          <pre className="text-[13px] text-[#888] font-mono whitespace-pre-wrap break-all leading-relaxed">
            {item.message}
          </pre>

          {item.recoveryHint && (
            <div className="mt-3 pt-3 border-t border-[#222]">
              <div className="text-[11px] text-[#555] font-mono mb-1 uppercase tracking-wider font-medium">Recovery Hint</div>
              <p className="text-[13px] text-[var(--color-success)] font-mono leading-relaxed">{item.recoveryHint}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
