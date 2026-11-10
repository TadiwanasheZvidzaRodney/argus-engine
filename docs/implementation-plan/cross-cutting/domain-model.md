# Cross-Cutting — Domain Model

> **Applies to:** Phases 1–9  
> **Purpose:** Define tenancy, relational schema, graph schema, identity rules, event contracts, and retention so every phase uses the same vocabulary.

---

## 1. Tenancy hierarchy

```text
Tenant (customer organization)
  └── Membership (user + role + account/region scopes)
  └── AWS Account (12-digit account ID)
        └── AWS Region
              └── Resource (VPC, subnet, EC2, S3, IAM role, ...)
                    └── Relationship (contains, routes to, can access, ...)
  └── Action Request → Plan → Approval → Execution → Evidence
  └── Finding → Remediation → Action Request
  └── Cost Snapshot / Recommendation
```

**Invariants:**

- A tenant can connect many AWS accounts; an AWS account belongs to exactly one tenant in v1.
- A user can belong to multiple tenants; the active tenant is explicit in the session.
- Every tenant-scoped row and graph node carries `tenant_id`.
- No cross-tenant query, cache key, queue message, S3 prefix, MCP session, or log stream is permitted.
- Resource identity is the ARN when available; display names are never identity.

---

## 2. Identity and key conventions

| Concept | Convention | Example |
|---|---|---|
| Tenant ID | `tnt_` + UUIDv7 | `tnt_0190c3a1...` |
| User ID | `usr_` + UUIDv7 | `usr_0190c3a1...` |
| Account ID | 12-digit AWS account | `123456789012` |
| Region | AWS region code | `us-east-1` |
| Node ID | ARN, or synthetic URN | `arn:aws:ec2:us-east-1:123456789012:instance/i-...` |
| Synthetic ID | `urn:argus:{tenant}:{account}:{region}:{type}:{natural_key}` | `urn:argus:tnt_...:123...:us-east-1:route-table/rtb-...` |
| Resource key | URL-safe base64 of SHA-256(node_id), 22 chars | `9f3a...` |
| Edge ID | URL-safe base64 of SHA-256(`source\|type\|target`) | `a1b2...` |
| Action ID | `act_` + UUIDv7 | `act_0190c3a1...` |
| Plan ID | `pln_` + UUIDv7 | `pln_0190c3a1...` |
| Execution ID | `exe_` + UUIDv7 | `exe_0190c3a1...` |
| Finding ID | `fnd_` + UUIDv7 | `fnd_0190c3a1...` |
| Event ID | `evt_` + UUIDv7 | `evt_0190c3a1...` |

Database primary keys are `uuid` (UUIDv7). The prefixed forms above are API/human-facing representations of the same UUID; clients never see raw UUIDs. Foreign keys use `uuid` internally.

**Why a resource key?** ARNs can be long and contain characters that are awkward in URL paths. The API uses `resource_key` in paths and includes the full ARN in the response. The mapping is deterministic and tenant-scoped.

**Edge identity:** `(source_id, relationship_type, target_id)` is unique. Parallel edges of the same type must be merged with aggregated properties or split into distinct semantic types.

---

## 3. PostgreSQL schema

All tenant-scoped tables include `tenant_id uuid not null` and are protected by row-level security. The application role sets `SET LOCAL app.tenant_id = '...'` per transaction. Migrations and admin jobs use a separate role with explicit bypass.

Required extensions:

```sql
create extension if not exists citext;
create extension if not exists pgcrypto;
```

### 3.1 Identity and tenancy

