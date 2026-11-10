# Cross-Cutting — Observability & SRE

> **Applies to:** Phases 0–9  
> **Purpose:** Define how Argus is monitored, alerted, capacity-planned, and operated, including SLIs/SLOs, dashboards, runbooks, and incident response.

---

## 1. Principles

1. **Instrument the user journey, not just the service.** Measure from AWS change to canvas paint, not only queue depth.
2. **Every alert has a runbook and an owner.** No orphan alerts.
3. **SLOs drive priorities.** Error budget burn pauses feature work.
4. **Tenant dimensions are first-class.** Every metric can be sliced by tenant without leaking data.
5. **Audit is separate from logs.** Audit is immutable and access-controlled; logs are operational.
6. **Cardinality is controlled.** No unbounded labels (resource IDs, ARNs) in metrics; use traces/logs for high-cardinality detail.
7. **Synthetic checks cover critical paths.** Login, topology load, action plan, and webhook health are probed continuously.

---

## 2. SLIs and SLOs

| Service | SLI | SLO | Measurement |
|---|---|---|---|
| Control plane | Successful API requests | 99.9% monthly | 2xx+3xx / total, excluding 4xx client errors |
| Canvas API | Read latency | 95% < 500ms | Server histogram by endpoint |
| Topology | Query latency | 95% < 1s | By query shape/depth |
| Event pipeline | AWS change → graph commit | 95% < 30s | Capture timestamp → write timestamp |
| WebSocket | Graph commit → client delivery | 95% < 2s | Commit → ack/fanout |
| Discovery | Sync success | 98% of shards | Succeeded / attempted |
| Reconciliation | Drift repaired | 99% within 24h | Detected → repaired |
| Actions | Plan availability | 99% monthly | Successful plan responses |
| Actions | Execution success | 99% of approved | Excluding user/template errors |
| Metrics | CloudWatch timestamp → client | 95% < 60s | Sample timestamp → SSE delivery |
| Cost | Daily ingestion freshness | 99% < 26h | AWS publish → available |
| Frontend | Core Web Vitals | 75th percentile "good" | LCP, INP, CLS |
| Availability | Public status | 99.9% monthly | Synthetic + real traffic |

### Error budget policy

- **50% burn:** review risky changes; increase testing.
- **75% burn:** freeze non-critical feature launches; reliability work takes priority.
- **100% burn:** incident review, executive sign-off to resume, postmortem required.
- **Fast burn alert:** 2% budget consumed in 1 hour; page on-call.
- **Slow burn alert:** 10% budget consumed in 6 hours; ticket to team.

---

## 3. Telemetry stack

| Signal | Backend | Notes |
|---|---|---|
| Traces | OpenTelemetry → AWS X-Ray or Grafana Tempo | W3C trace context; sample 10% baseline, 100% on errors |
| Metrics | OpenTelemetry → CloudWatch/Prometheus | RED/USE + domain metrics; tenant dimension with cardinality control |
| Logs | Structured JSON → CloudWatch Logs/S3 | Include tenant, request, trace, action IDs; redact secrets/PII |
| Errors | Sentry | Release tagging, source maps, breadcrumbs |
| RUM | Frontend beacon → analytics backend | Web Vitals, canvas performance, errors |
| Audit | PostgreSQL + S3 Object Lock | Separate from operational logs |
| Synthetic | Global canary probes | Login, topology, action plan, public status |

**Correlation:** every request, event, action, and MCP tool call carries a `trace_id`; audit rows store it. The same `request_id` propagates from the browser through the BFF to workers.

---

## 4. Domain metrics

### Discovery and graph

- `sync.jobs.started/succeeded/failed/partial`
- `sync.shards.failed`
- `sync.duration` by account size
- `discovery.api.throttles` by service
- `graph.nodes/edges` by tenant/type
- `graph.write.errors`
- `graph.query.latency` by depth
- `graph.unresolved_edges`
- `reconciliation.drift.count`
- `coverage.supported/mapped/unsupported`

### Events and WebSocket

- `event.ingest.rate`
- `event.lag.capture_to_graph` p50/p95/p99
- `event.duplicates`
- `event.dlq.depth/age`
- `event.replay.count`
- `ws.connections`
- `ws.subscriptions`
- `ws.fanout.latency`
- `ws.disconnects/reconnects`
- `ws.queue.depth`
- `ws.resync.count`

### API and data

