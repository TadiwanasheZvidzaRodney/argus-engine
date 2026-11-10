# Phase 1 — Identity, Tenancy & AWS Account Onboarding

> **Release:** R0 · **Duration:** 5–6 weeks · **Depends on:** Phase 0 · **Owner:** Backend + Security  
> **Entry criteria:** Phase 0 exit gate passed; KMS/Secrets Manager and staging environments available.

---

## 1. Objective

Make Argus Engine safely multi-tenant and able to assume scoped, auditable access into customer AWS accounts without storing long-lived credentials. At the end of this phase, a tenant can sign in, invite users, connect an AWS account through CloudFormation, and pass automated isolation tests.

This is the security foundation for every later phase. No discovery, canvas, or mutation work starts until account onboarding and tenant isolation are trustworthy.

---

## 2. Architecture mapping

| Architecture component | Phase 1 contribution |
|---|---|
| Multi-tenant auth (OIDC / IAM Identity) | OIDC login, corporate federation, sessions, RBAC |
| AWS STS AssumeRole + Control Tower | Cross-account role template, external IDs, credential broker |
| PostgreSQL audit/state | Tenant, identity, account, and audit schemas |
| Backend API gateway | Tenant resolution middleware, authorization, rate limits |
| AWS Organizations | Optional account discovery and organization metadata |

**Clarification:** IAM Identity Center is for workforce access to AWS accounts, not end-user authentication to Argus. Argus users authenticate through OIDC (Cognito or equivalent). IAM Identity Center can be used by platform operators and optionally federated for customer AWS console deep links.

---

## 3. Scope

### In scope

- OIDC Authorization Code + PKCE, BFF session handling, MFA, logout/revocation.
- Tenant, user, membership, role, and invitation model.
- RBAC with account/region scopes; auditor role; approval role reserved for Phase 6.
- AWS account onboarding via CloudFormation template/StackSet.
- External ID generation, storage, and rotation.
- STS credential broker with caching, scope-down, session tags, and audit.
- Connection validation and health checks.
- Append-only audit log with hash chain and S3 Object Lock export.
- Admin UI for users, accounts, regions, and audit.
- Tenant isolation test suite.

### Out of scope

- Resource discovery (Phase 2).
- Event forwarding from customer accounts (resources are created in the onboarding template, activation is Phase 3).
- Mutation/write roles in active use (role template may include an optional write role, but execution is Phase 6).
- SCIM provisioning (design now, implement later if demanded).
- Billing and subscription management.

---

## 4. Workstreams and tasks

### WS-ID-A — Authentication and sessions

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P1-01 | OIDC integration | Cognito user pool (or Keycloak dev) with Authorization Code + PKCE | L | Backend |
| P1-02 | Next.js BFF session | HttpOnly/Secure/SameSite cookies, token refresh rotation, CSRF protection, logout | L | Frontend + Backend |
| P1-03 | MFA policy | TOTP/WebAuthn option; MFA required for Admin/Owner/Approver roles | M | Backend + Security |
| P1-04 | Enterprise federation | SAML/OIDC IdP metadata, JIT user provisioning, domain verification | M | Backend |
| P1-05 | Session management | Idle timeout (30m), absolute session (12h), revoke-all, device/session list | M | Backend |
| P1-06 | Step-up authentication | Re-auth/MFA challenge for sensitive actions and approvals | M | Backend + Frontend |
| P1-07 | Auth rate limits and lockout | Per-IP/per-account throttles, anomaly logging | S | Backend |

### WS-ID-B — Tenancy and authorization

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P1-08 | Tenant schema and lifecycle | `tenants`, `users`, `memberships`, invitations; soft delete; slug rules | L | Backend |
| P1-09 | Postgres row-level security | RLS policies on tenant-scoped tables; migration and test harness | L | Backend + Security |
| P1-10 | Tenant resolution middleware | JWT `tenant_id` claim, active tenant cookie, membership validation | M | Backend |
| P1-11 | RBAC model | Owner, Admin, Operator, Approver, Viewer, Auditor; permission matrix | M | Backend + Product |
| P1-12 | Scoped access | Optional account/region scopes per membership; tag-based scope reserved | M | Backend |
| P1-13 | Invitation and onboarding flow | Email invite, accept, role assignment, expiry, resend | M | Backend + Frontend |
| P1-14 | User and role admin UI | Member list, role changes, remove, session revoke | L | Frontend |
| P1-15 | Tenant switcher | Multi-tenant membership switching with audit | M | Frontend |

