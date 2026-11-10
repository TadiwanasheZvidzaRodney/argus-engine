# Cross-Cutting — Testing Strategy

> **Applies to:** Phases 0–9  
> **Purpose:** Define how correctness, safety, performance, and security are proven at every phase, including environments, test types, data, and release gates.

---

## 1. Testing principles

1. **Test the riskiest thing first.** Multi-tenant isolation, write safety, and event correctness get dedicated suites.
2. **Contract-first.** OpenAPI, event schemas, and MCP tool schemas are tested before implementation.
3. **Fast feedback, slow confidence.** Unit and contract tests run on every PR; AWS sandbox and scale tests run nightly or at gates.
4. **Production-like where it matters.** LocalStack/moto for speed, real AWS sandbox accounts for STS, IAM, Config, EventBridge, CloudFormation, CloudWatch, and Cost Explorer.
5. **Every bug becomes a test.** Regressions are added to the suite before the fix ships.
6. **No flaky gates.** Quarantine flaky tests within 24 hours; fix or delete them.
7. **Security tests are release blockers.** Tenant isolation, prompt injection, and authZ failures stop the release.

---

## 2. Test pyramid and ownership

| Layer | Share | Scope | Tools | Runs |
|---|---|---|---|---|
| Unit | ~55% | Pure logic, mappers, validators, policy rules, reducers | pytest, Vitest | Every commit |
| Contract | ~10% | OpenAPI, event schemas, MCP tools, JWT/WS messages | Schemathesis, JSON Schema, Pact-style fixtures | Every PR |
| Integration | ~20% | DB, graph, queue, cache, AWS adapters | Testcontainers, LocalStack, moto, real sandbox | Every PR (fast subset), nightly (full) |
| E2E | ~10% | Critical user journeys | Playwright | Every PR (smoke), nightly (full) |
| Non-functional | ~5% | Performance, load, chaos, security | k6, Locust, custom chaos, ZAP, Semgrep | Nightly, gates |

Ownership: feature teams own unit/integration/E2E for their area; QA owns cross-cutting suites, environments, and release gates; Security owns isolation, authZ, prompt-injection, and pen-test coordination.

---

## 3. Environments

| Environment | Purpose | Data | AWS |
|---|---|---|---|
| **Local** | Fast development | Seeded synthetic | LocalStack/moto |
| **Ephemeral PR** | Preview and smoke | Seeded synthetic | LocalStack or shared sandbox |
| **Integration** | Cross-service tests | Synthetic multi-tenant | Real sandbox accounts |
| **Staging** | Release candidate, scale, DR | Anonymized/synthetic | Real sandbox + staging accounts |
| **Production** | Customer traffic | Real | Customer accounts |

Rules:

- No production data in lower environments.
- Sandbox AWS accounts are dedicated per test suite where possible.
- Credentials for tests are short-lived and scoped; no personal keys.
- Test tenants are labeled and cleaned up automatically.
- Cost-incurring tests (Cost Explorer, CloudWatch) have budgets and schedules.

---

## 4. Test suites by domain

### 4.1 Identity and tenancy

- AuthZ matrix: every role × endpoint × scope.
- JWT validation: signature, issuer, audience, expiry, tenant claim, MFA claim.
- Session lifecycle: refresh rotation, revocation, idle/absolute timeout.
- Cross-tenant isolation: API, Postgres RLS, Neo4j, Redis, S3, queues, WS, MCP.
- CSRF, XSS, open redirect, session fixation.
- Invitation and role-change flows.
- STS scope-down: unlisted actions denied; external ID mismatch fails.

### 4.2 Discovery and graph

- Adapter fixtures for every supported resource type.
- Golden fixture organizations with expected topology snapshots.
- Idempotency: run sync twice; graph hash unchanged.
- Reconciliation: create/update/delete in sandbox; graph converges.
- Relationship correctness: network, IAM, load balancing, cross-account.
- Rate limiting and throttling behavior.
- Graph performance: 10k/100k datasets; 1-hop/3-hop queries.
- Tenant isolation in graph queries and raw payload access.

### 4.3 Real-time events

- Event envelope validation and schema compatibility.
- Deduplication, ordering, late events, deletion events.
- Config/CloudTrail normalizers with recorded payloads.
- DLQ and replay.
- Event storm and backlog drain.
- WS auth, subscription, fanout, sequence, resume, backpressure.
- 10k connections and reconnect storm.
- Chaos: worker kill after graph commit, broker outage, Redis failover.

