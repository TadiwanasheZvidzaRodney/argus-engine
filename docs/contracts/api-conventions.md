# Argus Engine — API Conventions (v1)

> **Status:** Ratified in Phase 0  
> **Applies to:** `services/api`, `services/ws`, and client SDKs

---

## 1. URL Structure and Versioning

- Base URL: `/api/v1`
- Versioning is strictly via URL major version.
- Within a major version, all changes are strictly additive:
  - New endpoints may be added.
  - New optional request fields may be added.
  - New response fields may be added (clients must ignore unknown fields).
- Breaking field renames or type changes require a major version bump (`/api/v2`).

---

## 2. Authentication and Authorization

- Edge requests carry `Authorization: Bearer <token>`.
- The Web client communicates through the BFF using httpOnly, sameSite cookies; browser code never holds raw refresh tokens.
- Internal service-to-service communication is authenticated via mTLS and AWS IAM SigV4 when running on ECS Fargate.

---

## 3. Error Handling (RFC 9457)

All non-2xx responses must return `application/problem+json` with the following structure:

```json
{
  "type": "https://errors.argus.example.com/validation-failed",
  "title": "Validation Failed",
  "status": 422,
  "detail": "One or more fields are invalid.",
  "instance": "/api/v1/demo/resources",
  "request_id": "req_01M72X6SD6VEXNY91EQRVAQP54",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "errors": [
    {
      "pointer": "/name",
      "code": "string_too_short",
      "detail": "String should have at least 1 character"
    }
  ]
}
```

Standard error codes:
- `bad-request` (400)
- `idempotency-key-required` (400)
- `idempotency-key-invalid` (400)
- `unauthorized` (401)
- `forbidden` (403)
- `not-found` (404)
- `idempotency-request-in-flight` (409)
- `idempotency-key-reuse` (409)
- `payload-too-large` (413)
- `validation-failed` (422)
- `rate-limited` (429)
- `internal-error` (500)
- `service-unavailable` (503)

---

## 4. Cursor-Based Pagination

List endpoints must not use offset/limit pagination (which drifts and performs poorly on graphs).

- Query parameters:
  - `limit`: Integer, default 50, maximum 200.
  - `cursor`: Opaque, HMAC-signed Base64URL token returned by the previous page.
- Response envelope:
  ```json
  {
    "items": [...],
    "next_cursor": "eyJpbmRleCI6MjV9.qN8sP3...",
    "has_more": true
  }
  ```
- Cursors are tamper-evident. If a client alters a cursor, the API rejects it with `422 validation-failed`.

---

## 5. Idempotent Mutations

- Every non-safe HTTP request (`POST`, `PATCH`, `DELETE`) **must** provide an `Idempotency-Key` header (8–128 characters matching `^[A-Za-z0-9._:-]+$`).
- The API computes a SHA-256 fingerprint over `method + path + body`.
- Semantics:
  - If the key is new: request proceeds, response is cached in Redis for 24 hours.
  - If the key is seen with the same fingerprint: returns cached response with `X-Idempotent-Replay: true`.
  - If the key is currently executing: returns `409 idempotency-request-in-flight` with `Retry-After: 1`.
  - If the key is reused with a different fingerprint: returns `409 idempotency-key-reuse`.

---

## 6. Correlation and Observability Headers

Every response echoes:
- `X-Request-Id`: Client-supplied or server-generated ULID (`req_...`).
- `X-Trace-Id`: OpenTelemetry 32-character hex trace ID when active.
- Browser security headers: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`.
