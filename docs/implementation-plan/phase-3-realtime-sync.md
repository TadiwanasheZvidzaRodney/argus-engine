# Phase 3 — Real-Time Event Synchronization

> **Release:** R2 · **Duration:** 5–6 weeks · **Depends on:** Phase 2 · **Owner:** Backend + Platform  
> **Entry criteria:** Graph backfill and reconciliation stable; onboarding template versioned; WebSocket service skeleton deployed.

---

## 1. Objective

Make the graph converge within seconds of real AWS changes and push only the affected deltas to connected canvases. At the end of this phase, a security-group change in a customer account appears on an open canvas in under 30 seconds (p95), duplicate or out-of-order events cannot corrupt the graph, and missed events are repaired by reconciliation.

---

## 2. Architecture mapping

| Architecture component | Phase 3 contribution |
|---|---|
| AWS Config + EventBridge global bus | Cross-account event ingestion, buffering, replay, DLQ |
| SQS / event processing | Normalization, idempotency, delta application |
| Neo4j live topology | Incremental node/edge upserts and tombstones |
| WebSocket gateway | Tenant-scoped subscriptions, delta fanout, resume |
| CloudTrail | Change attribution and coverage for non-Config resources |
| Reconciliation | Gap detection and repair |

---

## 3. Scope

### In scope

- Onboarding template v2 with Config, EventBridge, CloudTrail, and IAM resources.
- Regional ingress event buses and central hub forwarding.
- SQS queues with DLQ, encryption, retention, and replay.
- Canonical event envelope, dedupe store, and ordering rules.
- Config event normalization and graph delta application.
- CloudTrail enrichment for actor/API attribution (best effort).
- Scheduled reconciliation and gap detection.
- WebSocket gateway with auth, subscriptions, resume, backpressure.
- Delta protocol and client resync contract.
- Replay tooling and operational dashboards.

### Out of scope

- Metrics streaming (Phase 7).
- Action progress streaming (Phase 6 reuses the gateway).
- Full CloudTrail Lake analytics.
- Event-driven auto-remediation.
- Real-time cost updates (Phase 8 uses daily data).

---

## 4. Event architecture

### Ingestion path

```text
Customer AWS account / region
  ├─ AWS Config recorder
  │    └─ Config change event ──► EventBridge (customer account)
  │                                  └─ cross-account rule ──► Argus regional ingress bus
  ├─ CloudTrail management events ──► EventBridge / trail ──► enrichment (optional)
  └─ Selected native service events ──► EventBridge rule ──────┘
                                      │
                         ┌────────────▼─────────────┐
                         │ Argus regional ingress   │
                         │ bus + archive + DLQ      │
                         └────────────┬─────────────┘
                                      │ forwarder / hub
                         ┌────────────▼─────────────┐
                         │ Central event bus        │
                         │ (per region or hub)      │
                         └────────────┬─────────────┘
                                      │
                         ┌────────────▼─────────────┐
                         │ SQS standard queue       │
                         │ + DLQ + replay           │
                         └────────────┬─────────────┘
                                      │
                    ┌─────────────────▼─────────────────┐
                    │ Normalizer → dedupe → delta worker │
                    └─────────────────┬─────────────────┘
                                      │
                    ┌─────────────────▼─────────────────┐
                    │ Neo4j graph writer + outbox        │
                    └─────────────────┬─────────────────┘
                                      │
                    ┌─────────────────▼─────────────────┐
                    │ Redis Streams + WS gateway         │
                    └─────────────────┬─────────────────┘
                                      │
                                  Browser canvas
```

**Cross-region note:** Do not assume arbitrary cross-region EventBridge delivery. Use a regional ingress bus in every supported region and forward to the hub through a dedicated forwarder (native cross-region bus target where available, otherwise a small Lambda/API destination). Validate the chosen mechanism per region before Phase 3 exit.

### Why Config + CloudTrail + native events

- **Config** provides resource configuration snapshots and change notifications for supported types.
- **CloudTrail** captures control-plane API calls, actor identity, and changes for resources Config does not cover.
- **Native service events** (e.g., EC2 state changes, S3 events) fill gaps but are high-volume and selectively enabled.
- **Reconciliation** is the ultimate correctness backstop.

