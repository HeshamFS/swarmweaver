"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { formatKeys } from "../hooks/useKeybindings";

interface KeyBinding {
  id: string;
  label: string;
  keys: string[];
  category: string;
  isDefault?: boolean;
}

interface KeybindingsEditorProps {
  open: boolean;
  onClose: () => void;
}

const CATEGORY_LABELS: Record<string, string> = {
  navigation: "Navigation",
  actions: "Actions",
  panels: "Panels",
  custom: "Custom",
};

export function KeybindingsEditor({ open, onClose }: KeybindingsEditorProps) {
  const [bindings, setBindings] = useState<KeyBinding[]>([]);
  const [reserved, setReserved] = useState<string[]>([]);
  const [capturing, setCapturing] = useState<string | null>(null);
  const [capturedKeys, setCapturedKeys] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const captureRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    fetch("/api/keybindings")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d) {
          setBindings(d.bindings || []);
          setReserved(d.reserved || []);
        }
      })
      .catch(() => {});
  }, [open]);

  const startCapture = (id: string) => {
    setCapturing(id);
    setCapturedKeys("");
    setError(null);
  };

  // Capture key press
  useEffect(() => {
    if (!capturing) return;
    const handler = (e: KeyboardEvent) => {
      e.preventDefault();
      e.stopPropagation();

      if (e.key === "Escape") {
        setCapturing(null);
        return;
      }

      const parts: string[] = [];
      if (e.ctrlKey || e.metaKey) parts.push("ctrl");
      if (e.shiftKey) parts.push("shift");
      if (e.altKey) parts.push("alt");

      let key = e.key.toLowerCase();
      if (key === " ") key = "space";
      if (!["control", "shift", "alt", "meta"].includes(key)) {
        parts.push(key);
      }

      if (parts.length > 0 && !["control", "shift", "alt", "meta"].includes(parts[parts.length - 1])) {
        const combo = parts.join("+");

        // Check reserved
        if (reserved.includes(combo)) {
          setError(`'${combo}' is a reserved shortcut`);
          return;
        }

        // Check conflicts
        const conflict = bindings.find(
          (b) => b.id !== capturing && b.keys.some((k) => k.toLowerCase() === combo)
        );
        if (conflict) {
          setError(`Conflicts with '${conflict.label}'`);
          return;
        }

        setCapturedKeys(combo);
        setError(null);

        // Apply
        const updated = bindings.map((b) =>
          b.id === capturing ? { ...b, keys: [combo], isDefault: false } : b
        );
        setBindings(updated);
        setCapturing(null);

        // Save
        fetch("/api/keybindings", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ bindings: updated.map((b) => ({ id: b.id, keys: b.keys })) }),
        }).catch(() => {});
      }
    };

    document.addEventListener("keydown", handler, true);
    return () => document.removeEventListener("keydown", handler, true);
  }, [capturing, bindings, reserved]);

  const handleReset = async () => {
    await fetch("/api/keybindings/reset", { method: "POST" });
    const r = await fetch("/api/keybindings");
    if (r.ok) {
      const d = await r.json();
      setBindings(d.bindings || []);
    }
  };

  if (!open) return null;

  const categories = Array.from(new Set(bindings.map((b) => b.category)));

  return (
    <>
      <div className="fixed inset-0 bg-black/60 z-40" onClick={onClose} />
      <div className="fixed right-0 top-0 bottom-0 w-[480px] z-50 bg-[#0C0C0C] border-l border-[#333] flex flex-col shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#222] shrink-0">
          <h2 className="text-sm font-mono font-bold text-[#E0E0E0] uppercase tracking-wider">Keyboard Shortcuts</h2>
          <div className="flex items-center gap-2">
            <button
              onClick={handleReset}
              className="text-[10px] font-mono text-[#555] hover:text-[#888] transition-colors"
            >
              Reset All
            </button>
            <button onClick={onClose} className="text-[#555] hover:text-[#E0E0E0] text-lg">&times;</button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto min-h-0 p-4 space-y-4">
          {categories.map((cat) => (
            <div key={cat}>
              <div className="text-[10px] font-bold text-[#555] uppercase tracking-wider mb-2 font-mono">
                {CATEGORY_LABELS[cat] || cat}
              </div>
              <div className="space-y-1">
                {bindings
                  .filter((b) => b.category === cat)
                  .map((b) => (
                    <div
                      key={b.id}
                      className="flex items-center justify-between px-2 py-2 hover:bg-[#1A1A1A] transition-colors"
                    >
                      <div className="flex-1">
                        <div className="text-xs font-mono text-[#E0E0E0]">{b.label}</div>
                        {!b.isDefault && (
                          <div className="text-[9px] font-mono text-[var(--color-accent)]">customized</div>
                        )}
                      </div>
                      <button
                        onClick={() => startCapture(b.id)}
                        className={`px-2 py-1 text-[11px] font-mono border transition-colors min-w-[100px] text-center ${
                          capturing === b.id
                            ? "border-[var(--color-accent)] bg-[var(--color-accent)]/10 text-[var(--color-accent)] animate-pulse"
                            : "border-[#333] bg-[#1A1A1A] text-[#888] hover:border-[#555] hover:text-[#E0E0E0]"
                        }`}
                      >
                        {capturing === b.id ? "Press key..." : formatKeys(b.keys)}
                      </button>
                    </div>
                  ))}
              </div>
            </div>
          ))}

          {error && (
            <div className="text-[10px] font-mono text-[#EF4444] px-2">{error}</div>
          )}
        </div>

        {/* Footer */}
        <div className="px-4 py-2.5 border-t border-[#222] text-[10px] font-mono text-[#555] shrink-0">
          Click a shortcut to rebind. Press Escape to cancel.
        </div>
      </div>
    </>
  );
}