```sql
create table tenants (
  id uuid primary key,
  name text not null,
  slug text not null unique,
  status text not null default 'active', -- active | suspended | deleted
  plan text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz
);

create table users (
  id uuid primary key,
  email citext not null unique,
  name text,
  idp_subject text unique,
  status text not null default 'active',
  mfa_enrolled boolean not null default false,
  created_at timestamptz not null default now(),
  last_login_at timestamptz
);

create table memberships (
  tenant_id uuid not null references tenants(id),
  user_id uuid not null references users(id),
  role text not null, -- owner | admin | operator | approver | viewer | auditor
  account_scopes text[], -- null = all accounts
  region_scopes text[],  -- null = all regions
  status text not null default 'active',
  created_at timestamptz not null default now(),
  primary key (tenant_id, user_id)
);

create table invitations (
  id uuid primary key,
  tenant_id uuid not null references tenants(id),
  email citext not null,
  role text not null,
  token_hash text not null,
  invited_by uuid not null references users(id),
  expires_at timestamptz not null,
  accepted_at timestamptz,
  created_at timestamptz not null default now()
);

create table sessions (
  id uuid primary key,
  tenant_id uuid not null,
  user_id uuid not null references users(id),
  refresh_token_hash text not null,
  user_agent text,
  ip inet,
  mfa_at timestamptz,
  expires_at timestamptz not null,
  revoked_at timestamptz,
  created_at timestamptz not null default now()
);
```

### 3.2 AWS accounts and sync

```sql
create table aws_accounts (
  id uuid primary key,
  tenant_id uuid not null references tenants(id),
  account_id char(12) not null,
  alias text,
  org_id text,
  ou_id text,
  read_role_arn text not null,
  write_role_arn text,
  external_id_secret_ref text not null,
  external_id_fingerprint text not null,
  status text not null, -- pending | active | degraded | error | disconnected
  last_validated_at timestamptz,
  last_sync_at timestamptz,
  created_by uuid not null references users(id),
  created_at timestamptz not null default now(),
  unique (tenant_id, account_id)
);

create table aws_regions (
  id uuid primary key,
  tenant_id uuid not null,
  account_id uuid not null references aws_accounts(id) on delete cascade,
  region text not null,
  enabled boolean not null default true,
  discovery_status text not null default 'pending',
  last_sync_at timestamptz,
  unique (account_id, region)
);

create table sync_jobs (
  id uuid primary key,
  tenant_id uuid not null,
  account_id uuid not null references aws_accounts(id),
  region text,
  type text not null, -- backfill | incremental | reconciliation
  status text not null, -- queued | running | succeeded | partial | failed | cancelled
  progress jsonb not null default '{}',
  stats jsonb not null default '{}',
  error jsonb,
  started_at timestamptz,
  finished_at timestamptz,
  created_by uuid,
  created_at timestamptz not null default now()
);

create table sync_job_shards (
  id uuid primary key,
  job_id uuid not null references sync_jobs(id) on delete cascade,
  service text not null,
  shard_key text not null,
  status text not null,
  cursor text,
  error jsonb,
  updated_at timestamptz not null default now()
);

create table resource_coverage (
  tenant_id uuid not null,
  account_id uuid not null,
  region text not null,
  resource_type text not null,
  discovered_count bigint not null default 0,
  mapped_count bigint not null default 0,
  unsupported_count bigint not null default 0,
  updated_at timestamptz not null default now(),
  primary key (tenant_id, account_id, region, resource_type)
);
```

### 3.3 Audit and outbox

```sql
create table audit_events (
  id uuid primary key,
  tenant_id uuid not null,
  actor_type text not null, -- user | system | service
  actor_id text,
  action text not null,
  resource_type text,
  resource_id text,
  request_id text,
  trace_id text,
  source_ip inet,
  user_agent text,
  before_hash text,
  after_hash text,
  metadata jsonb not null default '{}',
  prev_hash text,
  hash text not null,
  created_at timestamptz not null default now()
);

create table outbox_events (
  id uuid primary key,
  tenant_id uuid not null,
  type text not null,
  payload jsonb not null,
  idempotency_key text not null,
  status text not null default 'pending', -- pending | published | failed
  attempts int not null default 0,
  available_at timestamptz not null default now(),
  published_at timestamptz,
  last_error text,
  created_at timestamptz not null default now(),
  unique (tenant_id, idempotency_key)
);
```

