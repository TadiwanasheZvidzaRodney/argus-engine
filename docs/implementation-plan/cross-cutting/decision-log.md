# Cross-Cutting — Decision Log (ADR-001 – ADR-012)

> **Status:** All ADRs (ADR-001 through ADR-012) are **Ratified** in Phase 0.  
> **Rule:** An ADR is required for any decision that changes a cross-cutting contract, vendor, data model, trust boundary, or write path.  
> **Format:** Context → Decision → Alternatives → Consequences → Revisit trigger.

---

## ADR-001 — Backend framework: FastAPI + Python

**Status:** Ratified (Phase 0)  
**Deciders:** Tech Lead, Backend, Platform

### Context

The backend must integrate deeply with AWS APIs, MCP servers, graph queries, event processing, and data normalization. The team needs fast iteration, strong typing, async I/O, and a mature testing ecosystem.

### Decision

Use **FastAPI + Python 3.12+**, Pydantic v2, SQLAlchemy 2, Alembic, and `uv` for dependency management. Services are packaged as containers and deployed on ECS Fargate.

### Alternatives considered

- **NestJS/Node:** strong TypeScript across frontend/backend, but weaker AWS data-processing ecosystem and MCP Python tooling.
- **Go:** excellent performance and concurrency, but slower iteration for graph/data transforms and a smaller MCP ecosystem.
- **Django:** mature but heavier and less async-friendly for WebSocket/event workloads.

### Consequences

- Native boto3, MCP Python SDK, and data-processing libraries.
- Type safety via mypy + Pydantic; runtime validation at boundaries.
- CPU-bound work (layout, large graph transforms) must run in workers or be optimized; avoid blocking the event loop.
- Python packaging and image size require discipline (multi-stage builds, pinned dependencies).

### Revisit trigger

- Team becomes Node-native and hiring favors TypeScript.
- CPU-bound graph processing dominates and Python cannot meet latency/cost targets.
- MCP ecosystem shifts decisively to another language.

---

## ADR-002 — Graph database: Neo4j

**Status:** Ratified (Phase 0)  
**Deciders:** Tech Lead, Data, Platform

### Context

AWS infrastructure is a graph. The product needs recursive traversals, path finding, and relationship-heavy queries that are awkward and slow in relational databases.

### Decision

Use **Neo4j 5** with Cypher. Production uses **Neo4j AuraDB** (managed) unless procurement or data-residency requires self-hosting. Local development uses the Neo4j Docker image.

### Alternatives considered

- **Amazon Neptune:** AWS-native and managed, but Cypher support and tooling are less mature; Gremlin adds complexity.
- **PostgreSQL recursive CTEs:** simpler operations, but poor fit for deep/variable traversals and path analysis at scale.
- **TigerGraph/JanusGraph:** powerful but heavier operational burden.

### Consequences

- Expressive topology and attack-path queries.
- Graph-specific schema migrations, indexes, and query tuning.
- Shared-database multi-tenancy for MVP; dedicated databases for large tenants later.
- Aura cost and vendor dependency; export/portability plan required.

### Revisit trigger

- AWS-native mandate requires Neptune.
- Aura cost exceeds unit economics or data residency prohibits it.
- Graph size/query patterns exceed Neo4j’s practical limits.

---

## ADR-003 — Relational database: Aurora PostgreSQL

**Status:** Ratified (Phase 0)  
**Deciders:** Tech Lead, Backend, Security

### Context

Tenancy, identity, audit, job state, approvals, findings, and cost aggregates need ACID transactions, relational integrity, row-level security, and JSON flexibility.

### Decision

Use **Aurora PostgreSQL 16** with row-level security, JSONB for flexible payloads, PITR, and read replicas.

### Alternatives considered

- **RDS PostgreSQL:** simpler/cheaper at small scale, but less elastic.
- **DynamoDB:** excellent scale, but poor fit for relational audit/approval queries and RLS.
- **CockroachDB:** strong global consistency, but operational overhead not justified for v1.

### Consequences

- RLS provides defense-in-depth for tenant isolation.
- JSONB supports evolving plan/finding/evidence payloads.
- Connection pooling and query tuning are required at scale.
- Multi-region active-active is deferred; DR uses global database/PITR.

### Revisit trigger

- Global active-active or multi-region writes become mandatory.
- Aurora cost dominates unit economics.
- A relational workload moves to a specialized store (e.g., time series).

---

## ADR-004 — Multi-tenancy isolation model

**Status:** Ratified (Phase 0)  
**Deciders:** Security, Tech Lead, Backend

