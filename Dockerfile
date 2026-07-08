# syntax=docker/dockerfile:1

# ── Stage 1: build the React frontend ────────────────────────────────────────
FROM node:22-slim AS frontend
WORKDIR /app/frontend
# Install deps first (cached until the lockfile changes), then build.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build   # → /app/frontend/dist

# ── Stage 2: Python runtime serving both the API and the built UI ────────────
FROM python:3.14-slim AS runtime

# uv for a fast, reproducible install from uv.lock.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    MPLBACKEND=Agg \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    # SQLite lives on the persistent /home volume (App Service Files); this only
    # survives restarts when WEBSITES_ENABLE_APP_SERVICE_STORAGE=true is set.
    DATA_DIR=/home/data \
    # App Service terminates TLS, so the session cookie must be Secure in prod.
    # Local `docker run` over http should pass -e COOKIE_SECURE=0.
    COOKIE_SECURE=1

WORKDIR /app

# Install dependencies against the lockfile first, without the app itself, so
# this layer is cached until the lockfile changes.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Now the application source, plus the built frontend from stage 1.
COPY retirement_sim/ ./retirement_sim/
COPY README.md ./
COPY --from=frontend /app/frontend/dist ./frontend/dist
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

EXPOSE 8000
# main() binds 0.0.0.0 and honors $PORT (injected by App Service / `docker run`).
CMD ["retirement-sim-web"]
