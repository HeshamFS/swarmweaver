"use client";

import { useState, useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { ApprovalRequestData } from "../hooks/useSwarmWeaver";

interface ApprovalGateProps {
  request: ApprovalRequestData;
  onResolve: (decision: string, feedback: string) => void;
}

export function ApprovalGate({ request, onResolve }: ApprovalGateProps) {
  const [feedback, setFeedback] = useState("");
  const [showFeedback, setShowFeedback] = useState(false);
  const [feedbackAction, setFeedbackAction] = useState<"rejected" | "reflect" | null>(null);

  /* ── Keyboard shortcuts ── */
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLInputElement) return;
      if (e.key === "a" || e.key === "A") {
        e.preventDefault();
        onResolve("approved", feedback);
      } else if (e.key === "r" || e.key === "R") {
        e.preventDefault();
        setFeedbackAction("rejected");
        setShowFeedback(true);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [feedback, onResolve]);

  const handleFeedbackAction = () => {
    if (feedbackAction) {
      onResolve(feedbackAction, feedback);
      setShowFeedback(false);
      setFeedbackAction(null);
    }
  };

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-[100] flex items-center justify-center bg-black/40 backdrop-blur-xl p-4 sm:p-8"
      >
        <motion.div
          initial={{ scale: 0.95, opacity: 0, y: 20 }}
          animate={{ scale: 1, opacity: 1, y: 0 }}
          exit={{ scale: 0.95, opacity: 0, y: 20 }}
          transition={{ type: "spring", bounce: 0.3, duration: 0.6 }}
          className="w-full max-w-6xl h-full max-h-[800px] bg-[var(--color-surface-glass)] backdrop-blur-2xl border border-[var(--color-border-subtle)] rounded-3xl shadow-[0_20px_60px_rgba(0,0,0,0.8)] flex flex-col overflow-hidden relative"
        >
          {/* Header */}
          <div className="flex items-center justify-between px-8 py-5 border-b border-[var(--color-border-subtle)] bg-[var(--color-surface-1)]/30 backdrop-blur-md">
            <div className="flex items-center gap-4">
              <div className="w-10 h-10 rounded-full bg-[var(--color-accent)]/20 text-[var(--color-accent)] border border-[var(--color-accent)]/40 flex items-center justify-center glow-border">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
              </div>
              <div>
                <h2 className="text-xl font-bold text-[var(--color-text-primary)]">Agent Approval Required</h2>
                <div className="flex items-center gap-2 mt-1">
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded-md bg-[var(--color-accent)]/10 text-[var(--color-accent)] border border-[var(--color-accent)]/20 uppercase tracking-widest">
                    {request.gate_type}
                  </span>
                  <span className="text-xs text-[var(--color-text-muted)] font-medium">SwarmWeaver is waiting for your authorization</span>
                </div>
              </div>
            </div>

            {/* Action Buttons Top Right */}
            <div className="flex items-center gap-2">
              <button onClick={() => onResolve("skipped", feedback)} className="px-4 py-2 rounded-xl text-xs font-bold uppercase tracking-wider text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-2)] transition-colors border border-transparent hover:border-[var(--color-border-subtle)]">
                Skip
              </button>
              <button
                onClick={() => { setFeedbackAction("reflect"); setShowFeedback(true); }}
                className="px-4 py-2 rounded-xl text-xs font-bold uppercase tracking-wider text-[var(--color-accent)] bg-[var(--color-accent)]/10 hover:bg-[var(--color-accent)]/20 border border-[var(--color-accent)]/30 transition-colors"
              >
                Reflect
              </button>
              <button
                onClick={() => { setFeedbackAction("rejected"); setShowFeedback(true); }}
                className="px-4 py-2 rounded-xl text-xs font-bold uppercase tracking-wider text-[var(--color-error)] bg-[var(--color-error)]/10 hover:bg-[var(--color-error)]/20 border border-[var(--color-error)]/30 transition-colors"
                title="Keyboard: R"
              >
                Reject <kbd className="ml-1 opacity-50 font-mono">R</kbd>
              </button>
              <button
                onClick={() => onResolve("approved", feedback)}
                className="px-6 py-2 rounded-xl text-xs font-bold uppercase tracking-wider text-white bg-[var(--color-success)] hover:bg-[var(--color-success)]/80 shadow-[0_0_15px_rgba(16,185,129,0.3)] transition-colors hover:scale-105 active:scale-95"
                title="Keyboard: A"
              >
                Approve <kbd className="ml-1 opacity-50 font-mono border-none bg-black/20 px-1 py-0.5 rounded">A</kbd>
              </button>
            </div>
          </div>

          {/* Main Content Split View */}
          <div className="flex-1 flex overflow-hidden">
            {/* Left: Context & Feedback */}
            <div className="w-1/3 flex flex-col border-r border-[var(--color-border-subtle)] bg-[var(--color-surface-base)]/50">
              <div className="p-8 flex-1 overflow-y-auto">
                <h3 className="text-xs font-bold uppercase tracking-widest text-[var(--color-text-secondary)] mb-4">Request Summary</h3>
                <p className="text-sm text-[var(--color-text-primary)] leading-relaxed font-medium bg-[var(--color-surface-1)]/50 p-4 rounded-xl border border-[var(--color-border-subtle)] shadow-inner">
                  {request.summary}
                </p>

                <AnimatePresence>
                  {showFeedback && (
                    <motion.div
                      initial={{ opacity: 0, height: 0, marginTop: 0 }}
                      animate={{ opacity: 1, height: "auto", marginTop: 32 }}
                      exit={{ opacity: 0, height: 0, marginTop: 0 }}
                      className="overflow-hidden"
                    >
                      <h3 className="text-xs font-bold uppercase tracking-widest text-[var(--color-text-secondary)] mb-3 flex items-center gap-2">
                        {feedbackAction === "rejected" ? <span className="text-[var(--color-error)]">\u26A0\uFE0F Reason for Rejection</span> : <span className="text-[var(--color-accent)]">\uD83D\uDCA1 Reflection Guidance</span>}
                      </h3>
                      <textarea
                        autoFocus
                        value={feedback}
                        onChange={(e) => setFeedback(e.target.value)}
                        placeholder="Type your instructions to the agent here..."
                        rows={4}
                        className={`w-full p-4 rounded-xl border bg-[var(--color-surface-1)]/80 text-sm text-[var(--color-text-primary)] focus:outline-none transition-colors shadow-inner resize-none ${feedbackAction === "rejected" ? "focus:border-[var(--color-error)] border-[var(--color-error)]/30 focus:shadow-[0_0_0_3px_rgba(239,68,68,0.1)]" : "focus:border-[var(--color-accent)] border-[var(--color-border-subtle)] focus:shadow-[0_0_0_3px_var(--color-accent-glow)]"}`}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                            e.preventDefault();
                            handleFeedbackAction();
                          }
                        }}
                      />
                      <div className="flex justify-end mt-3">
                        <button
                          onClick={handleFeedbackAction}
                          className={`px-4 py-2 rounded-lg text-xs font-bold uppercase tracking-wider text-white transition-colors hover:scale-105 active:scale-95 ${feedbackAction === "rejected" ? "bg-[var(--color-error)] hover:bg-[var(--color-error)]/80" : "bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)]"}`}
                        >
                          Submit {feedbackAction === "rejected" ? "Rejection" : "Reflection"}
                        </button>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </div>

            {/* Right: Immersive Side-by-Side Diff (Mocked) */}
            <div className="w-2/3 bg-[#0D1117] flex flex-col relative overflow-hidden">
              <div className="absolute top-0 left-0 right-0 h-10 bg-[#010409] border-b border-[#30363D] flex items-center px-4 justify-between">
                <div className="flex gap-4 text-xs font-mono font-bold">
                  <span className="text-[#FF7B72]">- original_file.tsx</span>
                  <span className="text-[#3FB950]">+ proposed_changes.tsx</span>
                </div>
                <span className="text-[#8B949E] text-[10px] uppercase font-bold tracking-wider">Simulated Diff View</span>
              </div>
              <div className="flex-1 mt-10 p-6 overflow-y-auto font-mono text-sm leading-relaxed text-[#c9d1d9] flex select-none">
                {/* Left gutter */}
                <div className="flex flex-col text-[#484f58] text-right pr-4 border-r border-[#30363D]">
                  <span>1</span><span>2</span><span>3</span><span>4</span><span>5</span><span>6</span><span>7</span>
                </div>
                {/* Code body */}
                <div className="flex flex-col flex-1 pl-4 whitespace-pre">
                  <span><span className="text-[#FF7B72]">import</span> &#123; useState &#125; <span className="text-[#FF7B72]">from</span> <span className="text-[#a5d6ff]">&apos;react&apos;</span>;</span>
                  <span className="bg-[#2ea043]/15 w-full block border-l-2 border-[#2ea043] pl-2 -ml-[2px]"><span className="text-[#FF7B72]">import</span> &#123; motion &#125; <span className="text-[#FF7B72]">from</span> <span className="text-[#a5d6ff]">&apos;framer-motion&apos;</span>; <span className="text-[#8b949e]">{" "}{/* Agent addition */}</span></span>
                  <span></span>
                  <span><span className="text-[#FF7B72]">export</span> <span className="text-[#FF7B72]">default</span> <span className="text-[#FF7B72]">function</span> <span className="text-[#d2a8ff]">Component</span>() &#123;</span>
                  <span className="bg-[#f85149]/15 w-full block border-l-2 border-[#f85149] pl-2 -ml-[2px] opacity-60 text-decoration-line-through">  <span className="text-[#FF7B72]">return</span> &lt;<span className="text-[#7ee787]">div</span>&gt;Hello World&lt;/<span className="text-[#7ee787]">div</span>&gt;;</span>
                  <span className="bg-[#2ea043]/15 w-full block border-l-2 border-[#2ea043] pl-2 -ml-[2px]">  <span className="text-[#FF7B72]">return</span> &lt;<span className="text-[#7ee787]">motion.div</span> animate=&#123;&#123; opacity: <span className="text-[#79c0ff]">1</span> &#125;&#125;&gt;Hello Worlds Mode!&lt;/<span className="text-[#7ee787]">motion.div</span>&gt;;</span>
                  <span>&#125;</span>
                </div>
              </div>

              {/* Flashline animation simulating scanning */}
              <motion.div
                animate={{ y: [0, 600, 0] }}
                transition={{ duration: 4, repeat: Infinity, ease: "linear" }}
                className="absolute left-0 right-0 h-0.5 bg-[var(--color-accent)]/30 shadow-[0_0_20px_var(--color-accent)] pointer-events-none"
              />
            </div>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
