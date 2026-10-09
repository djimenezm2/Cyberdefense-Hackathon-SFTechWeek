# Input Handling and Database Access Policy

Status: approved · Owner: Rootlane security · Applies to: every service that reads or writes a database

## Purpose

Untrusted input must never change the structure of a query or of rendered output. This policy
keeps data as data.

## Rules

1. **Parameterized queries only.** Every database statement passes untrusted values as bound
   parameters (placeholders such as `?`, `$1` or `:name`) or through ORM bindings. The query text
   itself is a constant.
2. **Never build SQL from strings.** Concatenation, template literals or string formatting that
   place request data into SQL text are forbidden, including in "raw query" escape hatches of an
   ORM. When a dynamic identifier (a sort column, a table name) is unavoidable, it is chosen from
   a fixed allow-list in code, never copied from the request.
3. **Validate at the boundary.** Each endpoint validates type, length, format and range of its
   inputs against a schema and rejects what does not match, before any business logic runs.
4. **Encode on output.** Values rendered into HTML, JavaScript, URLs or shell commands are
   encoded for that context by the framework's encoder, not by hand.
5. **Least privilege for database users.** The application's database account has only the
   permissions it needs.
6. **Errors stay generic.** Database errors are logged server-side and never returned to the
   client verbatim.

## Detection hints

Bursts of requests with quote characters, comment markers or boolean expressions in search or
login fields, database syntax errors in responses, or responses far larger than normal are
signals to investigate under the incident runbook.

## Enforcement

A Semgrep rule flags string-built SQL in CI; findings block the merge.
