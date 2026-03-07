"use client";

import { useState, useEffect, useRef } from "react";
import type { ToolOperationItem } from "../../hooks/useActivityFeed";
import { detectLanguage, highlightToSpans } from "../../utils/syntaxHighlight";
import { computeLineDiff } from "../../utils/lineDiff";

// ── Tool label + color map ──

const TOOL_META: Record<string, { label: string }> = {
  Read:  { label: "Read"    },
  Edit:  { label: "Edit"    },
  Bash:  { label: "Execute" },
  Write: { label: "Create"  },
  Glob:  { label: "Search"  },
  Grep:  { label: "Grep"    },
  // Orchestrator MCP tools — friendly labels
  "mcp__orchestrator_tools__spawn_worker": { label: "Spawn worker" },
  "mcp__orchestrator_tools__merge_worker": { label: "Merge worker" },
  "mcp__orchestrator_tools__wait_seconds": { label: "Wait" },
  "mcp__orchestrator_tools__list_workers": { label: "List workers" },
  "mcp__orchestrator_tools__get_worker_updates": { label: "Worker updates" },
  "mcp__orchestrator_tools__terminate_worker": { label: "Terminate worker" },
  "mcp__orchestrator_tools__reassign_tasks": { label: "Reassign tasks" },
  "mcp__orchestrator_tools__get_task_status": { label: "Task status" },
  "mcp__orchestrator_tools__send_directive": { label: "Send directive" },
  "mcp__orchestrator_tools__signal_complete": { label: "Signal complete" },
  // Worker MCP tools — friendly labels
  "mcp__worker_tools__get_my_tasks": { label: "Get my tasks" },
  "mcp__worker_tools__start_task": { label: "Start task" },
  "mcp__worker_tools__complete_task": { label: "Complete task" },
  "mcp__worker_tools__report_blocker": { label: "Report blocker" },
  "mcp__worker_tools__report_to_orchestrator": { label: "Report to orchestrator" },
  // Puppeteer MCP tools — browser automation
  "mcp__puppeteer__puppeteer_navigate": { label: "Navigate" },
  "mcp__puppeteer__puppeteer_screenshot": { label: "Screenshot" },
  "mcp__puppeteer__puppeteer_click": { label: "Click" },
  "mcp__puppeteer__puppeteer_fill": { label: "Fill" },
  "mcp__puppeteer__puppeteer_select": { label: "Select" },
  "mcp__puppeteer__puppeteer_hover": { label: "Hover" },
  "mcp__puppeteer__puppeteer_evaluate": { label: "Evaluate" },
};

function getToolMeta(toolName: string) {
  if (TOOL_META[toolName]) return TOOL_META[toolName];
  // Fallback for other mcp__orchestrator_tools__* — humanize the action name
  if (toolName.startsWith("mcp__orchestrator_tools__")) {
    const action = toolName.replace("mcp__orchestrator_tools__", "").replace(/_/g, " ");
    return { label: action.charAt(0).toUpperCase() + action.slice(1) };
  }
  // Fallback for mcp__worker_tools__*
  if (toolName.startsWith("mcp__worker_tools__")) {
    const action = toolName.replace("mcp__worker_tools__", "").replace(/_/g, " ");
    return { label: action.charAt(0).toUpperCase() + action.slice(1) };
  }
  // Fallback for mcp__puppeteer__*
  if (toolName.startsWith("mcp__puppeteer__")) {
    const action = toolName.replace("mcp__puppeteer__", "").replace(/_/g, " ");
    return { label: action.charAt(0).toUpperCase() + action.slice(1) };
  }
  return { label: toolName };
}

// ── Parse structured tool input ──

interface ParsedToolInput {
  filePath?: string;
  command?: string;
  pattern?: string;
  description?: string;
  codeContent?: string;
  language?: string;
  oldString?: string;
  newString?: string;
  lineOffset?: number;
  lineLimit?: number;
  taskIds?: string[];
  fileScope?: string[];
  url?: string;
}

function tryParseJSON(raw: string): Record<string, unknown> | null {
  try {
    const obj = JSON.parse(raw);
    if (obj && typeof obj === "object") return obj as Record<string, unknown>;
  } catch { /* not JSON */ }
  return null;
}

