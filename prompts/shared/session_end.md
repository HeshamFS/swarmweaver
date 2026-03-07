## ENDING THIS SESSION (MANDATORY)

Before your context fills up, you MUST do the following:

### 1. Commit All Working Code
```bash
git add .
git commit -m "Session progress: [brief summary of what was accomplished]

- [specific changes made]
- [tasks completed]
- Updated task list
"
```

### 2. Update Progress Notes
Update `.swarmweaver/claude-progress.txt` with:
- What you accomplished this session
- Which tasks you completed
- Any issues discovered or fixed
- What should be worked on next
- Current completion status (e.g., "12/20 tasks done")

### 3. Save Task List
Ensure `.swarmweaver/task_list.json` (or `.swarmweaver/feature_list.json`) is saved with accurate task statuses.

### 4. Reflect & Save Learnings

Before ending, reflect on this session and save what you learned to `.swarmweaver/session_reflections.json`.
This file is automatically collected by the harness and saved to cross-project memory so future sessions benefit from your experience.

Write `.swarmweaver/session_reflections.json` with 1–5 entries:

```json
[
  {
    "category": "pattern",
    "content": "Brief description of what you learned or discovered",
    "tags": ["relevant", "technology", "tags"]
  }
]
```

**Categories:**
- `"pattern"` — Useful approach that worked well (e.g., "Using `--legacy-peer-deps` fixes npm conflicts in Next.js 15 projects")
- `"mistake"` — Something that failed or wasted time (e.g., "Don't use React.lazy with server components — causes hydration errors")
- `"solution"` — A specific fix for a specific problem (e.g., "ESM chunk loading errors fixed by replacing react-markdown with custom component")
- `"preference"` — User preferences or project conventions (e.g., "User prefers Tailwind CSS v4 with CSS variables, no utility classes in JS")

**Rules:**
- Only save genuinely useful learnings — things that would help a future agent on a similar project
- Be specific, not vague: "Vitest requires `globals: true` in vite.config" not "Testing was hard"
- Include technology/framework names in tags for better matching
- If the user explicitly asked you to remember something, save it as a `"preference"` entry
- If nothing noteworthy happened, write an empty array `[]`

### 5. Leave Clean State
- Ensure no uncommitted changes
- Leave app in working state (no broken features)
- No running processes left hanging (the harness will clean up, but be tidy)

---

**Remember:** You have unlimited time across many sessions. Focus on quality over speed.
The next agent will continue from here with a fresh context window.
