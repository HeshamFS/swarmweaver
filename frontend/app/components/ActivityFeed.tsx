"use client";

import { useRef, useEffect, useState, useCallback, useMemo } from "react";
import type { AgentEvent } from "../hooks/useSwarmWeaver";
import { type ActivityItem, type ActivityFilter, type ToolOperationItem } from "../hooks/useActivityFeed";
import { useNativeActivityFeed } from "../hooks/useNativeActivityFeed";
import { ToolOperationCard } from "./feed/ToolOperationCard";
import { InlineFilePreview } from "./feed/InlineFilePreview";
import { AgentMessageBlock } from "./feed/AgentMessageBlock";
import { UserMessageBlock } from "./feed/UserMessageBlock";
import { PhaseMarkerBlock } from "./feed/PhaseMarkerBlock";
import { ErrorBlock } from "./feed/ErrorBlock";
import { VerificationBlock } from "./feed/VerificationBlock";

const SCROLL_BOTTOM_THRESHOLD = 150;

interface ActivityFeedProps {
  output: string[];
  events: AgentEvent[];
  className?: string;
  /** undefined = show all agents, null = main/orchestrator only, number = specific worker */
  filterWorkerId?: number | null;
}

const FILTER_BUTTONS: { key: ActivityFilter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "tools", label: "Tools" },
  { key: "files", label: "Files" },
  { key: "errors", label: "Errors" },
];

const FILE_TOOLS = ["Read", "Write", "Edit", "NotebookEdit", "NotebookRead", "Glob"];

function matchesFilter(item: ActivityItem, filter: ActivityFilter): boolean {
  if (filter === "all") return true;
  if (filter === "tools") return item.type === "tool_operation";
  if (filter === "files") {
    if (item.type === "file_change") return true;
    if (item.type === "tool_operation") {
      return FILE_TOOLS.includes((item as ToolOperationItem).toolName);
    }
    return false;
  }
  if (filter === "errors") return item.type === "error" || item.type === "verification";
  return true;
}

