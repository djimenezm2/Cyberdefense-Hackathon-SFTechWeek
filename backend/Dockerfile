# Rootlane `backend` app image: FastAPI API + Semgrep CLI + Node 22 + the Juice Shop fork
# source for ephemeral replicas. Deployed on Akash at api.rootlane.xyz.
#
# Build context is the REPO ROOT (so the juiceshop/juice-shop submodule is in scope). Built by
# GitHub Actions and pushed to ghcr.io/djimenezm2/rootlane-backend.
#   docker build -f backend/Dockerfile -t rootlane-backend .
#
# All configuration comes from env at runtime (see backend/deploy/akash.sdl.yaml); no secrets in the image.

# ---- juiceshop-deps: Juice Shop fork source with its npm dependencies installed ----
FROM public.ecr.aws/docker/library/node:22-bookworm AS juiceshop-deps
WORKDIR /juice-shop
COPY juiceshop/juice-shop/ ./
RUN npm ci --no-audit --no-fund

# ---- runtime ----
FROM public.ecr.aws/docker/library/python:3.12-slim-bookworm

# Node 22 runtime (same Debian base as the juiceshop-deps stage).
COPY --from=public.ecr.aws/docker/library/node:22-bookworm-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=public.ecr.aws/docker/library/node:22-bookworm-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# uv from its official image (pinned).
COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_TOOL_DIR=/opt/uv-tools \
    UV_TOOL_BIN_DIR=/usr/local/bin

# Semgrep CLI in its own tool environment.
RUN uv tool install --no-cache semgrep

# Non-root runtime user with a writable home (Semgrep and npm write caches there).
RUN useradd --create-home --uid 10001 rootlane

WORKDIR /app

# Dependencies first (cached until the lockfile changes), then the project itself.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --no-cache
COPY backend/ ./
RUN uv sync --frozen --no-dev --no-cache

# Juice Shop fork source, writable by the runtime user so replicas can be built from it.
COPY --from=juiceshop-deps --chown=rootlane:rootlane /juice-shop /app/juice-shop

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
USER rootlane
EXPOSE 8000
CMD ["uvicorn", "rootlane_toolbox.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
