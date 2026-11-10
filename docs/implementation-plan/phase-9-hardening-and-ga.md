# Phase 9 — Hardening, Scale & GA

> **Release:** R4 · **Duration:** 7–8 weeks · **Depends on:** All prior phases · **Owner:** Platform/SRE + Security + Tech Lead  
> **Entry criteria:** R3 feature-complete in staging; no open critical security defects; DR plan drafted.

---

## 1. Objective

Turn a feature-complete product into a production service: prove it at target scale, survive failures, pass security review, operate it with runbooks and SLOs, and launch to design partners and then GA.

This phase is not a buffer. It is where reliability, security, and operability become real.

---

## 2. Architecture mapping

| Architecture component | Phase 9 contribution |
|---|---|
| Whole system | Scale validation, DR, degraded modes, cost efficiency |
| Multi-account/multi-region AWS | Failover, regional resilience, cross-region backup |
| Security & audit | Pen test, compliance evidence, access reviews |
| Operations | On-call, runbooks, status page, support tooling |
| Commercial | Usage metering, billing hooks, tenant lifecycle |

---

## 3. Scope

### In scope

- Scale and soak testing at target capacity.
- Multi-region backup/restore and failover drills.
- Security hardening, pen test, and remediation.
- Reliability program: SLOs, error budgets, chaos, circuit breakers, degraded modes.
- Cost efficiency and unit economics.
- Operability: runbooks, on-call, incident process, status page, admin console.
- Compliance readiness: SOC 2 evidence, retention, DPA, subprocessors, security whitepaper.
- Documentation, training, and customer onboarding.
- Canary release, GA checklist, and hypercare.

### Out of scope

- New product features beyond launch-critical fixes.
- Multi-cloud expansion.
- Full billing system (hooks and metering only unless commercial launch requires more).
- SOC 2 Type II certification audit (readiness only).
- On-prem/air-gapped deployment.

---

## 4. Scale targets

| Dimension | Target | Headroom |
|---|---|---|
| Tenants | 50 | 2× |
| Resources per tenant | 100k | 2× |
| Total graph nodes | 5M | 2× |
| Total graph edges | 25M | 2× |
| Concurrent canvas users | 1,000 | 2× |
| Concurrent WebSocket connections | 10,000 | 2× |
| Event ingestion | 1,000 events/s sustained, 10,000/s burst | 2× |
| API requests | 2,000 rps peak | 2× |
| Actions | 100 concurrent plans, 20 concurrent executions | 2× |
| Metric samples | 500 resources × 3 metrics per active canvas | 2× |
| Cost rows | 50 tenants × 12 months × account/service/tag | — |

If the cost of 2× headroom is prohibitive, document the accepted limit and the scaling path per component.

---

## 5. Workstreams and tasks

### WS-GA-A — Scale and performance

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P9-01 | Capacity model | Per-component throughput/cost model; bottleneck ranking | L | Platform |
| P9-02 | Data generation | Synthetic 5M-node/25M-edge multi-tenant dataset | L | QA + Data |
| P9-03 | Scale test — graph | Ingest, query, reconcile at 100k/tenant and 5M total | XL | Platform + Backend |
| P9-04 | Scale test — API/WS | 2k rps; 10k WS; 1k concurrent canvases | XL | Platform + QA |
| P9-05 | Scale test — events | 1k/s sustained; 10k/s burst; backlog drain | L | Platform |
| P9-06 | Scale test — actions | 100 plans, 20 executions, queueing, locks | L | Backend + QA |
| P9-07 | Scale test — telemetry | 500 resources × 3 metrics per canvas; 1k SSE clients | L | Backend + QA |
| P9-08 | Tuning | Neo4j, Aurora, Redis, ECS, queue, cache, connection pools | XL | Platform + Backend |
| P9-09 | Soak test | 7-day run at 70% peak; memory/disk leaks; queue stability | L | Platform |
| P9-10 | Performance regression suite | Automated benchmarks in CI/nightly with thresholds | M | QA |