export function ActivityFeed({ output, events, className = "", filterWorkerId }: ActivityFeedProps) {
  // Always use native SDK feed — subprocess mode has been removed
  const { items, toggleCollapse, collapseAll, expandAll } = useNativeActivityFeed(events, output);
  const [filter, setFilter] = useState<ActivityFilter>("all");
  const [showJumpButton, setShowJumpButton] = useState(false);
  const [collapsedSessions, setCollapsedSessions] = useState<Set<number>>(new Set());

  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const isNearBottomRef = useRef(true);

  // Filter items by type AND by agent/worker
  const filteredItems = useMemo(
    () => items.filter((item) => {
      if (!matchesFilter(item, filter)) return false;
      if (filterWorkerId === undefined) return true; // show all agents
      if (filterWorkerId === null) return item.workerId == null; // main/orchestrator
      return item.workerId === filterWorkerId; // specific worker
    }),
    [items, filter, filterWorkerId]
  );

  // Group items by sessionIndex
  const sessionGroups = useMemo(() => {
    const groups: { sessionIndex: number; items: ActivityItem[] }[] = [];
    for (const item of filteredItems) {
      const idx = item.sessionIndex ?? 0;
      const last = groups[groups.length - 1];
      if (last && last.sessionIndex === idx) {
        last.items.push(item);
      } else {
        groups.push({ sessionIndex: idx, items: [item] });
      }
    }
    return groups;
  }, [filteredItems]);

  const toggleSession = useCallback((sessionIdx: number) => {
    setCollapsedSessions((prev) => {
      const next = new Set(prev);
      if (next.has(sessionIdx)) {
        next.delete(sessionIdx);
      } else {
        next.add(sessionIdx);
      }
      return next;
    });
  }, []);

  // Find the nearest scrollable ancestor for scroll tracking
  const getScrollParent = useCallback((): HTMLElement | null => {
    let el = scrollRef.current?.parentElement;
    while (el) {
      const style = getComputedStyle(el);
      if (style.overflowY === "auto" || style.overflowY === "scroll") return el;
      el = el.parentElement;
    }
    return null;
  }, []);

  // Auto-scroll: only if user is near the bottom
  useEffect(() => {
    if (isNearBottomRef.current && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [filteredItems.length]);

  // Track scroll position on the parent scroll container
  useEffect(() => {
    const scrollEl = getScrollParent();
    if (!scrollEl) return;
    const onScroll = () => {
      const distFromBottom = scrollEl.scrollHeight - scrollEl.scrollTop - scrollEl.clientHeight;
      isNearBottomRef.current = distFromBottom < SCROLL_BOTTOM_THRESHOLD;
      setShowJumpButton(!isNearBottomRef.current && filteredItems.length > 10);
    };
    scrollEl.addEventListener("scroll", onScroll, { passive: true });
    return () => scrollEl.removeEventListener("scroll", onScroll);
  }, [filteredItems.length, getScrollParent]);

  const jumpToLatest = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    isNearBottomRef.current = true;
    setShowJumpButton(false);
  }, []);

  return (
    <div className={`relative ${className}`}>
      {/* Toolbar — sticky so filters stay visible when scrolling */}
      <div className="flex items-center justify-between px-6 h-11 text-sm font-mono border-b border-[var(--color-border-subtle)] bg-[var(--color-surface-base)] sticky top-0 z-10">
        {/* Filter buttons */}
        <div className="flex items-center gap-6">
          {FILTER_BUTTONS.map(({ key, label }) => (
            <button
              key={key}
              onClick={() => setFilter(key)}
              className={`py-2.5 transition-colors uppercase tracking-wider ${
                filter === key
                  ? "text-[var(--color-accent)] border-b-2 border-[var(--color-accent)] font-bold"
                  : "text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
              }`}
            >
              {label}
              {key === "errors" && (() => {
                const visibleErrors = items.filter((i) => {
                  if (i.type !== "error") return false;
                  if (filterWorkerId === undefined) return true;
                  if (filterWorkerId === null) return i.workerId == null;
                  return i.workerId === filterWorkerId;
                });
                return visibleErrors.length > 0 ? (
                  <span className="ml-1 text-[var(--color-error)] font-bold">
                    {visibleErrors.length}
                  </span>
                ) : null;
              })()}
            </button>
          ))}
        </div>

        {/* Collapse/Expand controls */}
        <div className="flex items-center gap-5">
          <button
            onClick={collapseAll}
            className="text-[var(--color-text-secondary)] hover:text-[var(--color-accent)] transition-colors uppercase tracking-wider"
            title="Collapse all current items"
          >
            Collapse
          </button>
          <button
            onClick={expandAll}
            className="text-[var(--color-text-secondary)] hover:text-[var(--color-accent)] transition-colors uppercase tracking-wider"
            title="Expand all; keep new items expanded from now on"
          >
            Expand
          </button>
        </div>
      </div>

      {/* Feed content — scrolling handled by parent container */}
      <div
        ref={scrollRef}
        className="px-6 py-4 space-y-1"
      >
        {filteredItems.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center py-12">
            <svg className="w-8 h-8 text-text-muted mb-3 opacity-50" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <p className="text-xs text-text-muted">Waiting for agent output...</p>
          </div>
        ) : sessionGroups.length <= 1 ? (
          // Single session — render items directly
          filteredItems.map((item) => (
            <div key={item.id}>
              <ActivityItemRenderer
                item={item}
                onToggle={() => toggleCollapse(item.id)}
              />
            </div>
          ))
        ) : (
          // Multiple sessions — wrap older ones in collapsible groups
          sessionGroups.map((group, gi) => {
            const isLatest = gi === sessionGroups.length - 1;
            const isCollapsed = collapsedSessions.has(group.sessionIndex);

            if (isLatest) {
              // Active session — always expanded, no wrapper
              return (
                <div key={`session-active-${group.sessionIndex}`} className="contents">
                  {group.items.map((item) => (
                    <div key={item.id}>
                      <ActivityItemRenderer
                        item={item}
                        onToggle={() => toggleCollapse(item.id)}
                      />
                    </div>
                  ))}
                </div>
              );
            }

            // Previous session — collapsible wrapper
            return (
              <div
                key={`session-${group.sessionIndex}`}
                className="border border-[var(--color-border-subtle)] bg-[var(--color-surface-1)] overflow-hidden mb-1"
              >
                <button
                  onClick={() => toggleSession(group.sessionIndex)}
                  className="w-full px-4 py-2.5 flex items-center gap-3 text-left cursor-pointer group"
                >
                  {/* Session icon */}
                  <span className="text-[var(--color-accent)] font-mono shrink-0">{"\u25A1"}</span>

                  <span className="text-[13px] font-mono font-medium text-[var(--color-text-secondary)]">
                    Session {group.sessionIndex + 1}
                  </span>

                  <span className="text-[11px] text-[var(--color-text-muted)] font-mono tabular-nums">
                    {group.items.length} {group.items.length === 1 ? "item" : "items"}
                  </span>

                  <div className="flex-1" />

                  {/* Chevron */}
                  <span
                    className="text-[var(--color-text-muted)] group-hover:text-[var(--color-accent)] transition-colors shrink-0"
                  >
                    {isCollapsed ? "\u203A" : "\u2039"}
                  </span>
                </button>

                {!isCollapsed && (
                  <div className="px-3 py-2 space-y-1 border-t border-[var(--color-border-subtle)] bg-[var(--color-surface-base)]">
                    {group.items.map((item) => (
                      <div key={item.id}>
                        <ActivityItemRenderer
                          item={item}
                          onToggle={() => toggleCollapse(item.id)}
                        />
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })
        )}
        <div ref={bottomRef} />
      </div>

      {/* Jump to latest button */}
      {showJumpButton && (
        <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-10">
          <button
            onClick={jumpToLatest}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-[var(--color-accent)] text-[var(--color-surface-base)] text-xs font-bold shadow-lg hover:bg-[var(--color-accent-hover)] transition-colors"
          >
            <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="6 9 12 15 18 9" />
            </svg>
            Jump to latest
          </button>
        </div>
      )}
    </div>
  );
}

// ── Item renderer ──

interface ActivityItemRendererProps {
  item: ActivityItem;
  onToggle: () => void;
}

function ActivityItemRenderer({ item, onToggle }: ActivityItemRendererProps) {
  switch (item.type) {
    case "tool_operation":
      return (
        <ToolOperationCard
          item={item}
          collapsed={item.collapsed}
          onToggle={onToggle}
        />
      );
    case "file_change":
      return (
        <InlineFilePreview
          item={item}
          collapsed={item.collapsed}
          onToggle={onToggle}
        />
      );
    case "agent_message":
      return <AgentMessageBlock item={item} />;
    case "user_message":
      return <UserMessageBlock item={item} />;
    case "phase_marker":
      return <PhaseMarkerBlock item={item} />;
    case "error":
      return (
        <ErrorBlock
          item={item}
          collapsed={item.collapsed}
          onToggle={onToggle}
        />
      );
    case "verification":
      return (
        <VerificationBlock
          item={item}
          collapsed={item.collapsed}
          onToggle={onToggle}
        />
      );
    default:
      return null;
  }
}
