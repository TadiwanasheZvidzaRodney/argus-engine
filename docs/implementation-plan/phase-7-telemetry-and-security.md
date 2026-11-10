# Phase 7 — Live Telemetry & Security Intelligence

> **Release:** R3 · **Duration:** 5–6 weeks · **Depends on:** Phase 4, Phase 5 · **Owner:** Backend + Frontend + Security  
> **Entry criteria:** Canvas overlays framework available; graph and findings storage ready; CloudWatch read permissions validated.

---

## 1. Objective

Turn the topology from a map into an operating picture: stream live CloudWatch metrics onto visible nodes, evaluate security posture continuously, visualize attack paths, and hand findings directly into the Phase 6 action engine.

At the end of this phase, a user can see which resources are unhealthy, which are exposed, and how an internet attacker could reach sensitive data — without leaving the canvas.

---

## 2. Architecture mapping

| Architecture component | Phase 7 contribution |
|---|---|
| Live metrics & overlays | CloudWatch metric pipeline, node micro-charts, SSE streaming |
| Security & IAM attack surface visualizer | Rule engine, findings, attack-path queries, red edge rendering |
| Neo4j graph | Security traversals, reachability, effective-access edges |
| PostgreSQL state | Findings, rule versions, suppressions, metric quotas |
| Phase 6 action engine | Remediation handoff and status linkage |

---

## 3. Scope

### In scope

- Viewport-driven CloudWatch metric subscriptions.
- Batching, caching, downsampling, and SSE streaming.
- Metric catalog and node micro-charts.
- Static-threshold and EWMA/z-score anomaly indicators.
- Declarative security rule engine with 20 initial rules.
- Findings model, lifecycle, suppression, and risk acceptance.
- Attack-path and blast-radius queries.
- Security and metrics overlays on the canvas.
- Remediation handoff to Phase 6.
- Optional ingestion of Security Hub/GuardDuty findings.
- Cost controls and per-tenant telemetry budgets.

### Out of scope

- Long-term metrics warehouse or full observability platform.
- Custom customer-authored rules (design the extension point, ship curated rules).
- Automated remediation without approval.
- Real-time log analysis or SIEM.
- CloudTrail Lake analytics.
- Anomaly detection using ML models beyond statistical baselines.
- Cost overlay (Phase 8).

---

## 4. Metric pipeline

```text
Canvas viewport
  → subscribe(resource IDs, metric sets, resolution)
  → telemetry API validates scope and quotas
  → subscription registry (Redis)
  → metric collector (per account/region shard)
      → batch CloudWatch GetMetricData (≤500 metrics/call)
      → normalize samples
      → Redis cache (1m/5m)
      → publish to tenant channel
  → SSE gateway
  → browser charts
```

### Design rules

- **Batch by account/region.** One CloudWatch call can request up to 500 metrics; group compatible periods and statistics.
- **Cache before fanout.** Multiple users viewing the same resource share one CloudWatch request within the cache window.
- **Resolution tiers.** 1-minute for selected/alerting resources, 5-minute for other visible resources, 1-hour for historical context.
- **Viewport only.** Do not poll metrics for collapsed or off-screen resources.
- **Pause when hidden.** The client stops subscriptions when the tab is hidden; the collector expires idle subscriptions.
- **Quota-aware.** Per-tenant metric budget; degrade to 5-minute or top-N sampling when exceeded.
- **No metric data in Neo4j.** Metrics are time-series cache data, not graph properties.

### Metric catalog

| Resource | Metrics |
|---|---|
| EC2 | CPUUtilization, NetworkIn/Out, DiskReadOps/WriteOps, StatusCheckFailed |
| RDS/Aurora | CPUUtilization, DatabaseConnections, FreeableMemory, Read/WriteIOPS, Latency |
| ALB/NLB | RequestCount, TargetResponseTime, HTTPCode_ELB_5XX, HealthyHostCount |
| Lambda | Invocations, Errors, Throttles, Duration, ConcurrentExecutions |
| SQS | ApproximateNumberOfMessagesVisible, AgeOfOldestMessage |
| SNS | NumberOfMessagesPublished, NumberOfNotificationsFailed |
| DynamoDB | ConsumedRead/WriteCapacityUnits, ThrottledRequests |
| ECS/EKS | CPUUtilization, MemoryUtilization, RunningTaskCount/PodCount |
| S3 | BucketSizeBytes, NumberOfObjects (daily) |
| API Gateway | Count, 4XXError, 5XXError, Latency |
| CloudFront | Requests, BytesDownloaded, 4xx/5xxErrorRate |

