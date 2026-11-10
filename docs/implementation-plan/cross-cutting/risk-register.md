# Cross-Cutting — Risk Register

> **Applies to:** Program-wide  
> **Review cadence:** Monthly, plus at every phase gate  
> **Scoring:** Likelihood (1–5) × Impact (1–5); 15–25 critical, 8–14 high, 4–7 medium, 1–3 low

---

## 1. Scoring guide

| Score | Likelihood | Impact |
|---|---|---|
| 5 | Almost certain | Existential: data breach, unsafe write, company-threatening |
| 4 | Likely | Major: launch delay, customer loss, significant cost |
| 3 | Possible | Moderate: degraded feature, rework, budget overrun |
| 2 | Unlikely | Minor: localized issue, workaround exists |
| 1 | Rare | Negligible |

A risk with score ≥ 15 requires an owner, a mitigation plan, and a steering-committee review. Score ≥ 20 requires an explicit go/no-go decision at the next phase gate.

---

## 2. Register

| ID | Risk | Phase | L | I | Score | Mitigation | Owner | Trigger / early warning |
|---|---|---|---|---|---|---|---|---|
| **R-01** | Cross-tenant data leakage via graph, cache, queue, S3, logs, or MCP session | P1–P9 | 3 | 5 | **15** | Tenant guards, RLS, prefixed keys, isolation suite, external pen test, canary tenants | Security | Any isolation test failure; anomalous cross-tenant query |
| **R-02** | Unsafe mutation or prompt injection causes unintended AWS change | P6–P9 | 3 | 5 | **15** | Deterministic plans, policy gate, human approval, sandbox, verification, rollback, red team | Security | Guardrail block spike; prompt-injection success in test |
| **R-03** | AWS API throttling or quota limits break discovery at scale | P2–P3 | 4 | 3 | **12** | Token buckets, adaptive retry, sharding, off-peak sync, progressive coverage | Backend | Throttle rate > 1%; sync duration > target |
| **R-04** | Event loss, duplication, or ordering corrupts graph state | P3–P9 | 3 | 4 | **12** | Idempotency, version guards, DLQ/replay, reconciliation, chaos tests | Backend | Event lag spike; drift > 1%; DLQ growth |
| **R-05** | Neo4j performance/cost degrades at 100k+ resources per tenant | P2–P9 | 3 | 4 | **12** | Bounded queries, batching, indexes, read replicas, dedicated DB option, benchmark gates | Data | Query p95 > 1s; page cache hit < 95% |
| **R-06** | Canvas performance collapses at 5k+ nodes | P5–P9 | 3 | 3 | **9** | LOD, culling, clustering, worker layout, caps, WebGL evaluation | Frontend | Frame rate < 30fps; memory > 500MB |
| **R-07** | MCP server ecosystem is immature or breaks compatibility | P6–P9 | 3 | 3 | **9** | Pin versions, signed images, adapter layer, direct SDK fallback, contract tests | Backend | Tool schema change; server CVE; timeout spike |
| **R-08** | Customer onboarding friction (trust policy, StackSets, permissions) blocks adoption | P1–P9 | 4 | 3 | **12** | One-click template, validation, error guidance, StackSet path, support runbook | Product | Onboarding success < 90%; support tickets |
| **R-09** | CloudWatch/Cost Explorer API costs exceed unit economics | P7–P9 | 3 | 3 | **9** | Viewport-only, batching, caching, quotas, degradation, cost alarms | Platform | Cost per tenant > budget; API request spike |
| **R-10** | Timeline/scope creep delays GA | P0–P9 | 4 | 3 | **12** | Phase gates, feature freeze, change control, contingency plan | PM | Any gate slip > 2 weeks; scope additions |
| **R-11** | Nested layout/ELK complexity produces unreadable or unstable graphs | P5 | 3 | 3 | **9** | Deterministic layout, incremental updates, manual positions, usability tests | Frontend | Layout instability reports; task failure |
| **R-12** | IAM effective-access modeling is inaccurate, causing false security conclusions | P7–P9 | 3 | 3 | **9** | High-value action allowlist, conservative confidence, evidence, explanations | Security | False-positive/negative reports |
| **R-13** | Cost attribution is inaccurate or misleading | P8–P9 | 4 | 2 | **8** | Confidence labels, method disclosure, unallocated bucket, reconciliation, CUR path | Data | Variance > 2%; customer disputes |
| **R-14** | Compliance/SOC 2 scope expands beyond readiness | P9 | 3 | 3 | **9** | Readiness only, gap plan, auditor scoping, legal review | Security | Certification demanded pre-GA |
| **R-15** | Vendor lock-in (Neo4j, AWS MCP, Bedrock, React Flow) | P0–P9 | 2 | 3 | **6** | Abstractions, export formats, ADRs, license review, exit plans | Tech Lead | Price change; license change; outage |
| **R-16** | Key-person dependency on graph/action engine | P2–P9 | 3 | 3 | **9** | Pairing, ADRs, runbooks, code ownership rotation | Tech Lead | Single reviewer on critical module |
| **R-17** | DR failover fails or exceeds RTO/RPO | P9 | 2 | 5 | **10** | Early drills, automated restore tests, quarterly exercises, runbooks | Platform | Failed drill; backup restore error |
| **R-18** | Security finding fatigue reduces trust | P7–P9 | 4 | 2 | **8** | Curated rules, false-positive corpus, suppression, grouping, trend metrics | Security | Suppression rate > 20%; low click-through |
| **R-19** | Cross-region EventBridge complexity causes gaps | P3 | 3 | 3 | **9** | Regional ingress buses, forwarder, supported-region matrix, spike early | Platform | Missing events in a region; lag |
| **R-20** | Token/credential leakage through logs, URLs, or browser storage | P1–P9 | 2 | 5 | **10** | HttpOnly cookies, one-time WS tickets, redaction, secret scanning, CSP | Security | Secret in logs; token in URL; CSP violation |
| **R-21** | Tenant offboarding leaves data behind | P9 | 2 | 4 | **8** | Deletion workflow, checksums, certificate, backup expiry, audit | Backend | Failed deletion audit; customer request |
| **R-22** | Design-partner adoption is slower than expected | P9 | 3 | 3 | **9** | Early recruitment, onboarding runbook, success criteria, feedback loop | Product | Activation < target; low weekly usage |
| **R-23** | Event storm or noisy tenant starves others | P3–P9 | 3 | 3 | **9** | Per-tenant quotas, weighted queues, coalescing, backpressure, fair scheduling | Platform | Queue age imbalance; one tenant dominates |
| **R-24** | IAM/SCP changes in customer accounts break Argus roles | P1–P9 | 3 | 3 | **9** | Health checks, drift detection, alerts, reconnect flow, customer comms | Backend | Role assumption failure spike |

