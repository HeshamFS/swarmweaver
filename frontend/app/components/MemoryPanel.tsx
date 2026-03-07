"use client";

import { useState, useEffect, useMemo, useCallback } from "react";

interface ExpertiseEntry {
  id: string;
  content: string;
  category: string;
  domain: string;
  tags: string[];
  source_file: string;
  created_at: string;
  relevance_score: number;
}

interface MemoryEntry {
  id: string;
  category: string;
  content: string;
  tags: string[];
  project_source: string;
  created_at: string;
  domain: string;
  expertise_type: string;
  outcome: string;
  outcome_count: number;
  success_count: number;
  relevance_score?: number;
}

type OutcomeFilter = "all" | "proven" | "failures" | "untracked";
type SortMode = "relevance" | "success_rate" | "most_used";

const CATEGORY_COLORS: Record<string, string> = {
  pattern: "text-accent bg-accent/10 border-accent/30",
  mistake: "text-error bg-error/10 border-error/30",
  solution: "text-success bg-success/10 border-success/30",
  preference: "text-warning bg-warning/10 border-warning/30",
  convention: "text-info bg-info/10 border-info/30",
  failure: "text-error bg-error/10 border-error/30",
  decision: "text-accent bg-accent/10 border-accent/30",
  reference: "text-text-secondary bg-surface border-border-subtle",
};

const DOMAIN_COLORS: Record<string, string> = {
  python: "text-[#3572A5]",
  typescript: "text-[#3178c6]",
  javascript: "text-[#f1e05a]",
  rust: "text-[#dea584]",
  golang: "text-[#00ADD8]",
  database: "text-[#e38c00]",
  testing: "text-success",
  frontend: "text-info",
  devops: "text-warning",
  security: "text-error",
  architecture: "text-accent",
  performance: "text-[#bc8cff]",
  styling: "text-[#ff69b4]",
};

function getSuccessRate(mem: MemoryEntry): number {
  if (!mem.outcome_count) return -1;
  return mem.success_count / mem.outcome_count;
}

function getSuccessRateColor(rate: number): string {
  if (rate > 0.7) return "text-success";
  if (rate >= 0.4) return "text-warning";
  return "text-error";
}

function getSuccessRateBgColor(rate: number): string {
  if (rate > 0.7) return "bg-success";
  if (rate >= 0.4) return "bg-warning";
  return "bg-error";
}

