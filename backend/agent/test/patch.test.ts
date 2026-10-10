import { test } from "node:test"
import assert from "node:assert/strict"
import { buildDiff, flaggedLines, hasTimeFor, missingPaths, numberedSource, stripFences, verifyErrorKind } from "../guild/lib/patch"

const file = { path: "routes/login.ts", content: "a\nb\nc\nd\ne\nf\ng\nh\ni\n", truncated: false }

test("an invalid rule is told apart from a patch failure", () => {
  assert.equal(verifyErrorKind({ error: "Error: 422 rule could not run: invalid YAML at line 2" }), "rule")
  assert.equal(verifyErrorKind({ error: "422 rule is invalid: missing key 'message'" }), "rule")
  assert.equal(verifyErrorKind({ error: "409 another replica is running" }), "busy")
  assert.equal(verifyErrorKind({ error: "422 diff does not apply" }), null)
  assert.equal(verifyErrorKind({ passed: false, exploit_after: 200 }), null)
  assert.equal(verifyErrorKind(null), null)
})

test("a new attempt starts only if it fits before the deadline", () => {
  assert.equal(hasTimeFor(0, 1000, 500, 100), true)
  assert.equal(hasTimeFor(600, 1000, 500, 100), false)
  assert.equal(hasTimeFor(0, 1000, 0, 2000), false)
})

test("a structured edit becomes a unified diff with exact context", () => {
  const built = buildDiff([file], [{ path: "routes/login.ts", old_text: "e\n", new_text: "E1\nE2\n" }])
  assert.ok("diff" in built)
  assert.equal(built.diff, [
    "diff --git a/routes/login.ts b/routes/login.ts", "--- a/routes/login.ts", "+++ b/routes/login.ts",
    "@@ -2,7 +2,8 @@", " b", " c", " d", "-e", "+E1", "+E2", " f", " g", " h", "",
  ].join("\n"))
})

test("edits inside a line and at the start of the file keep line numbers right", () => {
  const built = buildDiff([file], [{ path: "routes/login.ts", old_text: "a", new_text: "A" }])
  assert.ok("diff" in built)
  assert.match(built.diff, /@@ -1,4 \+1,4 @@\n-a\n\+A\n b\n c\n d\n$/)
})

test("edits that do not match exactly once are rejected", () => {
  assert.ok("error" in buildDiff([file], [{ path: "routes/login.ts", old_text: "zzz", new_text: "y" }]))
  assert.ok("error" in buildDiff([{ ...file, content: "x\nx\n" }], [{ path: "routes/login.ts", old_text: "x", new_text: "y" }]))
  assert.ok("error" in buildDiff([file], [{ path: "other.ts", old_text: "a", new_text: "b" }]))
  assert.ok("error" in buildDiff([file], [{ path: "routes/login.ts", old_text: "a", new_text: "a" }]))
})

test("a file without a final newline is marked in the diff", () => {
  const built = buildDiff([{ ...file, content: "a\nb" }], [{ path: "routes/login.ts", old_text: "b", new_text: "B" }])
  assert.ok("diff" in built)
  assert.match(built.diff, /-b\n\\ No newline at end of file\n\+B\n\\ No newline at end of file\n$/)
})

test("helpers: fences stripped, sources numbered, unread paths listed", () => {
  assert.equal(stripFences("```yaml\nrules: []\n```"), "rules: []")
  assert.equal(stripFences("rules: []\n"), "rules: []\n")
  assert.match(numberedSource(file), /^path: routes\/login\.ts\n 1\| a\n 2\| b/)
  assert.deepEqual(missingPaths([{ path: "x.ts" }, { path: "routes/login.ts" }, { path: "x.ts" }], [file]), ["x.ts"])
})

test("files over the limit show the head and the windows around Semgrep findings", () => {
  const big = { path: "big.ts", content: Array.from({ length: 2000 }, (_, i) => `line ${i + 1} ${"x".repeat(40)}`).join("\n") + "\n" }
  const flagged = flaggedLines({ results: [{ path: "big.ts", start: { line: 1000 } }, { path: "other.ts", start: { line: 5 } }] }, "big.ts")
  assert.deepEqual(flagged, [1000])
  const shown = numberedSource(big, flagged, 20000)
  assert.ok(shown.length <= 20200)
  assert.match(shown, /   1\| line 1 /)
  assert.match(shown, /1000\| line 1000 /)
  assert.doesNotMatch(shown, /\| line 500 /)
  assert.match(numberedSource(big, [], 200000), /2000\| line 2000 /)
})
