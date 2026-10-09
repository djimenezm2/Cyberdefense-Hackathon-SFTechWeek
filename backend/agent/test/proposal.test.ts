import { test } from "node:test"
import assert from "node:assert/strict"
import { isMissingEndpoint, proposalHash } from "../guild/lib/outcome"

test("a 404 or Not Found error means the endpoint is missing", () => {
  for (const e of [new Error("HTTP 404"), "Request failed with status code 404", { status: 404 }, new Error("Not Found")]) assert.equal(isMissingEndpoint(e), true)
  for (const e of [new Error("HTTP 401 Unauthorized"), new Error("500 internal"), null, { status: 400 }]) assert.equal(isMissingEndpoint(e), false)
})

test("proposal hash only from a non-empty string field", () => {
  assert.equal(proposalHash({ proposal_hash: "abc123" }), "abc123")
  for (const r of [{ proposal_hash: "" }, { proposal_hash: 7 }, {}, null, "abc"]) assert.equal(proposalHash(r), null)
})
