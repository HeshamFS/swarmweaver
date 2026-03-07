"use client";

import { useState, useEffect, useRef } from "react";
import { motion } from "framer-motion";

interface LiveStreamEditorProps {
    filename?: string;
    isStreaming?: boolean;
}

const DUMMY_CODE = `// \u2728 Auto-generating code...
import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';

export function ThemeToggle() {
  const [theme, setTheme] = useState('dark');
  
  // Injecting into globals
  useEffect(() => {
    document.documentElement.className = theme;
    localStorage.setItem('theme', theme);
  }, [theme]);

  return (
    <motion.button 
      whileHover={{ scale: 1.05 }}
      whileTap={{ scale: 0.95 }}
      onClick={() => setTheme(t => t === 'dark' ? 'light' : 'dark')}
      className="p-2 rounded-full backdrop-blur-md bg-white/10"
    >
      {theme === 'dark' ? '\uD83C\uDF19' : '\u2600\uFE0F'}
    </motion.button>
  );
}
`;

export function LiveStreamEditor({ filename = "components/ThemeToggle.tsx", isStreaming = true }: LiveStreamEditorProps) {
    const [displayedCode, setDisplayedCode] = useState("");
    const contentRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (!isStreaming) {
            setDisplayedCode(DUMMY_CODE);
            return;
        }

        setDisplayedCode("");
        let currentIndex = 0;

        // Simulate typing effect
        const interval = setInterval(() => {
            if (currentIndex < DUMMY_CODE.length) {
                setDisplayedCode(prev => prev + DUMMY_CODE.charAt(currentIndex));
                currentIndex++;

                // Auto-scroll to bottom
                if (contentRef.current) {
                    contentRef.current.scrollTop = contentRef.current.scrollHeight;
                }
            } else {
                clearInterval(interval);
            }
        }, 15); // Adjust speed here

        return () => clearInterval(interval);
    }, [isStreaming]);

    // Very basic syntax highlighting for demo purposes
    const highlightCode = (code: string) => {
        return code
            .replace(/import|from|export|function|const|let|var|return|if|else/g, match => `<span class="text-[var(--color-accent)] font-bold">${match}</span>`)
            .replace(/useState|useEffect|motion/g, match => `<span class="text-[var(--color-info)]">${match}</span>`)
            .replace(/'[^']*'/g, match => `<span class="text-[var(--color-success)]">${match}</span>`)
            .replace(/<[^>]+>/g, match => `<span class="text-[var(--color-warning)]">${match.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</span>`);
    };

    return (
        <div className="flex flex-col w-full h-full bg-[#0D1117] rounded-xl border border-[var(--color-border-subtle)] overflow-hidden shadow-2xl relative">

            {/* Editor Header / Tabs */}
            <div className="flex bg-[#010409] border-b border-[var(--color-border-subtle)]">
                <div className="flex items-center px-4 py-2 border-r border-b border-b-transparent border-r-[var(--color-border-subtle)] bg-[#0D1117] gap-2">
                    <svg className="w-3.5 h-3.5 text-[var(--color-info)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" /></svg>
                    <span className="text-xs font-mono font-medium text-[var(--color-text-primary)]">{filename}</span>
                    {isStreaming && (
                        <span className="w-2 h-2 rounded-full bg-[var(--color-success)] shadow-[0_0_8px_var(--color-success)] animate-pulse" />
                    )}
                </div>
            </div>

            {/* Editor Content Area */}
            <div
                ref={contentRef}
                className="flex-1 overflow-auto p-4 font-mono text-sm leading-relaxed"
            >
                <div className="flex">
                    {/* Line Numbers */}
                    <div className="flex flex-col text-right pr-4 text-[#484F58] select-none border-r border-[#30363D] font-mono text-xs pt-[3px]">
                        {displayedCode.split('\n').map((_, i) => (
                            <span key={i} className="leading-relaxed">{i + 1}</span>
                        ))}
                    </div>

                    {/* Actual Code View */}
                    <pre className="pl-4 m-0 overflow-visible text-[#E6EDF3] whitespace-pre-wrap word-break">
                        <code dangerouslySetInnerHTML={{ __html: highlightCode(displayedCode) }} />
                        {isStreaming && <motion.span animate={{ opacity: [1, 0, 1] }} transition={{ repeat: Infinity, duration: 0.8 }} className="inline-block w-2.5 h-4 bg-[var(--color-text-primary)] ml-1 translate-y-[3px]" />}
                    </pre>
                </div>
            </div>

            {/* Editor Footer / Status */}
            <div className="bg-[#010409] border-t border-[var(--color-border-subtle)] px-4 py-1.5 flex items-center justify-between text-[#8B949E] text-[10px] uppercase font-bold tracking-widest font-mono">
                <div className="flex items-center gap-4">
                    <span className="flex items-center gap-1.5">
                        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                        Live Sync
                    </span>
                    <span>UTF-8</span>
                    <span>TypeScript React</span>
                </div>
                <div>
                    {displayedCode.split('\n').length} Ln, {displayedCode.length} Ch
                </div>
            </div>
        </div>
    );
}
