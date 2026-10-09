# Object-Level Authorization Policy

Status: approved · Owner: Rootlane security · Applies to: every endpoint that reads or writes user-owned data

## Purpose

Being logged in is not permission to touch every record. Each request must prove that the
authenticated principal may act on the specific object it names.

## Rules

1. **Deny by default.** An endpoint grants access only when an explicit check passes. A missing
   check, an unknown role or an error means deny.
2. **Check ownership on every read and write.** When a request names a user-owned object (a
   basket, an order, an address, a profile, a payment method) by id, the service loads the object
   and compares its owner with the authenticated principal before returning or changing it.
   Knowing or guessing an id is never enough.
3. **The principal comes from authentication.** The owner check uses the identity from the
   verified credential (see the authentication policy), never a user id sent in the path, query
   or body.
4. **Scope queries to the owner.** Where possible, the query itself filters by owner
   (`WHERE id = ? AND owner_id = ?`) so another user's object is never loaded.
5. **Same rule for every verb.** GET, PUT, PATCH and DELETE on the same object apply the same
   check; list endpoints return only the principal's objects.
6. **Administrative access is explicit.** Roles that may act on other users' objects are
   checked by name and every such action is audited.
7. **Answer consistently.** A request for an object the principal does not own returns 403 or
   404 without revealing whether the object exists.

## Detection hints

One session reading or modifying many objects with sequential ids, or objects whose owner
differs from the session's user, is a signal to investigate under the incident runbook.
