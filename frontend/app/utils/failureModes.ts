export interface FailureMode {
  code: string;
  description: string;
  recovery: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  roles: string[];
}

export const FAILURE_MODES: Record<string, FailureMode> = {
  // Shared across multiple roles
  PATH_BOUNDARY_VIOLATION: {
    code: 'PATH_BOUNDARY_VIOLATION',
    description: 'Agent attempting to access files outside assigned scope',
    recovery: 'Stop immediately, report scope conflict to orchestrator',
    severity: 'critical',
    roles: ['builder', 'scout', 'reviewer', 'lead'],
  },
  TEST_FAILURE_LOOP: {
    code: 'TEST_FAILURE_LOOP',
    description: 'Same test failing 3+ consecutive attempts',
    recovery: 'Revert last change, try alternative approach',
    severity: 'high',
    roles: ['builder', 'reviewer'],
  },
  DEPENDENCY_DEADLOCK: {
    code: 'DEPENDENCY_DEADLOCK',
    description: 'Circular dependency preventing progress',
    recovery: 'Report to orchestrator, request scope adjustment',
    severity: 'high',
    roles: ['builder', 'lead'],
  },
  SPEC_DRIFT: {
    code: 'SPEC_DRIFT',
    description: 'Implementation or output diverging from specification',
    recovery: 'Re-read spec, revert uncommitted changes, restart task',
    severity: 'high',
    roles: ['builder', 'scout', 'reviewer', 'lead'],
  },
  UNBOUNDED_LOOP: {
    code: 'UNBOUNDED_LOOP',
    description: 'Retry or coordination loop without progress for 5+ minutes',
    recovery: 'Break loop, commit partial progress, report status',
    severity: 'high',
    roles: ['builder', 'lead'],
  },
  MERGE_CONFLICT_CASCADE: {
    code: 'MERGE_CONFLICT_CASCADE',
    description: 'Multiple merge conflicts across files',
    recovery: 'Stop merging, request orchestrator intervention',
    severity: 'high',
    roles: ['builder', 'lead', 'merger'],
  },
  RESOURCE_EXHAUSTION: {
    code: 'RESOURCE_EXHAUSTION',
    description: 'Approaching token/budget limits',
    recovery: 'Commit current progress, summarize remaining work',
    severity: 'high',
    roles: ['builder', 'scout', 'reviewer', 'lead', 'merger'],
  },
  STALE_CONTEXT: {
    code: 'STALE_CONTEXT',
    description: 'Working with outdated file state',
    recovery: 'Re-read all modified files, verify assumptions',
    severity: 'medium',
    roles: ['builder', 'scout', 'reviewer'],
  },
  INCOMPLETE_COVERAGE: {
    code: 'INCOMPLETE_COVERAGE',
    description: 'Missing critical files or directories in scope',
    recovery: 'Re-scan file scope, check all relevant paths',
    severity: 'medium',
    roles: ['scout', 'reviewer'],
  },
  SCOPE_CREEP: {
    code: 'SCOPE_CREEP',
    description: 'Analysis or work expanding beyond assigned scope',
    recovery: 'Document out-of-scope items, stay focused',
    severity: 'medium',
    roles: ['scout', 'lead'],
  },

  // Builder-specific
  BUILD_FAILURE_SPIRAL: {
    code: 'BUILD_FAILURE_SPIRAL',
    description: 'Build errors increasing after each fix attempt',
    recovery: 'Revert to last working state, analyze root cause',
    severity: 'high',
    roles: ['builder'],
  },
  INCOMPLETE_VERIFICATION: {
    code: 'INCOMPLETE_VERIFICATION',
    description: 'Tests pass but acceptance criteria unmet',
    recovery: 'Re-read acceptance criteria, add missing test cases',
    severity: 'medium',
    roles: ['builder'],
  },

  // Scout-specific
  ANALYSIS_PARALYSIS: {
    code: 'ANALYSIS_PARALYSIS',
    description: 'Spending >10min on single file without output',
    recovery: 'Write preliminary findings, move to next file',
    severity: 'medium',
    roles: ['scout'],
  },
  OUTPUT_FORMAT_ERROR: {
    code: 'OUTPUT_FORMAT_ERROR',
    description: 'Generating malformed JSON output',
    recovery: 'Validate JSON before writing, use templates',
    severity: 'medium',
    roles: ['scout'],
  },

  // Reviewer-specific
  FALSE_POSITIVE_FLOOD: {
    code: 'FALSE_POSITIVE_FLOOD',
    description: 'Flagging too many non-issues',
    recovery: 'Increase severity threshold, focus on criticals',
    severity: 'medium',
    roles: ['reviewer'],
  },
  SEVERITY_MISCALIBRATION: {
    code: 'SEVERITY_MISCALIBRATION',
    description: 'All issues marked same severity',
    recovery: 'Re-calibrate using severity definitions',
    severity: 'low',
    roles: ['reviewer'],
  },

  // Merger-specific
  TEST_REGRESSION: {
    code: 'TEST_REGRESSION',
    description: 'Tests fail after merge',
    recovery: 'Revert merge, report failing tests to source workers',
    severity: 'high',
    roles: ['merger'],
  },
  BRANCH_CORRUPTION: {
    code: 'BRANCH_CORRUPTION',
    description: 'Branch in inconsistent state after merge attempt',
    recovery: 'Reset to pre-merge state, report to orchestrator',
    severity: 'critical',
    roles: ['merger'],
  },
  STALE_BRANCH: {
    code: 'STALE_BRANCH',
    description: 'Branch too far behind main for clean merge',
    recovery: 'Rebase before merge, re-verify',
    severity: 'medium',
    roles: ['merger'],
  },
  CIRCULAR_DEPENDENCY: {
    code: 'CIRCULAR_DEPENDENCY',
    description: 'Merge order creates circular dependencies',
    recovery: 'Report to lead agent for resequencing',
    severity: 'high',
    roles: ['merger'],
  },
  SEMANTIC_CONFLICT: {
    code: 'SEMANTIC_CONFLICT',
    description: 'No git conflict but logic is incompatible',
    recovery: 'Flag for human review, do not auto-merge',
    severity: 'high',
    roles: ['merger'],
  },
  INCOMPLETE_MERGE: {
    code: 'INCOMPLETE_MERGE',
    description: 'Merge partially applied, inconsistent state',
    recovery: 'Revert to clean state, retry from scratch',
    severity: 'high',
    roles: ['merger'],
  },

  // Lead-specific
  COORDINATION_DEADLOCK: {
    code: 'COORDINATION_DEADLOCK',
    description: 'Workers waiting on each other',
    recovery: 'Identify cycle, reassign tasks to break deadlock',
    severity: 'critical',
    roles: ['lead'],
  },
  SCOPE_OVERLAP_CONFLICT: {
    code: 'SCOPE_OVERLAP_CONFLICT',
    description: 'Multiple workers editing same files',
    recovery: 'Stop conflicting workers, reassign scopes',
    severity: 'critical',
    roles: ['lead'],
  },
  WORKER_ABANDONMENT: {
    code: 'WORKER_ABANDONMENT',
    description: 'Worker unresponsive for >5 minutes',
    recovery: 'Escalate to watchdog, reassign tasks',
    severity: 'high',
    roles: ['lead'],
  },
  PLAN_DEVIATION: {
    code: 'PLAN_DEVIATION',
    description: 'Execution diverging from swarm plan',
    recovery: 'Pause workers, re-evaluate plan',
    severity: 'high',
    roles: ['lead'],
  },
  ESCALATION_FLOOD: {
    code: 'ESCALATION_FLOOD',
    description: 'Too many simultaneous escalations',
    recovery: 'Prioritize by severity, batch similar issues',
    severity: 'medium',
    roles: ['lead'],
  },
};

// Regex pattern to match failure mode codes in output
export const FAILURE_MODE_PATTERN = new RegExp(
  `\\b(${Object.keys(FAILURE_MODES).join('|')})\\b`,
  'g'
);

export function getFailureMode(code: string): FailureMode | undefined {
  return FAILURE_MODES[code];
}

export function detectFailureModes(text: string): FailureMode[] {
  const matches = text.match(FAILURE_MODE_PATTERN);
  if (!matches) return [];
  return [...new Set(matches)]
    .map(code => FAILURE_MODES[code])
    .filter(Boolean);
}
