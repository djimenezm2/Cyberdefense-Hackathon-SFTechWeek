/*
  CONTRATO CON EL BACKEND (toolbox) — copia de docs/ui/dashboard-contract.md del repo.
  Si el backend cambia una ruta, se cambia solo aquí.
*/
export const ENDPOINTS = {
  overview: '/api/overview',
  events: (since) => `/api/events?limit=100${since ? `&since=${encodeURIComponent(since)}` : ''}`,
  windows: '/api/windows?limit=20',
  incidents: '/api/incidents',
  incident: (id) => `/api/incidents/${id}`,
  actions: (id) => (id ? `/api/actions?incident_id=${id}` : '/api/actions'),
  approve: (id) => `/api/incidents/${id}/approve`, // POST {approver} + header X-Admin-Token
  reject: (id) => `/api/incidents/${id}/reject`,   // POST {approver, reason} + header X-Admin-Token
  stream: '/api/stream',                            // SSE: verdict, step, incident_update, ping
}
export const POLL_MS = 2000

// Los `steps[].kind` del contrato agrupados en 7 fases visibles
export const KIND_TO_PHASE = {
  query: 'investigate', read_source: 'investigate', context: 'investigate',
  semgrep: 'semgrep', replay: 'reproduce', verify: 'verify',
  propose: 'verify', approval: 'approval', apply: 'apply', lesson: 'apply', chat: null,
}
export const PHASES = [
  { key: 'detected', label: 'Detected' },
  { key: 'investigate', label: 'Investigate' },
  { key: 'semgrep', label: 'Semgrep' },
  { key: 'reproduce', label: 'Reproduce' },
  { key: 'verify', label: 'Verify' },
  { key: 'approval', label: 'Approval' },
  { key: 'apply', label: 'Applied' },
]
export const KIND_LABEL = {
  detected: 'Incident opened', query: 'Queried events', read_source: 'Read source', context: 'Checked Senso context',
  semgrep: 'Semgrep scan', replay: 'Reproduced on replica', verify: 'Verified the patch', propose: 'Proposed a fix',
  approval: 'Approval', apply: 'Applied to production', lesson: 'Saved the lesson', chat: 'Chat',
}

// Estados del incidente del contrato → cómo se muestran
export const STATUS = {
  investigating: { t: 'Investigating', tone: 'warn', working: true },
  pending_approval: { t: 'Waiting for approval', tone: 'agent', working: true },
  applying: { t: 'Applying fix', tone: 'agent', working: true },
  applied: { t: 'Fixed', tone: 'ok' },
  not_reproduced: { t: 'Not reproduced', tone: 'off' },
  fix_failed: { t: 'Fix failed', tone: 'bad' },
  rejected: { t: 'Rejected', tone: 'off' },
}

export const STATUS_COPY = {
  paused: { label: 'Paused', tone: 'off' },
  watching: { label: 'Watching', tone: 'ok' },
  investigating: { label: 'Investigating', tone: 'warn' },
  approval: { label: 'Needs approval', tone: 'agent' },
  applying: { label: 'Applying', tone: 'agent' },
}

// Lo que el toolbox exige antes de pedir aprobación (spec: propose se rechaza sin verify_patch aprobado)
export const GUARDRAILS = [
  { t: 'Reproduce the attack on a fresh replica of production', d: 'If it does not reproduce, the agent reports it and stops.' },
  { t: 'Verify the patch on the replica', d: 'The exploit must fail after the patch and the regression smoke suite must pass.' },
  { t: 'Ship a Semgrep rule that catches the pattern', d: 'It must fire on the old code and stay silent on the new code.' },
  { t: 'A named person approves the exact proposal', d: 'The toolbox refuses to apply anything without it.' },
  { t: 'Replay the attack against production after applying', d: 'Proof that production now answers 401 instead of 200.' },
]