### WS-GA-B — Reliability and DR

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P9-11 | SLO finalization | SLIs, targets, error budgets, burn-rate alerts | M | Platform + Product |
| P9-12 | Backup strategy | Aurora PITR, Neo4j snapshots, S3 versioning/CRR, Redis durability | L | Platform |
| P9-13 | Restore drills | Full restore to isolated environment; data integrity checks | L | Platform + QA |
| P9-14 | Multi-region DR plan | RTO 1h, RPO 15m; failover/failback runbooks | L | Platform |
| P9-15 | DR drill | Simulated primary-region loss; execute failover; measure | XL | Platform + all |
| P9-16 | Chaos experiments | Worker kill, queue outage, Neo4j failover, Redis loss, AWS throttle, MCP outage | L | Platform + QA |
| P9-17 | Degraded modes | Read-only mode, live pause, telemetry off, actions disabled, cached graph | L | Backend + Frontend |
| P9-18 | Circuit breakers and bulkheads | Per-dependency isolation; timeouts; retry budgets | M | Backend |
| P9-19 | Incident process | Severity matrix, roles, comms, postmortem template, paging | M | Platform |
| P9-20 | Status page | Public component status and incident history | M | Platform |

### WS-GA-C — Security and compliance

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P9-21 | Threat-model refresh | Full-system review including MCP/LLM and multi-tenancy | M | Security |
| P9-22 | Penetration test | External test of web/API/auth/tenant isolation/action engine | XL | Security + external |
| P9-23 | Pen-test remediation | Fix critical/high; risk-accept documented mediums | L | Engineering |
| P9-24 | Access review | Platform IAM, database roles, break-glass, secrets access | M | Security |
| P9-25 | Vulnerability management | SLAs by severity; automated scanning; patch cadence | M | Security + Platform |
| P9-26 | Supply chain | Image signing, SBOM retention, provenance, dependency policy | M | Platform |
| P9-27 | Encryption review | At rest, in transit, key rotation, tenant key strategy | M | Security |
| P9-28 | Data retention and deletion | Tenant offboarding, export, hard delete, audit retention | L | Backend + Security |
| P9-29 | SOC 2 readiness | Control mapping, evidence collection, policy set, gap plan | XL | Security + Compliance |
| P9-30 | Legal and privacy | DPA, subprocessors, privacy policy, data processing register | L | Legal + Security |
| P9-31 | Security whitepaper | Architecture, controls, tenancy, incident response | M | Security + Product |

### WS-GA-D — Operability and commercial

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P9-32 | Runbook library | All critical alerts have a runbook with diagnosis and remediation | L | Platform + all |
| P9-33 | On-call rotation | Primary/secondary, escalation, handoff, compensation | M | Platform |
| P9-34 | Admin console | Tenant lookup, quotas, feature flags, kill switch, support actions | L | Backend + Frontend |
| P9-35 | Usage metering | Resources, events, metric requests, actions, storage per tenant | L | Backend |
| P9-36 | Billing hooks | Plan limits, overage events, invoice export (if commercial) | M | Backend |
| P9-37 | Tenant lifecycle | Signup, trial, suspend, export, delete, offboarding | L | Backend + Product |
| P9-38 | Support tooling | Impersonation with audit, diagnostic bundles, log search | M | Backend + Security |
| P9-39 | Cost efficiency | Unit economics per tenant/resource; right-sizing; savings backlog | L | Platform + Finance |
| P9-40 | Capacity scaling plan | Trigger thresholds and playbooks for each component | M | Platform |