---

## 5. Security rule engine

### Rule model

```yaml
id: sg-public-admin-port
version: 3
severity: critical
title: Security group exposes an administrative port to the internet
resource_types: [AWS::EC2::SecurityGroup]
evaluator: graph_query
query: security/sg_public_sensitive_port.cypher
evidence: [sg_id, port, cidr, attached_resources]
remediation_action: network.restrict_sg_ingress
references: [CIS-AWS-5.2, NIST-AC-4]
```

Rules are versioned, tested against fixture graphs, and rolled out with a changelog. Findings store the rule version so results are reproducible.

### Initial rule catalog (20)

| ID | Severity | Check |
|---|---|---|
| `sg-public-admin-port` | Critical | SG ingress from `0.0.0.0/0`/`::/0` to 22, 3389, 3306, 5432, 6379, 9200, 27017 |
| `sg-public-all-ports` | High | SG ingress from internet on all ports/protocols |
| `sg-public-uncommon-port` | Medium | Any other internet ingress |
| `s3-public-policy` | Critical | S3 bucket policy or ACL grants public access |
| `s3-no-default-encryption` | Medium | S3 bucket lacks default SSE |
| `s3-no-tls-enforcement` | Medium | Bucket policy does not deny non-TLS access |
| `s3-no-versioning` | Low | Versioning disabled on data bucket |
| `ebs-unencrypted` | Medium | EBS volume not encrypted |
| `rds-unencrypted` | Medium | RDS storage not encrypted |
| `rds-publicly-accessible` | Critical | RDS instance publicly accessible |
| `iam-wildcard-action-resource` | High | Policy allows `Action:*` and `Resource:*` |
| `iam-privilege-escalation` | Critical | Policy grants known escalation combinations |
| `iam-trust-wildcard-principal` | Critical | Role trust policy allows `*` |
| `iam-cross-account-trust-outside-org` | High | Trust policy allows accounts outside the organization |
| `iam-old-access-key` | Medium | Active access key older than 90 days |
| `iam-root-access-key` | Critical | Root account has an access key |
| `lambda-public-url` | High | Lambda function URL auth type is `NONE` |
| `apigw-unauthenticated` | High | API Gateway route/method has no authorization |
| `cloudtrail-not-multiregion` | Medium | No multi-region CloudTrail trail |
| `guardduty-disabled` | Medium | GuardDuty detector absent/disabled |

Additional rules can be added after the initial catalog is stable.

### Finding lifecycle

```text
OPEN → ACKNOWLEDGED → (RESOLVED | RISK_ACCEPTED | SUPPRESSED)
```

- Findings are deduplicated by `(rule_id, resource_id, finding_key)`, where `finding_key` is a stable sub-identifier such as a port/CIDR or policy statement. The evidence hash detects changes and drives reopening, but does not create a new finding on every scan.
- `first_seen`, `last_seen`, and `resolved_at` are tracked.
- Suppressions have an owner, reason, and expiry; expired suppressions reopen findings.
- Risk acceptance requires an approver and expiry.
- A finding reopens automatically if the evidence changes after resolution.
- Remediation links to a Phase 6 action and reflects its status.

---

## 6. Attack-path analysis

### Paths to model

1. **Internet → exposed compute → IAM role → data**
   - Internet → SG open port → ENI/EC2/ALB → instance role → S3/RDS/Secrets.
2. **Internet → public load balancer → target → role → data**
   - ALB/NLB → target group → EC2/Lambda → role → data store.
3. **Compromised identity → privilege escalation**
   - IAM role → `iam:PassRole`/`lambda:CreateFunction`/`iam:CreatePolicyVersion` → admin.
4. **Cross-account trust chain**
   - Role in account A → assumes role in account B → sensitive resource.
5. **Public data path**
   - Internet → public S3 object/bucket policy.

### Query strategy

