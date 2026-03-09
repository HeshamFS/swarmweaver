import { useState, useEffect } from "react";

interface MailAttachment {
  type: string;
  name: string;
  content: string;
}

interface MailMessage {
  id: string;
  sender: string;
  recipient: string;
  msg_type: string;
  subject: string;
  body: string;
  priority: string;
  read: boolean;
  created_at: string;
  thread_id?: string;
  payload?: Record<string, unknown>;
  attachments?: MailAttachment[];
}

interface MailAnalytics {
  total?: number;
  unread?: number;
  top_senders?: Record<string, number>;
  unread_by_recipient?: Record<string, number>;
  avg_response_time_seconds?: number | null;
  dead_letter_count?: number;
}

export interface SwarmMailTabProps {
  mailMessages: MailMessage[];
  mailStats: { total: number; unread: number };
  markMailRead: () => void;
  projectDir?: string;
}

const MSG_TYPE_ICONS: Record<string, string> = {
  status: "\u2139",
  worker_done: "\u2713",
  merge_ready: "\u21BB",
  error: "\u2717",
  question: "?",
  result: "\u2605",
  DISPATCH: "\u{1F4E4}",
  ASSIGN: "\u{1F4CB}",
  ESCALATION: "\u26A0",
  HEALTH_CHECK: "\u{1F493}",
  MERGED: "\u2713\u2713",
  MERGE_FAILED: "\u2717\u2717",
};

const MSG_TYPE_BADGE_STYLES: Record<string, string> = {
  DISPATCH: "bg-blue-500/10 text-blue-400",
  ASSIGN: "bg-blue-500/10 text-blue-400",
  ESCALATION: "bg-red-500/10 text-red-400 animate-pulse",
  HEALTH_CHECK: "bg-green-500/10 text-green-400",
  MERGED: "bg-green-500/10 text-green-400",
  MERGE_FAILED: "bg-red-500/10 text-red-400",
};

const FILTER_OPTIONS = [
  { value: "", label: "All" },
  { value: "status", label: "Status" },
  { value: "error", label: "Error" },
  { value: "DISPATCH", label: "Dispatch" },
  { value: "ASSIGN", label: "Assign" },
  { value: "ESCALATION", label: "Escalation" },
  { value: "HEALTH_CHECK", label: "Health Check" },
  { value: "MERGED", label: "Merged" },
  { value: "MERGE_FAILED", label: "Merge Failed" },
  { value: "worker_done", label: "Worker Done" },
  { value: "merge_ready", label: "Merge Ready" },
  { value: "question", label: "Question" },
  { value: "result", label: "Result" },
];

