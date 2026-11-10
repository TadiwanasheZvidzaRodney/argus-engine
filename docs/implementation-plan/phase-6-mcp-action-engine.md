# Phase 6 — MCP Action Engine & Safe Mutations

> **Release:** R2 · **Duration:** 9–10 weeks · **Depends on:** Phase 5, Phase 3 · **Owner:** Backend + Security + ML  
> **Entry criteria:** Canvas read-only mode stable; live deltas reliable; sandbox AWS accounts available; write-role template approved.

---

## 1. Objective

Enable bidirectional canvas operations without giving an LLM the keys to production. Every action becomes a typed intent, a deterministic plan, a reviewable diff, an explicit approval, a scoped execution, and a verified outcome with rollback and audit.

At the end of this phase, six golden actions work end-to-end in sandbox accounts, no write can occur without approval, and the audit trail is complete enough for a security review.

---

## 2. Architecture mapping

| Architecture component | Phase 6 contribution |
|---|---|
| AWS MCP Host Client & Prompt Execution Engine | MCP host, sandboxed server sessions, tool registry, LLM gateway |
| Interactive command engine | Canvas intents, action catalog, plan/diff review, approvals |
| Safe mutation protocol | Deterministic planning, change sets, guardrails, rollback |
| Neo4j topology | Pre-action validation and post-action verification |
| PostgreSQL audit/state | Action requests, approvals, plans, executions, evidence |
| WebSocket gateway | Action progress and status updates |

### 2.1 Runtime topology

The MCP **host control plane** runs in the platform and launches an **ephemeral ECS task per plan/execution**. Inside the sandbox task, a host agent talks to the pinned MCP servers over localhost or a private Unix socket; results are written to evidence storage and streamed back through the control plane. The sandbox has no inbound public listener and no public egress. This keeps credentials, tool processes, and tenant data inside one short-lived, auditable boundary.

---

## 3. Non-negotiable safety rules

1. **No write without an approved plan.** A plan must be immutable once approved; any change requires re-approval.
2. **No raw model output executes.** LLMs may propose intent or explanation, but plans are generated from deterministic templates and validated by policy.
3. **No permanent credentials.** Execution uses a short-lived STS session scoped to the action, with session tags.
4. **No unbounded blast radius.** Every plan declares the resources and permissions it will change; limits are enforced before execution.
5. **No silent failure.** Post-execution verification is mandatory; failed verification triggers rollback or a `FAILED` state with an incident.
6. **No bypass of guardrails.** The execution service refuses plans that violate protected-resource, deny-list, or approval rules.
7. **No cross-tenant context.** MCP sessions, prompts, credentials, and plan artifacts are tenant-scoped and never reused.
8. **Kill switch always available.** Writes can be disabled globally or per tenant within one minute.

---

## 4. Action model

### Supported action categories

| Category | Examples | Preferred mechanism |
|---|---|---|
| **Identity & access** | Grant role access to S3; attach least-privilege policy; create role | CDK/CloudFormation + IAM validation |
| **Network exposure** | Allow SG ingress from a source SG/CIDR; remove stale rule | CDK/CloudFormation change set |
| **Data protection** | Enable S3 encryption/versioning; enforce TLS; block public access | CDK/CloudFormation change set |
| **Resource configuration** | Tag/untag; enable logging; adjust retention | CDK/CloudFormation or direct API |
| **Lifecycle** | Stop/start instance; snapshot volume; delete idle resource | Direct API + compensating action |
| **Observability** | Create CloudWatch alarm; enable trail | CDK/CloudFormation |
| **Optimization** | Resize instance class; migrate to Graviton | Plan + maintenance window + rollback |

### Golden actions for exit gate

1. **Connect EC2 to S3** — grant the instance role least-privilege access to a bucket (IAM policy, optional bucket policy).
2. **App to database connectivity** — allow ingress from the app security group to the database security group on the required port.
3. **Harden an S3 bucket** — enable versioning, SSE-KMS, block public access, and TLS-only bucket policy.
4. **Attach a least-privilege IAM policy** — create and attach a scoped policy to a role, validated by Access Analyzer.
5. **Tag resources** — apply/remove tags across a selected set with a blast-radius limit.
6. **Stop and start an instance** — imperative action with compensating rollback and post-verification.

---

## 5. Action lifecycle

