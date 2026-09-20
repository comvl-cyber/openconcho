# Honcho model administration — private server-side service.
# Multi-stage build: 1. python:3.11-slim installs deps; 2. python:3.11-slim runtime.
# Runs as non-root UID 1000, no shell, read-only rootfs.

# ---------- Builder stage ----------
FROM python:3.11-slim AS builder

WORKDIR /app

# Install uv for fast pip
RUN pip install --no-cache-dir uv==0.8.14

# Copy admin sources
COPY admin/server.py admin/test_server.py admin/requirements.txt ./

# Install dependencies into a virtual environment
RUN uv venv /app/.venv && \
    uv pip install --python /app/.venv/bin/python --no-cache -r requirements.txt

# ---------- Runtime stage ----------
FROM python:3.11-slim

# git + ssh client for GitOps writes via the Flux deploy key
RUN apt-get update && apt-get install -y --no-install-recommends git openssh-client && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --no-create-home --uid 1000 --shell /usr/sbin/nologin appuser

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder --chown=1000:1000 /app/.venv /app/.venv

# Copy admin source
COPY --chown=1000:1000 admin/server.py .

# Healthcheck runs inside the container network against the admin service
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s CMD ["/app/.venv/bin/python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8091/admin-api/session', timeout=5)"]

USER 1000

EXPOSE 8091

# Entrypoint: run the HTTP server
ENTRYPOINT ["/bin/sh", "-c", "mkdir -p /tmp/ssh && cp /home/nonroot/.ssh/identity /tmp/ssh/ && cp /home/nonroot/.ssh/known_hosts /tmp/ssh/ && chmod 600 /tmp/ssh/* && exec /app/.venv/bin/python server.py"]