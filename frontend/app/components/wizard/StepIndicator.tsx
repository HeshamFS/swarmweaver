"use client";

interface StepIndicatorProps {
  steps: string[];
  currentStep: number;
  onStepClick?: (index: number) => void;
}

export default function StepIndicator({ steps, currentStep, onStepClick }: StepIndicatorProps) {
  return (
    <div className="flex items-center justify-center gap-0 px-6 py-3.5 border-b border-[var(--border-subtle)] bg-[var(--surface-raised)]">
      {steps.map((label, i) => {
        const isCompleted = i < currentStep;
        const isCurrent = i === currentStep;
        const isClickable = onStepClick && (isCompleted || i === currentStep + 1);

        return (
          <div key={label} className="flex items-center">
            <div
              className={`flex items-center gap-2 ${isClickable ? "cursor-pointer group" : ""}`}
              onClick={() => { if (isClickable) onStepClick(i); }}
            >
              <div
                className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold transition-all duration-300 ${isCompleted
                    ? "bg-[var(--accent)] text-white shadow-[0_0_12px_var(--accent-glow)] group-hover:bg-[var(--accent-hover)]"
                    : isCurrent
                      ? "bg-[var(--accent)] text-white shadow-[0_0_16px_var(--accent-glow)]"
                      : isClickable
                        ? "bg-[var(--surface-overlay)] text-[var(--text-primary)] border border-[var(--accent)] group-hover:border-[var(--accent-hover)]"
                        : "bg-[var(--surface-overlay)] text-[var(--text-muted)] border border-[var(--border-default)]"
                  }`}
              >
                {isCompleted ? (
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                ) : (
                  i + 1
                )}
              </div>
              <span
                className={`text-sm hidden sm:inline transition-colors duration-300 ${isCurrent
                    ? "text-[var(--text-primary)] font-medium"
                    : isCompleted
                      ? "text-[var(--text-secondary)]"
                      : "text-[var(--text-muted)]"
                  }`}
              >
                {label}
              </span>
            </div>

            {i < steps.length - 1 && (
              <div className="w-16 h-px mx-4 relative overflow-hidden rounded-full">
                <div className="absolute inset-0 bg-[var(--border-default)]" />
                <div
                  className="absolute inset-y-0 left-0 bg-[var(--accent)] transition-all duration-500 rounded-full"
                  style={{ width: i < currentStep ? "100%" : "0%" }}
                />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
