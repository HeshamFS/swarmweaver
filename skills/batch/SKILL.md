---
name: batch
description: Execute a task across multiple files or directories in parallel
when_to_use: When the same change needs to be applied to many files
context: fork
allowed-tools: Read, Edit, Write, Bash, Grep, Glob
arguments: pattern, task
---

# Batch Operation

Apply the following task to all files matching the pattern.

**Pattern**: ${pattern}
**Task**: ${task}

## Steps

1. Find all files matching the pattern using Glob
2. For each file:
   a. Read the current content
   b. Apply the requested change
   c. Write the updated content
3. After all files are processed, run any relevant tests
4. Report: how many files were changed, what was done to each