### 4.4 API and search

- OpenAPI contract and backward compatibility.
- Filter semantics, pagination, ETag/304, truncation.
- Search ranking and facets.
- Path and blast-radius limits.
- Cache invalidation and stampede protection.
- Cypher injection and tenant probes.
- Snapshot export, diff, restore, retention.

### 4.5 Frontend

- Component tests and Storybook states.
- Graph store reducers and delta application.
- E2E: sign in, explore, search, inspect, live update, resync, action review.
- Visual regression for light/dark, density, severity.
- Accessibility: axe, keyboard-only, screen-reader smoke.
- Performance: 5k nodes/15k edges, frame rate, memory, long tasks.
- Cross-browser: Chrome, Firefox, Safari (latest two versions).

### 4.6 MCP and actions

- Deterministic plan generation and plan hash stability.
- IAM policy validation and risk scoring.
- Change-set preview vs apply consistency.
- Approval rules: self-approval blocked, four-eyes, expiry, MFA.
- Guardrails: protected resources, deny-list, blast radius, change windows.
- Execution: success, partial failure, verification failure, rollback.
- Idempotency and resource locks.
- Prompt injection and tool abuse.
- Sandbox escape and cross-tenant session reuse.
- Kill switch.

### 4.7 Telemetry and security

- Metric batching, caching, downsampling, quotas.
- SSE reconnect and ordering.
- Rule fixtures: positive, negative, false-positive corpus.
- Finding dedupe, reopening, suppression expiry.
- Attack-path correctness and performance.
- Overlay rendering and accessibility.
- CloudWatch cost estimation vs actual.

### 4.8 Cost and 3D

- Allocation invariants: allocated + unallocated = total.
- Reconciliation to Cost Explorer within 2%.
- Recommendation evidence and savings.
- Budget evaluation.
- 3D performance, picking, LOD, fallback.
- Tenant isolation for cost data.

---

## 5. Contract testing

| Contract | Tool | Gate |
|---|---|---|
| OpenAPI | `openapi-spec-validator`, Schemathesis, generated SDK compile | Breaking change fails PR |
| Event schemas | JSON Schema + compatibility checker | Additive-only within major version |
| MCP tool schemas | JSON Schema snapshots | Tool version mismatch fails |
| WS/SSE messages | JSON Schema + protocol tests | Client/server fixture parity |
| JWT claims | Schema + negative tests | Missing tenant/MFA fails |
| Terraform modules | `terraform validate`, Checkov/tfsec, plan | Security and drift checks |
| Database migrations | Alembic upgrade/downgrade, Cypher migration dry-run | Reversible and idempotent |

**Compatibility policy:** Additive fields are allowed within a major version. Removing/renaming fields, changing types, or changing semantics requires a new major version and a parallel-run period.

---

## 6. AWS integration testing

### LocalStack/moto (fast)

Use for:

- SQS/SNS/EventBridge payload handling.
- S3 presigned URLs and lifecycle logic.
- STS basic assume-role flows.
- DynamoDB/Redis interactions.
- API adapters with recorded responses.

Do not rely on LocalStack for:

- IAM trust policy evaluation and external ID conditions.
- SCPs and permission boundaries.
- CloudFormation change-set fidelity.
- Config recorder behavior and EventBridge cross-account policies.
- CloudWatch metric data.
- Cost Explorer.

### Real sandbox accounts (authoritative)

Use for:

- Onboarding, STS, external ID, scope-down.
- Config/EventBridge/CloudTrail end-to-end.
- CloudFormation change sets and rollback.
- CloudWatch `GetMetricData`.
- Cost Explorer ingestion.
- IAM Access Analyzer validation.

Schedule: nightly full suite; on-demand before phase gates; never on every PR.

---

## 7. Performance testing

| Area | Tool | Scenario | Target |
|---|---|---|---|
| API | k6 | 2k rps, 50 concurrent canvases | p95 < 500ms |
| Topology | k6 + seeded graph | 1-hop/3-hop at 100k nodes | p95 < 300ms / < 1s |
| WS | k6/ws or custom | 10k connections, 1k deltas/s | p95 delivery < 2s |
| Events | Locust/custom | 1k/s sustained, 10k/s burst | No loss; backlog drains |
| Graph ingest | custom | 100k nodes, 500k edges | < 2h full sync |
| Telemetry | custom | 500 resources × 3 metrics, 1k SSE | < 5s freshness |
| Frontend | Playwright trace | 5k nodes, 15k edges | 30fps floor, < 500MB |
| Actions | custom | 100 plans, 20 executions | plan p95 < 60s |

