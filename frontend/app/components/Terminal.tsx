"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { Terminal as XTerm } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { SearchAddon } from "@xterm/addon-search";
import "@xterm/xterm/css/xterm.css";
import { FAILURE_MODES, FAILURE_MODE_PATTERN, type FailureMode } from "../utils/failureModes";

interface TerminalProps {
  output: string[];
  status: string;
  onSteer: (message: string, type: string) => void;
  wsConnected?: boolean;
  isOverlay?: boolean;
  onCloseOverlay?: () => void;
}

/* ── ANSI color helpers for line classification ── */
const ANSI = {
  orange: "\x1b[38;2;249;115;22m",   // accent / tool-use
  green: "\x1b[38;2;63;185;80m",     // success / tool-done
  red: "\x1b[38;2;248;81;73m",       // error / tool-error
  yellow: "\x1b[38;2;210;153;34m",   // warning / tool-blocked
  magenta: "\x1b[35m",               // failure mode codes
  reset: "\x1b[0m",
};

/** Highlight any failure mode codes in magenta within a line */
function highlightFailureCodes(line: string): string {
  // Reset the regex lastIndex for each call since it's global
  FAILURE_MODE_PATTERN.lastIndex = 0;
  return line.replace(FAILURE_MODE_PATTERN, (match) =>
    `${ANSI.magenta}${match}${ANSI.reset}`
  );
}

function colorize(line: string): string {
  let colored: string;
  if (line.startsWith("[Tool:")) colored = `${ANSI.orange}${line}${ANSI.reset}`;
  else if (line.includes("[Done]")) colored = `${ANSI.green}${line}${ANSI.reset}`;
  else if (line.includes("[Error]") || line.startsWith("Error")) colored = `${ANSI.red}${line}${ANSI.reset}`;
  else if (line.includes("[BLOCKED]")) colored = `${ANSI.yellow}${line}${ANSI.reset}`;
  else colored = line;
  return highlightFailureCodes(colored);
}

/** Extract failure mode codes found in a single line */
function extractFailureCodes(line: string): string[] {
  FAILURE_MODE_PATTERN.lastIndex = 0;
  const matches = line.match(FAILURE_MODE_PATTERN);
  return matches ? [...new Set(matches)] : [];
}

/** Scroll xterm viewport to bottom after layout (double rAF for reliability) */
function scheduleScrollToBottom(term: XTerm): void {
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      try { term.scrollToBottom(); } catch { /* ignore */ }
    });
  });
}

