import { test } from "node:test"
import assert from "node:assert/strict"
import { REPRODUCE_REQUEST_FIELD, SESSION_BODY_FIELD, toolArgs } from "../guild/lib/tool-args"

test("flat and wrapped shapes carry the session id in the body", () => {
  assert.deepEqual(toolArgs({ sql: "SELECT 1" }, "s1", "flat", null), { sql: "SELECT 1", guild_session_id: "s1" })
  assert.deepEqual(toolArgs({ sql: "SELECT 1" }, "s1", "body", null), { body: { sql: "SELECT 1", guild_session_id: "s1" } })
  assert.deepEqual(toolArgs({ sql: "SELECT 1" }, "s1", "flat", "X-Guild-Session"),
    { sql: "SELECT 1", guild_session_id: "s1", "X-Guild-Session": "s1" })
})

test("defaults match the generated Guild tools: flat body fields, no header argument", () => {
  assert.deepEqual(toolArgs({ sql: "SELECT 1", incident_id: "i1" }, "01a122ab-c194-cf83-0000-a046f9ff3608"),
    { sql: "SELECT 1", incident_id: "i1", guild_session_id: "01a122ab-c194-cf83-0000-a046f9ff3608" })
})

test("a session id the toolbox would refuse is left out", () => {
  for (const bad of ["", "a b", "x\n", "s/1", "é", "a".repeat(65)]) {
    assert.deepEqual(toolArgs({ sql: "SELECT 1" }, bad), { sql: "SELECT 1" }, JSON.stringify(bad))
  }
  assert.deepEqual(toolArgs({ sql: "SELECT 1" }, "a".repeat(64)), { sql: "SELECT 1", guild_session_id: "a".repeat(64) })
})

test("session body field name matches the toolbox contract", () => {
  assert.equal(SESSION_BODY_FIELD, "guild_session_id")
})

test("reproduce request field name has a single source", () => {
  assert.equal(REPRODUCE_REQUEST_FIELD, "reproduction")
})