Audit rules:

- Application role has `insert` only; no `update`/`delete`.
- `prev_hash` chains within a tenant; a daily anchor is written to S3 Object Lock.
- Sensitive metadata is redacted before insert; raw payloads go to restricted S3.

### 3.4 Actions, approvals, and evidence

```sql
create table action_catalog (
  action_type text primary key,
  version text not null,
  category text not null,
  risk_level text not null,
  required_permissions text[] not null,
  enabled boolean not null default false,
  definition_hash text not null,
  updated_at timestamptz not null default now()
);

create table action_requests (
  id uuid primary key,
  tenant_id uuid not null,
  action_type text not null references action_catalog(action_type),
  status text not null,
  targets jsonb not null,
  parameters jsonb not null,
  constraints jsonb not null default '{}',
  justification text,
  risk_level text,
  requested_by uuid not null references users(id),
  idempotency_key text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, idempotency_key)
);

create table action_plans (
  id uuid primary key,
  tenant_id uuid not null,
  action_id uuid not null references action_requests(id) on delete cascade,
  plan_hash text not null,
  graph_version bigint not null,
  template_version text not null,
  risk jsonb not null,
  changes jsonb not null,
  permissions text[] not null,
  diff_uri text,
  rollback_uri text,
  evidence_uri text,
  expires_at timestamptz not null,
  created_at timestamptz not null default now()
);

create table action_approvals (
  id uuid primary key,
  tenant_id uuid not null,
  action_id uuid not null references action_requests(id) on delete cascade,
  plan_id uuid not null references action_plans(id),
  approver_id uuid not null references users(id),
  decision text not null, -- approved | rejected
  comment text,
  mfa_at timestamptz,
  created_at timestamptz not null default now()
);

create table action_executions (
  id uuid primary key,
  tenant_id uuid not null,
  action_id uuid not null references action_requests(id),
  plan_id uuid not null references action_plans(id),
  status text not null,
  state_machine_arn text,
  started_at timestamptz,
  finished_at timestamptz,
  error jsonb,
  verification jsonb,
  rollback_status text,
  evidence_uri text,
  created_at timestamptz not null default now()
);

create table action_locks (
  tenant_id uuid not null,
  resource_key text not null,
  action_id uuid not null references action_requests(id),
  acquired_at timestamptz not null default now(),
  expires_at timestamptz not null,
  primary key (tenant_id, resource_key)
);
```

### 3.5 Findings, cost, telemetry

```sql
create table findings (
  id uuid primary key,
  tenant_id uuid not null,
  rule_id text not null,
  rule_version int not null,
  resource_id text not null,
  finding_key text not null default '', -- stable sub-identifier, e.g. port/cidr
  severity text not null,
  status text not null, -- open | acknowledged | resolved | risk_accepted | suppressed
  evidence jsonb not null,
  evidence_hash text not null,
  assignee_id uuid,
  first_seen timestamptz not null,
  last_seen timestamptz not null,
  resolved_at timestamptz,
  created_at timestamptz not null default now(),
  unique (tenant_id, rule_id, resource_id, finding_key)
);

create table cost_daily (
  tenant_id uuid not null,
  account_id text not null,
  service text not null,
  usage_type text not null default '',
  tag_key text not null default '',
  tag_value text not null default '',
  period_start date not null,
  amount numeric(18,6) not null,
  currency char(3) not null,
  primary key (tenant_id, account_id, service, usage_type, tag_key, tag_value, period_start)
);

create table telemetry_usage (
  tenant_id uuid not null,
  period_start date not null,
  metric_requests bigint not null default 0,
  estimated_cost numeric(12,4) not null default 0,
  primary key (tenant_id, period_start)
);
```

See the phase documents for the complete table set: action evidence, findings events, snapshots, cost recommendations, budgets, and usage metering.