```text
DRAFT
  → PLANNING
  → PLAN_READY
  → PENDING_APPROVAL
  → APPROVED
  → EXECUTING
  → VERIFYING
  → SUCCEEDED

Failure branches:
  PLANNING → PLAN_FAILED
  PENDING_APPROVAL → REJECTED | EXPIRED
  EXECUTING → FAILED → ROLLING_BACK → ROLLED_BACK | ROLLBACK_FAILED
  VERIFYING → VERIFICATION_FAILED → ROLLING_BACK
```

Rules:

- Plans expire (default 30 minutes; high-risk 24 hours) and must be re-planned if the graph version changes materially.
- Approval binds to the plan hash, approver identity, tenant, and expiry.
- Execution is idempotent; retries with the same key return the same result.
- A resource lock prevents concurrent conflicting actions on the same resource.
- Cancellation is allowed before execution starts; during execution it follows the rollback policy.

---

## 6. Workstreams and tasks

### WS-MCP-A — MCP host and sandbox

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P6-01 | MCP host service | Python MCP client, server registry, session lifecycle, health, timeouts | L | Backend |
| P6-02 | Transport support | stdio for local/dev; Streamable HTTP for remote; reconnect and error handling | M | Backend |
| P6-03 | AWS MCP server packaging | Pin `aws-api`, `cdk`, `iam`, `cost-explorer` servers; signed images in ECR | L | Platform + Security |
| P6-04 | Version and compatibility matrix | Server versions, MCP protocol versions, tool schema snapshots | M | Backend |
| P6-05 | Sandbox runtime | Per-action ECS task, private subnet, no NAT, VPC endpoints, read-only FS, non-root, limits | XL | Platform + Security |
| P6-06 | Credential injection | STS session per action, scope-down policy, env/agent injection, no disk persistence | L | Backend + Security |
| P6-07 | Tool registry | Allowlisted tools, JSON schemas, read/write classification, risk level, dry-run support | L | Backend + Security |
| P6-08 | Tool call mediation | Validate inputs/outputs, enforce timeouts, redact secrets, log calls | L | Backend |
| P6-09 | Sandbox teardown | TTL, orphan cleanup, audit of task lifecycle | M | Platform |
| P6-10 | Supply-chain controls | Image signing, SBOM, admission policy, dependency review | M | Security |

### WS-MCP-B — Intent capture and planning

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P6-11 | Intent schema | Typed actions with parameters, target resources, constraints, requester | L | Backend |
| P6-12 | Canvas intent service | Drag-to-connect, context menu, action palette, natural-language entry | L | Backend + Frontend |
| P6-13 | Pre-flight validation | Resource existence, account/region scope, permissions, current state, conflicts | L | Backend |
| P6-14 | Action catalog | Supported actions, required permissions, risk level, plan template, rollback template | L | Backend + Security |
| P6-15 | Deterministic planners | CDK constructs/templates per action category; parameter validation | XL | Backend |
| P6-16 | IAM policy builder | Least-privilege policy synthesis from graph relationships and action intent | L | Security + Backend |
| P6-17 | Plan artifact | Immutable JSON: resources, permissions, diffs, risk, blast radius, rollback, cost impact | L | Backend |
| P6-18 | Plan versioning | Hash, graph version, template version, expiry, re-plan triggers | M | Backend |
| P6-19 | Conflict detection | Concurrent actions, drift since plan, dependency conflicts, lock status | M | Backend |

### WS-MCP-C — Diff, validation, and risk

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P6-20 | CDK synth in sandbox | Deterministic build, dependency pinning, reproducible output | L | Backend |
| P6-21 | Change set preview | CloudFormation change set per target account/region; no execution | L | Backend + Platform |
| P6-22 | CDK diff integration | Human-readable diff for supported stacks; fallback to change set | M | Backend |
| P6-23 | IAM validation | `ValidatePolicy`, `CheckNoNewAccess`, `CheckAccessNotGranted`, Policy Simulator | L | Security |
| P6-24 | Risk scoring | Blast radius, privilege level, data exposure, reversibility, environment | L | Security + Backend |
| P6-25 | Security checks | Public exposure, privilege escalation, wildcard actions/resources, protected resources | L | Security |
| P6-26 | Cost impact | Estimate via Cost Explorer/price list where available; flag unknown | M | Backend |
| P6-27 | Visual diff contract | Added/removed/changed nodes/edges and attributes for canvas overlay | M | Backend + Frontend |
| P6-28 | Plan review UI | Summary, diff, policy, risk, blast radius, rollback, approve/reject | XL | Frontend + Design |

