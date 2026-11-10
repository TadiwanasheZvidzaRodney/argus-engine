# Phase 8 — Cost Intelligence & 3D Macro View

> **Release:** R3 · **Duration:** 4–5 weeks · **Depends on:** Phase 5, Phase 7 · **Owner:** Backend + Frontend + Data  
> **Entry criteria:** Overlay framework and findings/action handoff stable; Cost Explorer permissions validated; cost allocation tags agreed with pilot tenants.

---

## 1. Objective

Add the financial dimension to the topology and an optional three-dimensional macro view for executives and platform teams. At the end of this phase, users can see where spend concentrates, which resources are likely wasting money, and how accounts and regions relate at a glance — with honest confidence labels on estimated data.

---

## 2. Architecture mapping

| Architecture component | Phase 8 contribution |
|---|---|
| React Flow + Three.js/R3F | 3D account/region macro view, selection sync, LOD |
| Resource Graph Aggregator | Cost rollups by account/region/service/tag; resource estimates |
| PostgreSQL state | Cost snapshots, allocation mappings, recommendations, budgets |
| Phase 6 action engine | Optimization remediation handoff |
| Phase 7 overlay framework | Cost heatmap and badges |

---

## 3. Scope

### In scope

- Cost Explorer ingestion for daily cost by service, account, and activated tags.
- 12-month historical backfill.
- Cost allocation and rollup APIs.
- Estimated per-resource cost with confidence levels.
- Cost overlay on the canvas: badges, heatmap, top spenders, trends.
- Optimization rules with savings estimates and remediation handoff.
- Budget thresholds and alerts (simple, not full AWS Budgets parity).
- Optional 3D macro view with account/region clusters.
- Feature flags and 2D fallback.

### Out of scope

- Exact per-resource cost without customer CUR/Athena (documented limitation; CUR path is a later enhancement).
- Invoice reconciliation, billing, chargeback workflows, or showback reports.
- Reserved Instance/Savings Plan purchase recommendations.
- Multi-currency conversion beyond AWS-reported currency.
- Full 3D editing or 3D-only workflows.
- Real-time cost updates (AWS cost data is daily).

---

## 4. Cost data model and limitations

### Data sources

| Source | Granularity | Use |
|---|---|---|
| Cost Explorer `GetCostAndUsage` | Daily/monthly by service/account/tag | Primary v1 source |
| Cost Explorer `GetCostForecast` | Forecast | Trend and budget projection |
| Cost Explorer `GetDimensionValues` | Dimension discovery | Account/service/tag catalogs |
| CUR + Athena (optional later) | Line-item/resource-level | Exact resource attribution |

### Important limitation

AWS Cost Explorer does not reliably attribute cost to individual resources. Phase 8 therefore provides:

- **Exact** cost at account, service, and activated-tag levels.
- **Estimated** per-resource cost using account/service/tag allocation and usage heuristics.
- **Confidence** labels: `exact`, `allocated`, `estimated`, `unknown`.
- **Untagged/unallocated** bucket so totals still reconcile.

Never present an estimate as exact. The UI must show the method and confidence in the inspector.

### Allocation strategy

1. Start with account + service + usage type totals.
2. Allocate shared service cost by tag where possible.
3. Allocate remaining cost by resource count/usage heuristics within the service.
4. Keep an `unallocated` remainder; require `sum(allocated) + unallocated = total`.
5. Reconcile monthly against Cost Explorer totals and alert on variance > 2%.

---

## 5. Optimization rules

