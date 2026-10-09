# Hackathon context

Cyberdefense Hackathon #SFTechWeek — Friday 2026-10-09, AWS Builder Loft, 525 Market St, 2nd floor,
San Francisco. Organized by tokens& (Andy Tran, Lead Organizer). Verified against tokensand.com/cyberhack,
luma.com/cyberhack and the event Discord on 2026-10-09 around noon PT.

## Schedule (PT)

11:00 kickoff and hacking · 1:30 lunch · **4:30 PM public submission deadline** (the site config
closes at 5:00 PM; treat it as emergency margin only) · 5:00 finalist demos and judging · 7:00 awards.

## Challenge (verbatim, #announcements, edited 11:19)

> Build agents that preserve what matters. Ship an autonomous agent that does real work on the open
> web. Your agent(s) need to take real action — publish, monitor, orchestrate, transact — grounded in
> truthful sources. Use 3+ sponsor tools.
>
> What should your agent know before it writes? As you build today, think about the context your
> agent is working with. What does it need to understand about the application? Which security
> boundaries could its changes affect? And which decisions are you leaving it to guess?

Tracks: Threat discovery, Attack intelligence, Autonomous remediation, Continuous defense.

## Submission (https://tokensand.com/cyberhack/submit, tokens& login required)

Required: project name (2–80 chars); description of what we built, how it works and **how each tool
was used**; GitHub repo `github.com/owner/repo` accessible to judges; demo video URL (~3 min — use
YouTube unlisted, galleries have failed to show Loom/Drive links); each teammate's full name and a
distinct email; tools picked from a catalog. Optional: website, screenshot (≤5 MB), technical
architecture, judge-access instructions. Editable after submitting.

No general judging criteria are published. There is a finalist cut before demos, so the README and
the video must convince on their own.

## Prizes and what each sponsor asks for

| Sponsor | Prize | What they judge / provide |
|---|---|---|
| Pi | Top overall: $1000 / $600 / $400 gift cards | No product or tech access at this event. Do not list Pi as a tool. Its thesis: fix once, stays fixed; vulnerabilities that recur. |
| Guild.ai | Best use of Guild to host and run agents: $1000 + 2×$500 | docs.guild.ai. See `docs/research/guild.md`. |
| ClickHouse | Best use of real-time analytics: 1st $1000 + $500 credits, 2nd $500 + $300 credits, 3rd $250 | "Real-time backbone for cyberdefense: logs, network events or agent telemetry into instant detections, attack timelines or automated responses." Data scale, query latency, how directly data drives detection/remediation. Their deck: "Security is a data problem" (cloud audit logs, identity events, endpoint telemetry, network flows). |
| Semgrep | Best vulnerability detected by Semgrep in AI-generated code: $1000 / $500 + 20 credits each | Install Guardian: `claude plugin install semgrep@claude-plugins-official`, restart, log in. Show findings detected and resolved in its logs. **Bonus for new custom rules.** |
| Senso | Best use of Senso: $3k / $1k / $1k in credits | Shared verified-context memory for agents. See `docs/research/senso-akashml.md` and the Senso hackathon memory guide (below). |
| Akash | Best use of Akash | akash.network/docs, akashml.com/docs/getting-started. |
| ElevenLabs | — | Credit codes ran out on 2026-10-08. |

OpenAI, MongoDB and AWS appear as partners but have no channel, prize or access announced.

## Credits

Promo codes are shared in the team chat, not in this public repo. ClickHouse Cloud credits require a
**fresh email** that never had a ClickHouse Cloud account. Senso gives new organizations $100.
AkashML trial credits require card verification. Akash Console has a $1 free trial (30 days,
deployments live ≤24 h). Guild has no documented free allowance; the sponsor is being asked.

## Senso hackathon memory guide (from #senso)

Senso as one memory for all your agents: `npm i -g @senso-ai/cli`, `senso login`, one folder per event.
Habits: a `CURRENT.md` progress doc rewritten in place; `senso search` before asking a person; hand
work between agents by document ID; version ideas instead of overwriting; label every number as
measured, fixture or guessed. Trap: search spans the whole organization, not the folder — use a fresh
organization or `--content-ids … --require-scoped-ids`. Every search spends credits.

## Judge themes heard in the room

Identity: who the actor is, on whose behalf it acts, how it authenticates. ClickHouse as the data
engine. Speed and security. Vulnerabilities that recur. Knowledge scattered across docs, Slack and
conversations with no trace of what happened. Unverified patches (no sandbox). Agents without control
or traces of their actions. Very capable zero-day agents running unchecked. Disaster recovery. Model
energy use; open models only where they make sense.