### WS-MCP-D — Approval and guardrails

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P6-29 | Approval workflow | Request, reviewers, comments, approve/reject, expiry, notifications | L | Backend |
| P6-30 | Four-eyes policy | Requester cannot approve; two approvers for high/critical risk | M | Backend + Security |
| P6-31 | Step-up authentication | MFA re-challenge at approval and execution | M | Backend + Frontend |
| P6-32 | Break-glass flow | Incident ID, justification, time-bound bypass, post-review, alerting | M | Security |
| P6-33 | Guardrail engine | Protected tags, deny-list, account/region restrictions, change windows, max blast radius | L | Security + Backend |
| P6-34 | Policy-as-code | OPA/Cedar rules for action eligibility and approval requirements | L | Security |
| P6-35 | Kill switch | Global and per-tenant disable; revoke write role; in-flight handling | M | Backend + Platform |
| P6-36 | Rate limits and quotas | Actions per tenant/hour, concurrent executions, max resources per plan | M | Backend |
| P6-37 | Approval inbox UI | Pending, approved, rejected, expired; filters and bulk actions | L | Frontend |

### WS-MCP-E — Execution, verification, rollback

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P6-38 | Execution orchestrator | Step Functions state machine; idempotency, retries, timeouts, cancellation | L | Backend + Platform |
| P6-39 | Resource locking | Per-resource/account locks; TTL; conflict errors | M | Backend |
| P6-40 | Scoped execution role | Assume write role with session policy limited to planned actions/resources | L | Security |
| P6-41 | Declarative execution | CloudFormation stack update/change set execution; drift detection | L | Backend |
| P6-42 | Imperative execution | Direct API calls with compensating actions for lifecycle actions | L | Backend |
| P6-43 | Post-action verification | Read-back APIs, expected state checks, graph reconciliation | L | Backend |
| P6-44 | Rollback engine | Stack rollback, previous template/version, compensating API, verification | L | Backend |
| P6-45 | Failure handling | Partial failure, retry safety, incident creation, operator runbook | M | Backend |
| P6-46 | Action progress stream | WS messages for plan, approval, execution, verification stages | M | Backend + Frontend |
| P6-47 | Action history UI | Timeline, evidence, logs, diff, approvals, rollback controls | L | Frontend |
| P6-48 | Execution sandbox tests | Fault injection at each step; rollback drills | L | QA + Security |

### WS-MCP-F — LLM gateway and evaluation

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P6-49 | LLM gateway | Bedrock client, provider abstraction, tenant routing, quotas, timeouts | L | ML + Backend |
| P6-50 | Prompt templates | Intent parsing, explanation, parameter extraction; structured outputs | L | ML |
| P6-51 | Data protection | Redaction, no training, retention policy, tenant isolation, audit | M | Security + ML |
| P6-52 | Prompt-injection defenses | Treat resource data as untrusted; delimiters; tool allowlist; output validation | L | Security + ML |
| P6-53 | Evaluation harness | Golden intents, adversarial prompts, accuracy and safety metrics | L | ML + QA |
| P6-54 | Fallback behavior | Deterministic UI flow when LLM unavailable; no degradation of safety | M | Backend |
| P6-55 | Cost and token controls | Per-tenant budgets, caching, model routing, max tokens | M | ML + Platform |

### WS-MCP-G — Audit, docs, and launch readiness

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P6-56 | Action audit trail | Prompt, tool calls, plan, approval, execution, verification, rollback | L | Backend + Security |
| P6-57 | Evidence export | Plan artifacts and logs to S3 Object Lock; retention and retrieval | M | Backend |
| P6-58 | Action catalog docs | What each action does, permissions, risks, rollback, limits | L | Product + Security |
| P6-59 | Admin guide | Guardrails, approvals, break-glass, kill switch, troubleshooting | M | Product |
| P6-60 | Security review | Threat model update, red team, pen-test scope for action engine | L | Security |
| P6-61 | Sandbox E2E | All golden actions end-to-end with rollback | L | QA |

---

## 7. Deliverables