export function SwarmMailTab({
  mailMessages,
  mailStats,
  markMailRead,
  projectDir,
}: SwarmMailTabProps) {
  const [expandedThreads, setExpandedThreads] = useState<Set<string>>(new Set());
  const [typeFilter, setTypeFilter] = useState<string>("");
  const [analytics, setAnalytics] = useState<MailAnalytics | null>(null);

  // Fetch analytics on mount + 30s poll
  useEffect(() => {
    if (!projectDir) return;
    const fetchAnalytics = async () => {
      try {
        const res = await fetch(
          `/api/swarm/mail/analytics?path=${encodeURIComponent(projectDir)}`
        );
        const data = await res.json();
        setAnalytics(data.analytics || null);
      } catch {
        // Ignore
      }
    };
    fetchAnalytics();
    const interval = setInterval(fetchAnalytics, 30000);
    return () => clearInterval(interval);
  }, [projectDir]);

  // Filter messages by type
  const filteredMessages = typeFilter
    ? mailMessages.filter((m) => m.msg_type === typeFilter)
    : mailMessages;

  // Group messages by thread_id
  const threads = new Map<string, MailMessage[]>();
  for (const msg of filteredMessages) {
    const tid = msg.thread_id || msg.id;
    if (!threads.has(tid)) threads.set(tid, []);
    threads.get(tid)!.push(msg);
  }
  const threadEntries = Array.from(threads.entries());

  const formatResponseTime = (seconds: number | null | undefined) => {
    if (seconds == null) return "N/A";
    if (seconds < 60) return `${Math.round(seconds)}s`;
    return `${Math.round(seconds / 60)}m`;
  };

  return (
    <div className="flex flex-col">
      {/* Analytics mini-dashboard (M2-4) */}
      {analytics && (
        <div className="px-3 py-2 border-b border-border-subtle bg-surface-raised/30 flex items-center gap-4 text-[10px] font-mono text-text-muted">
          <span>{analytics.total ?? 0} total</span>
          <span>{analytics.unread ?? 0} unread</span>
          <span>Avg resp: {formatResponseTime(analytics.avg_response_time_seconds)}</span>
          {(analytics.dead_letter_count ?? 0) > 0 && (
            <span className="text-warning">{analytics.dead_letter_count} dead letters</span>
          )}
          {analytics.top_senders && Object.keys(analytics.top_senders).length > 0 && (
            <span className="ml-auto truncate max-w-[200px]" title={Object.entries(analytics.top_senders).map(([k, v]) => `${k}: ${v}`).join(", ")}>
              Top: {Object.entries(analytics.top_senders).slice(0, 2).map(([k, v]) => `${k}(${v})`).join(", ")}
            </span>
          )}
        </div>
      )}
      {/* Filter bar */}
      <div className="px-3 py-2 border-b border-border-subtle flex items-center gap-2">
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="rounded-md border border-border-subtle bg-surface px-2 py-0.5 text-[10px] font-mono text-text-primary"
        >
          {FILTER_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
        {mailStats.unread > 0 && (
          <>
            <span className="text-xs text-text-secondary flex-1">
              {mailStats.unread} unread of {mailStats.total} ({threadEntries.length} threads)
            </span>
            <button
              onClick={markMailRead}
              className="text-xs text-accent hover:text-accent-hover transition-colors"
            >
              Mark all read
            </button>
          </>
        )}
      </div>
      {/* Threaded messages */}
      {mailMessages.length === 0 ? (
        <div className="flex items-center justify-center p-8">
          <span className="text-xs text-text-muted">
            No inter-agent messages yet
          </span>
        </div>
      ) : (
        <div className="divide-y divide-border-subtle/50">
          {threadEntries.map(([threadId, msgs]) => {
            const first = msgs[0];
            const isExpanded = expandedThreads.has(threadId);
            const hasReplies = msgs.length > 1;
            const hasUnread = msgs.some((m) => !m.read);

            return (
              <div key={threadId}>
                {/* Thread header */}
                <button
                  onClick={() => {
                    setExpandedThreads((prev) => {
                      const next = new Set(prev);
                      if (next.has(threadId)) next.delete(threadId);
                      else next.add(threadId);
                      return next;
                    });
                  }}
                  className={`w-full text-left px-3 py-2.5 hover:bg-surface-raised/50 transition-colors ${hasUnread ? "bg-accent/5" : ""}`}
                >
                  <div className="flex items-center gap-2 mb-0.5">
                    {hasReplies && (
                      <span className="text-[10px] text-text-muted">
                        {isExpanded ? "\u25BC" : "\u25B6"}
                      </span>
                    )}
                    <span className="text-xs font-mono">
                      {MSG_TYPE_ICONS[first.msg_type] || "\u2022"}
                    </span>
                    <span className="text-xs font-mono text-accent">
                      {first.sender}
                    </span>
                    <span className="text-[10px] text-text-muted">{"\u2192"}</span>
                    <span className="text-xs font-mono text-text-secondary">
                      {first.recipient}
                    </span>
                    <span
                      className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${
                        MSG_TYPE_BADGE_STYLES[first.msg_type]
                          ? MSG_TYPE_BADGE_STYLES[first.msg_type]
                          : first.priority === "high" || first.priority === "urgent"
                            ? "text-error bg-error/10"
                            : "text-text-muted bg-surface"
                      }`}
                    >
                      {first.msg_type}
                    </span>
                    {hasReplies && (
                      <span className="text-[10px] text-text-muted font-mono ml-auto">
                        {msgs.length} msgs
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-text-primary font-medium">
                    {first.subject}
                  </div>
                  {!isExpanded && first.body && (
                    <div className="text-[10px] text-text-muted mt-0.5 font-mono">
                      {first.body.length > 120 ? first.body.slice(0, 120) + "..." : first.body}
                    </div>
                  )}
                  <div className="text-[9px] text-text-muted mt-1">
                    {new Date(first.created_at).toLocaleTimeString()}
                  </div>
                </button>
                {/* Expanded thread messages */}
                {isExpanded && msgs.map((msg, idx) => (
                  <div
                    key={msg.id}
                    className={`px-3 py-2 ml-4 border-l-2 ${
                      idx === 0 ? "border-accent/40" : "border-border-subtle"
                    } ${!msg.read ? "bg-accent/5" : ""}`}
                  >
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className="text-xs font-mono text-accent">
                        {msg.sender}
                      </span>
                      <span className="text-[10px] text-text-muted">{"\u2192"}</span>
                      <span className="text-xs font-mono text-text-secondary">
                        {msg.recipient}
                      </span>
                      <span className="text-[9px] text-text-muted ml-auto">
                        {new Date(msg.created_at).toLocaleTimeString()}
                      </span>
                    </div>
                    {msg.body && (
                      <div className="text-[10px] text-text-muted font-mono whitespace-pre-wrap">
                        {msg.body}
                      </div>
                    )}
                    {msg.attachments && msg.attachments.length > 0 && (
                      <div className="mt-1 space-y-1">
                        {msg.attachments.map((att, i) => (
                          <details key={i} className="border border-border-subtle rounded">
                            <summary className="text-[10px] px-2 py-0.5 cursor-pointer text-text-secondary">
                              {att.type}: {att.name}
                            </summary>
                            <pre className="text-[9px] p-2 overflow-x-auto bg-surface font-mono max-h-40">
                              {att.content}
                            </pre>
                          </details>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