### WS-GA-E — Documentation, training, and launch

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P9-41 | Admin guide | Onboarding, accounts, roles, guardrails, troubleshooting | L | Product |
| P9-42 | User guide | Canvas, search, findings, actions, cost | L | Product |
| P9-43 | API and integration docs | Auth, endpoints, webhooks, rate limits, examples | M | Backend |
| P9-44 | Security operations guide | Monitoring, incident response, evidence, audit | M | Security |
| P9-45 | Training | Internal support and sales engineering enablement | M | Product |
| P9-46 | Design-partner onboarding | Runbook, checklist, success criteria, feedback loop | L | Product + Customer Success |
| P9-47 | Canary release | Internal tenants → design partners → GA; feature flags | L | Platform |
| P9-48 | GA checklist | Security, reliability, docs, support, legal, billing sign-off | M | Tech Lead |
| P9-49 | Hypercare | 30-day enhanced monitoring and rapid response | L | All |
| P9-50 | Post-launch review | SLO review, incident review, roadmap update | M | Tech Lead + Product |

---

## 6. Deliverables

- Capacity model and scale-test reports for graph, API, WS, events, actions, telemetry.
- 7-day soak-test report with no leaks or unbounded growth.
- DR plan, restore drills, and successful multi-region failover test.
- Chaos experiment results and fixes.
- Degraded-mode runbooks and feature controls.
- Penetration-test report and remediation evidence.
- SOC 2 readiness gap assessment and control evidence plan.
- Access review, vulnerability management, and supply-chain evidence.
- Runbook library, on-call rotation, status page, and incident process.
- Admin console, usage metering, billing hooks, tenant lifecycle.
- Unit economics model and cost-optimization backlog.
- Admin/user/API/security documentation.
- Canary and GA checklists, design-partner onboarding, hypercare plan.

---

## 7. SLOs and error budgets

| SLO | Target | Measurement |
|---|---|---|
| Control-plane availability | 99.9% monthly | Successful API requests / total |
| Canvas API availability | 99.9% monthly | 2xx+3xx / total |
| API latency (read) | 95% < 500ms | Server-side histogram |
| Topology query latency | 95% < 1s | By query shape |
| Event freshness | 95% < 30s | AWS capture → graph commit |
| WS delivery | 95% < 2s | Graph commit → client ack |
| Action plan availability | 99% monthly | Plan requests succeeded |
| Action execution success | 99% of approved actions | Excluding user/template errors |
| Telemetry freshness | 95% < 60s | CloudWatch timestamp → client |
| Data durability | 99.999999999% | S3/Aurora/Neo4j backups |

Error budget policy:

- At 50% burn, freeze risky launches and prioritize reliability.
- At 75% burn, stop feature work until the budget recovers.
- At 100% burn, incident review and executive sign-off required to resume.

---

## 8. DR targets

| Metric | Target |
|---|---|
| RTO (control plane) | < 1 hour |
| RTO (read-only graph) | < 2 hours |
| RPO (Postgres) | < 15 minutes |
| RPO (graph) | < 1 hour (snapshot + replay from events) |
| RPO (audit) | 0 (S3 Object Lock / cross-region replication) |
| Backup restore verification | Monthly |
| Full DR exercise | Before GA and quarterly |

DR runbook must cover:

1. Declare disaster and incident command.
2. Fail over DNS/edge to the recovery region.
3. Restore Aurora from PITR/global database.
4. Restore Neo4j from snapshot and replay events.
5. Rebuild Redis caches; re-establish WS connections.
6. Verify tenant isolation and auth.
7. Enable read-only mode first, then writes.
8. Communicate status and tenant impact.
9. Fail back and validate.

---

## 9. Exit gate / GA checklist

### Engineering

- [ ] Scale targets met with documented headroom or accepted limits.
- [ ] 7-day soak test clean.
- [ ] DR failover drill meets RTO/RPO.
- [ ] Restore drill verifies graph, Postgres, audit, and S3 integrity.
- [ ] Chaos experiments pass; no single point of failure without a runbook.
- [ ] Degraded modes tested: read-only, live pause, telemetry off, actions disabled.
- [ ] All critical/high alerts have runbooks and owners.
- [ ] Performance regression suite runs nightly.