### WS-ID-C — AWS account onboarding and credentials

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P1-16 | Account registry | `aws_accounts`, `aws_regions`; status, tags, org metadata, health | L | Backend |
| P1-17 | Onboarding CloudFormation template | Read role, optional write role, external ID condition, permission boundary, Config/EventBridge placeholders | L | Backend + Security |
| P1-18 | StackSet and manual onboarding paths | Organization-wide StackSet for Control Tower customers; per-account template for others | L | Backend |
| P1-19 | External ID lifecycle | Generate per tenant/account, store in Secrets Manager, deliver only through the one-time onboarding flow, never log, support rotation | M | Security + Backend |
| P1-20 | STS credential broker | AssumeRole, session cache, refresh, session tags (`tenant`, `account`, `purpose`), max 1h | L | Backend |
| P1-21 | Credential scope-down | Session policies limiting each call path to required actions | M | Security |
| P1-22 | Connection validation | `GetCallerIdentity`, permission checks, Resource Explorer/Config dry-run, error taxonomy | M | Backend |
| P1-23 | Account health monitor | Periodic validation, role expiry alerts, reconnect workflow | M | Backend |
| P1-24 | Organization discovery | Optional `organizations:ListAccounts` to propose accounts; never auto-connect without consent | M | Backend |
| P1-25 | Onboarding UI | Step-by-step wizard, CloudFormation launch link, progress, validation results | L | Frontend |
| P1-26 | Region enablement UI | Select regions per account; discovery readiness state | M | Frontend |

### WS-ID-D — Audit and notifications

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P1-27 | Audit schema and writer | Append-only table, hash chain, actor/tenant/action/resource, before/after hashes | L | Backend |
| P1-28 | Audit export | Batched export to S3 Object Lock; retention and verification job | M | Backend + Platform |
| P1-29 | Audit query API/UI | Filter by actor, action, resource, time; CSV/JSON export | M | Backend + Frontend |
| P1-30 | Email notifications | Invitations, onboarding status, role changes, connection failures | M | Backend |
| P1-31 | In-app notifications | Bell, read state, links to affected resources | S | Frontend |
| P1-32 | Admin security settings | Session policy, MFA enforcement, allowed email domains | M | Frontend + Backend |

### WS-QA — Isolation and security validation

| ID | Task | Key output | Size | Owner |
|---|---|---|---|---|
| P1-33 | AuthZ matrix tests | Every role × every endpoint, allow/deny snapshots | M | QA + Backend |
| P1-34 | Tenant isolation suite | Cross-tenant read/write probes for API, Postgres, Redis, S3, audit | L | Security + QA |
| P1-35 | STS scope tests | Verify session policies block unlisted actions; verify external ID mismatch fails | M | Security |
| P1-36 | CSRF/XSS/session tests | Cookie flags, token leakage, redirect validation | M | Security |
| P1-37 | Onboarding failure drills | Wrong external ID, missing permissions, deleted role, expired credentials | M | QA |

---

## 5. Deliverables

- Working OIDC login with MFA and BFF session handling.
- Tenant/user/membership model with Postgres RLS and RBAC enforcement.
- Invitation and member-management flows.
- CloudFormation onboarding template and StackSet path.
- STS credential broker with scoped, tagged, short-lived sessions.
- Account registry, health checks, and onboarding wizard.
- Append-only audit log with S3 Object Lock export and query UI.
- Tenant isolation and authZ test suites.
- Runbooks for onboarding, trust-policy, and credential failures.

---

## 6. Interfaces and contracts

### Core API endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/me` | Current user, memberships, active tenant, permissions |
| `GET` | `/api/v1/tenants/{id}/members` | List members |
| `POST` | `/api/v1/tenants/{id}/invitations` | Invite user |
| `PATCH` | `/api/v1/tenants/{id}/members/{userId}` | Change role/scopes |
| `GET` | `/api/v1/aws-accounts` | List connected accounts |
| `POST` | `/api/v1/aws-accounts/onboarding` | Start onboarding; returns CloudFormation URL + external ID reference |
| `POST` | `/api/v1/aws-accounts/{id}/validate` | Validate role and permissions |
| `GET` | `/api/v1/aws-accounts/{id}/health` | Connection and permission health |
| `GET` | `/api/v1/audit-events` | Query audit log |

### JWT claims

```json
{
  "sub": "usr_...",
  "tenant_id": "tnt_...",
  "roles": ["operator"],
  "scopes": {
    "accounts": ["123456789012"],
    "regions": ["us-east-1", "eu-west-1"]
  },
  "mfa": true,
  "session_id": "ses_...",
  "exp": 1760000000
}
```

Rules:

- `tenant_id` is mandatory for tenant-scoped routes.
- Roles are resolved server-side from membership; token roles are hints only.
- Account/region scopes are enforced in the repository layer, not just middleware.
- Tokens are never placed in `localStorage`; the BFF stores them server-side.

