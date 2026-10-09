import { test } from "node:test"
import assert from "node:assert/strict"
import { REPRODUCE_REQUEST_FIELD, toolArgs } from "../guild/lib/tool-args"

test("flat and wrapped shapes, with and without the session header", () => {
  assert.deepEqual(toolArgs({ sql: "SELECT 1" }, "s1", "flat", null), { sql: "SELECT 1" })
  assert.deepEqual(toolArgs({ sql: "SELECT 1" }, "s1", "body", null), { body: { sql: "SELECT 1" } })
  assert.deepEqual(toolArgs({ sql: "SELECT 1" }, "s1", "flat", "X-Guild-Session"), { sql: "SELECT 1", "X-Guild-Session": "s1" })
})

test("defaults match the generated Guild tools: flat body fields, no header argument", () => {
  assert.deepEqual(toolArgs({ sql: "SELECT 1", incident_id: "i1" }, "s1"), { sql: "SELECT 1", incident_id: "i1" })
})

test("reproduce request field name has a single source", () => {
  assert.equal(REPRODUCE_REQUEST_FIELD, "reproduction")
})
