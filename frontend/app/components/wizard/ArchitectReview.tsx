"use client";

import { useState, useEffect, useRef, useMemo } from "react";
import { motion } from "framer-motion";
import { Group, Panel, Separator } from "react-resizable-panels";
import MarkdownPreview from "../MarkdownPreview";

interface ArchitectReviewProps {
  isLoading: boolean;
  generatedSpec: string | null;
  projectDir: string;
  onApproveAndBuild: () => void;
  onRegenerate: (feedback: string) => void;
  onSaveSpec: (projectDir: string, spec: string) => Promise<void>;
  onBack: () => void;
}

const ARCHITECT_PHASES = [
  { key: "research", label: "Researching your idea", icon: "search" },
  { key: "analyze", label: "Analyzing tech stack options", icon: "settings" },
  { key: "write", label: "Writing project specification", icon: "doc" },
  { key: "ready", label: "Ready for review", icon: "check" },
];

const PhaseIcon = ({ type }: { type: string }) => {
  const color = "currentColor";
  if (type === "search") return <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2"><circle cx="11" cy="11" r="8" /><path d="M21 21l-4.35-4.35" /></svg>;
  if (type === "settings") return <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2"><path d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><circle cx="12" cy="12" r="3" /></svg>;
  if (type === "doc") return <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2"><path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>;
  return <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2.5"><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>;
};