function parseToolInput(toolName: string, rawInput: string): ParsedToolInput {
  const json = tryParseJSON(rawInput);

  const filePath = json
    ? ((json.file_path || json.path) as string | undefined)
    : rawInput.match(/(?:file_path|path)["']?\s*[:=]\s*["']?([^\s"'}{,\]]+)/)?.[1];

  const command = json
    ? (json.command as string | undefined)
    : rawInput.match(/['"]?command['"]?\s*[:=]\s*['"]([^'"]+)['"]/)?.[1];

  const description = json
    ? (json.description as string | undefined)
    : undefined;

  const codeContent = json ? (json.content as string | undefined) : undefined;

  const pattern = json
    ? (json.pattern as string | undefined)
    : rawInput.match(/['"]?pattern['"]?\s*[:=]\s*['"]([^'"]+)['"]/)?.[1];

  const oldString = json ? (json.old_string as string | undefined) : undefined;
  const newString = json ? (json.new_string as string | undefined) : undefined;
  const lineOffset = json ? (json.offset as number | undefined) : undefined;
  const lineLimit = json ? (json.limit as number | undefined) : undefined;

  // Orchestrator spawn_worker input
  let taskIds: string[] | undefined;
  let fileScope: string[] | undefined;
  if (toolName === "mcp__orchestrator_tools__spawn_worker" && json) {
    const ids = json.task_ids;
    taskIds = Array.isArray(ids) ? ids.map(String) : undefined;
    const scope = json.file_scope;
    fileScope = Array.isArray(scope) ? scope.map(String) : undefined;
  }

  const language = filePath ? detectLanguage(filePath.split("/").pop() || "") : undefined;
  const url = json ? (json.url as string | undefined) : undefined;

  return { filePath, command, description, codeContent, language, pattern, oldString, newString, lineOffset, lineLimit, taskIds, fileScope, url };
}

/** Parse spawn_worker tool result from outputLines (JSON string). */
function parseSpawnWorkerResult(outputLines: string[]): { workerId?: number; name?: string; success?: boolean } | null {
  const joined = outputLines.join("\n");
  try {
    const parsed = JSON.parse(joined) as Record<string, unknown>;
    if (parsed && typeof parsed === "object") {
      const workerId = typeof parsed.worker_id === "number" ? parsed.worker_id : undefined;
      const name = typeof parsed.name === "string" ? parsed.name : undefined;
      const success = parsed.success === true;
      return { workerId, name, success };
    }
  } catch {
    // Try to extract JSON from content block format (e.g. [{"type":"text","text":"{...}"}])
    const jsonMatch = joined.match(/\{"success"\s*:\s*true[^}]*"worker_id"\s*:\s*\d+/);
    if (jsonMatch) {
      const objMatch = joined.match(/\{[\s\S]*"worker_id"\s*:\s*(\d+)[\s\S]*"name"\s*:\s*"([^"]+)"/);
      if (objMatch) {
        return { workerId: parseInt(objMatch[1], 10), name: objMatch[2], success: true };
      }
    }
  }
  return null;
}

/** Extract and format blocked/error content — handles Python repr and JSON. */
function tryExtractAndFormatBlockedContent(raw: string): { lines: string[]; language: string } | null {
  if (!raw || !raw.trim()) return null;
  let extracted = raw;

  // Python repr: [{'type': 'text', 'text': '...'}] — extract inner text
  const reprMatch = raw.match(/'text'\s*:\s*['"]([^'"]*(?:\\.[^'"]*)*)['"]/);
  if (reprMatch) {
    try {
      extracted = reprMatch[1].replace(/\\n/g, "\n").replace(/\\"/g, '"');
    } catch {
      /* use raw */
    }
  }
  // Also try JSON array of content blocks
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (Array.isArray(parsed)) {
      const texts: string[] = [];
      for (const block of parsed) {
        if (block && typeof block === "object" && "text" in block && typeof (block as { text: string }).text === "string") {
          texts.push((block as { text: string }).text);
        }
      }
      if (texts.length > 0) extracted = texts.join("\n");
    }
  } catch {
    /* not JSON array */
  }

  // Pretty-print if valid JSON
  try {
    const obj = JSON.parse(extracted) as unknown;
    const formatted = JSON.stringify(obj, null, 2);
    return { lines: formatted.split("\n"), language: "json" };
  } catch {
    /* not JSON */
  }

  // Return as plain text lines
  return { lines: extracted.split("\n"), language: "plain" };
}

// ── Main component ──

interface ToolOperationCardProps {
  item: ToolOperationItem;
  collapsed: boolean;
  onToggle: () => void;
}

export function ToolOperationCard({ item, collapsed, onToggle }: ToolOperationCardProps) {
  const meta = getToolMeta(item.toolName);
  const isActive = item.result === "active";
  const [elapsed, setElapsed] = useState(0);
  const startRef = useRef(Date.now());

  useEffect(() => {
    if (!isActive) return;
    startRef.current = Date.now();
    const timer = setInterval(() => {
      setElapsed((Date.now() - startRef.current) / 1000);
    }, 100);
    return () => clearInterval(timer);
  }, [isActive]);

  const parsed = item.input ? parseToolInput(item.toolName, item.input) : null;

  const displayDuration = item.duration
    ? `${item.duration.toFixed(1)}s`
    : isActive
      ? `${elapsed.toFixed(1)}s`
      : null;

  // ── Content line ──
  const isSpawnWorker = item.toolName === "mcp__orchestrator_tools__spawn_worker";
  const spawnResult = isSpawnWorker && item.outputLines.length > 0
    ? parseSpawnWorkerResult(item.outputLines)
    : null;

  const superseded = !!item.supersededByWorkerSpawned;

  let contentDisplay = "";
  if (item.toolName === "Bash" && parsed?.command) {
    contentDisplay = parsed.command;
  } else if (isSpawnWorker) {
    if (superseded) {
      contentDisplay = "Spawned ✓";
    } else if (spawnResult?.success && spawnResult.workerId != null) {
      const name = spawnResult.name ?? `worker-${spawnResult.workerId}`;
      const tasks = parsed?.taskIds?.length
        ? parsed.taskIds.join(", ")
        : "";
      contentDisplay = tasks ? `${name} — ${tasks}` : `${name} spawned`;
    } else if (parsed?.taskIds?.length) {
      const tasks = parsed.taskIds.join(", ");
      const scope = parsed.fileScope?.length
        ? ` → ${parsed.fileScope.join(", ")}`
        : "";
      contentDisplay = `${tasks}${scope}`;
    }
  } else if (item.toolName === "mcp__puppeteer__puppeteer_screenshot" && item.outputLines.length > 0) {
    const out = item.outputLines.join(" ");
    contentDisplay = /Screenshot\s+['\"][^'\"]*['\"]\s+taken\s+at/i.test(out)
      ? "Screenshot captured"
      : item.outputLines[0]?.slice(0, 60) || "Screenshot";
  } else if (item.toolName === "mcp__puppeteer__puppeteer_navigate" && parsed?.url) {
    contentDisplay = parsed.url;
  } else if (parsed?.filePath) {
    contentDisplay = parsed.filePath;
  } else if (parsed?.pattern) {
    contentDisplay = parsed.filePath
      ? `${parsed.pattern}  in ${parsed.filePath}`
      : parsed.pattern;
  }

  // Badge extras
  const hasOutputLines = item.outputLines.length > 0;
  const isFileOp = ["Read", "Write", "Edit"].includes(item.toolName);
  const lineCount = item.toolName === "Read" && hasOutputLines
    ? item.outputLines.length
    : null;
  const diffStat = item.toolName === "Edit" && parsed?.oldString && parsed?.newString
    ? (() => {
        const d = computeLineDiff(parsed.oldString!, parsed.newString!);
        const a = d.filter(x => x.type === "add").length;
        const r = d.filter(x => x.type === "remove").length;
        return { a, r };
      })()
    : null;

  // Code to show when expanded — hide raw JSON for spawn_worker when we have a clean summary
  const codeLanguage = isFileOp ? (parsed?.language || "plain") : "bash";
  const isNewFile = item.toolName === "Write" && !hasOutputLines && !!parsed?.codeContent;
  const codeToShow: string[] | null =
    isSpawnWorker && spawnResult?.success
      ? null
      : hasOutputLines
        ? item.outputLines
        : parsed?.codeContent
          ? parsed.codeContent.split("\n")
          : null;

  // Steering blocks: directives, not errors — use accent/info styling
  const isSteeringBlock =
    item.result === "blocked" &&
    /\[STEERING\]|\[DIRECTIVE FROM ORCHESTRATOR\]|Message from operator/i.test(item.errorMessage || "");

  // Status symbol — accent for success/active/directive, semantic only for errors
  const statusSymbol = isActive ? null
    : item.result === "success" ? "✓"
    : item.result === "error" ? "✗"
    : isSteeringBlock ? "◉"
    : item.result === "blocked" ? "!"
    : "–";
  const statusColor = isActive ? "var(--color-accent)"
    : item.result === "success" ? "var(--color-accent)"
    : item.result === "error" ? "var(--color-error)"
    : isSteeringBlock ? "var(--color-accent)"
    : item.result === "blocked" ? "var(--color-warning)"
    : "var(--color-text-muted)";

  return (
    <div className={`font-mono group border border-[var(--color-border-subtle)] mb-1 overflow-hidden ${!collapsed ? "bg-[var(--color-surface-1)]" : "bg-[var(--color-surface-1)] hover:border-[var(--color-border-default)] transition-colors"}`}>
      {/* ── Header row ── */}
      <button
        onClick={onToggle}
        className="w-full px-4 py-1.5 flex items-center text-left hover:bg-[var(--color-surface-2)] transition-colors cursor-pointer"
      >
        {/* Status dot / symbol */}
        <span
          className={`text-[10px] shrink-0 mr-2.5 ${isActive ? "animate-pulse" : ""}`}
          style={{ color: statusColor }}
        >
          {isActive ? "●" : statusSymbol}
        </span>

        {/* Tool name label */}
        <span
          className="shrink-0 text-[13px] font-bold mr-3 text-[var(--color-accent)]"
          style={{ minWidth: "5rem" }}
        >
          {meta.label}
        </span>

        {/* DIRECTIVE badge when steering block */}
        {isSteeringBlock && (
          <span className="text-[10px] px-1.5 py-0.5 font-mono font-medium shrink-0 mr-2 text-[var(--color-accent)] border border-[var(--color-accent)]/40 bg-[var(--color-accent)]/10">
            DIRECTIVE
          </span>
        )}
        {/* BLOCKED badge for capability/security blocks (not steering) */}
        {item.result === "blocked" && !isSteeringBlock && (
          <span className="text-[10px] px-1.5 py-0.5 font-mono font-medium shrink-0 mr-2 text-[var(--color-warning)] border border-[var(--color-warning)]/40 bg-[var(--color-warning)]/10">
            BLOCKED
          </span>
        )}
        {/* BLOCKED badge for capability/security blocks (non-steering) */}
        {item.result === "blocked" && !isSteeringBlock && (
          <span className="text-[10px] px-1.5 py-0.5 font-mono font-medium shrink-0 mr-2 text-[var(--color-warning)] border border-[var(--color-warning)]/40 bg-[var(--color-warning)]/10">
            BLOCKED
          </span>
        )}

        {/* Content (path or command) */}
        <span className="text-[var(--color-text-secondary)] text-[12px] truncate flex-1 leading-5 mr-3">
          {contentDisplay}
        </span>

        {/* Badges */}
        {lineCount !== null && (
          <span className="text-[var(--color-text-muted)] text-[11px] shrink-0 mr-3 tabular-nums">
            {lineCount} lines
          </span>
        )}
        {diffStat && (
          <span className="text-[11px] shrink-0 mr-3 font-mono">
            <span style={{ color: "var(--color-success)" }}>+{diffStat.a}</span>
            <span className="text-[var(--color-border-default)] mx-1">/</span>
            <span style={{ color: "var(--color-error)" }}>−{diffStat.r}</span>
          </span>
        )}
        {displayDuration && (
          <span
            className="text-[11px] shrink-0 mr-3 tabular-nums font-mono"
            style={{ color: isActive ? "var(--color-accent)" : "var(--color-text-muted)" }}
          >
            {displayDuration}
          </span>
        )}

        {/* Chevron */}
        <span className="text-[var(--color-border-default)] group-hover:text-[var(--color-text-secondary)] transition-colors text-[13px] shrink-0 select-none">
          {collapsed ? "›" : "‹"}
        </span>
      </button>

      {/* ── Expanded body ── */}
      {!collapsed && (
        <div className="border-t border-[var(--color-surface-2)]">
          {/* Full file path */}
          {parsed?.filePath && isFileOp && (
            <div className="px-4 py-1.5 border-b border-[var(--color-surface-2)]">
              <span className="text-[11px] text-[var(--color-text-muted)] font-mono">{parsed.filePath}</span>
              {parsed.lineOffset !== undefined && (
                <span className="text-[var(--color-border-default)] text-[11px] ml-3">
                  offset {parsed.lineOffset}{parsed.lineLimit !== undefined ? `, limit ${parsed.lineLimit}` : ""}
                </span>
              )}
            </div>
          )}

          {/* Bash full command */}
          {item.toolName === "Bash" && parsed?.command && (
            <div className="px-4 py-2 border-b border-[var(--color-surface-2)]">
              <pre className="text-[12px] text-[var(--color-text-secondary)] font-mono whitespace-pre-wrap break-all leading-relaxed">
                <span className="text-[var(--color-accent)] select-none">$ </span>
                {parsed.command}
              </pre>
              {parsed.description && (
                <p className="text-[11px] text-[var(--color-text-muted)] mt-1">{parsed.description}</p>
              )}
            </div>
          )}

          {/* Edit diff */}
          {item.toolName === "Edit" && parsed?.oldString && parsed?.newString && (
            <div className="font-mono text-[12px] leading-[1.6]">
              {computeLineDiff(parsed.oldString, parsed.newString).map((dl, i) => (
                <div
                  key={i}
                  className={
                    dl.type === "remove"
                      ? "px-4 bg-[#1A0808] border-l-2 border-[var(--color-error)]/50"
                      : dl.type === "add"
                        ? "px-4 bg-[#081A0A] border-l-2 border-[var(--color-success)]/50"
                        : "px-4 border-l-2 border-transparent"
                  }
                >
                  <span className={`select-none mr-3 ${
                    dl.type === "remove" ? "text-[var(--color-error)]/50"
                      : dl.type === "add" ? "text-[var(--color-success)]/50"
                        : "text-[var(--color-border-subtle)]"
                  }`}>
                    {dl.type === "remove" ? "−" : dl.type === "add" ? "+" : " "}
                  </span>
                  <span className={
                    dl.type === "remove" ? "text-[var(--color-error)]/80"
                      : dl.type === "add" ? "text-[var(--color-success)]/80"
                        : "text-[var(--color-text-muted)]"
                  }>
                    {dl.text}
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* Code / file content */}
          {codeToShow && codeToShow.length > 0 && (
            <CodeBlock
              lines={codeToShow}
              language={codeLanguage}
              maxLines={30}
              isNewFile={isNewFile}
            />
          )}

          {/* Error / directive message — extract and format JSON/repr when possible */}
          {item.errorMessage && (() => {
            const formatted = tryExtractAndFormatBlockedContent(item.errorMessage);
            if (formatted) {
              return (
                <CodeBlock
                  lines={formatted.lines}
                  language={formatted.language}
                  maxLines={30}
                />
              );
            }
            return (
              <div className="px-4 py-3">
                <pre className={`text-[12px] font-mono whitespace-pre-wrap break-all leading-relaxed ${isSteeringBlock ? "text-[var(--color-text-secondary)]" : "text-[var(--color-error)]"}`}>
                  {item.errorMessage}
                </pre>
              </div>
            );
          })()}
        </div>
      )}
    </div>
  );
}

// ── Code block with syntax highlighting ──

function CodeBlock({
  lines,
  language,
  maxLines,
  isNewFile,
}: {
  lines: string[];
  language: string;
  maxLines: number;
  isNewFile?: boolean;
}) {
  const [showAll, setShowAll] = useState(false);
  const hasMore = lines.length > maxLines;
  const visible = showAll ? lines : lines.slice(0, maxLines);

  return (
    <div className="bg-[var(--color-surface-base)] overflow-x-auto">
      <table className="w-full text-[12px] font-mono leading-5">
        <tbody>
          {visible.map((line, i) => (
            <tr
              key={i}
              className={isNewFile ? "bg-[var(--color-success)]/[0.03]" : "hover:bg-[var(--color-surface-1)]"}
            >
              {isNewFile && (
                <td className="text-right select-none pl-4 pr-1 py-0 w-6 text-[11px] text-[var(--color-success)] opacity-30">
                  +
                </td>
              )}
              <td className="text-right text-[var(--color-border-subtle)] select-none pl-4 pr-3 py-0 w-10 text-[11px]">
                {i + 1}
              </td>
              <td
                className={`pr-4 py-0 whitespace-pre overflow-x-auto ${
                  isNewFile ? "border-l border-[var(--color-success)]/20" : ""
                }`}
              >
                {highlightToSpans(line, language)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {hasMore && !showAll && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            setShowAll(true);
          }}
          className="w-full px-4 py-1.5 text-[12px] text-[var(--color-text-muted)] hover:text-[var(--color-accent)] text-center border-t border-[var(--color-surface-2)] transition-colors font-mono"
        >
          ↓ {lines.length - maxLines} more lines
        </button>
      )}
    </div>
  );
}
