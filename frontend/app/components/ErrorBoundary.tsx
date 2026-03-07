"use client";

import { Component, ReactNode } from "react";

interface Props {
  children: ReactNode;
  /** Label shown in the error card header (e.g. "Terminal", "Task Panel") */
  fallbackLabel?: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

/**
 * Panel-level error boundary.
 * Catches render errors in children and shows a dark-themed recovery card
 * with the error message and a Retry button.
 *
 * Usage:
 *   <ErrorBoundary fallbackLabel="Terminal">
 *     <Terminal />
 *   </ErrorBoundary>
 */
export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // Log to console for debugging; could be wired to an observability service
    console.error(
      `[ErrorBoundary${this.props.fallbackLabel ? `: ${this.props.fallbackLabel}` : ""}]`,
      error,
      info.componentStack,
    );
  }

  private handleRetry = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      const label = this.props.fallbackLabel ?? "Panel";

      return (
        <div
          className="flex items-center justify-center p-6 rounded-xl border"
          style={{
            backgroundColor: "var(--color-surface-raised, #0d1117)",
            borderColor: "var(--color-border-subtle, rgba(255,255,255,0.06))",
            minHeight: 160,
          }}
        >
          <div className="text-center max-w-md space-y-4">
            {/* Icon */}
            <div
              className="mx-auto flex h-12 w-12 items-center justify-center rounded-full"
              style={{ backgroundColor: "rgba(248, 81, 73, 0.12)" }}
            >
              <svg
                width="24"
                height="24"
                viewBox="0 0 24 24"
                fill="none"
                stroke="var(--color-error, #f85149)"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
            </div>

            {/* Heading */}
            <h3
              className="text-sm font-semibold"
              style={{ color: "var(--color-text-primary, #f0f2f5)" }}
            >
              {label} — Something went wrong
            </h3>

            {/* Error message */}
            {this.state.error && (
              <p
                className="text-xs font-mono leading-relaxed break-all"
                style={{ color: "var(--color-text-muted, #484f58)" }}
              >
                {this.state.error.message}
              </p>
            )}

            {/* Retry button */}
            <button
              onClick={this.handleRetry}
              className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-medium rounded-lg transition-colors cursor-pointer"
              style={{
                backgroundColor: "var(--color-accent, #f97316)",
                color: "#fff",
              }}
              onMouseEnter={(e) =>
                (e.currentTarget.style.backgroundColor =
                  "var(--color-accent-hover, #fb923c)")
              }
              onMouseLeave={(e) =>
                (e.currentTarget.style.backgroundColor =
                  "var(--color-accent, #f97316)")
              }
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <polyline points="23 4 23 10 17 10" />
                <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
              </svg>
              Retry
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
