#!/bin/bash
# SwarmWeaver Setup Script
# Installs dependencies using uv (fast Python package manager)

set -e

echo "=================================="
echo "  SwarmWeaver - Setup"
echo "=================================="
echo

# ── Install uv if missing ─────────────────────────────────────────
if ! command -v uv &> /dev/null; then
    echo "uv not found — installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Reload PATH to pick up the freshly installed uv
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    if ! command -v uv &> /dev/null; then
        echo "Error: uv installation failed or PATH not updated."
        echo "Install manually: https://docs.astral.sh/uv/getting-started/installation/"
        exit 1
    fi
fi

echo "Using $(uv --version)"
echo

# ── Sync all dependencies ─────────────────────────────────────────
# Creates .venv if needed, installs from pyproject.toml (including the
# swarmweaver CLI entry point), and writes/updates uv.lock.
echo "Syncing dependencies..."
uv sync

echo
echo "=================================="
echo "  Setup Complete!"
echo "=================================="
echo
echo "To run the agent (pick one):"
echo
echo "  Option A — via uv (uses .venv):"
echo "    uv run swarmweaver --help"
echo
echo "  Option B — activate the venv directly:"
echo "    source .venv/bin/activate"
echo "    swarmweaver --help"
echo
echo "  Option C — install globally with pip:"
echo "    pip install -e ."
echo "    swarmweaver --help"
echo
echo "Or start the full dev stack (backend + frontend):"
echo "  npm run dev"
echo
