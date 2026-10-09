# Rootlane backend

FastAPI service at `api.rootlane.xyz`: telemetry ingest, ClickHouse storage, continuous analysis, incident workflow and the tool API used by the Guild agent.

Entry point: `rootlane_toolbox.api.app:create_app` (alias `rootlane_toolbox.app:create_app`). Tests: `uv run --extra dev pytest -q`.

## Layers

| Layer | Modules | Responsibility |
| --- | --- | --- |
| `api/` | `app`, `ingest`, `dashboard`, `stream`, `tools`, `deps` | HTTP surface: routers, auth, app assembly, shared state |
| `analysis/` | `features`, `decider`, `analyzer` | Window features, triage decision, the analysis loop |
| `storage/` | `db`, `store`, `migrate`, `schema/` | ClickHouse clients, incident and audit store, SQL migrations |
| `integrations/` | `guild`, `semgrep_runner` | External services: Guild trigger, Semgrep |
| `core/` | `config`, `models`, `guards`, `broker` | Settings, contract models, safety guards, event broker |

`__main__.py` is the `migrate` CLI.

## Flow

```
juiceshop telemetry
  -> api/ingest -> storage (http_requests, auth_events)
                     -> analysis (features -> decider -> analyzer)
                          -> incidents (storage/store)
                               -> api/dashboard + api/stream (SSE) -> UI

Guild agent -> api/tools -> core/guards -> storage / integrations (Semgrep)
```