| Rule | Signal | Savings estimate | Risk |
|---|---|---|---|
| `ec2-idle` | CPU p95 < 5% over 14 days | Instance + EBS cost | Medium |
| `ebs-unattached` | Volume state `available` > 7 days | Volume GB-month | Low |
| `snapshot-stale` | Snapshot older than retention policy | Snapshot GB-month | Low |
| `rds-idle` | Low connections/CPU over 14 days | Instance + storage | Medium |
| `ec2-oversized` | CPU/memory low relative to family baseline | Rightsize delta | Medium |
| `graviton-candidate` | Compatible instance family, low risk | Family price delta | Medium |
| `s3-no-lifecycle` | Growing bucket without lifecycle policy | Storage class delta | Low |
| `idle-load-balancer` | Zero requests over 14 days | ALB/NLB base cost | Low |
| `unused-elastic-ip` | Unassociated EIP | EIP hourly cost | Low |

Each recommendation stores evidence, confidence, estimated monthly savings, and a link to a Phase 6 action where one exists.

---

## 6. 3D macro view

### Concept

- Each **account** is a cluster; **regions** orbit or stack within it.
- **VPCs** are grouped volumes; resource density is represented by instanced points or columns.
- Color encodes cost, risk, or health depending on the active layer.
- Clicking a cluster drills into the 2D canvas at the corresponding scope.
- Selection in 2D highlights the same entity in 3D and vice versa.

### Technical approach

- React Three Fiber + drei.
- Instanced meshes for resource points; no individual React components per resource.
- Level of detail: clusters at distance, points at mid-range, labels only for selected/hovered.
- Raycasting for picking with a low-poly proxy layer.
- Web worker for layout/aggregation; main thread only renders.
- Cap rendered instances (e.g., 10k points) and aggregate beyond that.
- Feature flag `canvas.3d`; default off.
- 2D canvas and table view remain the primary accessible interfaces.

### Performance budgets

| Metric | Target |
|---|---|
| Initial 3D scene (10k points) | < 3s on mid-tier GPU |
| Frame rate | ≥ 30fps during orbit |
| Selection response | < 100ms |
| Memory | < 400MB |
| Fallback | Automatic to 2D if WebGL unavailable or frame rate < 20fps for 5s |

---

## 7. Workstreams and tasks

### WS-COST-A — Ingestion and allocation

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P8-01 | Cost Explorer adapter | `GetCostAndUsage`, `GetCostForecast`, pagination, retries, throttling | L | Backend |
| P8-02 | Daily ingestion job | Per-account/region daily sync, idempotency, backfill 12 months | L | Backend |
| P8-03 | Cost schema | Daily aggregates by account/service/tag/usage type; currency; period | L | Data |
| P8-04 | Tag activation checks | Detect which cost allocation tags are active; guide customer | M | Backend |
| P8-05 | Allocation engine | Account/service/tag allocation; unallocated bucket; confidence | L | Data |
| P8-06 | Resource cost estimator | Heuristics per service; confidence labels; explain method | L | Data |
| P8-07 | Reconciliation | Compare allocated + unallocated to totals; variance alerts | M | Data |
| P8-08 | Cost API | Rollups, trends, top-N, resource cost, budgets | L | Backend |
| P8-09 | Cost freshness metadata | As-of timestamp, source, lag indicator | S | Backend |

### WS-COST-B — Cost UI and recommendations

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P8-10 | Cost overlay | Node badges, heatmap, legend, layer toggle | L | Frontend |
| P8-11 | Cost inspector tab | Resource estimate, method, confidence, trend | M | Frontend |
| P8-12 | Cost dashboard | Account/region/service rollups, top spenders, trend | L | Frontend |
| P8-13 | Budget settings | Threshold, scope, notification channel | M | Backend + Frontend |
| P8-14 | Budget alerts | Daily evaluation, notification, audit | M | Backend |
| P8-15 | Optimization rule engine | Rule evaluation over graph + cost + metrics | L | Backend + Data |
| P8-16 | Recommendations API/UI | List, detail, evidence, savings, confidence | L | Backend + Frontend |
| P8-17 | Remediation handoff | Create Phase 6 action from recommendation | M | Backend + Frontend |
| P8-18 | Cost anomaly flags | Day-over-day and forecast deviation | M | Data |

