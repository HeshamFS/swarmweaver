"use client";

import { useState } from "react";
import { ChevronRight, BrainCog } from "lucide-react";
import type { AgentMessageItem } from "../../hooks/useActivityFeed";
import { renderIconShortcode } from "../../utils/agentIcons";

interface AgentMessageBlockProps {
  item: AgentMessageItem;
}

function parseTableRow(line: string): string[] {
  return line.split("|").slice(1, -1).map((c) => c.trim());
}

// ── TUI helpers ──

const BOX_CHARS_ONLY = /^[\u2500-\u257F\u2550-\u256C\u2580-\u259F═─│┌┐└┘├┤┬┴┼╔╗╚╝╠╣╦╩╬\s]+$/;
const HAS_BOX_CHARS = /[\u2500-\u257F\u2550-\u256C═─│┌┐└┘├┤┬┴┼╔╗╚╝╠╣╦╩╬]/;
const TASK_ID_PATTERN = /\b(TASK-[A-Z0-9]+)\b/g;
/** MCP/tool names like mcp_orchestrator_tools_get_task_status or *_tools_* */
const MCP_TOOL_PATTERN = /\b(mcp_[a-z0-9_]+|[a-z0-9_]+_tools_[a-z0-9_]+)\b/gi;

/** Map Unicode status chars to Lucide icon shortcodes */
const STATUS_CHAR_TO_ICON: Record<string, string> = {
  "●": "check",
  "○": "circle",
  "◆": "square",
  "◇": "circle",
  "✓": "check",
  "✗": "x",
  "✘": "x",
  "⚡": "zap",
  "⚠": "alert",
};

/** True if the line is purely box-drawing border characters */
function isBoxBorderLine(line: string): boolean {
  return BOX_CHARS_ONLY.test(line) && HAS_BOX_CHARS.test(line);
}

/** True if line is a box content row (starts and ends with │ or |) */
function isBoxContentRow(line: string): boolean {
  const t = line.trim();
  const starts = t.startsWith("│") || t.startsWith("║") || t.startsWith("|");
  const ends = t.endsWith("│") || t.endsWith("║") || t.endsWith("|");
  return starts && ends && t.length > 1;
}

/** Extract [PREFIX] from start of line. Returns {prefix, rest} or null */
function extractLogPrefix(line: string): { prefix: string; rest: string } | null {
  const m = line.match(/^\[([A-Z][A-Z0-9 _\-]*)\]\s*/);
  if (!m) return null;
  return { prefix: m[1], rest: line.slice(m[0].length) };
}

/** Color TASK-XXX IDs and status indicator characters in a text string */
function applyTuiColors(text: string, keyBase: number): React.ReactNode[] {
  // Split on TASK-IDs and status chars, interleaving colored nodes
  const parts: React.ReactNode[] = [];
  let pos = 0;
  let idx = 0;

  // Build list of all matches with positions
  interface Span { start: number; end: number; node: React.ReactNode }
  const spans: Span[] = [];

  // TASK-XXX matches
  TASK_ID_PATTERN.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = TASK_ID_PATTERN.exec(text)) !== null) {
    spans.push({
      start: m.index,
      end: m.index + m[0].length,
      node: (
        <code key={`tid-${keyBase}-${idx++}`} className="px-1 py-0.5 bg-[var(--color-surface-2)] text-[var(--color-accent)] text-[0.85em] font-mono border border-[var(--color-border-default)]">
          {m[0]}
        </code>
      ),
    });
  }
  TASK_ID_PATTERN.lastIndex = 0;

  // MCP/tool name matches
  MCP_TOOL_PATTERN.lastIndex = 0;
  while ((m = MCP_TOOL_PATTERN.exec(text)) !== null) {
    spans.push({
      start: m.index,
      end: m.index + m[0].length,
      node: (
        <code key={`mcp-${keyBase}-${idx++}`} className="px-1 py-0.5 bg-[var(--color-surface-2)] text-[var(--color-accent)] text-[0.85em] font-mono border border-[var(--color-border-default)]">
          {m[0]}
        </code>
      ),
    });
  }
  MCP_TOOL_PATTERN.lastIndex = 0;

  // Status char matches → Lucide icons
  for (const [ch, iconName] of Object.entries(STATUS_CHAR_TO_ICON)) {
    let p = 0;
    while (true) {
      const found = text.indexOf(ch, p);
      if (found === -1) break;
      spans.push({
        start: found,
        end: found + ch.length,
        node: (
          <span key={`sc-${keyBase}-${idx++}`} className="inline-flex align-middle">
            {renderIconShortcode(iconName, "", 12)}
          </span>
        ),
      });
      p = found + ch.length;
    }
  }

  // Sort by position, skip overlapping
  spans.sort((a, b) => a.start - b.start);
  const used: Span[] = [];
  let lastEnd = 0;
  for (const s of spans) {
    if (s.start >= lastEnd) {
      used.push(s);
      lastEnd = s.end;
    }
  }

  pos = 0;
  for (const s of used) {
    if (s.start > pos) parts.push(text.slice(pos, s.start));
    parts.push(s.node);
    pos = s.end;
  }
  if (pos < text.length) parts.push(text.slice(pos));

  return parts.length > 0 ? parts : [text];
}

