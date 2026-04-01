"use client";

import { useState, useEffect, useCallback, useRef } from "react";

export interface KeyBinding {
  id: string;
  label: string;
  keys: string[];
  category: string;
  handler?: () => void;
  isDefault?: boolean;
}

interface KeybindingConfig {
  bindings: KeyBinding[];
  reserved: string[];
}

// Global handler registry (shared across all hook instances)
const handlerRegistry = new Map<string, () => void>();

// Parse a key string like "ctrl+shift+k" into a check function
function matchesKeyEvent(keyStr: string, e: KeyboardEvent): boolean {
  const parts = keyStr.toLowerCase().split("+");
  const key = parts[parts.length - 1];
  const needsCtrl = parts.includes("ctrl") || parts.includes("cmd");
  const needsShift = parts.includes("shift");
  const needsAlt = parts.includes("alt");

  const ctrlMatch = needsCtrl ? (e.ctrlKey || e.metaKey) : !(e.ctrlKey || e.metaKey);
  const shiftMatch = needsShift ? e.shiftKey : !e.shiftKey;
  const altMatch = needsAlt ? e.altKey : !e.altKey;

  // Normalize key names
  let eventKey = e.key.toLowerCase();
  if (eventKey === " ") eventKey = "space";
  if (eventKey === "escape") eventKey = "esc";
  if (eventKey === ".") eventKey = ".";
  if (eventKey === "$") eventKey = "$";

  return ctrlMatch && shiftMatch && altMatch && eventKey === key;
}

export function useKeybindings() {
  const [config, setConfig] = useState<KeybindingConfig | null>(null);
  const configRef = useRef<KeybindingConfig | null>(null);

  // Fetch config on mount
  useEffect(() => {
    fetch("/api/keybindings")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d) {
          setConfig(d);
          configRef.current = d;
        }
      })
      .catch(() => {});
  }, []);

  // Register a handler for a binding ID
  const registerHandler = useCallback((id: string, handler: () => void) => {
    handlerRegistry.set(id, handler);
    return () => { handlerRegistry.delete(id); };
  }, []);

  // Global keyboard listener
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Skip when typing in inputs (except Escape)
      const target = e.target as HTMLElement;
      if (
        (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable) &&
        e.key !== "Escape"
      ) {
        return;
      }

      const cfg = configRef.current;
      if (!cfg) return;

      for (const binding of cfg.bindings) {
        for (const keyStr of binding.keys) {
          if (matchesKeyEvent(keyStr, e)) {
            const fn = handlerRegistry.get(binding.id);
            if (fn) {
              e.preventDefault();
              fn();
              return;
            }
          }
        }
      }
    };

    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, []);

  // Update a binding
  const updateBinding = useCallback(async (id: string, newKeys: string[]) => {
    const current = configRef.current;
    if (!current) return;

    const updated = current.bindings.map((b) =>
      b.id === id ? { ...b, keys: newKeys, isDefault: false } : b
    );
    const newConfig = { ...current, bindings: updated };
    setConfig(newConfig);
    configRef.current = newConfig;

    // Persist
    await fetch("/api/keybindings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ bindings: updated.map((b) => ({ id: b.id, keys: b.keys })) }),
    }).catch(() => {});
  }, []);

  // Reset all
  const resetToDefaults = useCallback(async () => {
    await fetch("/api/keybindings/reset", { method: "POST" }).catch(() => {});
    // Refetch
    const r = await fetch("/api/keybindings").catch(() => null);
    if (r && r.ok) {
      const d = await r.json();
      setConfig(d);
      configRef.current = d;
    }
  }, []);

  return { config, registerHandler, updateBinding, resetToDefaults };
}

// Helper to format a key binding for display
export function formatKeys(keys: string[]): string {
  return keys
    .map((k) =>
      k
        .split("+")
        .map((p) => {
          const s = p.trim();
          if (s === "ctrl" || s === "cmd") return "Ctrl";
          if (s === "shift") return "Shift";
          if (s === "alt") return "Alt";
          return s.length === 1 ? s.toUpperCase() : s.charAt(0).toUpperCase() + s.slice(1);
        })
        .join("+")
    )
    .join(", ");
}
