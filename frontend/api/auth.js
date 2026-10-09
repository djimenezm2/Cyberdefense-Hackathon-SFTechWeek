// Vercel serverless function: GitHub sign-in for the dashboard, plus a server-side proxy for
// approve/reject so the admin token never reaches the browser. The approver is the GitHub login.
//
// Vercel env (Project → Settings → Environment Variables):
//   GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET  GitHub OAuth App (callback: https://app.rootlane.xyz/api/auth)
//   SESSION_SECRET                          any long random string
//   ADMIN_TOKEN                             same value as the toolbox ADMIN_TOKEN
//   API_BASE                                https://api.rootlane.xyz
//   ALLOWED_GITHUB_USERS                    comma-separated GitHub logins allowed to approve (empty = anyone)
//
// Routes (all on /api/auth):
//   GET  ?a=login            → redirect to GitHub
//   GET  ?code=&state=       → GitHub callback, sets the session cookie, redirects to /
//   GET  ?a=me               → { login, name, avatar } or 401
//   POST ?a=logout           → clears the cookie
//   POST ?a=decide&id=&kind=approve|reject   body { reason? } → forwards to the toolbox
import crypto from 'node:crypto'

const COOKIE = 'rl_session'
const STATE = 'rl_oauth_state'
const MAX_AGE = 60 * 60 * 12

const env = (k) => (process.env[k] || '').trim()
const sign = (v) => crypto.createHmac('sha256', env('SESSION_SECRET')).update(v).digest('base64url')

function cookies(req) {
  return Object.fromEntries((req.headers.cookie || '').split(';').map((c) => c.trim().split('=')).filter((p) => p[0]).map(([k, ...v]) => [k, decodeURIComponent(v.join('='))]))
}
const setCookie = (name, value, maxAge) =>
  `${name}=${encodeURIComponent(value)}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${maxAge}`

function readSession(req) {
  const raw = cookies(req)[COOKIE]
  if (!raw || !env('SESSION_SECRET')) return null
  const [body, mac] = raw.split('.')
  if (!body || !mac) return null
  const good = sign(body)
  if (mac.length !== good.length || !crypto.timingSafeEqual(Buffer.from(mac), Buffer.from(good))) return null
  const s = JSON.parse(Buffer.from(body, 'base64url').toString())
  return s.exp > Date.now() ? s : null
}

const json = (res, status, data) => { res.statusCode = status; res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(data)) }
const redirect = (res, to, extra = []) => { res.statusCode = 302; res.setHeader('Location', to); if (extra.length) res.setHeader('Set-Cookie', extra); res.end() }

export default async function handler(req, res) {
  const url = new URL(req.url, `https://${req.headers.host}`)
  const a = url.searchParams.get('a')
  const origin = `https://${req.headers.host}`

  // 1. Start: send the user to GitHub
  if (a === 'login') {
    if (!env('GITHUB_CLIENT_ID')) return json(res, 500, { error: 'GITHUB_CLIENT_ID is not set' })
    const state = crypto.randomBytes(16).toString('hex')
    const q = new URLSearchParams({ client_id: env('GITHUB_CLIENT_ID'), redirect_uri: `${origin}/api/auth`, scope: 'read:user', state, allow_signup: 'false' })
    return redirect(res, `https://github.com/login/oauth/authorize?${q}`, [setCookie(STATE, state, 600)])
  }

  // 2. GitHub callback
  if (url.searchParams.get('code')) {
    const state = url.searchParams.get('state')
    if (!state || state !== cookies(req)[STATE]) return redirect(res, '/?auth=state')
    const tok = await fetch('https://github.com/login/oauth/access_token', {
      method: 'POST',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: JSON.stringify({ client_id: env('GITHUB_CLIENT_ID'), client_secret: env('GITHUB_CLIENT_SECRET'), code: url.searchParams.get('code'), redirect_uri: `${origin}/api/auth` }),
    }).then((r) => r.json()).catch(() => ({}))
    if (!tok.access_token) return redirect(res, '/?auth=exchange')
    const user = await fetch('https://api.github.com/user', { headers: { Authorization: `Bearer ${tok.access_token}`, 'User-Agent': 'rootlane-dashboard' } }).then((r) => r.json()).catch(() => ({}))
    if (!user.login) return redirect(res, '/?auth=user')
    const allowed = env('ALLOWED_GITHUB_USERS').toLowerCase().split(',').map((s) => s.trim()).filter(Boolean)
    if (allowed.length && !allowed.includes(user.login.toLowerCase())) return redirect(res, '/?auth=denied', [setCookie(STATE, '', 0)])
    const body = Buffer.from(JSON.stringify({ login: user.login, name: user.name || user.login, avatar: user.avatar_url, exp: Date.now() + MAX_AGE * 1000 })).toString('base64url')
    return redirect(res, '/', [setCookie(COOKIE, `${body}.${sign(body)}`, MAX_AGE), setCookie(STATE, '', 0)])
  }

  if (a === 'me') {
    const s = readSession(req)
    return s ? json(res, 200, { login: s.login, name: s.name, avatar: s.avatar }) : json(res, 401, { error: 'not signed in' })
  }

  if (a === 'logout') return (res.setHeader('Set-Cookie', setCookie(COOKIE, '', 0)), json(res, 200, { ok: true }))

  // 3. Approve / reject on behalf of the signed-in GitHub user
  if (a === 'decide' && req.method === 'POST') {
    const s = readSession(req)
    if (!s) return json(res, 401, { error: 'not signed in' })
    const id = url.searchParams.get('id') || ''
    const kind = url.searchParams.get('kind')
    if (!/^[\w-]+$/.test(id) || !['approve', 'reject'].includes(kind)) return json(res, 400, { error: 'bad request' })
    let reason = 'Rejected from the dashboard'
    try { const b = typeof req.body === 'string' ? JSON.parse(req.body) : req.body; if (b?.reason) reason = String(b.reason).slice(0, 500) } catch { /* default */ }
    const approver = `${s.login} (GitHub)`
    const r = await fetch(`${env('API_BASE')}/api/incidents/${id}/${kind}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Admin-Token': env('ADMIN_TOKEN') },
      body: JSON.stringify(kind === 'approve' ? { approver } : { approver, reason }),
    }).catch(() => null)
    if (!r) return json(res, 502, { error: 'toolbox unreachable' })
    res.statusCode = r.status === 401 ? 502 : r.status // 401 here means the server's ADMIN_TOKEN is wrong, not the user
    res.setHeader('Content-Type', 'application/json')
    return res.end(await r.text())
  }

  return json(res, 404, { error: 'unknown action' })
}