---

## 4. Neo4j graph schema

### 4.1 Labels

All infrastructure nodes carry the base label `:Resource` plus a specific label.

| Label | Key properties | Notes |
|---|---|---|
| `:Tenant` | `id`, `name`, `status` | Root container; optional but useful for lifecycle |
| `:Account` | `tenant_id`, `account_id`, `name`, `ou_id` | One per connected account |
| `:Region` | `tenant_id`, `account_id`, `code` | One per enabled region |
| `:Resource` | `id`, `arn`, `type`, `name`, `tenant_id`, `account_id`, `region`, `state`, `tags`, `version`, `source`, `created_at`, `updated_at`, `deleted_at`, `last_event_at`, `last_action_id` | Base label for every resource |
| `:Internet` | `tenant_id`, `account_id`, `region` | Sentinel for public exposure |
| `:EC2Instance`, `:Vpc`, `:Subnet`, `:SecurityGroup`, `:Eni`, `:S3Bucket`, `:IamRole`, ... | Type-specific properties | Domain labels for query readability |

**Label naming:** PascalCase domain labels (`:EC2Instance`, `:SecurityGroup`, `:S3Bucket`, `:IamRole`, `:KmsKey`). The canonical AWS type (`AWS::EC2::Instance`) stays in the `type` property for API filtering and catalog mapping.

### 4.2 Relationship types

| Relationship | From → To | Properties | Meaning |
|---|---|---|---|
| `BELONGS_TO` | Account → Tenant | — | Tenant ownership |
| `HAS_REGION` | Account → Region | — | Enabled region |
| `CONTAINS` | Region → VPC; VPC → Subnet; Subnet → Resource; Account → Region | — | Hierarchical containment |
| `RUNS_IN` | EC2/Lambda/ECS task/EKS pod → Subnet | — | Network placement |
| `HAS_ENI` | EC2/RDS/Lambda → ENI | — | Network interface |
| `IN_SECURITY_GROUP` | ENI → SecurityGroup | `direction` | SG membership |
| `EXPOSES` | SecurityGroup → Internet | `protocol`, `from_port`, `to_port`, `cidr`, `source_sg` | Public ingress |
| `ALLOWS` | SecurityGroup → SecurityGroup | `protocol`, `from_port`, `to_port` | SG-to-SG ingress |
| `HAS_ROUTE_TABLE` | Subnet → RouteTable | — | Subnet association |
| `ROUTES_TO` | RouteTable → InternetGateway/NatGateway/TransitGateway/VpcPeering/VpnGateway | `destination_cidr` | Routing |
| `PEERS_WITH` | VPC ↔ VPC | `status` | VPC peering |
| `ATTACHED_TO_TGW` | VPC → TransitGateway | `attachment_id` | TGW attachment |
| `HAS_ROLE` | EC2/Lambda/ECS/EKS → IamRole | `via` (instance profile, task role, etc.) | Identity |
| `HAS_POLICY` | IamRole/User/Group → IamPolicy | `attachment_type` | Policy attachment |
| `CAN_ACCESS` | IamRole/Policy → Resource | `actions`, `confidence`, `evidence` | Effective access (materialized for high-value actions) |
| `ENCRYPTED_BY` | S3/EBS/RDS/EFS/Secrets → KmsKey | — | Encryption |
| `USES_SECRET` | Resource → Secret | — | Secret dependency |
| `HAS_TARGET_GROUP` | LoadBalancer → TargetGroup | — | LB listener/target |
| `TARGETS` | TargetGroup → EC2/Lambda/IP | `port`, `health` | Load balancing target |
| `FRONTED_BY` | Resource → CloudFrontDistribution | — | CDN |
| `PROTECTS` | WafWebAcl → Resource | — | WAF association |
| `ISSUED_FOR` | AcmCertificate → Resource | — | TLS certificate |
| `LOGS_TO` | CloudTrail/Config → S3Bucket | — | Logging destination |
| `ALARMS_ON` | CloudWatchAlarm → Resource | — | Alarm target |
| `SHARES_WITH` | Resource → Resource/Account | `ram_share_id` | Cross-account share |
| `DEPENDS_ON` | Resource → Resource | `reason` | Generic dependency |
| `MANAGED_BY` | Resource → Action/Stack | `action_id` | Argus-managed mutation provenance |

