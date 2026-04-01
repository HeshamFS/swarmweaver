---
name: verify
description: Run tests and verify that recent changes work correctly
when_to_use: After implementing a feature or fix, to ensure correctness
context: inline
allowed-tools: Bash, Read, Grep, Glob
---

# Verification

1. Identify the test framework used in this project
2. Run the full test suite
3. If tests fail, analyze the failures and determine if they're related to recent changes
4. Run any linters or type checkers configured in the project
5. Verify that the application starts without errors (if applicable)

Report: which tests pass, which fail, and whether the failures are pre-existing or new.
