"use client";

import { useState } from "react";
import { BrainCog } from "lucide-react";
import type { SessionTabMeta } from "./TabBar";
import type { Mode } from "../hooks/useSwarmWeaver";
import { MODE_COLORS, MODE_ICONS } from "../utils/modeIcons";

/* ── Relative time formatter ── */

function relativeTime(timestamp: number): string {
  const diff = Date.now() - timestamp;
  const seconds = Math.floor(diff / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

/* ── Status indicator ── */

function SessionStatusIndicator({ status }: { status: SessionTabMeta["status"] }) {
  if (status === "running") {
    return (
      <span className="text-[var(--color-success)] shrink-0 animate-pulse">
        <BrainCog className="w-3 h-3 inline-block" />
      </span>
    );
  }
  if (status === "configuring") {
    return (
      <span className="text-[var(--color-warning)] shrink-0 animate-pulse">
        <BrainCog className="w-3 h-3 inline-block" />
      </span>
    );
  }
  if (status === "completed") {
    return (
      <span className="text-[10px] font-mono text-[var(--color-success)] shrink-0">{"\u2713"}</span>
    );
  }
  if (status === "error") {
    return (
      <span className="text-[10px] font-mono text-[var(--color-error)] shrink-0">{"\u2717"}</span>
    );
  }
  // idle
  return <span className="text-[10px] font-mono text-[#555] shrink-0">{"\u25CB"}</span>;
}

/* ── Props ── */

interface SessionSidebarProps {
  tabs: SessionTabMeta[];
  activeTabId: string;
  onSelectTab: (tabId: string) => void;
  onCloseTab: (tabId: string) => void;
  onNewTab: () => void;
  onOpenSettings?: () => void;
}

/* ── Component ── */

export function SessionSidebar({
  tabs,
  activeTabId,
  onSelectTab,
  onCloseTab,
  onNewTab,
  onOpenSettings,
}: SessionSidebarProps) {
  const [collapsed, setCollapsed] = useState(false);
  const activeMode: Mode = tabs.find((t) => t.id === activeTabId)?.mode ?? "feature";
  const ActiveModeIcon = MODE_ICONS[activeMode];

  if (collapsed) {
    return (
      <div className="flex flex-col items-center w-12 bg-[#0C0C0C] border-r border-[#222] shrink-0 py-3 gap-2">
        {/* App icon (top) */}
        <div className="w-8 h-8 flex items-center justify-center shrink-0" title="SwarmWeaver">
          <BrainCog className="w-5 h-5" style={{ color: "var(--color-accent)" }} />
        </div>

        {/* Expand button */}
        <button
          onClick={() => setCollapsed(false)}
          className="w-8 h-8 flex items-center justify-center hover:bg-[#1A1A1A] transition-colors"
          title="Expand sidebar"
        >
          <svg className="w-4 h-4 text-[#555]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="m9 18 6-6-6-6" />
          </svg>
        </button>

        {/* New session — plus icon only */}
        <button
          onClick={onNewTab}
          className="w-8 h-8 flex items-center justify-center hover:bg-[#1A1A1A] text-[#555] hover:text-[var(--color-accent)] transition-colors"
          title="New session"
        >
          <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M5 12h14" /><path d="M12 5v14" />
          </svg>
        </button>

        <div className="w-6 h-px bg-[#222] my-1" />

        {/* Mini session icons */}
        {tabs.map((tab) => {
          const isActive = tab.id === activeTabId;
          const modeColor = tab.mode ? MODE_COLORS[tab.mode] : "var(--color-text-muted)";
          const TabModeIcon = (tab.mode ? MODE_ICONS[tab.mode] : MODE_ICONS.feature) as React.ComponentType<{ className?: string; style?: React.CSSProperties }>;
          return (
            <button
              key={tab.id}
              onClick={() => onSelectTab(tab.id)}
              className={`w-8 h-8 flex items-center justify-center transition-colors relative ${
                isActive
                  ? "bg-[var(--color-accent)]/10"
                  : "hover:bg-[#1A1A1A]"
              }`}
              title={tab.label}
            >
              <TabModeIcon className="w-4 h-4" style={{ color: modeColor }} />
              {(tab.status === "running" || tab.status === "configuring") && (
                <span
                  className="absolute inset-0 animate-pulse opacity-20"
                  style={{ backgroundColor: tab.status === "running" ? "var(--color-success)" : "var(--color-warning)" }}
                />
              )}
            </button>
          );
        })}

        <div className="flex-1" />

        {/* Settings gear */}
        {onOpenSettings && (
          <button
            onClick={onOpenSettings}
            className="w-8 h-8 flex items-center justify-center hover:bg-[#1A1A1A] text-[#555] hover:text-[#E0E0E0] transition-colors mb-2"
            title="Global settings"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" /><circle cx="12" cy="12" r="3" />
            </svg>
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col w-64 bg-[#0C0C0C] border-r border-[#222] shrink-0 h-full">
      {/* Header */}
      <div className="h-14 flex items-center justify-between px-4 border-b border-[#222]">
        <div className="flex items-center gap-2">
          <BrainCog className="w-5 h-5 shrink-0" style={{ color: "var(--color-accent)" }} />
          <span className="font-mono font-bold tracking-widest text-sm">
            <span className="text-[var(--color-text-primary)]">SWARM</span><span className="text-[var(--color-accent)]">WEAVER</span><span className="animate-pulse text-[var(--color-accent)] ml-0.5 font-normal">_</span>
          </span>
        </div>
        <button
          onClick={() => setCollapsed(true)}
          className="w-7 h-7 flex items-center justify-center hover:bg-[#1A1A1A] transition-colors text-[#555] hover:text-[#E0E0E0]"
          title="Collapse sidebar"
        >
          <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="m15 18-6-6 6-6" />
          </svg>
        </button>
      </div>

      {/* New session button */}
      <div className="p-4">
        <button
          onClick={onNewTab}
          className="w-full bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-[#0C0C0C] font-bold py-2.5 flex items-center justify-center gap-2 transition-colors text-[13px]"
        >
          <ActiveModeIcon className="w-4 h-4" />
          <span>+ New Session</span>
        </button>
      </div>

      {/* Sessions label */}
      <div className="px-4 pb-2">
        <span className="text-[#555] text-xs uppercase tracking-widest">
          Sessions ({tabs.length})
        </span>
      </div>

      {/* Sessions list */}
      <div className="flex-1 overflow-y-auto tui-scrollbar px-2 pb-3 space-y-1">
        {tabs.map((tab) => {
          const isActive = tab.id === activeTabId;
          const modeColor = tab.mode ? MODE_COLORS[tab.mode] : "var(--color-text-muted)";
          const TabModeIcon = (tab.mode ? MODE_ICONS[tab.mode] : MODE_ICONS.feature) as React.ComponentType<{ className?: string; style?: React.CSSProperties }>;

          return (
            <div
              key={tab.id}
              role="button"
              tabIndex={0}
              onClick={() => onSelectTab(tab.id)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelectTab(tab.id);
                }
              }}
              className={`group relative flex items-start gap-3 p-3 cursor-pointer select-none transition-colors ${
                isActive
                  ? "bg-[#1A1A1A] border border-[#333]"
                  : "border border-transparent hover:bg-[#1A1A1A] hover:border-[#333]"
              }`}
            >
              {/* Mode icon */}
              <div
                className="w-5 h-5 flex items-center justify-center shrink-0 mt-0.5"
                style={{ color: modeColor }}
              >
                <TabModeIcon className="w-3.5 h-3.5" />
              </div>

              {/* Session info */}
              <div className="flex-1 min-w-0">
                <span
                  className={`text-sm truncate block ${
                    isActive
                      ? "text-[#E0E0E0]"
                      : "text-[#888]"
                  }`}
                >
                  {tab.label}
                </span>
                <div className="flex items-center gap-1.5 mt-1">
                  <SessionStatusIndicator status={tab.status} />
                  <span className="text-[11px] text-[#555]">
                    {relativeTime(tab.createdAt)}
                  </span>
                </div>
              </div>

              {/* Close button (on hover) */}
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onCloseTab(tab.id);
                }}
                className="p-1 opacity-0 group-hover:opacity-60 hover:!opacity-100 text-[#555] hover:text-[#E0E0E0] transition-all shrink-0"
                title="Close session"
              >
                <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          );
        })}
      </div>

      {/* Settings button */}
      {onOpenSettings && (
        <button
          onClick={onOpenSettings}
          className="mx-4 mb-2 flex items-center gap-2.5 px-3 py-2 border border-[#222] hover:border-[#444] hover:bg-[#1A1A1A] text-[#888] hover:text-[#E0E0E0] transition-colors"
        >
          <svg className="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" /><circle cx="12" cy="12" r="3" />
          </svg>
          <span className="text-xs font-mono">Settings</span>
        </button>
      )}

      {/* Footer */}
      <div className="p-4 border-t border-[#222] flex items-center text-[#888]">
        <div className="w-8 h-8 border border-[#333] bg-[#121212] flex items-center justify-center mr-3 text-[#E0E0E0] text-xs">
          N
        </div>
        <div className="text-xs">
          <div className="text-[#E0E0E0]">User_Ctrl</div>
          <div className="text-[#555]">
            <kbd className="font-mono text-[10px]">Ctrl+N</kbd> new session
          </div>
        </div>
      </div>
    </div>
  );
}
