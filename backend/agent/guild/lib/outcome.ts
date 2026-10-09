export type Outcome = "not_reproduced" | "fix_failed" | "pending_approval" | "rejected" | "applied"
export type Approval = "approved" | "rejected" | "pending"
export interface Reproduction { method: string; path: string; headers: Record<string, string>; body: string | null; expected_blocked_status: number }
export interface AgentOutput { incident_id: string; outcome: Outcome; summary: string; proposal_hash: string | null; pr_url: string | null }

const ID = /^[A-Za-z0-9_-]{1,64}$/
type Loose = Record<string, any> | null | undefined

export function resolveIncidentId(input: { incident_id?: string; text?: string }): string | null {
  const raw = (input.incident_id ?? input.text ?? "").trim()
  return ID.test(raw) ? raw : null
}

export function incidentQuery(id: string): string {
  if (!ID.test(id)) throw new Error(`invalid incident id: ${id}`)
  return `SELECT document FROM incidents FINAL WHERE id = '${id}'`
}

export function incidentFromRows(result: unknown): Record<string, unknown> | null {
  const row = (result as Loose)?.rows?.[0]
  const doc = Array.isArray(row) ? row[0] : row?.document
  if (typeof doc !== "string") return null
  try { return JSON.parse(doc) } catch { return null }
}

export function isReproduced(replay: unknown, repro: Reproduction): boolean {
  const status = (replay as Loose)?.status
  return typeof status === "number" && status >= 200 && status < 300 && status !== repro.expected_blocked_status
}

export function verifyPassed(result: unknown): boolean {
  return (result as Loose)?.passed === true
}

export function approvalDecision(doc: unknown, proposalHash: string): Approval {
  const d = doc as Loose
  const forThisProposal = d?.approval?.proposal_hash === proposalHash
  if (d?.approval?.decision === "reject") return forThisProposal ? "rejected" : "pending"
  if (d?.status === "rejected" && (!d.approval || forThisProposal)) return "rejected"
  if (d?.approval?.decision === "approve" && forThisProposal) return "approved"
  return "pending"
}

export function applySucceeded(result: unknown, repro: Reproduction): boolean {
  return (result as Loose)?.production_status === repro.expected_blocked_status
}

export function finalOutput(id: string, outcome: Outcome, summary: string, proposalHash: string | null = null, prUrl: string | null = null): AgentOutput {
  return { incident_id: id, outcome, summary, proposal_hash: proposalHash, pr_url: prUrl }
}

export function parsePositiveInt(raw: string | undefined, fallback: number): number {
  const n = Number(raw)
  return raw && Number.isInteger(n) && n > 0 ? n : fallback
}
