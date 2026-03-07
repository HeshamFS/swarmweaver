export interface CodebaseProfile {
  project_name?: string;
  languages?: Record<string, number>;
  frameworks?: string[];
  package_managers?: string[];
  entry_points?: Record<string, string>;
  key_directories?: Record<string, string>;
  existing_tests?: { count?: number; framework?: string; location?: string };
  build_commands?: Record<string, string>;
  [key: string]: unknown;
}

export interface ProfileViewProps {
  profile: CodebaseProfile | null;
  loading: boolean;
}

export function ProfileView({
  profile,
  loading,
}: ProfileViewProps) {
  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <span className="text-sm text-text-muted animate-pulse">Loading codebase profile...</span>
      </div>
    );
  }

  if (!profile || Object.keys(profile).length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <span className="text-sm text-text-muted">
          No codebase profile available. Run an analysis phase first.
        </span>
      </div>
    );
  }

  const languages = profile.languages ? Object.entries(profile.languages) : [];
  const frameworks = profile.frameworks || [];
  const keyDirs = profile.key_directories ? Object.entries(profile.key_directories) : [];
  const tests = profile.existing_tests;

  return (
    <div className="p-3 space-y-3">
      {/* Project name */}
      {profile.project_name && (
        <div className="rounded-lg border border-border-subtle bg-surface-raised p-3">
          <span className="text-xs text-text-muted block">Project</span>
          <span className="text-sm font-semibold text-text-primary">
            {profile.project_name}
          </span>
        </div>
      )}

      {/* Languages */}
      {languages.length > 0 && (
        <div className="rounded-lg border border-border-subtle bg-surface-raised p-3">
          <span className="text-xs text-text-muted font-medium uppercase tracking-wider block mb-2">
            Languages
          </span>
          <div className="space-y-1.5">
            {languages
              .sort(([, a], [, b]) => b - a)
              .map(([lang, pct]) => (
                <div key={lang} className="flex items-center gap-2">
                  <span className="text-xs text-text-primary font-mono w-20 truncate">
                    {lang}
                  </span>
                  <div className="flex-1 h-1.5 rounded-full bg-border-subtle overflow-hidden">
                    <div
                      className="h-full rounded-full bg-accent transition-all"
                      style={{ width: `${Math.min(pct, 100)}%` }}
                    />
                  </div>
                  <span className="text-[10px] text-text-muted font-mono w-8 text-right">
                    {pct}%
                  </span>
                </div>
              ))}
          </div>
        </div>
      )}

      {/* Frameworks */}
      {frameworks.length > 0 && (
        <div className="rounded-lg border border-border-subtle bg-surface-raised p-3">
          <span className="text-xs text-text-muted font-medium uppercase tracking-wider block mb-2">
            Frameworks
          </span>
          <div className="flex flex-wrap gap-1.5">
            {frameworks.map((fw) => (
              <span
                key={fw}
                className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-accent/10 text-accent border border-accent/20"
              >
                {fw}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Key directories */}
      {keyDirs.length > 0 && (
        <div className="rounded-lg border border-border-subtle bg-surface-raised p-3">
          <span className="text-xs text-text-muted font-medium uppercase tracking-wider block mb-2">
            Key Directories
          </span>
          <div className="space-y-1">
            {keyDirs.map(([dir, desc]) => (
              <div key={dir} className="flex items-baseline gap-2">
                <span className="text-xs text-accent font-mono flex-shrink-0">
                  {dir}
                </span>
                <span className="text-[10px] text-text-muted truncate">
                  {String(desc)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tests summary */}
      {tests && (
        <div className="rounded-lg border border-border-subtle bg-surface-raised p-3">
          <span className="text-xs text-text-muted font-medium uppercase tracking-wider block mb-2">
            Tests
          </span>
          <div className="flex items-center gap-4">
            {tests.count != null && (
              <div>
                <span className="text-lg font-bold text-text-primary font-mono">
                  {tests.count}
                </span>
                <span className="text-xs text-text-muted ml-1">tests</span>
              </div>
            )}
            {tests.framework && (
              <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-surface text-text-secondary border border-border-subtle">
                {tests.framework}
              </span>
            )}
            {tests.location && (
              <span className="text-xs text-text-muted font-mono">
                {tests.location}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