---

## 5. Workstreams and tasks

### WS-EVT-A — Ingestion infrastructure

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P3-01 | Onboarding template v2 | Config recorder/delivery channel, EventBridge rules, CloudTrail trail, IAM roles, S3 bucket | L | Backend + Security |
| P3-02 | Cross-account bus policy | Central bus resource policy scoped by account/principal; organization-aware conditions | L | Platform |
| P3-03 | Regional ingress topology | Bus per supported region; hub forwarding; archive; encryption | L | Platform |
| P3-04 | Queue topology | Standard queue, DLQ, redrive policy, visibility timeout, retention, encryption | M | Platform |
| P3-05 | Event archive | EventBridge archive or S3 archive for replay; retention policy | M | Platform |
| P3-06 | EventBridge Scheduler | Reconciliation, health checks, backlog alarms | S | Platform |
| P3-07 | Template upgrade path | Versioned template; detect drift; prompt re-deploy | M | Backend |

### WS-EVT-B — Normalization and delta processing

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P3-08 | Event envelope v1 implementation | Serializer/deserializer, schema registry, validation at ingress | M | Backend |
| P3-09 | Dedupe store | Redis/DynamoDB idempotency keys with TTL; metrics for duplicates | M | Backend |
| P3-10 | Config normalizer | Configuration item → canonical resource model; change type detection | L | Backend |
| P3-11 | CloudTrail normalizer | API call → actor/resource/action enrichment; conservative fallback | M | Backend |
| P3-12 | Delta applier | Insert/update/delete nodes and edges with version and capture-time guards | L | Backend |
| P3-13 | Out-of-order handling | Last-write-wins by version; ignore stale events; log anomalies | M | Backend |
| P3-14 | Deletion semantics | Config `DELETE`, CloudTrail delete APIs, tombstones, edge cleanup | M | Backend |
| P3-15 | Relationship deltas | Recompute affected edges only; queue unresolved edges | L | Data |
| P3-16 | Poison message handling | Schema errors to DLQ; retry policy; operator inspection | M | Backend |
| P3-17 | Batch/coalesce writes | Micro-batching per resource/tenant; transaction sizing | M | Backend |

### WS-EVT-C — Reconciliation and replay

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P3-18 | Gap detection | Compare event sequence/last-seen to inventory; flag stale resources | M | Backend |
| P3-19 | Reconciliation scheduler | Hourly/daily incremental sync; priority for high-risk resources | M | Backend |
| P3-20 | Replay tool | Replay DLQ or time window; dry-run; idempotent; audit | L | Backend |
| P3-21 | Event storm protection | Per-tenant rate limits, coalescing, priority levels, circuit breaker | L | Backend |
| P3-22 | Tenant fairness | Queue partition or weighted consumption per tenant | M | Backend |
| P3-23 | Event lineage | Store source event ID, capture time, trace ID on graph writes | S | Backend |

### WS-EVT-D — WebSocket gateway and delta protocol

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P3-24 | WS gateway service | FastAPI WebSocket service on ECS behind ALB; health, metrics, graceful drain | L | Backend + Platform |
| P3-25 | Connection auth | One-time ticket or secure cookie; tenant/role validation; expiry | M | Backend + Security |
| P3-26 | Subscription model | Subscribe/unsubscribe by account, region, resource IDs, topology scope | L | Backend |
| P3-27 | Redis fanout | Pub/sub plus bounded Streams for replay; per-tenant channels | L | Backend |
| P3-28 | Sequence and resume | Monotonic per-tenant sequence; cursor; gap detection; resync fallback | L | Backend |
| P3-29 | Delta protocol v1 | Message types, versioning, batching, compression, size limits | M | Backend |
| P3-30 | Backpressure | Per-connection queue, coalescing window, drop policy for low-priority events | L | Backend |
| P3-31 | Heartbeat and reconnect | Ping/pong, idle timeout, reconnect storm protection | M | Backend + Frontend |
| P3-32 | Presence and connection registry | Active connections per tenant/user; admin visibility | S | Backend |
| P3-33 | Load balancer tuning | Idle timeout, sticky-less design, target group settings | S | Platform |

