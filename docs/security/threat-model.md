# Argus Engine — Threat Model (Phase 0 STRIDE)

> **Status:** Ratified in Phase 0  
> **Review Cadence:** Quarterly and on any write-path/trust-boundary change  
> **Methodology:** STRIDE (Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service, Elevation of Privilege)

---

## 1. System Trust Boundaries

1. **Browser / BFF Boundary:** The React/Next.js frontend runs in an untrusted browser. Session cookies are `httpOnly`, `secure`, and `sameSite: lax`. No raw access/refresh tokens are exposed to JavaScript.
2. **Edge API Boundary:** All API traffic terminates at the AWS ALB, which enforces TLS 1.3 and passes requests to containerized FastAPI services in private subnets.
3. **Tenant Boundary:** Logical isolation in PostgreSQL via Row-Level Security (RLS), tenant-scoped Neo4j node labels and index predicates (`WHERE n.tenant_id = $tenant_id`), and Redis key prefixes (`tnt_{id}:...`).
4. **AWS Customer Role Boundary:** Argus assumes customer IAM roles using STS with a cryptographically random, unique `ExternalId` and an immutable scope-down session policy.
5. **LLM / Intent Boundary:** Large Language Models (AWS Bedrock) are **read-only and advisory**. LLMs never execute AWS API calls or write CloudFormation templates directly; they only parse human intent into deterministic Action Engine plans.
6. **Action Execution Boundary:** Action execution happens in an ephemeral, sandboxed worker with single-purpose, time-bound STS credentials (maximum 15 minutes session duration).

---

## 2. STRIDE Analysis and Mitigations

| Threat | Component | Risk | Phase 0 Mitigation |
|---|---|---|---|
| **Spoofing** | API Requests | Attacker impersonates another tenant or user | OIDC JWT verification, signed session cookies, rejected client-supplied tenant headers outside local dev. |
| **Spoofing** | AWS AssumeRole | Attacker tricks Argus into assuming another customer's role (Confused Deputy) | Mandatory unique `ExternalId` per tenant; STS scope-down policies. |
| **Tampering** | Pagination Cursors | Client modifies cursor to access another tenant's offset | HMAC-SHA256 signature over cursor payload; rejected with 422 if altered. |
| **Tampering** | Audit Trail | Malicious insider or compromised service alters audit logs | Cryptographic SHA-256 hash chaining (`prev_hash` -> `hash`); S3 Object Lock in Compliance mode. |
| **Repudiation** | Action Approvals | Operator denies approving a destructive action | Immutable Action Request record with approver identity, timestamp, IP, and plan hash. |
| **Information Disclosure** | CloudTrail / Config Ingest | AWS metadata contains customer secrets (e.g. env vars in Lambda/ECS) | Strict redaction pipeline; regex and key-based masking before storing in Neo4j/Postgres. |
| **Information Disclosure** | Logs & Traces | API logs leak customer authorization tokens or AWS credentials | Structlog processor redacts all keys matching `password`, `secret`, `token`, `credential`, etc. |
| **Denial of Service** | Mutating API | Replay attacks or storm of concurrent identical requests | Mandatory `Idempotency-Key` header with Redis distributed lock and rate limiting. |
| **Elevation of Privilege** | MCP Sandbox | Malicious action plan attempts privilege escalation in customer AWS account | Deterministic action compiler; read-only dry-run diff check; dual-operator approval for high-risk actions. |