### 4.3 Constraints and indexes

```cypher
CREATE CONSTRAINT tenant_unique IF NOT EXISTS
FOR (t:Tenant) REQUIRE t.id IS UNIQUE;

CREATE CONSTRAINT account_unique IF NOT EXISTS
FOR (a:Account) REQUIRE (a.tenant_id, a.account_id) IS UNIQUE;

CREATE CONSTRAINT region_unique IF NOT EXISTS
FOR (r:Region) REQUIRE (r.tenant_id, r.account_id, r.code) IS UNIQUE;

CREATE CONSTRAINT resource_unique IF NOT EXISTS
FOR (r:Resource) REQUIRE (r.tenant_id, r.id) IS UNIQUE;

CREATE INDEX resource_arn IF NOT EXISTS
FOR (r:Resource) ON (r.arn);

CREATE INDEX resource_type IF NOT EXISTS
FOR (r:Resource) ON (r.tenant_id, r.type);

CREATE INDEX resource_scope IF NOT EXISTS
FOR (r:Resource) ON (r.tenant_id, r.account_id, r.region);

CREATE INDEX resource_state IF NOT EXISTS
FOR (r:Resource) ON (r.tenant_id, r.state);

CREATE FULLTEXT INDEX resource_search IF NOT EXISTS
FOR (r:Resource) ON EACH [r.name, r.arn, r.private_ip, r.public_ip, r.tags_text];
```

`tags_text` is a derived space-joined string for full-text search; the canonical `tags` map remains for filtering and display.

### 4.4 Query guardrails

- Every query anchors on a node with `tenant_id = $tenant`.
- Every traversed node must also match `tenant_id`; use a tenant guard predicate or a subquery.
- Depth limits: 3 for topology, 6 for paths, 8 for attack paths.
- Result caps: 5,000 nodes / 15,000 edges per API response.
- Timeouts: 2s for interactive queries, 10s for async analysis.
- No client-supplied Cypher, labels, or relationship types.
- All writes go through the repository and carry a graph version.

### 4.5 Multi-tenancy strategy

| Stage | Strategy | Trade-off |
|---|---|---|
| **MVP (P1–P8)** | Shared Neo4j database; `tenant_id` on every node/edge; repository guard; per-tenant quotas | Lowest cost; largest blast radius if a query bug escapes |
| **Enterprise option (P9+)** | Dedicated Neo4j database per large tenant (Aura multi-db/Enterprise); routing table in Postgres | Strong isolation; higher cost and operational overhead |
| **Migration path** | Export tenant subgraph → import into dedicated DB → flip routing → delete shared subgraph | Requires careful cutover and verification |

Decision triggers for dedicated databases:

- Tenant exceeds 500k resources or 20% of shared graph.
- Contractual isolation requirement.
- Repeated noisy-neighbor incidents.
- Regulatory/data residency requirement.

---

## 5. Event contracts

### 5.1 Envelope

```json
{
  "id": "evt_01J...",
  "type": "argus.resource.changed.v1",
  "source": "argus.discovery",
  "tenant_id": "tnt_...",
  "account_id": "123456789012",
  "region": "us-east-1",
  "subject": "arn:aws:ec2:...",
  "time": "2026-11-10T12:00:00Z",
  "idempotency_key": "aws-config:123456789012:us-east-1:i-...:v3",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "schema_version": "1.0",
  "data": {}
}
```

### 5.2 Event types