### WS-EVT-E — Observability and operations

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P3-34 | Event lag metrics | Capture→ingest→graph→WS latency; per tenant/account/region | M | Platform |
| P3-35 | Queue and DLQ dashboards | Depth, age, redrive, poison rate | M | Platform |
| P3-36 | WS dashboards | Connections, subscription counts, delivery latency, disconnects, queue depth | M | Platform |
| P3-37 | Alerts | Event lag > 2m, DLQ > 0, queue age > 5m, WS error spike, reconcile failure | M | Platform |
| P3-38 | Runbooks | Event storm, DLQ backlog, cross-account policy failure, WS outage, replay | M | Platform |
| P3-39 | Load tests | 1k events/s sustained, 10k burst, 10k WS connections, reconnect storm | L | QA + Platform |

---

## 6. Deliverables

- Updated onboarding stack enabling Config, EventBridge, CloudTrail, and IAM.
- Regional ingress buses, central hub, queues, DLQ, archive, and replay.
- Canonical event envelope and schema registry integration.
- Idempotent, version-aware delta processor.
- WebSocket gateway with tenant-scoped subscriptions and resume.
- Delta protocol contract and frontend integration guide.
- Event lag, queue, and WS dashboards with alerts.
- Replay tool and operational runbooks.
- Load-test report for event and connection targets.

---

## 7. Interfaces and contracts

### Delta protocol messages

```json
{
  "type": "graph.delta",
  "schema_version": "1.0",
  "tenant_id": "tnt_...",
  "seq": 1048577,
  "batch_id": "batch_...",
  "sent_at": "2026-11-10T12:00:01Z",
  "changes": [
    {
      "op": "upsert",
      "entity": "node",
      "id": "arn:aws:ec2:...",
      "type": "AWS::EC2::Instance",
      "account_id": "123456789012",
      "region": "us-east-1",
      "version": 43,
      "properties": { "state": "stopped" }
    },
    {
      "op": "delete",
      "entity": "edge",
      "source": "arn:aws:ec2:...",
      "relationship": "IN_SECURITY_GROUP",
      "target": "arn:aws:ec2:...:security-group/sg-..."
    }
  ]
}
```

Other message types:

- `graph.snapshot_required` — client must reload the current viewport.
- `sync.progress` — backfill/reconciliation progress for the account.
- `connection.ack` — subscription accepted with current sequence.
- `error` — structured error with retry guidance.

### Sequence and resume rules

- Sequence is monotonic per tenant, assigned at graph commit, not at AWS capture.
- Client stores the last applied `seq`.
- On reconnect, client sends `resume_from_seq`.
- If the requested sequence is within the Redis Stream retention window, the gateway replays missed deltas.
- If it is older, the gateway responds with `graph.snapshot_required`; the client refetches the viewport.
- Gaps detected client-side trigger the same resync path.

### Subscription message

```json
{
  "type": "subscribe",
  "accounts": ["123456789012"],
  "regions": ["us-east-1"],
  "resource_ids": ["arn:aws:ec2:..."],
  "include": ["nodes", "edges", "sync_progress"]
}
```

Limits: max 50 accounts, 20 regions, 2,000 explicit resource IDs per connection; viewport subscriptions are preferred over explicit IDs.

---

## 8. Data and schema changes

New PostgreSQL tables:

- `event_ingest_log` (optional, sampled) — source, event ID, received time, status.
- `event_dlq_index` — DLQ message metadata for operator tooling.
- `ws_connection_audit` — connection open/close, tenant, user, reason.
- `reconciliation_runs` — scope, counts, drift, duration.

New Redis structures:

- `dedupe:{tenant}:{idempotency_key}` — TTL 7 days.
- `stream:{tenant}:deltas` — bounded stream, 5–15 minute retention.
- `seq:{tenant}` — monotonic counter (or database sequence).
- `ws:subs:{tenant}` — subscription registry (optional, instance-local).

New graph properties:

