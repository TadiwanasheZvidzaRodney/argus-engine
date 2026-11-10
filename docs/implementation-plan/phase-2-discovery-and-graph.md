# Phase 2 — Discovery Pipeline & Resource Graph

> **Release:** R1 · **Duration:** 7–8 weeks · **Depends on:** Phase 1 · **Owner:** Backend + Data  
> **Entry criteria:** Tenant-scoped accounts connected; credential broker and audit operational; Neo4j available in staging.

---

## 1. Objective

Build a correct, tenant-scoped inventory of supported AWS resources and their relationships in Neo4j. At the end of this phase, connecting an AWS account triggers a resumable backfill that produces a queryable topology, and re-running discovery is idempotent.

This phase turns Argus from an account registry into a graph of infrastructure.

---

## 2. Architecture mapping

| Architecture component | Phase 2 contribution |
|---|---|
| Initial sync via AWS Resource Explorer | Aggregator index integration, cross-account search, fallback APIs |
| Parallelized SDK workers via STS | Fan-out workers with rate limiting, checkpointing, retries |
| Neo4j resource topology | Node/edge schema, constraints, bulk writer, query repository |
| PostgreSQL state | Sync jobs, progress, errors, coverage reports |
| Permissions/read role | Curated read permissions validated during sync |

---

## 3. Scope

### In scope

- Graph schema v1 and migration framework.
- Declarative resource-type catalog with per-type discovery and mapping.
- Resource Explorer cross-account search plus direct AWS describe adapters.
- Parallel, resumable backfill per account/region.
- Relationship resolution into typed edges.
- Daily reconciliation and tombstoning.
- Sync job API and UI.
- Graph repository with tenant-scoped query helpers.
- Performance benchmark at 100k nodes / 500k edges.
- Coverage reporting and unsupported-resource quarantine.

### Out of scope

- Real-time event ingestion (Phase 3).
- Canvas rendering (Phase 5).
- Mutation actions (Phase 6).
- Metrics, security findings, and cost data (Phases 7–8).
- Every AWS resource type; v1 covers the catalog below.
- Historical graph versioning beyond daily snapshots (Phase 4 adds snapshots).

---

## 4. Supported resource catalog v1

The catalog is intentionally opinionated: cover the resources that explain network reachability, identity, data exposure, and cost, then expand.

| Domain | Resource types |
|---|---|
| **Organization & accounts** | Account, Region, Organization/OU metadata (stored on Account, not as graph nodes) |
| **Networking** | VPC, Subnet, Route Table, Internet Gateway, NAT Gateway, Transit Gateway, VPC Peering, Network ACL, Security Group, ENI, Elastic IP, VPN Gateway, Client VPN, PrivateLink Endpoint |
| **Compute** | EC2 Instance, Auto Scaling Group, Launch Template, ECS Cluster, ECS Service, EKS Cluster, EKS Node Group, Lambda Function |
| **Load balancing** | ALB/NLB, Target Group, Listener, Listener Rule |
| **Storage** | S3 Bucket, EBS Volume, EBS Snapshot, EFS File System |
| **Databases** | RDS Instance, RDS Cluster, Aurora Cluster, DynamoDB Table, ElastiCache Cluster, Redshift Cluster (optional) |
| **Identity** | IAM Role, IAM Policy, IAM User, Instance Profile, IAM Access Key metadata |
| **Security & keys** | KMS Key, Secrets Manager Secret, ACM Certificate, WAF WebACL |
| **Serverless & integration** | API Gateway (REST/HTTP), SNS Topic, SQS Queue, Step Functions State Machine, EventBridge Rule |
| **Observability & governance** | CloudWatch Alarm, CloudTrail Trail, AWS Config Recorder, GuardDuty Detector |
| **Containers & artifacts** | ECR Repository |
| **Content** | CloudFront Distribution, Route 53 Hosted Zone (metadata only) |

Resource types not in the catalog are recorded in a coverage report and optionally stored as generic `Resource` nodes with minimal properties.

---

## 5. Workstreams and tasks

### WS-DISC-A — Graph schema and repository

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P2-01 | Graph schema v1 | Labels, relationship types, common properties, naming rules | L | Data + Backend |
| P2-02 | Constraints and indexes | Tenant-scoped uniqueness, lookup indexes, full-text index foundation | M | Data |
| P2-03 | Migration framework | Versioned Cypher migrations, dry-run, rollback, CI application | M | Backend |
| P2-04 | Graph repository | Typed upsert/delete/query helpers, parameterized Cypher, timeouts, depth limits | L | Backend |
| P2-05 | Tenant guardrails | Repository rejects queries without `tenant_id`; query allowlist; integration tests | M | Backend + Security |
| P2-06 | Raw payload storage | Full AWS payloads in S3 with graph nodes holding a reference; TTL policy | M | Backend |
| P2-07 | Graph schema documentation | ER diagram, property dictionary, relationship semantics | M | Data |