| Type | Producer | Consumer | Payload |
|---|---|---|---|
| `argus.resource.changed.v1` | Normalizer | Graph writer | Node/edge changes, change type, before/after hashes |
| `argus.resource.deleted.v1` | Normalizer | Graph writer | Resource ID, deletion time, source |
| `argus.relationship.changed.v1` | Relationship resolver | Graph writer | Source, type, target, operation |
| `argus.sync.progress.v1` | Sync orchestrator | API/WS | Job, phase, percent, counts |
| `argus.action.requested.v1` | Action service | Planner | Action ID, intent |
| `argus.action.planned.v1` | Planner | Approval/WS | Plan ID, risk, diff URI |
| `argus.action.approved.v1` | Approval service | Executor | Action/plan hash, approvers |
| `argus.action.executed.v1` | Executor | Graph/audit/WS | Execution ID, status, verification |
| `argus.finding.changed.v1` | Rule engine | API/WS | Finding ID, status, severity |

### 5.3 Delivery guarantees

- At-least-once delivery; consumers must be idempotent.
- Ordering is per resource via version/capture time, not global.
- DLQ after 5 failed attempts; replay is idempotent.
- Event archive retention 30 days; audit retention 7 years.
- Schema compatibility: additive changes only within a major version; new major versions run in parallel during migration.

---

## 6. Data classification and retention

| Data | Classification | Retention | Storage |
|---|---|---|---|
| Tenant identity and membership | Confidential | Life of tenant + 30 days | Postgres |
| AWS account metadata and external ID refs | Restricted | Life of account + 30 days | Postgres + Secrets Manager |
| Graph current state | Confidential | Current + 90-day soft delete | Neo4j |
| Raw AWS payloads | Confidential | 30 days | S3, encrypted |
| Event archive | Confidential | 30 days | EventBridge archive/S3 |
| Audit events | Restricted | 7 years | Postgres + S3 Object Lock |
| Action plans and evidence | Restricted | 7 years | S3 Object Lock |
| Findings | Confidential | 2 years after resolution | Postgres |
| Metrics samples | Internal | 1 hour at 1m; 24 hours at 5m | Redis |
| Cost data | Confidential | 3 years | Postgres/S3 |
| Frontend analytics | Internal | 13 months | Analytics provider |
| Logs | Confidential | 30–90 days | CloudWatch/S3 |
| Backups | Restricted | 35 days (PITR), 90 days (graph snapshots) | AWS Backup/S3 |

Tenant deletion:

1. Disable access and revoke STS sessions.
2. Export tenant data on request.
3. Delete graph subgraph, Postgres rows, S3 prefixes, caches, queues, MCP sessions.
4. Retain audit and action evidence per legal requirements, with access restricted.
5. Issue deletion certificate with timestamps and checksums.
6. Hard delete backups after the retention window.

---

## 7. State machines

### Sync job

```text
QUEUED → RUNNING → SUCCEEDED
                 → PARTIAL → (retry) → SUCCEEDED | FAILED
                 → FAILED
                 → CANCELLED
```

### Action

```text
DRAFT → PLANNING → PLAN_READY → PENDING_APPROVAL → APPROVED
      → EXECUTING → VERIFYING → SUCCEEDED

PLANNING → PLAN_FAILED
PENDING_APPROVAL → REJECTED | EXPIRED
EXECUTING → FAILED → ROLLING_BACK → ROLLED_BACK | ROLLBACK_FAILED
VERIFYING → VERIFICATION_FAILED → ROLLING_BACK
```

### Finding

```text
OPEN → ACKNOWLEDGED → RESOLVED
                    → RISK_ACCEPTED (expiry)
                    → SUPPRESSED (expiry)
Any state → OPEN on evidence change
```

### WebSocket connection

```text
CONNECTING → AUTHENTICATED → SUBSCRIBED → LIVE
           → STALE (gap) → RESYNCING → LIVE
           → OFFLINE → RECONNECTING → LIVE
```