- `http.requests` by route/status
- `http.latency` p50/p95/p99
- `http.errors` 4xx/5xx
- `cache.hit_rate` by endpoint
- `query.timeouts`
- `query.truncation_rate`
- `postgres.connections/locks/replication_lag`
- `neo4j.query.latency/transaction_retries/page_cache_hit`
- `redis.evictions/memory`

### Actions and MCP

- `action.requests/plans/approvals/executions`
- `action.plan.latency`
- `action.approval.time`
- `action.execution.duration`
- `action.verification.success`
- `action.rollback.success`
- `action.guardrail.blocks`
- `mcp.tool.calls/errors/timeouts`
- `mcp.sandbox.starts/failures`
- `llm.tokens/cost/latency`
- `killswitch.activations`

### Telemetry, security, cost

- `telemetry.samples/requests`
- `telemetry.cloudwatch.cost_estimate`
- `telemetry.sse.connections`
- `findings.open` by severity
- `findings.rule.evaluation_duration`
- `findings.false_positive_reports`
- `attackpath.query.latency`
- `cost.ingest.freshness`
- `cost.reconciliation.variance`
- `cost.recommendations.open`
- `billing.usage.metered`

### Frontend

- `canvas.load_time`
- `canvas.frame_rate`
- `canvas.long_tasks`
- `canvas.resync`
- `search.latency`
- `inspector.open`
- `web_vitals.lcp/inp/cls`
- `frontend.errors`

---

## 5. Dashboards

| Dashboard | Panels |
|---|---|
| **Platform health** | Request rate, error rate, latency, deploy markers, dependency status |
| **Discovery & sync** | Active jobs, progress, failures, throttles, coverage, duration |
| **Event pipeline** | Ingest rate, lag, queue depth, DLQ, duplicates, replay, graph writes |
| **API & cache** | RED metrics, p95 by endpoint, cache hit, timeouts, truncation |
| **WebSocket** | Connections, subscriptions, fanout latency, disconnects, resync |
| **Graph databases** | Neo4j latency, retries, memory, page cache; Postgres connections, locks, replication |
| **Actions/MCP** | Requests, plans, approvals, executions, rollbacks, guardrail blocks, sandbox health |
| **Security** | Findings by severity, rule duration, suppressions, attack-path usage |
| **Telemetry** | Samples, SSE clients, CloudWatch cost, quota usage |
| **Cost intelligence** | Ingestion freshness, reconciliation variance, recommendations |
| **Frontend RUM** | Web Vitals, canvas performance, errors by release |
| **Tenant health** | Per-tenant request/error/latency, sync status, quota usage, action activity |
| **Unit economics** | Cost per tenant/resource/event/metric request, margin |

Tenant dashboards are access-controlled and show aggregated metrics only; no cross-tenant data in shared views.

---

## 6. Alerts

| Alert | Severity | Threshold | Runbook |
|---|---|---|---|
| API error rate | P1 | > 5% for 5 min | `api-errors.md` |
| API latency | P2 | p95 > 2s for 10 min | `api-latency.md` |
| Event lag | P1 | p95 > 2 min for 10 min | `event-lag.md` |
| DLQ depth | P2 | > 100 messages or age > 15 min | `dlq-backlog.md` |
| Sync failure | P2 | > 10% shards failed in 30 min | `sync-failures.md` |
| Reconciliation drift | P3 | > 1% resources stale for 24h | `reconciliation-drift.md` |
| WS disconnect spike | P2 | > 20% connections drop in 5 min | `ws-outage.md` |
| Neo4j latency | P1 | p95 > 2s for 10 min | `neo4j-latency.md` |
| Postgres failover/replication | P1 | Replica lag > 30s or failover | `postgres-failover.md` |
| Action execution failure | P1 | Any approved action fails verification | `action-failure.md` |
| Rollback failure | P1 | Any rollback fails | `rollback-failure.md` |
| Guardrail bypass attempt | P1 | Any detected bypass | `security-incident.md` |
| Kill switch activated | P1 | Manual/auto | `killswitch.md` |
| CloudWatch cost | P2 | > 120% of tenant budget | `telemetry-cost.md` |
| Cost anomaly | P3 | > 25% day-over-day for tenant | `cost-anomaly.md` |
| Cert/secret expiry | P2 | < 30 days | `certificate-rotation.md` |
| Backup failure | P1 | Any critical backup fails | `backup-restore.md` |
| SLO fast burn | P1 | 2% budget in 1h | `slo-burn.md` |

All alerts include tenant impact, dashboard link, runbook link, and recent deploy marker.

---

## 7. Runbook library

Minimum runbooks before GA:

