"use client";

import type { VerificationItem } from "../../hooks/useActivityFeed";

interface VerificationBlockProps {
  item: VerificationItem;
  collapsed: boolean;
  onToggle: () => void;
}

export function VerificationBlock({ item, collapsed, onToggle }: VerificationBlockProps) {
  return (
    <div
      className={`border bg-[#121212] mb-1 overflow-hidden border-l-2 ${
        item.passed
          ? "border-[#222] border-l-[var(--color-success)]"
          : "border-[#222] border-l-[var(--color-error)]"
      }`}
    >
      <button
        onClick={onToggle}
        className="w-full px-4 py-3 flex items-center gap-3 text-left cursor-pointer group"
      >
        {/* Pass/fail indicator */}
        <span className={`font-mono font-bold shrink-0 ${item.passed ? "text-[var(--color-success)]" : "text-[var(--color-error)]"}`}>
          {item.passed ? "\u2713" : "\u2717"}
        </span>

        {/* Task title */}
        <span className="text-[13px] text-[#E0E0E0] truncate flex-1 font-mono">
          {item.taskTitle}
        </span>

        {/* Status badge */}
        <span className={`text-[11px] px-2 py-0.5 font-mono font-medium shrink-0 border ${
          item.passed
            ? "text-[var(--color-success)] border-[var(--color-success)]/20"
            : "text-[var(--color-error)] border-[var(--color-error)]/20"
        }`}>
          {item.passed ? "PASS" : "FAIL"}
        </span>

        {/* Expand chevron */}
        {item.output && (
          <span className="text-[#555] group-hover:text-[#E0E0E0] transition-colors shrink-0">
            {collapsed ? "\u203A" : "\u2039"}
          </span>
        )}
      </button>

      {/* Expanded: test output */}
      {!collapsed && item.output && (
        <div className="border-t border-[#222] px-4 py-3">
          <pre className="text-[13px] text-[#888] font-mono whitespace-pre-wrap break-all leading-relaxed max-h-64 overflow-y-auto">
            {item.output}
          </pre>
        </div>
      )}
    </div>
  );
}