### Security and compliance

- [ ] Pen test critical/high findings remediated or formally risk-accepted.
- [ ] Tenant isolation verified by external test.
- [ ] Threat model refreshed and approved.
- [ ] Access review complete; least privilege verified.
- [ ] Vulnerability SLAs defined and current backlog within SLA.
- [ ] Image signing, SBOM, and provenance in place.
- [ ] SOC 2 readiness gaps documented with owners and dates.
- [ ] DPA, subprocessors, privacy policy, and retention/deletion documented.

### Operations and commercial

- [ ] On-call rotation staffed and paging tested.
- [ ] Status page live.
- [ ] Support tooling and impersonation audited.
- [ ] Admin console supports tenant lifecycle and kill switch.
- [ ] Usage metering reconciles to actual consumption.
- [ ] Billing hooks tested (if commercial).
- [ ] Unit economics reviewed; gross margin target agreed.
- [ ] Design partners onboarded; success criteria met.
- [ ] Canary period completed without Sev-1/Sev-2 incidents.
- [ ] Hypercare plan and 30-day review scheduled.

### Documentation

- [ ] Admin, user, API, and security docs published.
- [ ] Runbooks complete and reviewed.
- [ ] Training completed for support and sales engineering.
- [ ] Architecture diagrams and ADRs current.
- [ ] GA checklist signed by Engineering, Security, Product, and Legal.

---

## 10. Test and validation plan

| Area | Validation |
|---|---|
| Scale | Synthetic 5M-node/25M-edge dataset; 2k rps; 10k WS; 1k/s events |
| Soak | 7 days at 70% peak; memory, disk, queue, connection stability |
| DR | Primary-region loss simulation; measured RTO/RPO; data integrity |
| Chaos | Dependency failures; worker kills; broker/DB failover; throttle storms |
| Security | External pen test; tenant isolation; prompt injection; supply chain |
| Operability | Alert → runbook drill; on-call paging; incident simulation |
| Commercial | Metering reconciliation; billing export; tenant lifecycle |
| Usability | Design-partner onboarding; task success; support ticket analysis |

---

## 11. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Scale test reveals architectural limits | Early capacity modeling; 2× headroom; documented limits; scaling playbook |
| DR drill fails | Run drills before GA; fix gaps; repeat quarterly; automated restore tests |
| Pen-test criticals late | Start external test early in Phase 9; reserve remediation time |
| SOC 2 scope expands | Define trust criteria early; readiness not certification; gap plan |
| On-call burnout | Staffing, escalation, runbooks, blameless postmortems, compensation |
| Cost overruns | Unit economics, budget alarms, right-sizing, per-tenant quotas |
| GA scope creep | Feature freeze after P8; launch-critical fixes only |
| Design partners demand custom features | Triage against roadmap; configuration over code; document workarounds |
| Vendor dependency (Neo4j/Aura, MCP servers) | Exit/portability plans; pinned versions; fallback adapters |

---

## 12. Metrics

- SLO attainment and error-budget burn.
- Incident count, MTTR, MTTA, Sev-1/Sev-2 frequency.
- Scale-test throughput, latency, and resource utilization.
- DR RTO/RPO actuals.
- Cost per tenant, per 1k resources, per 1M events, per 1k metric requests.
- Gross margin (if commercial).
- Support ticket volume and resolution time.
- Design-partner activation and retention.
- Security findings open/closed by severity and age.
- Change failure rate and deployment frequency.

---

## 13. Post-GA roadmap seeds

Capture but do not build during Phase 9:

- Exact resource-level cost via CUR/Athena.
- Custom security rules and policy-as-code for customers.
- Saved/shared canvas views and team annotations.
- Multi-cloud discovery.
- Terraform-based mutations and drift remediation.
- Automated low-risk remediation with policy guardrails.
- Finer-grained RBAC and SCIM.
- Additional AWS regions and data residency options.
- Public API and webhooks for external integrations.
