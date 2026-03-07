"use client";

import { useState, useEffect, useCallback } from "react";
import { ConfirmModal } from "./ConfirmModal";

interface GitCommit {
  sha: string;
  short_sha: string;
  message: string;
  timestamp: string;
  author: string;
  files_changed: number;
  insertions: number;
  deletions: number;
  task_summary?: { total: number; done: number };
}

function relativeTime(isoDate: string): string {
  try {
    const diff = Date.now() - new Date(isoDate).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    const days = Math.floor(hrs / 24);
    return `${days}d ago`;
  } catch {
    return "";
  }
}

export function CheckpointPanel({
  projectDir,
  status,
}: {
  projectDir: string;
  status?: string;
}) {
  const [commits, setCommits] = useState<GitCommit[]>([]);
  const [loading, setLoading] = useState(true);
  const [resetting, setResetting] = useState<string | null>(null);
  const [resetConfirm, setResetConfirm] = useState<{ sha: string; message: string } | null>(null);

  const fetchCommits = useCallback(async () => {
    if (!projectDir) return;
    try {
      const res = await fetch(
        `/api/session-history?path=${encodeURIComponent(projectDir)}&limit=100`
      );
      if (!res.ok) {
        setCommits([]);
        return;
      }
      const data = await res.json();
      const timeline: GitCommit[] = (data.timeline || []).map(
        (c: Record<string, unknown>) => ({
          sha: c.sha as string,
          short_sha: (c.sha as string).slice(0, 8),
          message: c.message as string,
          timestamp: c.timestamp as string,
          author: c.author as string,
          files_changed: (c.files_changed as number) || 0,
          insertions: (c.insertions as number) || 0,
          deletions: (c.deletions as number) || 0,
          task_summary: c.task_summary as
            | { total: number; done: number }
            | undefined,
        })
      );
      setCommits(timeline);
    } catch {
      setCommits([]);
    } finally {
      setLoading(false);
    }
  }, [projectDir]);

  // Initial fetch + poll while running
  useEffect(() => {
    fetchCommits();
    if (status === "running") {
      const interval = setInterval(fetchCommits, 10000);
      return () => clearInterval(interval);
    }
  }, [fetchCommits, status]);

  const handleResetClick = (sha: string, message: string) => {
    setResetConfirm({ sha, message });
  };

  const handleResetConfirm = async () => {
    if (!resetConfirm) return;
    const { sha } = resetConfirm;
    setResetConfirm(null);
    setResetting(sha);
    try {
      const res = await fetch("/api/git/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: projectDir, sha }),
      });
      const data = await res.json();
      if (data.status === "ok") {
        await fetchCommits();
      } else {
        alert(`Reset failed: ${data.error || "Unknown error"}`);
      }
    } catch {
      alert("Reset request failed");
    } finally {
      setResetting(null);
    }
  };

  const handleResetCancel = () => setResetConfirm(null);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-32 text-xs text-text-muted">
        Loading git history...
      </div>
    );
  }

  if (commits.length === 0) {
    return (
      <div className="flex items-center justify-center h-32 text-xs text-text-muted">
        No git commits found. Commits will appear here as the agent works.
      </div>
    );
  }

  return (
    <div className="overflow-y-auto h-full p-3">
      {/* Timeline */}
      <div className="relative">
        {/* Vertical line */}
        <div className="absolute left-3 top-0 bottom-0 w-px bg-border-subtle" />

        <div className="space-y-3">
          {commits.map((c, idx) => (
            <div key={c.sha} className="relative pl-8">
              {/* Timeline dot */}
              <div
                className={`absolute left-2 top-2 w-2.5 h-2.5 rounded-full border-2 ${
                  idx === 0
                    ? "bg-accent border-accent"
                    : "bg-surface border-border-default"
                }`}
              />

              <div className="rounded-lg border border-border-subtle bg-surface-raised p-2.5">
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2 min-w-0 flex-1">
                    <span className="text-[10px] font-mono text-accent bg-accent/10 px-1.5 py-0.5 rounded shrink-0">
                      {c.short_sha}
                    </span>
                    <span className="text-xs font-mono text-text-primary font-medium truncate">
                      {c.message}
                    </span>
                  </div>
                  {idx > 0 && (
                    <button
                      onClick={() => handleResetClick(c.sha, c.message)}
                      disabled={resetting === c.sha}
                      className="text-[10px] font-mono px-2 py-0.5 rounded border border-warning/30 text-warning hover:bg-warning/10 transition-colors disabled:opacity-50 shrink-0 ml-2"
                    >
                      {resetting === c.sha ? "Resetting..." : "Reset"}
                    </button>
                  )}
                </div>
                <div className="flex items-center gap-3 text-[10px] text-text-muted font-mono">
                  <span>{relativeTime(c.timestamp)}</span>
                  {c.files_changed > 0 && (
                    <span>
                      {c.files_changed} file{c.files_changed !== 1 ? "s" : ""}
                    </span>
                  )}
                  {c.insertions > 0 && (
                    <span className="text-success">+{c.insertions}</span>
                  )}
                  {c.deletions > 0 && (
                    <span className="text-error">-{c.deletions}</span>
                  )}
                  {c.task_summary && (
                    <span>
                      {c.task_summary.done}/{c.task_summary.total} tasks
                    </span>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <ConfirmModal
        open={!!resetConfirm}
        title="Reset to commit"
        message={
          resetConfirm
            ? `Reset project to commit ${resetConfirm.sha.slice(0, 8)}?\n\n"${resetConfirm.message}"\n\nLater commits will be lost.`
            : ""
        }
        confirmLabel="Reset"
        cancelLabel="Cancel"
        variant="danger"
        onConfirm={handleResetConfirm}
        onCancel={handleResetCancel}
      />
    </div>
  );
}
