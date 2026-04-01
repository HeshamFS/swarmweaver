---
name: loop
description: Run a command or check on a recurring interval
when_to_use: When you need to monitor something periodically
context: fork
allowed-tools: Bash, Read, Grep
arguments: interval, command
---

# Recurring Task

Execute the following on a recurring basis:

**Interval**: ${interval}
**Command**: ${command}

Run the command, report the result, wait for the interval, and repeat.
Stop after 10 iterations or when the user interrupts.
