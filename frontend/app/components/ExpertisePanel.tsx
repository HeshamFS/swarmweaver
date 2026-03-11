"use client";

import { useState, useEffect, useCallback } from "react";

// --- Types ---

interface ExpertiseRecord {
  id: string;
  record_type: string;
  classification: string;
  domain: string;
  content: string;
  structured: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  expires_at: string | null;
  source_project: string;
  source_agent: string;
  resolves: string | null;
  resolved_by: string[];
  confidence: number;
  relevance_score: number;
  outcome_count: number;
  success_count: number;
  failure_count: number;
  tags: string[];
  file_patterns: string[];
  is_archived: boolean;
}

export interface SessionLesson {
  id: string;
  session_id: string;
  content: string;
  severity: string;
  domain: string;
  quality_score: number;
  propagated_to: string[];
  created_at: string;
  promoted_to_record_id: string | null;
}

interface DomainInfo {
  name: string;
  count: number;
  parent: string | null;
  soft_limit: number;
  warn_limit: number;
  hard_limit: number;
}

interface AnalyticsData {
  total_records: number;
  by_type: Record<string, number>;
  by_classification: Record<string, number>;
  top_records: { id: string; content: string; confidence: number; domain: string }[];
  domain_health: { domain: string; count: number; status: string }[];
}

interface CausalChain {
  root: string;
  chain: ExpertiseRecord[];
}

interface ExpertisePanelProps {
  projectDir?: string;
  events?: { type: string; timestamp: string; data?: Record<string, unknown> }[];
}

// --- Constants ---

const RECORD_TYPE_ICONS: Record<string, string> = {
  convention: "C",
  pattern: "P",
  failure: "!",
  decision: "D",
  reference: "R",
  guide: "G",
  resolution: "F",
  insight: "I",
  antipattern: "X",
  heuristic: "H",
};

const CLASSIFICATION_COLORS: Record<string, string> = {
  foundational: "text-success",
  tactical: "text-info",
  observational: "text-text-muted",
};

const CATEGORY_COLORS: Record<string, string> = {
  convention: "text-accent bg-accent/10 border-accent/30",
  pattern: "text-accent bg-accent/10 border-accent/30",
  failure: "text-error bg-error/10 border-error/30",
  decision: "text-warning bg-warning/10 border-warning/30",
  reference: "text-text-secondary bg-surface border-border-subtle",
  guide: "text-info bg-info/10 border-info/30",
  resolution: "text-success bg-success/10 border-success/30",
  insight: "text-accent bg-accent/10 border-accent/30",
  antipattern: "text-error bg-error/10 border-error/30",
  heuristic: "text-warning bg-warning/10 border-warning/30",
};

export const SEVERITY_COLORS: Record<string, string> = {
  critical: "text-error",
  high: "text-warning",
  medium: "text-accent",
  low: "text-text-muted",
};

const DOMAIN_COLORS: Record<string, string> = {
  python: "text-[#3572A5]",
  typescript: "text-[#3178c6]",
  javascript: "text-[#f1e05a]",
  rust: "text-[#dea584]",
  golang: "text-[#00ADD8]",
  database: "text-[#e38c00]",
  testing: "text-success",
  devops: "text-warning",
  architecture: "text-accent",
  styling: "text-[#ff69b4]",
};

function getDomainColor(domain: string): string {
  const root = domain.split(".")[0];
  return DOMAIN_COLORS[root] || "text-text-secondary";
}

type TabId = "browser" | "causal" | "lessons" | "analytics" | "priming";

// --- API Helpers ---

const API_BASE = typeof window !== "undefined"
  ? `${window.location.protocol}//${window.location.hostname}:8000`
  : "http://localhost:8000";

async function fetchJSON<T>(url: string): Promise<T> {
  const res = await fetch(`${API_BASE}${url}`);
  return res.json() as Promise<T>;
}

// --- Component ---

