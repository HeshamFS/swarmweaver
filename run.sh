#!/bin/bash
# SwarmWeaver Run Script
# Runs the swarmweaver CLI via uv

# Install deps if .venv is missing
if [ ! -d ".venv" ]; then
    echo "Environment not set up. Running setup first..."
    ./setup.sh
fi

uv run swarmweaver "$@"
