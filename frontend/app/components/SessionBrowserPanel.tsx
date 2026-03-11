"use client";

import { useState, useEffect, useCallback } from "react";

interface SessionRecord {
  id: string;
  project_dir: string;
  mode: string;
  model: string;
  title: string;
  status: string;
  is_team: number;
  agent_count: number;
  tasks_total: number;
  tasks_completed: number;
  total_cost_usd: number;
  total_input_tokens: number;
  total_output_tokens: number;
  files_added: number;
  files_modified: number;
  files_deleted: number;
  lines_added: number;
  lines_deleted: number;
  created_at: string;
  completed_at: string | null;
  task_input: string;
  error_message: string | null;
  messages?: MessageRecord[];
  file_changes?: FileChangeRecord[];
}

interface MessageRecord {
  id: string;
  agent_name: string;
  phase: string;
  role: string;
  content_summary: string;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  model: string;
  turn_number: number;
  duration_ms: number;
  snapshot_before: string | null;
  snapshot_after: string | null;
  created_at: string;
}

interface FileChangeRecord {
  file_path: string;
  change_type: string;
  additions: number;
  deletions: number;
}

interface SessionBrowserPanelProps {
  projectDir?: string;
}

const MODE_COLORS: Record<string, string> = {
  greenfield: "bg-green-500/20 text-green-400",
  feature: "bg-blue-500/20 text-blue-400",
  refactor: "bg-purple-500/20 text-purple-400",
  fix: "bg-red-500/20 text-red-400",
  evolve: "bg-yellow-500/20 text-yellow-400",
  security: "bg-orange-500/20 text-orange-400",
};

const STATUS_DOTS: Record<string, string> = {
  running: "bg-accent animate-pulse",
  completed: "bg-success",
  stopped: "bg-warning",
  error: "bg-error",
  archived: "bg-text-muted",
};

function formatDuration(start: string, end: string | null): string {
  if (!end) return "running...";
  const ms = new Date(end).getTime() - new Date(start).getTime();
  if (ms < 60000) return `${Math.round(ms / 1000)}s`;
  if (ms < 3600000) return `${Math.round(ms / 60000)}m`;
  return `${(ms / 3600000).toFixed(1)}h`;
}

