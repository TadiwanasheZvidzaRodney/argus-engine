# Local GitHub / GitOps connection

This integration uses the `gh` executable and its OS keyring. It is intentionally
local-only, with an explicit tenant, login and repository allowlist. It is not a
production multi-tenant GitHub App or OAuth integration. Keep the development API
on a trusted machine; local stub authentication is not suitable for public access.

Configure these server-side values in `.env`, then restart the API:

```dotenv
ARGUS_GITHUB_ENABLED=true
ARGUS_GITHUB_TENANT_ID=<tenant UUID without tnt_ prefix>
ARGUS_GITHUB_OWNER=<personal GitHub login>
ARGUS_GITHUB_REPOSITORIES=["<login>/<repository>"]
```

Authenticate with `gh auth login --hostname github.com` on the API host, not in
the browser. Do not put a GitHub token in Argus forms, source control or database.
In `/iac`, connect the repository URL, branch and IaC directory. Argus verifies
the active login, repository write access, branch and directory before storing
the connection. Connections are tenant-scoped and limited to the allowlist.

## Approval workflow

1. Preparing a proposal stores its exact Markdown text locally as
   `PENDING_APPROVAL`; no external writes occur.
2. Review the text in `/iac`. An approver submits the displayed SHA-256 hash.
3. Argus checks permission, tenant, hash, instance/tenant kill switches and GitHub
   scope. It creates a deterministic branch and a **draft** PR containing only
   `.argus/proposals/<id>.md`. The approver and proposal hash are audited.
4. A GitHub reviewer must implement and review real IaC changes separately.

No auto-merge, Terraform apply, CloudFormation deployment, resource import or AWS
mutation is implemented by this bridge. Generated HCL examples from the original
synthesizer are not applied or published as executable remediation.

Repository linking is not Terraform-state reconciliation. The existing graph
drift detector flags heuristics; it does not fetch Terraform state or run a plan.
Zero detected heuristics does not prove infrastructure is in sync with Git.

Disable access with `ARGUS_GITHUB_ENABLED=false` and restart the API, or remove a
repository from the allowlist. For production, replace local CLI credentials and
stub authentication with a tenant-bound GitHub App and verified identity.
