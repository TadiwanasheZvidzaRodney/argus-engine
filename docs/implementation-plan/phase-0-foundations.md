# Phase 0 — Foundations, Decisions & Delivery Spine

> **Release:** R0 · **Duration:** 3–4 weeks · **Depends on:** — · **Owner:** Platform/SRE + Tech Lead  
> **Entry criteria:** Architecture document approved; initial team and budget confirmed.

---

## 1. Objective

Create the technical and operational spine that every later phase depends on: ratified architecture decisions, a buildable monorepo, one-command local development, AWS environments with CI/CD, baseline observability, security controls, and shared API/event conventions.

Phase 0 is deliberately short. It is not a prototype phase; it is the point where ambiguous architecture choices become enforceable standards.

---

## 2. Architecture mapping

| Architecture component | Phase 0 contribution |
|---|---|
| Frontend (React/Next.js) | Repo scaffold, routing shell, design system, auth placeholder, test harness |
| Backend API gateway & services | Service skeletons, OpenAPI conventions, error model, health endpoints |
| Data layer | Local Postgres/Neo4j/Redis, migration tooling, backup/restore baseline |
| AWS integration | Dev/staging accounts, OIDC deployment roles, network and KMS baseline |
| Security | Threat model, data classification, secrets management, tenant-isolation checklist |
| Operations | CI/CD, observability pipeline, SLO skeleton, incident process |

---

## 3. Scope

### In scope

- ADR ratification and decision log.
- Monorepo and package boundaries.
- Local development stack and seed data.
- AWS account/environment layout and Terraform foundation.
- CI/CD with security scanning and signed artifacts.
- OpenTelemetry, structured logging, error tracking, initial dashboards.
- API, event, error, and pagination conventions.
- Frontend design-system and test foundations.
- Engineering handbook: definition of done, review, release, incident.

### Out of scope

- Real AWS resource discovery.
- Production authentication and tenant data.
- Canvas graph rendering.
- MCP integration.
- Production-scale performance tuning.
- SOC 2 evidence collection.

---

## 4. Workstreams and tasks

### WS-PLAT — Environments and delivery

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P0-01 | Ratify ADR-001–ADR-012 | Signed decision log with owners and revisit triggers | M | Tech Lead |
| P0-02 | Define environment topology | Dev, staging, production, sandbox accounts; network CIDRs; SCP baseline | M | Platform |
| P0-03 | Monorepo scaffold | `apps/web`, `services/api`, `services/ws`, `services/worker`, `packages/contracts`, `packages/ui`, `infra/terraform`, `docs` | M | Tech Lead |
| P0-04 | Toolchain standardization | pnpm + Turborepo, `uv` + Ruff + mypy + pytest, ESLint/Prettier, pre-commit, conventional commits | M | Platform |
| P0-05 | Local Docker stack | Postgres 16, Neo4j 5, Redis 7, LocalStack (STS/SQS/EventBridge/S3), Keycloak, Mailpit | L | Platform |
| P0-06 | One-command developer workflow | `make dev`, `make test`, `make lint`, `make migrate`, seeded demo tenant | M | Platform |
| P0-07 | Terraform foundation | VPC, subnets, NAT, ECS cluster, ALB, Aurora, ElastiCache, S3, KMS, IAM, CloudFront, Route 53 | L | Platform |
| P0-08 | Remote state and locking | S3 + DynamoDB state backend per environment; state access controls | S | Platform |
| P0-09 | CI pipeline | Lint, typecheck, unit tests, build, SAST, dependency/container/IaC scans, SBOM, signed images | L | Platform |
| P0-10 | CD pipeline | GitHub OIDC to AWS, environment approvals, migrations, canary/rollback hooks | L | Platform |
| P0-11 | Preview environments | Ephemeral namespace or stack per PR for web + API where feasible | M | Platform |
| P0-12 | Backup/restore baseline | Aurora snapshots, Neo4j dump/restore, Redis non-persistent policy, S3 versioning | M | Platform |

