"use client";

import { useEffect, useRef, useMemo } from "react";
import MarkdownPreview from "../../MarkdownPreview";

interface AuditReportBlockProps {
  isLoading: boolean;
  reportText: string | null;
  onAcknowledge: () => void;
  acknowledged: boolean;
}

export default function AuditReportBlock({
  isLoading,
  reportText,
  onAcknowledge,
  acknowledged,
}: AuditReportBlockProps) {
  const contentRef = useRef<HTMLDivElement>(null);

  // Auto-scroll content while streaming
  useEffect(() => {
    if (isLoading && reportText && contentRef.current) {
      contentRef.current.scrollTop = contentRef.current.scrollHeight;
    }
  }, [reportText, isLoading]);

  const lineCount = useMemo(() => (reportText || "").split("\n").length, [reportText]);

  if (acknowledged) {
    return (
      <div className="border border-[#222] bg-[#121212] mb-3 font-mono">
        <div className="flex items-center gap-3 px-4 py-2">
          <span className="text-[#555]">{"\u2713"}</span>
          <span className="text-[#555] text-xs font-bold uppercase tracking-wider">Audit Acknowledged</span>
          <span className="text-[#555] text-xs ml-auto">{lineCount} lines</span>
        </div>
      </div>
    );
  }

  const isStreamingPartial = isLoading && !!reportText;

  if (isLoading && !reportText) {
    return null;
  }

  return (
    <div className="border border-[#333] bg-[#121212] mb-3 font-mono">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-[#222] bg-[#0C0C0C]">
        <span className="text-[var(--color-accent)]">{"\u25A0"}</span>
        <span className="text-[#E0E0E0] text-xs font-bold uppercase tracking-wider">Audit Report</span>
        {isStreamingPartial && (
          <span className="text-[var(--color-accent)] text-[10px] animate-pulse uppercase tracking-wider">streaming</span>
        )}
        <span className="text-[#555] text-xs ml-auto">{lineCount} lines</span>
      </div>

      {/* Content */}
      <div ref={contentRef} className="relative max-h-[400px] overflow-y-auto tui-scrollbar">
        <div className="p-4 text-xs">
          <MarkdownPreview>{reportText || ""}</MarkdownPreview>
          {isStreamingPartial && <span className="inline-block w-[2px] h-[14px] bg-[var(--color-accent)] ml-0.5 align-middle spec-cursor" />}
        </div>
      </div>

      {/* Actions — hidden while still streaming */}
      <div className={`flex items-center justify-end px-4 py-3 border-t border-[#222] ${isStreamingPartial ? "opacity-30 pointer-events-none" : ""}`}>
        <button
          onClick={onAcknowledge}
          className="bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-[#0C0C0C] px-6 py-1.5 font-bold text-xs uppercase tracking-wider transition-colors font-mono"
        >
          Acknowledge & Continue {"\u2192"}
        </button>
      </div>
    </div>
  );
}