- Materialize `CAN_ACCESS` edges for high-value actions (`s3:GetObject`, `secretsmanager:GetSecretValue`, `rds:Connect`, `kms:Decrypt`) from IAM policies and resource policies. Recompute on policy or attachment change.
- Use bounded variable-length paths (max 8 hops) with node/edge allowlists and time budgets.
- Rank paths by severity, hop count, and exposure.
- Cache path results per graph version; invalidate on delta.
- Provide an explanation payload for the UI: each hop, edge type, and why it matters.

### Example Cypher shape

```cypher
MATCH p = shortestPath(
  (internet:Internet {tenant_id: $tenant})<-[:EXPOSES]-(sg:SecurityGroup {tenant_id: $tenant})
  <-[:IN_SECURITY_GROUP]-(eni:Resource {tenant_id: $tenant})
  <-[:HAS_ENI]-(compute:Resource {tenant_id: $tenant})
  -[:HAS_ROLE|CAN_ACCESS*1..3]->(data:Resource {tenant_id: $tenant})
)
WHERE data.type IN $sensitive_types
RETURN p
LIMIT 25
```

Queries are prebuilt templates with parameters; no client-supplied Cypher.

---

## 7. Workstreams and tasks

### WS-OBS-A — Metrics pipeline

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P7-01 | Telemetry subscription API | Scope validation, metric selection, quotas, TTL | M | Backend |
| P7-02 | Subscription registry | Redis-backed subscriptions, idle expiry, per-tenant limits | M | Backend |
| P7-03 | CloudWatch adapter | `GetMetricData` batching, retries, throttling, metric math | L | Backend |
| P7-04 | Metric collector service | Per-account/region shards, aligned polling, fanout | L | Backend + Platform |
| P7-05 | Cache and downsampling | 1m/5m tiers, TTL, key design, invalidation | M | Backend |
| P7-06 | SSE gateway | Auth, subscription binding, keepalive, reconnect, backpressure | L | Backend |
| P7-07 | Sample normalization | Units, timestamps, null handling, outlier flags | M | Backend |
| P7-08 | Quota and cost controls | Per-tenant metric budget, degradation, cost accounting | M | Backend + Platform |
| P7-09 | Load test | 500 visible resources × 3 metrics, 1k SSE clients | L | QA + Platform |

### WS-OBS-B — Metrics UI

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P7-10 | Sparkline components | Canvas-safe micro-charts, no layout thrash | M | Frontend |
| P7-11 | Inspector metrics tab | Time-series charts, range selector, units, thresholds | L | Frontend |
| P7-12 | Node badges | CPU/health/error indicators with LOD rules | M | Frontend |
| P7-13 | Anomaly indicators | Threshold and EWMA/z-score chips; baseline windows | M | Backend + Frontend |
| P7-14 | Subscription lifecycle | Subscribe on viewport, unsubscribe off-screen, pause on hidden | M | Frontend |
| P7-15 | SSE client | Reconnect with Last-Event-ID, dedupe, ordering | M | Frontend |
| P7-16 | Degraded states | No data, permission denied, throttled, stale | S | Frontend |

### WS-OBS-C — Security rules and findings

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P7-17 | Rule engine | Declarative rule loading, versioning, evaluation, evidence capture | L | Security + Backend |
| P7-18 | Rule test harness | Fixture graphs, expected findings, false-positive corpus | L | Security + QA |
| P7-19 | Initial 20 rules | Rule definitions, queries, severity, remediation mapping | XL | Security |
| P7-20 | Findings schema and API | CRUD-lite, status transitions, assignment, suppression, risk acceptance | L | Backend |
| P7-21 | Findings evaluation triggers | On graph delta (debounced), daily full scan, manual rescan | M | Backend |
| P7-22 | Deduplication and lifecycle | Evidence hash, reopening, suppression expiry, audit events | M | Backend |
| P7-23 | Effective access materialization | IAM/resource policy → `CAN_ACCESS` edges for high-value actions | L | Backend + Security |
| P7-24 | Security Hub/GuardDuty ingestion (optional) | Normalize external findings, dedupe, link to resources | M | Backend |
| P7-25 | Findings UI | List, filters, detail, evidence, status actions, bulk acknowledge | L | Frontend |
| P7-26 | Security dashboard | Counts by severity/account/region, trends, top risks | M | Frontend |

