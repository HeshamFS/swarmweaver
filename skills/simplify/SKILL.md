---
name: simplify
description: Review changed code for reuse, quality, and efficiency, then fix any issues found
when_to_use: After completing a feature or refactor, to clean up and improve code quality
context: inline
allowed-tools: Read, Grep, Glob, Edit, Bash
---

# Code Simplification Review

Review the recently changed code in this project for three aspects:

## 1. Reuse Opportunities
- Are there duplicated patterns that could be extracted into shared utilities?
- Are there existing project utilities that the new code could use instead of reimplementing?

## 2. Code Quality
- Are there overly complex functions that should be split?
- Are variable/function names clear and consistent with the project's conventions?
- Are there unnecessary abstractions or premature optimizations?

## 3. Efficiency
- Are there N+1 query patterns or unnecessary iterations?
- Are there resource leaks (unclosed files, connections)?
- Could any synchronous operations be async?

After reviewing, fix any issues you find. Prioritize changes that reduce complexity.
