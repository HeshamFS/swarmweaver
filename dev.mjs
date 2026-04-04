/**
 * SwarmWeaver — single-command dev launcher.
 *
 * `node dev.mjs` (or `npm run dev`) does everything:
 *   1. Syncs Python deps via uv (creates .venv if missing)
 *   2. Installs frontend npm deps if needed
 *   3. Launches FastAPI backend + Next.js frontend
 *
 * All executables are resolved to absolute paths so no shell or
 * PATH lookup is needed (works on Windows cmd, PowerShell, bash).
 */

import { spawn, execSync } from "child_process";
import { dirname, join } from "path";
import { fileURLToPath } from "url";
import { existsSync } from "fs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const isWin = process.platform === "win32";

// ── Resolve absolute paths to executables ────────────────────────

// npm lives next to node
const npmCmd = join(dirname(process.execPath), isWin ? "npm.cmd" : "npm");

const frontendDir = join(__dirname, "frontend");
const nodeModules = join(frontendDir, "node_modules");

// Colors
const B = "\x1b[1m";
const R = "\x1b[0m";
const Y = "\x1b[33m";
const C = "\x1b[36m";
const G = "\x1b[32m";
const DIM = "\x1b[2m";
const RED = "\x1b[31m";

// ── Find uv executable ───────────────────────────────────────────

function findUv() {
  const name = isWin ? "uv.exe" : "uv";

  // Check PATH first
  try {
    const out = execSync(isWin ? "where uv" : "which uv", {
      encoding: "utf8",
      stdio: ["pipe", "pipe", "ignore"],
    });
    const resolved = out.trim().split(/\r?\n/)[0];
    if (resolved && existsSync(resolved)) return resolved;
  } catch {}

  // Check common install locations
  const extraDirs = isWin
    ? [join(process.env.USERPROFILE || "", ".cargo", "bin")]
    : [
        join(process.env.HOME || "", ".local", "bin"),
        join(process.env.HOME || "", ".cargo", "bin"),
      ];

  for (const dir of extraDirs) {
    const candidate = join(dir, name);
    if (existsSync(candidate)) return candidate;
  }

  return null;
}

// ── Helpers ──────────────────────────────────────────────────────

function log(msg) {
  console.log(`${B}[setup]${R} ${msg}`);
}

function run(cmd, args, opts = {}) {
  return new Promise((resolve, reject) => {
    const needsShell = isWin && cmd.endsWith(".cmd");
    const spawnCmd = needsShell ? `"${cmd}"` : cmd;
    const child = spawn(spawnCmd, args, {
      stdio: "inherit",
      cwd: __dirname,
      shell: needsShell,
      ...opts,
    });
    child.on("exit", (code) =>
      code === 0 ? resolve() : reject(new Error(`${cmd} exited with ${code}`))
    );
    child.on("error", reject);
  });
}

// ── Step 1: Python deps via uv ───────────────────────────────────

async function ensurePythonDeps(uvCmd) {
  log("Syncing Python dependencies via uv...");
  await run(uvCmd, ["sync"]);
  log(`${G}✓${R} Python dependencies ready`);
}

// ── Step 2: Frontend deps ────────────────────────────────────────

async function ensureFrontendDeps() {
  if (existsSync(join(nodeModules, "next"))) {
    log(`${G}✓${R} Frontend dependencies installed`);
    return;
  }
  log("Installing frontend dependencies...");
  await run(npmCmd, ["install"], { cwd: frontendDir });
  log(`${G}✓${R} Frontend dependencies installed`);
}

// ── Step 2.5: Install LSP servers if missing ────────────────────

async function ensureLspServers() {
  const { execSync: execS } = await import("child_process");

  // Core LSP servers needed for code intelligence
  const servers = [
    { check: "typescript-language-server", install: "npm install -g typescript-language-server typescript" },
    { check: "vscode-html-language-server", install: "npm install -g vscode-langservers-extracted" },
    { check: "pyright", install: "npm install -g pyright" },
  ];

  let needsInstall = false;
  for (const s of servers) {
    try {
      execS(isWin ? `where ${s.check}` : `which ${s.check}`, { stdio: "ignore" });
    } catch {
      needsInstall = true;
      break;
    }
  }

  if (!needsInstall) {
    log(`${G}✓${R} LSP servers installed`);
    return;
  }

  log("Installing LSP language servers (one-time setup)...");
  for (const s of servers) {
    try {
      execS(isWin ? `where ${s.check}` : `which ${s.check}`, { stdio: "ignore" });
      log(`  ${DIM}${s.check} — already installed${R}`);
    } catch {
      log(`  Installing ${s.check}...`);
      try {
        execS(s.install, { stdio: "inherit", timeout: 120_000 });
        log(`  ${G}✓${R} ${s.check} installed`);
      } catch (e) {
        log(`  ${RED}✗ Failed to install ${s.check} (non-fatal)${R}`);
      }
    }
  }
}

// ── Step 3: Launch servers ───────────────────────────────────────

const procs = [];

function launch(name, cmd, args, cwd) {
  const color = name === "backend" ? Y : C;
  const prefix = `${color}[${name}]${R} `;

  const needsShell = isWin && cmd.endsWith(".cmd");
  const spawnCmd = needsShell ? `"${cmd}"` : cmd;
  const child = spawn(spawnCmd, args, {
    cwd: cwd || __dirname,
    shell: needsShell,
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, FORCE_COLOR: "1" },
  });

  child.stdout.on("data", (data) => {
    for (const line of data.toString().split("\n")) {
      if (line.trim()) process.stdout.write(prefix + line + "\n");
    }
  });

  child.stderr.on("data", (data) => {
    for (const line of data.toString().split("\n")) {
      if (line.trim()) process.stderr.write(prefix + line + "\n");
    }
  });

  child.on("exit", (code) => {
    console.log(`${prefix}exited with code ${code}`);
  });

  procs.push(child);
}

function cleanup() {
  for (const p of procs) {
    if (!p.killed) {
      if (isWin) {
        try {
          execSync(`taskkill /pid ${p.pid} /f /t`, { stdio: "ignore" });
        } catch {}
      } else {
        p.kill("SIGTERM");
      }
    }
  }
  process.exit(0);
}

process.on("SIGINT", cleanup);
process.on("SIGTERM", cleanup);

// ── Main ─────────────────────────────────────────────────────────

async function main() {
  console.log(`\n${B}SwarmWeaver${R} ${DIM}— autonomous coding agent${R}\n`);

  // Find uv
  const uvCmd = findUv();
  if (!uvCmd) {
    console.error(
      `${RED}Error:${R} uv not found. Install it with:\n` +
        `  ${DIM}curl -LsSf https://astral.sh/uv/install.sh | sh${R}\n` +
        `  then restart your terminal or run: source $HOME/.local/bin/env`
    );
    process.exit(1);
  }
  log(`uv:  ${DIM}${uvCmd}${R}`);
  log(`npm: ${DIM}${npmCmd}${R}`);

  try {
    await ensurePythonDeps(uvCmd);
    await ensureFrontendDeps();
    await ensureLspServers();
  } catch (err) {
    console.error(`\n${RED}Setup failed:${R} ${err.message}`);
    process.exit(1);
  }

  console.log(`\n${B}Starting servers...${R}`);
  console.log(`  ${Y}Backend${R}   http://localhost:8000`);
  console.log(`  ${C}Frontend${R}  http://localhost:3000\n`);

  launch("backend", uvCmd, ["run", "uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]);
  launch("frontend", npmCmd, ["run", "dev"], frontendDir);
}

main();
