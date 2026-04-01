"use client";

import { useState, useEffect } from "react";

interface OutputStyle {
  id: string;
  name: string;
  description: string;
}

interface OutputStyleSelectorProps {
  currentStyle?: string;
  onStyleChange: (style: string) => void;
}

export function OutputStyleSelector({ currentStyle = "verbose", onStyleChange }: OutputStyleSelectorProps) {
  const [styles, setStyles] = useState<OutputStyle[]>([]);
  const [selected, setSelected] = useState(currentStyle);

  useEffect(() => {
    fetch("/api/output-styles")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (d?.styles) setStyles(d.styles); })
      .catch(() => {
        // Fallback styles
        setStyles([
          { id: "verbose", name: "Verbose", description: "Full detail" },
          { id: "concise", name: "Concise", description: "Key info only" },
          { id: "structured", name: "Structured", description: "Organized sections" },
          { id: "minimal", name: "Minimal", description: "Bare essentials" },
        ]);
      });
  }, []);

  useEffect(() => {
    setSelected(currentStyle);
  }, [currentStyle]);

  const handleChange = (styleId: string) => {
    setSelected(styleId);
    onStyleChange(styleId);
  };

  return (
    <div className="space-y-2">
      <h3 className="text-[10px] font-mono text-text-muted uppercase tracking-wider">
        Output Style
      </h3>
      <div className="grid grid-cols-2 gap-1.5">
        {styles.map((style) => (
          <button
            key={style.id}
            onClick={() => handleChange(style.id)}
            className={`text-left p-2 rounded-md border transition-all ${
              selected === style.id
                ? "border-accent bg-accent/10 text-accent"
                : "border-border-subtle bg-surface text-text-secondary hover:border-border-default hover:bg-surface-raised/50"
            }`}
          >
            <div className="text-xs font-mono font-medium">{style.name}</div>
            <div className="text-[10px] text-text-muted mt-0.5">{style.description}</div>
          </button>
        ))}
      </div>
    </div>
  );
}
