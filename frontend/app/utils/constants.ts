export const MODELS = [
  { id: "claude-opus-4-6", label: "Opus 4.6" },
  { id: "claude-sonnet-4-6", label: "Sonnet 4.6" },
  { id: "claude-sonnet-4-5-20250929", label: "Sonnet 4.5" },
  { id: "claude-haiku-4-5-20251001", label: "Haiku 4.5" },
];

export type PresetType = "fast" | "standard" | "production";

export const PRESETS: {
  id: PresetType;
  label: string;
  model: string;
  parallel: number;
  approvalGates: boolean;
  reviewPlan: boolean;
}[] = [
  { id: "fast", label: "Fast", model: "claude-haiku-4-5-20251001", parallel: 1, approvalGates: false, reviewPlan: false },
  { id: "standard", label: "Standard", model: "claude-sonnet-4-6", parallel: 1, approvalGates: false, reviewPlan: false },
  { id: "production", label: "Production", model: "claude-opus-4-6", parallel: 1, approvalGates: true, reviewPlan: true },
];