- `last_event_id`, `last_event_at`, `last_capture_at`, `graph_version` on nodes.
- `last_seen` on edges.

Retention:

- Event archive: 30 days.
- Redis delta stream: 15 minutes (tunable).
- Event ingest log: 30 days.
- WS connection audit: 90 days.

---

## 9. Exit gate / acceptance criteria

- [ ] Account onboarding enables Config/EventBridge/CloudTrail and verifies event flow end-to-end.
- [ ] A change made in a sandbox account reaches the graph and an open canvas with p95 < 30s, target < 10s.
- [ ] Duplicate events produce one graph write and no duplicate nodes/edges.
- [ ] Out-of-order events do not regress newer state.
- [ ] Deletion events tombstone resources and remove affected edges.
- [ ] DLQ replay repairs a deliberately corrupted graph without duplicates.
- [ ] Reconciliation detects and repairs a missed event within the configured interval.
- [ ] 10,000 concurrent WebSocket connections sustain p95 delta delivery < 2s.
- [ ] Reconnect after a 5-minute disconnect resumes without a full reload when the cursor is in retention.
- [ ] A cursor older than retention triggers a clean snapshot resync.
- [ ] Event lag, queue, and WS dashboards and alerts are live.
- [ ] Event storm test does not overwhelm graph writes; low-priority events coalesce or drop safely.
- [ ] Cross-account bus policy rejects unauthorized source accounts.
- [ ] Tenant isolation tests pass for queues, streams, WS channels, and graph writes.

---

## 10. Test and validation plan

| Layer | Tests |
|---|---|
| Unit | Envelope validation, dedupe, version guards, subscription matching, sequence assignment |
| Contract | Event schema compatibility; delta message schema; WS protocol |
| Integration | Real sandbox Config changes; EventBridge cross-account delivery; SQS/DLQ; Redis Streams |
| Graph correctness | Create/update/delete EC2, SG, S3, IAM role; assert nodes/edges and versions |
| Ordering | Inject shuffled and duplicated events; assert final state |
| Replay | Corrupt a node, replay events, assert convergence |
| Resilience | Broker outage, worker crash mid-batch, Redis failover, Neo4j restart |
| Performance | 1k events/s, 10k burst, 10k WS connections, 100 subscriptions per connection |
| Security | Forged events, wrong tenant ID, unauthorized subscription, ticket replay |

**Chaos scenarios:**

- Kill the delta worker after graph commit but before outbox publish → outbox retry must deliver.
- Pause the queue consumer for 10 minutes → backlog drains without data loss.
- Drop 1% of events → reconciliation repairs within the interval.

---

## 11. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Config coverage gaps | CloudTrail and native events; reconciliation; coverage report |
| Cross-account EventBridge policy misconfiguration | Template validation, onboarding self-test, health checks |
| Event storms after deployments | Per-tenant limits, coalescing, priority queues, backpressure |
| Duplicate/out-of-order corruption | Version guards, idempotency keys, idempotent graph writes |
| WebSocket fanout cost at scale | Subscription scoping, coalescing, Redis Streams, horizontal gateway scaling |
| Missed events during outages | Durable queue, DLQ, archive, scheduled reconciliation |
| Cross-region forwarding complexity | Regional ingress buses; explicit supported-region matrix; spike early |
| Event schema drift | Schema registry, versioned envelope, consumer compatibility tests |

---

## 12. Metrics

- Change-to-canvas latency p50/p95/p99.
- Event ingestion rate and duplicate rate.
- DLQ depth and age.
- Graph write failure rate.
- Reconciliation drift count per run.
- WebSocket connections, subscription count, delivery latency, disconnect rate.
- Reconnect success rate without full reload.
- Events per tenant per minute (for capacity and fairness).
- Cost per 1M events.

---

## 13. Handoff to Phase 6 and Phase 7

Phase 6 can assume:

- A reliable WS gateway for action progress messages.
- Graph freshness and reconciliation guarantees.
- Event lineage for verification after mutations.

Phase 7 can assume:

- Tenant-scoped fanout and backpressure patterns.
- Event lag and queue observability.
- A place to add new message types without breaking clients.
