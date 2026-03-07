"use client";

import type { UserMessageItem } from "../../hooks/useActivityFeed";

const STEERING_LABELS: Record<string, { label: string; color: string }> = {
  instruction: { label: "Instruction", color: "bg-accent/10 text-accent" },
  correction: { label: "Correction", color: "bg-error/10 text-error" },
  priority: { label: "Priority", color: "bg-warning/10 text-warning" },
  context: { label: "Context", color: "bg-info/10 text-info" },
};

interface UserMessageBlockProps {
  item: UserMessageItem;
}

export function UserMessageBlock({ item }: UserMessageBlockProps) {
  const steeringInfo = item.steeringType
    ? STEERING_LABELS[item.steeringType] || { label: item.steeringType, color: "bg-surface-2 text-text-muted" }
    : null;

  return (
    <div className="rounded-xl border border-accent/20 bg-surface-1/30 overflow-hidden">
      <div className="flex items-start gap-3 px-4 py-3 border-l-[3px] border-accent">
        {/* User icon */}
        <svg className="w-[18px] h-[18px] text-accent shrink-0 mt-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
          <circle cx="12" cy="7" r="4" />
        </svg>

        <div className="flex-1 min-w-0">
          {/* Steering badge */}
          {steeringInfo && (
            <span className={`inline-block text-[11px] px-2 py-0.5 rounded-md font-medium mb-1.5 ${steeringInfo.color}`}>
              {steeringInfo.label}
            </span>
          )}

          {/* Message text */}
          <div className="text-[14px] text-text-primary leading-relaxed">
            {item.text}
          </div>
        </div>
      </div>
    </div>
  );
}
