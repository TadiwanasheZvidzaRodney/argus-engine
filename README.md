# Argus Engine

[![CI](https://github.com/argus-engine/argus-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/argus-engine/argus-engine/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![Node](https://img.shields.io/badge/node-22%2B-green)](https://nodejs.org/)

> **See, understand, and safely change your AWS estate.**  
> Real-time topology graph, telemetry overlay, deterministic MCP action engine, and cost intelligence.

For the system design and roadmap, see:
- [High-Level Architecture](ARGUS_ENGINE_HIGH_LEVEL_SYSTEM_ARCHITECTURE.md)
- [Implementation Plan & Phase Map](IMPLEMENTATION_PLAN.md)
- [Phase 0 — Foundations](docs/implementation-plan/phase-0-foundations.md)
- [C4 Architecture Diagrams](docs/architecture/c4-models.md)
- [Engineering Handbook](docs/engineering-handbook.md)

---

## 1. Monorepo Structure

```text
argus-engine/
├── apps/
│   └── web/                     # Next.js 16 (App Router) frontend & BFF
├── services/
│   ├── api/                     # FastAPI read/admin REST API (OpenAPI 3.1, RFC 9457)
│   ├── ws/                      # FastAPI WebSocket delta streaming gateway
│   └── worker/                  # Discovery, sync, action, and telemetry daemons
├── packages/
│   ├── contracts/               # Generated JSON Schemas & typed TypeScript contracts
│   ├── python/argus-core/       # Shared runtime primitives (logging, errors, telemetry, envelopes)
│   └── ui/                      # Argus design system components (Tailwind, React 19)
├── infra/
│   ├── local/                   # LocalStack, Keycloak, Postgres, and OTel bootstrap
│   └── terraform/               # Modular AWS infrastructure (dev, staging, prod)
├── docs/                        # Architecture, contracts, security, and engineering docs
└── spikes/                      # De-risking prototypes (STS, Neo4j, MCP, Canvas)
```

---

## 2. Quick Start

### Prerequisites
- [uv](https://docs.astral.sh/uv/) (Python 3.12+ package manager)
- [Node.js](https://nodejs.org/) (v22+) and [pnpm](https://pnpm.io/) (v12+)
- [Docker](https://www.docker.com/) and Docker Compose

### One-Command Setup

```bash
# 1. Clone & copy environment configuration
cp .env.example .env

# 2. Start local dependencies (Postgres, Redis, Neo4j, LocalStack, Keycloak)
docker compose up -d postgres neo4j redis localstack mailpit

# 3. Install Python and Node dependencies
uv sync --all-groups
pnpm install

# 4. Run database migrations and seed demo data
cd services/api && uv run alembic upgrade head && cd ../..
uv run python -m scripts.seed

# 5. Start development servers
# Terminal 1 (API):
uv run uvicorn argus_api.main:app_factory --factory --reload --port 8000

# Terminal 2 (WebSocket Gateway):
uv run uvicorn argus_ws.main:app_factory --factory --reload --port 8001

# Terminal 3 (Worker):
uv run python -m argus_worker.main run --interval 10

# Terminal 4 (Web frontend):
pnpm --filter @argus/web dev
```

Visit the web application at **http://localhost:3000** (prefilled demo credentials: `demo@argus.local` / `argus-demo`).

---

## 3. Testing and Verification

Run the full local verification gate with:

```bash
# Backend verification (Python)
uv run ruff check .              # Linting
uv run ruff format --check .     # Formatting
uv run mypy                     # Strict type checking
uv run pytest                   # Unit & integration tests

# Frontend verification (TypeScript)
pnpm format:check                # Prettier check
pnpm turbo run lint              # ESLint across packages
pnpm turbo run typecheck         # TypeScript across packages
pnpm turbo run test              # Vitest across packages
pnpm --filter @argus/web e2e     # Playwright E2E browser tests

# Contract verification
uv run python -m argus_core.schema_export check packages/contracts/schemas
```

---

## 4. Key Platform Contracts

- **RFC 9457 Problem Details:** All API and WebSocket error responses adhere to `application/problem+json` with machine-readable error codes and JSON Pointer field references.
- **HMAC Cursors:** Paginated list endpoints return tamper-evident opaque cursors signed with HMAC-SHA256.
- **Idempotency:** All mutating requests (`POST`, `PATCH`, `DELETE`) require an `Idempotency-Key` header cached in Redis for 24 hours.
- **CloudEvents v1 Envelope:** Every event carries a time-ordered ULID (`evt_...`), `tenant_id` (`tnt_...`), and deduplication key.
- **Audit Trails:** Append-only hash-chained records (`prev_hash` -> `hash`) mirrored to S3 with Object Lock in Compliance mode.
