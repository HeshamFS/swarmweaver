/**
 * @deprecated This full-page component is replaced by SecurityScanBlock in
 * chat-blocks/SecurityScanBlock.tsx, which renders inside ChatWizardFeed with
 * the TUI aesthetic. Kept for reference only — do not import.
 */
"use client";

import { useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { SecurityReport, SecurityFinding } from "../../hooks/useSwarmWeaver";

/* -- Severity config -- */
const SEVERITY_CONFIG: Record<string, { label: string; color: string; bg: string; border: string; order: number }> = {
  critical: { label: "CRITICAL", color: "#f85149", bg: "rgba(248, 81, 73, 0.12)", border: "rgba(248, 81, 73, 0.3)", order: 0 },
  high:     { label: "HIGH",     color: "#f0883e", bg: "rgba(240, 136, 62, 0.12)", border: "rgba(240, 136, 62, 0.3)", order: 1 },
  medium:   { label: "MEDIUM",   color: "#d29922", bg: "rgba(210, 153, 34, 0.12)", border: "rgba(210, 153, 34, 0.3)", order: 2 },
  low:      { label: "LOW",      color: "#58a6ff", bg: "rgba(88, 166, 255, 0.12)", border: "rgba(88, 166, 255, 0.3)", order: 3 },
  info:     { label: "INFO",     color: "#8b949e", bg: "rgba(139, 148, 158, 0.12)", border: "rgba(139, 148, 158, 0.3)", order: 4 },
};

const SEVERITY_BAR_COLORS: Record<string, string> = {
  critical: "#f85149",
  high: "#f0883e",
  medium: "#d29922",
  low: "#58a6ff",
  info: "#8b949e",
};

const CATEGORY_LABELS: Record<string, string> = {
  secrets: "Secrets",
  dependencies: "Dependencies",
  injection: "Injection",
  auth: "Auth",
  config: "Configuration",
  xss: "XSS",
  csrf: "CSRF",
  "data-exposure": "Data Exposure",
  miscellaneous: "Misc",
};

type SortMode = "severity" | "file" | "category";
const SORT_OPTIONS: { value: SortMode; label: string }[] = [
  { value: "severity", label: "Severity" },
  { value: "file", label: "File" },
  { value: "category", label: "Category" },
];

interface SecurityReportReviewProps {
  isLoading: boolean;
  securityReport: SecurityReport | null;
  projectDir: string;
  onApproveFindings: (approvedIds: string[], ignoredReasons: Record<string, string>) => void;
  onBack: () => void;
}

export default function SecurityReportReview({
  isLoading,
  securityReport,
  projectDir,
  onApproveFindings,
  onBack,
}: SecurityReportReviewProps) {
  // Track which findings are selected for remediation
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [ignoredReasons, setIgnoredReasons] = useState<Record<string, string>>({});
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [initialized, setInitialized] = useState(false);

  // Sort and filter state
  const [sortBy, setSortBy] = useState<SortMode>("severity");
  const [activeFilters, setActiveFilters] = useState<Set<string>>(new Set()); // empty = show all

  // Auto-select critical and high findings when report arrives
  useMemo(() => {
    if (securityReport && !initialized) {
      const autoSelected = new Set<string>();
      for (const f of securityReport.findings) {
        if (f.severity === "critical" || f.severity === "high" || f.severity === "medium") {
          autoSelected.add(f.id);
        }
      }
      setSelected(autoSelected);
      setInitialized(true);
    }
  }, [securityReport, initialized]);

  // Compute severity counts for the bar chart
  const severityCounts = useMemo(() => {
    if (!securityReport) return {};
    const counts: Record<string, number> = {};
    for (const f of securityReport.findings) {
      counts[f.severity] = (counts[f.severity] || 0) + 1;
    }
    return counts;
  }, [securityReport]);

  const totalFindings = securityReport?.findings.length || 0;

  // Sort + filter findings
  const sortedFindings = useMemo(() => {
    if (!securityReport) return [];
    let findings = [...securityReport.findings];

    // Filter by active severity filters (empty set = no filter = show all)
    if (activeFilters.size > 0) {
      findings = findings.filter((f) => activeFilters.has(f.severity));
    }

    // Sort
    findings.sort((a, b) => {
      if (sortBy === "severity") {
        const oa = SEVERITY_CONFIG[a.severity]?.order ?? 9;
        const ob = SEVERITY_CONFIG[b.severity]?.order ?? 9;
        if (oa !== ob) return oa - ob;
        return a.id.localeCompare(b.id);
      }
      if (sortBy === "file") {
        const fa = a.file || "";
        const fb = b.file || "";
        if (fa !== fb) return fa.localeCompare(fb);
        return (a.line || 0) - (b.line || 0);
      }
      if (sortBy === "category") {
        if (a.category !== b.category) return a.category.localeCompare(b.category);
        const oa = SEVERITY_CONFIG[a.severity]?.order ?? 9;
        const ob = SEVERITY_CONFIG[b.severity]?.order ?? 9;
        return oa - ob;
      }
      return 0;
    });

    return findings;
  }, [securityReport, sortBy, activeFilters]);

  const approvedCount = selected.size;
  const totalCount = securityReport?.findings.length || 0;

  const toggleFinding = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
        // Remove ignore reason if re-selected
        setIgnoredReasons((prev) => {
          const copy = { ...prev };
          delete copy[id];
          return copy;
        });
      }
      return next;
    });
  };

  const selectAll = () => {
    const all = new Set(sortedFindings.map((f) => f.id));
    setSelected(all);
    setIgnoredReasons({});
  };

  const deselectAll = () => {
    setSelected(new Set());
  };

  // Bulk action: Approve all Critical + High
  const approveAllCriticalHigh = () => {
    if (!securityReport) return;
    const next = new Set(selected);
    for (const f of securityReport.findings) {
      if (f.severity === "critical" || f.severity === "high") {
        next.add(f.id);
        // Remove any ignore reason
        setIgnoredReasons((prev) => {
          const copy = { ...prev };
          delete copy[f.id];
          return copy;
        });
      }
    }
    setSelected(next);
  };

  // Bulk action: Ignore all Low
  const ignoreAllLow = () => {
    if (!securityReport) return;
    const next = new Set(selected);
    for (const f of securityReport.findings) {
      if (f.severity === "low") {
        next.delete(f.id);
      }
    }
    setSelected(next);
  };

  // Toggle severity filter chip
  const toggleFilter = (severity: string) => {
    setActiveFilters((prev) => {
      const next = new Set(prev);
      if (next.has(severity)) {
        next.delete(severity);
      } else {
        next.add(severity);
      }
      return next;
    });
  };

  const handleApprove = () => {
    const approvedIds = Array.from(selected);
    onApproveFindings(approvedIds, ignoredReasons);
  };

  const scanComplete = !isLoading && securityReport !== null;

  // --- SCANNING STATE: Show loading spinner ---
  if (isLoading) {
    return (
      <div className="max-w-4xl mx-auto px-6 py-10">
        <div className="flex items-center gap-4 mb-8">
          <button onClick={onBack} className="p-2 rounded-xl hover:bg-[var(--surface-overlay)] transition-colors text-[var(--text-muted)] hover:text-[var(--text-primary)] border border-[var(--border-subtle)]">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" /></svg>
          </button>
          <div>
            <h2 className="text-xl font-semibold text-[var(--text-primary)] flex items-center gap-3">
              <span className="w-8 h-8 rounded-lg flex items-center justify-center text-[var(--color-mode-security)]" style={{ background: "rgba(6, 182, 212, 0.1)", border: "1px solid rgba(6, 182, 212, 0.2)" }}>
                <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" /></svg>
              </span>
              Scanning...
            </h2>
            <p className="text-sm text-[var(--text-muted)] mt-0.5">Analyzing codebase for security vulnerabilities</p>
          </div>
          <div className="ml-auto">
            <span className="w-2 h-2 rounded-full bg-[var(--color-mode-security)] animate-pulse inline-block" />
          </div>
        </div>

        <div className="text-center py-16">
          <div className="inline-flex items-center gap-2.5 text-[var(--text-muted)] text-sm">
            <svg className="w-4 h-4 animate-spin text-[var(--color-mode-security)]" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
            Scanning codebase for vulnerabilities...
          </div>
        </div>
      </div>
    );
  }

  // --- REVIEW STATE: Show interactive findings report ---
  if (!securityReport) {
    return (
      <div className="max-w-4xl mx-auto px-6 py-10 text-center">
        <p className="text-[var(--text-muted)]">No security report found. The scan may not have completed successfully.</p>
        <button onClick={onBack} className="mt-4 px-4 py-2 text-sm rounded-lg border border-[var(--border-subtle)] text-[var(--text-secondary)] hover:bg-[var(--surface-overlay)]">Go Back</button>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-6 py-10">
      {/* Header */}
      <div className="flex items-center gap-4 mb-6">
        <button onClick={onBack} className="p-2 rounded-xl hover:bg-[var(--surface-overlay)] transition-colors text-[var(--text-muted)] hover:text-[var(--text-primary)] border border-[var(--border-subtle)]">
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" /></svg>
        </button>
        <div>
          <h2 className="text-xl font-semibold text-[var(--text-primary)] flex items-center gap-2">
            <span className="w-8 h-8 rounded-lg flex items-center justify-center text-[var(--color-mode-security)]" style={{ background: "rgba(6, 182, 212, 0.1)", border: "1px solid rgba(6, 182, 212, 0.2)" }}>
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" /><path d="M9 12l2 2 4-4" /></svg>
            </span>
            Security Report
          </h2>
          <p className="text-sm text-[var(--text-muted)] mt-0.5">{totalCount} findings &middot; Select which to fix, ignore the rest</p>
        </div>
      </div>

      {/* Severity summary bar */}
      {totalFindings > 0 && (
        <div className="mb-6 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-raised)] p-4">
          <div className="flex items-center gap-3 mb-3">
            <span className="text-xs font-medium text-[var(--text-secondary)] uppercase tracking-wider">Severity Distribution</span>
          </div>
          {/* Proportional horizontal bar */}
          <div className="flex h-6 rounded-lg overflow-hidden mb-3">
            {["critical", "high", "medium", "low", "info"].map((sev) => {
              const count = severityCounts[sev] || 0;
              if (count === 0) return null;
              const pct = (count / totalFindings) * 100;
              return (
                <div
                  key={sev}
                  className="flex items-center justify-center text-[10px] font-bold text-white transition-all duration-300"
                  style={{
                    width: `${pct}%`,
                    backgroundColor: SEVERITY_BAR_COLORS[sev],
                    minWidth: count > 0 ? "2rem" : 0,
                  }}
                  title={`${SEVERITY_CONFIG[sev]?.label}: ${count}`}
                >
                  {pct >= 8 ? count : ""}
                </div>
              );
            })}
          </div>
          {/* Legend labels */}
          <div className="flex flex-wrap gap-3">
            {["critical", "high", "medium", "low", "info"].map((sev) => {
              const count = severityCounts[sev] || 0;
              if (count === 0) return null;
              const cfg = SEVERITY_CONFIG[sev];
              return (
                <div key={sev} className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: cfg.color }} />
                  <span className="text-xs text-[var(--text-secondary)]">{count} {cfg.label}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Filter chips */}
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <span className="text-xs text-[var(--text-muted)] mr-1">Filter:</span>
        {["critical", "high", "medium", "low"].map((sev) => {
          const cfg = SEVERITY_CONFIG[sev];
          const count = severityCounts[sev] || 0;
          const isActive = activeFilters.has(sev);
          return (
            <button
              key={sev}
              onClick={() => toggleFilter(sev)}
              className={`px-2.5 py-1 text-xs font-semibold rounded-lg border transition-all duration-200 ${
                isActive
                  ? "text-white"
                  : "hover:opacity-80"
              }`}
              style={{
                color: isActive ? "#fff" : cfg.color,
                backgroundColor: isActive ? cfg.color : cfg.bg,
                borderColor: isActive ? cfg.color : cfg.border,
              }}
            >
              {cfg.label} ({count})
            </button>
          );
        })}
        {activeFilters.size > 0 && (
          <button
            onClick={() => setActiveFilters(new Set())}
            className="px-2 py-1 text-[10px] text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors"
          >
            Clear filters
          </button>
        )}
      </div>

      {/* Sort + Bulk actions row */}
      <div className="flex items-center gap-3 mb-4 flex-wrap">
        {/* Sort dropdown */}
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-[var(--text-muted)]">Sort:</span>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as SortMode)}
            className="text-xs px-2 py-1.5 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface)] text-[var(--text-secondary)] focus:outline-none focus:border-[var(--accent)] transition-colors cursor-pointer"
          >
            {SORT_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>

        <div className="w-px h-5 bg-[var(--border-subtle)]" />

        {/* Bulk actions */}
        <button onClick={approveAllCriticalHigh} className="text-xs px-3 py-1.5 rounded-lg border border-[var(--border-subtle)] text-[var(--text-secondary)] hover:bg-[var(--surface-overlay)] transition-colors">
          Approve all Critical+High
        </button>
        <button onClick={ignoreAllLow} className="text-xs px-3 py-1.5 rounded-lg border border-[var(--border-subtle)] text-[var(--text-secondary)] hover:bg-[var(--surface-overlay)] transition-colors">
          Ignore all Low
        </button>

        <div className="w-px h-5 bg-[var(--border-subtle)]" />

        <button onClick={selectAll} className="text-xs px-3 py-1.5 rounded-lg border border-[var(--border-subtle)] text-[var(--text-secondary)] hover:bg-[var(--surface-overlay)] transition-colors">Select All</button>
        <button onClick={deselectAll} className="text-xs px-3 py-1.5 rounded-lg border border-[var(--border-subtle)] text-[var(--text-secondary)] hover:bg-[var(--surface-overlay)] transition-colors">Deselect All</button>
        <span className="text-xs text-[var(--text-muted)] ml-auto">{approvedCount} of {totalCount} selected</span>
      </div>

      {/* Findings list */}
      <div className="space-y-2 mb-8">
        {sortedFindings.map((finding) => {
          const cfg = SEVERITY_CONFIG[finding.severity] || SEVERITY_CONFIG.info;
          const isSelected = selected.has(finding.id);
          const isExpanded = expandedId === finding.id;
          const catLabel = CATEGORY_LABELS[finding.category] || finding.category;

          return (
            <div
              key={finding.id}
              className={`rounded-xl border transition-all duration-200 ${
                isSelected
                  ? "border-[var(--border-default)] bg-[var(--surface-raised)]"
                  : "border-[var(--border-subtle)] bg-[var(--surface-raised)]/50 opacity-70"
              }`}
            >
              {/* Finding header row */}
              <div className="flex items-start gap-3 px-4 py-3">
                {/* Checkbox */}
                <button
                  onClick={() => toggleFinding(finding.id)}
                  className={`mt-0.5 w-5 h-5 rounded-md border-2 flex items-center justify-center shrink-0 transition-all duration-200 ${
                    isSelected
                      ? "border-[var(--color-mode-security)] bg-[var(--color-mode-security)]"
                      : "border-[var(--border-default)] hover:border-[var(--text-muted)]"
                  }`}
                >
                  {isSelected && (
                    <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>
                  )}
                </button>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap mb-1">
                    <span className="text-[10px] font-mono text-[var(--text-muted)]">{finding.id}</span>
                    <span
                      className="text-[10px] font-bold px-1.5 py-0.5 rounded"
                      style={{ color: cfg.color, background: cfg.bg }}
                    >
                      {cfg.label}
                    </span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--surface-overlay)] text-[var(--text-muted)]">{catLabel}</span>
                  </div>
                  <p className="text-sm font-medium text-[var(--text-primary)] leading-snug">{finding.title}</p>
                  {finding.file && (
                    <p className="text-xs text-[var(--text-muted)] mt-0.5 font-mono">
                      {finding.file}{finding.line ? `:${finding.line}` : ""}
                    </p>
                  )}
                </div>

                {/* Expand toggle */}
                <button
                  onClick={() => setExpandedId(isExpanded ? null : finding.id)}
                  className="p-1 rounded-lg hover:bg-[var(--surface-overlay)] text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors shrink-0"
                >
                  <svg className={`w-4 h-4 transition-transform duration-200 ${isExpanded ? "rotate-180" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                  </svg>
                </button>
              </div>

              {/* Animated expanded details */}
              <AnimatePresence initial={false}>
                {isExpanded && (
                  <motion.div
                    key={`detail-${finding.id}`}
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.25, ease: "easeInOut" }}
                    className="overflow-hidden"
                  >
                    <div className="px-4 pb-4 pt-0 ml-8 space-y-3 border-t border-[var(--border-subtle)] mt-1 pt-3">
                      <div>
                        <p className="text-xs font-medium text-[var(--text-secondary)] mb-1">Description</p>
                        <p className="text-sm text-[var(--text-secondary)] leading-relaxed">{finding.description}</p>
                      </div>
                      <div>
                        <p className="text-xs font-medium text-[var(--text-secondary)] mb-1">Recommendation</p>
                        <p className="text-sm text-[var(--text-secondary)] leading-relaxed">{finding.recommendation}</p>
                      </div>
                      {finding.acceptance_criteria.length > 0 && (
                        <div>
                          <p className="text-xs font-medium text-[var(--text-secondary)] mb-1">Acceptance Criteria</p>
                          <ul className="list-disc list-inside text-sm text-[var(--text-muted)] space-y-0.5">
                            {finding.acceptance_criteria.map((c, i) => (
                              <li key={i}>{c}</li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {/* Ignore reason input (only shown when unchecked) */}
                      {!isSelected && (
                        <div>
                          <label className="text-xs text-[var(--text-muted)] mb-1 block">Ignore reason (optional)</label>
                          <input
                            type="text"
                            value={ignoredReasons[finding.id] || ""}
                            onChange={(e) => setIgnoredReasons((prev) => ({ ...prev, [finding.id]: e.target.value }))}
                            placeholder="e.g. Intentional -- test fixture only"
                            className="w-full px-3 py-1.5 text-xs rounded-lg border border-[var(--border-subtle)] bg-[var(--surface)] text-[var(--text-primary)] placeholder:text-[var(--text-muted)]"
                          />
                        </div>
                      )}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          );
        })}
      </div>

      {/* Approve button */}
      <div className="sticky bottom-4">
        <button
          onClick={handleApprove}
          disabled={approvedCount === 0}
          className={`w-full py-3.5 rounded-xl text-sm font-semibold transition-all duration-300 ${
            approvedCount > 0
              ? "bg-[var(--color-mode-security)] hover:brightness-110 text-white shadow-lg shadow-[var(--color-mode-security)]/20"
              : "bg-[var(--surface-overlay)] text-[var(--text-muted)] cursor-not-allowed border border-[var(--border-subtle)]"
          }`}
        >
          {approvedCount > 0
            ? `Approve & Fix ${approvedCount} Finding${approvedCount > 1 ? "s" : ""}`
            : "Select findings to fix"
          }
        </button>
      </div>
    </div>
  );
}
