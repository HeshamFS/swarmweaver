"use client";

import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { DiffViewer } from "./DiffViewer";

interface CommitEntry {
  sha: string;
  message: string;
  timestamp: string;
  author: string;
  files_changed: number;
  insertions: number;
  deletions: number;
  task_summary?: {
    total: number;
    done: number;
  };
}

interface SessionReplayProps {
  projectDir: string;
  onClose: () => void;
}

const SPEED_OPTIONS = [
  { label: "0.5x", value: 0.5 },
  { label: "1x", value: 1 },
  { label: "2x", value: 2 },
];

export function SessionReplay({ projectDir, onClose }: SessionReplayProps) {
  const [timeline, setTimeline] = useState<CommitEntry[]>([]);
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [loading, setLoading] = useState(true);
  const [commitDetail, setCommitDetail] = useState<{
    diff: string | null;
    task_state: Record<string, unknown> | null;
  } | null>(null);
  const [commitSearch, setCommitSearch] = useState("");
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const playRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Filter timeline by search query (case-insensitive)
  const filteredTimeline = useMemo(() => {
    if (!commitSearch.trim()) return timeline;
    const q = commitSearch.toLowerCase();
    return timeline.filter(
      (c) =>
        c.message.toLowerCase().includes(q) ||
        c.sha.toLowerCase().startsWith(q) ||
        c.author.toLowerCase().includes(q)
    );
  }, [timeline, commitSearch]);

  useEffect(() => {
    fetchTimeline();
  }, [projectDir]);

  const fetchTimeline = async () => {
    if (!projectDir) return;
    setLoading(true);
    try {
      const res = await fetch(
        `/api/session-history?path=${encodeURIComponent(projectDir)}&limit=100`
      );
      const data = await res.json();
      const tl = (data.timeline || []).reverse(); // Oldest first
      setTimeline(tl);
      if (tl.length > 0) setSelectedIdx(tl.length - 1);
    } catch {
      // Ignore
    } finally {
      setLoading(false);
    }
  };

  const fetchCommitDetail = useCallback(
    async (sha: string) => {
      try {
        const res = await fetch(
          `/api/replay/commit/${sha}?path=${encodeURIComponent(projectDir)}`
        );
        const data = await res.json();
        setCommitDetail({
          diff: data.diff,
          task_state: data.task_state,
        });
      } catch {
        setCommitDetail(null);
      }
    },
    [projectDir]
  );

  useEffect(() => {
    if (timeline.length > 0 && timeline[selectedIdx]) {
      fetchCommitDetail(timeline[selectedIdx].sha);
    }
  }, [selectedIdx, timeline, fetchCommitDetail]);

  // Play/pause auto-advance with speed control
  useEffect(() => {
    if (playing) {
      const interval = 1500 / playbackSpeed;
      playRef.current = setInterval(() => {
        setSelectedIdx((prev) => {
          if (prev >= timeline.length - 1) {
            setPlaying(false);
            return prev;
          }
          return prev + 1;
        });
      }, interval);
    } else {
      if (playRef.current) clearInterval(playRef.current);
    }
    return () => {
      if (playRef.current) clearInterval(playRef.current);
    };
  }, [playing, timeline.length, playbackSpeed]);

  const selected = timeline[selectedIdx];

  // Calculate progress sparkline data
  const sparklineData = timeline
    .map((c) => (c.task_summary ? c.task_summary.done : null))
    .filter((v): v is number => v !== null);

  if (loading) {
    return (
      <div className="border-b border-border-subtle bg-surface-raised px-4 py-6">
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm font-medium text-text-primary">
            Session Replay
          </span>
          <button
            onClick={onClose}
            className="text-text-muted hover:text-text-primary text-xs"
          >
            Close {"\u2715"}
          </button>
        </div>
        <span className="text-xs text-text-muted">Loading history...</span>
      </div>
    );
  }

  if (timeline.length === 0) {
    return (
      <div className="border-b border-border-subtle bg-surface-raised px-4 py-6">
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm font-medium text-text-primary">
            Session Replay
          </span>
          <button
            onClick={onClose}
            className="text-text-muted hover:text-text-primary text-xs"
          >
            Close {"\u2715"}
          </button>
        </div>
        <span className="text-xs text-text-muted">
          No git commits found in this project.
        </span>
      </div>
    );
  }

  return (
    <div className="border-b border-border-subtle bg-surface-raised px-4 py-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <span className="text-sm font-medium text-text-primary">
            Session Replay
          </span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setPlaying(!playing)}
              className="rounded-md border border-border-subtle px-2 py-1 text-xs text-text-secondary hover:text-text-primary transition-colors"
            >
              {playing ? "\u23F8 Pause" : "\u25B6 Play"}
            </button>
            {/* Playback speed controls */}
            <div className="flex items-center gap-0.5 ml-1">
              {SPEED_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => setPlaybackSpeed(opt.value)}
                  className={`rounded-md px-1.5 py-1 text-[10px] font-mono transition-colors ${
                    playbackSpeed === opt.value
                      ? "bg-accent text-white"
                      : "text-text-muted hover:text-text-secondary border border-border-subtle"
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
            <span className="text-xs text-text-muted font-mono ml-1">
              {selectedIdx + 1}/{timeline.length}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={commitSearch}
            onChange={(e) => setCommitSearch(e.target.value)}
            placeholder="Filter commits..."
            className="w-40 rounded-md border border-border-subtle bg-surface px-2 py-1 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent transition-colors"
          />
          <button
            onClick={onClose}
            className="text-text-muted hover:text-text-primary text-xs"
          >
            Close {"\u2715"}
          </button>
        </div>
      </div>

      {/* Filtered commits list */}
      {commitSearch.trim() && filteredTimeline.length > 0 && (
        <div className="mb-3 max-h-32 overflow-y-auto rounded border border-border-subtle bg-surface divide-y divide-border-subtle/50">
          {filteredTimeline.map((commit, i) => {
            const origIdx = timeline.indexOf(commit);
            return (
              <button
                key={commit.sha}
                onClick={() => {
                  setSelectedIdx(origIdx);
                  setPlaying(false);
                }}
                className={`w-full text-left px-3 py-1.5 text-xs hover:bg-surface-raised transition-colors ${
                  origIdx === selectedIdx ? "bg-accent/10 text-accent" : "text-text-secondary"
                }`}
              >
                <span className="font-mono text-text-muted mr-2">{commit.sha.substring(0, 7)}</span>
                <span className="truncate">{commit.message}</span>
              </button>
            );
          })}
        </div>
      )}
      {commitSearch.trim() && filteredTimeline.length === 0 && (
        <div className="mb-3 px-3 py-2 text-xs text-text-muted">
          No commits match &quot;{commitSearch}&quot;
        </div>
      )}

      {/* Full-width timeline with commit markers */}
      <div className="mb-3">
        <div className="relative w-full">
          {/* Track background */}
          <div className="w-full h-2 rounded-full bg-border-subtle relative">
            {/* Filled portion up to selected */}
            <div
              className="absolute top-0 left-0 h-full rounded-full bg-accent/40 transition-all duration-200"
              style={{ width: timeline.length > 1 ? `${(selectedIdx / (timeline.length - 1)) * 100}%` : "100%" }}
            />
            {/* Commit markers */}
            {timeline.map((commit, i) => {
              const pct = timeline.length > 1 ? (i / (timeline.length - 1)) * 100 : 50;
              const isActive = i === selectedIdx;
              return (
                <button
                  key={commit.sha}
                  onClick={() => {
                    setSelectedIdx(i);
                    setPlaying(false);
                  }}
                  className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 group"
                  style={{ left: `${pct}%` }}
                  title={`${commit.sha.substring(0, 7)}: ${commit.message}`}
                >
                  <span
                    className={`block rounded-full transition-all duration-200 ${
                      isActive
                        ? "w-3.5 h-3.5 bg-accent ring-2 ring-accent/30"
                        : "w-1.5 h-1.5 bg-text-muted/50 group-hover:w-2.5 group-hover:h-2.5 group-hover:bg-accent/70"
                    }`}
                  />
                </button>
              );
            })}
          </div>
          {/* Hidden range input for keyboard/accessibility */}
          <input
            type="range"
            min={0}
            max={timeline.length - 1}
            value={selectedIdx}
            onChange={(e) => {
              setSelectedIdx(parseInt(e.target.value));
              setPlaying(false);
            }}
            className="absolute inset-0 w-full opacity-0 cursor-pointer"
            style={{ height: "1.5rem", top: "-0.25rem" }}
          />
        </div>
      </div>

      {/* Progress sparkline */}
      {sparklineData.length > 1 && (
        <div className="flex items-end gap-px h-6 mb-3">
          {sparklineData.map((val, i) => {
            const max = Math.max(...sparklineData, 1);
            const height = Math.max(2, (val / max) * 24);
            return (
              <div
                key={i}
                className={`flex-1 rounded-t-sm transition-all ${
                  i === selectedIdx ? "bg-accent" : "bg-accent/30"
                }`}
                style={{ height: `${height}px` }}
              />
            );
          })}
        </div>
      )}

      {/* Selected commit detail */}
      {selected && (
        <div className="grid grid-cols-2 gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs text-text-muted font-mono">
                {selected.sha.substring(0, 7)}
              </span>
              <span className="text-xs text-text-muted">
                {new Date(selected.timestamp).toLocaleString()}
              </span>
            </div>
            <p className="text-sm text-text-primary font-medium truncate">
              {selected.message}
            </p>
            <div className="flex gap-3 mt-1">
              <span className="text-xs text-text-muted">
                {selected.files_changed} files
              </span>
              <span className="text-xs text-success">
                +{selected.insertions}
              </span>
              <span className="text-xs text-error">
                -{selected.deletions}
              </span>
            </div>

            {/* Diff viewer with min height */}
            {commitDetail?.diff && (
              <div className="mt-2 overflow-y-auto rounded border border-border-subtle" style={{ minHeight: "200px", maxHeight: "400px" }}>
                <DiffViewer diff={commitDetail.diff} />
              </div>
            )}
          </div>

          {/* Task state snapshot */}
          <div>
            {selected.task_summary ? (
              <div className="rounded-lg border border-border-subtle bg-surface p-3">
                <span className="text-xs text-text-muted block mb-1">
                  Task State
                </span>
                <div className="flex items-center gap-2">
                  <div className="flex-1 h-1.5 rounded-full bg-border-subtle overflow-hidden">
                    <div
                      className="h-full rounded-full bg-accent transition-all"
                      style={{
                        width: `${
                          selected.task_summary.total > 0
                            ? (selected.task_summary.done /
                                selected.task_summary.total) *
                              100
                            : 0
                        }%`,
                      }}
                    />
                  </div>
                  <span className="text-xs text-text-secondary font-mono">
                    {selected.task_summary.done}/{selected.task_summary.total}
                  </span>
                </div>
              </div>
            ) : (
              <div className="rounded-lg border border-border-subtle/50 bg-surface p-3">
                <span className="text-xs text-text-muted">
                  No task data for this commit
                </span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