export default function ArchitectReview({
  isLoading, generatedSpec, projectDir, onApproveAndBuild, onRegenerate, onSaveSpec, onBack,
}: ArchitectReviewProps) {
  const [editedSpec, setEditedSpec] = useState("");
  const [regenerateFeedback, setRegenerateFeedback] = useState("");
  const [showRegenerateInput, setShowRegenerateInput] = useState(false);
  const editorRef = useRef<HTMLTextAreaElement>(null);
  const lineNumberRef = useRef<HTMLDivElement>(null);

  const isComplete = !!generatedSpec && !isLoading;

  // Animate through phases during loading
  const [currentPhase, setCurrentPhase] = useState(0);
  useEffect(() => {
    if (!isLoading) {
      setCurrentPhase(3); // Ready
      return;
    }
    setCurrentPhase(0);
    const timers = [
      setTimeout(() => setCurrentPhase(1), 5000),
      setTimeout(() => setCurrentPhase(2), 30000),
    ];
    return () => timers.forEach(clearTimeout);
  }, [isLoading]);

  useEffect(() => {
    if (generatedSpec) setEditedSpec(generatedSpec);
  }, [generatedSpec]);

  // Sync line number scroll with editor scroll
  const handleEditorScroll = () => {
    if (editorRef.current && lineNumberRef.current) {
      lineNumberRef.current.scrollTop = editorRef.current.scrollTop;
    }
  };

  // Compute line numbers from the edited spec
  const lineCount = useMemo(() => {
    return editedSpec.split("\n").length;
  }, [editedSpec]);

  const handleApprove = async () => {
    if (editedSpec !== generatedSpec) await onSaveSpec(projectDir, editedSpec);
    onApproveAndBuild();
  };

  const handleRegenerate = () => {
    if (regenerateFeedback.trim()) {
      onRegenerate(regenerateFeedback);
      setRegenerateFeedback("");
      setShowRegenerateInput(false);
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      {/* Header */}
      <div className="flex items-center gap-4 mb-8">
        <button onClick={onBack} className="p-2 rounded-xl hover:bg-[var(--surface-overlay)] transition-colors text-[var(--text-muted)] hover:text-[var(--text-primary)] border border-[var(--border-subtle)]">
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" /></svg>
        </button>
        <div>
          <h2 className="text-xl font-semibold text-[var(--text-primary)]">
            {isComplete ? "Review Your Specification" : "Designing Your Project"}
          </h2>
          <p className="text-sm text-[var(--text-muted)] mt-0.5">
            {isComplete ? "Edit on the left, preview on the right. Approve when ready." : "The architect is analyzing your idea and writing a spec"}
          </p>
        </div>
      </div>

      {/* Progress Checklist with staggered animation -- only while running */}
      {!isComplete && (
        <div className="mb-8 p-5 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-raised)]">
          <div className="space-y-3.5">
            {ARCHITECT_PHASES.map((phase, i) => {
              const isDone = i < currentPhase;
              const isCurrent = i === currentPhase;
              return (
                <motion.div
                  key={phase.key}
                  initial={{ opacity: 0, x: -12 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.12, duration: 0.35, ease: "easeOut" }}
                  className="flex items-center gap-3.5"
                >
                  <motion.div
                    className={`w-7 h-7 rounded-lg flex items-center justify-center transition-all duration-300 ${
                      isDone ? "bg-[var(--color-success)] text-white" : isCurrent ? "bg-[var(--accent)] text-white" : "bg-[var(--surface-overlay)] text-[var(--text-muted)]"
                    }`}
                    animate={isCurrent ? {
                      boxShadow: [
                        "0 0 0px rgba(var(--accent-rgb, 99, 102, 241), 0.3)",
                        "0 0 16px rgba(var(--accent-rgb, 99, 102, 241), 0.6)",
                        "0 0 0px rgba(var(--accent-rgb, 99, 102, 241), 0.3)",
                      ],
                    } : {}}
                    transition={isCurrent ? { duration: 1.5, repeat: Infinity, ease: "easeInOut" } : {}}
                  >
                    {isDone ? (
                      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>
                    ) : isCurrent ? (
                      <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
                    ) : (
                      <PhaseIcon type={phase.icon} />
                    )}
                  </motion.div>
                  <span className={`text-sm transition-colors ${isDone ? "text-[var(--text-secondary)] line-through" : isCurrent ? "text-[var(--text-primary)] font-medium" : "text-[var(--text-muted)]"}`}>
                    {phase.label}
                  </span>
                  {isCurrent && (
                    <motion.span
                      className="w-1.5 h-1.5 rounded-full bg-[var(--accent)]"
                      animate={{ opacity: [1, 0.3, 1] }}
                      transition={{ duration: 1.2, repeat: Infinity, ease: "easeInOut" }}
                    />
                  )}
                </motion.div>
              );
            })}
          </div>
        </div>
      )}

      {/* Side-by-Side Spec Editor + Preview using react-resizable-panels */}
      {isComplete && (
        <div className="space-y-5">
          <div className="rounded-xl border border-[var(--border-default)] bg-[var(--surface-raised)] overflow-hidden">
            {/* Header bar */}
            <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--border-subtle)] bg-[var(--surface-overlay)]">
              <div className="flex items-center gap-2">
                <svg className="w-4 h-4 text-[var(--text-muted)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <span className="text-sm font-mono text-[var(--text-secondary)]">app_spec.txt</span>
              </div>
              <span className="text-xs text-[var(--text-muted)]">
                Drag the divider to resize
              </span>
            </div>

            {/* Resizable side-by-side panels */}
            <div style={{ height: "clamp(400px, 55vh, 700px)" }}>
              <Group orientation="horizontal">
                {/* Left: Editor with line numbers */}
                <Panel defaultSize="50%" minSize="25%">
                  <div className="flex flex-col h-full min-h-0">
                    <div className="px-3 py-1.5 border-b border-[var(--border-subtle)] bg-[var(--surface)]">
                      <span className="text-[10px] font-mono text-[var(--text-muted)] uppercase tracking-wider">Editor</span>
                    </div>
                    <div className="flex flex-1 min-h-0 overflow-hidden">
                      {/* Line numbers */}
                      <div
                        ref={lineNumberRef}
                        className="overflow-hidden select-none py-4 pr-2 pl-3 text-right font-mono text-xs leading-relaxed text-[var(--text-muted)] bg-[var(--surface)] border-r border-[var(--border-subtle)]"
                        style={{ minWidth: "3rem" }}
                      >
                        {Array.from({ length: lineCount }, (_, i) => (
                          <div key={i + 1} className="h-[1.625em]">{i + 1}</div>
                        ))}
                      </div>
                      {/* Textarea */}
                      <textarea
                        ref={editorRef}
                        value={editedSpec}
                        onChange={(e) => setEditedSpec(e.target.value)}
                        onScroll={handleEditorScroll}
                        className="flex-1 w-full p-4 text-sm font-mono bg-[var(--surface)] text-[var(--text-primary)] border-none outline-none resize-none leading-relaxed"
                        spellCheck={false}
                      />
                    </div>
                  </div>
                </Panel>

                {/* Resize handle */}
                <Separator className="w-1.5 bg-[var(--border-subtle)] hover:bg-[var(--accent)] transition-colors cursor-col-resize" />

                {/* Right: Markdown Preview */}
                <Panel defaultSize="50%" minSize="25%">
                  <div className="flex flex-col h-full min-h-0">
                    <div className="px-3 py-1.5 border-b border-[var(--border-subtle)] bg-[var(--surface)]">
                      <span className="text-[10px] font-mono text-[var(--text-muted)] uppercase tracking-wider">Preview</span>
                    </div>
                    <div className="flex-1 overflow-y-auto p-4 prose-invert text-sm">
                      <MarkdownPreview>{editedSpec || generatedSpec || ""}</MarkdownPreview>
                    </div>
                  </div>
                </Panel>
              </Group>
            </div>
          </div>

          {/* Regenerate feedback input */}
          {showRegenerateInput && (
            <div className="p-5 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-raised)] space-y-3">
              <label className="block text-sm font-medium text-[var(--text-secondary)]">What should be different?</label>
              <textarea value={regenerateFeedback} onChange={(e) => setRegenerateFeedback(e.target.value)} placeholder="E.g., Use PostgreSQL instead of SQLite, add a WebSocket layer..." rows={3} className="w-full px-3.5 py-2.5 text-sm rounded-xl border border-[var(--border-default)] bg-[var(--surface)] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] resize-y" />
              <div className="flex gap-2">
                <button onClick={handleRegenerate} disabled={!regenerateFeedback.trim()} className={`px-4 py-2.5 text-sm rounded-xl font-medium transition-all ${regenerateFeedback.trim() ? "bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white" : "bg-[var(--surface-overlay)] text-[var(--text-muted)] cursor-not-allowed"}`}>
                  Regenerate
                </button>
                <button onClick={() => { setShowRegenerateInput(false); setRegenerateFeedback(""); }} className="px-4 py-2.5 text-sm rounded-xl text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors">Cancel</button>
              </div>
            </div>
          )}

          {/* Action buttons */}
          <div className="flex gap-3">
            <button onClick={() => setShowRegenerateInput(!showRegenerateInput)} className="px-5 py-3.5 text-sm rounded-xl border border-[var(--border-default)] text-[var(--text-secondary)] hover:bg-[var(--surface-overlay)] hover:text-[var(--text-primary)] transition-all">
              Regenerate
            </button>
            <button onClick={handleApprove} className="flex-1 py-3.5 rounded-xl text-sm font-semibold bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white shadow-lg shadow-[var(--accent)]/20 hover:shadow-[var(--accent)]/30 transition-all">
              Approve &amp; Build
            </button>
          </div>
        </div>
      )}

      {/* Initial loading state */}
      {isLoading && !generatedSpec && (
        <div className="text-center py-16">
          <div className="inline-flex items-center gap-2.5 text-[var(--text-muted)] text-sm">
            <svg className="w-4 h-4 animate-spin text-[var(--accent)]" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
            Generating specification...
          </div>
        </div>
      )}
    </div>
  );
}
