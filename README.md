# Argus Engine

[![CI](https://github.com/argus-engine/argus-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/argus-engine/argus-engine/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![Node](https://img.shields.io/badge/node-22%2B-green)](https://nodejs.org/)

> **See, understand, and safely change your cloud estate.**  
> Real-time topology graph, IAM attack path BFS, live telemetry, FinOps cost attribution, deterministic MCP action engine with automated rollback, SOC 2 cryptographic evidence locker, and GitOps IaC drift PR synthesis.

---

## Architecture Overview

```text
┌────────────────────────────────────────────────────────────────────────┐
│                          ARGUS WEB FRONTEND                            │
│  Next.js 16 (App Router) · React 19 · React Flow Canvas · Tailwind v4  │
└───────────────────▲────────────────────────────────▲───────────────────┘
                    │ REST (RFC 9457)                │ SSE & WebSockets
┌───────────────────┴────────────────┐   ┌───────────┴───────────────────┐
│         CONTROL-PLANE API          │   │      STREAMING GATEWAY        │
│       FastAPI (Port 8000)          │   │     FastAPI WS (Port 8001)    │
└───────┬────────────┬────────────┬──┘   └───────────┬───────────────────┘
        │            │            │                  │
        ▼            ▼            ▼                  ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌─────────────────────┐
│  PostgreSQL  │ │    Neo4j     │ │   Redis 7    │ │    DISCOVERY &      │
│  16 (+ RLS)  │ │  5.26 Graph  │ │ In-Memory /  │ │  INGESTION WORKER   │
│ Multi-tenant │ │ Tenant-scoped│ │ Idempotency  │ │ EventBridge / SQS   │
└──────────────┘ └──────────────┘ └──────────────┘ └──────────┬──────────┘
                                                              │
                                                     AWS Config / CloudTrail
```

---

## Key Capabilities

1. **Interactive Topology Canvas (`/topology`)**:
   - Nested container layout (VPCs, Subnets, Security Groups, EC2, RDS, S3, IAM, ALBs, Gateways).
   - Real-time layer toggles for **Security**, **Telemetry**, and **Cost**.
   - Inspector Drawer with detailed attributes, live CloudWatch sparklines, security findings, and estimated monthly run-rate with confidence disclosure.

2. **Security Intelligence & Attack Paths (`/security`, `/findings`)**:
   - 20 curated, versioned CIS AWS Foundations and NIST 800-53 security rules.
   - Deterministic BFS attack path engine calculating reachable risk paths from internet entry points to sensitive data stores (`S3`, `RDS`, `Secrets Manager`).
   - Automated finding lifecycle (deduplication, reopening on evidence change, time-bounded suppression, and one-click remediation handoff).

3. **Deterministic MCP Action Engine (`/actions`)**:
   - Code-defined, immutable action catalog (`network.restrict_security_group_ingress`, `optimization.resize_instance`, `ec2.stop_start_instance`, `s3.harden_bucket`, `tagging.apply`).
   - Risk matrix and approval policies (Low, Medium, High, Critical) with break-glass incident justification and blast-radius capping.
   - Dual-phase execution: simulated sandbox execution, pre-flight guardrails, post-apply verification, and automated rollback on failure.
   - Instance-wide and per-tenant kill switch controls.

4. **FinOps & Cost Intelligence (`/cost`)**:
   - Direct AWS Cost Explorer ingestion and 12-month backfill.
   - Allocation reconciliation engine maintaining strict invariant: `allocated + unallocated = total` (variance < 2%).
   - 9 automated optimization rules (idle EC2/RDS, unattached EBS, stale snapshots, oversized instances, Graviton upgrades, unassociated EIPs).
   - Monthly budget thresholds and alerting.

5. **SOC 2 Evidence Locker & Hardening (`/compliance`)**:
   - Continuous automated control evaluation across SOC 2 Type II, CIS AWS, and NIST 800-53.
   - Tamper-evident evidence locker with deterministic SHA-256 evidence hashing and 90-day retention.
   - Exportable, cryptographically signed audit package manifest (`SEALED_IMMUTABLE`).
   - Live production SLO tracking, error budget burn rates, operational degraded mode circuit breakers, and multi-region DR drill verification.

6. **GitOps Bridge & IaC Drift Remediation (`/iac`)**:
   - Closes the loop between ClickOps and GitOps.
   - Scans live cloud configuration against Terraform/OpenTofu baselines to detect manual untracked modifications.
   - Compiles exact unified HCL diffs and automatically opens ready-to-merge GitHub / GitLab Pull Requests.

---

## Monorepo Structure

```text
argus-engine/
├── apps/
│   └── web/                     # Next.js 16 (App Router) frontend, React Flow canvas, & BFF
├── services/
│   ├── api/                     # FastAPI read/admin REST API (OpenAPI 3.1, RFC 9457)
│   ├── ws/                      # FastAPI WebSocket delta streaming gateway
│   └── worker/                  # Discovery, sync, action, and telemetry daemons
├── packages/
│   ├── contracts/               # Generated JSON Schemas & typed TypeScript contracts
│   ├── python/argus-core/       # Shared runtime primitives (graph repo, logging, errors, settings)
│   └── ui/                      # Argus design system components (Tailwind v4, React 19)
├── infra/
│   ├── cloudformation/          # ArgusEngineOnboarding cross-account IAM role template
│   ├── local/                   # Docker bootstrap for Postgres, Neo4j, Redis, LocalStack, Keycloak
│   └── terraform/               # Modular AWS production infrastructure (dev, staging, prod)
├── scripts/
│   ├── seed.py                  # Seed initial tenant, admin, and topology baseline
│   └── clean_and_sync_real_aws.py # Real AWS account discovery and synchronization script
└── docs/                        # Architecture specs, ADRs, and implementation plans
```

---

## Quick Start (Local Development)

### Prerequisites
- [uv](https://docs.astral.sh/uv/) (Python 3.12+ package manager)
- [Node.js](https://nodejs.org/) (v22+) and [pnpm](https://pnpm.io/)
- [Docker](https://www.docker.com/) and Docker Compose
- [AWS CLI v2](https://aws.amazon.com/cli/) (optional, for connecting real AWS accounts)

### 1. Start Supporting Containers
```bash
docker compose up -d postgres neo4j redis
```

### 2. Configure Environment
```bash
cp .env.example .env
```
*(The default `.env` is configured for local development on `http://localhost:3000` with local $0.00 Docker data stores).*

### 3. Install Dependencies
```bash
uv sync --all-groups
pnpm install
```

### 4. Run Database Migrations & Seed Baseline
```bash
# Run PostgreSQL migrations
cd services/api
ARGUS_DATABASE_URL='postgresql+asyncpg://argus:argus@localhost:5432/argus' uv run --project ../.. alembic upgrade head
cd ../..

# Seed demo tenant, user, audit anchor, and topology
uv run python scripts/seed.py
```

### 5. Start Development Servers
Open two terminal tabs:

**Terminal 1 (FastAPI API):**
```bash
uv run uvicorn argus_api.main:create_app --factory --host 0.0.0.0 --port 8000 --reload
```

**Terminal 2 (Next.js Web Frontend):**
```bash
pnpm --filter @argus/web dev
```

Open **http://localhost:3000** and click **Continue** (logs in as `demo@argus.local`).

---

## Connecting Your Real AWS Account (Free Tier / $0.00)

To connect and visualize your real AWS account instead of mock data:

1. **Authenticate your AWS CLI**:
   ```bash
   aws sts get-caller-identity
   ```

2. **Deploy the Scoped Read-Only IAM Role ($0.00 / Free Tier)**:
   Deploy the included CloudFormation template to your account:
   ```bash
   aws cloudformation deploy \
     --template-file infra/cloudformation/ArgusEngineOnboarding.template.yaml \
     --stack-name argus-engine-onboarding \
     --region us-west-2 \
     --capabilities CAPABILITY_NAMED_IAM \
     --parameter-overrides \
         ArgusTenantId="tnt_0190c3a1-0000-7000-8000-000000000001" \
         ArgusExternalId="ext_0190c3a10000_secret_onboarding_token" \
         ArgusPlatformAccountId="YOUR_AWS_ACCOUNT_ID" \
         EnableRealTimeSync="false" \
         EnableWriteRole="false"
   ```

3. **Discover & Sync Real Resources**:
   Run the live sync script:
   ```bash
   uv run python scripts/clean_and_sync_real_aws.py
   ```
   Your live VPCs, subnets, route tables, internet gateways, security groups, S3 buckets, and IAM roles will be mapped into Neo4j and displayed on the canvas!

---

## Full Verification & Testing Suite

Run the quality gates locally:

```bash
# Contract verification
uv run python -m argus_core.schema_export check packages/contracts/schemas

# Python formatting, linting, and strict type checking
uv run ruff check .
uv run ruff format --check .
uv run mypy

# Backend unit & integration tests (163 tests)
uv run pytest -q

# Frontend Prettier, linting, type checking, and unit tests
pnpm format:check
pnpm turbo run lint typecheck test build

# Playwright End-to-End browser tests
pnpm --filter @argus/web e2e
```

---

## Key Platform Invariants

- **Multi-Tenancy Isolation:** Strict PostgreSQL Row-Level Security (RLS) via `app.tenant_id` session configuration and `tenant_id` properties indexed on all Neo4j graph nodes and edges.
- **RFC 9457 Problem Details:** All API errors adhere to `application/problem+json` with standard machine-readable codes and JSON Pointer field references.
- **Idempotency:** All mutating requests require an `Idempotency-Key` header cached in Redis. Read-only POST queries (`/topology/query`, `/security/attack-paths`, `/telemetry/snapshot`) use bypass validation.
- **Deterministic Action Engine:** Actions compile code-defined, immutable plans. LLMs are never permitted to execute raw shell/CLI commands.
- **Reconciliation Invariant:** Cost allocation strictly reconciles such that `sum(allocated) + unallocated = total` (variance < 2%).
- **Cryptographic Evidence Locker:** Audit events and compliance control evaluations are append-only and sealed with SHA-256 hashes.
