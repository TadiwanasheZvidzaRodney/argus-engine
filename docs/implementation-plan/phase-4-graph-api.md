# Phase 4 — Graph Query API & Aggregation Layer

> **Release:** R1 · **Duration:** 4–5 weeks · **Depends on:** Phase 2 · **Owner:** Backend  
> **Entry criteria:** Graph populated and queryable; tenant-scoped repository exists; sequence numbers available from Phase 3 (or a placeholder graph version before then).

---

## 1. Objective

Provide a stable, cached, tenant-safe read API that lets the canvas request exactly the topology it needs — viewport slices, neighborhoods, search results, aggregates, paths, and snapshots — without ever exposing raw Cypher or unbounded graph traversal.

This phase is the contract boundary between the graph and every user-facing experience.

---

## 2. Architecture mapping

| Architecture component | Phase 4 contribution |
|---|---|
| Resource Graph Dynamic Aggregator | Topology slices, grouping, counts, search, path queries |
| Backend API gateway | REST/OpenAPI endpoints, auth scopes, rate limits |
| PostgreSQL state | Snapshot metadata, search projections (if needed), API quotas |
| Redis cache | Query cache, ETags, single-flight, invalidation by graph sequence |
| WebSocket delta protocol | `as_of` / `seq` alignment so clients can apply deltas safely |

---

## 3. Scope

### In scope

- OpenAPI 3.1 contract for all read endpoints.
- Resource list, detail, and relationship endpoints.
- Viewport/topology slice endpoint with depth, filters, grouping, and truncation.
- Aggregate endpoint for counts and cluster summaries.
- Search with ranking and facets.
- Path and reachability queries with strict cost limits.
- Redis caching, ETags, and invalidation.
- Daily graph snapshots and snapshot diff.
- Generated TypeScript SDK and MSW mocks.
- Tenant isolation, query safety, and performance tests.

### Out of scope

- Write/mutation endpoints (Phase 6).
- Metrics and findings endpoints (Phase 7).
- Cost endpoints (Phase 8).
- Graph Data Science algorithms such as centrality or community detection (evaluate in Phase 7/9).
- Public API for external customers (internal API first; externalization later).
- GraphQL (REST is sufficient and easier to cache and secure).

---

## 4. API surface

### Accounts and resources

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/accounts` | List connected accounts with health and coverage |
| `GET` | `/api/v1/accounts/{accountId}/regions` | Regions and sync status |
| `GET` | `/api/v1/resources` | Filtered resource list (type, account, region, tag, state) |
| `GET` | `/api/v1/resources/{resourceKey}` | Resource detail with attributes and provenance |
| `GET` | `/api/v1/resources/{resourceKey}/relationships` | Direct relationships by direction and type |
| `GET` | `/api/v1/resources/{resourceKey}/neighborhood` | Bounded neighborhood (depth 1–3) |

### Topology

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/topology/query` | Viewport/topology slice with filters, depth, grouping, limits |
| `GET` | `/api/v1/topology/aggregate` | Counts grouped by type/account/region/state |
| `GET` | `/api/v1/topology/search` | Search resources with ranking and facets |
| `POST` | `/api/v1/topology/paths` | Shortest path or reachability between resources |
| `POST` | `/api/v1/topology/blast-radius` | Resources reachable from a source under constraints |

`POST` is used for complex topology queries because filter payloads can exceed practical URL limits.

