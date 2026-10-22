# syntax=docker/dockerfile:1.7
# API image: production-like, also for on-premise installs. Build from the repo root:
#   docker build -f infra/docker/api.Dockerfile .
# The base is the pinned uv image (Python 3.12, Debian bookworm slim); the source keeps the
# repository layout, so docs/input-data.md and the connector mappings resolve as in development.

FROM ghcr.io/astral-sh/uv:0.5.11-python3.12-bookworm-slim AS build
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# Dependencies first (cached until a lockfile or pyproject changes).
COPY pyproject.toml uv.lock ./
COPY packages/schema/pyproject.toml packages/schema/
COPY packages/constraint_engine/pyproject.toml packages/constraint_engine/
COPY packages/connectors/pyproject.toml packages/connectors/
COPY apps/api/pyproject.toml apps/api/
COPY workers/pyproject.toml workers/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package cip-api --no-install-workspace
COPY packages packages
COPY apps/api apps/api
COPY workers workers
COPY docs/input-data.md docs/input-data.md
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package cip-api

FROM ghcr.io/astral-sh/uv:0.5.11-python3.12-bookworm-slim AS runtime
RUN groupadd --gid 10001 cip && useradd --uid 10001 --gid cip --no-create-home cip
WORKDIR /app
COPY --from=build --chown=cip:cip /opt/venv /opt/venv
COPY --from=build --chown=cip:cip /app /app
RUN mkdir -p /app/var/data && chown cip:cip /app/var/data
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 CIP_ENV=production
# Which source the image was built from (scripts/source_id.sh); scripts/check_images.sh compares it.
ARG CIP_SOURCE_ID=unknown
LABEL org.opencontainers.image.revision=$CIP_SOURCE_ID
ENV CIP_SOURCE_ID=$CIP_SOURCE_ID
USER cip
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --retries=5 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/meta', timeout=2)"]
CMD ["uvicorn", "cip_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