Performance tests run nightly against staging with production-like data. Results are stored and compared to the previous baseline; regressions > 20% fail the nightly gate.

---

## 8. Security testing

| Type | Tool/approach | Frequency |
|---|---|---|
| SAST | Semgrep | Every PR |
| Dependency scanning | Trivy/Dependabot | Every PR + daily |
| Container scanning | Trivy/Grype | Every build |
| IaC scanning | Checkov/tfsec | Every PR |
| Secret scanning | gitleaks | Pre-commit + CI |
| DAST | OWASP ZAP | Nightly against staging |
| Tenant isolation | Custom suite | Every PR + release gate |
| AuthZ matrix | Custom suite | Every PR |
| Prompt injection | Adversarial corpus + red team | Phase 6 gate + quarterly |
| Penetration test | External firm | Before GA + annually |
| Supply chain | Image signing, SBOM, provenance | Every build |

**Release blocker:** any critical/high isolation, authZ, prompt-injection, or write-bypass finding.

---

## 9. Chaos and resilience testing

| Experiment | Expected behavior |
|---|---|
| Kill discovery worker mid-shard | Job resumes; no duplicate nodes |
| Kill delta worker after graph commit | Outbox retries; WS receives once |
| Pause queue consumer for 10 minutes | Backlog drains; no loss |
| Neo4j failover | Reads degrade gracefully; writes retry; graph converges |
| Redis loss | Cache miss; WS clients resync; no data loss |
| Postgres failover | API retries; audit/outbox intact |
| EventBridge outage | Events buffer/retry; reconciliation repairs |
| MCP sandbox crash | Action fails safely; no partial write without rollback |
| AWS API throttling | Backoff; sync slows; alerts fire |
| Primary region loss | DR failover meets RTO/RPO |

Run in staging monthly and before GA. Record results and fix gaps.

---

## 10. Test data and fixtures

### Reference organization

A synthetic but realistic AWS organization used across phases:

- 3 AWS accounts: `shared-services`, `production`, `staging`.
- 3 regions: `us-east-1`, `us-west-2`, `eu-west-1`.
- Shared VPC, VPC peering, Transit Gateway.
- Public ALB → app EC2 → RDS in private subnet.
- EC2 instance role with S3 read access.
- Public S3 bucket (intentional finding).
- Overly permissive IAM role (intentional finding).
- Cross-account role trust.
- Unencrypted EBS volume and RDS instance.
- CloudTrail and Config enabled in two accounts, disabled in one.

Fixture sources:

- Recorded AWS API payloads (anonymized).
- Terraform/CDK scripts to recreate sandbox resources.
- Synthetic graph generators for scale.
- Mock WS/SSE servers for frontend.

### Data rules

- Never use real customer data in tests.
- Anonymize account IDs, ARNs, names, and tags in recorded payloads.
- Seed deterministic IDs for snapshot tests.
- Clean up sandbox resources after each run; tag all test resources.

---

## 11. Release gates by phase

| Phase | Mandatory gates |
|---|---|
| P0 | CI scans, local stack smoke, threat model, contract lint |
| P1 | AuthZ matrix, tenant isolation, STS scope tests, onboarding E2E |
| P2 | Adapter fixtures, topology golden tests, idempotency, 100k benchmark |
| P3 | Event ordering/dedupe, replay, WS load, chaos |
| P4 | OpenAPI contract, query safety, cache, 10k/100k performance |
| P5 | E2E, accessibility, visual regression, 5k-node performance |
| P6 | Golden actions, approval rules, rollback, prompt injection, sandbox isolation |
| P7 | Rule fixtures, false-positive corpus, attack paths, SSE load |
| P8 | Cost reconciliation, recommendations, 3D performance/fallback |
| P9 | Scale, soak, DR, pen test, chaos, operational drills |

A gate is not "all tests green" alone; the phase acceptance criteria and demo must also pass.

---

## 12. Test observability and hygiene

- Test results published to CI with trend history.
- Flaky tests quarantined within 24 hours; owner assigned; fixed or deleted within 2 weeks.
- Coverage targets: 80% line coverage for core services, 90% for security-critical modules (authZ, policy, plan generation).
- Mutation testing for policy/plan modules before GA (optional but recommended).
- Nightly reports posted to the engineering channel.
- Every Sev-1/Sev-2 incident produces a regression test.
