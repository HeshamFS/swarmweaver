"use client";

import { useMemo, useRef, useState, useCallback } from "react";
import type { AgentEvent } from "./useSwarmWeaver";
import type {
  ActivityItem,
  ToolOperationItem,
  FileChangeItem,
  AgentMessageItem,
  PhaseMarkerItem,
  ErrorItem,
  VerificationItem,
  UseActivityFeedReturn,
} from "./useActivityFeed";

/**
 * Native Activity Feed Hook
 *
 * Consumes events[] directly from SDK event stream (no regex parsing).
 * Builds ToolOperationItems from tool_start -> tool_input_delta -> tool_done
 * sequences using ID-based tracking.
 *
 * Used when the engine runs in native mode (in-process SDK).
 * Falls back to useActivityFeed for subprocess mode.
 */

// ── File path regex for tool input JSON ──
const FILE_PATH_RE = /(?:file_path|path)["']?\s*[:=]\s*["']?([^\s"'}{,]+\.\w+)/;

// ── Helpers ──

let nextNativeId = 0;
function makeId(): string {
  return `naf-${++nextNativeId}-${Date.now()}`;
}

function now(): string {
  return new Date().toISOString();
}

// ── Hook ──

// Backend startup lines we want to surface in the feed
const BACKEND_INIT_RE = /^\[backend\]|\[SDK\]/;

