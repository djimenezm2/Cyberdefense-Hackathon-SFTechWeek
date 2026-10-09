# Infrastructure

State as of 2026-10-09 ~13:40 PT. Secrets live only in each teammate's local `.env` (see `.env.example`).

## Services

| Service | State | Notes |
|---|---|---|
| ClickHouse Cloud | Ready | Service `cyberhack`, AWS us-west-2, 1 replica, 8–16 GiB autoscaling. HTTPS port 8443. Database `rootlane` created. |
| GitHub | Ready | Fork `djimenezm2/juice-shop` (master only). Fine-grained token scoped to that fork: Contents and Pull requests read/write, 7-day expiry. |
| Senso | Ready | Dedicated org for the event (search spans the whole org). API base `https://apiv2.senso.ai/api/v1`, header `X-API-Key`. |
| AkashML | Ready | Console at `playground.akashml.com`. OpenAI-compatible API at `https://api.akashml.com/v1`. |
| Akash Console | Ready | API at `https://console-api.akash.network`, header `x-api-key`. |
| Guild | Ready | CLI `@guildai/cli` 0.27.1 at `~/.local/bin/guild`, authenticated as `djimenezm2`. Workspace `djimenezm2/hackaton`. Managed LLM access with a 50M Guild-token balance. API trigger key pending (needs a published agent). |
| Domain | Ready | `rootlane.xyz` registered at Porkbun; nameservers `alexa.ns.cloudflare.com`, `kobe.ns.cloudflare.com`. Cloudflare Free zone, SSL mode Flexible, Always Use HTTPS on. |

## Juice Shop fork

- Upstream: `juice-shop/juice-shop`. Ours: `djimenezm2/juice-shop` (`JUICE_SHOP_REPO`).
- Brought into this repo as a git submodule at `juiceshop/juice-shop`, pinned to a release tag.
- The `juiceshop` app is built from the fork; the toolbox keeps a copy of the same source to build replicas and to prepare patches.
- Approved fixes go to the fork as a pull request from a branch `rootlane/<incident-id>` into `master`, opened with `GITHUB_TOKEN`. The PR is the record; the toolbox redeploys the `juiceshop` app from the patched source at approval time.

## Deployment

- Three images and three Akash deployments:
  - `juiceshop`: Juice Shop built from the fork + telemetry middleware (Node 22).
  - `toolbox`: Python FastAPI + Semgrep + Node 22 and the fork source for ephemeral replicas.
  - `dashboard`: static Vite build served by a small web server.
- GitHub Actions builds each image and pushes it to GHCR (`ghcr.io/djimenezm2/rootlane-<app>`); Akash pulls it. Each app keeps its Akash SDL in its own folder (`<app>/deploy/akash.sdl.yaml`) and created through the Akash Console API.
- Public hostnames, each a proxied Cloudflare CNAME to the Akash provider ingress host, listed in the SDL `accept:` field:
  - `juiceshop.rootlane.xyz` → Juice Shop
  - `api.rootlane.xyz` → toolbox API (the Guild integration base URL)
  - `app.rootlane.xyz` → dashboard
- Cloudflare terminates HTTPS (Flexible): browser ⇄ Cloudflare is HTTPS, Cloudflare ⇄ Akash is HTTP.
- Secrets are passed as Akash environment variables from the local `.env`, never baked into the image.
- Redeploy = new image tag + Akash deployment update. Applying an approved fix redeploys the `juiceshop` app from the patched source through the same path.

## Open

- GHCR package visibility set to public after the first build.
- Guild API trigger key.
- DNS records once the Akash ingress host is known.
