"use client";

import React, { useState, useMemo, useCallback } from "react";

// ── Types ──────────────────────────────────────────────────────

interface LspDiagnostic {
  uri: string;
  line: number;
  character: number;
  end_line: number;
  end_character: number;
  severity: number;
  severity_label: string;
  message: string;
  source: string | null;
  code: string | number | null;
}

interface LspServerInfo {
  language_id: string;
  server_name: string;
  status: "stopped" | "starting" | "ready" | "degraded" | "crashed";
  root_uri: string;
  pid: number | null;
  started_at: string;
  restart_count: number;
  open_files: number;
  diagnostic_count: number;
  worker_id: number | null;
}

interface LspCodeHealth {
  score: number;
  error_count: number;
  warning_count: number;
  info_count: number;
  hint_count: number;
  by_language: Record<string, { score: number; errors: number; warnings: number }>;
}

interface LspCrossWorkerAlert {
  source_worker_id: number;
  affected_worker_id: number;
  file_path: string;
  diagnostics: LspDiagnostic[];
  timestamp: string;
}

interface ImpactResult {
  file: string;
  line: number;
  references_count: number;
  callers: { name: string; file: string; line: number }[];
  callees: { name: string; file: string; line: number }[];
  risk: "low" | "medium" | "high" | "critical";
}

interface LspStats {
  total_found: number;
  total_resolved: number;
  active_count: number;
  active_errors: number;
  active_warnings: number;
  by_worker: Record<string, { found: number; resolved: number }>;
  by_severity: Record<number, { found: number; resolved: number }>;
  recent_events: {
    event: "found" | "resolved";
    uri: string;
    key: string;
    severity?: number;
    message?: string;
    worker_id: string;
    timestamp: number;
  }[];
}

interface LSPPanelProps {
  diagnostics: Record<string, LspDiagnostic[]>;
  serverStatus: Record<string, LspServerInfo>;
  codeHealth: LspCodeHealth | null;
  codeHealthTrend: number[];
  crossWorkerAlerts: LspCrossWorkerAlert[];
  projectDir: string;
  isTeamMode: boolean;
  workerCount: number;
  stats?: LspStats;
}

// ── Constants ──────────────────────────────────────────────────

const SEVERITY_COLORS: Record<number, string> = {
  1: "#ef4444", // Error - red
  2: "#f59e0b", // Warning - amber
  3: "#3b82f6", // Info - blue
  4: "#9ca3af", // Hint - gray
};

const SEVERITY_LABELS: Record<number, string> = {
  1: "ERROR",
  2: "WARN",
  3: "INFO",
  4: "HINT",
};

const STATUS_COLORS: Record<string, string> = {
  stopped: "#6b7280",
  starting: "#f59e0b",
  ready: "#22c55e",
  degraded: "#f59e0b",
  crashed: "#ef4444",
};

const LANGUAGE_ICONS: Record<string, string> = {
  typescript: "TS",
  typescriptreact: "TSX",
  javascript: "JS",
  python: "PY",
  go: "GO",
  rust: "RS",
  java: "JV",
  ruby: "RB",
  php: "PHP",
  kotlin: "KT",
  swift: "SW",
  css: "CSS",
  html: "HTM",
  yaml: "YML",
  shellscript: "SH",
};

const RISK_COLORS: Record<string, string> = {
  low: "bg-green-500/20 text-green-400 border-green-500/30",
  medium: "bg-amber-500/20 text-amber-400 border-amber-500/30",
  high: "bg-red-500/20 text-red-400 border-red-500/30",
  critical: "bg-purple-500/20 text-purple-400 border-purple-500/30",
};

type TabId = "diagnostics" | "servers" | "workers" | "impact" | "stats";
type SortField = "file" | "line" | "severity" | "message";
type SortDir = "asc" | "desc";
type GroupBy = "none" | "file" | "severity";

// ── Helpers ────────────────────────────────────────────────────

function truncatePath(uri: string, maxLen = 40): string {
  if (uri.length <= maxLen) return uri;
  const parts = uri.split("/");
  if (parts.length <= 2) return "..." + uri.slice(-maxLen);
  return ".../" + parts.slice(-2).join("/");
}

