import { useMemo } from "react";
import type { AgentEvent } from "../hooks/useSwarmWeaver";
import { detectFailureModes, type FailureMode } from "../utils/failureModes";

export interface PersistedError {
  timestamp: string;
  agent: string;
  event_type: string;
  tool_name: string;
  tool_input: string;
  error: string;
  tool_use_id?: string;
}

export interface ErrorsViewProps {
  events: AgentEvent[];
  persistedErrors?: PersistedError[];
}

const SEVERITY_COLORS: Record<FailureMode['severity'], string> = {
  critical: 'bg-red-600 text-white',
  high: 'bg-orange-500 text-white',
  medium: 'bg-yellow-500 text-black',
  low: 'bg-blue-500 text-white',
};

function formatTime(timestamp: string): string {
  try {
    const d = new Date(timestamp);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return "";
  }
}

const STEERING_PATTERN = /\[STEERING\]|\[DIRECTIVE FROM ORCHESTRATOR\]|Message from operator/i;

/** Normalize live events and persisted errors into a unified list, newest first. Excludes steering blocks (directives). */
function mergeErrors(events: AgentEvent[], persisted: PersistedError[] = []): Array<{
  timestamp: string;
  agent: string;
  tool: string;
  tool_input: string;
  message: string;
  event_type: string;
}> {
  const items: Array<{ timestamp: string; agent: string; tool: string; tool_input: string; message: string; event_type: string }> = [];

  for (const e of events) {
    if (e.type !== "error" && e.type !== "blocked" && e.type !== "tool_error" && e.type !== "tool_blocked") continue;
    const workerId = (e as AgentEvent & { worker_id?: number }).worker_id;
    const agent = workerId != null ? `worker-${workerId}` : "orchestrator";
    const message = e.type === "tool_error" ? String((e.data as { error?: string })?.error ?? "")
      : e.type === "tool_blocked" ? String((e.data as { reason?: string })?.reason ?? "")
      : String((e.data as { message?: string; reason?: string })?.message ?? (e.data as { reason?: string })?.reason ?? "Unknown error");
    if (e.type === "tool_blocked" && STEERING_PATTERN.test(message)) continue;
    const tool = (e.data as { tool?: string })?.tool ?? "";
    items.push({
      timestamp: e.timestamp ?? new Date().toISOString(),
      agent,
      tool,
      tool_input: "",
      message,
      event_type: e.type,
    });
  }

  for (const p of persisted) {
    if (p.event_type === "tool_blocked" && STEERING_PATTERN.test(p.error ?? "")) continue;
    items.push({
      timestamp: p.timestamp,
      agent: p.agent,
      tool: p.tool_name,
      tool_input: p.tool_input ?? "",
      message: p.error ?? "",
      event_type: p.event_type,
    });
  }

  items.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
  return items;
}

export function ErrorsView({ events, persistedErrors = [] }: ErrorsViewProps) {
  const errors = useMemo(() => mergeErrors(events, persistedErrors), [events, persistedErrors]);

  if (errors.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <span className="text-sm text-text-muted">No errors recorded.</span>
      </div>
    );
  }

  return (
    <div className="p-2 space-y-2">
      {errors.slice(0, 50).map((item, i) => (
        <div
          key={i}
          className="rounded-lg border border-error/20 bg-error/5 p-3"
        >
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs text-error font-medium">
              {item.event_type === "tool_blocked" || item.event_type === "blocked" ? "Blocked" : "Error"}
              {item.agent ? ` \u2022 ${item.agent}` : ""}
              {item.tool ? ` \u2022 ${item.tool}` : ""}
            </span>
            <span className="text-[10px] text-text-muted">
              {formatTime(item.timestamp)}
            </span>
          </div>
          {item.tool_input && (
            <p className="text-[10px] font-mono text-[#888] mb-1 truncate max-w-full" title={item.tool_input}>
              {item.tool_input}
            </p>
          )}
          <p className="text-xs text-text-secondary">
            {item.message || "Unknown error"}
          </p>
          {(() => {
            const modes = detectFailureModes(item.message);
            if (modes.length === 0) return null;
            return (
              <div className="mt-2 space-y-1">
                {modes.map((fm) => (
                  <div key={fm.code} className="flex flex-col gap-0.5">
                    <span className={`inline-block w-fit text-[10px] font-semibold px-1.5 py-0.5 rounded ${SEVERITY_COLORS[fm.severity]}`}>
                      {fm.code}
                    </span>
                    <span className="text-[10px] text-text-muted ml-0.5">
                      Recovery: {fm.recovery}
                    </span>
                  </div>
                ))}
              </div>
            );
          })()}
        </div>
      ))}
    </div>
  );
}