### Cross-account role trust policy

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "AWS": "arn:aws:iam::<argus-platform-account>:root" },
    "Action": "sts:AssumeRole",
    "Condition": {
      "StringEquals": {
        "sts:ExternalId": "<per-tenant-account-external-id>"
      },
      "StringLike": {
        "aws:PrincipalArn": "arn:aws:iam::<argus-platform-account>:role/argus-credential-broker*"
      }
    }
  }]
}
```

The role also carries a permission boundary and a session policy applied at assume time. Session tags (`tenant`, `account`, `purpose`) are set by the broker for attribution and downstream conditions; they supplement but do not replace the external ID as the trust boundary.

### Onboarding stack resources

- `ArgusEngineReadRole` — read-only policies plus `resource-explorer-2:Search`, `config:Describe*`, `cloudwatch:GetMetricData`, `ce:Get*`, `tag:GetResources`.
- `ArgusEngineWriteRole` (optional, disabled by default) — mutation permissions limited to the supported action catalog in Phase 6.
- `ArgusEngineExternalId` parameter — no default; must match the tenant-generated value.
- Permission boundary — denies IAM/Organizations/SCP/account-level changes.
- Config recorder, delivery channel, EventBridge rule, and CloudTrail trail placeholders — activated in Phase 3.
- Stack tags: `argus:tenant`, `argus:managed=true`, `argus:version`.

---

## 7. Data and schema changes

New PostgreSQL tables (all tenant-scoped tables carry `tenant_id` and RLS):

- `tenants`
- `users`
- `memberships`
- `invitations`
- `aws_accounts`
- `aws_regions`
- `sessions` (server-side session/refresh metadata)
- `audit_events`
- `outbox_events`

Key constraints:

- Unique `(tenant_id, account_id)` on `aws_accounts`.
- Unique `(account_id, region)` on `aws_regions`.
- Unique lower-cased email globally for users; membership unique per tenant.
- Audit table append-only via database permissions and trigger; updates/deletes denied to the application role.
- External IDs are never stored in plaintext in Postgres; store a Secrets Manager reference and a fingerprint.

See [`cross-cutting/domain-model.md`](cross-cutting/domain-model.md) for full columns and relationships.

---

## 8. Exit gate / acceptance criteria

- [ ] A new user can sign up or be invited, complete MFA, and sign in through the BFF.
- [ ] An Owner can invite members and assign roles; permission changes take effect without re-login.
- [ ] An Admin can onboard an AWS account with the CloudFormation template; the platform validates the role and lists enabled regions.
- [ ] STS sessions are ≤ 1 hour, carry tenant/account/purpose tags, and are scoped down per call path.
- [ ] No long-lived AWS access keys exist anywhere in the platform.
- [ ] Cross-tenant API, database, cache, and audit probes fail and are logged.
- [ ] RBAC matrix tests pass for all roles and endpoints.
- [ ] Audit events are written for login, logout, invitation, role change, account connect/disconnect, role assumption, and audit read.
- [ ] Audit hash chain verifies; export to S3 Object Lock succeeds.
- [ ] Onboarding failure modes produce actionable errors and runbook links.
- [ ] Account health dashboard shows connected/degraded/error states.

---

## 9. Test and validation plan

| Layer | Tests |
|---|---|
| Unit | JWT validation, RBAC decisions, external ID generation, credential cache expiry |
| Integration | Postgres RLS with two tenants; STS against LocalStack and a real sandbox account; CloudFormation template validation |
| Contract | OpenAPI request/response schemas; JWT claim schema |
| Security | Cross-tenant probes, CSRF, session fixation, redirect validation, scope-down verification |
| E2E | Invite → accept → MFA → connect account → validate → view audit |
| Resilience | Secrets Manager outage, STS throttling, expired role, deleted trust policy |
| Operability | Runbook drills for onboarding and credential failures |

**Sandbox requirement:** At least two real AWS sandbox accounts are mandatory. LocalStack cannot validate IAM trust policies, external ID conditions, or SCP behavior faithfully.

---

## 10. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Cross-tenant leakage through a missed query | RLS + repository enforcement + mandatory isolation tests; deny-by-default middleware |
| Customers resist cross-account roles | Publish template, permissions, external ID explanation, and security whitepaper; support StackSets |
| External ID exposure | Store in Secrets Manager; return only a one-time launch link; rotate on demand |
| STS throttling during onboarding bursts | Credential cache, jittered retries, per-account concurrency limits |
| Role permission drift | Health checks compare actual policies to expected; alert on drift |
| Overly broad read role | Start with curated read policies, not `ReadOnlyAccess`; document each permission |
| Audit tampering | Append-only DB role, hash chain, S3 Object Lock, CloudTrail correlation |

---

## 11. Metrics

- Onboarding success rate on first attempt: **> 90%**.
- Median time from launch to validated connection: **< 5 minutes**.
- Cross-tenant isolation test failures: **0**.
- STS assume-role error rate: **< 0.5%**.
- Credential cache hit rate: **> 80%**.
- Audit write latency p95: **< 100ms**.
- MFA adoption for privileged roles: **100%**.

---

## 12. Handoff to Phase 2

Phase 2 can assume:

- Tenant-scoped AWS accounts and regions with validated read roles.
- A credential broker that returns scoped boto3 sessions per account/region.
- Account health and permission introspection.
- Tenant-aware API middleware, RBAC, and audit.
- Known gaps: no resource inventory, no events, no write execution.