### Snapshots and freshness

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/topology/snapshots` | List daily snapshots |
| `GET` | `/api/v1/topology/snapshots/{id}` | Snapshot manifest and metadata |
| `POST` | `/api/v1/topology/diff` | Diff two snapshots or snapshot vs current graph |
| `GET` | `/api/v1/topology/version` | Current graph sequence/version for the tenant |

### Topology query request

```json
{
  "root": "arn:aws:ec2:us-east-1:123456789012:vpc/vpc-123",
  "depth": 2,
  "accounts": ["123456789012"],
  "regions": ["us-east-1"],
  "types": ["AWS::EC2::Instance", "AWS::EC2::SecurityGroup", "AWS::S3::Bucket"],
  "relationship_types": ["CONTAINS", "IN_SECURITY_GROUP", "CAN_ACCESS"],
  "include_groups": true,
  "max_nodes": 2000,
  "max_edges": 6000,
  "cursor": null,
  "as_of": null
}
```

### Topology response

```json
{
  "nodes": [
    {
      "id": "arn:aws:ec2:...",
      "type": "AWS::EC2::Instance",
      "name": "web-prod-1",
      "account_id": "123456789012",
      "region": "us-east-1",
      "state": "running",
      "parent_id": "arn:aws:ec2:...:subnet/subnet-123",
      "tags": { "Environment": "prod" },
      "version": 43
    }
  ],
  "edges": [
    {
      "id": "edge_...",
      "source": "arn:aws:ec2:...",
      "target": "arn:aws:ec2:...",
      "type": "IN_SECURITY_GROUP",
      "properties": { "direction": "ingress" }
    }
  ],
  "groups": [
    {
      "id": "arn:aws:ec2:...:vpc/vpc-123",
      "type": "VPC",
      "name": "prod-vpc",
      "parent_id": "region:us-east-1:123456789012",
      "child_count": 42
    }
  ],
  "counts": {
    "nodes": 1240,
    "edges": 3810,
    "truncated": false,
    "by_type": { "AWS::EC2::Instance": 84 }
  },
  "as_of": "2026-11-10T12:00:00Z",
  "seq": 1048577,
  "cursor": null
}
```

**Contract rules:**

- Every node has `id`, `type`, `account_id`, `region`, `version`.
- `parent_id` is present when a node belongs to a container (region, VPC, subnet, account).
- `seq` is the graph commit sequence; the client uses it to detect whether a live delta is newer or older than the fetched slice.
- `truncated=true` and `cursor` indicate more data; clients must not assume completeness.
- `as_of` supports historical snapshot reads; live queries default to current.

---

## 5. Workstreams and tasks

### WS-GAPI-A — Contract and foundations

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P4-01 | OpenAPI 3.1 specification | All endpoints, schemas, errors, examples, auth scopes | L | Backend |
| P4-02 | Query model and validation | Request schemas, limits, filter semantics, depth/result caps | M | Backend |
| P4-03 | Graph query planner | Translates API requests into parameterized Cypher templates | L | Backend |
| P4-04 | Repository query templates | Bounded traversal, grouping, relationship filters, counts | L | Backend |
| P4-05 | Response serialization | Canonical JSON, field selection, null/empty semantics, versioning | M | Backend |
| P4-06 | Error taxonomy | Not found, too broad, timeout, truncated, unsupported filter | S | Backend |

### WS-GAPI-B — Resource and topology endpoints

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P4-07 | Resource list endpoint | Filters, cursor pagination, stable ordering | M | Backend |
| P4-08 | Resource detail endpoint | Attributes, tags, provenance, raw payload link, recent changes | M | Backend |
| P4-09 | Relationship endpoint | Direction, type filters, pagination, inverse relationships | M | Backend |
| P4-10 | Neighborhood endpoint | Depth 1–3, type filters, edge limits, truncation metadata | L | Backend |
| P4-11 | Topology query endpoint | Rooted traversal, groups, counts, cursor, max nodes/edges | L | Backend |
| P4-12 | Aggregate endpoint | Group by type/account/region/state; top-N; counts | M | Backend |
| P4-13 | Group/parent resolution | Account/region/VPC/subnet hierarchy for canvas nesting | M | Backend |
| P4-14 | Freshness/version endpoint | Tenant seq, last event time, last reconciliation time | S | Backend |

### WS-GAPI-C — Search and path analysis

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P4-15 | Search index | Neo4j full-text or Postgres projection; name, ARN, tags, IP, state | L | Backend + Data |
| P4-16 | Search ranking and facets | Exact/prefix/fuzzy ranking; type/account/region facets | M | Backend |
| P4-17 | Command palette API | Lightweight top-N search with icons and breadcrumbs | S | Backend |
| P4-18 | Shortest path | Bounded `shortestPath` with relationship allowlist and cost limits | M | Backend |
| P4-19 | Reachability / blast radius | Variable-length traversal with node/edge/time budgets | L | Backend |
| P4-20 | Path result shaping | Ordered hops, edge semantics, explanation for UI | M | Backend |

### WS-GAPI-D — Caching and performance

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P4-21 | Redis cache layer | Key design, serialization, TTL, tenant prefix, metrics | L | Backend |
| P4-22 | ETag and conditional GET | `ETag`/`If-None-Match`, `304` handling | M | Backend |
| P4-23 | Cache invalidation | Invalidate by tenant/account/resource on graph delta | M | Backend |
| P4-24 | Single-flight | Prevent cache stampedes for identical queries | M | Backend |
| P4-25 | Per-tenant quotas | Request rate, query cost, response size, concurrent traversals | M | Backend + Platform |
| P4-26 | Query timeouts and budgets | Max depth, visited nodes, execution time, graceful truncation | L | Backend |
| P4-27 | Load and benchmark suite | 10k and 100k node datasets; p95 targets; cache hit measurement | L | QA + Backend |

### WS-GAPI-E — Snapshots and diffs

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P4-28 | Snapshot exporter | Daily logical export of nodes/edges to S3 with manifest | L | Data |
| P4-29 | Snapshot metadata | Postgres records, retention, tenant scoping, checksums | M | Backend |
| P4-30 | Snapshot read path | Query historical snapshot for a resource/topology slice | L | Backend |
| P4-31 | Diff service | Added/removed/changed nodes and edges; summary and detail | L | Backend |
| P4-32 | Retention and cleanup | 90-day default; legal hold override; restore procedure | M | Platform |

### WS-GAPI-F — SDK, mocks, and docs

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P4-33 | TypeScript SDK generation | `openapi-typescript` + `openapi-fetch`, typed hooks | M | Frontend + Backend |
| P4-34 | MSW mock handlers | Fixture-backed mocks for every endpoint and state | M | Frontend |
| P4-35 | Contract tests | Schemathesis or Dredd against staging; schema compatibility checks | M | QA |
| P4-36 | API documentation | Redoc/Scalar portal with auth, pagination, errors, examples | M | Backend |
| P4-37 | Frontend integration guide | Topology query patterns, caching, delta alignment, resync | M | Backend + Frontend |

---

## 6. Deliverables

- Published OpenAPI 3.1 contract and documentation portal.
- Resource, relationship, neighborhood, topology, aggregate, search, path, and snapshot endpoints.
- Parameterized graph query planner with tenant scoping and cost limits.
- Redis caching with ETags and delta-based invalidation.
- Generated TypeScript SDK and complete MSW mock suite.
- Daily snapshots and diff API.
- Performance benchmark report at 10k and 100k nodes.
- Query safety and tenant isolation test suite.

---

## 7. Interfaces and contracts

### Filter semantics

- Multiple values within a field are OR; different fields are AND.
- `types` accepts AWS type names and friendly aliases.
- `relationship_types` is an allowlist; unknown types return `400`.
- `depth` max 3 for topology; max 6 for path queries.
- `max_nodes` default 1,000; hard cap 5,000 per response.
- `max_edges` default 3,000; hard cap 15,000.
- Empty result is `200` with empty arrays, not `404`.
- Unknown resource is `404` with a problem document.

### Cache keys

```text
t:{tenant_id}:q:{sha256(normalized_query)}:{graph_seq}
t:{tenant_id}:res:{resource_key}:{graph_seq}
t:{tenant_id}:search:{sha256(query)}:{limit}
```

- TTL: 15s for live topology; 5 minutes for resource detail; 60s for search.
- Invalidation: bump tenant graph sequence on write; cache keys include the sequence so old entries become unreachable and expire.
- ETag: `W/"{tenant_id}:{graph_seq}:{query_hash}"`.
- Never cache across tenants; never cache authorization decisions.

### Query safety rules

- Clients cannot submit Cypher, labels, or relationship names outside the allowlist.
- All queries are constructed from server-side templates with parameters.
- Every query includes `tenant_id` on the anchor node and a tenant guard on traversed nodes.
- Timeouts are enforced at the driver and statement level.
- Results are capped before serialization; truncation is explicit.
- Sensitive attributes (secret values, policy documents with secrets) are redacted by field policy.

### Search ranking

1. Exact ARN match.
2. Exact name match.
3. Name prefix match.
4. Tag key/value match.
5. Tokenized/fuzzy name match.
6. ARN substring.

Tie-breakers: resource type priority (network/identity first), account/region, updated time.

---

## 8. Data and schema changes

New PostgreSQL tables:

- `graph_snapshots` — id, tenant, scope, created_at, node_count, edge_count, manifest_uri, checksum, status.
- `graph_snapshot_diffs` — snapshot pair, summary, created_at, expires_at.
- `api_query_audit` (sampled) — tenant, user, endpoint, query hash, duration, result count, truncated.
- `tenant_quotas` — request/traversal limits and current usage.
- Optional `resource_search` projection if Neo4j full-text does not meet latency.

New Neo4j indexes:

- Full-text index on `name`, `arn`, `tags` values, `private_ip`, `public_ip`.
- Composite indexes for `(tenant_id, type)`, `(tenant_id, account_id, region)`, `(tenant_id, state)`.

Snapshot storage:

- `s3://argus-snapshots/tenant={tenant}/date={YYYY-MM-DD}/nodes.parquet`
- `s3://argus-snapshots/tenant={tenant}/date={YYYY-MM-DD}/edges.parquet`
- Manifest with counts, checksums, schema version.

