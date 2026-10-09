# Rootlane `juiceshop` app image: OWASP Juice Shop built from our fork + the Rootlane
# telemetry middleware. Deployed on Akash at juiceshop.rootlane.xyz.
#
# Build context is the REPO ROOT (so the submodule, the telemetry overlay and the patch
# are all in scope). Built by GitHub Actions and pushed to ghcr.io/djimenezm2/rootlane-juiceshop.
#   docker build -f juiceshop/Dockerfile -t rootlane-juiceshop .
#
# Telemetry is configured at runtime via env (INGEST_URL, INGEST_TOKEN). With them unset
# the shop runs normally and telemetry is a no-op.

# ---- builder: overlay telemetry, apply the server patch, build frontend + server ----
FROM public.ecr.aws/docker/library/node:24-bookworm AS builder
RUN apt-get update && apt-get install -y --no-install-recommends patch && rm -rf /var/lib/apt/lists/*
WORKDIR /juice-shop

# Juice Shop source from our pinned fork submodule.
COPY juiceshop/juice-shop/ ./

# Rootlane overlay: the telemetry module and the one-file server wiring patch.
COPY juiceshop/telemetry/telemetry.ts ./lib/telemetry.ts
COPY juiceshop/patches/server-telemetry.patch /tmp/server-telemetry.patch
RUN patch -p1 < /tmp/server-telemetry.patch

# The frontend's `sbom` step needs a dist/frontend/stats.json the production build does
# not emit, so it fails the install-time build. The SBOM is not needed to run the shop;
# neutralize it so `npm install`'s postinstall (which builds the frontend) succeeds.
RUN sed -i 's#"sbom": "cyclonedx-esbuild[^"]*"#"sbom": "echo skip-sbom"#' frontend/package.json

# Install (dev deps needed to compile). The postinstall builds the frontend here.
RUN npm install --no-audit --no-fund
# Compile the server explicitly (incl. build/lib/telemetry.js from our overlay). Unlike the
# postinstall's `build:server || cd .`, this fails loudly if the server does not compile.
RUN npm run build:server
# Drop dev dependencies for a lean runtime copy.
RUN npm prune --omit=dev && mkdir -p logs

# ---- runtime ----
FROM public.ecr.aws/docker/library/node:24-bookworm-slim
ENV NODE_ENV=production
WORKDIR /juice-shop
COPY --from=builder /juice-shop ./
EXPOSE 3000
# Juice Shop reads its port from config/env; it listens on 3000 by default.
CMD ["node", "build/app.js"]