**Platform**
- `deploy-rollback.md`
- `api-errors.md`
- `api-latency.md`
- `dependency-outage.md`
- `certificate-rotation.md`
- `backup-restore.md`
- `postgres-failover.md`
- `neo4j-latency.md`
- `redis-outage.md`

**Discovery and events**
- `sync-failures.md`
- `aws-throttling.md`
- `event-lag.md`
- `dlq-backlog.md`
- `event-storm.md`
- `reconciliation-drift.md`
- `cross-account-policy.md`

**WebSocket/frontend**
- `ws-outage.md`
- `ws-reconnect-storm.md`
- `frontend-error-spike.md`
- `canvas-performance.md`

**Actions/security**
- `action-failure.md`
- `rollback-failure.md`
- `mcp-sandbox-failure.md`
- `llm-outage.md`
- `guardrail-bypass.md`
- `killswitch.md`
- `security-incident.md`
- `tenant-isolation-incident.md`

**Tenant/operations**
- `tenant-onboarding.md`
- `tenant-offboarding.md`
- `tenant-suspension.md`
- `support-impersonation.md`
- `billing-metering.md`

Each runbook contains: symptoms, impact, diagnosis commands, mitigation, rollback, escalation, and post-incident actions.

---

## 8. Capacity model

Track utilization and scale triggers:

| Component | Primary metric | Scale trigger | Scaling action |
|---|---|---|---|
| API | CPU, RPS, p95 | > 70% CPU or p95 > 400ms for 10 min | Add tasks; tune queries |
| WebSocket | Connections per task, memory | > 70% capacity | Add tasks; shard by tenant |
| Event workers | Queue depth, age | Age > 5 min | Add consumers; increase batch |
| Neo4j | Page cache hit, CPU, query p95 | Hit < 95% or p95 > 800ms | Scale up/out; add read replica; dedicated DB |
| Aurora | CPU, connections, replica lag | > 70% CPU or lag > 5s | Scale instance; add reader |
| Redis | Memory, evictions, CPU | Evictions > 0 or CPU > 70% | Scale up; shard by tenant |
| S3 | Request rate | Throttling | Prefix strategy; request limits |
| CloudWatch | API throttling, cost | Throttles or budget | Batch, cache, reduce resolution |
| MCP sandbox | Concurrent tasks, queue | Queue > 5 min | Increase concurrency; pool read sessions |
| LLM | Tokens/min, latency | Quota or p95 > 10s | Request quota; route models; cache |

**Headroom target:** 2× peak for critical components, or a documented scaling playbook that can add capacity within 15 minutes.

---

## 9. On-call and incident response

### Severity

| Severity | Definition | Response |
|---|---|---|
| **P1** | Customer-facing outage, data loss, security breach, write safety issue | Page immediately; incident commander; status page |
| **P2** | Major degradation, single-tenant outage, event lag > 10 min | Page during business hours/on-call; update status |
| **P3** | Minor degradation, non-critical feature down | Ticket; next business day |
| **P4** | Cosmetic or informational | Backlog |

### Process

1. Detect and acknowledge.
2. Declare severity and incident commander.
3. Contain impact (disable feature, kill switch, fail over).
4. Communicate internally and externally.
5. Mitigate and restore.
6. Verify data integrity and tenant isolation.
7. Postmortem within 5 business days for P1/P2; blameless; action items tracked.

### On-call

- Primary/secondary rotation, weekly.
- Handoff document with active incidents, risks, and deploys.
- Escalation to service owners and engineering leadership.
- Compensation and workload review quarterly.

---

## 10. Synthetic monitoring

Run every 1–5 minutes from multiple regions:

- Login and session refresh.
- Load a seeded topology (small).
- Search for a known resource.
- Open a WebSocket and receive a synthetic delta.
- Create and approve a low-risk action in a sandbox tenant (non-destructive plan only).
- Check audit write and read.
- Check status page and public endpoints.

Synthetic failures page on-call if they persist for two consecutive checks.

---

## 11. Observability acceptance criteria

- [ ] Every service emits traces, metrics, and structured logs with tenant/request IDs.
- [ ] Every user journey has a dashboard and at least one SLO.
- [ ] Every alert has a runbook and owner.
- [ ] Audit is immutable and separate from logs.
- [ ] High-cardinality data is in traces/logs, not metric labels.
- [ ] Synthetic checks cover login, topology, search, WS, and action planning.
- [ ] Tenant health and unit economics dashboards exist.
- [ ] On-call rotation, escalation, and status page are live before GA.
- [ ] Load and chaos results are stored and reviewed.