---

## 9. Exit gate / acceptance criteria

- [ ] OpenAPI contract is published, lint-clean, and versioned.
- [ ] Every endpoint is covered by contract tests and has MSW mocks.
- [ ] Generated TypeScript SDK compiles and is used by a sample frontend page.
- [ ] 1-hop topology query at 10k nodes: p95 < 300ms.
- [ ] 3-hop topology query at 100k nodes: p95 < 1s and respects node/edge caps.
- [ ] Search returns relevant results in < 500ms with facets.
- [ ] Shortest path and blast-radius queries enforce depth, time, and node budgets.
- [ ] Cache hit rate for repeated viewport queries > 70%.
- [ ] ETag/304 behavior works and is tested.
- [ ] Every query path rejects missing tenant context and passes isolation probes.
- [ ] Cypher injection and relationship-allowlist tests pass.
- [ ] Snapshot export and diff work for a 100k-node tenant within the maintenance window.
- [ ] API error responses conform to RFC 9457 and include trace IDs.
- [ ] Load test meets p95 targets with 50 concurrent canvas sessions.

---

## 10. Test and validation plan

| Layer | Tests |
|---|---|
| Unit | Filter normalization, query planner, grouping, ranking, cache keys |
| Contract | OpenAPI schema validation and backward compatibility |
| Integration | Neo4j testcontainers with golden fixture graphs; Redis cache behavior |
| Performance | 10k/100k datasets; 1-hop/3-hop; search; path; concurrent sessions |
| Cache | Invalidation on delta, ETag, stampede, tenant isolation |
| Security | Cypher injection, tenant probes, redaction, quota bypass |
| Snapshot | Export/read/diff/restore; checksum verification; retention cleanup |
| Frontend contract | SDK compilation; MSW parity with OpenAPI; mock scenario coverage |

