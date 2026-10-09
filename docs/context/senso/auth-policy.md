# Authentication and Session Token Policy

Status: approved · Owner: Rootlane security · Applies to: every service behind the Rootlane toolbox

## Purpose

Authentication decides who a request comes from. Every later decision (authorization, audit,
rate limits) depends on that answer, so it must come from a credential the service has verified,
never from data the client can shape.

## Rules

1. **Verify every token before use.** A session or bearer token (for example a JWT) is accepted
   only after its signature has been verified with a key the service controls.
2. **Pin the algorithm allow-list.** The verifier accepts only the algorithms the service
   configured (for example `RS256` only). The algorithm named in the token header is never
   trusted on its own; tokens declaring `none`, or an algorithm outside the allow-list, are
   rejected.
3. **Check expiry and validity window.** `exp` and `nbf` are enforced on every request, with a
   small clock-skew tolerance. Expired tokens are rejected, not refreshed silently.
4. **Check issuer and audience.** `iss` and `aud` must match the values the service expects.
5. **Never trust claims from an unverified token.** Decoding a token without verifying it is
   allowed only for logging; no identity, role or permission may be read from it.
6. **Identity comes from a verified credential.** The authenticated principal (user id, email,
   role) is taken from the verified token or the server-side session, never from request
   bodies, query parameters or headers the client sets.
7. **Fail closed.** Any verification error rejects the request with 401 and is logged without
   the token value.

## Detection hints

Logins or privileged actions that succeed without a matching successful credential check,
tokens with unexpected algorithms, and identities that appear without a login are signals to
investigate under the incident runbook.
