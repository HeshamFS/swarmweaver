"use client";

import { useState, useEffect } from "react";

interface Template {
  id: string;
  name: string;
  description: string;
  category: string;
  tags: string[];
  difficulty: string;
  estimated_tasks: number;
  spec_available: boolean;
}

interface TemplateGalleryProps {
  onSelect: (specContent: string, templateName: string) => void;
  onClose: () => void;
}

const CATEGORY_LABELS: Record<string, string> = {
  all: "All",
  web: "Web",
  api: "API",
  cli: "CLI",
  fullstack: "Full-Stack",
};

const DIFFICULTY_COLORS: Record<string, string> = {
  beginner: "text-success bg-success/10 border-success/30",
  intermediate: "text-accent bg-accent/10 border-accent/30",
  advanced: "text-warning bg-warning/10 border-warning/30",
};

export function TemplateGallery({ onSelect, onClose }: TemplateGalleryProps) {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [category, setCategory] = useState("all");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchTemplates();
  }, []);

  const fetchTemplates = async () => {
    try {
      const res = await fetch("/api/templates");
      const data = await res.json();
      setTemplates(data.templates || []);
    } catch {
      // Backend might not be running
    } finally {
      setLoading(false);
    }
  };

  const handleSelect = async (templateId: string, templateName: string) => {
    try {
      const res = await fetch(`/api/templates/${templateId}`);
      const data = await res.json();
      if (data.spec_content) {
        onSelect(data.spec_content, templateName);
      }
    } catch {
      // Ignore
    }
  };

  const filtered =
    category === "all"
      ? templates
      : templates.filter((t) => t.category === category);

  const categories = ["all", ...new Set(templates.map((t) => t.category))];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="w-full max-w-2xl mx-4 rounded-xl border border-border-subtle bg-surface shadow-2xl max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border-subtle">
          <div>
            <h2 className="text-lg font-semibold text-text-primary">
              Project Templates
            </h2>
            <p className="text-xs text-text-muted mt-0.5">
              Choose a template to pre-fill the specification
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-text-muted hover:text-text-primary p-1 rounded transition-colors"
          >
            {"\u2715"}
          </button>
        </div>

        {/* Category tabs */}
        <div className="flex gap-1 px-5 py-3 border-b border-border-subtle">
          {categories.map((cat) => (
            <button
              key={cat}
              onClick={() => setCategory(cat)}
              className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                category === cat
                  ? "bg-accent/15 text-accent border border-accent/30"
                  : "text-text-secondary hover:text-text-primary border border-transparent"
              }`}
            >
              {CATEGORY_LABELS[cat] || cat}
            </button>
          ))}
        </div>

        {/* Template grid */}
        <div className="flex-1 overflow-y-auto p-5">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <span className="text-sm text-text-muted">
                Loading templates...
              </span>
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex items-center justify-center py-12">
              <span className="text-sm text-text-muted">
                No templates found
              </span>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-3">
              {filtered.map((template) => (
                <button
                  key={template.id}
                  onClick={() => handleSelect(template.id, template.name)}
                  className="text-left rounded-lg border border-border-subtle bg-surface-raised p-4 hover:border-accent/50 hover:bg-accent/5 transition-all group"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-text-primary group-hover:text-accent transition-colors">
                          {template.name}
                        </span>
                        <span
                          className={`text-[10px] px-1.5 py-0.5 rounded-full border font-medium ${
                            DIFFICULTY_COLORS[template.difficulty] ||
                            "text-text-muted"
                          }`}
                        >
                          {template.difficulty}
                        </span>
                      </div>
                      <p className="text-xs text-text-secondary mt-1 leading-relaxed">
                        {template.description}
                      </p>
                      <div className="flex items-center gap-3 mt-2">
                        <span className="text-[10px] text-text-muted font-mono">
                          ~{template.estimated_tasks} tasks
                        </span>
                        <div className="flex gap-1">
                          {template.tags.slice(0, 4).map((tag) => (
                            <span
                              key={tag}
                              className="text-[10px] text-text-muted bg-surface px-1.5 py-0.5 rounded border border-border-subtle"
                            >
                              {tag}
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>
                    <span className="text-text-muted group-hover:text-accent text-lg ml-3 transition-colors">
                      {"\u2192"}
                    </span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
