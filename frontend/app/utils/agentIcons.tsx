"use client";

import {
  Check,
  X,
  AlertTriangle,
  Zap,
  Rocket,
  GitMerge,
  Ban,
  ListTodo,
  Circle,
  Square,
  List,
  Table2,
  Code2,
  FileText,
  Clock,
  Play,
  Pause,
  Bot,
  Users,
  ChevronRight,
  Minus,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

/** Curated icon shortcodes for agent output. Use :shortcode: in text. */
export const AGENT_ICON_SHORTCODES: Record<string, LucideIcon> = {
  check: Check,
  x: X,
  alert: AlertTriangle,
  zap: Zap,
  rocket: Rocket,
  merge: GitMerge,
  block: Ban,
  task: ListTodo,
  circle: Circle,
  square: Square,
  list: List,
  table: Table2,
  code: Code2,
  file: FileText,
  clock: Clock,
  play: Play,
  pause: Pause,
  bot: Bot,
  users: Users,
  arrow: ChevronRight,
  bullet: Minus,
};

/** Semantic color for certain icons (success, error, warning, accent). */
const ICON_SEMANTIC_COLORS: Record<string, string> = {
  check: "var(--color-success)",
  x: "var(--color-error)",
  block: "var(--color-error)",
  alert: "var(--color-warning)",
  zap: "var(--color-warning)",
};

/**
 * Render an icon from a shortcode name. Returns a styled Lucide icon.
 * Unknown shortcodes fall back to Circle.
 */
export function renderIconShortcode(
  shortcode: string,
  className?: string,
  size?: number
): React.ReactNode {
  const key = shortcode.toLowerCase().replace(/\s/g, "-");
  const Icon = AGENT_ICON_SHORTCODES[key] ?? Circle;

  const semanticColor = ICON_SEMANTIC_COLORS[key];
  const colorClass = semanticColor ? "" : "text-[var(--color-accent)]";

  return (
    <Icon
      size={size ?? 12}
      className={`inline-block shrink-0 align-[-0.15em] ${colorClass} ${className ?? ""}`.trim()}
      style={semanticColor ? { color: semanticColor } : undefined}
    />
  );
}

/** Regex to find :icon-name: shortcodes in text */
export const ICON_SHORTCODE_RE = /:([a-z0-9_-]+):/g;