### Context

Argus serves multiple customer organizations. Strong isolation is mandatory, but dedicated infrastructure per tenant is expensive at launch.

### Decision

Use a **shared-database model with tenant-scoped rows and graph nodes** for MVP:

- PostgreSQL RLS on every tenant table.
- Neo4j `tenant_id` on every node/edge with repository-enforced guards.
- Tenant-prefixed Redis keys, S3 prefixes, queue attributes, and MCP sessions.
- Automated cross-tenant isolation tests on every PR.
- **Dedicated Neo4j database per tenant** as an enterprise option, with a documented migration path.

### Alternatives considered

- **Database-per-tenant from day one:** strongest isolation, highest cost/ops.
- **Schema-per-tenant in Postgres:** moderate isolation, migration complexity at scale.
- **Siloed deployments:** strongest isolation, unacceptable operational cost for SaaS.

### Consequences

- Lower cost and faster onboarding for most customers.
- Blast radius of a query bug is larger; mitigated by guardrails, tests, and canaries.
- Dedicated DB routing adds complexity later but is planned.
- Contractual isolation requirements may force a dedicated deployment sooner.

### Revisit trigger

- Any confirmed cross-tenant leak.
- A tenant exceeds 500k resources or 20% of shared graph.
- Contractual/regulatory isolation requirement.
- Noisy-neighbor incidents.

---

## ADR-005 — Event backbone: Config + EventBridge + SQS + CloudTrail

**Status:** Ratified (Phase 0)  
**Deciders:** Tech Lead, Platform, Backend

### Context

The graph must reflect AWS changes within seconds. Events can be lost, duplicated, or reordered; a single source is insufficient.

### Decision

Use **AWS Config** as the primary change signal, **EventBridge** for cross-account routing, **SQS + DLQ** for buffering and replay, **CloudTrail** for attribution and coverage gaps, and **scheduled reconciliation** as the correctness backstop.

Regional ingress buses forward to a central hub; cross-region forwarding uses a native mechanism where available, otherwise a dedicated forwarder.

### Alternatives considered

- **Kinesis/Kafka (MSK):** higher throughput and replay, but more operational complexity and cost at launch.
- **SNS fanout only:** no buffering/retry semantics comparable to SQS.
- **Polling only:** simpler but cannot meet freshness targets.
- **Third-party event pipeline:** adds vendor and data-handling risk.

### Consequences

- Native AWS integration and per-tenant isolation via account conditions.
- Event coverage depends on Config resource support; CloudTrail and reconciliation fill gaps.
- Cross-region delivery requires explicit testing and a supported-region matrix.
- Multiple event sources require a canonical envelope and idempotent consumers.

### Revisit trigger

- Sustained throughput > 10k events/s.
- Multi-cloud expansion.
- A managed event bus provides materially better replay/isolation.

---

## ADR-006 — Authentication and authorization

**Status:** Ratified (Phase 0)  
**Deciders:** Security, Backend, Product

### Context

Enterprise customers need SSO, MFA, fine-grained roles, and auditable approvals. Tokens must not be exposed to browser JavaScript. AWS IAM Identity Center is not an end-user IdP for a SaaS app.

### Decision

Use **OIDC Authorization Code + PKCE** with Cognito (or Keycloak in development) and federation to customer IdPs. The **Next.js BFF** stores tokens server-side and issues HttpOnly cookies. Authorization uses **RBAC + account/region ABAC scopes**, with a policy-as-code layer (OPA/Cedar) for action eligibility and approvals.

### Alternatives considered

- **Auth0/Clerk:** strong DX, but cost and data-processing review at enterprise scale.
- **IAM Identity Center as app IdP:** designed for AWS workforce access, not SaaS end users.
- **Custom auth:** unacceptable security and maintenance burden.

### Consequences

- Standards-based SSO and MFA.
- BFF adds a server component and session store.
- Role changes require short token TTL or session revalidation.
- SCIM provisioning is deferred but designed for.

### Revisit trigger

- Enterprise IdP requirements exceed Cognito capabilities.
- SCIM becomes a sales blocker.
- BFF latency/cost becomes material.

---

## ADR-007 — Frontend stack and canvas engine

**Status:** Ratified (Phase 0)  
**Deciders:** Product, Frontend, Design

### Context

The canvas must render nested AWS topology, support interactive exploration, and remain performant at thousands of nodes. The team wants a mature React ecosystem.

### Decision

