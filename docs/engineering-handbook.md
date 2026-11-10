# Argus Engine — Engineering Handbook

> **Status:** Operational Baseline (Phase 0)

---

## 1. Definition of Done (DoD)

A task or pull request is **Done** when all of the following criteria are met:

1. **Code Standards:** Code passes Ruff, mypy (strict), ESLint, Prettier, and has no compiler or linter warnings.
2. **Contract Compliance:** Any change to wire contracts has updated the Python Pydantic models and passes `pnpm contracts:check`.
3. **Tests:**
   - Unit tests cover all branches and edge cases (minimum 80% coverage across core services).
   - Integration tests verify data layer operations against containerized Postgres/Neo4j/Redis.
   - Frontend changes include component tests (Vitest) and critical journey tests (Playwright).
4. **Tenant Isolation:** Any database query or cache access includes `tenant_id` verification according to the Tenant Isolation Checklist.
5. **Observability:**
   - Error cases raise domain errors mapping to RFC 9457 problem documents.
   - Operations log structured JSON with context (`request_id`, `tenant_id`, `trace_id`).
6. **Documentation & ADRs:** New components, schemas, or architectural changes are documented; any deviation from approved stack has a ratified ADR.

---

## 2. Branching & Release Strategy

- **Trunk-Based Development:** Short-lived feature branches merged to `main` via Pull Request with at least one peer review approval.
- **Commit Messages:** Conventional Commits format:
  - `feat(api): add cursor pagination to topology list`
  - `fix(ws): handle client frame timeout gracefully`
  - `docs(handbook): ratify definition of done`
- **Continuous Deployment:** Merges to `main` automatically deploy to the **Staging** environment via GitHub Actions.
- **Production Releases:** Tagged GitHub releases (`vX.Y.Z`) deploy to Production after automated verification in Staging and release gate sign-off.

---

## 3. Incident Management & Severity Levels

| Severity | Criteria | Response Target | Escalation |
|---|---|---|---|
| **SEV-1 (Critical)** | Production outage, data corruption, cross-tenant leak, or unauthorized AWS action. | 15 minutes | Page on-call Tech Lead & SRE; War room opened immediately. |
| **SEV-2 (Major)** | Major feature degraded (e.g. sync stalled, canvas offline for multiple tenants). | 1 hour | Page primary on-call engineer. |
| **SEV-3 (Minor)** | Non-critical bug with functional workaround (e.g. cost export delayed). | Next business day | Log Jira/Linear ticket for current sprint. |

---

## 4. Initial SLO Skeleton

| Metric | Target | Error Budget | Measurement Point |
|---|---|---|---|
| **API Availability** | 99.9% uptime | ~43 minutes / month | Percentage of non-5xx responses on `/api/v1/*` |
| **API Latency (p95)** | < 250ms | 5% exceeding target | Server response time measured at ALB |
| **WebSocket Freshness** | < 2s delta latency | 2% exceeding target | Time from AWS Config event to browser receipt |
| **Action Execution Reliability**| 99.99% correct execution | Zero unhandled failures | Ratio of successful plan executions to approvals |