### WS-ID — Contracts and security baseline

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P0-13 | System context and container diagrams | C4-level diagrams aligned to the architecture doc | M | Tech Lead |
| P0-14 | Threat model workshop | STRIDE model, trust boundaries, top risks, mitigations | M | Security |
| P0-15 | Data classification and retention draft | Public/internal/confidential/restricted; retention per data type | S | Security |
| P0-16 | Tenant-isolation checklist | Storage, cache, queue, graph, logs, MCP, tests | S | Security + Backend |
| P0-17 | Secrets and encryption baseline | Secrets Manager, KMS keys, envelope encryption, rotation policy | M | Security + Platform |
| P0-18 | IAM baseline | Deployment roles, permission boundaries, break-glass procedure | M | Security |
| P0-19 | API conventions | OpenAPI 3.1, RFC 9457 errors, cursor pagination, idempotency, versioning, auth scopes | M | Backend |
| P0-20 | Event conventions | CloudEvents-compatible envelope, schema registry, versioning, DLQ/replay rules | M | Backend |
| P0-21 | Audit event schema v1 | Actor, tenant, action, resource, before/after hashes, correlation IDs | S | Backend + Security |

### WS-FE — Frontend foundation

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P0-22 | Next.js application scaffold | App Router, TypeScript strict, route groups, error boundaries, loading states | M | Frontend |
| P0-23 | Design system foundation | Tailwind + shadcn/ui, tokens, dark/light themes, typography, icon rules | M | Design + Frontend |
| P0-24 | Component workshop | Storybook, visual regression baseline, accessibility addon | M | Frontend |
| P0-25 | Test harness | Vitest + React Testing Library, Playwright, MSW, axe-core | M | Frontend + QA |
| P0-26 | Auth shell placeholder | Login page, session context, protected route pattern, tenant switcher stub | M | Frontend |

### WS-SPIKE — De-risking spikes

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P0-34 | STS + CloudFormation onboarding spike | Real sandbox account connected; external ID and scope-down verified; template reviewed | M | Backend + Security |
| P0-35 | Neo4j scale spike | 100k nodes/500k edges ingested; 3-hop query benchmark; memory/index notes | M | Data |
| P0-36 | MCP + CDK diff spike | Pinned AWS MCP server runs in a sandbox; one synthetic change produces a change set/diff | M | Backend + Security |
| P0-37 | Canvas scale spike | React Flow nested containers + ELK in worker at 5k nodes; frame-rate findings | M | Frontend |

### WS-OBS — Observability and operations

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P0-27 | OpenTelemetry pipeline | Collector, trace propagation, service resource attributes, sampling policy | M | Platform |
| P0-28 | Structured logging standard | JSON schema, correlation IDs, tenant IDs, redaction rules | S | Platform |
| P0-29 | Error tracking | Sentry projects for web/API/workers with release tagging | S | Platform |
| P0-30 | Initial dashboards | API health, deploy status, queue depth, database health, error rate | M | Platform |
| P0-31 | SLO skeleton | Availability, latency, freshness definitions with placeholder targets | S | Platform + Product |
| P0-32 | Alert routing | PagerDuty/Opsgenie routes, severity levels, escalation policy | S | Platform |
| P0-33 | Engineering handbook | Definition of done, review rules, branching, release, incident, postmortem | M | Tech Lead |

---

## 5. Deliverables

- Ratified ADR set and decision log.
- Architecture diagrams, threat model, data classification, tenant-isolation checklist.
- Working monorepo with API/web/worker skeletons and shared contracts package.
- `make dev` local environment with all dependencies and seeded data.
- Terraform-managed dev/staging environments.
- GitHub Actions CI/CD with scans, SBOM, image signing, and deployment approvals.
- OpenTelemetry traces, structured logs, Sentry, baseline dashboards, and alerts.
- API/event/error/pagination/idempotency conventions.
- Frontend design system, Storybook, Playwright, and accessibility baseline.
- Engineering handbook and phase-gate checklist.

---

## 6. Interfaces and contracts introduced

### API conventions

- Base path: `/api/v1`.
- Auth: `Authorization: Bearer <access_token>` at the edge; browser uses BFF cookies.
- Errors: RFC 9457 `application/problem+json` with `type`, `title`, `status`, `detail`, `instance`, `trace_id`, `errors[]`.
- Pagination: cursor-based (`cursor`, `limit`), opaque cursors, max page size enforced.
- Idempotency: `Idempotency-Key` required for all non-GET requests; stored for 24 hours minimum.
- Versioning: URL major version; additive changes only within a major version.
- Rate limits: per-tenant and per-user; `429` with `Retry-After`.

### Event envelope v1