export function MemoryPanel({ projectDir }: { projectDir?: string }) {
  const [topTab, setTopTab] = useState<"global" | "project">("global");
  const [memories, setMemories] = useState<MemoryEntry[]>([]);
  const [search, setSearch] = useState("");
  const [showAdd, setShowAdd] = useState(false);
  const [newCategory, setNewCategory] = useState("pattern");
  const [newContent, setNewContent] = useState("");
  const [newTags, setNewTags] = useState("");
  const [newDomain, setNewDomain] = useState("");
  const [loading, setLoading] = useState(true);
  const [filterDomain, setFilterDomain] = useState<string>("");
  const [viewMode, setViewMode] = useState<"flat" | "domains" | "priming">("flat");
  const [primingFiles, setPrimingFiles] = useState("");
  const [primingResult, setPrimingResult] = useState<string | null>(null);
  const [primingLoading, setPrimingLoading] = useState(false);
  const [outcomeFilter, setOutcomeFilter] = useState<OutcomeFilter>("all");
  const [sortMode, setSortMode] = useState<SortMode>("relevance");

  // Project expertise state
  const [expertise, setExpertise] = useState<ExpertiseEntry[]>([]);
  const [expertiseDomains, setExpertiseDomains] = useState<string[]>([]);
  const [expertiseLoading, setExpertiseLoading] = useState(false);
  const [expertiseFilterDomain, setExpertiseFilterDomain] = useState("");
  const [showExpertiseAdd, setShowExpertiseAdd] = useState(false);
  const [peContent, setPeContent] = useState("");
  const [peCategory, setPeCategory] = useState("pattern");
  const [peDomain, setPeDomain] = useState("");
  const [peTags, setPeTags] = useState("");

  useEffect(() => {
    fetchMemories();
  }, []);

  const fetchExpertise = useCallback(async () => {
    if (!projectDir) return;
    setExpertiseLoading(true);
    try {
      const params = new URLSearchParams({ path: projectDir });
      if (expertiseFilterDomain) params.set("domain", expertiseFilterDomain);
      const res = await fetch(`/api/projects/expertise?${params}`);
      const data = await res.json();
      setExpertise(data.entries || []);
      setExpertiseDomains(data.domains || []);
    } catch {
      // Ignore
    } finally {
      setExpertiseLoading(false);
    }
  }, [projectDir, expertiseFilterDomain]);

  useEffect(() => {
    if (topTab === "project") {
      fetchExpertise();
    }
  }, [topTab, fetchExpertise]);

  const fetchMemories = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/memory");
      const data = await res.json();
      setMemories(data.memories || []);
    } catch {
      // Ignore
    } finally {
      setLoading(false);
    }
  };

  const searchMemories = async (query: string) => {
    if (!query.trim()) {
      fetchMemories();
      return;
    }
    try {
      const res = await fetch(`/api/memory/search?q=${encodeURIComponent(query)}`);
      const data = await res.json();
      setMemories(data.results || []);
    } catch {
      // Ignore
    }
  };

  const addMemory = async () => {
    if (!newContent.trim()) return;
    const params = new URLSearchParams();
    params.set("category", newCategory);
    params.set("content", newContent);
    if (newTags.trim()) {
      params.set("tags", newTags.trim());
    }
    if (newDomain.trim()) {
      params.set("domain", newDomain.trim());
    }
    try {
      await fetch(`/api/memory?${params.toString()}`, { method: "POST" });
      setNewContent("");
      setNewTags("");
      setNewDomain("");
      setShowAdd(false);
      fetchMemories();
    } catch {
      // Ignore
    }
  };

  const deleteMemory = async (id: string) => {
    try {
      await fetch(`/api/memory/${id}`, { method: "DELETE" });
      setMemories((prev) => prev.filter((m) => m.id !== id));
    } catch {
      // Ignore
    }
  };

  const recordOutcome = async (id: string, outcome: "success" | "partial" | "failure") => {
    try {
      const res = await fetch(`/api/memory/${id}/outcome?outcome=${outcome}`, { method: "POST" });
      const data = await res.json();
      if (data.status === "ok" && data.entry) {
        setMemories((prev) =>
          prev.map((m) => (m.id === id ? { ...m, ...data.entry } : m))
        );
      }
    } catch {
      // Ignore
    }
  };

  const addExpertise = async () => {
    if (!peContent.trim() || !projectDir) return;
    const params = new URLSearchParams({ path: projectDir, content: peContent, category: peCategory });
    if (peDomain.trim()) params.set("domain", peDomain);
    if (peTags.trim()) params.set("tags", peTags);
    try {
      await fetch(`/api/projects/expertise?${params}`, { method: "POST" });
      setPeContent("");
      setPeTags("");
      setShowExpertiseAdd(false);
      fetchExpertise();
    } catch {
      // Ignore
    }
  };

  const deleteExpertise = async (id: string) => {
    if (!projectDir) return;
    try {
      await fetch(`/api/projects/expertise/${id}?path=${encodeURIComponent(projectDir)}`, { method: "DELETE" });
      setExpertise((prev) => prev.filter((e) => e.id !== id));
    } catch {
      // Ignore
    }
  };

  // Get unique domains
  const domains = Array.from(new Set(memories.map((m) => m.domain).filter(Boolean))).sort();

  // Filter and sort memories
  const filteredMemories = useMemo(() => {
    let result = filterDomain
      ? memories.filter((m) => m.domain === filterDomain)
      : [...memories];

    // Apply outcome filter
    if (outcomeFilter === "proven") {
      result = result.filter((m) => m.outcome_count > 0 && getSuccessRate(m) > 0.7);
    } else if (outcomeFilter === "failures") {
      result = result.filter((m) => m.outcome_count > 0 && getSuccessRate(m) < 0.4);
    } else if (outcomeFilter === "untracked") {
      result = result.filter((m) => !m.outcome_count);
    }

    // Apply sort
    if (sortMode === "success_rate") {
      result.sort((a, b) => {
        const rateA = getSuccessRate(a);
        const rateB = getSuccessRate(b);
        if (rateA === -1 && rateB === -1) return 0;
        if (rateA === -1) return 1;
        if (rateB === -1) return -1;
        return rateB - rateA;
      });
    } else if (sortMode === "most_used") {
      result.sort((a, b) => (b.outcome_count || 0) - (a.outcome_count || 0));
    } else {
      result.sort((a, b) => (b.relevance_score ?? 1) - (a.relevance_score ?? 1));
    }

    return result;
  }, [memories, filterDomain, outcomeFilter, sortMode]);

  // Group by domain for domain view
  const memoryByDomain: Record<string, MemoryEntry[]> = {};
  for (const m of memories) {
    const d = m.domain || "general";
    if (!memoryByDomain[d]) memoryByDomain[d] = [];
    memoryByDomain[d].push(m);
  }

  // Group expertise by domain
  const expertiseByDomain: Record<string, ExpertiseEntry[]> = {};
  for (const e of expertise) {
    const d = e.domain || "general";
    if (!expertiseByDomain[d]) expertiseByDomain[d] = [];
    expertiseByDomain[d].push(e);
  }

  return (
    <div className="flex flex-col h-full rounded-lg border border-border-subtle bg-surface overflow-hidden">
      {/* Top-level tab toggle: Global Memory | Project Expertise */}
      <div className="flex border-b border-border-subtle bg-surface-raised">
        <button
          onClick={() => setTopTab("global")}
          className={`flex-1 px-3 py-1.5 text-[11px] font-mono transition-colors ${
            topTab === "global"
              ? "text-accent border-b-2 border-accent bg-accent/5"
              : "text-text-muted hover:text-text-secondary"
          }`}
        >
          Global Memory
        </button>
        <button
          onClick={() => setTopTab("project")}
          className={`flex-1 px-3 py-1.5 text-[11px] font-mono transition-colors ${
            topTab === "project"
              ? "text-accent border-b-2 border-accent bg-accent/5"
              : "text-text-muted hover:text-text-secondary"
          }`}
        >
          Project Expertise
          {expertise.length > 0 && (
            <span className="ml-1 text-[9px] text-text-muted">({expertise.length})</span>
          )}
        </button>
      </div>

      {/* === PROJECT EXPERTISE TAB === */}
      {topTab === "project" && (
        <>
          {/* Expertise header */}
          <div className="px-3 py-2 border-b border-border-subtle bg-surface-raised">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-text-muted font-mono">
                Project Knowledge Base
              </span>
              <button
                onClick={() => setShowExpertiseAdd(!showExpertiseAdd)}
                className="text-xs text-accent hover:text-accent-hover transition-colors"
              >
                {showExpertiseAdd ? "Cancel" : "+ Record Expertise"}
              </button>
            </div>
            {expertiseDomains.length > 0 && (
              <div className="flex flex-wrap gap-1">
                <button
                  onClick={() => setExpertiseFilterDomain("")}
                  className={`text-[10px] px-1.5 py-0.5 rounded font-mono transition-colors ${
                    !expertiseFilterDomain ? "bg-accent/20 text-accent" : "text-text-muted hover:text-text-secondary bg-surface"
                  }`}
                >
                  All
                </button>
                {expertiseDomains.map((d) => (
                  <button
                    key={d}
                    onClick={() => setExpertiseFilterDomain(d === expertiseFilterDomain ? "" : d)}
                    className={`text-[10px] px-1.5 py-0.5 rounded font-mono transition-colors ${
                      d === expertiseFilterDomain
                        ? "bg-accent/20 text-accent"
                        : `${DOMAIN_COLORS[d] || "text-text-muted"} hover:bg-surface-raised bg-surface`
                    }`}
                  >
                    {d}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Expertise add form */}
          {showExpertiseAdd && (
            <div className="px-3 py-3 border-b border-border-subtle space-y-2">
              <div className="flex gap-2">
                <select
                  value={peCategory}
                  onChange={(e) => setPeCategory(e.target.value)}
                  className="flex-1 rounded-md border border-border-subtle bg-surface-raised px-2 py-1 text-xs text-text-primary"
                >
                  <option value="convention">Convention</option>
                  <option value="pattern">Pattern</option>
                  <option value="failure">Failure</option>
                  <option value="decision">Decision</option>
                  <option value="reference">Reference</option>
                </select>
                <select
                  value={peDomain}
                  onChange={(e) => setPeDomain(e.target.value)}
                  className="flex-1 rounded-md border border-border-subtle bg-surface-raised px-2 py-1 text-xs text-text-primary"
                >
                  <option value="">No domain</option>
                  <option value="python">Python</option>
                  <option value="typescript">TypeScript</option>
                  <option value="javascript">JavaScript</option>
                  <option value="database">Database</option>
                  <option value="testing">Testing</option>
                  <option value="frontend">Frontend</option>
                  <option value="devops">DevOps</option>
                  <option value="security">Security</option>
                  <option value="architecture">Architecture</option>
                  <option value="performance">Performance</option>
                </select>
              </div>
              <textarea
                value={peContent}
                onChange={(e) => setPeContent(e.target.value)}
                placeholder="Describe the expertise, convention, or pattern..."
                rows={2}
                className="w-full rounded-md border border-border-subtle bg-surface-raised px-2 py-1 text-xs text-text-primary placeholder:text-text-muted resize-none"
              />
              <input
                type="text"
                value={peTags}
                onChange={(e) => setPeTags(e.target.value)}
                placeholder="Tags (comma-separated)"
                className="w-full rounded-md border border-border-subtle bg-surface-raised px-2 py-1 text-xs text-text-primary placeholder:text-text-muted"
              />
              <button
                onClick={addExpertise}
                disabled={!peContent.trim() || !projectDir}
                className="rounded-md bg-accent px-3 py-1 text-xs font-medium text-white hover:bg-accent-hover transition-colors disabled:opacity-50"
              >
                Save Expertise
              </button>
            </div>
          )}

          {/* Expertise list grouped by domain */}
          <div className="flex-1 overflow-y-auto min-h-0">
            {expertiseLoading ? (
              <div className="flex items-center justify-center h-32">
                <span className="text-sm text-text-muted">Loading...</span>
              </div>
            ) : !projectDir ? (
              <div className="flex items-center justify-center h-32 p-4">
                <span className="text-sm text-text-muted text-center">
                  Select a project to view its expertise.
                </span>
              </div>
            ) : expertise.length === 0 ? (
              <div className="flex items-center justify-center h-32 p-4">
                <span className="text-sm text-text-muted text-center">
                  No project expertise yet. Record conventions, patterns, and decisions as the agent works.
                </span>
              </div>
            ) : (
              <div className="divide-y divide-border-subtle">
                {Object.entries(expertiseByDomain)
                  .sort(([a], [b]) => a.localeCompare(b))
                  .map(([domain, entries]) => (
                    <div key={domain}>
                      <div className="px-3 py-2 bg-surface-raised sticky top-0 z-10 flex items-center gap-2">
                        <span className={`text-xs font-mono font-medium ${DOMAIN_COLORS[domain] || "text-text-primary"}`}>
                          {domain}
                        </span>
                        <span className="text-[10px] text-text-muted">
                          {entries.length} {entries.length === 1 ? "entry" : "entries"}
                        </span>
                      </div>
                      {entries.map((entry) => (
                        <ExpertiseItem key={entry.id} entry={entry} onDelete={deleteExpertise} />
                      ))}
                    </div>
                  ))}
              </div>
            )}
          </div>
        </>
      )}

      {/* === GLOBAL MEMORY TAB === */}
      {topTab === "global" && <>
      {/* Header */}
      <div className="px-3 py-2 border-b border-border-subtle bg-surface-raised">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <span className="text-xs text-text-muted font-mono">
              Agent Memory
            </span>
            {/* View toggle */}
            <div className="flex rounded-md border border-border-subtle overflow-hidden">
              <button
                onClick={() => setViewMode("flat")}
                className={`px-1.5 py-0.5 text-[10px] font-mono transition-colors ${
                  viewMode === "flat" ? "bg-accent/20 text-accent" : "text-text-muted hover:text-text-secondary"
                }`}
              >
                Flat
              </button>
              <button
                onClick={() => setViewMode("domains")}
                className={`px-1.5 py-0.5 text-[10px] font-mono transition-colors ${
                  viewMode === "domains" ? "bg-accent/20 text-accent" : "text-text-muted hover:text-text-secondary"
                }`}
              >
                Domains
              </button>
              <button
                onClick={() => setViewMode("priming")}
                className={`px-1.5 py-0.5 text-[10px] font-mono transition-colors ${
                  viewMode === "priming" ? "bg-accent/20 text-accent" : "text-text-muted hover:text-text-secondary"
                }`}
              >
                Priming
              </button>
            </div>
          </div>
          <button
            onClick={() => setShowAdd(!showAdd)}
            className="text-xs text-accent hover:text-accent-hover transition-colors"
          >
            {showAdd ? "Cancel" : "+ Add"}
          </button>
        </div>
        <input
          type="text"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            searchMemories(e.target.value);
          }}
          placeholder="Search memories..."
          className="w-full rounded-md border border-border-subtle bg-surface px-2 py-1 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent transition-colors"
        />

        {/* Outcome filter + sort controls */}
        {viewMode === "flat" && (
          <div className="flex items-center gap-2 mt-2">
            <div className="flex rounded-md border border-border-subtle overflow-hidden">
              {(
                [
                  ["all", "All"],
                  ["proven", "Proven"],
                  ["failures", "Failures"],
                  ["untracked", "Untracked"],
                ] as [OutcomeFilter, string][]
              ).map(([key, label]) => (
                <button
                  key={key}
                  onClick={() => setOutcomeFilter(key)}
                  className={`px-1.5 py-0.5 text-[10px] font-mono transition-colors ${
                    outcomeFilter === key
                      ? "bg-accent/20 text-accent"
                      : "text-text-muted hover:text-text-secondary"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            <select
              value={sortMode}
              onChange={(e) => setSortMode(e.target.value as SortMode)}
              className="text-[10px] font-mono rounded border border-border-subtle bg-surface px-1 py-0.5 text-text-muted"
            >
              <option value="relevance">Relevance</option>
              <option value="success_rate">Success Rate</option>
              <option value="most_used">Most Used</option>
            </select>
          </div>
        )}

        {/* Domain filter pills */}
        {domains.length > 0 && viewMode === "flat" && (
          <div className="flex flex-wrap gap-1 mt-2">
            <button
              onClick={() => setFilterDomain("")}
              className={`text-[10px] px-1.5 py-0.5 rounded font-mono transition-colors ${
                !filterDomain ? "bg-accent/20 text-accent" : "text-text-muted hover:text-text-secondary bg-surface"
              }`}
            >
              All
            </button>
            {domains.map((d) => (
              <button
                key={d}
                onClick={() => setFilterDomain(d === filterDomain ? "" : d)}
                className={`text-[10px] px-1.5 py-0.5 rounded font-mono transition-colors ${
                  d === filterDomain
                    ? "bg-accent/20 text-accent"
                    : `${DOMAIN_COLORS[d] || "text-text-muted"} hover:bg-surface-raised bg-surface`
                }`}
              >
                {d}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Add form */}
      {showAdd && (
        <div className="px-3 py-3 border-b border-border-subtle space-y-2">
          <div className="flex gap-2">
            <select
              value={newCategory}
              onChange={(e) => setNewCategory(e.target.value)}
              className="flex-1 rounded-md border border-border-subtle bg-surface-raised px-2 py-1 text-xs text-text-primary"
            >
              <option value="pattern">Pattern</option>
              <option value="mistake">Mistake</option>
              <option value="solution">Solution</option>
              <option value="preference">Preference</option>
            </select>
            <select
              value={newDomain}
              onChange={(e) => setNewDomain(e.target.value)}
              className="flex-1 rounded-md border border-border-subtle bg-surface-raised px-2 py-1 text-xs text-text-primary"
            >
              <option value="">No domain</option>
              <option value="python">Python</option>
              <option value="typescript">TypeScript</option>
              <option value="javascript">JavaScript</option>
              <option value="database">Database</option>
              <option value="testing">Testing</option>
              <option value="frontend">Frontend</option>
              <option value="devops">DevOps</option>
              <option value="security">Security</option>
              <option value="architecture">Architecture</option>
              <option value="performance">Performance</option>
            </select>
          </div>
          <textarea
            value={newContent}
            onChange={(e) => setNewContent(e.target.value)}
            placeholder="What did you learn?"
            rows={2}
            className="w-full rounded-md border border-border-subtle bg-surface-raised px-2 py-1 text-xs text-text-primary placeholder:text-text-muted resize-none"
          />
          <input
            type="text"
            value={newTags}
            onChange={(e) => setNewTags(e.target.value)}
            placeholder="Tags (comma-separated)"
            className="w-full rounded-md border border-border-subtle bg-surface-raised px-2 py-1 text-xs text-text-primary placeholder:text-text-muted"
          />
          <button
            onClick={addMemory}
            className="rounded-md bg-accent px-3 py-1 text-xs font-medium text-white hover:bg-accent-hover transition-colors"
          >
            Save Memory
          </button>
        </div>
      )}

      {/* Priming view */}
      {viewMode === "priming" && (
        <div className="flex-1 overflow-y-auto min-h-0 p-3 space-y-3">
          <div className="space-y-2">
            <label className="text-[10px] font-mono text-text-muted uppercase tracking-wider block">
              File Paths (one per line)
            </label>
            <textarea
              value={primingFiles}
              onChange={(e) => setPrimingFiles(e.target.value)}
              placeholder="src/auth.py&#10;src/models/user.py&#10;tests/test_auth.py"
              rows={4}
              className="w-full rounded-md border border-border-subtle bg-surface-raised px-2 py-1 text-xs text-text-primary placeholder:text-text-muted font-mono resize-none"
            />
            <button
              onClick={async () => {
                setPrimingLoading(true);
                try {
                  const files = primingFiles.split("\n").map(f => f.trim()).filter(Boolean);
                  const params = new URLSearchParams();
                  files.forEach(f => params.append("files", f));
                  const res = await fetch(`/api/memory/prime?${params}`);
                  const data = await res.json();
                  setPrimingResult(data.context || data.priming_context || "No priming context generated.");
                } catch {
                  setPrimingResult("Failed to fetch priming context.");
                } finally {
                  setPrimingLoading(false);
                }
              }}
              disabled={primingLoading || !primingFiles.trim()}
              className="rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-white hover:bg-accent-hover transition-colors disabled:opacity-50"
            >
              {primingLoading ? "Loading..." : "Preview Priming"}
            </button>
          </div>

          {/* Domain mapping visualization */}
          <div>
            <h3 className="text-[10px] font-mono text-text-muted uppercase tracking-wider mb-1.5">
              File-to-Domain Mapping
            </h3>
            <div className="space-y-1 text-[10px] font-mono">
              {[
                { ext: ".py", domain: "python", color: "text-[#3572A5]" },
                { ext: ".ts/.tsx", domain: "typescript", color: "text-[#3178c6]" },
                { ext: ".js/.jsx", domain: "javascript", color: "text-[#f1e05a]" },
                { ext: ".sql/.prisma", domain: "database", color: "text-[#e38c00]" },
                { ext: "test/spec", domain: "testing", color: "text-success" },
                { ext: ".css/.scss", domain: "styling", color: "text-[#ff69b4]" },
                { ext: ".yml/Dockerfile", domain: "devops", color: "text-warning" },
              ].map(({ ext, domain, color }) => (
                <div key={ext} className="flex items-center gap-2">
                  <span className="text-text-muted w-24">{ext}</span>
                  <span className="text-text-muted">{"\u2192"}</span>
                  <span className={color}>{domain}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Priming result */}
          {primingResult && (
            <div>
              <h3 className="text-[10px] font-mono text-text-muted uppercase tracking-wider mb-1.5">
                Priming Context Preview
              </h3>
              <pre className="text-xs font-mono text-text-secondary bg-surface rounded-lg border border-border-subtle p-3 whitespace-pre-wrap overflow-x-auto max-h-64 overflow-y-auto">
                {primingResult}
              </pre>
            </div>
          )}
        </div>
      )}

      {/* Memory list */}
      {viewMode !== "priming" && <div className="flex-1 overflow-y-auto min-h-0">
        {loading ? (
          <div className="flex items-center justify-center h-full">
            <span className="text-sm text-text-muted">Loading...</span>
          </div>
        ) : filteredMemories.length === 0 ? (
          <div className="flex items-center justify-center h-full p-4">
            <span className="text-sm text-text-muted text-center">
              {filterDomain
                ? `No memories in ${filterDomain} domain.`
                : outcomeFilter !== "all"
                ? `No memories matching "${outcomeFilter}" filter.`
                : "No memories yet. The agent learns from errors automatically, or add memories manually."}
            </span>
          </div>
        ) : viewMode === "domains" ? (
          /* Domain-grouped view */
          <div className="divide-y divide-border-subtle">
            {Object.entries(memoryByDomain)
              .sort(([a], [b]) => a.localeCompare(b))
              .map(([domain, entries]) => (
                <div key={domain}>
                  <div className="px-3 py-2 bg-surface-raised sticky top-0 z-10 flex items-center gap-2">
                    <span className={`text-xs font-mono font-medium ${DOMAIN_COLORS[domain] || "text-text-primary"}`}>
                      {domain}
                    </span>
                    <span className="text-[10px] text-text-muted">
                      {entries.length} {entries.length === 1 ? "entry" : "entries"}
                    </span>
                  </div>
                  {entries.map((mem) => (
                    <MemoryItem key={mem.id} mem={mem} onDelete={deleteMemory} onRecordOutcome={recordOutcome} />
                  ))}
                </div>
              ))}
          </div>
        ) : (
          /* Flat view */
          <div className="divide-y divide-border-subtle/50">
            {filteredMemories.map((mem) => (
              <MemoryItem key={mem.id} mem={mem} onDelete={deleteMemory} onRecordOutcome={recordOutcome} />
            ))}
          </div>
        )}
      </div>}
      </>}
    </div>
  );
}

function ExpertiseItem({ entry, onDelete }: { entry: ExpertiseEntry; onDelete: (id: string) => void }) {
  return (
    <div className="px-3 py-2.5 hover:bg-surface-raised/50 transition-colors">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span
              className={`text-[10px] px-1.5 py-0.5 rounded-full border font-medium ${
                CATEGORY_COLORS[entry.category] || CATEGORY_COLORS.pattern
              }`}
            >
              {entry.category}
            </span>
            {entry.domain && (
              <span
                className={`text-[10px] px-1.5 py-0.5 rounded bg-surface border border-border-subtle font-mono ${
                  DOMAIN_COLORS[entry.domain] || "text-text-muted"
                }`}
              >
                {entry.domain}
              </span>
            )}
            {entry.tags
              .filter((t) => t !== entry.domain)
              .map((tag) => (
                <span
                  key={tag}
                  className="text-[10px] text-text-muted bg-surface px-1 rounded"
                >
                  {tag}
                </span>
              ))}
          </div>
          <p className="text-xs text-text-secondary">{entry.content}</p>
          <div className="flex items-center gap-3 mt-1">
            {entry.source_file && (
              <span className="text-[10px] text-text-muted font-mono truncate">
                {entry.source_file}
              </span>
            )}
            {entry.created_at && (
              <span className="text-[10px] text-text-muted">
                {new Date(entry.created_at).toLocaleDateString()}
              </span>
            )}
          </div>
        </div>
        <button
          onClick={() => onDelete(entry.id)}
          className="text-text-muted hover:text-error text-xs p-0.5 transition-colors shrink-0"
          title="Delete expertise"
        >
          {"\u2715"}
        </button>
      </div>
    </div>
  );
}

function MemoryItem({
  mem,
  onDelete,
  onRecordOutcome,
}: {
  mem: MemoryEntry;
  onDelete: (id: string) => void;
  onRecordOutcome: (id: string, outcome: "success" | "partial" | "failure") => void;
}) {
  const successRate = getSuccessRate(mem);
  const hasOutcomes = mem.outcome_count > 0;

  return (
    <div className="px-3 py-2.5 hover:bg-surface-raised/50 transition-colors">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span
              className={`text-[10px] px-1.5 py-0.5 rounded-full border font-medium ${
                CATEGORY_COLORS[mem.category] || CATEGORY_COLORS.pattern
              }`}
            >
              {mem.category}
            </span>
            {mem.domain && (
              <span
                className={`text-[10px] px-1.5 py-0.5 rounded bg-surface border border-border-subtle font-mono ${
                  DOMAIN_COLORS[mem.domain] || "text-text-muted"
                }`}
              >
                {mem.domain}
              </span>
            )}
            {mem.expertise_type && (
              <span className="text-[10px] text-text-muted bg-surface px-1 rounded font-mono">
                {mem.expertise_type}
              </span>
            )}
            {/* Success rate badge */}
            {hasOutcomes && (
              <span
                className={`text-[10px] px-1.5 py-0.5 rounded font-mono font-medium ${getSuccessRateColor(successRate)} bg-surface border border-border-subtle`}
              >
                {mem.success_count}/{mem.outcome_count}
              </span>
            )}
            {mem.tags
              .filter((t) => t !== mem.domain)
              .map((tag) => (
                <span
                  key={tag}
                  className="text-[10px] text-text-muted bg-surface px-1 rounded"
                >
                  {tag}
                </span>
              ))}
          </div>

          {/* Confidence bar */}
          {hasOutcomes && (
            <div className="h-1 w-full rounded-full bg-border-subtle overflow-hidden mb-1.5">
              <div
                className={`h-full rounded-full transition-all ${getSuccessRateBgColor(successRate)}`}
                style={{ width: `${Math.max(successRate * 100, 2)}%` }}
              />
            </div>
          )}

          <p className="text-xs text-text-secondary">{mem.content}</p>
          {mem.project_source && (
            <p className="text-[10px] text-text-muted mt-0.5 font-mono truncate">
              {mem.project_source}
            </p>
          )}

          {/* Record outcome buttons */}
          <div className="flex items-center gap-1.5 mt-1.5">
            <button
              onClick={() => onRecordOutcome(mem.id, "success")}
              className="text-[10px] px-1.5 py-0.5 rounded border border-success/30 text-success hover:bg-success/10 transition-colors font-mono"
              title="Record success"
            >
              {"✓"} Success
            </button>
            <button
              onClick={() => onRecordOutcome(mem.id, "partial")}
              className="text-[10px] px-1.5 py-0.5 rounded border border-warning/30 text-warning hover:bg-warning/10 transition-colors font-mono"
              title="Record partial success"
            >
              ~ Partial
            </button>
            <button
              onClick={() => onRecordOutcome(mem.id, "failure")}
              className="text-[10px] px-1.5 py-0.5 rounded border border-error/30 text-error hover:bg-error/10 transition-colors font-mono"
              title="Record failure"
            >
              {"✗"} Failure
            </button>
          </div>
        </div>
        <button
          onClick={() => onDelete(mem.id)}
          className="text-text-muted hover:text-error text-xs p-0.5 transition-colors shrink-0"
          title="Delete memory"
        >
          {"\u2715"}
        </button>
      </div>
    </div>
  );
}