- MCP host service with pinned, signed AWS MCP servers.
- Sandboxed execution runtime with no public egress and scoped credentials.
- Tool registry with read/write classification and schema validation.
- Typed intent schema and canvas action entry points.
- Deterministic planners, IAM policy builder, plan artifacts, and change-set previews.
- Risk scoring, security checks, cost impact, and visual diff contract.
- Approval workflow with four-eyes, step-up MFA, break-glass, and kill switch.
- Execution orchestrator, resource locks, verification, and rollback.
- LLM gateway with structured outputs, redaction, and evaluation harness.
- Action history UI, audit evidence, docs, and sandbox E2E suite.

---

## 8. Interfaces and contracts

### Action request

```json
{
  "type": "iam.grant_s3_access",
  "targets": {
    "source": "arn:aws:ec2:us-east-1:123456789012:instance/i-...",
    "target": "arn:aws:s3:::example-bucket"
  },
  "parameters": {
    "actions": ["s3:GetObject", "s3:ListBucket"],
    "prefix": "app-data/*"
  },
  "constraints": {
    "expires_at": "2026-12-31T00:00:00Z",
    "environment": "staging"
  },
  "justification": "App needs read access to processed data",
  "idempotency_key": "act_..."
}
```

### Plan artifact

```json
{
  "plan_id": "pln_...",
  "action_id": "act_...",
  "tenant_id": "tnt_...",
  "plan_hash": "sha256:...",
  "graph_version": 1048577,
  "template_version": "iam-grant-s3-v3",
  "summary": "Grant i-... read access to example-bucket/app-data/*",
  "risk": {
    "level": "medium",
    "blast_radius": 1,
    "reversible": true,
    "reasons": ["cross-service access", "data read"]
  },
  "changes": [
    {
      "resource": "arn:aws:iam::123456789012:role/app-role",
      "operation": "update",
      "attribute": "inline_policy",
      "before_hash": "...",
      "after_hash": "..."
    }
  ],
  "permissions": ["iam:PutRolePolicy", "s3:GetBucketPolicy"],
  "diff": { "format": "cloudformation-change-set", "uri": "s3://..." },
  "rollback": { "strategy": "previous-template", "artifact": "s3://..." },
  "expires_at": "2026-11-10T13:00:00Z"
}
```

### Approval matrix

| Risk | Approvals | MFA | Expiry | Examples |
|---|---|---|---|---|
| **Low** | 1 (requester or operator) | No | 30 min | Tagging, non-prod read access |
| **Medium** | 1 approver, not requester | Yes | 1 hour | SG rule, S3 encryption |
| **High** | 2 approvers, not requester | Yes | 4 hours | IAM policy grant, prod SG exposure |
| **Critical** | 2 approvers + break-glass/incident | Yes | 1 hour | Public exposure, privilege escalation, deletion |

The policy engine computes risk; the requester cannot downgrade it.

### Tool registry entry

```json
{
  "name": "iam.validate_policy",
  "server": "iam-mcp-server",
  "version": "1.2.0",
  "class": "read",
  "risk": "low",
  "input_schema": "schemas/iam.validate_policy.json",
  "timeout_ms": 15000,
  "allowed_actions": ["plan", "verify"]
}
```

---

## 9. Data and schema changes

New PostgreSQL tables:

- `action_requests` — intent, target resources, parameters, status, requester, risk, idempotency key.
- `action_plans` — plan hash, graph version, template version, artifact URI, diff URI, expiry.
- `action_approvals` — approver, decision, comment, MFA timestamp, expiry.
- `action_executions` — execution ID, state machine ARN, status, timings, error, rollback status.
- `action_locks` — resource key, action ID, acquired_at, expires_at.
- `action_evidence` — audit links, prompt IDs, tool call IDs, S3 URIs, checksums.
- `action_catalog` — supported actions, versions, risk, required permissions, enabled flag.
- `guardrail_rules` — policy-as-code version, scope, enabled, evaluation result cache.

New S3 prefixes:

- `s3://argus-action-evidence/tenant=.../action=.../plan.json`
- `.../diff.json`, `.../execution.log`, `.../rollback.json`
- Object Lock in compliance mode for evidence; retention 7 years.

New graph properties:

- Action-managed resources: `managed_by=argus`, `last_action_id`, `last_action_at`.
- Temporary changes: `expires_at` on edges/nodes where applicable (e.g., SG rule with expiry).

---

## 10. Exit gate / acceptance criteria

