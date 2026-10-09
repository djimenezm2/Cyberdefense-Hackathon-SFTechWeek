import { test } from "node:test"
import assert from "node:assert/strict"
import { extractJson } from "../guild/lib/json"

test("plain, fenced and prose-wrapped JSON are recovered", () => {
  assert.deepEqual(extractJson('{"a":1}'), { a: 1 })
  assert.deepEqual(extractJson('```json\n{"a":1}\n```'), { a: 1 })
  assert.deepEqual(extractJson('Here it is: {"a":{"b":2}} done'), { a: { b: 2 } })
})

test("unrecoverable replies give null", () => {
  for (const t of ["", "no json here", "{broken", "[1,2]"]) assert.equal(extractJson(t), null)
})
