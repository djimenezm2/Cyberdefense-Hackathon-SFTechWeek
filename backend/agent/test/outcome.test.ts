import { test } from "node:test"
import assert from "node:assert/strict"
import { approvalDecision, applySucceeded, incidentFromRows, incidentQuery, isReproduced, parsePositiveInt, resolveIncidentId, verifyPassed } from "../guild/lib/outcome"

const repro = { method: "GET", path: "/x", headers: {}, body: null, expected_blocked_status: 401 }

test("reproduced only on a 2xx that is not the blocked status", () => {
  assert.equal(isReproduced({ status: 200 }, repro), true)
  for (const status of [401, 404, 500, "200"]) assert.equal(isReproduced({ status }, repro), false)
  assert.equal(isReproduced(null, repro), false)
})

test("verify passes only on passed === true", () => {
  assert.equal(verifyPassed({ passed: true }), true)
  for (const r of [{ passed: "true" }, {}, null, { passed: false }]) assert.equal(verifyPassed(r), false)
})

test("approval must match this proposal and say approve", () => {
  const ok = { status: "pending_approval", approval: { decision: "approve", proposal_hash: "p1" } }
  assert.equal(approvalDecision(ok, "p1"), "approved")
  assert.equal(approvalDecision(ok, "p2"), "pending")
  assert.equal(approvalDecision({ status: "pending_approval", approval: null }, "p1"), "pending")
  assert.equal(approvalDecision({ status: "rejected", approval: null }, "p1"), "rejected")
  assert.equal(approvalDecision({ approval: { decision: "reject", proposal_hash: "p1" } }, "p1"), "rejected")
})

test("a rejection of another proposal does not reject this one", () => {
  const stale = { status: "pending_approval", approval: { decision: "reject", proposal_hash: "old" } }
  assert.equal(approvalDecision(stale, "new"), "pending")
  assert.equal(approvalDecision({ ...stale, status: "rejected" }, "new"), "pending")
  assert.equal(approvalDecision(stale, "old"), "rejected")
})

test("applied only when production replay hit the blocked status", () => {
  assert.equal(applySucceeded({ production_status: 401, pr_url: "u" }, repro), true)
  assert.equal(applySucceeded({ production_status: 200 }, repro), false)
  assert.equal(applySucceeded(null, repro), false)
})

test("incident id comes from incident_id or bare text and is validated", () => {
  assert.equal(resolveIncidentId({ incident_id: "inc_01" }), "inc_01")
  assert.equal(resolveIncidentId({ text: " inc_01 " }), "inc_01")
  assert.equal(resolveIncidentId({ incident_id: "x'; DROP" }), null)
  assert.throws(() => incidentQuery("a' OR 1=1"))
  assert.equal(incidentQuery("inc_01"), "SELECT document FROM incidents FINAL WHERE id = 'inc_01'")
})

test("incident document parsed from array or object rows", () => {
  const doc = JSON.stringify({ id: "inc_01", status: "investigating" })
  assert.equal(incidentFromRows({ columns: ["document"], rows: [[doc]] })?.status, "investigating")
  assert.equal(incidentFromRows({ rows: [{ document: doc }] })?.id, "inc_01")
  assert.equal(incidentFromRows({ rows: [] }), null)
})

test("positive int env parsing falls back", () => {
  assert.equal(parsePositiveInt("3", 40), 3)
  for (const raw of [undefined, "", "0", "-2", "abc"]) assert.equal(parsePositiveInt(raw, 40), 40)
})
