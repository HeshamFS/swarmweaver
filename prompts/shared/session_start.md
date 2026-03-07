## SESSION START (MANDATORY)

This is a FRESH context window - you have no memory of previous sessions.
All context must come from files on disk.

### Orient Yourself

```bash
# 1. See your working directory
pwd

# 2. List files to understand project structure
ls -la

# 3. Read progress notes from previous sessions (if any)
cat .swarmweaver/claude-progress.txt 2>/dev/null || echo "No progress notes yet"

# 4. Check recent git history
git log --oneline -20 2>/dev/null || echo "No git history yet"

# 5. Check task progress
cat .swarmweaver/task_list.json 2>/dev/null | head -50 || cat .swarmweaver/feature_list.json 2>/dev/null | head -50 || echo "No task list yet"
```

### Knowledge Resources Available

You have access to documentation and web search capabilities. USE THEM when needed.

**Local Documentation** (if docs/ folder exists):
- Search docs with: `Grep(pattern="search term", path="docs/")`
- Read specific files: `Read(file_path="docs/filename.md")`

**Web Search** (for current/external information):
- Use the `mcp__web_search__search` tool to search the web
- Useful for: latest API docs, troubleshooting, best practices
- **Don't guess - search!** Web search is fast and free.

**Tool Usage:**
- **Edit/Write:** If the file is not already in your context, use Read first. The SDK requires reading a file before editing or writing to it.
- **Puppeteer selectors:** Use standard CSS selectors. Avoid Playwright-specific syntax like `:has-text()` — use `[aria-label="..."]` or match by element type and attributes instead.

**Browser Automation** (for UI testing):
- Use the MCP puppeteer tools: `mcp__puppeteer__puppeteer_navigate`, `_click`, `_fill`, `_screenshot`, etc.
- These tools are **pre-configured and ready to use** — do NOT install Playwright, Puppeteer, or Selenium manually
- Navigate to your app, click elements, fill forms, take screenshots to verify features work
- **Use Puppeteer sparingly.** Prefer `npm run build` for per-task verification. Batch 2–3 features before a single browser check.

**WSL Filesystem Note** (if running on WSL/Windows):
- If the project is on a Windows drive (`/mnt/c/`, `/mnt/d/`), `npm install` may fail with ENOTDIR errors
- **Workaround**: Create node_modules on the Linux filesystem and symlink it:
  ```bash
  PROJECT_NAME=$(basename "$PWD")
  mkdir -p "/home/$USER/.npm-cache/$PROJECT_NAME/node_modules"
  ln -sfn "/home/$USER/.npm-cache/$PROJECT_NAME/node_modules" ./node_modules
  npm install
  ```
- Or use `init.sh` if it exists — it handles this automatically
- If init.sh fails with `invalid option` or `command not found`, run `sed -i 's/\r$//' init.sh` to fix CRLF line endings
- **NEVER create git worktrees, copy the project, or work outside the project directory.**
  ALL files must be written to the project directory you were given.

{agent_memory}
