/*
 * Rootlane telemetry middleware for OWASP Juice Shop (the `juiceshop` app).
 *
 * Overlaid into the fork at build time as `lib/telemetry.ts` and wired in `server.ts`
 * (see deploy/patches/server-telemetry.patch). On every response it posts a generic,
 * behavioural event to the toolbox at `INGEST_URL` (default
 * https://api.rootlane.xyz/internal/events) authenticated with `INGEST_TOKEN`. The
 * toolbox ingests these into ClickHouse — telemetry never talks to ClickHouse directly.
 *
 * Decisions (docs/.../rootlane-design.md, docs/context/team-status.md):
 *   - Fields are GENERIC and behavioural, not tied to any one weakness.
 *   - Store ONLY derived fields: never passwords, tokens or request bodies. `principal_id`
 *     is the identity the APP acts as (claimed, since a vulnerable app trusts the
 *     credential). `param_flags` are derived markers; param values are never sent.
 *   - Event shape matches docs/ui/dashboard-contract.md (/api/events).
 *
 * Safety: telemetry must never break the shop. Every failure is swallowed; with no
 * INGEST_URL/INGEST_TOKEN it is a no-op (says so once). Uses Node 22's global fetch —
 * no new dependency, and no use of the vulnerable jsonwebtoken@0.4.0 the app ships.
 */

import { type Request, type Response, type NextFunction, type RequestHandler } from 'express'
import { randomUUID } from 'node:crypto'

const FLUSH_INTERVAL_MS = 1000
const FLUSH_AT_ROWS = 100
const MAX_BUFFER = 5000
const LOGIN_ROUTE = '/rest/user/login'

interface Event {
  ts: string
  trace_id: string
  method: string
  route: string
  path: string
  status: number
  latency_ms: number
  ip: string
  user_agent: string
  has_token: boolean
  principal_id: string
  auth_outcome: string
  param_flags: string[]
}

let warned = false
const buffer: Event[] = []

function endpoint (): string {
  return process.env.INGEST_URL || 'https://api.rootlane.xyz/internal/events'
}
function token (): string {
  return process.env.INGEST_TOKEN || ''
}

function b64urlToJson (segment: string): Record<string, any> | null {
  try {
    const json = Buffer.from(segment.replace(/-/g, '+').replace(/_/g, '/'), 'base64').toString('utf8')
    return JSON.parse(json)
  } catch {
    return null
  }
}

function tokenFrom (req: Request): string {
  const cookie = (req as any).cookies?.token
  if (typeof cookie === 'string' && cookie.length > 0) return cookie
  const auth = req.headers.authorization
  if (typeof auth === 'string' && auth.startsWith('Bearer ')) return auth.slice(7)
  return ''
}

// Identity the application acts as: the id claimed by the presented token, parsed from
// claims WITHOUT verifying (what a vulnerable app does). Never the token itself.
function claimedPrincipal (tok: string): string {
  if (!tok) return ''
  const payload = b64urlToJson(tok.split('.')[1] || '')
  if (!payload) return ''
  const id = payload.data?.id ?? payload.id ?? payload.sub ?? payload.data?.email ?? payload.email
  return id != null ? String(id) : ''
}

const META = /[`'";<>{}$()|&]|--|\/\*|\.\.\//
// Generic, scenario-agnostic markers derived from params. Values are inspected, never sent.
function paramFlags (req: Request): string[] {
  const flags = new Set<string>()
  const scan = (obj: unknown): void => {
    if (obj == null) return
    if (typeof obj === 'string') {
      if (META.test(obj)) flags.add('meta_chars')
      if (obj.length > 512) flags.add('long_value')
      if (obj.includes('../') || obj.includes('..\\')) flags.add('path_traversal')
      return
    }
    if (typeof obj === 'object') for (const v of Object.values(obj as Record<string, unknown>)) scan(v)
  }
  try { scan(req.query) } catch { /* ignore */ }
  try { scan((req as any).body) } catch { /* ignore */ }
  return [...flags]
}

function authOutcome (route: string, hasToken: boolean, status: number): string {
  const ok2xx = status >= 200 && status < 300
  if (route === LOGIN_ROUTE) return ok2xx ? 'login_success' : 'login_failure'
  if (!hasToken) return 'none'
  if (ok2xx) return 'accepted'
  if (status === 401 || status === 403) return 'rejected'
  return 'accepted'
}

async function flush (): Promise<void> {
  if (!buffer.length) return
  const url = endpoint()
  const tok = token()
  if (!tok) {
    if (!warned) { console.warn('[rootlane-telemetry] INGEST_TOKEN unset — telemetry disabled (shop runs normally).'); warned = true }
    buffer.length = 0
    return
  }
  const batch = buffer.splice(0, buffer.length)
  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'content-type': 'application/json', authorization: `Bearer ${tok}` },
      body: JSON.stringify({ events: batch }),
      // keepalive keeps the post alive across the response lifecycle; small batches only.
      signal: AbortSignal.timeout(5000)
    })
    if (!res.ok && !warned) {
      console.warn('[rootlane-telemetry] ingest responded', res.status); warned = true
    }
  } catch (err) {
    if (!warned) { console.warn('[rootlane-telemetry] ingest post failed:', (err as Error).message); warned = true }
    // drop this batch; bounded buffer protects memory if the API is down
  }
}

let timer: NodeJS.Timeout | null = null
function ensureTimer (): void {
  if (timer) return
  timer = setInterval(() => { void flush() }, FLUSH_INTERVAL_MS)
  if (typeof timer.unref === 'function') timer.unref()
}

export default function telemetry (): RequestHandler {
  ensureTimer()
  return function (req: Request, res: Response, next: NextFunction): void {
    const start = process.hrtime.bigint()
    const trace_id = randomUUID()
    ;(req as any).rootlaneTraceId = trace_id

    res.on('finish', () => {
      try {
        const tok = tokenFrom(req)
        const hasToken = tok.length > 0
        const route = (req.route?.path && typeof req.route.path === 'string')
          ? ((req.baseUrl || '') + req.route.path)
          : req.path
        const latency_ms = Math.round(Number((process.hrtime.bigint() - start) / 1000n) / 1000)
        const ip = (req.headers['x-forwarded-for']?.toString().split(',')[0].trim()) || req.ip || ''

        if (buffer.length < MAX_BUFFER) {
          buffer.push({
            ts: new Date().toISOString(),
            trace_id,
            method: req.method,
            route,
            path: req.originalUrl.split('?')[0],
            status: res.statusCode,
            latency_ms,
            ip,
            user_agent: (req.headers['user-agent'] || '').toString().slice(0, 512),
            has_token: hasToken,
            principal_id: claimedPrincipal(tok),
            auth_outcome: authOutcome(route, hasToken, res.statusCode),
            param_flags: paramFlags(req)
          })
        }
        if (buffer.length >= FLUSH_AT_ROWS) void flush()
      } catch {
        // Telemetry never interferes with serving traffic.
      }
    })

    next()
  }
}
