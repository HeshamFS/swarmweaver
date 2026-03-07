"use client";

import type { Mode } from "../hooks/useSwarmWeaver";

/* ── Tab metadata shape (shared with page.tsx) ── */

export interface SessionTabMeta {
  id: string;
  label: string;
  mode: Mode | null;
  status: "idle" | "configuring" | "running" | "completed" | "error";
  createdAt: number;
}

export function createNewTabMeta(): SessionTabMeta {
  const id = `tab-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  return { id, label: "New Session", mode: null, status: "idle", createdAt: Date.now() };
}

/* ── Mode accent colors (reference CSS variables) ── */

const MODE_COLORS: Record<string, string> = {
  greenfield: "var(--color-mode-greenfield)",
  feature: "var(--color-mode-feature)",
  refactor: "var(--color-mode-refactor)",
  fix: "var(--color-mode-fix)",
  evolve: "var(--color-mode-evolve)",
  security: "var(--color-mode-security)",
};

/* ── Status dot ── */

function StatusDot({ status }: { status: SessionTabMeta["status"] }) {
  if (status === "running") {
    return <span className="w-2 h-2 rounded-full bg-[var(--color-success)] animate-pulse shrink-0" />;
  }
  if (status === "completed") {
    return (
      <svg className="w-3 h-3 text-[var(--color-success)] shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
      </svg>
    );
  }
  if (status === "error") {
    return (
      <svg className="w-3 h-3 text-[var(--color-error)] shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
      </svg>
    );
  }
  return null;
}

/* ── TabBar ── */

interface TabBarProps {
  tabs: SessionTabMeta[];
  activeTabId: string;
  onSelectTab: (tabId: string) => void;
  onCloseTab: (tabId: string) => void;
  onNewTab: () => void;
}

export default function TabBar({ tabs, activeTabId, onSelectTab, onCloseTab, onNewTab }: TabBarProps) {
  return (
    <div className="flex items-center h-10 bg-[var(--color-surface-1)] border-b border-[var(--color-border-subtle)] shrink-0 tab-bar-scroll overflow-x-auto z-50">
      {/* Tab items */}
      <div className="flex items-stretch min-w-0 px-2 py-1 gap-1">
        {tabs.map((tab) => {
          const isActive = tab.id === activeTabId;
          const modeColor = tab.mode ? MODE_COLORS[tab.mode] : null;

          return (
            <div
              key={tab.id}
              role="tab"
              aria-selected={isActive}
              className={`group relative flex items-center gap-2 px-3 h-8 rounded-md cursor-pointer select-none max-w-[200px] ${isActive
                ? "bg-[var(--color-surface-2)] text-[var(--color-text-primary)] border border-[var(--color-border-subtle)]"
                : "bg-transparent text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-2)] border border-transparent"
                }`}
              onClick={() => onSelectTab(tab.id)}
            >
              {/* Mode color accent bar */}
              {modeColor && (
                <span
                  className="w-1 h-3.5 rounded-full shrink-0"
                  style={{ backgroundColor: modeColor }}
                />
              )}

              {/* Status indicator */}
              <StatusDot status={tab.status} />

              {/* Label */}
              <span className="text-xs font-medium truncate">{tab.label}</span>

              {/* Close button */}
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onCloseTab(tab.id);
                }}
                className="ml-auto p-0.5 rounded opacity-0 group-hover:opacity-60 hover:!opacity-100 hover:bg-[var(--color-surface-3)] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] shrink-0"
                title="Close tab"
              >
                <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          );
        })}
      </div>

      {/* New tab button */}
      <button
        onClick={onNewTab}
        className="flex items-center justify-center w-8 h-8 mx-1 rounded-md text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-2)] shrink-0"
        title="New session"
      >
        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
        </svg>
      </button>
    </div>
  );
}
