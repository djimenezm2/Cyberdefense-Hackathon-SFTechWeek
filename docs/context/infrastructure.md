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
| Guild | Pending | CLI `@guildai/cli` 0.27.1 installed at `~/.local/bin/guild`; login, workspace, provider key and trigger key pending. Use BYOK (own Anthropic key) so usage does not draw on Guild tokens. |
| Domain | Propagating | `rootlane.xyz` registered at Porkbun; nameservers `alexa.ns.cloudflare.com`, `kobe.ns.cloudflare.com`. Cloudflare Free zone, SSL mode Flexible, Always Use HTTPS on. |

## Juice Shop fork

- Upstream: `juice-shop/juice-shop`. Ours: `djimenezm2/juice-shop` (`JUICE_SHOP_REPO`).
- Brought into this repo as a git submodule at `target/juice-shop`, pinned to a release tag.
- The production source the toolbox serves and patches is a working copy of that fork inside the image.
- Approved fixes go to the fork as a pull request from a branch `rootlane/<incident-id>` into `master`, opened with `GITHUB_TOKEN`. The PR is the record; production is patched by the toolbox at approval time, not by merging.

## Deployment

- One Docker image: Python toolbox + Node 22 Juice Shop (built from the fork) + Semgrep, processes run by supervisord.
- Image pushed to a public registry; Akash pulls it. Deployment described in `deploy/akash.sdl.yaml` and created through the Akash Console API.
- Public hostnames, each a proxied Cloudflare CNAME to the Akash provider ingress host, listed in the SDL `accept:` field:
  - `shop.rootlane.xyz` → Juice Shop
  - `api.rootlane.xyz` → toolbox API (the Guild integration base URL)
  - `app.rootlane.xyz` → dashboard
- Cloudflare terminates HTTPS (Flexible): browser ⇄ Cloudflare is HTTPS, Cloudflare ⇄ Akash is HTTP.
- Secrets are passed as Akash environment variables from the local `.env`, never baked into the image.
- Redeploy = new image tag + Akash deployment update. Applying an approved fix does not redeploy; it patches and restarts the target process inside the running container.

## Open

- Registry: GHCR under `djimenezm2` (needs a token with `write:packages`) or Docker Hub.
- Guild login and keys.
- DNS records once the Akash ingress host is known.
