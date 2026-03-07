"use client";

import { useState, useEffect, useCallback } from "react";

interface GitHubPanelProps {
  projectDir: string;
  onClose: () => void;
}

interface SyncStatusInfo {
  last_synced: string;
  direction: string;
  tasks_pulled: number;
  tasks_pushed: number;
  conflicts: { task_id: string; reason: string }[];
  errors: string[];
  in_progress: boolean;
}

interface CIStatus {
  available: boolean;
  branch?: string;
  checks?: { name: string; status: string; conclusion: string; url?: string }[];
  message?: string;
}

interface PRResult {
  status: string;
  url?: string;
  number?: number;
  message?: string;
}

export function GitHubPanel({ projectDir, onClose }: GitHubPanelProps) {
  const [ciStatus, setCIStatus] = useState<CIStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [prTitle, setPRTitle] = useState("");
  const [prBody, setPRBody] = useState("");
  const [prResult, setPRResult] = useState<PRResult | null>(null);
  const [creatingPR, setCreatingPR] = useState(false);
  const [syncStatus, setSyncStatus] = useState<SyncStatusInfo | null>(null);
  const [syncing, setSyncing] = useState(false);

  const fetchSyncStatus = useCallback(async () => {
    try {
      const res = await fetch(`/api/tasks/sync/status?path=${encodeURIComponent(projectDir)}`);
      if (res.ok) {
        const data = await res.json();
        setSyncStatus(data);
      }
    } catch {
      // ignore
    }
  }, [projectDir]);

  const handleSyncNow = useCallback(async () => {
    if (syncing) return;
    setSyncing(true);
    try {
      const res = await fetch(`/api/tasks/sync?path=${encodeURIComponent(projectDir)}&direction=bidirectional`, { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        setSyncStatus(data);
      }
    } catch {
      // ignore
    } finally {
      setSyncing(false);
    }
  }, [projectDir, syncing]);

  useEffect(() => {
    fetchCI();
    fetchSyncStatus();
    const interval = setInterval(fetchCI, 15000);
    return () => clearInterval(interval);
  }, [projectDir, fetchSyncStatus]);

  const fetchCI = async () => {
    try {
      const res = await fetch(`/api/github/status?path=${encodeURIComponent(projectDir)}`);
      const data = await res.json();
      setCIStatus(data);
    } catch {
      setCIStatus({ available: false, message: "Failed to fetch" });
    } finally {
      setLoading(false);
    }
  };

  const createPR = async () => {
    if (!prTitle.trim()) return;
    setCreatingPR(true);
    try {
      const res = await fetch(
        `/api/github/pr?path=${encodeURIComponent(projectDir)}&title=${encodeURIComponent(prTitle)}&body=${encodeURIComponent(prBody)}`,
        { method: "POST" }
      );
      const data = await res.json();
      setPRResult(data);
    } catch {
      setPRResult({ status: "error", message: "Network error" });
    } finally {
      setCreatingPR(false);
    }
  };

  const CHECK_COLORS: Record<string, string> = {
    success: "text-success",
    failure: "text-error",
    pending: "text-warning",
    neutral: "text-text-muted",
  };

  const CHECK_ICONS: Record<string, string> = {
    success: "\u2713",
    failure: "\u2717",
    pending: "\u25CB",
    neutral: "\u2014",
  };

  return (
    <div className="fixed inset-y-0 right-0 w-96 bg-surface-raised border-l border-border-subtle z-40 flex flex-col shadow-xl animate-slide-in">
      {/* Header */}
      <div className="px-4 py-3 border-b border-border-subtle flex items-center justify-between">
        <span className="text-sm font-medium text-text-primary">GitHub</span>
        <button
          onClick={onClose}
          className="text-text-muted hover:text-text-primary transition-colors"
        >
          {"\u2715"}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {/* CI Status Section */}
        <div>
          <h3 className="text-xs font-mono text-text-muted mb-2 uppercase tracking-wider">
            CI Status
          </h3>
          {loading ? (
            <div className="text-xs text-text-muted">Checking...</div>
          ) : !ciStatus?.available ? (
            <div className="text-xs text-text-muted">
              {ciStatus?.message || "gh CLI not available"}
            </div>
          ) : (
            <div className="space-y-2">
              {ciStatus.branch && (
                <div className="text-xs font-mono text-text-secondary">
                  Branch: <span className="text-accent">{ciStatus.branch}</span>
                </div>
              )}
              {ciStatus.checks && ciStatus.checks.length > 0 ? (
                <div className="space-y-1">
                  {ciStatus.checks.map((check, i) => (
                    <div
                      key={i}
                      className="flex items-center gap-2 px-2 py-1 rounded bg-surface"
                    >
                      <span className={`text-xs ${CHECK_COLORS[check.conclusion] || CHECK_COLORS.neutral}`}>
                        {CHECK_ICONS[check.conclusion] || CHECK_ICONS.neutral}
                      </span>
                      <span className="text-xs text-text-primary flex-1 truncate">
                        {check.name}
                      </span>
                      <span className={`text-[10px] ${CHECK_COLORS[check.conclusion] || ""}`}>
                        {check.conclusion || check.status}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-xs text-text-muted">No CI checks found</div>
              )}
            </div>
          )}
        </div>

        {/* Create PR Section */}
        <div>
          <h3 className="text-xs font-mono text-text-muted mb-2 uppercase tracking-wider">
            Create Pull Request
          </h3>
          <div className="space-y-2">
            <input
              type="text"
              value={prTitle}
              onChange={(e) => setPRTitle(e.target.value)}
              placeholder="PR title..."
              className="w-full rounded-md border border-border-subtle bg-surface px-3 py-1.5 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent"
            />
            <textarea
              value={prBody}
              onChange={(e) => setPRBody(e.target.value)}
              placeholder="PR description (optional)..."
              rows={4}
              className="w-full rounded-md border border-border-subtle bg-surface px-3 py-1.5 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent resize-none"
            />
            <button
              onClick={createPR}
              disabled={!prTitle.trim() || creatingPR}
              className="w-full rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-white hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {creatingPR ? "Creating..." : "Create PR"}
            </button>

            {prResult && (
              <div
                className={`rounded-md px-3 py-2 text-xs ${
                  prResult.status === "ok"
                    ? "bg-success/10 text-success border border-success/30"
                    : "bg-error/10 text-error border border-error/30"
                }`}
              >
                {prResult.status === "ok" ? (
                  <span>
                    PR #{prResult.number} created.{" "}
                    {prResult.url && (
                      <a
                        href={prResult.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="underline"
                      >
                        Open on GitHub
                      </a>
                    )}
                  </span>
                ) : (
                  <span>{prResult.message || "Failed to create PR"}</span>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Task Sync Section */}
        <div>
          <h3 className="text-xs font-mono text-text-muted mb-2 uppercase tracking-wider">
            Task Sync
          </h3>
          <div className="space-y-2">
            {/* Sync status */}
            <div className="rounded-md border border-border-subtle bg-surface p-3 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs text-text-secondary">
                  {syncStatus?.last_synced
                    ? `Last synced: ${new Date(syncStatus.last_synced).toLocaleString()}`
                    : "Never synced"}
                </span>
                {syncStatus?.direction && (
                  <span className="text-[10px] text-text-muted font-mono px-1.5 py-0.5 rounded border border-border-subtle bg-surface-raised">
                    {syncStatus.direction}
                  </span>
                )}
              </div>

              {/* Stats */}
              {syncStatus?.last_synced && (
                <div className="flex items-center gap-3 text-[10px] text-text-muted font-mono">
                  {syncStatus.tasks_pulled > 0 && (
                    <span className="text-success">+{syncStatus.tasks_pulled} pulled</span>
                  )}
                  {syncStatus.tasks_pushed > 0 && (
                    <span className="text-accent">{syncStatus.tasks_pushed} pushed</span>
                  )}
                </div>
              )}

              {/* Errors */}
              {syncStatus?.errors && syncStatus.errors.length > 0 && (
                <div className="space-y-1">
                  {syncStatus.errors.map((err, i) => (
                    <div key={i} className="text-[10px] text-error bg-error/10 px-2 py-1 rounded">
                      {err}
                    </div>
                  ))}
                </div>
              )}

              {/* Conflicts */}
              {syncStatus?.conflicts && syncStatus.conflicts.length > 0 && (
                <div className="space-y-1">
                  <span className="text-[10px] text-warning font-medium">Conflicts:</span>
                  {syncStatus.conflicts.map((c, i) => (
                    <div key={i} className="text-[10px] text-warning bg-warning/10 px-2 py-1 rounded">
                      {c.task_id}: {c.reason}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Sync button */}
            <button
              onClick={handleSyncNow}
              disabled={syncing}
              className="w-full rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-white hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {syncing ? "Syncing..." : "Sync Now"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