/** Normalize common emojis to icon shortcodes for backward compatibility */
function normalizeEmojis(text: string): string {
  const emojiToShortcode: Record<string, string> = {
    "✅": ":check:",
    "✓": ":check:",
    "🚀": ":rocket:",
    "⛔": ":block:",
    "🤖": ":bot:",
    "⚡": ":zap:",
    "⚠️": ":alert:",
    "⚠": ":alert:",
  };
  let out = text;
  for (const [emoji, code] of Object.entries(emojiToShortcode)) {
    out = out.split(emoji).join(code);
  }
  return out;
}

function renderSimpleMarkdown(text: string): React.ReactNode[] {
  const normalized = normalizeEmojis(text);
  const lines = normalized.split("\n");
  const nodes: React.ReactNode[] = [];

  let i = 0;
  while (i < lines.length) {
    const line = lines[i];

    // ── Markdown table ──
    if (line.trim().startsWith("|") && line.trim().endsWith("|") && line.includes("|", 1)) {
      const tableLines: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) {
        tableLines.push(lines[i]);
        i++;
      }
      if (tableLines.length >= 2) {
        const headers = parseTableRow(tableLines[0]);
        // tableLines[1] is the separator row (|---|---|) — skip it
        const rows = tableLines.slice(2).map(parseTableRow);
        nodes.push(
          <div key={`tbl-${i}`} className="my-3 overflow-x-auto rounded border border-[var(--color-border-default)]">
            <table className="w-full font-mono text-xs border-collapse">
              <thead>
                <tr>
                  {headers.map((cell, ci) => (
                    <th
                      key={ci}
                      className="text-left px-3 py-1.5 text-[var(--color-accent)] border-b border-[var(--color-border-default)] font-bold uppercase tracking-wide text-[11px]"
                    >
                      {processInline(cell, i * 100 + ci)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, ri) => (
                  <tr key={ri} className="border-b border-[var(--color-surface-2)] hover:bg-[var(--color-surface-2)]/50 transition-colors">
                    {row.map((cell, ci) => (
                      <td key={ci} className="px-3 py-1 text-[var(--color-text-secondary)]">
                        {processInline(cell, i * 100 + ri * 20 + ci)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      }
      continue;
    }

    // ── Code block (``` fences) ──
    if (line.trimStart().startsWith("```")) {
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trimStart().startsWith("```")) {
        codeLines.push(lines[i]);
        i++;
      }
      i++;
      nodes.push(
        <div key={`cb-${i}`} className="my-2 bg-[var(--color-surface-base)] border border-[var(--color-border-default)] overflow-hidden">
          <pre className="p-3 text-xs font-mono text-[var(--color-text-secondary)] overflow-x-auto leading-relaxed whitespace-pre">
            {codeLines.join("\n")}
          </pre>
        </div>
      );
      continue;
    }

    // ── Blockquote (> ) ──
    if (line.trimStart().startsWith("> ")) {
      const quoteLines: string[] = [];
      while (i < lines.length && lines[i].trimStart().startsWith("> ")) {
        quoteLines.push(lines[i].trimStart().slice(2));
        i++;
      }
      nodes.push(
        <div
          key={`bq-${i}`}
          className="my-2 pl-3 border-l-2 border-[var(--color-accent)] text-[var(--color-text-secondary)]"
        >
          {quoteLines.map((ln, qi) => (
            <div key={qi} className="py-0.5 text-xs">
              {processInline(ln, i * 100 + qi)}
            </div>
          ))}
        </div>
      );
      continue;
    }

    // ── Skip raw XML tags ──
    if (/^<\/?[\w_]+>/.test(line.trim())) {
      i++;
      continue;
    }

    // ── Horizontal rule (--- or ===) ──
    if (/^-{3,}$/.test(line.trim()) || /^={3,}$/.test(line.trim())) {
      nodes.push(<div key={i} className="my-3 h-px bg-[var(--color-border-default)]" />);
      i++;
      continue;
    }

    // ── Headers (# / ## / ###) ──
    const headerMatch = line.match(/^(#{1,3})\s+(.+)/);
    if (headerMatch) {
      const level = headerMatch[1].length;
      const content = processInline(headerMatch[2], i);
      if (level === 1) {
        nodes.push(
          <div key={i} className="mt-4 mb-2 pb-1.5 border-b border-[var(--color-border-default)]">
            <span className="text-[var(--color-text-primary)] text-sm font-bold uppercase tracking-wider">{content}</span>
          </div>
        );
      } else if (level === 2) {
        nodes.push(
          <div key={i} className="mt-3 mb-1.5 flex items-center gap-2">
            <span className="text-[var(--color-accent)] shrink-0">{renderIconShortcode("square", "", 10)}</span>
            <span className="text-[var(--color-text-primary)] text-[13px] font-bold uppercase tracking-wider">{content}</span>
          </div>
        );
      } else {
        nodes.push(
          <div key={i} className="mt-2 mb-1 flex items-center gap-2">
            <span className="text-[var(--color-text-muted)] shrink-0">{renderIconShortcode("arrow", "", 10)}</span>
            <span className="text-[var(--color-text-primary)] text-xs font-bold uppercase tracking-wide">{content}</span>
          </div>
        );
      }
      i++;
      continue;
    }

    // ── Checkbox lines (- [x] / - [ ]) ──
    const checkMatch = line.match(/^-\s+\[([ xX])\]\s*(.*)/);
    if (checkMatch) {
      const checked = checkMatch[1] !== " ";
      const content = processInline(checkMatch[2], i);
      nodes.push(
        <div key={i} className="flex items-start gap-2.5 ml-2 py-0.5">
          <span className={`shrink-0 ${checked ? "text-[var(--color-success)]" : "text-[var(--color-text-muted)]"}`}>
            {checked ? renderIconShortcode("check", "", 12) : renderIconShortcode("square", "", 12)}
          </span>
          <span className={`text-xs ${checked ? "text-[var(--color-text-secondary)]" : "text-[var(--color-text-muted)]"}`}>{content}</span>
        </div>
      );
      i++;
      continue;
    }

    // ── Bullet lists (- / *) ──
    if (line.startsWith("- ") || line.startsWith("* ")) {
      if (line.slice(2).trim() === "") {
        i++;
        continue;
      }
      const content = processInline(line.slice(2), i);
      nodes.push(
        <div key={i} className="flex gap-2.5 ml-2 py-0.5">
          <span className="text-[var(--color-accent)] shrink-0">{renderIconShortcode("bullet", "", 10)}</span>
          <span className="text-xs">{content}</span>
        </div>
      );
      i++;
      continue;
    }

    // ── Numbered lists ──
    const numMatch = line.match(/^(\d+)\.\s+(.*)/);
    if (numMatch) {
      if (numMatch[2].trim() === "") {
        i++;
        continue;
      }
      const content = processInline(numMatch[2], i);
      nodes.push(
        <div key={i} className="flex gap-2.5 ml-2 py-0.5">
          <span className="text-[var(--color-text-muted)] shrink-0 text-xs font-bold">{numMatch[1]}.</span>
          <span className="text-xs">{content}</span>
        </div>
      );
      i++;
      continue;
    }

    // ── Empty line ──
    if (line.trim() === "") {
      nodes.push(<div key={i} className="h-1.5" />);
      i++;
      continue;
    }

    // ── TUI box border line (e.g. ┌─────┐ or ╔═════╗ or ├─────┤) ──
    if (isBoxBorderLine(line)) {
      nodes.push(
        <div key={i} className="py-0 leading-none font-mono text-xs text-[var(--color-border-default)] select-none">
          {line}
        </div>
      );
      i++;
      continue;
    }

    // ── TUI box content row (e.g. │ Worker 1  running │) ──
    if (isBoxContentRow(line)) {
      nodes.push(
        <div key={i} className="py-0 leading-snug font-mono text-xs">
          <span className="text-[var(--color-border-default)]">{line.slice(0, 1)}</span>
          <span className="text-[var(--color-text-secondary)]">{applyTuiColors(line.slice(1, -1), i * 1000)}</span>
          <span className="text-[var(--color-border-default)]">{line.slice(-1)}</span>
        </div>
      );
      i++;
      continue;
    }

    // ── Log prefix line: [ORCH], [WORKER-1], [SMART ORCH], [BUILDER] etc. ──
    const logPrefix = extractLogPrefix(line);
    if (logPrefix) {
      const prefixColors: Record<string, string> = {
        ORCH: "var(--color-accent)",
        ORCHESTRATOR: "var(--color-accent)",
        "SMART ORCH": "var(--color-accent)",
        WORKER: "var(--color-info)",
        BUILDER: "var(--color-info)",
        REVIEWER: "var(--color-success)",
        SCOUT: "var(--color-warning)",
        LEAD: "var(--color-mode-refactor)",
        MERGER: "var(--color-mode-refactor)",
        MARATHON: "var(--color-warning)",
        HOOK: "var(--color-text-muted)",
        BUDGET: "var(--color-success)",
        IDENTITY: "var(--color-text-secondary)",
      };
      // Check for prefix match (partial key match)
      let prefixColor = "var(--color-text-muted)";
      for (const [key, col] of Object.entries(prefixColors)) {
        if (logPrefix.prefix.startsWith(key) || logPrefix.prefix.includes(key)) {
          prefixColor = col;
          break;
        }
      }
      nodes.push(
        <div key={i} className="py-0.5 text-xs flex items-baseline gap-1.5">
          <span
            className="font-mono font-bold shrink-0 text-[10px]"
            style={{ color: prefixColor }}
          >
            [{logPrefix.prefix}]
          </span>
          <span className="text-[var(--color-text-secondary)]">{applyTuiColors(logPrefix.rest, i * 2000)}</span>
        </div>
      );
      i++;
      continue;
    }

    // ── Normal text (with TASK-ID, MCP tools, and status char coloring) ──
    const hasSpecial = TASK_ID_PATTERN.test(line) || MCP_TOOL_PATTERN.test(line) || Object.keys(STATUS_CHAR_TO_ICON).some((ch) => line.includes(ch));
    TASK_ID_PATTERN.lastIndex = 0;
    MCP_TOOL_PATTERN.lastIndex = 0;
    if (hasSpecial) {
      nodes.push(
        <div key={i} className="py-0.5 text-xs text-[var(--color-text-secondary)]">
          {applyTuiColors(line, i * 3000)}
        </div>
      );
      i++;
      continue;
    }

    // ── Plain text ──
    const rendered = processInline(line, i);
    nodes.push(<div key={i} className="py-0.5 text-xs">{rendered}</div>);
    i++;
  }

  return nodes;
}

function processInline(text: string, keyBase: number): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  let remaining = text;
  let idx = 0;

  while (remaining.length > 0) {
    const boldMatch = remaining.match(/\*\*(.+?)\*\*/);
    const codeMatch = remaining.match(/`([^`]+)`/);
    const linkMatch = remaining.match(/\[([^\]]+)\]\(([^)]+)\)/);
    const iconMatch = remaining.match(/:([a-z0-9_-]+):/);

    type InlineMatch = { index: number; length: number; node: React.ReactNode };
    const matches: InlineMatch[] = [];

    if (boldMatch && boldMatch.index !== undefined) {
      matches.push({
        index: boldMatch.index,
        length: boldMatch[0].length,
        node: <strong key={`${keyBase}-b-${idx}`} className="text-[var(--color-text-primary)] font-bold">{boldMatch[1]}</strong>,
      });
    }
    if (codeMatch && codeMatch.index !== undefined) {
      matches.push({
        index: codeMatch.index,
        length: codeMatch[0].length,
        node: (
          <code key={`${keyBase}-c-${idx}`} className="px-1.5 py-0.5 bg-[var(--color-surface-2)] text-[var(--color-accent)] text-[0.9em] font-mono border border-[var(--color-border-default)]">
            {codeMatch[1]}
          </code>
        ),
      });
    }
    if (linkMatch && linkMatch.index !== undefined) {
      matches.push({
        index: linkMatch.index,
        length: linkMatch[0].length,
        node: (
          <a
            key={`${keyBase}-l-${idx}`}
            href={linkMatch[2]}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[var(--color-accent)] underline underline-offset-2 hover:text-[var(--color-accent-hover)]"
          >
            {linkMatch[1]}
          </a>
        ),
      });
    }
    if (iconMatch && iconMatch.index !== undefined) {
      const shortcode = iconMatch[1];
      matches.push({
        index: iconMatch.index,
        length: iconMatch[0].length,
        node: (
          <span key={`${keyBase}-i-${idx}`} className="inline-flex align-middle">
            {renderIconShortcode(shortcode, "", 12)}
          </span>
        ),
      });
    }

    if (matches.length === 0) {
      parts.push(remaining);
      break;
    }

    matches.sort((a, b) => a.index - b.index);
    const best = matches[0];

    if (best.index > 0) {
      parts.push(remaining.slice(0, best.index));
    }
    parts.push(best.node);
    remaining = remaining.slice(best.index + best.length);
    idx++;
  }

  return parts;
}

export function AgentMessageBlock({ item }: AgentMessageBlockProps) {
  const [expanded, setExpanded] = useState(false);

  if (item.isThinking && item.thinkingText) {
    return (
      <div className="py-1 px-1 font-mono">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-1.5 text-[10px] text-[#666] hover:text-[#999] transition-colors w-full text-left group"
        >
          <ChevronRight
            className={`w-3 h-3 shrink-0 transition-transform ${expanded ? "rotate-90" : ""}`}
          />
          <BrainCog className="w-3 h-3 shrink-0 text-[#555] group-hover:text-[#777]" />
          <span className="uppercase tracking-wider font-medium">{item.text}</span>
        </button>
        {expanded && (
          <pre className="mt-2 ml-5 text-[11px] text-[#888] leading-relaxed whitespace-pre-wrap break-words max-h-[600px] overflow-y-auto tui-scrollbar">
            {item.thinkingText}
          </pre>
        )}
      </div>
    );
  }

  return (
    <div className="py-2 px-1 text-xs text-[var(--color-text-secondary)] leading-relaxed font-mono">
      {renderSimpleMarkdown(item.text)}
    </div>
  );
}
