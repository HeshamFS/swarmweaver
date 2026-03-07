import type { AgentEvent } from "../hooks/useSwarmWeaver";

export interface AuditEntry {
  timestamp: string;
  tool_use_id?: string;
  tool_name: string;
  tool_input_preview?: string;
  is_error: boolean;
}

export interface EventStoreEvent {
  id: number;
  agent_name: string;
  run_id: string;
  event_type: string;
  tool_name: string;
  duration_ms: number;
  level: string;
  data: Record<string, unknown>;
  created_at: string;
}

export interface EventStoreStats {
  total: number;
  errors: number;
  by_type: Record<string, number>;
}

export interface EventStoreResponse {
  events: EventStoreEvent[];
  stats: EventStoreStats;
}

export interface ToolStatEntry {
  tool_name: string;
  call_count: number;
  avg_duration: number;
  max_duration: number;
  error_count: number;
}

export interface AuditViewProps {
  loading: boolean;
  events: AgentEvent[];
  eventStoreData: EventStoreResponse | null;
  toolStats: ToolStatEntry[];
}

// --- Relative timestamp helper ---
function relativeTime(timestamp: string): string {
  try {
    const now = Date.now();
    const then = new Date(timestamp).getTime();
    const diffMs = now - then;
    if (diffMs < 0) return "just now";
    const secs = Math.floor(diffMs / 1000);
    if (secs < 60) return `${secs}s ago`;
    const mins = Math.floor(secs / 60);
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
  } catch {
    return "";
  }
}

// --- Context Priming Card ---
function ContextPrimingCard({ events }: { events: AgentEvent[] }) {
  // Look for context-related messages in the first 30 events
  const contextHints: string[] = [];
  const early = events.slice(0, 30);
  for (const ev of early) {
    const msg = String(ev.data?.message || ev.data?.reason || "");
    const output = String(ev.data?.output || "");
    for (const text of [msg, output]) {
      if (/\[CONTEXT\]/i.test(text) || /memory.*inject/i.test(text) || /context.*prim/i.test(text)) {
        contextHints.push(text.slice(0, 120));
      }
    }
    if (ev.type === "phase_change" && ev.data?.phase) {
      contextHints.push(`Phase: ${String(ev.data.phase)}`);
    }
  }

  if (contextHints.length === 0) return null;

  return (
    <div className="mx-2 mt-2 rounded-lg border border-accent/25 bg-accent/5 p-3">
      <span className="text-[10px] font-semibold uppercase tracking-wider text-accent block mb-1.5">
        Context Priming
      </span>
      <div className="space-y-1">
        {contextHints.slice(0, 5).map((hint, i) => (
          <p key={i} className="text-xs text-text-secondary truncate">
            {hint}
          </p>
        ))}
      </div>
    </div>
  );
}

export function AuditView({
  loading,
  events,
  eventStoreData,
  toolStats,
}: AuditViewProps) {
  if (loading && !eventStoreData) {
    return (
      <div className="flex items-center justify-center h-full">
        <span className="text-sm text-text-muted animate-pulse">Loading audit timeline...</span>
      </div>
    );
  }

  if (!eventStoreData || eventStoreData.events.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <span className="text-sm text-text-muted">No audit entries yet. Run an agent to generate the audit log.</span>
      </div>
    );
  }

  return (
    <div>
      <ContextPrimingCard events={events} />

      {/* Event Store Stats Summary */}
      {eventStoreData && eventStoreData.stats && (
        <div className="mx-2 mt-2 rounded-lg border border-border-subtle bg-surface-raised p-2.5">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-text-muted block mb-1">
            Event Store
          </span>
          <div className="text-xs text-text-secondary font-mono">
            Total: {eventStoreData.stats.total} events
            {" | "}
            <span className={eventStoreData.stats.errors > 0 ? "text-error" : ""}>
              Errors: {eventStoreData.stats.errors}
            </span>
            {eventStoreData.stats.by_type && Object.keys(eventStoreData.stats.by_type).length > 0 && (
              <>
                {" | "}
                Types: {Object.keys(eventStoreData.stats.by_type).join(", ")}
              </>
            )}
          </div>
        </div>
      )}

      {/* Tool Statistics Table */}
      {toolStats.length > 0 && (
        <div className="mx-2 mt-2 rounded-lg border border-border-subtle bg-surface-raised p-2.5">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-text-muted block mb-1.5">
            Tool Statistics
          </span>
          <div className="overflow-x-auto">
            <table className="w-full text-[10px] font-mono">
              <thead>
                <tr className="text-text-muted border-b border-border-subtle">
                  <th className="text-left py-1 pr-2">Tool</th>
                  <th className="text-right py-1 px-2">Calls</th>
                  <th className="text-right py-1 px-2">Avg (ms)</th>
                  <th className="text-right py-1 px-2">Max (ms)</th>
                  <th className="text-right py-1 pl-2">Errors</th>
                </tr>
              </thead>
              <tbody>
                {toolStats.map((stat) => (
                  <tr key={stat.tool_name} className="border-b border-border-subtle/30 hover:bg-surface/50">
                    <td className="py-1 pr-2 text-text-primary">{stat.tool_name}</td>
                    <td className="text-right py-1 px-2 text-text-secondary">{stat.call_count}</td>
                    <td className="text-right py-1 px-2 text-text-secondary">
                      {typeof stat.avg_duration === "number" ? stat.avg_duration.toFixed(0) : "-"}
                    </td>
                    <td className="text-right py-1 px-2 text-text-secondary">
                      {typeof stat.max_duration === "number" ? stat.max_duration.toFixed(0) : "-"}
                    </td>
                    <td className={`text-right py-1 pl-2 ${stat.error_count > 0 ? "text-error" : "text-text-muted"}`}>
                      {stat.error_count}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Event list */}
      <div className="p-2 space-y-0.5">
        {eventStoreData.events.map((evt, i) => (
          <div
            key={evt.id || i}
            className={`flex items-center gap-2 px-2 py-1.5 rounded transition-colors ${
              evt.level === "error"
                ? "bg-error/5 hover:bg-error/10"
                : "hover:bg-surface-raised/50"
            }`}
          >
            <span
              className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                evt.level === "error" ? "bg-error" : evt.level === "warning" ? "bg-warning" : "bg-accent/40"
              }`}
            />
            <span
              className={`text-[10px] font-mono font-medium px-1.5 py-0.5 rounded border flex-shrink-0 ${
                evt.level === "error"
                  ? "bg-error/10 text-error border-error/20"
                  : "bg-accent/10 text-accent border-accent/20"
              }`}
            >
              {evt.tool_name || evt.event_type}
            </span>
            {evt.agent_name && (
              <span className="text-[10px] text-text-muted font-mono flex-shrink-0">
                [{evt.agent_name}]
              </span>
            )}
            {evt.duration_ms > 0 && (
              <span className="text-[10px] text-text-muted font-mono flex-shrink-0">
                {evt.duration_ms}ms
              </span>
            )}
            <span className="text-xs text-text-muted truncate flex-1 min-w-0">
              {evt.data?.message ? String(evt.data.message) : evt.data?.file ? String(evt.data.file) : ""}
            </span>
            <span className="text-[10px] text-text-muted whitespace-nowrap flex-shrink-0">
              {relativeTime(evt.created_at)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
