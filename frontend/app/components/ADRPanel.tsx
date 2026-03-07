"use client";

import { useState, useEffect } from "react";

interface ADREntry {
  number: number;
  title: string;
  status: string;
  date: string;
  filename: string;
}

interface ADRPanelProps {
  projectDir: string;
}

const STATUS_BADGES: Record<string, string> = {
  accepted: "text-success bg-success/10 border-success/30",
  proposed: "text-accent bg-accent/10 border-accent/30",
  deprecated: "text-text-muted bg-surface border-border-subtle",
  superseded: "text-warning bg-warning/10 border-warning/30",
};

export function ADRPanel({ projectDir }: ADRPanelProps) {
  const [adrs, setAdrs] = useState<ADREntry[]>([]);
  const [expandedFile, setExpandedFile] = useState<string | null>(null);
  const [content, setContent] = useState<string>("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchAdrs();
  }, [projectDir]);

  const fetchAdrs = async () => {
    if (!projectDir) return;
    setLoading(true);
    try {
      const res = await fetch(
        `/api/adrs?path=${encodeURIComponent(projectDir)}`
      );
      const data = await res.json();
      setAdrs(data.adrs || []);
    } catch {
      // Ignore
    } finally {
      setLoading(false);
    }
  };

  const fetchContent = async (filename: string) => {
    if (expandedFile === filename) {
      setExpandedFile(null);
      setContent("");
      return;
    }
    try {
      const res = await fetch(
        `/api/adrs/${filename}?path=${encodeURIComponent(projectDir)}`
      );
      const data = await res.json();
      setContent(data.content || "");
      setExpandedFile(filename);
    } catch {
      // Ignore
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col h-full rounded-lg border border-border-subtle bg-surface overflow-hidden">
        <div className="px-3 py-2 border-b border-border-subtle bg-surface-raised">
          <span className="text-xs text-text-muted font-mono">ADRs</span>
        </div>
        <div className="flex-1 flex items-center justify-center">
          <span className="text-sm text-text-muted">Loading...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full rounded-lg border border-border-subtle bg-surface overflow-hidden">
      {/* Header */}
      <div className="px-3 py-2 border-b border-border-subtle bg-surface-raised">
        <div className="flex items-center justify-between">
          <span className="text-xs text-text-muted font-mono">
            Architecture Decision Records
          </span>
          <span className="text-xs text-text-secondary font-mono">
            {adrs.length} ADR{adrs.length !== 1 ? "s" : ""}
          </span>
        </div>
      </div>

      {/* ADR list */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {adrs.length === 0 ? (
          <div className="flex items-center justify-center h-full p-4">
            <span className="text-sm text-text-muted text-center">
              No ADRs yet. Run the agent in feature or refactor mode to
              auto-generate architectural decisions.
            </span>
          </div>
        ) : (
          <div className="divide-y divide-border-subtle/50">
            {adrs.map((adr) => (
              <div key={adr.filename}>
                <button
                  onClick={() => fetchContent(adr.filename)}
                  className="w-full text-left px-3 py-3 hover:bg-surface-raised/50 transition-colors"
                >
                  <div className="flex items-start gap-2">
                    <span className="text-xs text-text-muted font-mono mt-0.5">
                      {String(adr.number).padStart(4, "0")}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm text-text-primary font-medium truncate">
                          {adr.title}
                        </span>
                        <span
                          className={`text-[10px] px-1.5 py-0.5 rounded-full border font-medium shrink-0 ${
                            STATUS_BADGES[adr.status] || STATUS_BADGES.accepted
                          }`}
                        >
                          {adr.status}
                        </span>
                      </div>
                      {adr.date && (
                        <span className="text-xs text-text-muted">
                          {adr.date}
                        </span>
                      )}
                    </div>
                    <span className="text-text-muted text-xs">
                      {expandedFile === adr.filename ? "\u25BC" : "\u25B6"}
                    </span>
                  </div>
                </button>

                {/* Expanded content */}
                {expandedFile === adr.filename && content && (
                  <div className="px-4 pb-3 border-t border-border-subtle/30">
                    <pre className="text-xs text-text-secondary whitespace-pre-wrap font-mono leading-relaxed mt-2 max-h-60 overflow-y-auto">
                      {content}
                    </pre>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