// Vague "CODE" lines from orchestrator — filter out (treat as noise)
const VAGUE_CODE_RE = /^(:zap:\s*CODE|:code:)(\s*#\d+)?\s*$/i;

export function useNativeActivityFeed(
  events: AgentEvent[],
  output: string[] = []
): UseActivityFeedReturn {
  const lastEventIdx = useRef(0);
  const itemsRef = useRef<ActivityItem[]>([]);
  // Map of active tools by SDK tool_use_id
  const activeTools = useRef<Map<string, ToolOperationItem>>(new Map());
  // Accumulated input JSON per tool ID
  const inputBuffers = useRef<Map<string, string>>(new Map());
  // Start time (ms) per tool ID for duration computation
  const toolStartTimes = useRef<Map<string, number>>(new Map());
  // Live text item — updated in place as text_delta events arrive.
  // Cleared (set to null) when a tool_start or phase boundary is reached.
  const currentTextItemRef = useRef<AgentMessageItem | null>(null);
  // Whether we have already created the startup log item
  const startupDoneRef = useRef(false);

  const [collapseOverrides, setCollapseOverrides] = useState<Record<string, boolean>>({});
  const [expandNewByDefault, setExpandNewByDefault] = useState(false);

  // Reset all state when events array is cleared (new run started)
  const prevEventsLengthRef = useRef(0);
  if (events.length === 0 && prevEventsLengthRef.current > 0) {
    itemsRef.current = [];
    lastEventIdx.current = 0;
    activeTools.current.clear();
    toolStartTimes.current.clear();
    inputBuffers.current.clear();
    currentTextItemRef.current = null;
    startupDoneRef.current = false;
  }
  prevEventsLengthRef.current = events.length;

  const processedItems = useMemo(() => {
    const items = itemsRef.current;

    // ── Startup log: surface [backend] init lines once, as first item ──
    if (!startupDoneRef.current && output.length > 0) {
      const initLines = output
        .filter((l) => BACKEND_INIT_RE.test(l))
        .map((l) => l.replace(/^\[backend\]\s*/, "").replace(/^\[SDK\]\s*/, "[SDK] "));
      if (initLines.length > 0) {
        startupDoneRef.current = true;
        const startupItem: AgentMessageItem = {
          id: makeId(),
          type: "agent_message",
          timestamp: now(),
          collapsed: false,
          text: initLines.join("\n"),
        };
        items.unshift(startupItem);
      }
    }

    const startEv = lastEventIdx.current;
    for (let i = startEv; i < events.length; i++) {
      const ev = events[i];
      const evData = ev.data || {};
      // worker_id is set by swarm worker events; absent = orchestrator/main agent
      const workerId = typeof evData.worker_id === "number" ? evData.worker_id : null;

      switch (ev.type) {
        case "tool_start": {
          // Seal the current text item so the next text_delta starts a new one
          currentTextItemRef.current = null;

          const toolId = (evData.id as string) || "";
          const toolName = (evData.tool as string) || "Unknown";

          const toolItem: ToolOperationItem = {
            id: makeId(),
            type: "tool_operation",
            timestamp: ev.timestamp,
            collapsed: true,
            toolName,
            input: "",
            outputLines: [],
            result: "active",
            workerId,
          };

          activeTools.current.set(toolId, toolItem);
          inputBuffers.current.set(toolId, "");
          const startMs = ev.timestamp ? new Date(ev.timestamp).getTime() : Date.now();
          if (!isNaN(startMs)) toolStartTimes.current.set(toolId, startMs);
          items.push(toolItem);
          break;
        }

        case "tool_input_delta": {
          const toolId = (evData.id as string) || "";
          const chunk = (evData.chunk as string) || "";
          const existing = inputBuffers.current.get(toolId) || "";
          inputBuffers.current.set(toolId, existing + chunk);

          // Update the active tool's input live
          const tool = activeTools.current.get(toolId);
          if (tool) {
            tool.input = inputBuffers.current.get(toolId) || "";
          }
          break;
        }

        case "tool_input_complete": {
          // Complete input JSON from AssistantMessage.ToolUseBlock —
          // more reliable than accumulating input_json_delta chunks.
          const toolId = (evData.id as string) || "";
          const fullInput = (evData.input as string) || "";
          const tool = activeTools.current.get(toolId);
          if (tool) {
            tool.input = fullInput;
            inputBuffers.current.set(toolId, fullInput);
            // Also set tool name if it was missing (fallback path)
            const tn = (evData.tool as string) || "";
            if (tn && tool.toolName === "Unknown") tool.toolName = tn;
          }
          break;
        }

        case "tool_done": {
          const toolId = (evData.id as string) || "";
          const tool = activeTools.current.get(toolId);
          if (tool) {
            // Compute duration from tool_start to tool_done
            const startMs = toolStartTimes.current.get(toolId);
            const endMs = ev.timestamp ? new Date(ev.timestamp).getTime() : Date.now();
            if (startMs != null && !isNaN(endMs)) {
              tool.duration = (endMs - startMs) / 1000;
            }
            toolStartTimes.current.delete(toolId);

            // Finalize input from buffer
            const fullInput = inputBuffers.current.get(toolId) || "";
            tool.input = fullInput;
            tool.result = "success";
            tool.collapsed = true; // Collapse the raw tool card

            // Extract file path from input JSON
            const fpMatch = fullInput.match(FILE_PATH_RE);
            if (fpMatch) tool.filePath = fpMatch[1];

            // For Write/Edit, create a FileChangeItem with actual code content
            const tn = tool.toolName;
            if ((tn === "Write" || tn === "Edit") && fpMatch) {
              try {
                const parsed = JSON.parse(fullInput);
                if (tn === "Write" && parsed.content) {
                  const fc: FileChangeItem = {
                    id: makeId(),
                    type: "file_change",
                    timestamp: ev.timestamp,
                    collapsed: false,
                    filePath: parsed.file_path || fpMatch[1],
                    action: "create",
                    content: parsed.content,
                    additions: parsed.content.split("\n").length,
                    workerId,
                  };
                  items.push(fc);
                } else if (tn === "Edit" && parsed.old_string != null && parsed.new_string != null) {
                  const fc: FileChangeItem = {
                    id: makeId(),
                    type: "file_change",
                    timestamp: ev.timestamp,
                    collapsed: false,
                    filePath: parsed.file_path || fpMatch[1],
                    action: "edit",
                    oldString: parsed.old_string,
                    newString: parsed.new_string,
                    workerId,
                  };
                  items.push(fc);
                }
              } catch {
                // JSON parse failed — fall through, raw tool card is still shown
              }
            }

            activeTools.current.delete(toolId);
            inputBuffers.current.delete(toolId);
          }
          break;
        }

        case "tool_result": {
          const toolId = (evData.id as string) || "";
          const tool = activeTools.current.get(toolId);
          if (tool) {
            const content = (evData.content as string) || "";
            if (content) {
              tool.outputLines = content.split("\n").slice(0, 50);
            }
            // Don't finalize here — tool_done handles that
          }
          break;
        }

        case "tool_error": {
          const toolId = (evData.id as string) || "";
          const tool = activeTools.current.get(toolId);
          if (tool) {
            const startMs = toolStartTimes.current.get(toolId);
            const endMs = ev.timestamp ? new Date(ev.timestamp).getTime() : Date.now();
            if (startMs != null && !isNaN(endMs)) {
              tool.duration = (endMs - startMs) / 1000;
            }
            toolStartTimes.current.delete(toolId);
            tool.result = "error";
            tool.errorMessage = (evData.error as string) || "Unknown error";
            tool.collapsed = false;
            activeTools.current.delete(toolId);
            inputBuffers.current.delete(toolId);
          } else {
            // Orphan error — show as error item
            const errItem: ErrorItem = {
              id: makeId(),
              type: "error",
              timestamp: ev.timestamp,
              collapsed: false,
              message: (evData.error as string) || "Tool error",
              severity: "error",
              workerId,
            };
            items.push(errItem);
          }
          break;
        }

        case "tool_blocked": {
          const toolId = (evData.id as string) || "";
          const tool = activeTools.current.get(toolId);
          if (tool) {
            const startMs = toolStartTimes.current.get(toolId);
            const endMs = ev.timestamp ? new Date(ev.timestamp).getTime() : Date.now();
            if (startMs != null && !isNaN(endMs)) {
              tool.duration = (endMs - startMs) / 1000;
            }
            toolStartTimes.current.delete(toolId);
            tool.result = "blocked";
            tool.errorMessage = (evData.reason as string) || "Blocked";
            tool.collapsed = false;
            activeTools.current.delete(toolId);
            inputBuffers.current.delete(toolId);
          } else {
            const blkItem: ErrorItem = {
              id: makeId(),
              type: "error",
              timestamp: ev.timestamp,
              collapsed: false,
              message: (evData.reason as string) || "Operation blocked",
              severity: "blocked",
              workerId,
            };
            items.push(blkItem);
          }
          break;
        }

        case "text_delta": {
          // Append to live text item (or create one) — no buffering, no flushing
          const text = (evData.text as string) || "";
          if (text) {
            if (!currentTextItemRef.current || currentTextItemRef.current.workerId !== workerId) {
              const msg: AgentMessageItem = {
                id: makeId(),
                type: "agent_message",
                timestamp: ev.timestamp,
                collapsed: false,
                text,
                workerId,
              };
              currentTextItemRef.current = msg;
              items.push(msg);
            } else {
              currentTextItemRef.current.text += text;
            }
          }
          break;
        }

        case "phase_change":
        case "session_start": {
          // Seal the current text item at phase boundaries
          currentTextItemRef.current = null;

          const marker: PhaseMarkerItem = {
            id: makeId(),
            type: "phase_marker",
            timestamp: ev.timestamp,
            collapsed: false,
            phase: (evData.phase as string) || "unknown",
            sessionNumber: evData.session as number | undefined,
            workerId,
          };
          items.push(marker);
          break;
        }

        case "verification": {
          const action = (evData.action as string) || "";
          const taskIds = evData.task_ids as string[] | undefined;
          const taskRange = evData.task_range as string | undefined;
          const taskTitle =
            taskRange ??
            (taskIds && taskIds.length > 1 ? taskIds.join(", ") : (evData.task_id as string) || "");
          const vItem: VerificationItem = {
            id: makeId(),
            type: "verification",
            timestamp: ev.timestamp,
            collapsed: false,
            taskTitle,
            passed: action === "verified" || action === "verified_no_tests",
            output: (evData.message as string) || undefined,
          };
          items.push(vItem);
          break;
        }

        case "session_error": {
          const errItem: ErrorItem = {
            id: makeId(),
            type: "error",
            timestamp: ev.timestamp,
            collapsed: false,
            message: (evData.error as string) || "Session error",
            severity: "error",
            workerId,
          };
          items.push(errItem);
          break;
        }

        // ── Smart Orchestrator events (no worker_id = main/orchestrator) ──
        case "orchestrator_text": {
          const text = (evData.data as string) || (evData.text as string) || "";
          if (text) {
            // Continue existing orchestrator text item or start a new one
            if (!currentTextItemRef.current || currentTextItemRef.current.workerId !== null) {
              const msg: AgentMessageItem = {
                id: makeId(),
                type: "agent_message",
                timestamp: ev.timestamp,
                collapsed: false,
                text,
                workerId: null,
              };
              currentTextItemRef.current = msg;
              items.push(msg);
            } else {
              currentTextItemRef.current.text += text;
            }
          }
          break;
        }

        case "orchestrator_decision": {
          currentTextItemRef.current = null;
          const action = (evData.action as string) || "";
          const details = (evData.details as string) || "";
          const decisionText = details ? `**${action}**\n${details}` : action;
          if (decisionText) {
            const msg: AgentMessageItem = {
              id: makeId(),
              type: "agent_message",
              timestamp: ev.timestamp,
              collapsed: false,
              text: `:bot: ${decisionText}`,
              workerId: null,
            };
            items.push(msg);
          }
          break;
        }

        case "orchestrator_analysis": {
          currentTextItemRef.current = null;
          const rec = (evData.recommended_workers as number) ?? 0;
          const total = (evData.total_tasks as number) ?? 0;
          const reason = (evData.reasoning as string) || "";
          const analysisText = `**Orchestrator analysis**: ${total} tasks → ${rec} worker${rec !== 1 ? "s" : ""} recommended\n${reason}`;
          const msg: AgentMessageItem = {
            id: makeId(),
            type: "agent_message",
            timestamp: ev.timestamp,
            collapsed: false,
            text: analysisText,
            workerId: null,
          };
          items.push(msg);
          break;
        }

        case "worker_spawned": {
          currentTextItemRef.current = null;
          const wId = (evData.worker_id as number) ?? 0;
          const wName = (evData.name as string) || `worker-${wId}`;
          const wTasks = (evData.task_ids as string[]) || [];
          // Mark matching spawn_worker tool as superseded — worker_spawned is canonical display
          for (let j = items.length - 1; j >= 0; j--) {
            const it = items[j];
            if (it.type === "tool_operation" && it.toolName === "mcp__orchestrator_tools__spawn_worker") {
              try {
                const out = (it as ToolOperationItem).outputLines?.join("\n") || "";
                const parsed = JSON.parse(out) as { worker_id?: number };
                if (parsed?.worker_id === wId) {
                  (it as ToolOperationItem).supersededByWorkerSpawned = true;
                  break;
                }
              } catch {
                /* ignore parse errors */
              }
            }
          }
          const msg: AgentMessageItem = {
            id: makeId(),
            type: "agent_message",
            timestamp: ev.timestamp,
            collapsed: false,
            text: `:rocket: Spawned **${wName}** — tasks: ${wTasks.join(", ")}`,
            workerId: null,
          };
          items.push(msg);
          break;
        }

        case "worker_merged": {
          currentTextItemRef.current = null;
          const wId = (evData.worker_id as number) ?? 0;
          const tier = (evData.resolution_tier as string) || "clean";
          const msg: AgentMessageItem = {
            id: makeId(),
            type: "agent_message",
            timestamp: ev.timestamp,
            collapsed: false,
            text: `:check: Merged worker-${wId} (${tier} merge)`,
            workerId: null,
          };
          items.push(msg);
          break;
        }

        case "worker_terminated": {
          currentTextItemRef.current = null;
          const wId = (evData.worker_id as number) ?? 0;
          const reason = (evData.reason as string) || "";
          const msg: AgentMessageItem = {
            id: makeId(),
            type: "agent_message",
            timestamp: ev.timestamp,
            collapsed: false,
            text: `:block: Terminated worker-${wId}: ${reason}`,
            workerId: null,
          };
          items.push(msg);
          break;
        }

        case "worker_error": {
          currentTextItemRef.current = null;
          const wId = (evData.worker_id as number) ?? 0;
          const errMsg = (evData.error as string) || "Unknown error";
          const errItem: ErrorItem = {
            id: makeId(),
            type: "error",
            timestamp: ev.timestamp,
            collapsed: false,
            message: `Worker-${wId} error: ${errMsg}`,
            severity: "error",
            workerId: wId,
          };
          items.push(errItem);
          break;
        }

        case "thinking_block": {
          currentTextItemRef.current = null;
          const text = (evData.text as string) || "";
          const agent = (evData.agent as string) || "";
          if (text) {
            const label = agent ? `${agent} thinking` : "Thinking";
            const msg: AgentMessageItem = {
              id: makeId(),
              type: "agent_message",
              timestamp: ev.timestamp,
              collapsed: true,
              text: label,
              isThinking: true,
              thinkingText: text,
              workerId,
            };
            items.push(msg);
          }
          break;
        }

        case "context_budget_warning": {
          currentTextItemRef.current = null;
          const tokens = (evData.input_tokens as number) || 0;
          const msg: AgentMessageItem = {
            id: makeId(),
            type: "agent_message",
            timestamp: ev.timestamp,
            collapsed: false,
            text: `:warning: **Context budget warning**: ${tokens.toLocaleString()} input tokens — approaching limit`,
            workerId: null,
          };
          items.push(msg);
          break;
        }

        case "budget_stop_broadcast": {
          currentTextItemRef.current = null;
          const reason = (evData.reason as string) || "Budget exhausted";
          const errItem: ErrorItem = {
            id: makeId(),
            type: "error",
            timestamp: ev.timestamp,
            collapsed: false,
            message: `Budget stop: ${reason}`,
            severity: "error",
            workerId: null,
          };
          items.push(errItem);
          break;
        }

        case "merge_error": {
          currentTextItemRef.current = null;
          const errMsg = (evData.error as string) || "Unknown merge error";
          const errItem: ErrorItem = {
            id: makeId(),
            type: "error",
            timestamp: ev.timestamp,
            collapsed: false,
            message: `Merge failed: ${errMsg}`,
            severity: "error",
            workerId: null,
          };
          items.push(errItem);
          break;
        }

        case "swarm_status": {
          currentTextItemRef.current = null;
          const phase = (evData.phase as string) || "";
          if (phase) {
            const msg: AgentMessageItem = {
              id: makeId(),
              type: "agent_message",
              timestamp: ev.timestamp,
              collapsed: false,
              text: `:gear: Swarm phase: **${phase}**`,
              workerId: null,
            };
            items.push(msg);
          }
          break;
        }

        default:
          break;
      }
    }
    lastEventIdx.current = events.length;

    itemsRef.current = items;
    return [...items];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [events.length, output.length]);

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

