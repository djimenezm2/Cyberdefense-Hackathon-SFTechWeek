# Rootlane diagrams

Rendered with Mermaid CLI 11.4.2 (`mmdc -b white -w 2000`); edit the `.mmd` source and re-render.

1. [System architecture](1-system-architecture.png) ([source](src/1-system-architecture.mmd)) — the hackathon deployment: public hosts, runtime on Akash and Vercel, and the managed services the toolbox API and Guild agent call.
2. [GitHub, CI and deployment](2-github-ci-deployment.png) ([source](src/2-github-ci-deployment.mmd)) — how the team and their agents work through the repo, which Actions build which images, and how they reach Akash, Vercel and DNS.
3. [Incident lifecycle](3-incident-lifecycle.png) ([source](src/3-incident-lifecycle.mmd)) — sequence from telemetry and triage through the agent's investigation, verified fix, human approval and redeploy.
4. [Product integration](4-product-integration.png) ([source](src/4-product-integration.mmd)) — Rootlane as a product: the five integration points a customer company connects to the platform.
5. [Internal pipeline](5-internal-pipeline.png) ([source](src/5-internal-pipeline.mmd)) — the observe, investigate, prove, decide and ship stages from signal to verified fix, with the audit trail.
