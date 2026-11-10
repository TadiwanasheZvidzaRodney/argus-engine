# Argus Engine — Tenant Isolation Checklist

> **Status:** Enforced from Phase 0 onwards  
> **Rule:** Every PR touching data storage, caching, messaging, or query logic must validate against this checklist.

---

## 1. Storage & Relational Database (PostgreSQL)

- [x] **Tenant Key:** All tenant-scoped tables must have `tenant_id uuid not null`.
- [x] **Row-Level Security (RLS):** Every tenant table has `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY`.
- [x] **Session Variable:** Database connection pools set `SET LOCAL app.tenant_id = '<current_tenant_id>'` inside each transaction.
- [x] **Default Deny:** If `app.tenant_id` is unset or empty, RLS policies return zero rows.
- [x] **Foreign Keys:** All child entities include `tenant_id` and have composite foreign keys `(id, tenant_id)` referencing the parent table.

---

## 2. Graph Database (Neo4j)

- [x] **Node Property:** Every node must carry a `tenant_id: $tenant_id` property.
- [x] **Relationship Property:** Every relationship must carry a `tenant_id: $tenant_id` property.
- [x] **Cypher Predicate Guardrail:** Every Cypher query executed by backend services must contain `WHERE node.tenant_id = $tenant_id` in its initial MATCH/SCAN clause.
- [x] **Composite Indexes:** Graph indexes must include `tenant_id` as the leading property (e.g. `CREATE INDEX FOR (r:Resource) ON (r.tenant_id, r.arn)`).
- [x] **Enterprise Segregation:** Tier-3 Enterprise tenants support a dedicated Neo4j database instance within the same cluster.

---

## 3. Cache & Ephemeral State (Redis)

- [x] **Key Namespacing:** Every cache and rate-limit key must begin with the tenant prefix:
  `tnt_{tenant_id}:{subsystem}:{key}`
- [x] **No Cross-Tenant SCANs:** Code must never call `KEYS *` or global patterns that inspect keys across tenants.
- [x] **Pub/Sub Channels:** WebSocket delta broadcast channels are strictly isolated by tenant:
  `channel:tnt_{tenant_id}:deltas`

---

## 4. Message Queues & Event Backbone

- [x] **Mandatory Envelope Attribute:** Every message published to SQS, EventBridge, or Redis contains `tenant_id` at the top level of the `EventEnvelope`.
- [x] **Consumer Context:** Message worker handlers immediately set tenant context in logging and database connections before processing `data`.

---

## 5. Logging, Telemetry & SRE

- [x] **Log Context:** Every log entry carries `tenant_id` as a structured JSON attribute when in request/worker scope.
- [x] **No Cross-Tenant Metrics:** OpenTelemetry metrics with customer identifiers use high-cardinality protection and tenant hashing where required.

---

## 6. MCP & AWS Execution Isolation

- [x] **Dedicated STS Credentials:** The MCP runtime requests an assumed role session specific to the tenant and account being acted upon.
- [x] **Ephemeral Sandboxes:** Workers running MCP servers execute in isolated Linux containers with non-root privileges and no host filesystem access.
- [x] **ExternalId Verification:** Cross-account role assumptions must always specify the tenant's unique `ExternalId`.
