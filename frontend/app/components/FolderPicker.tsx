"use client";

import { useState, useEffect, useCallback, useRef } from "react";

const GLOBAL_SETTINGS_KEY = "swarmweaver-global-settings";
const LAST_BROWSE_PATH_KEY = "swarmweaver-last-browse-path";

interface DirEntry {
  name: string;
  path: string;
  is_dir: boolean;
}

interface FolderPickerProps {
  onSelect: (path: string) => void;
  onClose: () => void;
}

function getInitialPath(): string {
  if (typeof window === "undefined") return "/";
  try {
    const defaultPath =
      (JSON.parse(localStorage.getItem(GLOBAL_SETTINGS_KEY) || "{}") as { defaultBrowsePath?: string | null })
        ?.defaultBrowsePath?.trim() || "";
    const lastPath = localStorage.getItem(LAST_BROWSE_PATH_KEY)?.trim() || "";
    return defaultPath || lastPath || "/";
  } catch {
    return "/";
  }
}

function saveLastBrowsePath(path: string): void {
  try {
    localStorage.setItem(LAST_BROWSE_PATH_KEY, path);
  } catch {
    /* ignore */
  }
}

export function FolderPicker({ onSelect, onClose }: FolderPickerProps) {
  const [entries, setEntries] = useState<DirEntry[]>([]);
  const [current, setCurrent] = useState("");
  const [error, setError] = useState("");
  const [pathInput, setPathInput] = useState("");
  const [creatingFolder, setCreatingFolder] = useState(false);
  const [newFolderName, setNewFolderName] = useState("");
  const [createError, setCreateError] = useState("");
  const newFolderRef = useRef<HTMLInputElement>(null);

  const browse = useCallback(async (path: string): Promise<{ current?: string; error?: string }> => {
    try {
      const res = await fetch(
        `/api/browse?path=${encodeURIComponent(path)}`
      );
      const data = await res.json();
      if (data.error) {
        setError(data.error);
        return { error: data.error };
      }
      setError("");
      setEntries(data.entries || []);
      const resolved = data.current || path;
      setCurrent(resolved);
      setPathInput(resolved);
      return { current: resolved };
    } catch {
      setError("Failed to connect to backend");
      return { error: "Failed to connect to backend" };
    }
  }, []);

  useEffect(() => {
    const initialPath = getInitialPath();
    browse(initialPath).then((result) => {
      if (result.error && initialPath !== "/") {
        browse("/");
      }
    });
  }, [browse]);

  const handleNavigate = (path: string) => {
    setCreatingFolder(false);
    browse(path).then((result) => {
      if (result.current) {
        saveLastBrowsePath(result.current);
      }
    });
  };

  const handlePathSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    browse(pathInput).then((r) => {
      if (r.current) saveLastBrowsePath(r.current);
    });
  };

  const handleCreateFolder = async () => {
    const name = newFolderName.trim();
    if (!name) return;
    setCreateError("");

    try {
      const res = await fetch("/api/mkdir", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ parent: current, name }),
      });
      const data = await res.json();
      if (data.error) {
        setCreateError(data.error);
        return;
      }
      // Refresh the current directory and navigate into the new folder
      setCreatingFolder(false);
      setNewFolderName("");
      browse(data.path).then((r) => r.current && saveLastBrowsePath(r.current));
    } catch {
      setCreateError("Failed to create folder.");
    }
  };

  const handleNewFolderKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleCreateFolder();
    } else if (e.key === "Escape") {
      setCreatingFolder(false);
      setNewFolderName("");
      setCreateError("");
    }
  };

  // Auto-focus the new folder input when it appears
  useEffect(() => {
    if (creatingFolder && newFolderRef.current) {
      newFolderRef.current.focus();
    }
  }, [creatingFolder]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80">
      <div className="w-[600px] max-h-[500px] flex flex-col border border-[#333] bg-[#0C0C0C] shadow-2xl font-mono text-sm">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#222] bg-[#121212]">
          <h3 className="text-xs font-bold text-[#E0E0E0] uppercase tracking-wider">
            {"\u25A0"} Select Folder
          </h3>
          <button
            onClick={onClose}
            className="text-[#555] hover:text-[var(--color-accent)] text-sm leading-none transition-colors"
          >
            {"\u2717"}
          </button>
        </div>

        {/* Quick nav + Path input */}
        <div className="flex items-center gap-1.5 px-4 py-1.5 border-b border-[#222] bg-[#0C0C0C]">
          <button
            type="button"
            onClick={() => browse("/").then((r) => r.current && saveLastBrowsePath(r.current))}
            className="px-2 py-0.5 text-[10px] font-mono text-[#888] hover:text-[#E0E0E0] hover:border-[#555] border border-[#333] bg-[#121212] transition-colors shrink-0"
            title="Filesystem root"
          >
            /
          </button>
          <button
            type="button"
            onClick={() => browse("").then((r) => r.current && saveLastBrowsePath(r.current))}
            className="px-2 py-0.5 text-[10px] font-mono text-[#888] hover:text-[#E0E0E0] hover:border-[#555] border border-[#333] bg-[#121212] transition-colors shrink-0"
            title="Home directory"
          >
            Home
          </button>
          <button
            type="button"
            onClick={() => browse("/mnt").then((r) => r.current && saveLastBrowsePath(r.current))}
            className="px-2 py-0.5 text-[10px] font-mono text-[#888] hover:text-[#E0E0E0] hover:border-[#555] border border-[#333] bg-[#121212] transition-colors shrink-0"
            title="Drives (WSL)"
          >
            Drives
          </button>
          <div className="flex-1" />
          <button
            type="button"
            onClick={() => { setCreatingFolder(true); setCreateError(""); setNewFolderName(""); }}
            className="px-2 py-0.5 text-[10px] font-bold font-mono text-[var(--color-accent)] hover:bg-[var(--color-accent)]/10 border border-[var(--color-accent)]/30 transition-colors shrink-0"
            title="Create a new folder here"
          >
            + New Folder
          </button>
        </div>
        <form
          onSubmit={handlePathSubmit}
          className="flex gap-2 px-4 py-2 border-b border-[#222] bg-[#0C0C0C]"
        >
          <span className="text-[#555] font-bold text-xs py-1.5 shrink-0">&gt;</span>
          <input
            type="text"
            value={pathInput}
            onChange={(e) => setPathInput(e.target.value)}
            className="flex-1 border border-[#333] bg-[#121212] px-3 py-1.5 text-sm text-[#E0E0E0] font-mono focus:outline-none focus:border-[var(--color-accent)] placeholder-[#333]"
          />
          <button
            type="submit"
            className="border border-[#333] bg-[#1A1A1A] px-3 py-1.5 text-xs text-[#888] hover:text-[#E0E0E0] hover:border-[#555] font-mono transition-colors"
          >
            Go
          </button>
        </form>

        {error && (
          <div className="px-4 py-2 text-xs text-[var(--color-error)] font-mono bg-[var(--color-error)]/5">{error}</div>
        )}

        {/* File list */}
        <div className="flex-1 overflow-y-auto min-h-0 tui-scrollbar bg-[#0C0C0C]">
          {/* New folder inline input */}
          {creatingFolder && (
            <div className="flex items-center gap-2 px-4 py-1.5 bg-[var(--color-accent)]/5 border-b border-[var(--color-accent)]/20">
              <span className="text-[var(--color-accent)] text-xs font-mono w-5 text-center">{"\u25A1"}</span>
              <input
                ref={newFolderRef}
                type="text"
                value={newFolderName}
                onChange={(e) => setNewFolderName(e.target.value)}
                onKeyDown={handleNewFolderKeyDown}
                placeholder="Folder name..."
                className="flex-1 border border-[#333] bg-[#121212] px-2 py-1 text-sm text-[#E0E0E0] font-mono focus:outline-none focus:border-[var(--color-accent)] placeholder-[#333]"
              />
              <button
                onClick={handleCreateFolder}
                disabled={!newFolderName.trim()}
                className="px-2 py-1 text-[10px] font-bold font-mono bg-[var(--color-accent)] text-[#0C0C0C] hover:bg-[var(--color-accent-hover)] disabled:opacity-40 transition-colors"
              >
                Create
              </button>
              <button
                onClick={() => { setCreatingFolder(false); setNewFolderName(""); setCreateError(""); }}
                className="text-[10px] text-[#555] hover:text-[var(--color-accent)] transition-colors font-mono"
              >
                {"\u2717"}
              </button>
            </div>
          )}
          {createError && (
            <div className="px-4 py-1 text-xs text-[var(--color-error)] font-mono">{createError}</div>
          )}

          {entries.map((entry) => (
            <button
              key={entry.path}
              onClick={() =>
                entry.is_dir ? handleNavigate(entry.path) : undefined
              }
              className={`w-full flex items-center gap-2 px-4 py-1.5 text-left text-sm hover:bg-[#1A1A1A] transition-colors border-b border-[#1A1A1A] ${
                entry.is_dir
                  ? "text-[#E0E0E0] cursor-pointer"
                  : "text-[#555] cursor-default"
              }`}
            >
              <span className={`text-xs w-5 text-center font-mono ${entry.is_dir ? "text-[var(--color-accent)]" : "text-[#333]"}`}>
                {entry.is_dir ? "\u25B8" : "\u00B7"}
              </span>
              <span className="truncate font-mono">{entry.name}</span>
            </button>
          ))}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-4 py-3 border-t border-[#333] bg-[#121212]">
          <span className="text-xs text-[#555] font-mono truncate mr-4">
            {current}
          </span>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="border border-[#333] px-3 py-1.5 text-xs text-[#888] hover:text-[#E0E0E0] hover:border-[#555] font-mono transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={() => {
                if (current) saveLastBrowsePath(current);
                onSelect(current);
              }}
              className="bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] px-4 py-1.5 text-xs font-bold font-mono text-[#0C0C0C] transition-colors uppercase tracking-wider"
            >
              Select {"\u2192"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