function buildSparklinePoints(values: number[], width: number, height: number): string {
  if (values.length === 0) return "";
  const max = Math.max(...values, 1);
  const step = width / Math.max(values.length - 1, 1);
  return values
    .map((v, i) => {
      const x = i * step;
      const y = height - (v / max) * height;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

function scoreColor(score: number): string {
  if (score > 80) return "#22c55e";
  if (score >= 50) return "#f59e0b";
  return "#ef4444";
}

// ── Component ──────────────────────────────────────────────────

export function LSPPanel({
  diagnostics,
  serverStatus,
  codeHealth,
  codeHealthTrend,
  crossWorkerAlerts,
  projectDir,
  isTeamMode,
  workerCount,
  stats,
}: LSPPanelProps) {
  const [activeTab, setActiveTab] = useState<TabId>("stats");

  // Diagnostics tab state
  const [sortField, setSortField] = useState<SortField>("severity");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [severityFilter, setSeverityFilter] = useState<number | null>(null);
  const [fileSearch, setFileSearch] = useState("");
  const [groupBy, setGroupBy] = useState<GroupBy>("none");

  // Impact tab state
  const [impactFile, setImpactFile] = useState("");
  const [impactLine, setImpactLine] = useState("");
  const [impactLoading, setImpactLoading] = useState(false);
  const [impactResult, setImpactResult] = useState<ImpactResult | null>(null);

  // ── Flatten diagnostics ────────────────────────────────────

  const allDiagnostics = useMemo(() => {
    const flat: (LspDiagnostic & { _file: string })[] = [];
    for (const [uri, diags] of Object.entries(diagnostics)) {
      for (const d of diags) {
        flat.push({ ...d, _file: uri });
      }
    }
    return flat;
  }, [diagnostics]);

  // ── Filter + Sort diagnostics ──────────────────────────────

  const filteredDiagnostics = useMemo(() => {
    let result = allDiagnostics;
    if (severityFilter !== null) {
      result = result.filter((d) => d.severity === severityFilter);
    }
    if (fileSearch.trim()) {
      const q = fileSearch.toLowerCase();
      result = result.filter((d) => d._file.toLowerCase().includes(q));
    }
    result.sort((a, b) => {
      let cmp = 0;
      switch (sortField) {
        case "file":
          cmp = a._file.localeCompare(b._file);
          break;
        case "line":
          cmp = a.line - b.line;
          break;
        case "severity":
          cmp = a.severity - b.severity;
          break;
        case "message":
          cmp = a.message.localeCompare(b.message);
          break;
      }
      return sortDir === "asc" ? cmp : -cmp;
    });
    return result;
  }, [allDiagnostics, severityFilter, fileSearch, sortField, sortDir]);

  // ── Grouped diagnostics ────────────────────────────────────

  const groupedDiagnostics = useMemo(() => {
    if (groupBy === "none") return null;
    const groups: Record<string, typeof filteredDiagnostics> = {};
    for (const d of filteredDiagnostics) {
      const key = groupBy === "file" ? d._file : SEVERITY_LABELS[d.severity] || "UNKNOWN";
      if (!groups[key]) groups[key] = [];
      groups[key].push(d);
    }
    return groups;
  }, [filteredDiagnostics, groupBy]);

  // ── Sort toggle ────────────────────────────────────────────

  const handleSort = useCallback(
    (field: SortField) => {
      if (sortField === field) {
        setSortDir((d) => (d === "asc" ? "desc" : "asc"));
      } else {
        setSortField(field);
        setSortDir("asc");
      }
    },
    [sortField]
  );

  // ── Server actions ─────────────────────────────────────────

  const handleServerAction = useCallback(
    async (serverId: string, action: "restart" | "stop" | "start") => {
      try {
        await fetch(`/api/lsp/servers/${encodeURIComponent(serverId)}/${action}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path: projectDir }),
        });
      } catch {
        /* ignore */
      }
    },
    [projectDir]
  );

  // ── Impact analysis ────────────────────────────────────────

  const handleImpactAnalyze = useCallback(async () => {
    if (!impactFile.trim()) return;
    setImpactLoading(true);
    setImpactResult(null);
    try {
      const params = new URLSearchParams({
        path: projectDir,
        file: impactFile.trim(),
      });
      if (impactLine.trim()) params.set("line", impactLine.trim());
      const res = await fetch(`/api/lsp/impact-analysis?${params}`);
      const data = await res.json();
      if (data && !data.error) {
        setImpactResult(data);
      }
    } catch {
      /* ignore */
    } finally {
      setImpactLoading(false);
    }
  }, [projectDir, impactFile, impactLine]);

  // ── Per-worker diagnostic counts ───────────────────────────

  const workerDiagCounts = useMemo(() => {
    if (!isTeamMode) return {};
    const counts: Record<
      number,
      { errors: number; warnings: number; infos: number; total: number }
    > = {};
    for (const server of Object.values(serverStatus)) {
      if (server.worker_id == null) continue;
      if (!counts[server.worker_id]) {
        counts[server.worker_id] = { errors: 0, warnings: 0, infos: 0, total: 0 };
      }
    }
    // Aggregate from diagnostics by scanning server mapping
    for (const [, diags] of Object.entries(diagnostics)) {
      for (const d of diags) {
        // Best effort: attribute by iterating servers
        for (const server of Object.values(serverStatus)) {
          if (server.worker_id == null) continue;
          if (!counts[server.worker_id]) {
            counts[server.worker_id] = { errors: 0, warnings: 0, infos: 0, total: 0 };
          }
          if (d.uri.startsWith(server.root_uri)) {
            counts[server.worker_id].total++;
            if (d.severity === 1) counts[server.worker_id].errors++;
            else if (d.severity === 2) counts[server.worker_id].warnings++;
            else counts[server.worker_id].infos++;
            break;
          }
        }
      }
    }
    return counts;
  }, [isTeamMode, diagnostics, serverStatus]);

  // ── Tabs ───────────────────────────────────────────────────

  const tabs: { id: TabId; label: string; visible: boolean }[] = [
    { id: "stats", label: "Stats", visible: true },
    { id: "diagnostics", label: "Diagnostics", visible: true },
    { id: "servers", label: "Servers", visible: true },
    { id: "workers", label: "Workers", visible: isTeamMode },
    { id: "impact", label: "Impact", visible: true },
  ];

  // ── Sort indicator ─────────────────────────────────────────

  const sortIndicator = (field: SortField) =>
    sortField === field ? (sortDir === "asc" ? " ^" : " v") : "";

  // ── Render ─────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-full overflow-hidden text-xs font-mono">
      {/* ── Section 1: Code Health Bar ─────────────────────── */}
      {codeHealth && (
        <div className="px-3 py-2 border-b border-border-subtle bg-surface-raised flex items-center gap-3 shrink-0">
          {/* Score badge */}
          <div className="flex items-center gap-2">
            <span
              className="text-lg font-bold"
              style={{ color: scoreColor(codeHealth.score) }}
            >
              {codeHealth.score}
            </span>
            <span className="text-text-muted text-[10px]">Health</span>
          </div>

          {/* Progress bar */}
          <div className="flex-1 h-1.5 rounded-full bg-border-subtle overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{
                width: `${codeHealth.score}%`,
                backgroundColor: scoreColor(codeHealth.score),
              }}
            />
          </div>

          {/* Per-language badges */}
          <div className="flex items-center gap-1 shrink-0">
            {Object.entries(codeHealth.by_language).map(([lang, info]) => (
              <span
                key={lang}
                className="px-1.5 py-0.5 rounded text-[10px] font-medium border"
                style={{
                  color: scoreColor(info.score),
                  borderColor: scoreColor(info.score) + "44",
                  backgroundColor: scoreColor(info.score) + "15",
                }}
                title={`${lang}: score ${info.score}, ${info.errors} errors, ${info.warnings} warnings`}
              >
                {LANGUAGE_ICONS[lang] || lang.slice(0, 3).toUpperCase()} {info.score}
              </span>
            ))}
          </div>

          {/* Sparkline */}
          {codeHealthTrend.length > 1 && (
            <svg
              width="60"
              height="20"
              viewBox="0 0 60 20"
              className="shrink-0"
              aria-label="Code health trend"
            >
              <polyline
                fill="none"
                stroke={scoreColor(codeHealth.score)}
                strokeWidth="1.5"
                strokeLinejoin="round"
                strokeLinecap="round"
                points={buildSparklinePoints(codeHealthTrend.slice(-20), 60, 18)}
              />
            </svg>
          )}

          {/* Error/Warning counts */}
          <div className="flex items-center gap-2 shrink-0">
            <span className="text-[10px]" style={{ color: SEVERITY_COLORS[1] }}>
              {codeHealth.error_count} err
            </span>
            <span className="text-[10px]" style={{ color: SEVERITY_COLORS[2] }}>
              {codeHealth.warning_count} warn
            </span>
          </div>
        </div>
      )}

      {/* ── Section 2: Tab navigation ──────────────────────── */}
      <div className="px-3 py-1.5 border-b border-border-subtle bg-surface-raised shrink-0">
        <div className="flex gap-0.5" role="tablist" aria-label="LSP panel tabs">
          {tabs
            .filter((t) => t.visible)
            .map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                role="tab"
                aria-selected={activeTab === tab.id}
                aria-label={`${tab.label} tab`}
                className={`px-2 py-1 rounded text-[10px] transition-colors ${
                  activeTab === tab.id
                    ? "bg-accent/15 text-accent font-medium"
                    : "text-text-muted hover:text-text-secondary"
                }`}
              >
                {tab.label}
                {tab.id === "stats" && stats && stats.total_resolved > 0 && (
                  <span className="ml-1 text-[10px] bg-green-500/20 text-green-400 px-1 rounded-full">
                    {stats.total_resolved}
                  </span>
                )}
                {tab.id === "diagnostics" && allDiagnostics.length > 0 && (
                  <span className="ml-1 text-[10px] bg-error/20 text-error px-1 rounded-full">
                    {allDiagnostics.length}
                  </span>
                )}
                {tab.id === "workers" && crossWorkerAlerts.length > 0 && (
                  <span className="ml-1 text-[10px] bg-amber-500/20 text-amber-400 px-1 rounded-full">
                    {crossWorkerAlerts.length}
                  </span>
                )}
              </button>
            ))}
        </div>
      </div>

      {/* ── Tab content ────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {/* ── Tab: Stats ─────────────────────────────────── */}
        {activeTab === "stats" && (
          <div className="p-3 space-y-3">
            {/* Summary cards */}
            <div className="grid grid-cols-3 gap-2">
              <div className="border border-border-subtle rounded p-2 bg-surface-raised text-center">
                <div className="text-lg font-bold" style={{ color: "#ef4444" }}>
                  {stats?.total_found ?? 0}
                </div>
                <div className="text-[10px] text-text-muted">Issues Found</div>
              </div>
              <div className="border border-border-subtle rounded p-2 bg-surface-raised text-center">
                <div className="text-lg font-bold" style={{ color: "#22c55e" }}>
                  {stats?.total_resolved ?? 0}
                </div>
                <div className="text-[10px] text-text-muted">Issues Fixed</div>
              </div>
              <div className="border border-border-subtle rounded p-2 bg-surface-raised text-center">
                <div className="text-lg font-bold" style={{ color: stats?.active_errors ? "#f59e0b" : "#22c55e" }}>
                  {stats?.active_count ?? 0}
                </div>
                <div className="text-[10px] text-text-muted">Active Now</div>
              </div>
            </div>

            {/* Fix rate */}
            {stats && stats.total_found > 0 && (
              <div className="border border-border-subtle rounded p-2 bg-surface-raised">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[11px] text-text-secondary font-medium">Fix Rate</span>
                  <span className="text-[11px] font-bold" style={{ color: "#22c55e" }}>
                    {Math.round((stats.total_resolved / stats.total_found) * 100)}%
                  </span>
                </div>
                <div className="h-2 rounded-full bg-border-subtle overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{
                      width: `${Math.round((stats.total_resolved / stats.total_found) * 100)}%`,
                      backgroundColor: "#22c55e",
                    }}
                  />
                </div>
                <div className="flex justify-between mt-1 text-[10px] text-text-muted">
                  <span>{stats.active_errors} errors / {stats.active_warnings} warnings remaining</span>
                  <span>{stats.total_resolved} / {stats.total_found} fixed</span>
                </div>
              </div>
            )}

            {/* By severity */}
            {stats && (stats.by_severity[1]?.found > 0 || stats.by_severity[2]?.found > 0) && (
              <div className="border border-border-subtle rounded p-2 bg-surface-raised">
                <div className="text-[10px] text-text-muted uppercase tracking-wider mb-1.5">
                  By Severity
                </div>
                <div className="space-y-1.5">
                  {[1, 2].map((sev) => {
                    const s = stats.by_severity[sev];
                    if (!s || s.found === 0) return null;
                    return (
                      <div key={sev} className="flex items-center gap-2">
                        <span
                          className="px-1.5 py-0.5 rounded text-[10px] font-medium w-14 text-center"
                          style={{
                            color: SEVERITY_COLORS[sev],
                            backgroundColor: SEVERITY_COLORS[sev] + "20",
                          }}
                        >
                          {SEVERITY_LABELS[sev]}
                        </span>
                        <div className="flex-1 h-1.5 rounded-full bg-border-subtle overflow-hidden">
                          <div
                            className="h-full rounded-full"
                            style={{
                              width: `${s.found > 0 ? Math.round((s.resolved / s.found) * 100) : 0}%`,
                              backgroundColor: "#22c55e",
                            }}
                          />
                        </div>
                        <span className="text-[10px] text-text-muted w-16 text-right">
                          {s.resolved}/{s.found} fixed
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Per-worker stats */}
            {stats && Object.keys(stats.by_worker).length > 0 && (
              <div className="border border-border-subtle rounded p-2 bg-surface-raised">
                <div className="text-[10px] text-text-muted uppercase tracking-wider mb-1.5">
                  Per Worker
                </div>
                <div className="space-y-1">
                  {Object.entries(stats.by_worker)
                    .sort(([, a], [, b]) => b.resolved - a.resolved)
                    .map(([wid, w]) => (
                      <div key={wid} className="flex items-center gap-2 text-[11px]">
                        <span className="text-text-secondary font-medium w-8">
                          {wid === "main" ? "Main" : `W${wid}`}
                        </span>
                        <div className="flex-1 h-1.5 rounded-full bg-border-subtle overflow-hidden">
                          <div
                            className="h-full rounded-full"
                            style={{
                              width: `${w.found > 0 ? Math.round((w.resolved / w.found) * 100) : 0}%`,
                              backgroundColor: "#22c55e",
                            }}
                          />
                        </div>
                        <span className="text-[10px] text-text-muted w-20 text-right">
                          {w.resolved} fixed / {w.found}
                        </span>
                      </div>
                    ))}
                </div>
              </div>
            )}

            {/* Recent activity timeline */}
            {stats && stats.recent_events.length > 0 && (
              <div className="border border-border-subtle rounded p-2 bg-surface-raised">
                <div className="text-[10px] text-text-muted uppercase tracking-wider mb-1.5">
                  Recent Activity
                </div>
                <div className="space-y-0.5 max-h-[200px] overflow-y-auto">
                  {[...stats.recent_events].reverse().slice(0, 30).map((evt, i) => {
                    const isResolved = evt.event === "resolved";
                    const ts = new Date(evt.timestamp * 1000);
                    const timeStr = ts.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
                    const fileName = evt.uri.split("/").pop() || evt.uri;
                    return (
                      <div
                        key={`evt-${i}`}
                        className="flex items-center gap-1.5 py-0.5 text-[10px]"
                      >
                        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${isResolved ? "bg-green-500" : "bg-red-500"}`} />
                        <span className="text-text-muted w-16 shrink-0">{timeStr}</span>
                        <span className="text-text-muted w-6 shrink-0">
                          {evt.worker_id === "main" ? "" : `W${evt.worker_id}`}
                        </span>
                        <span className={`shrink-0 ${isResolved ? "text-green-400" : "text-red-400"}`}>
                          {isResolved ? "FIXED" : SEVERITY_LABELS[evt.severity ?? 1]}
                        </span>
                        <span className="text-text-secondary truncate flex-1" title={evt.message || ""}>
                          {fileName}{evt.message ? `: ${evt.message}` : ""}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Empty state */}
            {(!stats || stats.total_found === 0) && (
              <div className="flex items-center justify-center p-6">
                <span className="text-text-muted text-[11px]">
                  No diagnostic activity yet. Stats will appear as workers write and edit files.
                </span>
              </div>
            )}
          </div>
        )}

        {/* ── Tab: Diagnostics ───────────────────────────── */}
        {activeTab === "diagnostics" && (
          <div className="flex flex-col h-full">
            {/* Filter bar */}
            <div className="px-3 py-1.5 border-b border-border-subtle flex items-center gap-2 shrink-0 flex-wrap">
              <select
                value={severityFilter ?? ""}
                onChange={(e) =>
                  setSeverityFilter(e.target.value ? Number(e.target.value) : null)
                }
                className="px-1.5 py-0.5 rounded text-[10px] bg-surface-raised border border-border-subtle text-text-primary"
                aria-label="Filter by severity"
              >
                <option value="">All severities</option>
                <option value="1">Error</option>
                <option value="2">Warning</option>
                <option value="3">Info</option>
                <option value="4">Hint</option>
              </select>
              <input
                type="text"
                value={fileSearch}
                onChange={(e) => setFileSearch(e.target.value)}
                placeholder="Search files..."
                className="flex-1 min-w-[120px] px-1.5 py-0.5 rounded text-[10px] bg-surface-raised border border-border-subtle text-text-primary placeholder:text-text-muted"
                aria-label="Search by file path"
              />
              <div className="flex items-center gap-1">
                <span className="text-[10px] text-text-muted">Group:</span>
                {(["none", "file", "severity"] as GroupBy[]).map((g) => (
                  <button
                    key={g}
                    onClick={() => setGroupBy(g)}
                    className={`px-1.5 py-0.5 rounded text-[10px] transition-colors ${
                      groupBy === g
                        ? "bg-accent/15 text-accent"
                        : "text-text-muted hover:text-text-secondary"
                    }`}
                  >
                    {g}
                  </button>
                ))}
              </div>
            </div>

            {/* Table */}
            <div className="flex-1 overflow-y-auto">
              {filteredDiagnostics.length === 0 ? (
                <div className="flex items-center justify-center p-8">
                  <span className="text-text-muted text-[11px]">
                    No diagnostics found. Code is clean or no LSP servers are running.
                  </span>
                </div>
              ) : groupedDiagnostics ? (
                /* Grouped view */
                <div className="p-2 space-y-2">
                  {Object.entries(groupedDiagnostics).map(([group, diags]) => (
                    <div key={group}>
                      <div className="text-text-muted mb-1 uppercase tracking-wider text-[10px] px-1">
                        {group} ({diags.length})
                      </div>
                      <div className="space-y-0.5">
                        {diags.map((d, i) => (
                          <DiagnosticRow key={`${d._file}-${d.line}-${i}`} diag={d} />
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                /* Flat table view */
                <div>
                  {/* Header row */}
                  <div className="flex items-center gap-2 px-3 py-1 border-b border-border-subtle bg-surface-raised text-[10px] text-text-muted sticky top-0">
                    <button
                      onClick={() => handleSort("severity")}
                      className="w-14 text-left hover:text-text-secondary"
                    >
                      Sev{sortIndicator("severity")}
                    </button>
                    <button
                      onClick={() => handleSort("file")}
                      className="flex-1 min-w-0 text-left hover:text-text-secondary"
                    >
                      File{sortIndicator("file")}
                    </button>
                    <button
                      onClick={() => handleSort("line")}
                      className="w-10 text-right hover:text-text-secondary"
                    >
                      Ln{sortIndicator("line")}
                    </button>
                    <button
                      onClick={() => handleSort("message")}
                      className="flex-[2] min-w-0 text-left hover:text-text-secondary"
                    >
                      Message{sortIndicator("message")}
                    </button>
                    <span className="w-14 text-left">Source</span>
                  </div>
                  {/* Rows */}
                  <div className="divide-y divide-border-subtle/50">
                    {filteredDiagnostics.map((d, i) => (
                      <DiagnosticRow key={`${d._file}-${d.line}-${i}`} diag={d} />
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── Tab: Servers ───────────────────────────────── */}
        {activeTab === "servers" && (
          <div className="p-2 space-y-1.5">
            {Object.keys(serverStatus).length === 0 ? (
              <div className="flex items-center justify-center p-8">
                <span className="text-text-muted text-[11px]">
                  No LSP servers running. Servers start automatically when files are opened.
                </span>
              </div>
            ) : (
              Object.entries(serverStatus).map(([id, server]) => (
                <div
                  key={id}
                  className="border border-border-subtle rounded p-2 bg-surface-raised"
                >
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-1.5">
                      {/* Language icon badge */}
                      <span
                        className="px-1.5 py-0.5 rounded text-[10px] font-bold border"
                        style={{
                          color: STATUS_COLORS[server.status],
                          borderColor: STATUS_COLORS[server.status] + "44",
                          backgroundColor: STATUS_COLORS[server.status] + "15",
                        }}
                      >
                        {LANGUAGE_ICONS[server.language_id] ||
                          server.language_id.slice(0, 3).toUpperCase()}
                      </span>
                      {/* Server name */}
                      <span className="text-text-secondary font-medium text-[11px]">
                        {server.server_name}
                      </span>
                      {/* Status dot */}
                      <span
                        className="w-2 h-2 rounded-full inline-block"
                        style={{ backgroundColor: STATUS_COLORS[server.status] }}
                        title={server.status}
                      />
                      <span className="text-[10px] text-text-muted">{server.status}</span>
                    </div>
                    {/* Action buttons */}
                    <div className="flex items-center gap-1">
                      {server.status === "stopped" || server.status === "crashed" ? (
                        <button
                          onClick={() => handleServerAction(id, "start")}
                          className="px-1.5 py-0.5 rounded text-[10px] bg-green-500/10 text-green-400 hover:bg-green-500/20"
                        >
                          Start
                        </button>
                      ) : (
                        <button
                          onClick={() => handleServerAction(id, "stop")}
                          className="px-1.5 py-0.5 rounded text-[10px] bg-gray-500/10 text-text-muted hover:bg-gray-500/20"
                        >
                          Stop
                        </button>
                      )}
                      <button
                        onClick={() => handleServerAction(id, "restart")}
                        className="px-1.5 py-0.5 rounded text-[10px] bg-amber-500/10 text-amber-400 hover:bg-amber-500/20"
                      >
                        Restart
                      </button>
                    </div>
                  </div>
                  {/* Server details */}
                  <div className="flex items-center gap-3 text-[10px] text-text-muted">
                    <span>Files: {server.open_files}</span>
                    <span>Diags: {server.diagnostic_count}</span>
                    {server.pid && <span>PID: {server.pid}</span>}
                    {server.restart_count > 0 && (
                      <span className="text-amber-400">
                        Restarts: {server.restart_count}
                      </span>
                    )}
                    {server.worker_id != null && (
                      <span>Worker: W{server.worker_id}</span>
                    )}
                  </div>
                  {/* Root URI */}
                  <div className="text-[10px] text-text-muted mt-0.5 truncate">
                    {truncatePath(server.root_uri, 60)}
                  </div>
                </div>
              ))
            )}
          </div>
        )}

        {/* ── Tab: Per-Worker Diagnostics ─────────────────── */}
        {activeTab === "workers" && isTeamMode && (
          <div className="p-2 space-y-1.5">
            {workerCount === 0 ? (
              <div className="flex items-center justify-center p-8">
                <span className="text-text-muted text-[11px]">
                  No workers active. Start a team session to see per-worker diagnostics.
                </span>
              </div>
            ) : (
              <>
                {/* Worker diagnostic cards */}
                <div className="grid grid-cols-1 gap-1.5">
                  {Array.from({ length: workerCount }, (_, i) => i).map((wid) => {
                    const counts = workerDiagCounts[wid] || {
                      errors: 0,
                      warnings: 0,
                      infos: 0,
                      total: 0,
                    };
                    const mergeReady =
                      counts.errors === 0
                        ? counts.warnings === 0
                          ? "green"
                          : "amber"
                        : "red";
                    const mergeColors: Record<string, string> = {
                      green: "bg-green-500/20 text-green-400 border-green-500/30",
                      amber: "bg-amber-500/20 text-amber-400 border-amber-500/30",
                      red: "bg-red-500/20 text-red-400 border-red-500/30",
                    };
                    return (
                      <div
                        key={wid}
                        className="border border-border-subtle rounded p-2 bg-surface-raised"
                      >
                        <div className="flex items-center justify-between mb-1">
                          <div className="flex items-center gap-1.5">
                            <span className="text-text-secondary font-medium">
                              W{wid}
                            </span>
                            {/* Merge readiness badge */}
                            <span
                              className={`px-1.5 py-0.5 rounded border text-[10px] ${mergeColors[mergeReady]}`}
                            >
                              {mergeReady === "green"
                                ? "Merge Ready"
                                : mergeReady === "amber"
                                ? "Warnings Only"
                                : "Has Errors"}
                            </span>
                          </div>
                          <span className="text-[10px] text-text-muted">
                            {counts.total} total
                          </span>
                        </div>
                        {/* Count badges */}
                        <div className="flex items-center gap-2 text-[10px]">
                          <span style={{ color: SEVERITY_COLORS[1] }}>
                            {counts.errors} errors
                          </span>
                          <span style={{ color: SEVERITY_COLORS[2] }}>
                            {counts.warnings} warnings
                          </span>
                          <span style={{ color: SEVERITY_COLORS[3] }}>
                            {counts.infos} info
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>

                {/* Cross-worker alerts */}
                {crossWorkerAlerts.length > 0 && (
                  <div>
                    <div className="text-text-muted mb-1.5 uppercase tracking-wider text-[10px]">
                      Cross-Worker Conflicts
                    </div>
                    <div className="space-y-1">
                      {crossWorkerAlerts.map((alert, i) => (
                        <div
                          key={`alert-${i}`}
                          className="border border-amber-500/30 rounded p-2 bg-amber-500/5"
                        >
                          <div className="flex items-center gap-2 mb-0.5">
                            <span className="text-amber-400 text-[10px] font-medium">
                              W{alert.source_worker_id} &rarr; W{alert.affected_worker_id}
                            </span>
                            <span className="text-text-muted text-[10px]">
                              {alert.timestamp?.slice(11, 19) || ""}
                            </span>
                          </div>
                          <div className="text-[10px] text-text-secondary truncate">
                            {truncatePath(alert.file_path, 50)}
                          </div>
                          <div className="text-[10px] text-text-muted mt-0.5">
                            {alert.diagnostics.length} diagnostic
                            {alert.diagnostics.length !== 1 ? "s" : ""} affected
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* ── Tab: Impact Visualization ──────────────────── */}
        {activeTab === "impact" && (
          <div className="p-3 space-y-3">
            {/* Input form */}
            <div className="flex items-end gap-2">
              <div className="flex-1">
                <label className="text-[10px] text-text-muted block mb-0.5">
                  File path
                </label>
                <input
                  type="text"
                  value={impactFile}
                  onChange={(e) => setImpactFile(e.target.value)}
                  placeholder="src/components/App.tsx"
                  className="w-full px-2 py-1 rounded text-[11px] bg-surface-raised border border-border-subtle text-text-primary placeholder:text-text-muted"
                />
              </div>
              <div className="w-20">
                <label className="text-[10px] text-text-muted block mb-0.5">
                  Line
                </label>
                <input
                  type="text"
                  value={impactLine}
                  onChange={(e) => setImpactLine(e.target.value)}
                  placeholder="42"
                  className="w-full px-2 py-1 rounded text-[11px] bg-surface-raised border border-border-subtle text-text-primary placeholder:text-text-muted"
                />
              </div>
              <button
                onClick={handleImpactAnalyze}
                disabled={impactLoading || !impactFile.trim()}
                className="px-3 py-1 rounded text-[11px] bg-accent/20 text-accent hover:bg-accent/30 disabled:opacity-40 transition-colors"
              >
                {impactLoading ? "..." : "Analyze"}
              </button>
            </div>

            {/* Results */}
            {impactResult && (
              <div className="space-y-2">
                {/* Summary */}
                <div className="border border-border-subtle rounded p-2 bg-surface-raised">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-text-secondary font-medium text-[11px]">
                      Impact Analysis
                    </span>
                    <span
                      className={`px-1.5 py-0.5 rounded border text-[10px] font-medium ${
                        RISK_COLORS[impactResult.risk] || ""
                      }`}
                    >
                      {impactResult.risk.toUpperCase()} RISK
                    </span>
                  </div>
                  <div className="text-[10px] text-text-muted truncate">
                    {impactResult.file}:{impactResult.line}
                  </div>
                  <div className="text-[10px] text-text-secondary mt-0.5">
                    {impactResult.references_count} references found
                  </div>
                </div>

                {/* Callers */}
                {impactResult.callers.length > 0 && (
                  <div>
                    <div className="text-text-muted mb-1 uppercase tracking-wider text-[10px]">
                      Callers ({impactResult.callers.length})
                    </div>
                    <div className="space-y-0.5">
                      {impactResult.callers.map((c, i) => (
                        <div
                          key={`caller-${i}`}
                          className="flex items-center gap-2 px-2 py-1 rounded hover:bg-surface-raised/50 text-[10px]"
                        >
                          <span className="text-accent shrink-0">{c.name}</span>
                          <span className="text-text-muted truncate">{truncatePath(c.file)}</span>
                          <span className="text-text-muted shrink-0">:{c.line}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Callees */}
                {impactResult.callees.length > 0 && (
                  <div>
                    <div className="text-text-muted mb-1 uppercase tracking-wider text-[10px]">
                      Callees ({impactResult.callees.length})
                    </div>
                    <div className="space-y-0.5">
                      {impactResult.callees.map((c, i) => (
                        <div
                          key={`callee-${i}`}
                          className="flex items-center gap-2 px-2 py-1 rounded hover:bg-surface-raised/50 text-[10px]"
                        >
                          <span className="text-accent shrink-0">{c.name}</span>
                          <span className="text-text-muted truncate">{truncatePath(c.file)}</span>
                          <span className="text-text-muted shrink-0">:{c.line}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Empty callers/callees */}
                {impactResult.callers.length === 0 &&
                  impactResult.callees.length === 0 && (
                    <div className="text-[10px] text-text-muted text-center py-2">
                      No callers or callees found at this location.
                    </div>
                  )}
              </div>
            )}

            {/* Empty state */}
            {!impactResult && !impactLoading && (
              <div className="flex items-center justify-center p-6">
                <span className="text-text-muted text-[11px]">
                  Enter a file path and optional line number, then click Analyze to see
                  references, callers, and callees.
                </span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Diagnostic Row Sub-component ─────────────────────────────

function DiagnosticRow({
  diag,
}: {
  diag: LspDiagnostic & { _file: string };
}) {
  const isError = diag.severity === 1;
  return (
    <div className="flex items-center gap-2 px-3 py-1 hover:bg-surface-raised/50 transition-colors text-[10px]">
      {/* Severity badge */}
      <span
        className={`w-14 shrink-0 px-1 py-0.5 rounded text-center font-medium ${
          isError ? "animate-pulse" : ""
        }`}
        style={{
          color: SEVERITY_COLORS[diag.severity] || "#9ca3af",
          backgroundColor: (SEVERITY_COLORS[diag.severity] || "#9ca3af") + "20",
        }}
      >
        {SEVERITY_LABELS[diag.severity] || "?"}
      </span>
      {/* File path */}
      <span className="flex-1 min-w-0 text-text-secondary truncate" title={diag._file}>
        {truncatePath(diag._file)}
      </span>
      {/* Line number */}
      <span className="w-10 text-right text-text-muted shrink-0">{diag.line}</span>
      {/* Message */}
      <span className="flex-[2] min-w-0 text-text-primary truncate" title={diag.message}>
        {diag.message}
      </span>
      {/* Source */}
      <span className="w-14 text-left text-text-muted truncate shrink-0">
        {diag.source || "-"}
      </span>
    </div>
  );
}