**Golden datasets:**

- `small`: 3 accounts, 3 regions, 2k resources.
- `medium`: 10 accounts, 5 regions, 25k resources.
- `large`: 30 accounts, 10 regions, 100k resources, 500k edges.

---

## 11. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Unbounded traversals take down Neo4j | Depth/result/time budgets; query allowlist; per-tenant concurrency limits |
| Cache invalidation complexity | Sequence-keyed cache; short TTL; correctness over hit rate |
| Search relevance is poor | Start with deterministic ranking; measure queries; add Postgres trigram if needed |
| API shape churns under frontend pressure | Contract-first; weekly contract review with frontend; version additively |
| Snapshot cost at 100k nodes | Columnar export, compression, incremental snapshots if needed |
| Tenant leakage in cache/search | Tenant-prefixed keys; tenant guard in every query; isolation tests |
| Delta/snapshot mismatch | Include `seq` and `as_of`; client resync when gap detected |

---

## 12. Metrics

- Request rate and error rate by endpoint.
- Latency p50/p95/p99 by endpoint and query shape.
- Truncation rate and average result size.
- Cache hit rate, miss rate, eviction rate.
- Traversal nodes/edges visited per query.
- Query timeout rate.
- Search zero-result rate and click-through (from frontend analytics).
- Snapshot duration and size.
- Per-tenant quota utilization.

---

## 13. Handoff to Phase 5

Phase 5 can assume:

- A stable, typed API for topology, resources, search, paths, and snapshots.
- `seq` and `as_of` semantics for aligning live deltas with fetched slices.
- MSW mocks for every UI state, including empty, partial, truncated, and error.
- Group/parent metadata for nested canvas containers.
- Known performance envelope and response-size limits.