### WS-OBS-D — Attack paths and overlays

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P7-27 | Attack-path query templates | Internet→compute→role→data, privilege escalation, cross-account | L | Backend + Security |
| P7-28 | Path ranking and explanation | Severity, hop count, exposure; per-hop rationale | M | Backend |
| P7-29 | Path result API | Nodes, edges, evidence, limits, cache | M | Backend |
| P7-30 | Security overlay | Heatmap by severity, red exposed edges, legend, filters | L | Frontend |
| P7-31 | Metrics overlay | Node badges and sparklines layer | M | Frontend |
| P7-32 | Attack-path mode | Select source/target or show internet paths; dim unrelated graph | L | Frontend |
| P7-33 | Inspector security tab | Findings, evidence, attack paths, remediation links | M | Frontend |
| P7-34 | Layer controls | Toggle security/metrics/cost/changes; persist preferences | M | Frontend |
| P7-35 | Remediation handoff | "Fix" opens Phase 6 intent with prefilled parameters | L | Backend + Frontend |

---

## 8. Deliverables

- Telemetry subscription API, collector, cache, and SSE gateway.
- Metric catalog and canvas/inspector visualizations.
- Anomaly indicators.
- Rule engine with 20 tested rules and findings lifecycle.
- Effective-access materialization for high-value actions.
- Attack-path queries, ranking, and visual mode.
- Security and metrics overlays.
- Findings dashboard and remediation handoff.
- Telemetry cost controls and quotas.
- Load-test and false-positive reports.

---

## 9. Interfaces and contracts

### Subscription API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/telemetry/subscriptions` | Create a scoped metric subscription |
| `GET` | `/api/v1/telemetry/subscriptions/{id}` | Subscription status and quota usage |
| `DELETE` | `/api/v1/telemetry/subscriptions/{id}` | Cancel |
| `GET` | `/api/v1/telemetry/stream?subscription_id=...` | SSE stream |
| `GET` | `/api/v1/telemetry/catalog` | Supported metrics per resource type |

### SSE event

```text
id: 1048577:1712345678
event: telemetry.sample
data: {"subscription_id":"sub_...","resource_id":"arn:...","metric":"CPUUtilization","unit":"Percent","points":[[1712345670000,42.1]],"resolution":60}
```

### Findings API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/findings` | Filter by severity, status, account, region, rule |
| `GET` | `/api/v1/findings/{id}` | Detail with evidence and remediation |
| `PATCH` | `/api/v1/findings/{id}` | Acknowledge, assign, resolve, risk-accept, suppress |
| `POST` | `/api/v1/findings/{id}/remediation` | Create action intent via Phase 6 |
| `GET` | `/api/v1/security/summary` | Counts and trends |
| `POST` | `/api/v1/security/scan` | Trigger a scoped rescan |

### Attack-path request

```json
{
  "source": "internet",
  "target_types": ["AWS::S3::Bucket", "AWS::RDS::DBInstance"],
  "max_depth": 8,
  "limit": 25,
  "accounts": ["123456789012"],
  "regions": ["us-east-1"]
}
```

Response includes `paths[]`, each with ordered `hops`, `severity`, `score`, and `evidence`.

---

## 10. Data and schema changes

New PostgreSQL tables:

- `findings` — rule_id, rule_version, resource_id, severity, status, evidence, first_seen, last_seen, resolved_at, assignee.
- `finding_events` — status changes, comments, suppressions, risk acceptance.
- `finding_suppressions` — owner, reason, expiry, scope.
- `security_rule_versions` — rule ID, version, definition hash, changelog, enabled.
- `telemetry_subscriptions` (if server-side state is needed beyond Redis).
- `telemetry_usage` — tenant, metric requests, period, estimated cost.
- `attack_path_cache` — query hash, graph version, result URI, expires_at.

New graph structures:

- `:Internet` sentinel node per account/region (or global per tenant) for public exposure.
- `CAN_ACCESS` edges from roles/policies to resources with `actions`, `confidence`, `evidence`.
- `EXPOSES` edges from security groups to `:Internet` with port/protocol/CIDR properties.
- Finding nodes? Prefer Postgres for findings and link by `resource_id`; do not duplicate mutable finding state in Neo4j.

Redis structures:

- `telemetry:sub:{tenant}:{subscription}`.
- `telemetry:cache:{tenant}:{account}:{region}:{metric}:{resource}:{resolution}`.
- `telemetry:anomaly:{tenant}:{resource}:{metric}`.
- `telemetry:quota:{tenant}:{date}`.

---

## 11. Exit gate / acceptance criteria

- [ ] Metrics for visible resources appear within 5 seconds of subscription.
- [ ] 500 visible resources × 3 metrics stream without UI jank or excessive CloudWatch calls.
- [ ] Metrics pause when the tab is hidden and resume on focus.
- [ ] Per-tenant telemetry budget is enforced; degradation is visible.
- [ ] All 20 rules have fixture tests and a documented false-positive rate.
- [ ] False-positive rate on the curated corpus is < 5% for high/critical rules.
- [ ] Findings deduplicate, reopen on evidence change, and honor suppression expiry.
- [ ] Attack paths render for internet→EC2→role→S3 and internet→ALB→target→role→data fixtures.
- [ ] Path queries respect depth/time limits and return explanations.
- [ ] Security overlay highlights exposed edges and critical nodes; color is not the only encoding.
- [ ] Remediation handoff creates a valid Phase 6 action request with prefilled parameters.
- [ ] Security Hub/GuardDuty ingestion (if enabled) does not create duplicates.
- [ ] Telemetry and findings APIs pass tenant isolation tests.
- [ ] CloudWatch API cost per tenant is within the approved budget at target viewport sizes.
- [ ] Security review signs off on rule severity and evidence quality.

---

## 12. Test and validation plan

| Layer | Tests |
|---|---|
| Unit | Metric batching, caching, downsampling, anomaly math, rule evaluators |
| Rule correctness | Fixture graphs for each rule; positive/negative cases; false-positive corpus |
| Integration | CloudWatch in sandbox accounts; SSE gateway; Redis pub/sub; findings lifecycle |
| Attack paths | Golden fixture organization; expected paths and rankings; performance |
| UI | Sparklines, overlays, filters, path mode, accessibility |
| Load | 500 resources × 3 metrics; 1k SSE clients; 20 concurrent tenants |
| Cost | Compare estimated vs actual CloudWatch metric charges for a test window |
| Security | Tenant isolation, permission boundaries, evidence redaction |

**False-positive corpus:** Build 100+ real-world configurations (public ALBs, bastion hosts, intentionally public buckets in sandbox) and label expected findings. Review quarterly.

---

## 13. Risks and mitigations

| Risk | Mitigation |
|---|---|
| CloudWatch API cost spikes | Viewport-only, batching, caching, quotas, 5m fallback, cost alarms |
| Too many low-value findings | Curated 20 rules, severity review, suppression, false-positive corpus |
| Attack-path queries are expensive | Bounded depth, allowlists, path cache, node/edge caps, async generation for large scopes |
| IAM effective-access modeling is hard | Start with high-value action allowlist; conservative confidence; explain limitations |
| Metric streaming overwhelms the browser | Sample, LOD, sparkline-only, pause hidden, cap visible metrics |
| SSE scaling and proxy timeouts | Keepalive, HTTP/2, reconnect, Redis fanout, connection limits |
| Security findings create alert fatigue | Grouping, dedupe, ownership, risk acceptance, trend dashboards |
| Remediation creates unsafe actions | Reuse Phase 6 guardrails; never auto-execute from a finding |

---

## 14. Metrics

- Metric sample latency p50/p95.
- CloudWatch metrics requested per tenant per day and estimated cost.
- Cache hit rate.
- SSE connection count, disconnect rate, reconnect success.
- Findings open/closed by severity.
- Mean time to acknowledge/resolve.
- Suppression and risk-acceptance counts.
- False-positive rate per rule.
- Attack-path query latency and cache hit rate.
- Remediation conversion rate (findings → actions).

---

## 15. Handoff to Phase 8 and Phase 9

Phase 8 can assume:

- Overlay framework for cost heatmaps and badges.
- Findings and attack-path visual patterns.
- Telemetry quota and cost-accounting patterns.

Phase 9 can assume:

- Security rule and finding lifecycle for compliance evidence.
- Metric and SSE load profiles.
- Attack-path queries for pen-test and blast-radius analysis.
