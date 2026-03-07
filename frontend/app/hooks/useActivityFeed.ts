"use client";

import { useMemo, useRef, useState, useCallback } from "react";
import type { AgentEvent } from "./useSwarmWeaver";
import { computeLineDiff } from "../utils/lineDiff";

// ── Regex patterns mirroring backend services/events.py ──

const TOOL_CALL_RE = /^\[Tool:\s*(\w+)\]/;
const TOOL_INPUT_RE = /^\s+Input:\s*(.+)/;
const TOOL_DONE_RE = /^\s+\[Done\]/;
const TOOL_ERROR_RE = /^\s+\[Error\]\s*(.*)/;
const TOOL_BLOCKED_RE = /^\s+\[BLOCKED\]\s*(.*)/;
const SESSION_RE = /^\s*SESSION\s+(\d+):\s*(.+)/;
const VERIFY_RE = /^\[VERIFY\]\s*(.+)/;
const FILE_PATH_RE = /(?:file_path|path)["']?\s*[:=]\s*["']?([^\s"'}{,]+\.\w+)/;

// Session infrastructure noise — filtered from activity feed (already shown in UI)
const SESSION_NOISE_RE = /^(={3,}$|-{3,}$|Mode:\s+\w+\s+-\s|Project directory:|Project:|Model:|Max iterations:|Idea:|Flow:|Resume from|Attempting to resume|Resuming session|Using CLAUDE_CODE_OAUTH_TOKEN|Created security settings|\[SDK\]|\[CHAIN\]|\[IDENTITY\]|\[ARCHITECT\]|\[Phase\s|\[State\]|\[HOOK\]|\[BUDGET\]|\[Session saved|\[Session\s+\w+\s+saved|Checkpoint manager:|Continuing existing|Tasks:\s+\d+\/\d+\s+done\s+\[|Status:\s+\d+|By category:$|Mode:\s+\w+$|\[MARATHON\]|Sending prompt to Claude|Preparing next session|Agent will auto-continue)/;
// Bullet-prefixed infrastructure lines (- Sandbox enabled, - Filesystem restricted, etc.)
const SESSION_NOISE_BULLET_RE = /^-\s+(Sandbox enabled|Filesystem restricted|Bash commands restricted|MCP servers:|Checkpointing:|Subagents:|Audit logging:|Streaming:)/;
const CATEGORY_PROGRESS_RE = /^\s*[+\u2022]?\s*\w+\s+\d+\/\d+\s+\[/;
const XML_TAG_RE = /^<\/?[\w_]+>/;

// Detect true session restart (agent process restarted, not just a new phase)
const SESSION_RESTART_RE = /^(AUTONOMOUS CODING AGENT|---\s*End of previous session|---\s*Previous session)/;

// Vague "CODE" lines from orchestrator — filter out (treat as noise)
const VAGUE_CODE_RE = /^(:zap:\s*CODE|:code:)(\s*#\d+)?\s*$/i;

// ── Types ──

export type ActivityItemType =
  | "tool_operation"
  | "file_change"
  | "agent_message"
  | "user_message"
  | "phase_marker"
  | "error"
  | "verification";

export interface ActivityItemBase {
  id: string;
  type: ActivityItemType;
  timestamp: string;
  collapsed: boolean;
  sessionIndex?: number;
  /** worker_id from swarm events. null/undefined = orchestrator/main agent */
  workerId?: number | null;
}

export interface ToolOperationItem extends ActivityItemBase {
  type: "tool_operation";
  toolName: string;
  input: string;
  outputLines: string[];
  result: "success" | "error" | "blocked" | "active";
  errorMessage?: string;
  duration?: number;
  filePath?: string;
  /** When true, worker_spawned message is the canonical display; render tool card minimally */
  supersededByWorkerSpawned?: boolean;
}

export interface FileChangeItem extends ActivityItemBase {
  type: "file_change";
  filePath: string;
  action: "create" | "edit" | "read" | "delete";
  additions?: number;
  deletions?: number;
  content?: string;
  oldString?: string;
  newString?: string;
}

export interface AgentMessageItem extends ActivityItemBase {
  type: "agent_message";
  text: string;
  /** When true, renders as a collapsible thinking block with toggle arrow */
  isThinking?: boolean;
  /** Full thinking text (stored separately so `text` can hold the label) */
  thinkingText?: string;
}

export interface UserMessageItem extends ActivityItemBase {
  type: "user_message";
  text: string;
  steeringType?: string;
}

export interface PhaseMarkerItem extends ActivityItemBase {
  type: "phase_marker";
  phase: string;
  sessionNumber?: number;
}

export interface ErrorItem extends ActivityItemBase {
  type: "error";
  message: string;
  severity: "error" | "warning" | "blocked";
  recoveryHint?: string;
}

export interface VerificationItem extends ActivityItemBase {
  type: "verification";
  taskTitle: string;
  passed: boolean;
  output?: string;
}

export type ActivityItem =
  | ToolOperationItem
  | FileChangeItem
  | AgentMessageItem
  | UserMessageItem
  | PhaseMarkerItem
  | ErrorItem
  | VerificationItem;

// ── Filter types ──

export type ActivityFilter = "all" | "tools" | "files" | "errors";

// ── Helpers ──

let nextId = 0;
function makeId(): string {
  return `af-${++nextId}-${Date.now()}`;
}

function now(): string {
  return new Date().toISOString();
}

function inferFileAction(toolName: string): FileChangeItem["action"] {
  switch (toolName) {
    case "Read":
      return "read";
    case "Write":
      return "create";
    case "Edit":
      return "edit";
    default:
      return "edit";
  }
}

function summarizeToolInput(toolName: string, input: string): string {
  const fileMatch = input.match(FILE_PATH_RE);
  const filePath = fileMatch ? fileMatch[1] : null;

  switch (toolName) {
    case "Read":
      return filePath ? `Read ${filePath}` : "Read file";
    case "Edit":
      return filePath ? `Edit ${filePath}` : "Edit file";
    case "Write":
      return filePath ? `Write ${filePath}` : "Write file";
    case "Bash":
      return input.length > 80 ? input.slice(0, 77) + "..." : input;
    case "Glob":
      return `Search: ${input.length > 60 ? input.slice(0, 57) + "..." : input}`;
    case "Grep":
      return `Grep: ${input.length > 60 ? input.slice(0, 57) + "..." : input}`;
    default:
      return input.length > 80 ? input.slice(0, 77) + "..." : input;
  }
}

// ── Hook ──

export interface UseActivityFeedReturn {
  items: ActivityItem[];
  toggleCollapse: (id: string) => void;
  collapseAll: () => void;
  expandAll: () => void;
}

export function useActivityFeed(
  output: string[],
  events: AgentEvent[]
): UseActivityFeedReturn {
  // Track how far we've processed to avoid re-parsing
  const lastOutputIdx = useRef(0);
  const lastEventIdx = useRef(0);
  const itemsRef = useRef<ActivityItem[]>([]);
  // Queue of active tool operations (supports parallel tool calls).
  // New tools are pushed to the back; [Done]/[Error] finalizes from the front.
  const toolQueue = useRef<ToolOperationItem[]>([]);
  // Track whether we're still accumulating multi-line tool input JSON
  const accumulatingInput = useRef(false);
  const inputBuffer = useRef<string[]>([]);
  // Track orphan output lines to group into agent messages
  const orphanLines = useRef<string[]>([]);
  const orphanTs = useRef<string>(now());
  // Track session index for grouping
  const currentSessionIdx = useRef(0);

  // Collapse state override map: id -> collapsed boolean
  const [collapseOverrides, setCollapseOverrides] = useState<Record<string, boolean>>({});
  // When true, new items (and items without overrides) start expanded
  const [expandNewByDefault, setExpandNewByDefault] = useState(false);

  const processedItems = useMemo(() => {
    const items = itemsRef.current;

    // ── Process new output lines ──
    const startOut = lastOutputIdx.current;
    for (let i = startOut; i < output.length; i++) {
      const line = output[i];

      // Tool call start
      const toolMatch = line.match(TOOL_CALL_RE);
      if (toolMatch) {
        // Flush any orphan lines as agent message
        flushOrphanLines(items, orphanLines, orphanTs, currentSessionIdx.current);
        accumulatingInput.current = false;
        inputBuffer.current = [];

        const toolItem: ToolOperationItem = {
          id: makeId(),
          type: "tool_operation",
          timestamp: now(),
          collapsed: true,
          toolName: toolMatch[1],
          input: "",
          outputLines: [],
          result: "active",
          sessionIndex: currentSessionIdx.current,
        };
        toolQueue.current.push(toolItem);
        items.push(toolItem);
        continue;
      }

      // Tool input — attach to most recently opened tool (last in queue)
      {
        const lastTool = toolQueue.current.length > 0
          ? toolQueue.current[toolQueue.current.length - 1]
          : null;

        if (lastTool && lastTool.result === "active") {
          const inputMatch = line.match(TOOL_INPUT_RE);
          if (inputMatch) {
            const firstLine = inputMatch[1].trim();
            if (firstLine.startsWith("{") && !firstLine.endsWith("}")) {
              accumulatingInput.current = true;
              inputBuffer.current = [firstLine];
            } else {
              lastTool.input = firstLine;
              const fpMatch = firstLine.match(FILE_PATH_RE);
              if (fpMatch) lastTool.filePath = fpMatch[1];
            }
            continue;
          }

          // Continue accumulating multi-line input, but never swallow control markers
          if (accumulatingInput.current) {
            if (TOOL_DONE_RE.test(line) || TOOL_ERROR_RE.test(line) || TOOL_BLOCKED_RE.test(line) || TOOL_CALL_RE.test(line)) {
              const fullInput = inputBuffer.current.join("\n");
              lastTool.input = fullInput;
              const fpMatch = fullInput.match(FILE_PATH_RE);
              if (fpMatch) lastTool.filePath = fpMatch[1];
              accumulatingInput.current = false;
              inputBuffer.current = [];
              // Fall through — let this line be re-processed below
            } else {
              inputBuffer.current.push(line);
              const trimmed = line.trimStart();
              if (trimmed === "}" || trimmed.startsWith("}")) {
                const fullInput = inputBuffer.current.join("\n");
                lastTool.input = fullInput;
                const fpMatch = fullInput.match(FILE_PATH_RE);
                if (fpMatch) lastTool.filePath = fpMatch[1];
                accumulatingInput.current = false;
                inputBuffer.current = [];
              }
              if (inputBuffer.current.length > 200) {
                lastTool.input = inputBuffer.current.join("\n");
                accumulatingInput.current = false;
                inputBuffer.current = [];
              }
              continue;
            }
          }
        }
      }

      // Tool done — finalize the oldest active tool in the queue (FIFO)
      const doneMatch = line.match(TOOL_DONE_RE);
      if (doneMatch) {
        const tool = toolQueue.current.shift();
        if (tool) {
          // Flush any remaining input buffer into this tool
          if (accumulatingInput.current && inputBuffer.current.length > 0 && toolQueue.current.length === 0) {
            tool.input = inputBuffer.current.join("\n");
            const fpMatch = tool.input.match(FILE_PATH_RE);
            if (fpMatch) tool.filePath = fpMatch[1];
            accumulatingInput.current = false;
            inputBuffer.current = [];
          }
          tool.result = "success";
          tool.collapsed = true;

          // Create file change item for file-touching tools
          finalizeFileChangeItem(tool, items, currentSessionIdx.current);
        }
        // If no tool in queue, just suppress the orphan [Done]
        continue;
      }

      // Tool error — finalize oldest active tool with error status
      const errMatch = line.match(TOOL_ERROR_RE);
      if (errMatch) {
        const tool = toolQueue.current.shift();
        if (tool) {
          tool.result = "error";
          tool.errorMessage = errMatch[1];
          tool.collapsed = false;
        }
        // Suppress orphan [Error] lines (tool card already shows the error)
        continue;
      }

      // Tool blocked — finalize oldest active tool with blocked status
      const blockedMatch = line.match(TOOL_BLOCKED_RE);
      if (blockedMatch) {
        const tool = toolQueue.current.shift();
        if (tool) {
          tool.result = "blocked";
          tool.errorMessage = blockedMatch[1];
          tool.collapsed = false;
        }
        continue;
      }

      // True session restart (agent process restarted) — increment session counter
      if (SESSION_RESTART_RE.test(line)) {
        flushOrphanLines(items, orphanLines, orphanTs, currentSessionIdx.current);
        drainToolQueue(toolQueue);
        currentSessionIdx.current++;
        // Don't render this line — it's noise
        continue;
      }

      // Session/phase marker (SESSION 1: GREENFIELD / CODE)
      const sessionMatch = line.match(SESSION_RE);
      if (sessionMatch) {
        flushOrphanLines(items, orphanLines, orphanTs, currentSessionIdx.current);
        drainToolQueue(toolQueue);
        const marker: PhaseMarkerItem = {
          id: makeId(),
          type: "phase_marker",
          timestamp: now(),
          collapsed: false,
          phase: sessionMatch[2],
          sessionNumber: parseInt(sessionMatch[1], 10),
          sessionIndex: currentSessionIdx.current,
        };
        items.push(marker);
        continue;
      }

      // Verification (skip "no test suite" noise — not a real failure)
      const verifyMatch = line.match(VERIFY_RE);
      if (verifyMatch) {
        const text = verifyMatch[1];
        if (/verified_no_tests|no.test.suite/i.test(text)) {
          continue;
        }
        const passed = /pass|success|ok/i.test(text);
        const vItem: VerificationItem = {
          id: makeId(),
          type: "verification",
          timestamp: now(),
          collapsed: false,
          taskTitle: text,
          passed,
          sessionIndex: currentSessionIdx.current,
        };
        items.push(vItem);
        continue;
      }

      // Append output to the first active tool in the queue
      if (toolQueue.current.length > 0) {
        const firstActive = toolQueue.current[0];
        if (firstActive.result === "active") {
          firstActive.outputLines.push(line);
          continue;
        }
      }

      // Skip session infrastructure noise (banners, progress bars, metadata)
      if (SESSION_NOISE_RE.test(line) || SESSION_NOISE_BULLET_RE.test(line) || CATEGORY_PROGRESS_RE.test(line)) {
        continue;
      }

      // Skip raw XML tags (e.g., <tool_use_error>Sibling tool call errored</tool_use_error>)
      if (XML_TAG_RE.test(line.trim())) {
        continue;
      }

      // Orphan output -> group into agent message
      if (line.trim()) {
        orphanLines.current.push(line);
        if (orphanLines.current.length === 1) {
          orphanTs.current = now();
        }
        // Flush at 20 lines to keep messages manageable
        if (orphanLines.current.length >= 20) {
          flushOrphanLines(items, orphanLines, orphanTs, currentSessionIdx.current);
        }
      } else if (orphanLines.current.length > 0) {
        // Empty line = break between messages
        flushOrphanLines(items, orphanLines, orphanTs, currentSessionIdx.current);
      }
    }
    lastOutputIdx.current = output.length;

    // ── Process new events ──
    const startEv = lastEventIdx.current;
    for (let i = startEv; i < events.length; i++) {
      const ev = events[i];

      if (ev.type === "phase_change") {
        const marker: PhaseMarkerItem = {
          id: makeId(),
          type: "phase_marker",
          timestamp: ev.timestamp,
          collapsed: false,
          phase: (ev.data.phase as string) || "unknown",
        };
        items.push(marker);
      } else if (ev.type === "file_touch") {
        const fileItem: FileChangeItem = {
          id: makeId(),
          type: "file_change",
          timestamp: ev.timestamp,
          collapsed: true,
          filePath: (ev.data.path as string) || (ev.data.file as string) || "unknown",
          action: "edit",
          additions: ev.data.additions as number | undefined,
          deletions: ev.data.deletions as number | undefined,
        };
        items.push(fileItem);
      } else if (ev.type === "error") {
        const errItem: ErrorItem = {
          id: makeId(),
          type: "error",
          timestamp: ev.timestamp,
          collapsed: false,
          message: (ev.data.message as string) || (ev.data.error as string) || "Unknown error",
          severity: "error",
          recoveryHint: ev.data.recovery_hint as string | undefined,
        };
        items.push(errItem);
      } else if (ev.type === "blocked") {
        const blkItem: ErrorItem = {
          id: makeId(),
          type: "error",
          timestamp: ev.timestamp,
          collapsed: false,
          message: (ev.data.message as string) || "Operation blocked",
          severity: "blocked",
        };
        items.push(blkItem);
      } else if (ev.type === "verification") {
        const vItem: VerificationItem = {
          id: makeId(),
          type: "verification",
          timestamp: ev.timestamp,
          collapsed: false,
          taskTitle: (ev.data.task as string) || (ev.data.title as string) || "Verification",
          passed: (ev.data.passed as boolean) ?? (ev.data.result === "pass"),
          output: ev.data.output as string | undefined,
        };
        items.push(vItem);
      } else if (ev.type === "dispatch" || ev.type === "merge" || ev.type === "escalation") {
        const msg: AgentMessageItem = {
          id: makeId(),
          type: "agent_message",
          timestamp: ev.timestamp,
          collapsed: false,
          text: `[${ev.type.toUpperCase()}] ${(ev.data.message as string) || JSON.stringify(ev.data)}`,
        };
        items.push(msg);
      }
    }
    lastEventIdx.current = events.length;

    // Flush remaining orphans
    if (orphanLines.current.length > 0) {
      flushOrphanLines(items, orphanLines, orphanTs, currentSessionIdx.current);
    }

    itemsRef.current = items;
    // Return a new array reference to trigger re-render
    return [...items];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [output.length, events.length]);

  // Apply collapse overrides and "keep expanded" for new items
  // Filter out vague CODE-only agent messages (orchestrator noise)
  const finalItems = useMemo(() => {
    const filtered = processedItems.filter((item) => {
      if (item.type !== "agent_message") return true;
      const text = (item as AgentMessageItem).text?.trim() ?? "";
      return !VAGUE_CODE_RE.test(text);
    });
    return filtered.map((item) => {
      if (item.id in collapseOverrides) {
        return { ...item, collapsed: collapseOverrides[item.id] };
      }
      if (expandNewByDefault) {
        return { ...item, collapsed: false };
      }
      return item;
    });
  }, [processedItems, collapseOverrides, expandNewByDefault]);

  const toggleCollapse = useCallback((id: string) => {
    setCollapseOverrides((prev) => {
      const current = prev[id];
      const item = itemsRef.current.find((i) => i.id === id);
      const defaultCollapsed = item?.collapsed ?? true;
      const currentVal = current ?? defaultCollapsed;
      return { ...prev, [id]: !currentVal };
    });
  }, []);

  const collapseAll = useCallback(() => {
    setExpandNewByDefault(false);
    const overrides: Record<string, boolean> = {};
    for (const item of itemsRef.current) {
      overrides[item.id] = true;
    }
    setCollapseOverrides(overrides);
  }, []);

  const expandAll = useCallback(() => {
    setExpandNewByDefault(true);
    const overrides: Record<string, boolean> = {};
    for (const item of itemsRef.current) {
      overrides[item.id] = false;
    }
    setCollapseOverrides(overrides);
  }, []);

  return { items: finalItems, toggleCollapse, collapseAll, expandAll };
}

// ── Internal helpers ──

function flushOrphanLines(
  items: ActivityItem[],
  orphanLines: React.MutableRefObject<string[]>,
  orphanTs: React.MutableRefObject<string>,
  sessionIdx?: number,
) {
  if (orphanLines.current.length === 0) return;
  const msg: AgentMessageItem = {
    id: makeId(),
    type: "agent_message",
    timestamp: orphanTs.current,
    collapsed: false,
    text: orphanLines.current.join("\n"),
    sessionIndex: sessionIdx,
  };
  items.push(msg);
  orphanLines.current = [];
}

function drainToolQueue(
  toolQueue: React.MutableRefObject<ToolOperationItem[]>
) {
  for (const tool of toolQueue.current) {
    if (tool.result === "active") {
      tool.result = "success";
      tool.collapsed = true;
    }
  }
  toolQueue.current = [];
}

function finalizeFileChangeItem(
  tool: ToolOperationItem,
  items: ActivityItem[],
  sessionIdx: number,
) {
  const tn = tool.toolName;
  if (!tool.filePath || !(tn === "Read" || tn === "Write" || tn === "Edit")) return;

  let fileContent: string | undefined;
  if (tn === "Read" && tool.outputLines.length > 0) {
    fileContent = tool.outputLines.join("\n");
  }

  const fileItem: FileChangeItem = {
    id: makeId(),
    type: "file_change",
    timestamp: now(),
    collapsed: true,
    filePath: tool.filePath,
    action: inferFileAction(tn),
    content: fileContent,
    sessionIndex: sessionIdx,
  };

  if (tn === "Write" && tool.input) {
    try {
      const inputJson = JSON.parse(tool.input);
      if (inputJson.content) {
        fileItem.content = inputJson.content;
        fileItem.additions = inputJson.content.split("\n").length;
      }
    } catch { /* not JSON */ }
  }

  if (tn === "Edit" && tool.input) {
    try {
      const inputJson = JSON.parse(tool.input);
      if (inputJson.old_string) fileItem.oldString = inputJson.old_string;
      if (inputJson.new_string) fileItem.newString = inputJson.new_string;
      if (inputJson.old_string && inputJson.new_string) {
        const diff = computeLineDiff(inputJson.old_string, inputJson.new_string);
        fileItem.additions = diff.filter(d => d.type === "add").length;
        fileItem.deletions = diff.filter(d => d.type === "remove").length;
      }
    } catch { /* not JSON */ }
  }

  items.push(fileItem);
}
