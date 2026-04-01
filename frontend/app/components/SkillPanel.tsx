"use client";

import { useState, useEffect, useCallback } from "react";

interface SkillDef {
  name: string;
  description: string;
  when_to_use: string;
  allowed_tools: string[];
  model: string;
  context: string;
  paths: string[];
  arguments: string[];
  source_path: string;
  source_dir: string;
  body: string;
  enabled: boolean;
  user_invocable: boolean;
}

interface SkillPanelProps {
  projectDir: string;
}

const SOURCE_COLORS: Record<string, string> = {
  managed: "text-[#3B82F6] border-[#3B82F6]/30 bg-[#3B82F6]/10",
  user: "text-[#10B981] border-[#10B981]/30 bg-[#10B981]/10",
  project: "text-[var(--color-accent)] border-[var(--color-accent)]/30 bg-[var(--color-accent)]/10",
};

const CONTEXT_LABELS: Record<string, string> = {
  inline: "Expands into conversation",
  fork: "Runs as sub-agent",
};

export function SkillPanel({ projectDir }: SkillPanelProps) {
  const [skills, setSkills] = useState<SkillDef[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedSkill, setSelectedSkill] = useState<SkillDef | null>(null);
  const [filter, setFilter] = useState<string>("all");
  const [showUpload, setShowUpload] = useState(false);
  const [uploadContent, setUploadContent] = useState("");
  const [uploadName, setUploadName] = useState("");

  const fetchSkills = useCallback(() => {
    const params = projectDir ? `?path=${encodeURIComponent(projectDir)}` : "";
    fetch(`/api/skills${params}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (d?.skills) setSkills(d.skills); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [projectDir]);

  useEffect(() => { fetchSkills(); }, [fetchSkills]);

  const handleExecute = async (skill: SkillDef) => {
    const params = projectDir ? `?path=${encodeURIComponent(projectDir)}` : "";
    try {
      const res = await fetch(`/api/skills/${encodeURIComponent(skill.name)}/execute${params}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ args: {}, mode: "" }),
      });
      const data = await res.json();
      if (data.status === "ok") {
        // Show expanded content or trigger fork
        setSelectedSkill({ ...skill, body: data.expanded || data.prompt || skill.body });
      }
    } catch { /* silent */ }
  };

  const handleUpload = async () => {
    if (!uploadName.trim() || !uploadContent.trim()) return;
    try {
      await fetch("/api/skills/upload", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: uploadName.trim(),
          content: uploadContent,
          scope: "user",
          project_dir: projectDir,
        }),
      });
      setShowUpload(false);
      setUploadContent("");
      setUploadName("");
      fetchSkills();
    } catch { /* silent */ }
  };

  const handleDelete = async (skill: SkillDef) => {
    if (skill.source_dir === "managed") return;
    const params = `?scope=${skill.source_dir}&path=${encodeURIComponent(projectDir)}`;
    try {
      await fetch(`/api/skills/${encodeURIComponent(skill.name)}${params}`, { method: "DELETE" });
      setSelectedSkill(null);
      fetchSkills();
    } catch { /* silent */ }
  };

  const sources = Array.from(new Set(skills.map((s) => s.source_dir)));
  const filtered = filter === "all" ? skills : skills.filter((s) => s.source_dir === filter);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-32">
        <span className="text-xs font-mono text-[#555]">Discovering skills...</span>
      </div>
    );
  }

  // Detail view
  if (selectedSkill) {
    return (
      <div className="flex flex-col h-full">
        <div className="px-4 py-2.5 border-b border-[#222] bg-[#0C0C0C] shrink-0 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <button onClick={() => setSelectedSkill(null)} className="text-[#555] hover:text-[#E0E0E0] text-xs font-mono">{"\u2190"} Back</button>
            <span className="text-xs font-mono font-medium text-[#E0E0E0]">{selectedSkill.name}</span>
          </div>
          <div className="flex items-center gap-2">
            {selectedSkill.source_dir !== "managed" && (
              <button onClick={() => handleDelete(selectedSkill)}
                className="text-[10px] font-mono text-[#EF4444] hover:underline">Delete</button>
            )}
            <button onClick={() => handleExecute(selectedSkill)}
              className="text-[10px] font-mono font-bold px-2 py-0.5 bg-[var(--color-accent)] text-[#0C0C0C]">
              {selectedSkill.context === "fork" ? "Run as Agent" : "Expand"}
            </button>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto min-h-0 px-4 py-3 space-y-3">
          <div className="text-xs font-mono text-[#888]">{selectedSkill.description}</div>
          {selectedSkill.when_to_use && (
            <div className="text-[10px] font-mono text-[#555]">When: {selectedSkill.when_to_use}</div>
          )}
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`text-[9px] font-mono px-1 py-0.5 border ${SOURCE_COLORS[selectedSkill.source_dir] || "text-[#555] border-[#333]"}`}>
              {selectedSkill.source_dir}
            </span>
            <span className="text-[9px] font-mono px-1 py-0.5 border border-[#333] text-[#555]">
              {selectedSkill.context}
            </span>
            {selectedSkill.model && (
              <span className="text-[9px] font-mono px-1 py-0.5 border border-[#333] text-[#555]">
                model: {selectedSkill.model}
              </span>
            )}
          </div>
          {selectedSkill.allowed_tools.length > 0 && (
            <div>
              <div className="text-[10px] font-mono text-[#555] mb-1">Allowed Tools</div>
              <div className="flex flex-wrap gap-1">
                {selectedSkill.allowed_tools.map((t) => (
                  <span key={t} className="text-[9px] font-mono px-1 py-0.5 bg-[#1A1A1A] border border-[#333] text-[#888]">{t}</span>
                ))}
              </div>
            </div>
          )}
          <div>
            <div className="text-[10px] font-mono text-[#555] mb-1">Skill Content</div>
            <div className="bg-[#121212] border border-[#222] p-3 text-xs font-mono text-[#CCC] whitespace-pre-wrap max-h-[400px] overflow-y-auto leading-relaxed">
              {selectedSkill.body}
            </div>
          </div>
          <div className="text-[9px] font-mono text-[#444] truncate">
            Source: {selectedSkill.source_path}
          </div>
        </div>
      </div>
    );
  }

  // Upload view
  if (showUpload) {
    return (
      <div className="flex flex-col h-full">
        <div className="px-4 py-2.5 border-b border-[#222] bg-[#0C0C0C] shrink-0 flex items-center justify-between">
          <button onClick={() => setShowUpload(false)} className="text-[#555] hover:text-[#E0E0E0] text-xs font-mono">{"\u2190"} Back</button>
          <span className="text-xs font-mono font-medium text-[#E0E0E0]">Create Skill</span>
        </div>
        <div className="flex-1 overflow-y-auto min-h-0 px-4 py-3 space-y-3">
          <label className="block">
            <span className="text-[10px] text-[#555] mb-1 block font-mono">Skill Name</span>
            <input value={uploadName} onChange={(e) => setUploadName(e.target.value)}
              placeholder="my-skill"
              className="w-full bg-[#1A1A1A] border border-[#333] text-xs text-[#E0E0E0] font-mono px-2 py-1.5 focus:outline-none focus:border-[var(--color-accent)]" />
          </label>
          <label className="block">
            <span className="text-[10px] text-[#555] mb-1 block font-mono">Content (Markdown with YAML frontmatter)</span>
            <textarea value={uploadContent} onChange={(e) => setUploadContent(e.target.value)}
              placeholder={"---\nname: my-skill\ndescription: What it does\ncontext: inline\n---\n\n# My Skill\n\nInstructions here..."}
              rows={15}
              className="w-full bg-[#1A1A1A] border border-[#333] text-xs text-[#E0E0E0] font-mono px-2 py-1.5 focus:outline-none focus:border-[var(--color-accent)] resize-y" />
          </label>
          <button onClick={handleUpload} disabled={!uploadName.trim() || !uploadContent.trim()}
            className="px-3 py-1 text-[10px] font-mono font-bold bg-[var(--color-accent)] text-[#0C0C0C] disabled:opacity-30">
            Save Skill
          </button>
        </div>
      </div>
    );
  }

  // List view
  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-2.5 border-b border-[#222] bg-[#0C0C0C] shrink-0 flex items-center justify-between">
        <span className="text-xs font-mono font-medium text-[#E0E0E0] uppercase tracking-wider">Skills ({skills.length})</span>
        <button onClick={() => setShowUpload(true)}
          className="text-[10px] font-mono text-[var(--color-accent)] hover:underline">+ Create</button>
      </div>

      {/* Filter */}
      <div className="px-4 py-1.5 border-b border-[#222] flex items-center gap-1 shrink-0">
        <button onClick={() => setFilter("all")}
          className={`px-1.5 py-0.5 text-[10px] font-mono rounded transition-colors ${filter === "all" ? "bg-[var(--color-accent)]/20 text-[var(--color-accent)]" : "text-[#555] hover:text-[#888]"}`}>
          All
        </button>
        {sources.map((s) => (
          <button key={s} onClick={() => setFilter(s)}
            className={`px-1.5 py-0.5 text-[10px] font-mono rounded transition-colors ${filter === s ? "bg-[var(--color-accent)]/20 text-[var(--color-accent)]" : "text-[#555] hover:text-[#888]"}`}>
            {s}
          </button>
        ))}
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {filtered.length === 0 ? (
          <div className="flex items-center justify-center h-20">
            <span className="text-xs font-mono text-[#555]">No skills found</span>
          </div>
        ) : (
          <div className="divide-y divide-[#222]">
            {filtered.map((skill) => (
              <button key={skill.name} onClick={() => setSelectedSkill(skill)}
                className="w-full text-left px-4 py-2.5 hover:bg-[#1A1A1A] transition-colors">
                <div className="flex items-center gap-2 mb-0.5">
                  <span className="text-xs font-mono font-medium text-[#E0E0E0]">{skill.name}</span>
                  <span className={`text-[9px] font-mono px-1 py-0.5 border ${SOURCE_COLORS[skill.source_dir] || "text-[#555] border-[#333]"}`}>
                    {skill.source_dir}
                  </span>
                  <span className="text-[9px] font-mono text-[#444]">{skill.context}</span>
                </div>
                <div className="text-[10px] font-mono text-[#555] truncate">{skill.description}</div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