function formatTime(ts: string): string {
  try {
    const d = new Date(ts);
    return d.toLocaleString([], {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

function SessionCard({
  session,
  onClick,
}: {
  session: SessionRecord;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="w-full text-left p-3 rounded-lg border border-border-subtle bg-surface-raised hover:border-accent/40 transition-colors"
    >
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-2">
          <span
            className={`w-2 h-2 rounded-full ${STATUS_DOTS[session.status] || "bg-text-muted"}`}
          />
          <span
            className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${MODE_COLORS[session.mode] || "bg-surface text-text-muted"}`}
          >
            {session.mode}
          </span>
          {session.is_team ? (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent/10 text-accent">
              team ({session.agent_count})
            </span>
          ) : null}
        </div>
        <span className="text-[10px] text-text-muted font-mono">
          ${session.total_cost_usd.toFixed(3)}
        </span>
      </div>

      <p className="text-xs text-text-primary truncate mb-1">
        {session.title || session.task_input?.slice(0, 80) || "Untitled session"}
      </p>

      <div className="flex items-center gap-3 text-[10px] text-text-muted">
        <span>{formatTime(session.created_at)}</span>
        <span>{formatDuration(session.created_at, session.completed_at)}</span>
        {session.tasks_total > 0 && (
          <span>
            {session.tasks_completed}/{session.tasks_total} tasks
          </span>
        )}
        {(session.files_added + session.files_modified + session.files_deleted) > 0 && (
          <span>
            <span className="text-success">+{session.lines_added}</span>
            {" / "}
            <span className="text-error">-{session.lines_deleted}</span>
          </span>
        )}
      </div>
    </button>
  );
}

type DetailTab = "timeline" | "messages" | "files";

function SessionDetailView({
  session,
  onBack,
}: {
  session: SessionRecord;
  onBack: () => void;
}) {
  const [tab, setTab] = useState<DetailTab>("timeline");

  const messages = session.messages || [];
  const fileChanges = session.file_changes || [];

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="p-3 border-b border-border-subtle">
        <button
          onClick={onBack}
          className="text-xs text-accent hover:underline mb-2"
        >
          &larr; Back to sessions
        </button>
        <div className="flex items-center gap-2 mb-1">
          <span
            className={`w-2 h-2 rounded-full ${STATUS_DOTS[session.status] || "bg-text-muted"}`}
          />
          <span
            className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${MODE_COLORS[session.mode] || "bg-surface text-text-muted"}`}
          >
            {session.mode}
          </span>
          <span className="text-xs text-text-secondary font-mono">
            {session.status}
          </span>
        </div>
        <p className="text-sm text-text-primary">{session.title || "Untitled"}</p>
        <div className="flex items-center gap-4 mt-1 text-[10px] text-text-muted">
          <span>${session.total_cost_usd.toFixed(3)}</span>
          <span>{formatDuration(session.created_at, session.completed_at)}</span>
          <span>
            {session.tasks_completed}/{session.tasks_total} tasks
          </span>
          {session.files_added + session.files_modified + session.files_deleted > 0 && (
            <span>
              {session.files_added + session.files_modified + session.files_deleted} files changed
            </span>
          )}
        </div>
        {session.error_message && (
          <p className="text-xs text-error mt-1 truncate">{session.error_message}</p>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 px-3 py-2 border-b border-border-subtle">
        {(["timeline", "messages", "files"] as DetailTab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-2 py-1 rounded text-[10px] ${
              tab === t
                ? "bg-accent/15 text-accent font-medium"
                : "text-text-muted hover:text-text-secondary"
            }`}
          >
            {t.charAt(0).toUpperCase() + t.slice(1)}
            {t === "messages" && messages.length > 0 && (
              <span className="ml-1 text-text-muted">({messages.length})</span>
            )}
            {t === "files" && fileChanges.length > 0 && (
              <span className="ml-1 text-text-muted">({fileChanges.length})</span>
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto min-h-0 p-3">
        {tab === "timeline" && (
          <div className="space-y-2">
            {messages.map((msg, i) => (
              <div
                key={msg.id || i}
                className="flex items-start gap-2 py-1.5 border-l-2 border-accent/30 pl-3"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 text-[10px]">
                    <span className="font-medium text-text-secondary">
                      {msg.phase}
                    </span>
                    <span className="text-text-muted">
                      Turn {msg.turn_number}
                    </span>
                    {msg.agent_name && (
                      <span className="text-accent">{msg.agent_name}</span>
                    )}
                    <span className="text-text-muted font-mono">
                      {msg.duration_ms > 0
                        ? `${(msg.duration_ms / 1000).toFixed(1)}s`
                        : ""}
                    </span>
                  </div>
                  {msg.content_summary && (
                    <p className="text-xs text-text-muted mt-0.5 truncate">
                      {msg.content_summary}
                    </p>
                  )}
                </div>
                <div className="text-[10px] text-text-muted whitespace-nowrap text-right">
                  <div>${msg.cost_usd.toFixed(4)}</div>
                  <div>
                    {(msg.input_tokens / 1000).toFixed(1)}k/{(msg.output_tokens / 1000).toFixed(1)}k
                  </div>
                </div>
              </div>
            ))}
            {messages.length === 0 && (
              <p className="text-xs text-text-muted text-center py-4">
                No message data recorded for this session.
              </p>
            )}
          </div>
        )}

        {tab === "messages" && (
          <div className="space-y-2">
            {messages.map((msg, i) => (
              <div
                key={msg.id || i}
                className="p-2 rounded border border-border-subtle bg-surface"
              >
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2 text-[10px]">
                    <span className="font-mono text-text-secondary">
                      {msg.model || "unknown"}
                    </span>
                    <span className="text-accent">{msg.phase}</span>
                  </div>
                  <span className="text-[10px] text-text-muted">
                    {formatTime(msg.created_at)}
                  </span>
                </div>
                <p className="text-xs text-text-primary whitespace-pre-wrap">
                  {msg.content_summary || "(no summary)"}
                </p>
                <div className="flex items-center gap-3 mt-1 text-[10px] text-text-muted">
                  <span>In: {msg.input_tokens.toLocaleString()}</span>
                  <span>Out: {msg.output_tokens.toLocaleString()}</span>
                  <span>${msg.cost_usd.toFixed(4)}</span>
                  {msg.snapshot_before && (
                    <span className="text-accent" title={msg.snapshot_before}>
                      snap
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {tab === "files" && (
          <div className="space-y-1">
            {fileChanges.map((fc, i) => (
              <div
                key={i}
                className="flex items-center justify-between px-2 py-1.5 rounded hover:bg-surface-raised/50"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span
                    className={`text-[10px] font-mono ${
                      fc.change_type === "added"
                        ? "text-success"
                        : fc.change_type === "deleted"
                          ? "text-error"
                          : "text-warning"
                    }`}
                  >
                    {fc.change_type === "added"
                      ? "A"
                      : fc.change_type === "deleted"
                        ? "D"
                        : "M"}
                  </span>
                  <span className="text-xs text-text-primary font-mono truncate">
                    {fc.file_path}
                  </span>
                </div>
                <div className="flex items-center gap-2 text-[10px] whitespace-nowrap">
                  {fc.additions > 0 && (
                    <span className="text-success">+{fc.additions}</span>
                  )}
                  {fc.deletions > 0 && (
                    <span className="text-error">-{fc.deletions}</span>
                  )}
                </div>
              </div>
            ))}
            {fileChanges.length === 0 && (
              <p className="text-xs text-text-muted text-center py-4">
                No file changes recorded.
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export function SessionBrowserPanel({ projectDir }: SessionBrowserPanelProps) {
  const [sessions, setSessions] = useState<SessionRecord[]>([]);
  const [selectedSession, setSelectedSession] = useState<SessionRecord | null>(null);
  const [loading, setLoading] = useState(false);
  const [modeFilter, setModeFilter] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string | null>(null);

  const fetchSessions = useCallback(async () => {
    if (!projectDir) return;
    setLoading(true);
    try {
      const params = new URLSearchParams({ path: projectDir });
      if (modeFilter) params.set("mode", modeFilter);
      if (statusFilter) params.set("status", statusFilter);
      const res = await fetch(`/api/sessions?${params}`);
      const data = await res.json();
      if (data.sessions) setSessions(data.sessions);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [projectDir, modeFilter, statusFilter]);

  const fetchDetail = useCallback(
    async (sessionId: string) => {
      if (!projectDir) return;
      try {
        const res = await fetch(
          `/api/sessions/${sessionId}?path=${encodeURIComponent(projectDir)}`
        );
        const data = await res.json();
        if (data.id) setSelectedSession(data);
      } catch {
        // ignore
      }
    },
    [projectDir]
  );

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  if (selectedSession) {
    return (
      <SessionDetailView
        session={selectedSession}
        onBack={() => setSelectedSession(null)}
      />
    );
  }

  const modes = ["greenfield", "feature", "refactor", "fix", "evolve", "security"];
  const statuses = ["running", "completed", "stopped", "error"];

  return (
    <div className="flex flex-col h-full">
      {/* Filter bar */}
      <div className="p-2 border-b border-border-subtle flex items-center gap-1 flex-wrap">
        <button
          onClick={() => setModeFilter(null)}
          className={`px-1.5 py-0.5 rounded text-[10px] ${
            !modeFilter ? "bg-accent/15 text-accent" : "text-text-muted hover:text-text-secondary"
          }`}
        >
          All
        </button>
        {modes.map((m) => (
          <button
            key={m}
            onClick={() => setModeFilter(modeFilter === m ? null : m)}
            className={`px-1.5 py-0.5 rounded text-[10px] ${
              modeFilter === m
                ? "bg-accent/15 text-accent"
                : "text-text-muted hover:text-text-secondary"
            }`}
          >
            {m}
          </button>
        ))}
        <span className="mx-1 text-border-subtle">|</span>
        {statuses.map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(statusFilter === s ? null : s)}
            className={`px-1.5 py-0.5 rounded text-[10px] flex items-center gap-1 ${
              statusFilter === s
                ? "bg-accent/15 text-accent"
                : "text-text-muted hover:text-text-secondary"
            }`}
          >
            <span className={`w-1.5 h-1.5 rounded-full ${STATUS_DOTS[s] || "bg-text-muted"}`} />
            {s}
          </button>
        ))}
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto min-h-0 p-2 space-y-1.5">
        {loading && sessions.length === 0 && (
          <p className="text-xs text-text-muted text-center py-8">Loading sessions...</p>
        )}
        {!loading && sessions.length === 0 && (
          <p className="text-xs text-text-muted text-center py-8">
            No sessions found. Run an agent session to see history here.
          </p>
        )}
        {sessions.map((s) => (
          <SessionCard key={s.id} session={s} onClick={() => fetchDetail(s.id)} />
        ))}
      </div>
    </div>
  );
}