export function ExpertisePanel({ projectDir, events = [] }: ExpertisePanelProps) {
  const [activeTab, setActiveTab] = useState<TabId>("browser");
  const [records, setRecords] = useState<ExpertiseRecord[]>([]);
  const [domains, setDomains] = useState<DomainInfo[]>([]);
  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null);
  const [selectedDomain, setSelectedDomain] = useState<string>("");
  const [selectedType, setSelectedType] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [selectedRecord, setSelectedRecord] = useState<ExpertiseRecord | null>(null);
  const [causalChain, setCausalChain] = useState<CausalChain | null>(null);
  const [primingFiles, setPrimingFiles] = useState<string>("");
  const [primingBudget, setPrimingBudget] = useState<number>(2000);
  const [primingOutput, setPrimingOutput] = useState<string>("");
  const [loading, setLoading] = useState(false);

  const pdParam = projectDir ? `&project_dir=${encodeURIComponent(projectDir)}` : "";

  // Fetch records
  const fetchRecords = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (selectedDomain) params.set("domain", selectedDomain);
      if (selectedType) params.set("type", selectedType);
      if (searchQuery) params.set("q", searchQuery);
      if (projectDir) params.set("project_dir", projectDir);
      const data = await fetchJSON<{ records: ExpertiseRecord[] }>(`/api/expertise?${params}`);
      setRecords(data.records || []);
    } catch {
      setRecords([]);
    }
    setLoading(false);
  }, [selectedDomain, selectedType, searchQuery, projectDir]);

  // Fetch domains
  const fetchDomains = useCallback(async () => {
    try {
      const data = await fetchJSON<{ domains: DomainInfo[] }>(`/api/expertise/domains?${pdParam.slice(1)}`);
      setDomains(data.domains || []);
    } catch {
      setDomains([]);
    }
  }, [pdParam]);

  // Fetch analytics
  const fetchAnalytics = useCallback(async () => {
    try {
      const data = await fetchJSON<AnalyticsData>(`/api/expertise/analytics?${pdParam.slice(1)}`);
      setAnalytics(data);
    } catch {
      setAnalytics(null);
    }
  }, [pdParam]);

  useEffect(() => {
    fetchRecords();
    fetchDomains();
  }, [fetchRecords, fetchDomains]);

  useEffect(() => {
    if (activeTab === "analytics") fetchAnalytics();
  }, [activeTab, fetchAnalytics]);

  // Track expertise events from WS
  useEffect(() => {
    const expertiseEvents = events.filter(
      (e) => e.type.startsWith("expertise_")
    );
    if (expertiseEvents.length > 0) {
      fetchRecords();
    }
  }, [events, fetchRecords]);

  // Fetch causal chain
  const loadCausalChain = async (recordId: string) => {
    try {
      const data = await fetchJSON<CausalChain>(`/api/expertise/causal-chain/${recordId}?${pdParam.slice(1)}`);
      setCausalChain(data);
    } catch {
      setCausalChain(null);
    }
  };

  // Fetch priming preview
  const loadPriming = async () => {
    try {
      const params = new URLSearchParams();
      if (primingFiles) params.set("files", primingFiles);
      params.set("budget", String(primingBudget));
      if (projectDir) params.set("project_dir", projectDir);
      const data = await fetchJSON<{ context: string }>(`/api/expertise/prime?${params}`);
      setPrimingOutput(data.context || "(no records match)");
    } catch (e) {
      setPrimingOutput(`Error: ${e}`);
    }
  };

  // --- Confidence bar ---
  const ConfidenceBar = ({ value }: { value: number }) => (
    <div className="w-14 h-1 bg-surface-raised rounded-full overflow-hidden inline-block align-middle ml-1">
      <div
        className={`h-full rounded-full ${value >= 0.7 ? "bg-success" : value >= 0.4 ? "bg-warning" : "bg-error"}`}
        style={{ width: `${value * 100}%` }}
      />
    </div>
  );

  const formatTime = (ts: string) => {
    try {
      return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    } catch {
      return "";
    }
  };

  // --- Tab: Browser ---
  const renderBrowser = () => (
    <div className="flex h-full min-h-0">
      {/* Domain sidebar */}
      <div className="w-36 border-r border-border-subtle pr-2 overflow-y-auto shrink-0">
        <div className="text-[10px] text-text-muted font-mono uppercase tracking-wider mb-1 px-1">Domains</div>
        <button
          className={`block w-full text-left text-xs font-mono px-1.5 py-0.5 rounded transition-colors ${
            !selectedDomain ? "bg-accent/20 text-accent" : "text-text-muted hover:text-text-secondary hover:bg-surface-raised"
          }`}
          onClick={() => setSelectedDomain("")}
        >
          All ({records.length})
        </button>
        {domains.map((d) => (
          <button
            key={d.name}
            className={`block w-full text-left text-xs font-mono px-1.5 py-0.5 rounded truncate transition-colors ${
              selectedDomain === d.name ? "bg-accent/20 text-accent" : `${getDomainColor(d.name)} hover:bg-surface-raised`
            }`}
            onClick={() => setSelectedDomain(d.name)}
          >
            {d.name} ({d.count})
          </button>
        ))}
      </div>

      {/* Record list */}
      <div className="flex-1 overflow-y-auto min-w-0 px-2">
        {/* Search + filter */}
        <div className="flex gap-1 mb-2">
          <input
            className="flex-1 bg-surface-raised border border-border-subtle rounded-md px-2 py-1 text-xs font-mono text-text-primary placeholder:text-text-muted"
            placeholder="Search records..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && fetchRecords()}
          />
          <select
            className="bg-surface-raised border border-border-subtle rounded-md px-1.5 py-1 text-xs font-mono text-text-primary"
            value={selectedType}
            onChange={(e) => setSelectedType(e.target.value)}
          >
            <option value="">All types</option>
            {Object.keys(RECORD_TYPE_ICONS).map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </div>

        {loading && <div className="text-xs font-mono text-text-muted py-2">Loading...</div>}

        <div className="divide-y divide-border-subtle">
          {records.map((r) => (
            <div
              key={r.id}
              className={`py-1.5 px-1 cursor-pointer transition-colors ${
                selectedRecord?.id === r.id ? "bg-accent/10" : "hover:bg-surface-raised/50"
              }`}
              onClick={() => {
                setSelectedRecord(r);
                if (r.record_type === "failure" || r.record_type === "resolution") {
                  loadCausalChain(r.id);
                }
              }}
            >
              <div className="flex items-center gap-1.5">
                <span className="text-[10px] font-mono text-text-muted w-4 text-center shrink-0">
                  {RECORD_TYPE_ICONS[r.record_type] || "?"}
                </span>
                <span className={`text-[10px] font-mono px-1 py-0.5 rounded border ${CATEGORY_COLORS[r.record_type] || "text-text-muted border-border-subtle"}`}>
                  {r.record_type}
                </span>
                <span className="text-xs font-mono text-text-primary flex-1 truncate">{r.content}</span>
                <ConfidenceBar value={r.confidence} />
              </div>
              <div className="text-[10px] font-mono text-text-muted ml-5 mt-0.5 flex items-center gap-2">
                {r.domain && <span className={getDomainColor(r.domain)}>{r.domain}</span>}
                {r.resolved_by.length > 0 && <span className="text-success">(resolved)</span>}
                {r.resolves && <span className="text-info">(fixes)</span>}
                {r.tags.length > 0 && <span>{r.tags.slice(0, 3).join(", ")}</span>}
              </div>
            </div>
          ))}
        </div>

        {records.length === 0 && !loading && (
          <div className="text-xs font-mono text-text-muted py-8 text-center">No records found</div>
        )}
      </div>

      {/* Detail sidebar */}
      {selectedRecord && (
        <div className="w-48 border-l border-border-subtle pl-2 overflow-y-auto shrink-0">
          <div className="flex items-center justify-between mb-1">
            <span className={`text-[10px] font-mono font-medium px-1.5 py-0.5 rounded border ${CATEGORY_COLORS[selectedRecord.record_type] || ""}`}>
              {selectedRecord.record_type}
            </span>
            <button
              onClick={() => setSelectedRecord(null)}
              className="text-text-muted hover:text-text-primary text-xs"
            >
              {"\u2717"}
            </button>
          </div>
          <p className="text-xs font-mono text-text-primary mb-2 leading-relaxed">{selectedRecord.content}</p>
          <div className="text-[10px] font-mono text-text-muted space-y-1">
            <div className="flex justify-between">
              <span>Domain</span>
              <span className={`${getDomainColor(selectedRecord.domain)} text-right`}>{selectedRecord.domain || "none"}</span>
            </div>
            <div className="flex justify-between">
              <span>Classification</span>
              <span className={CLASSIFICATION_COLORS[selectedRecord.classification] || ""}>{selectedRecord.classification}</span>
            </div>
            <div className="flex justify-between">
              <span>Confidence</span>
              <span className="text-text-primary">{(selectedRecord.confidence * 100).toFixed(0)}%</span>
            </div>
            <div className="flex justify-between">
              <span>Outcomes</span>
              <span>
                {selectedRecord.outcome_count} (<span className="text-success">{selectedRecord.success_count}S</span> / <span className="text-error">{selectedRecord.failure_count}F</span>)
              </span>
            </div>
            <div className="flex justify-between">
              <span>Created</span>
              <span>{new Date(selectedRecord.created_at).toLocaleDateString()}</span>
            </div>
            {selectedRecord.file_patterns.length > 0 && (
              <div className="pt-1 border-t border-border-subtle">
                <span className="block mb-0.5">Files:</span>
                {selectedRecord.file_patterns.map((fp, i) => (
                  <div key={i} className="text-text-secondary truncate">{fp}</div>
                ))}
              </div>
            )}
            {selectedRecord.resolves && (
              <div className="text-info">Resolves: {selectedRecord.resolves}</div>
            )}
            {selectedRecord.resolved_by.length > 0 && (
              <div className="text-success">Resolved by: {selectedRecord.resolved_by.join(", ")}</div>
            )}
            {selectedRecord.tags.length > 0 && (
              <div className="pt-1 border-t border-border-subtle flex flex-wrap gap-1">
                {selectedRecord.tags.map((t) => (
                  <span key={t} className="px-1 py-0.5 bg-surface-raised rounded text-text-muted">{t}</span>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );

  // --- Tab: Causal Chains ---
  const renderCausalChains = () => {
    const failures = records.filter((r) => r.record_type === "failure");
    return (
      <div className="space-y-2 overflow-y-auto p-2">
        <div className="text-[10px] font-mono text-text-muted uppercase tracking-wider mb-1">
          {failures.length} failure record(s) — click to see resolution chain
        </div>
        {failures.map((f) => (
          <div key={f.id} className="border border-border-subtle rounded-lg p-2 bg-surface hover:bg-surface-raised/50 transition-colors">
            <div
              className="flex items-center gap-1.5 cursor-pointer"
              onClick={() => loadCausalChain(f.id)}
            >
              <span className="text-error text-xs font-mono">!</span>
              <span className="text-xs font-mono text-text-primary flex-1 truncate">{f.content}</span>
              {f.resolved_by.length > 0 ? (
                <span className="text-success text-[10px] font-mono">{f.resolved_by.length} fix(es)</span>
              ) : (
                <span className="text-error text-[10px] font-mono">unresolved</span>
              )}
            </div>
            {causalChain?.root === f.id && causalChain.chain.length > 1 && (
              <div className="mt-1.5 ml-4 border-l-2 border-success/30 pl-2 space-y-1">
                {causalChain.chain.slice(1).map((r) => (
                  <div key={r.id} className="text-xs font-mono text-success flex items-center gap-1">
                    <span className="text-[10px]">F</span>
                    <span className="truncate">{r.content}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
        {failures.length === 0 && (
          <div className="text-xs font-mono text-text-muted text-center py-8">No failure records</div>
        )}
      </div>
    );
  };

  // --- Tab: Session Lessons ---
  const renderLessons = () => {
    const lessonEvents = events.filter(
      (e) => e.type === "expertise_lesson_propagated" || e.type === "expertise_lesson_created" || e.type === "expertise_record_promoted"
    );

    return (
      <div className="space-y-2 overflow-y-auto p-2">
        <div className="text-[10px] font-mono text-text-muted uppercase tracking-wider mb-1">
          Real-time session lessons (live during swarm mode)
        </div>

        {lessonEvents.length > 0 ? (
          lessonEvents.map((ev, i) => {
            const label = ev.type === "expertise_lesson_propagated" ? "PROP" : ev.type === "expertise_record_promoted" ? "PERM" : "NEW";
            const labelColor = ev.type === "expertise_record_promoted" ? "text-success bg-success/10 border-success/30" : "text-warning bg-warning/10 border-warning/30";
            return (
              <div key={i} className="border border-border-subtle rounded-lg p-2 bg-surface">
                <div className="flex items-center gap-1.5">
                  <span className={`text-[10px] font-mono px-1 py-0.5 rounded border ${labelColor}`}>
                    {label}
                  </span>
                  <span className="text-xs font-mono text-text-primary flex-1 truncate">
                    {(ev.data?.content as string) || (ev.data?.lesson_id as string) || ""}
                  </span>
                </div>
                <div className="text-[10px] font-mono text-text-muted mt-0.5 ml-1">
                  {formatTime(ev.timestamp)}
                  {ev.data?.worker_id != null && ` | worker-${String(ev.data.worker_id)}`}
                </div>
              </div>
            );
          })
        ) : (
          <div className="text-xs font-mono text-text-muted text-center py-8">
            No session lessons yet. Lessons appear during swarm mode when workers encounter similar errors.
          </div>
        )}
      </div>
    );
  };

  // --- Tab: Analytics ---
  const renderAnalytics = () => {
    if (!analytics) return <div className="text-xs font-mono text-text-muted p-2">Loading analytics...</div>;

    const byType = analytics.by_type || {};
    const byClassification = analytics.by_classification || {};
    const domainHealth = analytics.domain_health || [];
    const topRecords = analytics.top_records || [];

    return (
      <div className="space-y-3 overflow-y-auto p-2">
        {/* Summary stats */}
        <div className="flex gap-2">
          <div className="flex-1 bg-surface-raised rounded-lg border border-border-subtle p-2">
            <div className="text-sm font-mono font-bold text-text-primary">{analytics.total_records ?? 0}</div>
            <div className="text-[10px] font-mono text-text-muted">Total Records</div>
          </div>
          <div className="flex-1 bg-surface-raised rounded-lg border border-border-subtle p-2">
            <div className="text-sm font-mono font-bold text-text-primary">{Object.keys(byType).length}</div>
            <div className="text-[10px] font-mono text-text-muted">Record Types</div>
          </div>
          <div className="flex-1 bg-surface-raised rounded-lg border border-border-subtle p-2">
            <div className="text-sm font-mono font-bold text-text-primary">{domainHealth.length}</div>
            <div className="text-[10px] font-mono text-text-muted">Domains</div>
          </div>
        </div>

        {/* By type */}
        {Object.keys(byType).length > 0 && (
          <div>
            <div className="text-[10px] font-mono text-text-muted uppercase tracking-wider mb-1">By Type</div>
            <div className="bg-surface-raised rounded-lg border border-border-subtle divide-y divide-border-subtle">
              {Object.entries(byType).map(([type, count]) => (
                <div key={type} className="flex justify-between items-center px-2 py-1">
                  <span className={`text-xs font-mono px-1 py-0.5 rounded border ${CATEGORY_COLORS[type] || "text-text-muted border-border-subtle"}`}>
                    {type}
                  </span>
                  <span className="text-xs font-mono text-text-secondary">{count}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* By classification */}
        {Object.keys(byClassification).length > 0 && (
          <div>
            <div className="text-[10px] font-mono text-text-muted uppercase tracking-wider mb-1">By Classification</div>
            <div className="bg-surface-raised rounded-lg border border-border-subtle divide-y divide-border-subtle">
              {Object.entries(byClassification).map(([cls, count]) => (
                <div key={cls} className="flex justify-between items-center px-2 py-1">
                  <span className={`text-xs font-mono ${CLASSIFICATION_COLORS[cls] || "text-text-muted"}`}>{cls}</span>
                  <span className="text-xs font-mono text-text-secondary">{count}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Domain Health */}
        {domainHealth.length > 0 && (
          <div>
            <div className="text-[10px] font-mono text-text-muted uppercase tracking-wider mb-1">Domain Health</div>
            <div className="bg-surface-raised rounded-lg border border-border-subtle divide-y divide-border-subtle">
              {domainHealth.map((d) => (
                <div key={d.domain} className="flex justify-between items-center px-2 py-1">
                  <span className={`text-xs font-mono ${getDomainColor(d.domain)}`}>{d.domain}</span>
                  <span className={`text-xs font-mono ${d.status === "critical" ? "text-error" : d.status === "warning" ? "text-warning" : "text-text-muted"}`}>
                    {d.count} ({d.status})
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Top records */}
        {topRecords.length > 0 && (
          <div>
            <div className="text-[10px] font-mono text-text-muted uppercase tracking-wider mb-1">Top Records by Confidence</div>
            <div className="bg-surface-raised rounded-lg border border-border-subtle divide-y divide-border-subtle">
              {topRecords.map((r) => (
                <div key={r.id} className="flex items-center gap-2 px-2 py-1">
                  <span className="text-[10px] font-mono text-accent shrink-0">{(r.confidence * 100).toFixed(0)}%</span>
                  <span className="text-xs font-mono text-text-primary flex-1 truncate">{r.content}</span>
                  {r.domain && <span className={`text-[10px] font-mono shrink-0 ${getDomainColor(r.domain)}`}>{r.domain}</span>}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  };

  // --- Tab: Priming Preview ---
  const renderPriming = () => (
    <div className="space-y-2 p-2">
      <div className="flex gap-2">
        <input
          className="flex-1 bg-surface-raised border border-border-subtle rounded-md px-2 py-1 text-xs font-mono text-text-primary placeholder:text-text-muted"
          placeholder="File paths (comma-separated)"
          value={primingFiles}
          onChange={(e) => setPrimingFiles(e.target.value)}
        />
        <div className="flex items-center gap-1 shrink-0">
          <span className="text-[10px] font-mono text-text-muted">Budget:</span>
          <input
            type="range"
            min={500}
            max={5000}
            step={100}
            value={primingBudget}
            onChange={(e) => setPrimingBudget(Number(e.target.value))}
            className="w-16"
          />
          <span className="text-[10px] font-mono text-text-secondary w-10">{primingBudget}t</span>
        </div>
        <button
          className="bg-accent hover:bg-accent-hover text-white text-xs font-mono px-3 py-1 rounded-md transition-colors"
          onClick={loadPriming}
        >
          Preview
        </button>
      </div>
      <pre className="bg-surface border border-border-subtle rounded-lg p-3 text-xs font-mono text-text-secondary overflow-auto whitespace-pre-wrap max-h-80">
        {primingOutput || "Enter file paths and click Preview to see formatted priming output."}
      </pre>
    </div>
  );

  // --- Main render ---
  return (
    <div className="flex flex-col h-full rounded-lg border border-border-subtle bg-surface overflow-hidden">
      {/* Tab bar — matches ObservabilityPanel style */}
      <div className="flex border-b border-border-subtle bg-surface-raised px-1 py-1">
        <div className="flex gap-0.5 flex-wrap">
          {([
            { id: "browser" as TabId, label: "Browser" },
            { id: "causal" as TabId, label: "Causal" },
            { id: "lessons" as TabId, label: "Lessons" },
            { id: "analytics" as TabId, label: "Analytics" },
            { id: "priming" as TabId, label: "Priming" },
          ]).map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-mono transition-colors ${
                activeTab === tab.id
                  ? "bg-accent/15 text-accent font-medium"
                  : "text-text-muted hover:text-text-secondary"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-hidden min-h-0">
        {activeTab === "browser" && renderBrowser()}
        {activeTab === "causal" && renderCausalChains()}
        {activeTab === "lessons" && renderLessons()}
        {activeTab === "analytics" && renderAnalytics()}
        {activeTab === "priming" && renderPriming()}
      </div>
    </div>
  );
}
