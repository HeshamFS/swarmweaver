"use client";

import { useState, useEffect, useCallback } from "react";

interface SnapshotRecord {
  hash: string;
  tree_hash?: string;
  commit_hash?: string;
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

interface Bookmark {
  name: string;
  description: string;
  created_at: string;
  commit_hash: string;
  tree_hash: string;
  label: string;
  session_id: string;
  phase: string;
  iteration: number;
  files_count: number;
  snap_timestamp: string;
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

/* ------------------------------------------------------------------ */
/*  DiffDrawer                                                        */
/* ------------------------------------------------------------------ */

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

/* ------------------------------------------------------------------ */
/*  BookmarkModal                                                     */
/* ------------------------------------------------------------------ */

function BookmarkModal({
  hash,
  onClose,
  onSave,
}: {
  hash: string;
  onClose: () => void;
  onSave: (name: string, description: string) => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center">
      <div className="bg-surface border border-border-subtle rounded-lg p-4 w-80 shadow-xl">
        <h3 className="text-sm font-medium text-text-primary mb-3">Bookmark Snapshot</h3>
        <p className="text-[10px] text-text-muted mb-3 font-mono">{hash.slice(0, 12)}...</p>
        <input
          type="text"
          placeholder="Bookmark name (e.g. before-refactor)"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-full px-2 py-1.5 rounded text-xs bg-surface-raised border border-border-subtle text-text-primary placeholder:text-text-muted mb-2"
          autoFocus
        />
        <textarea
          placeholder="Description (optional)"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          className="w-full px-2 py-1.5 rounded text-xs bg-surface-raised border border-border-subtle text-text-primary placeholder:text-text-muted mb-3 h-16 resize-none"
        />
        <div className="flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-3 py-1.5 rounded text-xs text-text-muted hover:text-text-primary"
          >
            Cancel
          </button>
          <button
            onClick={() => { if (name.trim()) onSave(name.trim(), description.trim()); }}
            disabled={!name.trim()}
            className="px-3 py-1.5 rounded text-xs bg-accent/20 text-accent hover:bg-accent/30 disabled:opacity-40"
          >
            Save
          </button>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  RestorePreviewModal                                               */
/* ------------------------------------------------------------------ */

function RestorePreviewModal({
  diff,
  hash,
  onClose,
  onConfirm,
  loading,
}: {
  diff: DiffResult;
  hash: string;
  onClose: () => void;
  onConfirm: () => void;
  loading: boolean;
}) {
  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center">
      <div className="bg-surface border border-border-subtle rounded-lg p-4 w-96 shadow-xl max-h-[80vh] flex flex-col">
        <h3 className="text-sm font-medium text-text-primary mb-1">Restore Preview</h3>
        <p className="text-[10px] text-text-muted mb-3">
          Restoring to <span className="font-mono">{hash.slice(0, 12)}</span> will change:
        </p>
        <div className="text-xs text-text-secondary mb-3 flex gap-3">
          <span>{diff.summary.files_changed} files</span>
          <span className="text-success">+{diff.summary.insertions}</span>
          <span className="text-error">-{diff.summary.deletions}</span>
        </div>
        <div className="flex-1 overflow-y-auto min-h-0 border border-border-subtle rounded mb-3 max-h-64">
          {diff.files.map((f) => (
            <div key={f.path} className="flex items-center gap-2 px-2 py-1 text-[10px] border-b border-border-subtle last:border-0">
              <span className={`font-mono ${
                f.status === "added" ? "text-success" : f.status === "deleted" ? "text-error" : "text-warning"
              }`}>
                {f.status === "added" ? "A" : f.status === "deleted" ? "D" : "M"}
              </span>
              <span className="font-mono text-text-primary truncate">{f.path}</span>
              <span className="ml-auto text-text-muted">
                {f.additions > 0 && <span className="text-success">+{f.additions}</span>}
                {f.deletions > 0 && <span className="text-error ml-1">-{f.deletions}</span>}
              </span>
            </div>
          ))}
          {diff.files.length === 0 && (
            <p className="text-[10px] text-text-muted text-center py-4">No changes — already at this state.</p>
          )}
        </div>
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-3 py-1.5 rounded text-xs text-text-muted hover:text-text-primary">
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={loading || diff.files.length === 0}
            className="px-3 py-1.5 rounded text-xs bg-warning/20 text-warning hover:bg-warning/30 disabled:opacity-40"
          >
            {loading ? "Restoring..." : "Restore"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main SnapshotPanel                                                */
/* ------------------------------------------------------------------ */

type ViewMode = "timeline" | "bookmarks";

export function SnapshotPanel({ projectDir, status }: SnapshotPanelProps) {
  const [snapshots, setSnapshots] = useState<SnapshotRecord[]>([]);
  const [bookmarks, setBookmarks] = useState<Bookmark[]>([]);
  const [systemStatus, setSystemStatus] = useState<{
    available: boolean;
    snapshot_count: number;
    bookmark_count: number;
    repo_size_mb: number;
  } | null>(null);
  const [diffResult, setDiffResult] = useState<DiffResult | null>(null);
  const [diffFrom, setDiffFrom] = useState<string>("");
  const [diffTo, setDiffTo] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>("timeline");
  const [bookmarkTarget, setBookmarkTarget] = useState<string | null>(null);
  const [restorePreview, setRestorePreview] = useState<{ hash: string; diff: DiffResult } | null>(null);
  const [restoreLoading, setRestoreLoading] = useState(false);

  const fetchSnapshots = useCallback(async () => {
    if (!projectDir) return;
    try {
      const res = await fetch(`/api/snapshots?path=${encodeURIComponent(projectDir)}&limit=100`);
      const data = await res.json();
      if (data.snapshots) setSnapshots(data.snapshots);
    } catch { /* ignore */ }
  }, [projectDir]);

  const fetchBookmarks = useCallback(async () => {
    if (!projectDir) return;
    try {
      const res = await fetch(`/api/snapshots/bookmarks?path=${encodeURIComponent(projectDir)}`);
      const data = await res.json();
      if (data.bookmarks) setBookmarks(data.bookmarks);
    } catch { /* ignore */ }
  }, [projectDir]);

  const fetchStatus = useCallback(async () => {
    if (!projectDir) return;
    try {
      const res = await fetch(`/api/snapshots/status?path=${encodeURIComponent(projectDir)}`);
      const data = await res.json();
      setSystemStatus(data);
    } catch { /* ignore */ }
  }, [projectDir]);

  const openDiff = useCallback(
    async (from: string, to: string) => {
      if (!projectDir) return;
      setLoading(true);
      try {
        const params = new URLSearchParams({ path: projectDir, from, to });
        const res = await fetch(`/api/snapshots/diff?${params}`);
        const data = await res.json();
        if (data.summary) {
          setDiffResult(data);
          setDiffFrom(from);
          setDiffTo(to);
        }
      } catch { /* ignore */ }
      finally { setLoading(false); }
    },
    [projectDir]
  );

  const handleRevert = useCallback(
    async (files: string[]) => {
      if (!projectDir || !diffFrom) return;
      try {
        const res = await fetch(`/api/snapshots/revert?path=${encodeURIComponent(projectDir)}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ hash: diffFrom, files }),
        });
        const data = await res.json();
        if (data.reverted?.length) {
          setDiffResult(null);
          fetchSnapshots();
        }
      } catch { /* ignore */ }
    },
    [projectDir, diffFrom, fetchSnapshots]
  );

  const handleBookmarkSave = useCallback(
    async (name: string, description: string) => {
      if (!projectDir || !bookmarkTarget) return;
      try {
        await fetch(`/api/snapshots/bookmark?path=${encodeURIComponent(projectDir)}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ hash: bookmarkTarget, name, description }),
        });
        setBookmarkTarget(null);
        fetchBookmarks();
        fetchStatus();
      } catch { /* ignore */ }
    },
    [projectDir, bookmarkTarget, fetchBookmarks, fetchStatus]
  );

  const handleBookmarkDelete = useCallback(
    async (name: string) => {
      if (!projectDir) return;
      try {
        await fetch(`/api/snapshots/bookmark/${encodeURIComponent(name)}?path=${encodeURIComponent(projectDir)}`, {
          method: "DELETE",
        });
        fetchBookmarks();
        fetchStatus();
      } catch { /* ignore */ }
    },
    [projectDir, fetchBookmarks, fetchStatus]
  );

  const handlePreviewRestore = useCallback(
    async (hash: string) => {
      if (!projectDir) return;
      setRestoreLoading(true);
      try {
        const res = await fetch(`/api/snapshots/preview-restore?path=${encodeURIComponent(projectDir)}&hash=${hash}`);
        const data = await res.json();
        if (data.summary) {
          setRestorePreview({ hash, diff: data });
        }
      } catch { /* ignore */ }
      finally { setRestoreLoading(false); }
    },
    [projectDir]
  );

  const handleRestore = useCallback(
    async () => {
      if (!projectDir || !restorePreview) return;
      setRestoreLoading(true);
      try {
        const res = await fetch(`/api/snapshots/restore?path=${encodeURIComponent(projectDir)}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ hash: restorePreview.hash }),
        });
        const data = await res.json();
        if (data.restored) {
          setRestorePreview(null);
          fetchSnapshots();
        }
      } catch { /* ignore */ }
      finally { setRestoreLoading(false); }
    },
    [projectDir, restorePreview, fetchSnapshots]
  );

  useEffect(() => {
    fetchSnapshots();
    fetchBookmarks();
    fetchStatus();
  }, [fetchSnapshots, fetchBookmarks, fetchStatus]);

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

  // Check if a hash is bookmarked
  const bookmarkedHashes = new Set(bookmarks.map((b) => b.tree_hash));

  return (
    <div className="flex flex-col h-full">
      {/* Status bar + view toggle */}
      <div className="px-3 py-2 border-b border-border-subtle flex items-center justify-between">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setViewMode("timeline")}
            className={`text-[10px] px-2 py-0.5 rounded ${
              viewMode === "timeline" ? "bg-accent/20 text-accent" : "text-text-muted hover:text-text-primary"
            }`}
          >
            Timeline
          </button>
          <button
            onClick={() => setViewMode("bookmarks")}
            className={`text-[10px] px-2 py-0.5 rounded ${
              viewMode === "bookmarks" ? "bg-accent/20 text-accent" : "text-text-muted hover:text-text-primary"
            }`}
          >
            Bookmarks{bookmarks.length > 0 ? ` (${bookmarks.length})` : ""}
          </button>
        </div>
        <span className="text-[10px] text-text-muted">
          {systemStatus?.available
            ? `${systemStatus.snapshot_count} snaps | ${systemStatus.bookmark_count} saved | ${systemStatus.repo_size_mb}MB`
            : "Unavailable"}
        </span>
      </div>

      {/* View content */}
      <div className="flex-1 overflow-y-auto min-h-0 p-2 space-y-1.5">
        {viewMode === "timeline" ? (
          <>
            {pairs.length === 0 && (
              <p className="text-xs text-text-muted text-center py-8">
                No snapshots yet. Captured before/after each agent turn.
              </p>
            )}
            {pairs.map((pair) => {
              const treeHash = pair.post?.hash || pair.pre?.hash || "";
              const isBookmarked = bookmarkedHashes.has(treeHash);

              return (
                <div
                  key={`${pair.phase}-${pair.iteration}`}
                  className="p-2.5 rounded-lg border border-border-subtle bg-surface-raised"
                >
                  <div className="flex items-center justify-between mb-1.5">
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-text-secondary font-mono">#{pair.iteration}</span>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded ${PHASE_COLORS[pair.phase] || "bg-surface text-text-muted"}`}>
                        {pair.phase}
                      </span>
                      {isBookmarked && (
                        <span className="text-[10px] text-amber-400" title="Bookmarked">&#9733;</span>
                      )}
                    </div>
                    <span className="text-[10px] text-text-muted">
                      {pair.pre ? formatTime(pair.pre.timestamp) : ""}
                    </span>
                  </div>

                  <div className="flex items-center gap-2 text-[10px]">
                    {pair.pre && (
                      <span className="text-text-muted font-mono" title={pair.pre.hash}>
                        pre: {pair.pre.hash.slice(0, 8)}
                        <span className="ml-1">({pair.pre.files_count} files)</span>
                      </span>
                    )}
                    {pair.pre && pair.post && <span className="text-text-muted">&rarr;</span>}
                    {pair.post && (
                      <span className="text-text-muted font-mono" title={pair.post.hash}>
                        post: {pair.post.hash.slice(0, 8)}
                      </span>
                    )}
                  </div>

                  <div className="flex items-center gap-1.5 mt-2">
                    {pair.pre && pair.post && (
                      <button
                        onClick={() => openDiff(pair.pre!.hash, pair.post!.hash)}
                        className="px-2 py-1 rounded text-[10px] bg-accent/10 text-accent hover:bg-accent/20"
                      >
                        Compare
                      </button>
                    )}
                    {treeHash && (
                      <>
                        <button
                          onClick={() => setBookmarkTarget(treeHash)}
                          className={`px-2 py-1 rounded text-[10px] ${
                            isBookmarked
                              ? "bg-amber-500/20 text-amber-400"
                              : "bg-surface text-text-muted hover:text-text-primary hover:bg-surface-raised"
                          }`}
                          title={isBookmarked ? "Already bookmarked" : "Bookmark this snapshot"}
                        >
                          {isBookmarked ? "\u2605 Saved" : "\u2606 Bookmark"}
                        </button>
                        <button
                          onClick={() => handlePreviewRestore(treeHash)}
                          className="px-2 py-1 rounded text-[10px] bg-surface text-text-muted hover:text-warning hover:bg-warning/10"
                          title="Preview & restore to this point"
                        >
                          Restore
                        </button>
                      </>
                    )}
                  </div>
                </div>
              );
            })}
          </>
        ) : (
          <>
            {bookmarks.length === 0 && (
              <p className="text-xs text-text-muted text-center py-8">
                No bookmarks yet. Bookmark a snapshot to preserve it from cleanup.
              </p>
            )}
            {bookmarks.map((bm) => (
              <div
                key={bm.name}
                className="p-2.5 rounded-lg border border-amber-500/30 bg-surface-raised"
              >
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    <span className="text-amber-400 text-xs">&#9733;</span>
                    <span className="text-xs text-text-primary font-medium">{bm.name}</span>
                    {bm.phase && (
                      <span className={`text-[10px] px-1.5 py-0.5 rounded ${PHASE_COLORS[bm.phase] || "bg-surface text-text-muted"}`}>
                        {bm.phase} #{bm.iteration}
                      </span>
                    )}
                  </div>
                  <span className="text-[10px] text-text-muted">
                    {formatTime(bm.created_at)}
                  </span>
                </div>

                {bm.description && (
                  <p className="text-[10px] text-text-muted mb-1.5">{bm.description}</p>
                )}

                <div className="text-[10px] text-text-muted font-mono mb-2">
                  {bm.tree_hash.slice(0, 12)} | {bm.files_count} files
                </div>

                <div className="flex items-center gap-1.5">
                  <button
                    onClick={() => handlePreviewRestore(bm.tree_hash)}
                    className="px-2 py-1 rounded text-[10px] bg-warning/10 text-warning hover:bg-warning/20"
                  >
                    Restore
                  </button>
                  <button
                    onClick={() => handleBookmarkDelete(bm.name)}
                    className="px-2 py-1 rounded text-[10px] text-text-muted hover:text-error hover:bg-error/10"
                  >
                    Remove
                  </button>
                </div>
              </div>
            ))}
          </>
        )}
      </div>

      {loading && (
        <div className="px-3 py-1 border-t border-border-subtle">
          <span className="text-[10px] text-accent">Loading...</span>
        </div>
      )}

      {/* Modals */}
      {bookmarkTarget && (
        <BookmarkModal
          hash={bookmarkTarget}
          onClose={() => setBookmarkTarget(null)}
          onSave={handleBookmarkSave}
        />
      )}

      {restorePreview && (
        <RestorePreviewModal
          diff={restorePreview.diff}
          hash={restorePreview.hash}
          onClose={() => setRestorePreview(null)}
          onConfirm={handleRestore}
          loading={restoreLoading}
        />
      )}

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