Use **Next.js (App Router) + React 19 + TypeScript**, **React Flow** for the 2D canvas, **ELK.js in a Web Worker** for nested layout, **TanStack Query** for server state, **Zustand** for normalized graph/UI state, and **Tailwind + shadcn/ui** for the design system. Three.js/R3F is optional for the Phase 8 macro view.

### Alternatives considered

- **Cytoscape.js:** strong graph algorithms, weaker React integration and custom node UX.
- **Sigma.js/WebGL:** excellent large-graph rendering, less flexible for rich node cards and nested containers.
- **D3:** maximum control, high maintenance cost.
- **Three.js-only:** poor fit for 2D nested topology and accessibility.

### Consequences

- Rich custom nodes, edges, and inspector integration.
- DOM performance limits require LOD, culling, clustering, and caps.
- React Flow Pro license review is required; the MIT core may suffice initially.
- Layout must run off the main thread to preserve frame rate.

### Revisit trigger

- Visible-node counts exceed 5k regularly.
- WebGL rendering becomes necessary for the 2D experience.
- React Flow licensing or maintenance becomes unfavorable.

---

## ADR-008 — Compute and deployment: ECS Fargate + managed data services

**Status:** Ratified (Phase 0)  
**Deciders:** Platform, Tech Lead, Security

### Context

The system has long-running API, WebSocket, worker, and sandbox workloads. The team wants managed compute with low operational overhead and strong AWS integration.

### Decision

Use **ECS Fargate** for API, WebSocket/SSE gateways, workers, and MCP sandbox tasks; **ALB + CloudFront + WAF** at the edge; **Aurora PostgreSQL**, **ElastiCache Redis**, and **Neo4j Aura** as managed data services. Terraform manages the platform.

### Alternatives considered

- **EKS:** more flexibility and ecosystem, but higher operational burden for a small team.
- **Lambda:** good for event handlers, poor fit for long-lived WebSockets and heavy workers.
- **Vercel for frontend:** excellent DX, but data residency, BFF, and enterprise networking requirements favor AWS-hosted Next.js.

### Consequences

- Simple scaling and patching model.
- ALB supports WebSockets with tuned idle timeouts.
- Fargate cold starts and task limits require warm pools for MCP sandboxes.
- Managed services reduce ops but increase per-unit cost.

### Revisit trigger

- Kubernetes mandate or multi-service complexity exceeds ECS.
- Fargate cost dominates at scale.
- Edge/BFF requirements favor a specialized frontend platform.

---

## ADR-009 — MCP runtime: sandboxed ECS tasks with scoped credentials

**Status:** Ratified (Phase 0)  
**Deciders:** Security, Backend, Platform

### Context

The action engine uses AWS MCP servers to inspect, plan, and apply changes. Running MCP servers inside the API process would give tool code broad network and credential access.

### Decision

Run a **Python MCP host** that launches **pinned AWS MCP servers in ephemeral ECS tasks**:

- Private subnets, no NAT, VPC endpoints for AWS APIs and Bedrock.
- Read-only root filesystem, non-root user, seccomp, resource/time limits.
- Short-lived STS credentials scoped to the action.
- Tool allowlist, schema validation, and full audit.
- Signed images, pinned digests, SBOM, and admission policy.

### Alternatives considered

- **In-process MCP servers:** simplest, unacceptable blast radius.
- **Lambda-hosted MCP:** cold starts and execution limits; poor fit for CDK synth/diff.
- **Third-party MCP gateway:** less control over credentials, networking, and audit.

### Consequences

- Strong isolation and least privilege.
- Task orchestration, image management, and cold-start mitigation required.
- Higher cost than in-process but bounded by action volume.
- Fallback direct AWS SDK paths for critical actions if MCP servers are unavailable.

### Revisit trigger

- A mature managed MCP gateway meets security requirements.
- Task startup latency makes the UX unacceptable.
- AWS MCP server consolidation reduces the tool surface.

---

## ADR-010 — LLM strategy: Bedrock + deterministic plans

**Status:** Ratified (Phase 0)  
**Deciders:** Security, ML, Backend

### Context

Natural-language intent, explanations, and parameter extraction benefit from LLMs. Allowing an LLM to generate and execute IAM policies or CloudFormation is unacceptable.

### Decision

Use **Amazon Bedrock** behind a provider abstraction. The LLM may:

- Parse intent and extract parameters.
- Explain a plan or diff.
- Suggest candidate actions.

The LLM may **not**:

- Emit raw IAM policies or CloudFormation that execute without validation.
- Call write tools directly.
- Bypass the policy engine or approval workflow.

