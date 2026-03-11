"use client";

import { useState, useEffect, useCallback } from "react";

interface SnapshotRecord {
  hash: string;
  label: string;
  timestamp: string;
  session_id: string;
  phase: string;
  iteration: number;
  files_count: number;
  worker_id: number | null;
}

interface DiffFile {
  path: string;
  status: string;
  additions: number;
  deletions: number;
  diff: string;
}

interface DiffResult {
  summary: { files_changed: number; insertions: number; deletions: number };
  files: DiffFile[];
}

interface SnapshotPanelProps {
  projectDir?: string;
  status?: string;
}

const PHASE_COLORS: Record<string, string> = {
  analyze: "bg-blue-500/20 text-blue-400",
  plan: "bg-purple-500/20 text-purple-400",
  implement: "bg-green-500/20 text-green-400",
  code: "bg-green-500/20 text-green-400",
  fix: "bg-red-500/20 text-red-400",
  migrate: "bg-yellow-500/20 text-yellow-400",
  improve: "bg-cyan-500/20 text-cyan-400",
  scan: "bg-orange-500/20 text-orange-400",
  initialize: "bg-indigo-500/20 text-indigo-400",
  investigate: "bg-amber-500/20 text-amber-400",
  audit: "bg-teal-500/20 text-teal-400",
  remediate: "bg-rose-500/20 text-rose-400",
};

function formatTime(ts: string): string {
  try {
    const d = new Date(ts);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return "";
  }
}