export function Terminal({ output, status, onSteer, wsConnected, isOverlay = false, onCloseOverlay }: TerminalProps) {
  /* ── Refs ── */
  const termContainerRef = useRef<HTMLDivElement>(null);
  const xtermRef = useRef<XTerm | null>(null);
  const fitAddonRef = useRef<FitAddon | null>(null);
  const searchAddonRef = useRef<SearchAddon | null>(null);
  const writtenCountRef = useRef(0);

  /* ── Detected failure modes ── */
  const [detectedFailures, setDetectedFailures] = useState<FailureMode[]>([]);

  /* ── Steering state ── */
  const [steerMessage, setSteerMessage] = useState("");
  const [steerType, setSteerType] = useState("instruction");

  /* ── Search state ── */
  const [showSearch, setShowSearch] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [matchInfo, setMatchInfo] = useState({ index: -1, count: 0 });
  const searchInputRef = useRef<HTMLInputElement>(null);

  /* ── Copy state ── */
  const [copied, setCopied] = useState(false);

  /* ── Initialize xterm ── */
  useEffect(() => {
    if (!termContainerRef.current) return;

    const term = new XTerm({
      allowTransparency: false,
      theme: {
        background: "#050508",
        foreground: "#f0f2f5",
        cursor: "#f97316",
        cursorAccent: "#06080d",
        selectionBackground: "rgba(249, 115, 22, 0.3)",
        selectionForeground: "#f0f2f5",
        black: "#06080d",
        red: "#f85149",
        green: "#3fb950",
        yellow: "#d29922",
        blue: "#58a6ff",
        magenta: "#bc8cff",
        cyan: "#06b6d4",
        white: "#f0f2f5",
        brightBlack: "#484f58",
        brightRed: "#f85149",
        brightGreen: "#3fb950",
        brightYellow: "#d29922",
        brightBlue: "#58a6ff",
        brightMagenta: "#bc8cff",
        brightCyan: "#06b6d4",
        brightWhite: "#f0f2f5",
      },
      fontFamily: "'JetBrains Mono', ui-monospace, 'Cascadia Code', 'Fira Code', monospace",
      fontSize: 13,
      lineHeight: 1.3,
      scrollback: 5000,
      cursorBlink: false,
      cursorStyle: "bar",
      cursorInactiveStyle: "none",
      disableStdin: true,
      convertEol: true,
      allowProposedApi: true,
    });

    const fitAddon = new FitAddon();
    const searchAddon = new SearchAddon();

    term.loadAddon(fitAddon);
    term.loadAddon(searchAddon);

    term.open(termContainerRef.current);

    // Initial fit after a small delay to ensure the container has dimensions
    requestAnimationFrame(() => {
      try {
        fitAddon.fit();
      } catch {
        // Container might not be visible yet
      }
    });

    xtermRef.current = term;
    fitAddonRef.current = fitAddon;
    searchAddonRef.current = searchAddon;
    writtenCountRef.current = 0;

    // Listen for search result changes
    searchAddon.onDidChangeResults((e) => {
      setMatchInfo({ index: e.resultIndex, count: e.resultCount });
    });

    // ResizeObserver to auto-fit on container resize
    const resizeObserver = new ResizeObserver(() => {
      requestAnimationFrame(() => {
        try {
          fitAddon.fit();
        } catch {
          // Ignore fit errors when container is hidden
        }
      });
    });
    resizeObserver.observe(termContainerRef.current);

    return () => {
      resizeObserver.disconnect();
      searchAddon.dispose();
      fitAddon.dispose();
      term.dispose();
      xtermRef.current = null;
      fitAddonRef.current = null;
      searchAddonRef.current = null;
      writtenCountRef.current = 0;
    };
  }, []);

  /* ── Periodic scroll-to-bottom while running (safety net for reliable auto-scroll) ── */
  useEffect(() => {
    if (status !== "running") return;
    const term = xtermRef.current;
    if (!term) return;
    const interval = setInterval(() => {
      try { xtermRef.current?.scrollToBottom(); } catch { /* ignore */ }
    }, 1500);
    return () => clearInterval(interval);
  }, [status]);

  /* ── Write new output lines incrementally (skip empty lines) ── */
  useEffect(() => {
    const term = xtermRef.current;
    if (!term) return;

    const alreadyWritten = writtenCountRef.current;
    const newCodes: string[] = [];

    // Handle full output reset (e.g. new session)
    if (output.length < alreadyWritten) {
      term.clear();
      writtenCountRef.current = 0;
      setDetectedFailures([]);
      const resetCodes: string[] = [];
      for (let i = 0; i < output.length; i++) {
        const line = output[i];
        if (line.trim() === "") continue;
        term.writeln(colorize(line));
        resetCodes.push(...extractFailureCodes(line));
      }
      writtenCountRef.current = output.length;
      if (resetCodes.length > 0) {
        const unique = [...new Set(resetCodes)];
        setDetectedFailures(unique.map(c => FAILURE_MODES[c]).filter(Boolean));
      }
      scheduleScrollToBottom(term);
      return;
    }

    // Write only new lines
    if (output.length > alreadyWritten) {
      for (let i = alreadyWritten; i < output.length; i++) {
        const line = output[i];
        if (line.trim() === "") continue;
        term.writeln(colorize(line));
        newCodes.push(...extractFailureCodes(line));
      }
      writtenCountRef.current = output.length;
      // Ensure viewport scrolls to bottom after DOM update (fixes intermittent auto-scroll stop)
      scheduleScrollToBottom(term);
    }

    // Append any newly detected failure modes
    if (newCodes.length > 0) {
      setDetectedFailures(prev => {
        const existingCodes = new Set(prev.map(f => f.code));
        const added = [...new Set(newCodes)]
          .filter(c => !existingCodes.has(c))
          .map(c => FAILURE_MODES[c])
          .filter(Boolean);
        return added.length > 0 ? [...prev, ...added] : prev;
      });
    }
  }, [output]);

  /* ── Search: Ctrl+F keyboard shortcut ── */
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "f") {
        e.preventDefault();
        setShowSearch(true);
        setTimeout(() => searchInputRef.current?.focus(), 0);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  /* ── Search: run search when query changes ── */
  useEffect(() => {
    const addon = searchAddonRef.current;
    if (!addon) return;

    if (!searchQuery.trim()) {
      addon.clearDecorations();
      setMatchInfo({ index: -1, count: 0 });
      return;
    }
    addon.findNext(searchQuery, {
      incremental: true,
      decorations: {
        matchBackground: "#d2992233",
        matchBorder: "#d29922",
        matchOverviewRuler: "#d29922",
        activeMatchBackground: "#f9731666",
        activeMatchBorder: "#f97316",
        activeMatchColorOverviewRuler: "#f97316",
      },
    });
  }, [searchQuery]);

  const navigateSearch = useCallback(
    (direction: "next" | "prev") => {
      const addon = searchAddonRef.current;
      if (!addon || !searchQuery.trim()) return;
      const opts = {
        decorations: {
          matchBackground: "#d2992233",
          matchBorder: "#d29922",
          matchOverviewRuler: "#d29922",
          activeMatchBackground: "#f9731666",
          activeMatchBorder: "#f97316",
          activeMatchColorOverviewRuler: "#f97316",
        },
      };
      if (direction === "next") {
        addon.findNext(searchQuery, opts);
      } else {
        addon.findPrevious(searchQuery, opts);
      }
    },
    [searchQuery]
  );

  const closeSearch = useCallback(() => {
    setShowSearch(false);
    setSearchQuery("");
    searchAddonRef.current?.clearDecorations();
    setMatchInfo({ index: -1, count: 0 });
  }, []);

  /* ── Copy all output ── */
  const handleCopy = useCallback(() => {
    // If there's a selection in the terminal, copy just that
    const term = xtermRef.current;
    const selection = term?.getSelection();
    const textToCopy = selection ? selection : output.join("\n");
    navigator.clipboard.writeText(textToCopy).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }).catch(() => {
      // Clipboard API not available (e.g. non-HTTPS)
    });
  }, [output]);

  const overlayClasses = isOverlay
    ? "fixed inset-0 z-50 flex flex-col bg-black/80 backdrop-blur-sm"
    : "";

  return (
    <div className={isOverlay ? overlayClasses : "flex flex-col h-full rounded-2xl border border-[var(--color-border-subtle)] bg-[#050508] backdrop-blur-2xl shadow-xl overflow-hidden terminal-crt relative"}>
      {isOverlay && (
        <div className="absolute inset-0 pointer-events-none z-0" onClick={onCloseOverlay} />
      )}
      <div className={`flex flex-col ${isOverlay ? "relative z-10 m-4 flex-1 min-h-0 rounded-2xl border border-[var(--color-border-subtle)] bg-[#050508] shadow-2xl overflow-hidden" : "h-full"}`}>
      <div className="absolute inset-0 pointer-events-none rounded-2xl shadow-[inset_0_0_60px_rgba(0,0,0,0.8)] z-10" />
      {/* Terminal header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-[var(--color-border-subtle)] bg-[var(--color-surface-1)]/40 backdrop-blur-md">
        <div className="flex gap-1.5" aria-hidden="true">
          <div className="w-3 h-3 rounded-full bg-[var(--color-error)]/80 shadow-[0_0_8px_var(--color-error)]" />
          <div className="w-3 h-3 rounded-full bg-[var(--color-warning)]/80 shadow-[0_0_8px_var(--color-warning)]" />
          <div className="w-3 h-3 rounded-full bg-[var(--color-success)]/80 shadow-[0_0_8px_var(--color-success)]" />
        </div>
        <span className="text-xs text-[var(--color-text-muted)] font-mono ml-2 font-medium tracking-wide">
          SwarmWeaver Agent Output
        </span>
        <span className="text-xs text-[var(--color-text-muted)] font-mono opacity-70">
          {output.length} lines
        </span>

        <div className="ml-auto flex items-center gap-2">
          {/* Copy button */}
          <button
            onClick={handleCopy}
            className="text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors px-2 py-1 rounded-md border border-[var(--color-border-subtle)] hover:border-[var(--color-border-default)] bg-[var(--color-surface-2)] shadow-sm"
            aria-label={copied ? "Output copied to clipboard" : "Copy terminal output"}
            title="Copy output"
          >
            {copied ? "Copied!" : "Copy"}
          </button>

          {/* Status indicators */}
          {status === "running" && (
            <span className="flex items-center gap-1.5 text-xs text-[var(--color-success)] font-medium" role="status" aria-label="Agent is running">
              <span className="w-2 h-2 rounded-full bg-[var(--color-success)] animate-pulse-dot shadow-[0_0_8px_var(--color-success)]" aria-hidden="true" />
              Running
            </span>
          )}
          {status === "completed" && (
            <span className="text-xs text-[var(--color-text-muted)] font-medium">Completed</span>
          )}
          {/* Close button for overlay mode */}
          {isOverlay && onCloseOverlay && (
            <button
              onClick={onCloseOverlay}
              className="text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors px-2 py-1 rounded-md border border-[var(--color-border-subtle)] hover:border-[var(--color-border-default)] bg-[var(--color-surface-2)] shadow-sm"
              aria-label="Close terminal overlay"
              title="Close (Ctrl+T)"
            >
              Close
            </button>
          )}
        </div>
      </div>

      {/* Reconnecting bar */}
      {wsConnected === false && status === "running" && (
        <div className="px-3 py-1 bg-[var(--color-warning)]/20 border-b border-[var(--color-warning)]/30 text-xs text-[var(--color-warning)] font-medium flex items-center gap-1.5 backdrop-blur-sm">
          <span className="w-2 h-2 rounded-full bg-[var(--color-warning)] animate-pulse shadow-[0_0_8px_var(--color-warning)]" />
          Reconnecting...
        </div>
      )}

      {/* Search bar */}
      {showSearch && (
        <div className="flex items-center gap-2 px-3 py-1.5 border-b border-[var(--color-border-subtle)] bg-[var(--color-surface-1)]/50 backdrop-blur-md">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="12"
            height="12"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="text-text-muted shrink-0"
            aria-hidden="true"
          >
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            ref={searchInputRef}
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                navigateSearch(e.shiftKey ? "prev" : "next");
              }
              if (e.key === "Escape") {
                closeSearch();
              }
            }}
            placeholder="Search output..."
            className="flex-1 bg-transparent text-xs text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] focus:outline-none"
          />
          {searchQuery.trim() && (
            <span className="text-xs text-[var(--color-text-muted)] whitespace-nowrap">
              {matchInfo.count > 0
                ? `${matchInfo.index + 1} of ${matchInfo.count} matches`
                : "0 matches"}
            </span>
          )}
          <button
            onClick={() => navigateSearch("prev")}
            disabled={matchInfo.count === 0}
            className="text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] disabled:opacity-30 transition-colors"
            aria-label="Previous match"
            title="Previous match (Shift+Enter)"
          >
            <svg aria-hidden="true" xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="18 15 12 9 6 15" /></svg>
          </button>
          <button
            onClick={() => navigateSearch("next")}
            disabled={matchInfo.count === 0}
            className="text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] disabled:opacity-30 transition-colors"
            aria-label="Next match"
            title="Next match (Enter)"
          >
            <svg aria-hidden="true" xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="6 9 12 15 18 9" /></svg>
          </button>
          <button
            onClick={closeSearch}
            className="text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors"
            aria-label="Close search"
            title="Close (Escape)"
          >
            <svg aria-hidden="true" xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
          </button>
        </div>
      )}

      {/* xterm.js terminal container */}
      <div
        ref={termContainerRef}
        className="flex-1 min-h-0 overflow-hidden"
        style={{ minHeight: "200px", padding: "8px 4px" }}
      />

      {/* Detected failure modes panel */}
      {detectedFailures.length > 0 && (
        <div className="border-t border-[var(--color-border-subtle)] bg-[var(--color-surface-1)]/60 backdrop-blur-md px-3 py-2 max-h-32 overflow-y-auto">
          <div className="text-[10px] text-[var(--color-text-muted)] font-semibold uppercase tracking-wider mb-1">
            Detected Failure Modes ({detectedFailures.length})
          </div>
          <div className="space-y-1">
            {detectedFailures.map((fm) => (
              <div key={fm.code} className="flex items-start gap-2 text-xs">
                <span className={`shrink-0 px-1.5 py-0.5 rounded font-mono text-[10px] font-semibold ${
                  fm.severity === 'critical' ? 'bg-red-600 text-white' :
                  fm.severity === 'high' ? 'bg-orange-500 text-white' :
                  fm.severity === 'medium' ? 'bg-yellow-500 text-black' :
                  'bg-blue-500 text-white'
                }`}>
                  {fm.code}
                </span>
                <span className="text-[var(--color-text-muted)]">{fm.recovery}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Steering is handled by the FloatingActionBar at the bottom */}
      </div>
    </div>
  );
}
