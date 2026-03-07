"use client";

import { useState } from "react";
import type { FileChangeItem } from "../../hooks/useActivityFeed";
import { detectLanguage, highlightToSpans } from "../../utils/syntaxHighlight";
import { computeLineDiff } from "../../utils/lineDiff";

const ACTION_LABELS: Record<string, { label: string; color: string }> = {
  create: { label: "Created", color: "var(--color-success)" },
  edit: { label: "Edited", color: "var(--color-warning)" },
  read: { label: "Read", color: "var(--color-text-muted)" },
  delete: { label: "Deleted", color: "var(--color-error)" },
};

const MAX_VISIBLE_LINES = 20;

interface InlineFilePreviewProps {
  item: FileChangeItem;
  collapsed: boolean;
  onToggle: () => void;
}

export function InlineFilePreview({ item, collapsed, onToggle }: InlineFilePreviewProps) {
  const [showAll, setShowAll] = useState(false);
  const fileName = item.filePath.split("/").pop() || item.filePath;
  const shortPath = item.filePath.split("/").slice(-2).join("/");
  const language = detectLanguage(fileName);
  const actionInfo = ACTION_LABELS[item.action] || ACTION_LABELS.edit;

  const lines = item.content ? item.content.split("\n") : [];
  const hasMore = lines.length > MAX_VISIBLE_LINES;
  const visibleLines = showAll ? lines : lines.slice(0, MAX_VISIBLE_LINES);

  const hasDiff = item.action === "edit" && item.oldString && item.newString;
  const isCreate = item.action === "create" && lines.length > 0;

  return (
    <div className="border border-[#222] bg-[#121212] mb-1 group hover:border-[#444] transition-colors overflow-hidden">
      {/* Header */}
      <button
        onClick={onToggle}
        className="w-full px-4 py-3 flex items-center gap-3 text-left cursor-pointer"
      >
        {/* Orange prompt */}
        <span className="text-[var(--color-accent)] shrink-0 font-bold">{"\u25A0"}</span>

        {/* File name */}
        <span className="text-[13px] text-[#E0E0E0] font-mono font-bold truncate flex-1">{shortPath}</span>

        {/* Add/remove counts */}
        {(item.additions != null || item.deletions != null) && (
          <div className="flex items-center gap-2 text-[12px] font-mono shrink-0">
            {item.additions != null && item.additions > 0 && (
              <span className="text-[var(--color-success)]">+{item.additions}</span>
            )}
            {item.deletions != null && item.deletions > 0 && (
              <span className="text-[var(--color-error)]">-{item.deletions}</span>
            )}
          </div>
        )}

        {/* Action badge */}
        <span className="text-[12px] font-mono font-medium shrink-0" style={{ color: actionInfo.color }}>
          {actionInfo.label}
        </span>

        {/* Chevron */}
        <span className="text-[#555] group-hover:text-[#E0E0E0] transition-colors shrink-0">
          {collapsed ? "\u203A" : "\u2039"}
        </span>
      </button>

      {/* Expanded: Edit diff view — unified inline diff */}
      {!collapsed && hasDiff && (
        <div className="border-t border-[#222]">
          <div className="px-4 py-1.5 bg-[#0C0C0C] border-b border-[#222]">
            <span className="text-[11px] uppercase tracking-wider text-[#555] font-mono font-medium">Changes</span>
          </div>
          <div className="font-mono text-[13px] leading-6 overflow-x-auto">
            {computeLineDiff(item.oldString!, item.newString!).map((dl, i) => (
              <div
                key={i}
                className={
                  dl.type === "remove"
                    ? "px-4 bg-[var(--color-error)]/8 border-l-2 border-[var(--color-error)]"
                    : dl.type === "add"
                      ? "px-4 bg-[var(--color-success)]/8 border-l-2 border-[var(--color-success)]"
                      : "px-4 border-l-2 border-transparent"
                }
              >
                <span className={`select-none mr-3 opacity-50 ${
                  dl.type === "remove" ? "text-[var(--color-error)]"
                    : dl.type === "add" ? "text-[var(--color-success)]"
                      : "text-[#333]"
                }`}>
                  {dl.type === "remove" ? "-" : dl.type === "add" ? "+" : " "}
                </span>
                <span className={
                  dl.type === "remove" ? "text-[var(--color-error)]"
                    : dl.type === "add" ? "text-[var(--color-success)]"
                      : "text-[#888]"
                }>
                  {dl.text}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Expanded: Create (new file) — green highlighted content */}
      {!collapsed && isCreate && !hasDiff && (
        <div className="border-t border-[#222] bg-[#0C0C0C] overflow-x-auto">
          <table className="w-full text-[13px] font-mono leading-6">
            <tbody>
              {visibleLines.map((line, i) => (
                <tr key={i} className="bg-[var(--color-success)]/[0.04]">
                  <td className="text-right select-none pl-4 pr-1 py-0 w-8 text-[12px] text-[var(--color-success)] opacity-40">
                    +
                  </td>
                  <td className="text-right select-none pr-3 py-0 w-10 text-[12px] text-[var(--color-text-muted)] opacity-40">
                    {i + 1}
                  </td>
                  <td className="pr-4 py-0 whitespace-pre overflow-x-auto border-l-2 border-[var(--color-success)]/30">
                    {highlightToSpans(line, language)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* Show more button */}
          {hasMore && !showAll && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                setShowAll(true);
              }}
              className="w-full px-4 py-2 text-[13px] text-[var(--color-accent)] hover:text-[var(--color-accent-hover)] text-center border-t border-[#222] transition-colors font-medium font-mono"
            >
              Show {lines.length - MAX_VISIBLE_LINES} more lines
            </button>
          )}
        </div>
      )}

      {/* Expanded: Read — syntax-highlighted content */}
      {!collapsed && item.action === "read" && lines.length > 0 && (
        <div className="border-t border-[#222] bg-[#0C0C0C] overflow-x-auto">
          <table className="w-full text-[13px] font-mono leading-6">
            <tbody>
              {visibleLines.map((line, i) => (
                <tr key={i} className="hover:bg-[#1A1A1A]">
                  <td className="text-right text-[#555] select-none pl-4 pr-3 py-0 w-12 opacity-40 text-[12px]">
                    {i + 1}
                  </td>
                  <td className="pr-4 py-0 whitespace-pre overflow-x-auto">
                    {highlightToSpans(line, language)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* Show more button */}
          {hasMore && !showAll && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                setShowAll(true);
              }}
              className="w-full px-4 py-2 text-[13px] text-[var(--color-accent)] hover:text-[var(--color-accent-hover)] text-center border-t border-[#222] transition-colors font-medium font-mono"
            >
              Show {lines.length - MAX_VISIBLE_LINES} more lines
            </button>
          )}
        </div>
      )}

      {/* If no content and no diff but expanded, show the full path */}
      {!collapsed && lines.length === 0 && !hasDiff && (
        <div className="border-t border-[#222] px-4 py-3">
          <span className="text-[13px] text-[#555] font-mono">{item.filePath}</span>
        </div>
      )}
    </div>
  );
}