function DiffDrawer({
  diff,
  onClose,
  onRevert,
}: {
  diff: DiffResult;
  onClose: () => void;
  onRevert: (files: string[]) => void;
  projectDir: string;
  fromHash: string;
  toHash: string;
}) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [expandedFile, setExpandedFile] = useState<string | null>(null);

  const toggleFile = (path: string) => {
    const next = new Set(selected);
    if (next.has(path)) next.delete(path);
    else next.add(path);
    setSelected(next);
  };

  return (
    <div className="fixed inset-y-0 right-0 w-[500px] bg-surface border-l border-border-subtle shadow-xl z-50 flex flex-col">
      {/* Header */}
      <div className="p-3 border-b border-border-subtle flex items-center justify-between">
        <div>
          <span className="text-sm text-text-primary font-medium">Snapshot Diff</span>
          <div className="text-[10px] text-text-muted mt-0.5">
            {diff.summary.files_changed} files |{" "}
            <span className="text-success">+{diff.summary.insertions}</span>{" "}
            <span className="text-error">-{diff.summary.deletions}</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {selected.size > 0 && (
            <button
              onClick={() => onRevert(Array.from(selected))}
              className="px-2 py-1 rounded text-[10px] bg-warning/20 text-warning hover:bg-warning/30"
            >
              Revert {selected.size} file{selected.size > 1 ? "s" : ""}
            </button>
          )}
          <button
            onClick={onClose}
            className="px-2 py-1 rounded text-xs text-text-muted hover:text-text-primary"
          >
            Close
          </button>
        </div>
      </div>

      {/* File list */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {diff.files.map((f) => (
          <div key={f.path} className="border-b border-border-subtle">
            <div className="flex items-center gap-2 px-3 py-2 hover:bg-surface-raised/50">
              <input
                type="checkbox"
                checked={selected.has(f.path)}
                onChange={() => toggleFile(f.path)}
                className="rounded border-border-subtle"
              />
              <button
                onClick={() =>
                  setExpandedFile(expandedFile === f.path ? null : f.path)
                }
                className="flex-1 flex items-center justify-between min-w-0"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span
                    className={`text-[10px] font-mono ${
                      f.status === "added"
                        ? "text-success"
                        : f.status === "deleted"
                          ? "text-error"
                          : "text-warning"
                    }`}
                  >
                    {f.status === "added" ? "A" : f.status === "deleted" ? "D" : "M"}
                  </span>
                  <span className="text-xs text-text-primary font-mono truncate">
                    {f.path}
                  </span>
                </div>
                <div className="flex items-center gap-2 text-[10px]">
                  {f.additions > 0 && <span className="text-success">+{f.additions}</span>}
                  {f.deletions > 0 && <span className="text-error">-{f.deletions}</span>}
                  <span className="text-text-muted">{expandedFile === f.path ? "\u25B2" : "\u25BC"}</span>
                </div>
              </button>
            </div>
            {expandedFile === f.path && f.diff && (
              <pre className="px-3 py-2 text-[10px] font-mono bg-surface overflow-x-auto whitespace-pre text-text-muted">
                {f.diff.split("\n").map((line, i) => (
                  <div
                    key={i}
                    className={
                      line.startsWith("+")
                        ? "text-success"
                        : line.startsWith("-")
                          ? "text-error"
                          : line.startsWith("@@")
                            ? "text-accent"
                            : ""
                    }
                  >
                    {line}
                  </div>
                ))}
              </pre>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export function SnapshotPanel({ projectDir, status }: SnapshotPanelProps) {
  const [snapshots, setSnapshots] = useState<SnapshotRecord[]>([]);
  const [systemStatus, setSystemStatus] = useState<{
    available: boolean;
    snapshot_count: number;
    repo_size_mb: number;
  } | null>(null);
  const [diffResult, setDiffResult] = useState<DiffResult | null>(null);
  const [diffFrom, setDiffFrom] = useState<string>("");
  const [diffTo, setDiffTo] = useState<string>("");
  const [loading, setLoading] = useState(false);

  const fetchSnapshots = useCallback(async () => {
    if (!projectDir) return;
    try {
      const res = await fetch(
        `/api/snapshots?path=${encodeURIComponent(projectDir)}&limit=100`
      );
      const data = await res.json();
      if (data.snapshots) setSnapshots(data.snapshots);
    } catch {
      // ignore
    }
  }, [projectDir]);

  const fetchStatus = useCallback(async () => {
    if (!projectDir) return;
    try {
      const res = await fetch(
        `/api/snapshots/status?path=${encodeURIComponent(projectDir)}`
      );
      const data = await res.json();
      setSystemStatus(data);
    } catch {
      // ignore
    }
  }, [projectDir]);

  const openDiff = useCallback(
    async (from: string, to: string) => {
      if (!projectDir) return;
      setLoading(true);
      try {
        const params = new URLSearchParams({
          path: projectDir,
          from: from,
          to: to,
        });
        const res = await fetch(`/api/snapshots/diff?${params}`);
        const data = await res.json();
        if (data.summary) {
          setDiffResult(data);
          setDiffFrom(from);
          setDiffTo(to);
        }
      } catch {
        // ignore
      } finally {
        setLoading(false);
      }
    },
    [projectDir]
  );

  const handleRevert = useCallback(
    async (files: string[]) => {
      if (!projectDir || !diffFrom) return;
      try {
        const res = await fetch(
          `/api/snapshots/revert?path=${encodeURIComponent(projectDir)}`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ hash: diffFrom, files }),
          }
        );
        const data = await res.json();
        if (data.reverted?.length) {
          setDiffResult(null);
          fetchSnapshots();
        }
      } catch {
        // ignore
      }
    },
    [projectDir, diffFrom, fetchSnapshots]
  );

  useEffect(() => {
    fetchSnapshots();
    fetchStatus();
  }, [fetchSnapshots, fetchStatus]);

  // Poll while running
  useEffect(() => {
    if (status !== "running" || !projectDir) return;
    const interval = setInterval(fetchSnapshots, 10000);
    return () => clearInterval(interval);
  }, [status, projectDir, fetchSnapshots]);

  // Group snapshots by iteration (pre/post pairs)
  const pairs: Array<{
    iteration: number;
    phase: string;
    pre?: SnapshotRecord;
    post?: SnapshotRecord;
  }> = [];
  const iterMap = new Map<string, { pre?: SnapshotRecord; post?: SnapshotRecord }>();

  for (const s of snapshots) {
    const key = `${s.phase}:${s.iteration}`;
    if (!iterMap.has(key)) iterMap.set(key, {});
    const entry = iterMap.get(key)!;
    if (s.label.startsWith("pre:")) entry.pre = s;
    else entry.post = s;
  }

  for (const [key, val] of iterMap) {
    const [phase, iterStr] = key.split(":");
    pairs.push({
      iteration: parseInt(iterStr) || 0,
      phase,
      ...val,
    });
  }
  pairs.sort((a, b) => b.iteration - a.iteration);

  return (
    <div className="flex flex-col h-full">
      {/* Status bar */}
      <div className="px-3 py-2 border-b border-border-subtle flex items-center justify-between">
        <span className="text-xs text-text-muted">
          {systemStatus?.available
            ? `${systemStatus.snapshot_count} snapshots | ${systemStatus.repo_size_mb}MB`
            : "Snapshots unavailable"}
        </span>
        {loading && <span className="text-[10px] text-accent">Loading...</span>}
      </div>

      {/* Snapshot timeline */}
      <div className="flex-1 overflow-y-auto min-h-0 p-2 space-y-1.5">
        {pairs.length === 0 && (
          <p className="text-xs text-text-muted text-center py-8">
            No snapshots yet. Snapshots are captured before and after each agent turn.
          </p>
        )}
        {pairs.map((pair) => (
          <div
            key={`${pair.phase}-${pair.iteration}`}
            className="p-2.5 rounded-lg border border-border-subtle bg-surface-raised"
          >
            <div className="flex items-center justify-between mb-1.5">
              <div className="flex items-center gap-2">
                <span className="text-xs text-text-secondary font-mono">
                  #{pair.iteration}
                </span>
                <span
                  className={`text-[10px] px-1.5 py-0.5 rounded ${PHASE_COLORS[pair.phase] || "bg-surface text-text-muted"}`}
                >
                  {pair.phase}
                </span>
              </div>
              <span className="text-[10px] text-text-muted">
                {pair.pre ? formatTime(pair.pre.timestamp) : ""}
              </span>
            </div>

            <div className="flex items-center gap-2 text-[10px]">
              {pair.pre && (
                <span className="text-text-muted font-mono" title={pair.pre.hash}>
                  pre: {pair.pre.hash.slice(0, 8)}
                  <span className="ml-1 text-text-muted">
                    ({pair.pre.files_count} files)
                  </span>
                </span>
              )}
              {pair.pre && pair.post && (
                <span className="text-text-muted">&rarr;</span>
              )}
              {pair.post && (
                <span className="text-text-muted font-mono" title={pair.post.hash}>
                  post: {pair.post.hash.slice(0, 8)}
                </span>
              )}
            </div>

            {pair.pre && pair.post && (
              <div className="flex items-center gap-2 mt-2">
                <button
                  onClick={() => openDiff(pair.pre!.hash, pair.post!.hash)}
                  className="px-2 py-1 rounded text-[10px] bg-accent/10 text-accent hover:bg-accent/20"
                >
                  Compare
                </button>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Diff drawer */}
      {diffResult && (
        <DiffDrawer
          diff={diffResult}
          onClose={() => setDiffResult(null)}
          onRevert={handleRevert}
          projectDir={projectDir || ""}
          fromHash={diffFrom}
          toHash={diffTo}
        />
      )}
    </div>
  );
}
