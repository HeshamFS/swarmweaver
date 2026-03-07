"use client";

import { Command } from "cmdk";
import { useState, useEffect, useCallback } from "react";

/* ── Mode badge colors (mirrors TabBar.tsx) ── */
const MODE_COLORS: Record<string, string> = {
  greenfield: "bg-mode-greenfield/15 text-mode-greenfield border-mode-greenfield/30",
  feature: "bg-mode-feature/15 text-mode-feature border-mode-feature/30",
  refactor: "bg-mode-refactor/15 text-mode-refactor border-mode-refactor/30",
  fix: "bg-mode-fix/15 text-mode-fix border-mode-fix/30",
  evolve: "bg-mode-evolve/15 text-mode-evolve border-mode-evolve/30",
  security: "bg-mode-security/15 text-mode-security border-mode-security/30",
};

interface CommandPaletteProps {
  /** Callback to navigate to a route */
  onNavigate?: (path: string) => void;
  /** Callback to execute a named action */
  onAction?: (action: string) => void;
  /** List of recent projects to show in the palette */
  projects?: Array<{ name: string; path: string; mode?: string }>;
  /** Whether the agent is currently running (controls Stop/Start visibility) */
  isAgentRunning?: boolean;
}

export function CommandPalette({
  onNavigate,
  onAction,
  projects = [],
  isAgentRunning = false,
}: CommandPaletteProps) {
  const [open, setOpen] = useState(false);

  /* ── Global keyboard shortcut: Ctrl+K / Cmd+K ── */
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, []);

  /* ── Helpers ── */
  const runAction = useCallback(
    (action: string) => {
      setOpen(false);
      onAction?.(action);
    },
    [onAction],
  );

  const navigate = useCallback(
    (path: string) => {
      setOpen(false);
      onNavigate?.(path);
    },
    [onNavigate],
  );

  return (
    <Command.Dialog
      open={open}
      onOpenChange={setOpen}
      label="Command palette"
      loop
      overlayClassName="fixed inset-0 z-50 bg-black/60 backdrop-blur-md transition-all duration-300"
      contentClassName="fixed inset-0 z-50 flex items-start justify-center pt-[15vh] pb-[15vh] px-4"
    >
      {/* Dialog content card */}
      <div className="w-full max-w-2xl rounded-2xl border border-[var(--color-border-subtle)] bg-[var(--color-surface-glass)] backdrop-blur-2xl shadow-[0_30px_100px_-20px_rgba(0,0,0,0.8)] overflow-hidden transition-all duration-300 transform scale-100 opacity-100">
        {/* ── Search input ── */}
        <div className="flex items-center gap-3 px-5 py-2 border-b border-[var(--color-border-subtle)] bg-[var(--color-surface-1)]/30 backdrop-blur-sm">
          <svg
            className="w-5 h-5 text-[var(--color-text-muted)] shrink-0"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2.5}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>
          <Command.Input
            placeholder="Search actions, projects, settings..."
            className="flex-1 h-14 bg-transparent text-base text-[var(--color-text-primary)] font-medium placeholder:text-[var(--color-text-muted)] focus:outline-none border-none ring-0 w-full"
          />
          <kbd className="shrink-0 text-[10px] px-2 py-1 rounded border border-[var(--color-border-default)] bg-[var(--color-surface-2)] text-[var(--color-text-secondary)] font-mono">Esc</kbd>
        </div>

        {/* ── Results list ── */}
        <Command.List className="max-h-[350px] overflow-y-auto p-3 !scroll-smooth pb-0">
          <Command.Empty className="text-center text-[var(--color-text-muted)] text-sm py-12">
            No results found.
          </Command.Empty>

          {/* ── Agent Actions ── */}
          <Command.Group
            heading="Agent Actions"
            className="[&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:text-[var(--color-text-muted)] [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-widest [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-2 [&_[cmdk-group-heading]]:font-bold mb-2"
          >
            {!isAgentRunning && (
              <Command.Item
                value="start-agent"
                onSelect={() => runAction("start-agent")}
                className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-[var(--color-text-primary)] cursor-pointer transition-all duration-200 data-[selected=true]:bg-[var(--color-surface-3)] data-[selected=true]:text-[var(--color-accent)] data-[selected=true]:shadow-[0_4px_12px_rgba(0,0,0,0.1)] outline-none"
              >
                <span className="w-6 h-6 flex items-center justify-center rounded-md bg-[var(--color-surface-2)] text-[var(--color-accent)] shadow-sm">&#9654;</span>
                <span className="flex-1 font-medium">Start Agent</span>
                <kbd className="text-[10px] px-2 py-0.5 rounded border border-[var(--color-border-subtle)] text-[var(--color-text-muted)]">Enter</kbd>
              </Command.Item>
            )}
            {isAgentRunning && (
              <Command.Item
                value="stop-agent"
                onSelect={() => runAction("stop-agent")}
                className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-[var(--color-text-primary)] cursor-pointer transition-all duration-200 data-[selected=true]:bg-[var(--color-error)]/10 data-[selected=true]:text-[var(--color-error)] outline-none"
              >
                <span className="w-6 h-6 flex items-center justify-center rounded-md bg-[var(--color-surface-2)] text-[var(--color-error)] shadow-sm">&#9632;</span>
                <span className="flex-1 font-medium">Stop Agent</span>
                <kbd className="text-[10px] px-2 py-0.5 rounded border border-[var(--color-border-subtle)] text-[var(--color-text-muted)]">Ctrl+Q</kbd>
              </Command.Item>
            )}
            <Command.Item
              value="reset-session"
              onSelect={() => runAction("reset-session")}
              className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-[var(--color-text-primary)] cursor-pointer transition-all duration-200 data-[selected=true]:bg-[var(--color-surface-3)] outline-none"
            >
              <span className="w-6 h-6 flex items-center justify-center rounded-md bg-[var(--color-surface-2)] text-[var(--color-text-secondary)] shadow-sm">&#8634;</span>
              <span className="flex-1 font-medium">Reset Session</span>
            </Command.Item>
          </Command.Group>

          <Command.Separator className="h-px bg-[var(--color-border-subtle)] mx-2 my-2" />

          {/* ── Navigation ── */}
          <Command.Group
            heading="Navigation"
            className="[&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:text-[var(--color-text-muted)] [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-widest [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-2 [&_[cmdk-group-heading]]:font-bold mb-2"
          >
            <Command.Item
              value="dashboard"
              onSelect={() => navigate("/")}
              className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-[var(--color-text-primary)] cursor-pointer transition-all duration-200 data-[selected=true]:bg-[var(--color-surface-3)] outline-none"
            >
              <span className="w-6 h-6 flex items-center justify-center rounded-md bg-[var(--color-surface-2)] text-[var(--color-text-secondary)] shadow-sm">&#9632;</span>
              <span className="flex-1 font-medium">Dashboard</span>
            </Command.Item>
            <Command.Item
              value="settings"
              onSelect={() => navigate("/settings")}
              className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-[var(--color-text-primary)] cursor-pointer transition-all duration-200 data-[selected=true]:bg-[var(--color-surface-3)] outline-none"
            >
              <span className="w-6 h-6 flex items-center justify-center rounded-md bg-[var(--color-surface-2)] text-[var(--color-text-secondary)] shadow-sm">&#9881;</span>
              <span className="flex-1 font-medium">Settings</span>
            </Command.Item>
            <Command.Item
              value="session-replay"
              onSelect={() => navigate("/replay")}
              className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-[var(--color-text-primary)] cursor-pointer transition-all duration-200 data-[selected=true]:bg-[var(--color-surface-3)] outline-none"
            >
              <span className="w-6 h-6 flex items-center justify-center rounded-md bg-[var(--color-surface-2)] text-[var(--color-text-secondary)] shadow-sm">&#9654;&#9654;</span>
              <span className="flex-1 font-medium">Session Replay</span>
            </Command.Item>
          </Command.Group>

          {/* ── Recent Projects (only shown if projects are provided) ── */}
          {projects.length > 0 && (
            <>
              <Command.Separator className="h-px bg-[var(--color-border-subtle)] mx-2 my-2" />
              <Command.Group
                heading="Recent Projects"
                className="[&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:text-[var(--color-text-muted)] [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-widest [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-2 [&_[cmdk-group-heading]]:font-bold mb-2"
              >
                {projects.map((project) => (
                  <Command.Item
                    key={project.path}
                    value={`project-${project.name}`}
                    keywords={[project.name, project.path, project.mode || ""]}
                    onSelect={() => runAction(`open-project:${project.path}`)}
                    className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-[var(--color-text-primary)] cursor-pointer transition-all duration-200 data-[selected=true]:bg-[var(--color-surface-3)] outline-none"
                  >
                    <span className="w-6 h-6 flex items-center justify-center rounded-md bg-[var(--color-surface-2)] text-[var(--color-info)] shadow-sm">&#128193;</span>
                    <span className="flex-1 font-medium truncate">{project.name}</span>
                    {project.mode && (
                      <span
                        className={`text-[9px] font-bold px-2 py-0.5 rounded-md border ${MODE_COLORS[project.mode] || "text-[var(--color-text-muted)] border-[var(--color-border-subtle)]"
                          }`}
                      >
                        {project.mode}
                      </span>
                    )}
                  </Command.Item>
                ))}
              </Command.Group>
            </>
          )}

          <Command.Separator className="h-px bg-[var(--color-border-subtle)] mx-2 my-2" />

          {/* ── Quick Actions ── */}
          <Command.Group
            heading="Quick Actions"
            className="[&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:text-[var(--color-text-muted)] [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-widest [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-2 [&_[cmdk-group-heading]]:font-bold mb-2"
          >
            <Command.Item
              value="toggle-right-panel"
              onSelect={() => runAction("toggle-right-panel")}
              className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-[var(--color-text-primary)] cursor-pointer transition-all duration-200 data-[selected=true]:bg-[var(--color-surface-3)] outline-none"
            >
              <span className="w-6 h-6 flex items-center justify-center rounded-md bg-[var(--color-surface-2)] text-[var(--color-text-secondary)] shadow-sm">&#9776;</span>
              <span className="flex-1 font-medium">Toggle Right Panel</span>
              <kbd className="text-[10px] px-2 py-0.5 rounded border border-[var(--color-border-subtle)] text-[var(--color-text-muted)]">Ctrl+B</kbd>
            </Command.Item>
            <Command.Item
              value="toggle-cli-mode"
              onSelect={() => runAction("toggle-cli-mode")}
              className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-[var(--color-text-primary)] cursor-pointer transition-all duration-200 data-[selected=true]:bg-[var(--color-surface-3)] outline-none"
            >
              <span className="w-6 h-6 flex items-center justify-center rounded-md bg-[var(--color-surface-2)] text-[var(--color-text-secondary)] shadow-sm">&gt;_</span>
              <span className="flex-1 font-medium">Toggle CLI Mode</span>
            </Command.Item>
            <Command.Item
              value="keyboard-shortcuts"
              onSelect={() => runAction("keyboard-shortcuts")}
              className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-[var(--color-text-primary)] cursor-pointer transition-all duration-200 data-[selected=true]:bg-[var(--color-surface-3)] outline-none"
            >
              <span className="w-6 h-6 flex items-center justify-center rounded-md bg-[var(--color-surface-2)] text-[var(--color-text-secondary)] shadow-sm">&#9000;</span>
              <span className="flex-1 font-medium">Keyboard Shortcuts</span>
              <kbd className="text-[10px] px-2 py-0.5 rounded border border-[var(--color-border-subtle)] text-[var(--color-text-muted)]">?</kbd>
            </Command.Item>
          </Command.Group>
        </Command.List>

        {/* ── Footer hint ── */}
        <div className="flex items-center justify-between px-5 py-3 border-t border-[var(--color-border-subtle)] bg-[var(--color-surface-1)]/30 backdrop-blur-md text-[10px] text-[var(--color-text-muted)] font-medium">
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1.5">
              <kbd className="px-1.5 py-0.5 rounded border border-[var(--color-border-subtle)] bg-[var(--color-surface-2)]">&uarr;&darr;</kbd> navigate
            </span>
            <span className="flex items-center gap-1.5">
              <kbd className="px-1.5 py-0.5 rounded border border-[var(--color-border-subtle)] bg-[var(--color-surface-2)]">&crarr;</kbd> select
            </span>
            <span className="flex items-center gap-1.5">
              <kbd className="px-1.5 py-0.5 rounded border border-[var(--color-border-subtle)] bg-[var(--color-surface-2)]">Esc</kbd> close
            </span>
          </div>
          <span className="font-bold tracking-wider uppercase text-[var(--color-accent)] opacity-80">SwarmWeaver</span>
        </div>
      </div>
    </Command.Dialog>
  );
}