### WS-DISC-B — Resource catalog and discovery adapters

> **Onboarding prerequisite:** Multi-account Resource Explorer requires an aggregator index in a central account plus AWS RAM sharing/association with source accounts. If a customer cannot enable it, the adapter falls back to direct describe APIs and the coverage report marks indexed-only types as unavailable. Validate this during account onboarding, not mid-sync.

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P2-08 | Resource catalog format | Declarative YAML/JSON per type: source, API calls, mapper, relationships, permissions, rate limits | L | Backend |
| P2-09 | Catalog validation tooling | Schema validation, duplicate detection, permission coverage check | M | Backend |
| P2-10 | Resource Explorer integration | Aggregator index setup, cross-account search, filters, pagination, throttling | L | Backend |
| P2-11 | Resource Explorer fallback | Detect unsupported/missing types; route to direct APIs | M | Backend |
| P2-12 | Networking adapters | VPC, subnet, route table, route, IGW, NAT, TGW, peering, NACL, SG, ENI, EIP | XL | Backend |
| P2-13 | Compute adapters | EC2, ASG, launch template, ECS, EKS, Lambda | XL | Backend |
| P2-14 | Storage and database adapters | S3, EBS, EFS, RDS/Aurora, DynamoDB, ElastiCache | XL | Backend |
| P2-15 | Identity adapters | IAM roles, policies, users, instance profiles, access key metadata | L | Backend |
| P2-16 | Load balancing and serverless adapters | ALB/NLB, target groups, listeners, API Gateway, SNS, SQS, Step Functions | XL | Backend |
| P2-17 | Security and governance adapters | KMS, Secrets Manager, ACM, WAF, CloudWatch alarms, CloudTrail, Config, GuardDuty | L | Backend |
| P2-18 | Tag normalization | Consistent tag map, case handling, reserved tags, tag-based search fields | S | Backend |
| P2-19 | Coverage report | Supported vs discovered vs unsupported types per account/region | M | Backend |

### WS-DISC-C — Backfill orchestration

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P2-20 | Sync job model | Job, phase, shard, checkpoint, error, stats, cancellation | L | Backend |
| P2-21 | Orchestrator | Step Functions Distributed Map (or equivalent) fan-out per account/region/service | L | Platform + Backend |
| P2-22 | Worker runtime | ECS task consuming SQS; concurrency, visibility timeout, graceful shutdown | L | Platform |
| P2-23 | Rate limiting | Per-account/region/service token buckets; adaptive retry; jitter | L | Backend |
| P2-24 | Checkpointing and resume | Per-shard cursors; resume without full restart; idempotent replay | M | Backend |
| P2-25 | Progress reporting | Percent, resource counts, ETA, error summary; SSE/polling endpoint | M | Backend |
| P2-26 | Cancellation and retry | Safe cancel, partial results, retry failed shards | M | Backend |
| P2-27 | Scheduled sync | Daily incremental/full sync via EventBridge Scheduler | M | Platform |
| P2-28 | Concurrency controls | Max concurrent accounts/regions per tenant; fair scheduling | M | Backend |

### WS-DISC-D — Relationship resolution

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P2-29 | Relationship framework | Resolver interface, dependency ordering, idempotent edge upserts | L | Data |
| P2-30 | Network topology resolver | VPC→subnet→ENI→instance; route tables→IGW/NAT/TGW/peering; SG↔ENI | XL | Backend |
| P2-31 | Compute and IAM resolver | Instance profile→role→policy; ECS task role; EKS node role; Lambda role | L | Backend |
| P2-32 | Load balancing resolver | ALB→listener→target group→targets; health and scheme | L | Backend |
| P2-33 | Data and encryption resolver | S3→KMS; EBS/RDS→KMS; secrets→KMS; certificates | M | Backend |
| P2-34 | Cross-account resolver | VPC peering, TGW attachments, RAM shares, resource policies | L | Backend |
| P2-35 | Serverless integration resolver | Lambda→SQS/SNS/APIGW/EventBridge; queue→DLQ; topic subscriptions | L | Backend |
| P2-36 | Edge confidence and provenance | Source API, confidence, last_seen, version; unresolved edge queue | M | Data |
| P2-37 | Orphan and dangling edge cleanup | Detect edges to missing nodes; repair on reconciliation | M | Backend |