---

## 3. Top five risks — detailed treatment

### R-01 — Cross-tenant data leakage

**Why it matters:** A single leak can end the business and violate customer trust.

**Prevention:**

- Tenant ID in every JWT, request context, database row, graph node, cache key, queue message, S3 prefix, and MCP session.
- RLS in Postgres; query builder enforcement in Neo4j; no raw query escape hatch.
- Isolation test suite runs on every PR and before every release.
- Canary tenants with distinctive data detect accidental cross-contamination.
- External pen test includes tenant isolation.

**Detection:**

- Alerts on queries lacking tenant predicates.
- Anomaly detection for cross-tenant resource IDs in requests.
- Audit review of admin/impersonation access.

**Response:**

- Disable affected endpoint or tenant, preserve evidence, notify security and legal, rotate credentials, patch, re-test, postmortem.

### R-02 — Unsafe mutation / prompt injection

**Why it matters:** Argus writes to production AWS; a bad write can cause an outage or breach.

**Prevention:**

- Deterministic plan generation; LLM never emits raw IAM or executes tools.
- Tool allowlist and schema validation; no write tools in the LLM session.
- Approval workflow with four-eyes and step-up MFA.
- Policy engine and guardrails; protected resources; blast-radius caps.
- Post-execution verification and rollback.
- Red-team prompt-injection exercises.

**Detection:**

- Guardrail block metrics; anomalous plan diffs; unusual approver/requester patterns.
- CloudTrail correlation for writes outside the expected plan.

**Response:**

- Activate kill switch, roll back, preserve evidence, notify affected tenants, security review, update guardrails, re-test.

### R-03 — AWS throttling at scale

**Why it matters:** Initial sync and live events can stall, making the product look broken.

**Prevention:**

- Per-account/region/service token buckets; adaptive retry; jitter.
- Shard by service and region; cap concurrency; prioritize network/identity/compute.
- Resource Explorer for bulk discovery; direct APIs only where needed.
- Off-peak scheduling for large tenants.

**Detection:**

- Throttle rate, retry count, sync duration, shard failure rate.
- AWS Service Quotas dashboards.

**Response:**

- Reduce concurrency, extend sync window, request quota increases, degrade to partial coverage with clear UI.

### R-05 — Neo4j scale and cost

**Why it matters:** Graph queries are the core experience; latency or cost overruns break the product economics.

**Prevention:**

- Bounded queries with depth/result caps; no client Cypher.
- Composite indexes and full-text index; query plan review.
- Batched writes; separate read/write routing later.
- Benchmark at 10k/100k nodes before Phase 4.
- Dedicated database option for large tenants.

**Detection:**

- Query p95, page cache hit rate, transaction retries, heap/GC, storage growth.
- Cost per tenant.

**Response:**

- Add read replica, optimize queries, archive cold subgraphs, move tenant to dedicated DB, renegotiate Aura tier.

### R-08 — Onboarding friction

**Why it matters:** If customers cannot connect accounts quickly, the product never reaches value.

**Prevention:**

- One-click CloudFormation template and StackSet path.
- Preflight validation and clear error messages.
- Least-privilege read role with documented permissions.
- Onboarding wizard with progress and support links.
- Sandbox dry runs and design-partner feedback.

**Detection:**

- Onboarding funnel: launch → role created → validated → first sync.
- Support ticket categorization.
- Time to first topology.

**Response:**

- Fix template/permission gaps, add guided remediation, offer assisted onboarding, update docs.

---

## 4. Risk review process

1. **Monthly review:** owner updates likelihood, impact, score, mitigation status, and trigger.
2. **Phase gate:** top risks reviewed; any score ≥ 15 requires a mitigation demo or plan.
3. **New risks:** anyone can add; Tech Lead triages within 48 hours.
4. **Closed risks:** retained in the register with closure rationale.
5. **Escalation:** score ≥ 20 or any R-01/R-02 trigger goes to the steering committee immediately.

---

## 5. Accepted risks (to be confirmed at gates)

| Risk | Rationale | Expiry |
|---|---|---|
| Shared Neo4j database for MVP | Cost/complexity; mitigated by guardrails and tests | Revisit at P9 or first large tenant |
| Per-resource cost estimates, not exact | Cost Explorer limitation; confidence labels | Revisit when CUR/Athena is prioritized |
| No autonomous remediation | Safety; human approval required | Revisit post-GA with policy guardrails |
| 3D view is optional and may be deferred | Not core to read/act value | Revisit after R3 usage data |
| No multi-cloud | Focus and differentiation | Post-GA roadmap |
| SOC 2 readiness, not certification | Time-to-market; customer demand may change | Revisit at GA |
