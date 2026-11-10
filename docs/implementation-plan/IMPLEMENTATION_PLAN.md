# Argus Engine — Implementation Plan (Executive Summary)

> **Status:** Draft for review  
> **Detailed plan:** [`docs/implementation-plan/README.md`](docs/implementation-plan/README.md)  
> **Source architecture:** [`ARGUS_ENGINE_HIGH_LEVEL_SYSTEM_ARCHITECTURE.md`](ARGUS_ENGINE_HIGH_LEVEL_SYSTEM_ARCHITECTURE.md)  
> **Last updated:** 2026-11-10

Argus Engine is a multi-tenant AWS management console that discovers infrastructure across accounts and regions, visualizes it as a live graph, and enables reviewed mutations through an MCP-based action engine. This document summarizes the phased delivery plan; the linked documents contain the tasks, contracts, exit gates, test strategy, and operational model.

---

## Delivery at a glance

| Phase | Name | Release | Duration | Primary outcome |
|---|---|---|---|---|
| **0** | Foundations, Decisions & Delivery Spine | R0 | 3–4 weeks | Repo, environments, CI/CD, ADRs, threat model, conventions |
| **1** | Identity, Tenancy & AWS Account Onboarding | R0 | 5–6 weeks | SSO, RBAC, cross-account roles, STS broker, audit |
| **2** | Discovery Pipeline & Resource Graph | R1 | 7–8 weeks | AWS inventory and relationships in Neo4j |
| **3** | Real-Time Event Synchronization | R2 | 5–6 weeks | Sub-minute graph freshness and live deltas |
| **4** | Graph Query API & Aggregation Layer | R1 | 4–5 weeks | Cached, tenant-safe topology API |
| **5** | Visual Canvas Frontend | R1/R2 | 7–8 weeks | Interactive nested topology canvas |
| **6** | MCP Action Engine & Safe Mutations | R2 | 9–10 weeks | Plan/diff/approve/apply/verify mutations |
| **7** | Live Telemetry & Security Intelligence | R3 | 5–6 weeks | Metrics overlays, findings, attack paths |
| **8** | Cost Intelligence & 3D Macro View | R3 | 4–5 weeks | Cost overlays, recommendations, 3D view |
| **9** | Hardening, Scale & GA | R4 | 7–8 weeks | Scale, DR, pen test, operability, GA |

**Recommended sequence:** P0 → P1 → P2 → (P3 ∥ P4) → P5 → P6 → P7 → P8 → P9. P6/P7/P8 are sequenced to fit the 8–10 FTE team; they can run in parallel only with a materially larger team.  
**Critical path:** P0 → P1 → P2 → P4 → P5 → P6 → P7 → P8 → P9 (~60 weeks plus contingency).

### Releases

| Release | Phases | What customers can do |
|---|---|---|
| **R0** | P0, P1 | Sign in, invite users, connect AWS accounts, pass isolation tests |
| **R1** | P2, P4, P5 | Explore a real multi-account topology with search, nesting, and inspector |
| **R2** | P3, P6 | See changes in seconds; perform six golden mutations with approval and rollback |
| **R3** | P7, P8 | View metrics, security findings, attack paths, cost, and 3D macro view |
| **R4** | P9 | Production SLA, DR, security sign-off, design partners, GA |

---

## Baseline stack

| Layer | Default |
|---|---|
| Frontend | Next.js + React 19 + TypeScript, React Flow, ELK.js, TanStack Query, Zustand |
| Backend | FastAPI + Python 3.12, Pydantic v2, SQLAlchemy, Alembic |
| Graph | Neo4j 5 (AuraDB production, Docker local) |
| Relational | Aurora PostgreSQL 16 with RLS |
| Cache / fanout | ElastiCache Redis 7 |
| Events | AWS Config + EventBridge + SQS + CloudTrail + reconciliation |
| Auth | OIDC (Cognito or Keycloak dev) + Next.js BFF + RBAC/ABAC |
| Cross-account | STS AssumeRole with external ID, session tags, scope-down |
| MCP / LLM | Python MCP host, pinned AWS MCP servers, sandboxed ECS tasks, Bedrock |
| Platform IaC | Terraform |
| Customer mutations | AWS CDK + CloudFormation change sets |
| Compute | ECS Fargate + ALB + CloudFront + WAF |
| Observability | OpenTelemetry, CloudWatch/Grafana, Sentry, PagerDuty |

All choices are recorded as ADRs in [`docs/implementation-plan/cross-cutting/decision-log.md`](docs/implementation-plan/cross-cutting/decision-log.md) and must be ratified in Phase 0.

---

## Non-negotiable safety rules

1. **Read before write.** No mutation work starts before the read-only topology is trustworthy.
2. **No write without an approved plan.** Approval binds to an immutable plan hash.
3. **No raw model output executes.** LLMs parse intent and explain; deterministic templates generate plans.
4. **No permanent AWS credentials.** Short-lived STS sessions with external IDs and scope-down policies only.
5. **Tenant isolation is tested, not assumed.** Cross-tenant probes run on every PR and before every release.
6. **Events for freshness, reconciliation for truth.** Lost or reordered events are repaired by scheduled sync.
7. **Every action is auditable and reversible.** Verification and rollback are part of the action state machine.
8. **Kill switch always available.** Writes can be disabled globally or per tenant within one minute.

---

## Top risks and mitigations

| Risk | Mitigation |
|---|---|
| Cross-tenant data leakage | RLS, tenant-guarded graph queries, prefixed caches/queues/storage, isolation suite, external pen test |
| Unsafe mutation or prompt injection | Deterministic plans, policy gate, human approval, sandbox, verification, rollback, red team |
| AWS throttling at scale | Token buckets, adaptive retry, sharding, Resource Explorer, off-peak sync |
| Event loss/duplication/ordering | Idempotency, version guards, DLQ/replay, reconciliation, chaos tests |
| Neo4j performance/cost | Bounded queries, indexes, batching, read replicas, dedicated DB option |
| Onboarding friction | One-click template, StackSet path, validation, clear errors, support runbooks |
| Timeline/scope creep | Phase gates, change control, feature freeze, contingency plan |

Full register: [`docs/implementation-plan/cross-cutting/risk-register.md`](docs/implementation-plan/cross-cutting/risk-register.md).

---

## What exists after this plan

- An executable phased backlog with task IDs, owners, sizes, dependencies, and measurable exit gates.
- A target domain model for tenancy, PostgreSQL, Neo4j, events, IDs, and retention.
- A security architecture covering trust boundaries, STS, tenant isolation, MCP sandboxing, LLM safety, and audit.
- A test strategy spanning contracts, AWS sandboxes, performance, security, chaos, and release gates.
- An observability and SRE model with SLOs, dashboards, alerts, runbooks, capacity, and on-call.
- A delivery roadmap with team shape, timeline, milestones, dependencies, cost drivers, and governance.
- A decision log (ADR-001–ADR-012) and an open-decisions list for Phase 0.

---

## Next two weeks

1. Ratify ADR-001–ADR-012 and assign decision owners.
2. Stand up the monorepo, local Docker stack, and CI skeleton.
3. Provision AWS dev/staging accounts and baseline SCPs.
4. Run the threat-model workshop and publish the tenant-isolation checklist.
5. Publish API, event, and error conventions.
6. Run four de-risking spikes: STS onboarding, Neo4j 100k ingest, MCP CDK diff, React Flow 5k nodes.
7. Convert phase plans into epics and the first two sprints.
8. Schedule the Phase 0 gate review.
