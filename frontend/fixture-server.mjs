// Servidor de prueba: responde el contrato del dashboard con los archivos de ui/fixtures.
// Sirve para probar la UI en "modo real" sin el backend:  node scripts/fixture-server.mjs
// y en otra terminal:  VITE_API_BASE_URL=http://localhost:8000 npm run dev
import http from 'node:http'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const dir = join(dirname(fileURLToPath(import.meta.url)), '..', 'fixtures')
const load = (f) => JSON.parse(readFileSync(join(dir, f), 'utf8'))
let detail = load('incident-detail.json')
const cors = { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': 'Content-Type, X-Admin-Token', 'Access-Control-Allow-Methods': 'GET, POST, OPTIONS' }
const json = (res, code, body) => { res.writeHead(code, { 'Content-Type': 'application/json', ...cors }); res.end(JSON.stringify(body)) }

http.createServer((req, res) => {
  const url = new URL(req.url, 'http://x')
  const p = url.pathname
  if (req.method === 'OPTIONS') { res.writeHead(204, cors); return res.end() }
  if (p === '/api/overview') return json(res, 200, load('overview.json'))
  if (p === '/api/events') return json(res, 200, load('events.json'))
  if (p === '/api/windows') return json(res, 200, load('windows.json'))
  if (p === '/api/incidents') return json(res, 200, [{ id: detail.id, title: detail.title, status: detail.status, severity: detail.severity, category: detail.category, opened_at: detail.opened_at }])
  if (p === `/api/incidents/${detail.id}`) return json(res, 200, detail)
  if (p === '/api/actions') return json(res, 200, load('actions.json'))
  if (p.endsWith('/approve') && req.method === 'POST') {
    if (!req.headers['x-admin-token']) return json(res, 401, { error: 'admin token required' })
    let body = ''; req.on('data', (c) => (body += c)); req.on('end', () => {
      const { approver } = JSON.parse(body || '{}')
      detail = { ...detail, status: 'applied', approval: { approver, decision: 'approve', ts: new Date().toISOString(), reason: null, proposal_hash: detail.proposal.proposal_hash },
        apply: { pr_url: 'https://github.com/djimenezm2/juice-shop/pulls', production_status: 401, production_summary: 'replayed attack rejected', variants: [] } }
      json(res, 200, detail)
    })
    return
  }
  if (p === '/api/stream') {
    res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', Connection: 'keep-alive', ...cors })
    for (const e of load('stream-events.json')) res.write(`event: ${e.event}\ndata: ${JSON.stringify(e.data)}\n\n`)
    const t = setInterval(() => res.write('event: ping\ndata: {}\n\n'), 15000)
    req.on('close', () => clearInterval(t))
    return
  }
  json(res, 404, { error: 'not found' })
}).listen(8000, () => console.log('fixture server on http://localhost:8000'))