```json
{
  "id": "evt_01J...",
  "type": "argus.resource.changed.v1",
  "source": "argus.discovery",
  "tenant_id": "tnt_...",
  "account_id": "123456789012",
  "region": "us-east-1",
  "subject": "arn:aws:ec2:us-east-1:123456789012:instance/i-...",
  "time": "2026-11-10T12:00:00Z",
  "idempotency_key": "aws-config:...:v3",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "schema_version": "1.0",
  "data": {}
}
```

### Repository layout

```text
argus-engine/
├── apps/
│   └── web/                     # Next.js App Router
├── services/
│   ├── api/                     # FastAPI read/admin API
│   ├── ws/                      # WebSocket gateway
│   └── worker/                  # Discovery, event, action workers
├── packages/
│   ├── contracts/               # OpenAPI, JSON Schema, generated TS client
│   └── ui/                      # Shared React components
├── infra/
│   └── terraform/               # Environment modules and stacks
├── docs/
│   ├── implementation-plan/
│   └── adr/
└── docker-compose.yml
```

---

## 7. Data and schema changes

- PostgreSQL initialized with migration tooling (Alembic) and an empty baseline.
- Neo4j initialized with migration tooling and a schema-version node.
- Redis configured with no persistence in dev; managed eviction policy in production.
- KMS keys created for: application data, audit archive, secrets, backups.
- S3 buckets created for: audit archive (Object Lock), raw AWS payloads, frontend assets, backups.
- No production tenant data yet.

---

## 8. Exit gate / acceptance criteria

All must be true:

- [ ] ADR-001–ADR-012 ratified; any deviations recorded.
- [ ] Architecture diagrams, threat model, data classification, and tenant-isolation checklist approved.
- [ ] `make dev` brings up the full local stack and passes a smoke test on a clean machine.
- [ ] A hello-world web + API + worker deployment reaches staging through CI/CD with no manual steps.
- [ ] CI blocks merges on lint, type, unit test, SAST, secret, dependency, container, and IaC failures.
- [ ] Container images are signed and SBOMs are retained per build.
- [ ] Traces, logs, and errors from the staging hello-world are visible in dashboards.
- [ ] Baseline SLOs and alert routes exist.
- [ ] API, event, error, idempotency, and pagination conventions are published.
- [ ] Engineering handbook and phase-gate checklist are published.
- [ ] Riskiest integrations have spike results: STS onboarding, Neo4j 100k ingest, MCP CDK diff, React Flow 5k nodes.

---

## 9. Test and validation plan

| Area | Validation |
|---|---|
| Local environment | Clean-machine setup test in CI and by a new engineer |
| CI/CD | Deliberate failing test, secret, vulnerable dependency, and unsigned image are blocked |
| Infrastructure | `terraform plan` in CI; drift detection on staging; policy-as-code checks |
| Security | Threat-model review; gitleaks clean; IAM access review; KMS encryption verified |
| Observability | Trace continuity from web → API → worker; log redaction test |
| Frontend | Storybook build, Playwright smoke, axe accessibility check |
| Contracts | OpenAPI lint, schema validation, generated client compiles |

---

## 10. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Foundation work expands into platform over-engineering | Timebox to 4 weeks; defer non-critical tooling; enforce exit gate |
| Team disagrees on stack late | Ratify ADRs in week 1; record dissent and revisit triggers |
| AWS account provisioning delays | Start Control Tower/account requests on day 1; use sandbox accounts for spikes |
| CI/CD security scanning slows delivery | Parallelize scans; cache dependencies; fail only on defined severities |
| Local stack diverges from AWS | Contract tests against LocalStack plus nightly sandbox tests from Phase 1 onward |

---

## 11. Metrics

- Time from clean clone to running local stack: **< 30 minutes**.
- CI pipeline duration (PR): **< 15 minutes**.
- Deployment frequency to staging: **on every merge**.
- Change failure rate: tracked from day one.
- Percentage of services emitting traces/logs/metrics: **100%**.
- Flaky test rate: **< 2%**.

---

## 12. Handoff to Phase 1

Phase 1 can assume:

- A deployable API/web/worker skeleton with auth middleware hooks.
- Postgres/Neo4j/Redis running locally and in staging.
- Terraform-managed network, database, cache, and secrets.
- CI/CD, observability, and security scanning operational.
- Contracts package ready for OpenAPI and event schemas.
- Agreed tenancy and audit data model direction from the domain-model document.
