"use client";

/**
 * Reusable skeleton loading components for the SwarmWeaver UI.
 * All variants use animate-pulse with surface-raised backgrounds
 * to match the dark theme.
 */

/* ── SkeletonLine ── horizontal bar placeholder */
export function SkeletonLine({
  width = "100%",
  height = "12px",
}: {
  width?: string;
  height?: string;
}) {
  return (
    <div
      className="animate-pulse rounded"
      style={{
        width,
        height,
        backgroundColor: "var(--color-surface-raised, #0d1117)",
      }}
    />
  );
}

/* ── SkeletonCard ── rectangular card placeholder with N lines */
export function SkeletonCard({ lines = 3 }: { lines?: number }) {
  return (
    <div
      className="rounded-xl border p-4 space-y-3"
      style={{
        backgroundColor: "var(--color-surface-raised, #0d1117)",
        borderColor: "var(--color-border-subtle, rgba(255,255,255,0.06))",
      }}
    >
      {/* Title line */}
      <SkeletonLine width="45%" height="16px" />

      {/* Body lines */}
      {Array.from({ length: lines }).map((_, i) => (
        <SkeletonLine
          key={i}
          width={i === lines - 1 ? "60%" : "100%"}
          height="12px"
        />
      ))}
    </div>
  );
}

/* ── SkeletonTable ── table rows placeholder */
export function SkeletonTable({
  rows = 5,
  cols = 3,
}: {
  rows?: number;
  cols?: number;
}) {
  return (
    <div
      className="rounded-xl border overflow-hidden"
      style={{
        borderColor: "var(--color-border-subtle, rgba(255,255,255,0.06))",
      }}
    >
      {/* Header row */}
      <div
        className="flex gap-4 px-4 py-3"
        style={{
          backgroundColor: "var(--color-surface-overlay, #161b22)",
        }}
      >
        {Array.from({ length: cols }).map((_, i) => (
          <SkeletonLine key={`h-${i}`} width="100%" height="14px" />
        ))}
      </div>

      {/* Data rows */}
      {Array.from({ length: rows }).map((_, rowIdx) => (
        <div
          key={rowIdx}
          className="flex gap-4 px-4 py-3"
          style={{
            borderTop: "1px solid var(--color-border-subtle, rgba(255,255,255,0.06))",
            backgroundColor: "var(--color-surface-base, #06080d)",
          }}
        >
          {Array.from({ length: cols }).map((_, colIdx) => (
            <SkeletonLine
              key={`r${rowIdx}-c${colIdx}`}
              width={colIdx === 0 ? "70%" : "50%"}
              height="12px"
            />
          ))}
        </div>
      ))}
    </div>
  );
}

/* ── SkeletonTerminal ── terminal output placeholder */
export function SkeletonTerminal({ lines = 10 }: { lines?: number }) {
  // Vary line widths to look like real terminal output
  const widths = [
    "35%", "80%", "62%", "90%", "48%",
    "75%", "55%", "85%", "40%", "70%",
    "60%", "95%", "42%", "78%", "50%",
  ];

  return (
    <div
      className="rounded-xl border p-4 space-y-2 font-mono"
      style={{
        backgroundColor: "var(--color-surface-base, #06080d)",
        borderColor: "var(--color-border-subtle, rgba(255,255,255,0.06))",
      }}
    >
      {/* Fake prompt header */}
      <div className="flex items-center gap-2 mb-3">
        <div
          className="w-2.5 h-2.5 rounded-full animate-pulse"
          style={{ backgroundColor: "var(--color-success, #3fb950)" }}
        />
        <SkeletonLine width="120px" height="10px" />
      </div>

      {/* Terminal lines */}
      {Array.from({ length: lines }).map((_, i) => (
        <SkeletonLine
          key={i}
          width={widths[i % widths.length]}
          height="10px"
        />
      ))}
    </div>
  );
}
