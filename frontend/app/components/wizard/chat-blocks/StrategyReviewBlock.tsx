"use client";

import { useState, useEffect, useRef, useMemo } from "react";
import { BrainCog } from "lucide-react";
import MarkdownPreview from "../../MarkdownPreview";

interface StrategyReviewBlockProps {
  isLoading: boolean;
  strategyText: string | null;
  onApprove: () => void;
  onRegenerate: (feedback: string) => void;
  approved: boolean;
}

export default function StrategyReviewBlock({
  isLoading,
  strategyText,
  onApprove,
  onRegenerate,
  approved,
}: StrategyReviewBlockProps) {
  const [editedStrategy, setEditedStrategy] = useState("");
  const [isEditing, setIsEditing] = useState(false);
  const [showRegenInput, setShowRegenInput] = useState(false);
  const [regenFeedback, setRegenFeedback] = useState("");
  const editorRef = useRef<HTMLTextAreaElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (strategyText) setEditedStrategy(strategyText);
  }, [strategyText]);

  useEffect(() => {
    if (isEditing && editorRef.current) editorRef.current.focus();
  }, [isEditing]);

  // Auto-scroll content while streaming
  useEffect(() => {
    if (isLoading && strategyText && contentRef.current) {
      contentRef.current.scrollTop = contentRef.current.scrollHeight;
    }
  }, [strategyText, isLoading]);

  const lineCount = useMemo(() => editedStrategy.split("\n").length, [editedStrategy]);
  const isModified = editedStrategy !== strategyText;

  const handleRegenerate = () => {
    if (!regenFeedback.trim()) return;
    setShowRegenInput(false);
    onRegenerate(regenFeedback.trim());
    setRegenFeedback("");
  };

  if (approved) {
    return (
      <div className="border border-[#222] bg-[#121212] mb-3 font-mono">
        <div className="flex items-center gap-3 px-4 py-2">
          <span className="text-[#555]">{"\u2713"}</span>
          <span className="text-[#555] text-xs font-bold uppercase tracking-wider">Strategy Approved</span>
          <span className="text-[#555] text-xs ml-auto">{lineCount} lines</span>
        </div>
      </div>
    );
  }

  const isStreamingPartial = isLoading && !!strategyText;

  if (isLoading && !strategyText) {
    return null;
  }

  return (
    <div className="border border-[#333] bg-[#121212] mb-3 font-mono">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-[#222] bg-[#0C0C0C]">
        <span className="text-[var(--color-accent)]">{"\u25A0"}</span>
        <span className="text-[#E0E0E0] text-xs font-bold uppercase tracking-wider">Migration Strategy</span>
        {isStreamingPartial && (
          <span className="text-[var(--color-accent)] text-[10px] animate-pulse uppercase tracking-wider">streaming</span>
        )}
        <span className="text-[#555] text-xs ml-auto">{lineCount} lines</span>
        {isModified && !isStreamingPartial && <span className="text-[var(--color-accent)] text-[10px] inline-flex items-center gap-1"><BrainCog className="w-3 h-3 shrink-0" /> modified</span>}
      </div>

      {/* Content */}
      <div ref={contentRef} className="relative max-h-[400px] overflow-y-auto tui-scrollbar">
        {isEditing ? (
          <textarea
            ref={editorRef}
            value={editedStrategy}
            onChange={(e) => setEditedStrategy(e.target.value)}
            className="w-full min-h-[300px] bg-[#0C0C0C] text-[#E0E0E0] text-xs p-4 font-mono resize-none focus:outline-none leading-relaxed"
            spellCheck={false}
          />
        ) : (
          <div className="p-4 text-xs">
            <MarkdownPreview>{editedStrategy}</MarkdownPreview>
            {isStreamingPartial && <span className="inline-block w-[2px] h-[14px] bg-[var(--color-accent)] ml-0.5 align-middle spec-cursor" />}
          </div>
        )}
      </div>

      {/* Regenerate input */}
      {showRegenInput && (
        <div className="px-4 py-2 border-t border-[#222] bg-[#0C0C0C]">
          <div className="flex items-center gap-2">
            <span className="text-[var(--color-accent)] text-xs">&gt;</span>
            <input
              type="text"
              value={regenFeedback}
              onChange={(e) => setRegenFeedback(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") handleRegenerate(); if (e.key === "Escape") setShowRegenInput(false); }}
              placeholder="What should be changed in the strategy?"
              className="flex-1 bg-transparent text-[#E0E0E0] text-xs outline-none placeholder-[#333] font-mono"
              autoFocus
            />
            <button
              onClick={handleRegenerate}
              disabled={!regenFeedback.trim()}
              className="text-[10px] text-[var(--color-accent)] hover:text-[var(--color-accent-hover)] disabled:text-[#333] uppercase tracking-wider transition-colors"
            >
              Regenerate
            </button>
          </div>
        </div>
      )}

      {/* Actions — hidden while still streaming */}
      <div className={`flex items-center justify-between px-4 py-3 border-t border-[#222] ${isStreamingPartial ? "opacity-30 pointer-events-none" : ""}`}>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setIsEditing(!isEditing)}
            className={`text-[10px] uppercase tracking-wider transition-colors font-mono border px-3 py-1 ${
              isEditing
                ? "border-[var(--color-accent)] text-[var(--color-accent)]"
                : "border-[#333] text-[#888] hover:text-[#E0E0E0] hover:border-[#555]"
            }`}
          >
            {isEditing ? "[ Preview ]" : "[ Edit ]"}
          </button>
          <button
            onClick={() => setShowRegenInput(!showRegenInput)}
            className="text-[10px] text-[#555] hover:text-[#888] uppercase tracking-wider transition-colors font-mono border border-[#333] px-3 py-1 hover:border-[#555]"
          >
            Regenerate
          </button>
        </div>
        <button
          onClick={onApprove}
          className="bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-[#0C0C0C] px-6 py-1.5 font-bold text-xs uppercase tracking-wider transition-colors font-mono"
        >
          Approve Strategy {"\u2192"}
        </button>
      </div>
    </div>
  );
}