- [ ] All six golden actions complete end-to-end in sandbox accounts.
- [ ] No write occurs without a plan hash and an approval bound to that hash.
- [ ] Requester cannot approve their own medium/high/critical action.
- [ ] High/critical actions require two approvers and step-up MFA.
- [ ] Plans are deterministic: same intent + graph version + template version produces the same plan hash.
- [ ] IAM policies pass Access Analyzer validation; no wildcard actions/resources unless explicitly justified and approved.
- [ ] Change set preview accurately reflects the applied changes for declarative actions.
- [ ] Post-execution verification confirms the intended state and updates the graph.
- [ ] Rollback succeeds for every golden action; rollback failure raises an incident and pages on-call.
- [ ] A changed plan after approval is rejected and requires re-approval.
- [ ] Concurrent conflicting actions are blocked by resource locks.
- [ ] Kill switch stops new executions within 1 minute and marks in-flight actions appropriately.
- [ ] Prompt-injection and tool-abuse red-team exercises produce no unapproved write.
- [ ] MCP sandbox has no public egress; credentials are short-lived and scoped.
- [ ] Audit evidence is complete, immutable, and retrievable for every action.
- [ ] Action latency targets: plan p95 < 60s; approval flow < 2 min UI; execution p95 < 5 min for golden actions.

---

## 11. Test and validation plan

| Layer | Tests |
|---|---|
| Unit | Intent validation, planner templates, policy builder, risk scoring, guardrails, state machine |
| Contract | Action API, plan schema, tool registry schemas, WS progress messages |
| Integration | MCP servers in sandbox; CloudFormation change sets; IAM validation; S3 evidence |
| E2E | Six golden actions; approval paths; rejection, expiry, cancellation, rollback |
| Security | Prompt injection, tool abuse, confused deputy, cross-tenant session reuse, privilege escalation |
| Fault injection | STS expiry mid-execution, change-set failure, partial apply, verification failure, rollback failure |
| Performance | Plan generation, change-set creation, execution, WS progress latency |
| Compliance | Evidence completeness, retention, access control, four-eyes enforcement |

**Red-team scenarios:**

- A resource tag contains instructions to ignore guardrails.
- A user tries to approve their own high-risk action.
- A plan is mutated after approval.
- A malicious MCP tool returns fabricated success.
- A cross-tenant action ID is guessed.
- An execution uses a session policy broader than the plan.

---

## 12. Risks and mitigations

| Risk | Mitigation |
|---|---|
| LLM hallucinates a dangerous change | Deterministic planners, schema validation, policy engine, human approval |
| Prompt injection via resource metadata | Treat all AWS data as untrusted; never place in system prompt; tool allowlist; output validation |
| MCP server compromise | Signed images, pinned versions, sandbox, no egress, least privilege, SBOM |
| Change set differs from actual apply | Same template/artifact used for preview and apply; hash binding; drift detection |
| Partial failure leaves drift | Verification, compensating actions, rollback drills, incident runbook |
| Approval fatigue | Risk-based approvals, low-risk self-service with guardrails, expiry, clear diffs |
| Cross-tenant credential reuse | Per-action sessions, tenant tags, no shared caches of credentials, isolation tests |
| CloudFormation limits | Per-account action stack strategy, resource limits, alternative imperative path |
| Cost/scale of sandbox tasks | Pooling read-only sessions, task TTL, right-sizing, batch plans |
| MCP ecosystem immaturity | Pin versions, wrap with our own adapters, fallback direct AWS SDK for critical paths |

---

## 13. Metrics

- Actions requested, planned, approved, executed, succeeded, failed, rolled back.
- Plan generation latency p50/p95.
- Approval time p50/p95 by risk.
- Execution duration p50/p95 by action type.
- Verification success rate.
- Rollback success rate.
- Guardrail block count and reasons.
- Prompt-injection detection rate and false positives.
- MCP tool error/timeout rate.
- Kill-switch activations.
- Percentage of actions with complete evidence: **100%**.

---

## 14. Handoff to Phase 7 and Phase 9

Phase 7 can assume:

- A finding can create an action intent with prefilled parameters.
- The action catalog exposes remediation actions and risk.
- The canvas diff overlay and action history are available.

Phase 9 can assume:

- A complete write-path audit trail.
- Guardrails, kill switch, and rollback procedures.
- Known failure modes and runbooks for execution.
