"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

interface WorkerState {
    id: string;
    angle: number;
    radius: number;
    status: "idle" | "working" | "sharing";
    currentTask: string;
    color: string;
}

export function SwarmVisualizer({ workerCount = 4, active = true }: { workerCount?: number; active?: boolean }) {
    const [workers, setWorkers] = useState<WorkerState[]>([]);
    const [activeConnections, setActiveConnections] = useState<[number, number][]>([]);

    // Initialize workers in a circle
    useEffect(() => {
        const newWorkers = Array.from({ length: workerCount }).map((_, i) => ({
            id: `worker-\${i}`,
            angle: (i * (360 / workerCount)),
            radius: 120, // distance from center
            status: "idle" as const,
            currentTask: "Waiting for instructions...",
            color: `var(--color-info)`, // Base color
        }));
        setWorkers(newWorkers);
    }, [workerCount]);

    // Simulate active worker states
    useEffect(() => {
        if (!active || workers.length === 0) return;

        const interval = setInterval(() => {
            setWorkers(prev => prev.map(w => {
                // Randomly change state to simulate work
                const rand = Math.random();
                let newStatus = w.status;
                let newColor = w.color;
                let newTask = w.currentTask;

                if (rand > 0.8) {
                    newStatus = "working";
                    newColor = "var(--color-accent)";
                    newTask = ["Analyzing dependencies", "Writing unit test", "Refactoring AST", "Generating code"][Math.floor(Math.random() * 4)];
                } else if (rand > 0.6) {
                    newStatus = "sharing";
                    newColor = "var(--color-success)";
                    newTask = "Syncing context...";
                } else if (rand < 0.1) {
                    newStatus = "idle";
                    newColor = "var(--color-info)";
                    newTask = "Standing by";
                }

                return { ...w, status: newStatus, color: newColor, currentTask: newTask };
            }));

            // Randomly create connections between sharing workers
            const newConnections: [number, number][] = [];
            for (let i = 0; i < workerCount; i++) {
                for (let j = i + 1; j < workerCount; j++) {
                    if (Math.random() > 0.8) {
                        newConnections.push([i, j]);
                    }
                }
            }
            setActiveConnections(newConnections);

        }, 2500);

        return () => clearInterval(interval);
    }, [active, workers.length, workerCount]);

    const centerX = 200;
    const centerY = 200;

    return (
        <div className="relative w-full h-full flex items-center justify-center bg-[var(--color-surface-base)] overflow-hidden rounded-2xl border border-[var(--color-border-subtle)] shadow-inner min-h-[400px]">
            {/* Background ambient pulse */}
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(59,130,246,0.05),transparent_70%)]" />

            <svg width={400} height={400} className="absolute z-10 pointer-events-none">
                {/* Draw connections */}
                <AnimatePresence>
                    {activeConnections.map(([i, j]) => {
                        const w1 = workers[i];
                        const w2 = workers[j];
                        if (!w1 || !w2) return null;

                        const x1 = centerX + Math.cos(w1.angle * (Math.PI / 180)) * w1.radius;
                        const y1 = centerY + Math.sin(w1.angle * (Math.PI / 180)) * w1.radius;
                        const x2 = centerX + Math.cos(w2.angle * (Math.PI / 180)) * w2.radius;
                        const y2 = centerY + Math.sin(w2.angle * (Math.PI / 180)) * w2.radius;

                        return (
                            <motion.line
                                key={`conn-\${i}-\${j}`}
                                x1={x1} y1={y1} x2={x2} y2={y2}
                                stroke="var(--color-success)"
                                strokeWidth={1.5}
                                initial={{ pathLength: 0, opacity: 0 }}
                                animate={{ pathLength: 1, opacity: 0.4 }}
                                exit={{ opacity: 0 }}
                                transition={{ duration: 0.5 }}
                            />
                        );
                    })}
                </AnimatePresence>
            </svg>

            {/* Main Core Node */}
            <div className="absolute z-20 flex flex-col items-center justify-center">
                <motion.div
                    animate={{ scale: active ? [1, 1.05, 1] : 1, boxShadow: active ? ["0 0 20px var(--color-accent)", "0 0 40px var(--color-accent)", "0 0 20px var(--color-accent)"] : "0 0 10px rgba(0,0,0,0.5)" }}
                    transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
                    className="w-16 h-16 rounded-full bg-[var(--color-surface-overlay)] border border-[var(--color-accent)] flex items-center justify-center z-20 backdrop-blur-md"
                >
                    <svg className="w-8 h-8 text-[var(--color-accent)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                </motion.div>
                <span className="text-[10px] font-bold uppercase tracking-widest text-[var(--color-text-muted)] mt-4">Coordinator</span>
            </div>

            {/* Orbiting Workers */}
            {workers.map((worker, index) => {
                const x = Math.cos(worker.angle * (Math.PI / 180)) * worker.radius;
                const y = Math.sin(worker.angle * (Math.PI / 180)) * worker.radius;

                return (
                    <motion.div
                        key={worker.id}
                        className="absolute z-30 flex flex-col items-center"
                        initial={{ opacity: 0, scale: 0 }}
                        animate={{
                            opacity: 1,
                            scale: 1,
                            x,
                            y,
                            rotate: active ? 360 : 0
                        }}
                        transition={{
                            opacity: { duration: 0.5, delay: index * 0.1 },
                            scale: { type: "spring", bounce: 0.5, delay: index * 0.1 },
                            rotate: { duration: 60, repeat: Infinity, ease: "linear" }
                        }}
                        style={{
                            transformOrigin: `\${-x}px \${-y}px`, // This makes them orbit around center! But text aligns to node.
                        }}
                    >
                        {/* The actual counter-rotated content so it stays upright */}
                        <motion.div
                            animate={{ rotate: active ? -360 : 0 }}
                            transition={{ duration: 60, repeat: Infinity, ease: "linear" }}
                            className="flex flex-col items-center"
                        >
                            <div
                                className="w-10 h-10 rounded-full border flex items-center justify-center relative shadow-lg backdrop-blur-md"
                                style={{
                                    backgroundColor: "var(--color-surface-glass)",
                                    borderColor: worker.color,
                                    boxShadow: `0 0 15px \${worker.color}40, inset 0 0 10px \${worker.color}20`
                                }}
                            >
                                {worker.status === "working" && (
                                    <svg className="w-5 h-5 animate-spin" style={{ color: worker.color }} fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                                )}
                                {worker.status !== "working" && (
                                    <span className="text-xs font-mono font-bold" style={{ color: worker.color }}>W{index + 1}</span>
                                )}

                                {/* Active glow ring */}
                                {worker.status !== "idle" && (
                                    <motion.div
                                        className="absolute inset-0 rounded-full border border-current"
                                        style={{ color: worker.color }}
                                        initial={{ scale: 1, opacity: 0.8 }}
                                        animate={{ scale: 1.5, opacity: 0 }}
                                        transition={{ duration: 1.5, repeat: Infinity }}
                                    />
                                )}
                            </div>
                            <div className="mt-2 bg-[var(--color-surface-glass)] backdrop-blur-md border border-[var(--color-border-subtle)] px-2 py-1 rounded truncate max-w-[120px]">
                                <span className="text-[9px] font-bold text-[var(--color-text-primary)] tracking-wide">{worker.currentTask}</span>
                            </div>
                        </motion.div>
                    </motion.div>
                );
            })}
        </div>
    );
}
