"use client";

import { motion } from "framer-motion";

interface PostMortemProps {
    onClose: () => void;
    onAction: (action: string) => void;
}

export function InteractivePostMortem({ onClose, onAction }: PostMortemProps) {
    const metrics = [
        { label: "Files Manipulated", value: "4", icon: "\uD83D\uDCC1" },
        { label: "Execution Time", value: "45s", icon: "\u23F1\uFE0F" },
        { label: "Total Tokens", value: "24,532", icon: "\uD83D\uDD04" },
        { label: "Est. Cost", value: "$0.08", icon: "\uD83D\uDCB8" },
    ];

    const files = [
        { name: "app/layout.tsx", status: "modified" },
        { name: "app/globals.css", status: "modified" },
        { name: "components/ThemeToggle.tsx", status: "created" },
        { name: "utils/theme.ts", status: "created" },
    ];

    return (
        <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-2xl p-4 sm:p-8"
        >
            <motion.div
                initial={{ scale: 0.9, opacity: 0, y: 20 }}
                animate={{ scale: 1, opacity: 1, y: 0 }}
                transition={{ type: "spring", bounce: 0.4, duration: 0.8 }}
                className="w-full max-w-4xl bg-[var(--color-surface-glass)] backdrop-blur-3xl border border-[var(--color-border-subtle)] rounded-3xl shadow-[0_30px_100px_rgba(0,0,0,0.8)] overflow-hidden relative"
            >
                {/* Glow effect */}
                <div className="absolute top-0 left-1/2 -translate-x-1/2 w-3/4 h-32 bg-[var(--color-success)]/20 blur-[100px] pointer-events-none" />

                <div className="p-8 sm:p-12 relative z-10 flex flex-col items-center">

                    <motion.div
                        initial={{ scale: 0 }}
                        animate={{ scale: 1 }}
                        transition={{ type: "spring", bounce: 0.5, delay: 0.2 }}
                        className="w-20 h-20 rounded-full bg-[var(--color-success)]/10 text-[var(--color-success)] flex items-center justify-center border border-[var(--color-success)]/20 shadow-[0_0_40px_rgba(16,185,129,0.3)] mb-6"
                    >
                        <svg className="w-10 h-10" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>
                    </motion.div>

                    <h2 className="text-3xl font-extrabold text-[var(--color-text-primary)] mb-2 tracking-tight text-center">Objective Complete</h2>
                    <p className="text-[var(--color-text-secondary)] text-center max-w-lg mb-10 font-medium">SwarmWeaver has successfully implemented the requested feature and verified the build.</p>

                    {/* Metrics Grid */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 w-full mb-10">
                        {metrics.map((m, i) => (
                            <motion.div
                                key={m.label}
                                initial={{ opacity: 0, y: 20 }}
                                animate={{ opacity: 1, y: 0 }}
                                transition={{ delay: 0.3 + (i * 0.1) }}
                                className="bg-[var(--color-surface-1)]/50 backdrop-blur-md border border-[var(--color-border-subtle)] rounded-2xl p-4 flex flex-col items-center justify-center gap-2 shadow-inner group hover:bg-[var(--color-surface-2)] transition-colors"
                            >
                                <div className="text-xl">{m.icon}</div>
                                <div className="text-2xl font-black text-[var(--color-text-primary)] font-mono">{m.value}</div>
                                <div className="text-[10px] font-bold uppercase tracking-wider text-[var(--color-text-muted)]">{m.label}</div>
                            </motion.div>
                        ))}
                    </div>

                    <div className="w-full flex flex-col sm:flex-row gap-8">
                        {/* File Changes */}
                        <div className="flex-1 bg-[var(--color-surface-base)]/50 border border-[var(--color-border-subtle)] rounded-2xl p-5 shadow-inner">
                            <h3 className="text-xs font-bold uppercase tracking-widest text-[var(--color-text-muted)] mb-4 flex items-center gap-2">
                                <svg className="w-4 h-4 text-[var(--color-accent)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
                                Files Manipulated
                            </h3>
                            <ul className="space-y-2">
                                {files.map((f, i) => (
                                    <motion.li
                                        key={f.name}
                                        initial={{ opacity: 0, x: -10 }}
                                        animate={{ opacity: 1, x: 0 }}
                                        transition={{ delay: 0.5 + (i * 0.1) }}
                                        className="flex items-center justify-between text-sm font-mono p-2 rounded-lg bg-[var(--color-surface-1)]/30 border border-transparent hover:border-[var(--color-border-subtle)] transition-colors cursor-pointer group"
                                    >
                                        <span className="text-[var(--color-text-primary)] group-hover:text-[var(--color-accent)] transition-colors">{f.name}</span>
                                        <span className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded-md ${f.status === 'created' ? 'bg-[var(--color-success)]/10 text-[var(--color-success)] border border-[var(--color-success)]/20' : 'bg-[var(--color-warning)]/10 text-[var(--color-warning)] border border-[var(--color-warning)]/20'}`}>
                                            {f.status}
                                        </span>
                                    </motion.li>
                                ))}
                            </ul>
                        </div>

                        {/* Next Actions */}
                        <div className="flex-1 flex flex-col gap-3">
                            <h3 className="text-xs font-bold uppercase tracking-widest text-[var(--color-text-muted)] mb-1 pl-2">Recommended Next Steps</h3>

                            <button onClick={() => onAction("tests")} className="w-full text-left p-4 rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-surface-1)] hover:bg-[var(--color-surface-2)] hover:border-[var(--color-border-default)] transition-all shadow-sm flex items-center justify-between group">
                                <div className="flex items-center gap-3">
                                    <span className="w-8 h-8 rounded-full bg-[var(--color-info)]/10 text-[var(--color-info)] flex items-center justify-center glow-border"><svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg></span>
                                    <div>
                                        <h4 className="text-sm font-bold text-[var(--color-text-primary)]">Write Unit Tests</h4>
                                        <p className="text-[10px] text-[var(--color-text-muted)] mt-0.5">Generate coverage for new components</p>
                                    </div>
                                </div>
                                <svg className="w-4 h-4 text-[var(--color-text-muted)] group-hover:text-[var(--color-info)] transform group-hover:translate-x-1 transition-all" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" /></svg>
                            </button>

                            <button onClick={() => onAction("docs")} className="w-full text-left p-4 rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-surface-1)] hover:bg-[var(--color-surface-2)] hover:border-[var(--color-border-default)] transition-all shadow-sm flex items-center justify-between group">
                                <div className="flex items-center gap-3">
                                    <span className="w-8 h-8 rounded-full bg-[var(--color-accent)]/10 text-[var(--color-accent)] flex items-center justify-center glow-border"><svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" /></svg></span>
                                    <div>
                                        <h4 className="text-sm font-bold text-[var(--color-text-primary)]">Update Documentation</h4>
                                        <p className="text-[10px] text-[var(--color-text-muted)] mt-0.5">Push changes to README.md</p>
                                    </div>
                                </div>
                                <svg className="w-4 h-4 text-[var(--color-text-muted)] group-hover:text-[var(--color-accent)] transform group-hover:translate-x-1 transition-all" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" /></svg>
                            </button>

                            <button onClick={onClose} className="w-full py-3 mt-auto rounded-xl border border-[var(--color-border-subtle)] text-sm font-bold text-[var(--color-text-primary)] hover:bg-[var(--color-surface-2)] transition-colors">
                                Return to Dashboard
                            </button>
                        </div>
                    </div>
                </div>
            </motion.div>
        </motion.div>
    );
}