### WS-DISC-E — Reconciliation and quality

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P2-38 | Inventory snapshot | Canonical hash per resource; stored for diffing | M | Backend |
| P2-39 | Reconciliation job | Compare current inventory to graph; add/update/tombstone; drift report | L | Backend |
| P2-40 | Deletion semantics | Soft delete (`deleted_at`) then hard delete after retention; edge cleanup | M | Backend |
| P2-41 | Deduplication | ARN-first identity; synthetic IDs for ARN-less resources; merge rules | M | Backend |
| P2-42 | Data-quality dashboard | Coverage, unresolved edges, stale nodes, sync failures, unknown types | M | Frontend + Backend |
| P2-43 | Fixture corpus | Recorded AWS payloads for every supported type; anonymized | L | QA |
| P2-44 | Integration tests | LocalStack/moto for adapters; real sandbox accounts nightly | L | QA |
| P2-45 | Graph recovery runbook | Corruption, partial ingest, constraint failures, restore from snapshot | S | Platform |

### WS-DISC-F — Sync UX

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P2-46 | Sync jobs API | List, detail, start, cancel, retry | M | Backend |
| P2-47 | Sync console UI | Account/region status, progress, errors, history | L | Frontend |
| P2-48 | Onboarding handoff | Auto-start discovery after account validation | S | Backend + Frontend |
| P2-49 | Empty and partial states | Clear messaging for unsupported regions/types and permission gaps | S | Frontend |

---

## 6. Deliverables

- Neo4j graph schema v1 with constraints, indexes, and migrations.
- Declarative resource catalog covering the v1 types.
- Resource Explorer + direct API discovery adapters.
- Resumable, rate-limited backfill orchestration with progress and cancellation.
- Relationship resolvers for network, compute, IAM, load balancing, data, and serverless.
- Daily reconciliation with tombstones and drift reporting.
- Graph repository with tenant-scoped query helpers.
- Sync jobs API and console UI.
- Coverage and data-quality dashboards.
- 100k-node performance benchmark report.
- Fixture corpus and adapter integration tests.

---

## 7. Interfaces and contracts

### Sync job API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/sync-jobs` | Start full or incremental sync for account/region |
| `GET` | `/api/v1/sync-jobs` | List jobs with status filters |
| `GET` | `/api/v1/sync-jobs/{id}` | Job detail, phases, shards, errors |
| `POST` | `/api/v1/sync-jobs/{id}/cancel` | Cancel remaining shards |
| `POST` | `/api/v1/sync-jobs/{id}/retry` | Retry failed shards |
| `GET` | `/api/v1/accounts/{id}/coverage` | Supported vs discovered resource types |

### Sync job states

```text
QUEUED → RUNNING → (SUCCEEDED | PARTIAL | FAILED | CANCELLED)
                  ↘ PAUSED (rate limit / operator)
```

A job is `PARTIAL` when at least one shard fails but others succeed; the UI must surface which resource types are incomplete.

### Graph node contract

```json
{
  "id": "arn:aws:ec2:us-east-1:123456789012:instance/i-0123456789abcdef0",
  "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-0123456789abcdef0",
  "type": "AWS::EC2::Instance",
  "name": "web-prod-1",
  "tenant_id": "tnt_...",
  "account_id": "123456789012",
  "region": "us-east-1",
  "state": "running",
  "tags": { "Environment": "prod", "Owner": "platform" },
  "source": "ec2:DescribeInstances",
  "version": 42,
  "created_at": "2025-01-01T00:00:00Z",
  "updated_at": "2026-11-10T12:00:00Z",
  "deleted_at": null,
  "raw_ref": "s3://argus-raw/tenant=.../account=.../region=.../ec2/i-.../2026-11-10.json"
}
```

### Identity rules

- Canonical ID is the ARN when available.
- ARN-less resources use `urn:argus:{tenant}:{account}:{region}:{type}:{natural_key}`.
- Node uniqueness is `(tenant_id, id)`.
- Edge identity is `(source_id, type, target_id)` with properties merged on upsert.
- Never use display names as identity.

See [`cross-cutting/domain-model.md`](cross-cutting/domain-model.md) for the full graph schema.

---

## 8. Data and schema changes

- New Neo4j labels and relationship types as defined in the domain model.
- New PostgreSQL tables: `sync_jobs`, `sync_job_shards`, `sync_job_errors`, `resource_coverage`, `inventory_snapshots`.
- New S3 prefixes for raw payloads, partitioned by tenant/account/region/type/date.
- Graph schema version node and migration history.
- Retention: raw payloads 30 days (configurable); inventory snapshots 90 days; graph current-state only.

