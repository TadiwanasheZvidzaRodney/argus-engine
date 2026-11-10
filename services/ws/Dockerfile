# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:0.5.11-python3.12-bookworm-slim AS builder

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
COPY packages/python/argus-core ./packages/python/argus-core
COPY services/api ./services/api
COPY services/ws ./services/ws
COPY services/worker ./services/worker

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package argus-ws

# --- Final image ---
FROM python:3.12-slim-bookworm

WORKDIR /app

RUN groupadd -g 1001 argus && useradd -u 1001 -g argus -m -s /bin/bash argus

COPY --from=builder --chown=argus:argus /app/.venv /app/.venv
COPY --from=builder --chown=argus:argus /app/services/ws /app/services/ws
COPY --from=builder --chown=argus:argus /app/packages/python/argus-core /app/packages/python/argus-core

USER argus
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    ARGUS_ENV=prod

EXPOSE 8001

HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/healthz')" || exit 1

ENTRYPOINT ["uvicorn", "argus_ws.main:app_factory", "--factory", "--host", "0.0.0.0", "--port", "8001", "--workers", "2"]
