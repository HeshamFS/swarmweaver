"use client";

import { useState, useMemo } from "react";

interface SecurityFinding {
  id: string;
  severity: "critical" | "high" | "medium" | "low" | "info";
  category: string;
  title: string;
  description: string;
  file?: string;
  line?: number;
  recommendation: string;
}

interface SecurityScanBlockProps {
  isLoading: boolean;
  findings: SecurityFinding[] | null;
  onApproveFindings: (ids: string[], reasons: Record<string, string>) => void;
  approved: boolean;
}

const SEVERITY_COLORS: Record<SecurityFinding["severity"], string> = {
  critical: "#f85149",
  high: "#f0883e",
  medium: "#d29922",
  low: "#58a6ff",
  info: "#8b949e",
};

const SEVERITY_ORDER: SecurityFinding["severity"][] = ["critical", "high", "medium", "low", "info"];

export default function SecurityScanBlock({
  isLoading,
  findings,
  onApproveFindings,
  approved,
}: SecurityScanBlockProps) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [ignoreReasons, setIgnoreReasons] = useState<Record<string, string>>({});
  const [initialized, setInitialized] = useState(false);

  const hasFindings = findings && findings.length > 0;

  // Auto-select critical + high findings on first load
  if (hasFindings && !initialized) {
    const autoSelected = new Set<string>();
    findings.forEach((f) => {
      if (f.severity === "critical" || f.severity === "high") {
        autoSelected.add(f.id);
      }
    });
    setSelected(autoSelected);
    setInitialized(true);
  }

  const grouped = useMemo(() => {
    if (!findings) return {};
    const groups: Record<string, SecurityFinding[]> = {};
    for (const sev of SEVERITY_ORDER) {
      const items = findings.filter((f) => f.severity === sev);
      if (items.length > 0) groups[sev] = items;
    }
    return groups;
  }, [findings]);

  const stats = useMemo(() => {
    if (!findings) return null;
    const total = findings.length;
    const selectedCount = selected.size;
    const bySeverity: Record<string, number> = {};
    findings.forEach((f) => {
      bySeverity[f.severity] = (bySeverity[f.severity] || 0) + 1;
    });
    return { total, selectedCount, bySeverity };
  }, [findings, selected]);

  const toggleSelected = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.delete(id); // ensure clean
        next.add(id);
        // Clear ignore reason when re-selecting
        setIgnoreReasons((prev) => {
          const copy = { ...prev };
          delete copy[id];
          return copy;
        });
      }
      return next;
    });
  };

  const toggleExpanded = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleApprove = () => {
    onApproveFindings(Array.from(selected), ignoreReasons);
  };

  if (approved) {
    return (
      <div className="border border-[#222] bg-[#121212] mb-3 font-mono">
        <div className="flex items-center gap-3 px-4 py-2">
          <span className="text-[#555]">{"\u2713"}</span>
          <span className="text-[#555] text-xs font-bold uppercase tracking-wider">Security Findings Approved</span>
          {stats && <span className="text-[#555] text-xs ml-auto">{stats.selectedCount} findings selected</span>}
        </div>
      </div>
    );
  }

  if (isLoading && !hasFindings) {
    return null;
  }

  if (!hasFindings) {
    return (
      <div className="border border-[#333] bg-[#121212] mb-3 font-mono p-4">
        <span className="text-[#555] text-xs">No security findings detected.</span>
      </div>
    );
  }

  return (
    <div className="border border-[#333] bg-[#121212] mb-3 font-mono">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-[#222] bg-[#0C0C0C]">
        <span className="text-[var(--color-accent)]">{"\u25A0"}</span>
        <span className="text-[#E0E0E0] text-xs font-bold uppercase tracking-wider">Security Findings</span>
        {stats && (
          <div className="flex items-center gap-3 ml-auto text-[10px]">
            <span className="text-[#888]">{stats.selectedCount}/{stats.total} selected</span>
            <span className="text-[#555]">|</span>
            {SEVERITY_ORDER.map(
              (sev) =>
                stats.bySeverity[sev] && (
                  <span key={sev} style={{ color: SEVERITY_COLORS[sev] }}>
                    {stats.bySeverity[sev]} {sev}
                  </span>
                )
            )}
          </div>
        )}
      </div>

      {/* Findings list grouped by severity */}
      <div className="max-h-[400px] overflow-y-auto tui-scrollbar">
        {Object.entries(grouped).map(([severity, items]) => (
          <div key={severity}>
            {/* Severity group header */}
            <div className="px-4 py-1.5 border-b border-[#1A1A1A] bg-[#0C0C0C]">
              <span
                className="text-[10px] uppercase tracking-widest font-bold"
                style={{ color: SEVERITY_COLORS[severity as SecurityFinding["severity"]] }}
              >
                {severity}
              </span>
              <span className="text-[#555] text-[10px] ml-2">({items.length})</span>
            </div>

            {items.map((finding) => {
              const isSelected = selected.has(finding.id);
              const isExpanded = expanded.has(finding.id);

              return (
                <div key={finding.id} className="border-b border-[#1A1A1A]">
                  {/* Finding row */}
                  <div
                    className={`flex items-start gap-3 px-4 py-2 hover:bg-[#1A1A1A] transition-colors ${!isSelected ? "opacity-50" : ""}`}
                  >
                    <button
                      onClick={() => toggleSelected(finding.id)}
                      className={`text-xs font-bold shrink-0 mt-0.5 transition-colors ${
                        isSelected ? "text-[var(--color-accent)]" : "text-[#555]"
                      }`}
                    >
                      {isSelected ? "[x]" : "[ ]"}
                    </button>
                    <div className="min-w-0 flex-1">
                      <button
                        onClick={() => toggleExpanded(finding.id)}
                        className="text-left w-full"
                      >
                        <div className="flex items-center gap-2">
                          <span
                            className="text-[10px] font-bold uppercase shrink-0"
                            style={{ color: SEVERITY_COLORS[finding.severity] }}
                          >
                            {"\u25A0"}
                          </span>
                          <span className={`text-xs ${isSelected ? "text-[#E0E0E0]" : "text-[#555]"}`}>
                            {finding.title}
                          </span>
                          <span className="text-[10px] text-[#555] shrink-0 ml-auto">
                            {isExpanded ? "\u25BC" : "\u25B6"}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 mt-0.5">
                          <span className="text-[10px] text-[#555]">{finding.category}</span>
                          {finding.file && (
                            <>
                              <span className="text-[10px] text-[#333]">|</span>
                              <span className="text-[10px] text-[#555]">
                                {finding.file}{finding.line !== undefined ? `:${finding.line}` : ""}
                              </span>
                            </>
                          )}
                        </div>
                      </button>

                      {/* Expanded details */}
                      {isExpanded && (
                        <div className="mt-2 pl-4 border-l border-[#222]">
                          <div className="text-[10px] text-[#888] mb-2 leading-relaxed">
                            {finding.description}
                          </div>
                          <div className="text-[10px] mb-1">
                            <span className="text-[#555] uppercase tracking-wider">Recommendation:</span>
                          </div>
                          <div className="text-[10px] text-[#888] leading-relaxed">
                            {finding.recommendation}
                          </div>
                        </div>
                      )}

                      {/* Ignore reason input when deselected */}
                      {!isSelected && (
                        <div className="flex items-center gap-2 mt-1.5">
                          <span className="text-[10px] text-[#555]">Ignore reason:</span>
                          <input
                            type="text"
                            value={ignoreReasons[finding.id] || ""}
                            onChange={(e) =>
                              setIgnoreReasons((prev) => ({ ...prev, [finding.id]: e.target.value }))
                            }
                            placeholder="Why is this being ignored?"
                            className="flex-1 bg-transparent text-[10px] text-[#888] outline-none placeholder-[#333] font-mono border-b border-[#222] pb-0.5"
                          />
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        ))}
      </div>

      {/* Actions */}
      <div className="flex items-center justify-between px-4 py-3 border-t border-[#222]">
        <span className="text-[10px] text-[#555] font-mono">
          {selected.size} of {findings.length} findings selected for remediation
        </span>
        <button
          onClick={handleApprove}
          disabled={selected.size === 0}
          className="bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] disabled:bg-[#333] disabled:text-[#555] text-[#0C0C0C] px-6 py-1.5 font-bold text-xs uppercase tracking-wider transition-colors font-mono"
        >
          Approve Selected & Generate Tasks {"\u2192"}
        </button>
      </div>
    </div>
  );
}