Estimated volume for a 100k-resource tenant:

| Data | Estimate |
|---|---|
| Nodes | 100k |
| Edges | 300k–500k |
| Raw payloads | ~5–20 GB (compressed, 30-day TTL) |
| Neo4j storage | ~2–5 GB before indexes; plan 2× headroom |

---

## 9. Exit gate / acceptance criteria

- [ ] Onboarding an account automatically starts discovery and completes without manual intervention.
- [ ] Every catalog type has a fixture test and appears in a real sandbox sync.
- [ ] Coverage report shows ≥ 90% of discovered resource types mapped; exceptions documented.
- [ ] A 10k-resource account completes initial sync in < 15 minutes (p50), and 100k resources in < 2 hours under test conditions.
- [ ] Re-running a sync produces zero duplicate nodes or edges.
- [ ] Deleting a resource in AWS results in a tombstone after reconciliation and removal from default queries.
- [ ] Network topology for a fixture account matches the expected graph exactly (snapshot test).
- [ ] Graph queries for 1-hop and 3-hop neighborhoods meet the performance targets below.
- [ ] Tenant isolation tests pass for every graph read and write path.
- [ ] Rate limiting prevents AWS throttling errors from failing a sync; retries and backoff are visible.
- [ ] Data-quality dashboard shows coverage, unresolved edges, and stale nodes.
- [ ] Runbooks for throttling, partial sync, and graph restore are published.

### Performance targets

| Operation | Target |
|---|---|
| Bulk upsert throughput | ≥ 2,000 nodes/min per worker |
| 1-hop neighborhood query (10k-node tenant) | p95 < 150ms |
| 3-hop neighborhood query (100k-node tenant) | p95 < 800ms |
| Full sync 10k resources | < 15 min |
| Full sync 100k resources | < 2 hours |
| Reconciliation diff 100k resources | < 10 min |

---

## 10. Test and validation plan

| Layer | Tests |
|---|---|
| Unit | Mappers, ID normalization, tag handling, relationship rules, rate-limiter math |
| Contract | Resource catalog schema; node/edge schema snapshots |
| Integration | Adapters against LocalStack/moto; real sandbox accounts nightly; Neo4j testcontainers |
| Graph correctness | Golden fixture accounts with expected topology snapshots |
| Idempotency | Run each sync twice; assert identical graph hash |
| Reconciliation | Create/update/delete resources in sandbox; assert graph convergence |
| Performance | 10k/100k synthetic graphs; ingest and query benchmarks |
| Resilience | Throttling, expired credentials, partial API failures, Neo4j restart mid-sync |
| Security | Tenant isolation, Cypher injection attempts, raw payload access control |

**Test data:** Build a synthetic "reference organization" with 3 accounts, 3 regions, overlapping VPC CIDRs, shared VPC, peering, TGW, and cross-account S3 access. This fixture becomes the canonical correctness test for Phases 2–7.

---

## 11. Risks and mitigations

| Risk | Mitigation |
|---|---|
| AWS API throttling during backfill | Token buckets, adaptive retry, shard-level concurrency caps, off-peak scheduling |
| Resource Explorer coverage gaps | Fallback describe adapters; coverage report; generic resource nodes |
| Neo4j write contention | Batched `UNWIND`, per-shard serialization, index tuning, separate read/write routing later |
| Graph schema churn | Versioned migrations; additive changes; snapshot tests |
| Cross-account relationships missed | Explicit resolver tests with shared VPC/TGW/peering fixtures |
| Raw payload storage growth | Compression, 30-day TTL, S3 lifecycle policies |
| Initial sync takes too long for large orgs | Prioritize network/identity/compute types first; progressive availability |

---

## 12. Metrics

- Sync success rate: **> 98%** of shards.
- Resource coverage: **> 90%** of catalog types per account.
- Sync duration p50/p95 by account size.
- AWS throttling rate and retry count.
- Graph write error rate: **< 0.1%**.
- Duplicate node rate: **0**.
- Unresolved edge rate: **< 2%**.
- Query latency p95 by depth.
- Stale node count (not seen in last reconciliation).

---

## 13. Handoff to Phase 3 and Phase 4

Phase 3 can assume:

- A stable graph schema and idempotent graph writer.
- Resource mappings from AWS Config types to graph nodes.
- Reconciliation jobs that can repair missed events.
- Raw payload storage and provenance fields.

Phase 4 can assume:

- A populated graph with consistent IDs and relationships.
- Repository-level tenant scoping and query limits.
- Coverage and sync state available for API responses.
- Known performance envelope at 100k nodes.
