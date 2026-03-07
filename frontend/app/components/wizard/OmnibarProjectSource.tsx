"use client";

import { useState, useEffect, useRef } from "react";
import { FolderPicker } from "../FolderPicker";
import type { ProjectInfo, ProjectStatus } from "../../hooks/useSwarmWeaver";
import { MODE_ICONS } from "../../utils/modeIcons";

export type SourceType = "new" | "clone" | "existing";

interface OmnibarProjectSourceProps {
  sourceType: SourceType;
  onSourceTypeChange: (t: SourceType) => void;
  projectDir: string;
  onProjectDirChange: (d: string) => void;
  cloneUrl: string;
  onCloneUrlChange: (u: string) => void;
  projects: ProjectInfo[];
  checkProjectStatus: (path: string) => Promise<ProjectStatus | null>;
}

const SOURCE_TABS: { id: SourceType; label: string }[] = [
  { id: "new", label: "New Project" },
  { id: "clone", label: "Clone Repo" },
  { id: "existing", label: "Open Local" },
];

export function OmnibarProjectSource({
  sourceType,
  onSourceTypeChange,
  projectDir,
  onProjectDirChange,
  cloneUrl,
  onCloneUrlChange,
  projects,
  checkProjectStatus,
}: OmnibarProjectSourceProps) {
  const [showPicker, setShowPicker] = useState(false);
  const [pickerTarget, setPickerTarget] = useState<"project" | "cloneDir">("project");
  const [showDropdown, setShowDropdown] = useState(false);
  const [projectStatus, setProjectStatus] = useState<ProjectStatus | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  /* Debounced project status check */
  useEffect(() => {
    if (sourceType !== "existing" || !projectDir.trim()) {
      setProjectStatus(null);
      return;
    }
    const timer = setTimeout(() => {
      checkProjectStatus(projectDir).then(setProjectStatus);
    }, 500);
    return () => clearTimeout(timer);
  }, [sourceType, projectDir, checkProjectStatus]);

  /* Close dropdown on outside click */
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  /* Filtered project list for autocomplete */
  const filtered = projectDir.trim()
    ? projects.filter((p) =>
      p.name.toLowerCase().includes(projectDir.toLowerCase()) ||
      p.path.toLowerCase().includes(projectDir.toLowerCase())
    )
    : projects;

  const openPicker = (target: "project" | "cloneDir") => {
    setPickerTarget(target);
    setShowPicker(true);
  };

  return (
    <div>
      {/* Source type tabs (TUI bracket style) */}
      <div className="flex border-b border-[#333] bg-[#0C0C0C] text-xs uppercase tracking-wider overflow-x-auto font-mono">
        {SOURCE_TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => onSourceTypeChange(tab.id)}
            className={`px-6 py-3 transition-colors whitespace-nowrap ${sourceType === tab.id
              ? "text-[var(--color-accent)] border-b-2 border-[var(--color-accent)] bg-[#121212] cursor-default"
              : "text-[#555] hover:text-[#E0E0E0] cursor-pointer"
              }`}
          >
            {sourceType === tab.id ? `[ ${tab.label} ]` : tab.label}
          </button>
        ))}
      </div>

      {/* ── New Project: path input ── */}
      {sourceType === "new" && (
        <div className="p-4 border-b border-[#222] flex items-center bg-[#0C0C0C]">
          <span className="text-[#555] mr-3 font-bold text-xs uppercase font-mono">DIR &gt;</span>
          <input
            type="text"
            value={projectDir}
            onChange={(e) => onProjectDirChange(e.target.value)}
            placeholder="Project folder name (e.g. my-app)"
            className="flex-1 bg-transparent text-[#E0E0E0] outline-none font-mono placeholder-[#333]"
          />
          <button
            onClick={() => openPicker("project")}
            className="border border-[#333] px-4 py-1.5 text-[#888] hover:text-[#E0E0E0] hover:border-[var(--color-accent)] text-xs uppercase transition-colors whitespace-nowrap font-mono"
          >
            [ Browse ]
          </button>
        </div>
      )}

      {/* ── Clone Repo: URL + target dir ── */}
      {sourceType === "clone" && (
        <div>
          <div className="p-4 border-b border-[#222] flex items-center bg-[#0C0C0C]">
            <span className="text-[#555] mr-3 font-bold text-xs uppercase font-mono">URL &gt;</span>
            <input
              type="text"
              value={cloneUrl}
              onChange={(e) => onCloneUrlChange(e.target.value)}
              placeholder="https://github.com/user/repo.git"
              className="flex-1 bg-transparent text-[#E0E0E0] outline-none font-mono placeholder-[#333]"
            />
          </div>
          <div className="p-4 border-b border-[#222] flex items-center bg-[#0C0C0C]">
            <span className="text-[#555] mr-3 font-bold text-xs uppercase font-mono">DIR &gt;</span>
            <input
              type="text"
              value={projectDir}
              onChange={(e) => onProjectDirChange(e.target.value)}
              placeholder="./generations/repo-name (auto)"
              className="flex-1 bg-transparent text-[#888] outline-none font-mono text-xs placeholder-[#333]"
            />
            <button
              onClick={() => openPicker("cloneDir")}
              className="border border-[#333] px-4 py-1.5 text-[#888] hover:text-[#E0E0E0] hover:border-[var(--color-accent)] text-xs uppercase transition-colors whitespace-nowrap font-mono"
            >
              [ Browse ]
            </button>
          </div>
        </div>
      )}

      {/* ── Open Local: path input with autocomplete ── */}
      {sourceType === "existing" && (
        <div className="p-4 border-b border-[#222] flex items-center bg-[#0C0C0C]" ref={dropdownRef}>
          <span className="text-[#555] mr-3 font-bold text-xs uppercase font-mono">DIR &gt;</span>
          <div className="relative flex-1">
            <input
              type="text"
              value={projectDir}
              onChange={(e) => {
                onProjectDirChange(e.target.value);
                setShowDropdown(true);
              }}
              onFocus={() => setShowDropdown(true)}
              placeholder="Select or type project path..."
              className="w-full bg-transparent text-[#E0E0E0] outline-none font-mono placeholder-[#333]"
            />

            {showDropdown && filtered.length > 0 && (
              <div className="absolute top-full left-0 right-0 mt-1 border border-[#333] bg-[#1A1A1A] shadow-lg z-50 max-h-48 overflow-y-auto tui-scrollbar">
                {filtered.slice(0, 8).map((p) => (
                  <button
                    key={p.path}
                    onClick={() => {
                      onProjectDirChange(p.path);
                      setShowDropdown(false);
                    }}
                    className="w-full text-left px-3 py-2 text-[12px] font-mono hover:bg-[#222] transition-colors flex items-center gap-2"
                  >
                    {(() => {
                      const ModeIcon = (p.mode ? MODE_ICONS[p.mode as keyof typeof MODE_ICONS] : MODE_ICONS.feature) as React.ComponentType<{ className?: string; style?: React.CSSProperties }>;
                      return <ModeIcon className="w-4 h-4 shrink-0" style={{ color: p.mode ? `var(--color-mode-${p.mode})` : "var(--color-text-muted)" }} />;
                    })()}
                    <span className="text-[#E0E0E0] truncate">{p.name}</span>
                    {p.mode && (
                      <span className="text-[10px] text-[#555] uppercase ml-auto shrink-0">{p.mode}</span>
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>

          <button
            onClick={() => openPicker("project")}
            className="border border-[#333] px-4 py-1.5 text-[#888] hover:text-[#E0E0E0] hover:border-[var(--color-accent)] text-xs uppercase transition-colors whitespace-nowrap font-mono ml-2"
          >
            [ Browse ]
          </button>

          {projectStatus && (
            <span className={`text-[10px] font-mono font-bold shrink-0 ml-3 ${projectStatus.exists ? "text-[var(--color-success)]" : "text-[var(--color-error)]"}`}>
              {projectStatus.exists
                ? projectStatus.resumable ? `${Math.round(projectStatus.percentage)}%` : "Ready"
                : "Not found"}
            </span>
          )}
        </div>
      )}

      {/* Folder picker modal */}
      {showPicker && (
        <FolderPicker
          onSelect={(path) => {
            if (pickerTarget === "cloneDir" || pickerTarget === "project") {
              onProjectDirChange(path);
            }
            setShowPicker(false);
          }}
          onClose={() => setShowPicker(false)}
        />
      )}
    </div>
  );
}
