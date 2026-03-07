# ============================================================
# Stage 1: Backend – install Python dependencies
# ============================================================
FROM python:3.11-slim AS backend

# Install uv for fast, reproducible dependency installs
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

# Copy all Python source files and directories
COPY server.py autonomous_agent_demo.py web_search_server.py ./
COPY cli/        cli/
COPY api/        api/
COPY core/       core/
COPY hooks/      hooks/
COPY state/      state/
COPY features/   features/
COPY services/   services/
COPY utils/      utils/
COPY prompts/    prompts/
COPY templates/  templates/
COPY scripts/    scripts/

# ============================================================
# Stage 2: Frontend – build the Next.js application
# ============================================================
FROM node:20-alpine AS frontend

WORKDIR /app/frontend

COPY frontend/ .
RUN npm install && npm run build

# ============================================================
# Stage 3: Runtime – combine backend + frontend
# ============================================================
FROM python:3.11-slim AS runtime

# Install Node.js 20.x
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get purge -y curl \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy Python environment from backend stage
COPY --from=backend /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=backend /usr/local/bin /usr/local/bin
COPY --from=backend /app /app

# Copy Next.js build output from frontend stage
COPY --from=frontend /app/frontend/.next        frontend/.next
COPY --from=frontend /app/frontend/public       frontend/public
COPY --from=frontend /app/frontend/package.json frontend/package.json
COPY --from=frontend /app/frontend/node_modules frontend/node_modules
COPY --from=frontend /app/frontend/next.config.ts frontend/next.config.ts

# Create the generations directory so the volume mount has a target
RUN mkdir -p /app/generations

EXPOSE 3000 8000

# Entrypoint: start both the FastAPI backend and the Next.js frontend
COPY <<'ENTRYPOINT' /app/entrypoint.sh
#!/bin/bash
set -e

# Start uvicorn (FastAPI backend) in the background
uvicorn server:app --host 0.0.0.0 --port 8000 &

# Start Next.js frontend in the foreground
cd /app/frontend
npx next start --hostname 0.0.0.0 --port 3000
ENTRYPOINT

RUN chmod +x /app/entrypoint.sh

CMD ["/app/entrypoint.sh"]
