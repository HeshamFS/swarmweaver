"use client";

import { type Mode } from "../hooks/useSwarmWeaver";

interface ModeOption {
  id: Mode;
  label: string;
  description: string;
  icon: string;
  inputLabel: string;
  inputPlaceholder: string;
  inputType: "description" | "goal" | "issue" | "spec";
}

const MODES: ModeOption[] = [
  {
    id: "greenfield",
    label: "Greenfield",
    description: "Build a new project from an idea or specification",
    icon: "\u{1F3D7}",
    inputLabel: "App idea or spec path",
    inputPlaceholder: "e.g. 'A real-time task management app with AI' or path to spec file",
    inputType: "spec",
  },
  {
    id: "feature",
    label: "Feature",
    description: "Add features to an existing codebase",
    icon: "\u{2728}",
    inputLabel: "Feature description",
    inputPlaceholder: "Add OAuth2 login with Google and GitHub providers",
    inputType: "description",
  },
  {
    id: "refactor",
    label: "Refactor",
    description: "Restructure or migrate a codebase",
    icon: "\u{1F504}",
    inputLabel: "Refactoring goal",
    inputPlaceholder: "Migrate from JavaScript to TypeScript with strict mode",
    inputType: "goal",
  },
  {
    id: "fix",
    label: "Fix",
    description: "Diagnose and fix bugs",
    icon: "\u{1F41B}",
    inputLabel: "Issue description",
    inputPlaceholder:
      "Login fails when email contains a plus sign - returns 400",
    inputType: "issue",
  },
  {
    id: "evolve",
    label: "Evolve",
    description: "Improve an existing codebase",
    icon: "\u{1F680}",
    inputLabel: "Improvement goal",
    inputPlaceholder: "Add comprehensive unit tests to achieve 80% coverage",
    inputType: "goal",
  },
];

interface ModeSelectorProps {
  selected: Mode;
  onSelect: (mode: Mode) => void;
  disabled: boolean;
}

export function ModeSelector({
  selected,
  onSelect,
  disabled,
}: ModeSelectorProps) {
  return (
    <div className="grid grid-cols-5 gap-2">
      {MODES.map((mode) => {
        const isActive = selected === mode.id;
        return (
          <button
            key={mode.id}
            onClick={() => onSelect(mode.id)}
            disabled={disabled}
            className={`
              relative flex flex-col items-center gap-1.5 rounded-lg border p-3
              transition-all text-center
              ${
                isActive
                  ? "border-accent bg-accent/10 text-accent"
                  : "border-border-subtle bg-surface-raised text-text-secondary hover:border-border-default hover:text-text-primary"
              }
              ${disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}
            `}
          >
            <span className="text-xl">{mode.icon}</span>
            <span className="text-sm font-medium">{mode.label}</span>
            <span className="text-xs text-text-muted leading-tight">
              {mode.description}
            </span>
          </button>
        );
      })}
    </div>
  );
}

export function getModeConfig(mode: Mode): ModeOption {
  return MODES.find((m) => m.id === mode) || MODES[0];
}