Plans are generated from deterministic templates; model output is schema-validated and treated as untrusted.

### Alternatives considered

- **Direct OpenAI/Anthropic APIs:** strong models, but data-processing and residency review.
- **Self-hosted models:** control, but operational and quality burden.
- **No LLM:** safest, but weaker UX for natural-language intent and explanations.

### Consequences

- Tenant data stays in AWS (Bedrock VPC endpoint).
- Model access, quotas, and cost management required.
- Prompt-injection defenses and evaluation harness are mandatory.
- Model quality is not on the critical path for safety.

### Revisit trigger

- Bedrock model quality/cost is uncompetitive.
- Data residency requires a different provider.
- Deterministic UI flows make LLM assistance unnecessary.

---

## ADR-011 — IaC: Terraform for platform, CDK for customer mutations

**Status:** Ratified (Phase 0)  
**Deciders:** Platform, Backend, Security

### Context

The platform infrastructure and customer-facing mutations have different requirements. Platform infra needs broad AWS coverage and mature state management; customer mutations need deterministic diffs, change sets, and rollback.

### Decision

Use **Terraform** for Argus platform infrastructure. Use **AWS CDK constructs + CloudFormation change sets** for customer mutations generated by the action engine. CDK apps are synthesized in the sandbox; change sets provide preview and rollback.

### Alternatives considered

- **All CDK:** consistent toolchain, but platform state management and multi-account orchestration are less mature.
- **All Terraform:** strong platform story, but customer mutation previews require Terraform plan/state access, which is a security and UX burden.
- **Pulumi:** good developer experience, smaller team familiarity.

### Consequences

- Two toolchains; clear boundary and ownership required.
- Customer mutations are declarative where possible and auditable via CloudFormation.
- Imperative actions use direct APIs with compensating rollback.
- CDK synthesis must be reproducible and pinned.

### Revisit trigger

- Terraform or CDK limitations block a critical action.
- A managed IaC platform provides safer customer mutation previews.
- The team standardizes on one toolchain with equivalent safety.

---

## ADR-012 — API style and real-time transport

**Status:** Ratified (Phase 0)  
**Deciders:** Tech Lead, Backend, Frontend

### Context

The canvas needs viewport-scoped reads, live graph deltas, action progress, and high-frequency telemetry. Different transports have different strengths.

### Decision

- **REST + OpenAPI 3.1** for reads, admin, actions, and webhooks.
- **WebSocket** for graph deltas and action progress (bidirectional subscription control).
- **SSE** for telemetry samples (server-to-client, simple reconnect, high frequency).
- Generated TypeScript SDK; contract tests; versioned schemas.

### Alternatives considered

- **GraphQL:** flexible queries, but caching, authorization, and query-cost control are harder for a graph product.
- **gRPC-web:** efficient, but browser/proxy complexity and tooling overhead.
- **Single WebSocket for everything:** simpler transport count, but telemetry head-of-line blocking and reconnect complexity.

### Consequences

- Clear separation of concerns and caching semantics.
- Three transport paths to secure and monitor.
- BFF must proxy/authenticate all three consistently.
- Contract tests and schema versioning are mandatory.

### Revisit trigger

- Transport complexity causes reliability issues.
- GraphQL demand from customers or internal teams.
- Telemetry volume requires a dedicated streaming protocol.

---

## Open decisions (resolve in Phase 0)

| Decision | Options | Owner | Deadline |
|---|---|---|---|
| Identity provider | Cognito vs Keycloak vs Auth0 | Security + Backend | Week 1 |
| Neo4j hosting | AuraDB vs self-hosted on EKS | Platform + Data | Week 1 |
| React Flow license | MIT core vs Pro | Frontend + Legal | Week 2 |
| Primary AWS region | us-east-1 vs eu-west-1 vs customer-driven | Platform + Product | Week 1 |
| Commercial model | Seat-based vs usage-based vs hybrid | Product + Finance | Phase 9 (hooks earlier) |
| SOC 2 timing | Readiness at GA vs certification | Security + Legal | Phase 9 |
| Tenant data residency | Single region vs regional cells | Platform + Product | Phase 9 |

---

## Decision process

1. Author drafts the ADR with context, options, and consequences.
2. Tech Lead + affected owners review within 2 business days.
3. Security reviews any trust-boundary, credential, or write-path change.
4. Decision is recorded with status `Accepted`, `Rejected`, or `Superseded`.
5. Superseded ADRs remain in the log with a link to the replacement.
6. Implementation does not start on a cross-cutting decision until the ADR is accepted.