### WS-COST-C — 3D macro view

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P8-19 | R3F scene scaffold | Scene, camera, controls, lighting, performance monitor | L | Frontend |
| P8-20 | Instanced resource points | Account/region/VPC aggregation, up to 10k points | L | Frontend |
| P8-21 | LOD and labels | Cluster → point → label transitions; hover/selection labels | L | Frontend |
| P8-22 | Picking and drill-down | Raycast selection; navigate to 2D scope | M | Frontend |
| P8-23 | 2D/3D selection sync | Shared selection state and URL scope | M | Frontend |
| P8-24 | Layer coloring | Cost/risk/health color modes and legend | M | Frontend |
| P8-25 | Performance and fallback | Frame monitor, WebGL detection, automatic 2D fallback | M | Frontend |
| P8-26 | Accessibility fallback | 2D/table equivalent, keyboard path, reduced motion | M | Frontend |

### WS-COST-D — Testing and docs

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P8-27 | Cost accuracy tests | Compare against known bills; variance < 2% for rollups | L | QA + Data |
| P8-28 | Recommendation tests | Fixture resources; expected savings and confidence | M | QA |
| P8-29 | 3D performance tests | 10k points, orbit, selection, memory | M | QA + Frontend |
| P8-30 | Cost docs | Data sources, allocation method, confidence, limitations | M | Product + Data |
| P8-31 | Customer onboarding guide | Enabling cost allocation tags, permissions, expected latency | M | Product |

---

## 8. Deliverables

- Cost Explorer ingestion with 12-month backfill and daily refresh.
- Cost schema, allocation engine, and resource cost estimator with confidence labels.
- Cost APIs for rollups, trends, top-N, resource cost, and budgets.
- Cost overlay, inspector tab, and cost dashboard.
- Budget thresholds and alerts.
- Nine optimization rules with evidence and savings estimates.
- Remediation handoff into Phase 6.
- Optional 3D macro view with LOD, picking, selection sync, and 2D fallback.
- Cost accuracy and 3D performance reports.
- Documentation of data sources and limitations.

---

## 9. Interfaces and contracts

### Cost endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/cost/summary` | Totals by period with as-of timestamp |
| `GET` | `/api/v1/cost/breakdown` | Group by account/region/service/tag |
| `GET` | `/api/v1/cost/resources/{resourceKey}` | Estimated resource cost and confidence |
| `GET` | `/api/v1/cost/trend` | Daily/monthly trend and forecast |
| `GET` | `/api/v1/cost/top` | Top spenders by scope |
| `GET` | `/api/v1/cost/recommendations` | Optimization recommendations |
| `POST` | `/api/v1/cost/recommendations/{id}/remediate` | Create Phase 6 action |
| `GET` | `/api/v1/cost/budgets` | Budgets and status |
| `PUT` | `/api/v1/cost/budgets/{id}` | Create/update budget |

### Cost summary response

```json
{
  "period": { "start": "2026-10-01", "end": "2026-11-01" },
  "currency": "USD",
  "total": 184230.42,
  "allocated": 161920.10,
  "unallocated": 22310.32,
  "as_of": "2026-11-09T06:00:00Z",
  "source_lag_hours": 18,
  "groups": [
    { "dimension": "account", "value": "123456789012", "amount": 84210.22 },
    { "dimension": "service", "value": "Amazon EC2", "amount": 51200.00 }
  ]
}
```

### Recommendation response

```json
{
  "id": "rec_...",
  "rule": "ec2-idle",
  "resource_id": "arn:aws:ec2:...",
  "confidence": "high",
  "evidence": { "cpu_p95_14d": 1.8, "period_days": 14 },
  "estimated_monthly_savings": 142.4,
  "currency": "USD",
  "remediation": { "action_type": "ec2.stop", "requires_approval": true }
}
```

---

## 10. Data and schema changes

New PostgreSQL tables:

- `cost_daily` — tenant, account, service, usage_type, tag_key, tag_value, amount, currency, period.
- `cost_resource_estimates` — resource_id, period, amount, confidence, method, computed_at.
- `cost_reconciliation` — period, total, allocated, unallocated, variance, status.
- `cost_budgets` — scope, threshold, period, notification channel, enabled.
- `cost_recommendations` — rule, resource_id, evidence, savings, confidence, status.
- `cost_sync_jobs` — account, period, status, error.

New S3 prefixes:

- `s3://argus-cost/tenant=.../account=.../year=.../month=.../cost.parquet`
- Raw Cost Explorer responses for audit/debug with 90-day retention.

Optional later:

- CUR bucket registration + Athena workgroup for exact resource-level cost.

---

## 11. Exit gate / acceptance criteria

- [ ] Cost data for a sandbox account is ingested and visible within 24 hours of AWS publishing it.
- [ ] 12-month backfill completes without gaps; periods and currency are correct.
- [ ] Account/service/tag rollups reconcile to Cost Explorer totals within 2%.
- [ ] Every resource cost shows a confidence label and method explanation.
- [ ] Cost overlay renders on the canvas with a clear legend and as-of timestamp.
- [ ] Top spenders and trends are correct for the sandbox fixture.
- [ ] Budget thresholds trigger notifications and audit events.
- [ ] Nine optimization rules produce evidence-backed recommendations on fixture data.
- [ ] Remediation handoff creates a valid Phase 6 action.
- [ ] 3D view renders 10k points at ≥ 30fps on a mid-tier GPU and falls back to 2D when needed.
- [ ] 2D/3D selection sync works.
- [ ] 3D is feature-flagged off by default and does not block the 2D experience.
- [ ] Cost APIs pass tenant isolation tests.
- [ ] Documentation clearly states the per-resource cost limitation.

---

## 12. Test and validation plan

| Layer | Tests |
|---|---|
| Unit | Allocation math, confidence rules, savings estimates, budget evaluation |
| Integration | Cost Explorer sandbox; daily job; tag activation; backfill |
| Accuracy | Reconcile rollups to Cost Explorer; known-bill fixture; variance alerts |
| UI | Overlay, inspector, dashboard, budgets, recommendation flow |
| 3D | 10k points, orbit, picking, LOD, memory, fallback |
| Security | Tenant isolation, cost data access, budget authorization |
| Resilience | Cost Explorer throttling, missing tags, partial periods, currency changes |

**Data caveat:** Test accounts must have predictable spend or use a synthetic Cost Explorer fixture. Do not assert exact dollar values from live accounts in CI; assert reconciliation and allocation invariants instead.

---

## 13. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Per-resource cost is inaccurate | Confidence labels, method disclosure, unallocated bucket, CUR path later |
| Cost Explorer API cost | Cache daily, minimize group-bys, per-tenant quotas, as-of metadata |
| Cost data latency confuses users | Show as-of/lag, explain AWS publishing delay |
| Allocation double-counting | Invariant tests: allocated + unallocated = total; monthly reconciliation |
| Recommendation false positives | Evidence, confidence, minimum observation window, human approval |
| 3D view distracts from core product | Feature flag off by default, strict performance budget, 2D fallback |
| WebGL compatibility | Detect and fall back; no 3D-only workflows |
| Tag activation friction | Onboarding guide and detection of inactive tags |

---

## 14. Metrics

- Cost ingestion freshness and success rate.
- Reconciliation variance per tenant/month.
- Percentage of cost allocated vs unallocated.
- Cost overlay adoption (sessions using the layer).
- Recommendations viewed, accepted, remediated.
- Estimated savings accepted vs realized (post-action tracking).
- 3D view usage, frame rate, fallback rate.
- Cost Explorer requests and estimated API spend per tenant.

---

## 15. Handoff to Phase 9

Phase 9 can assume:

- Cost data for unit economics and per-tenant metering.
- Cost overlay and recommendations for launch demos.
- 3D feature flag and performance telemetry.
- Known cost drivers for capacity and pricing models.
