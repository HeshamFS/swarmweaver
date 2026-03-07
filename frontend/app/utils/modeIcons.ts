import { Sprout, Code2, RefreshCw, Bug, TrendingUp, Shield } from "lucide-react";
import type { Mode } from "../hooks/useSwarmWeaver";

export const MODE_COLORS: Record<string, string> = {
  greenfield: "var(--color-mode-greenfield)",
  feature: "var(--color-mode-feature)",
  refactor: "var(--color-mode-refactor)",
  fix: "var(--color-mode-fix)",
  evolve: "var(--color-mode-evolve)",
  security: "var(--color-mode-security)",
};

export const MODE_ICONS: Record<Mode, React.ComponentType<{ size?: number; className?: string; style?: React.CSSProperties }>> = {
  greenfield: Sprout,
  feature: Code2,
  refactor: RefreshCw,
  fix: Bug,
  evolve: TrendingUp,
  security: Shield,
};
