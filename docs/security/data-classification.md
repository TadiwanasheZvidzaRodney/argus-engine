# Argus Engine — Data Classification and Retention

> **Status:** Ratified in Phase 0  
> **Compliance Alignment:** SOC 2 Type II, ISO 27001, GDPR Article 32

---

## 1. Classification Tiers

| Tier | Definition | Examples | Storage Location | Encryption |
|---|---|---|---|---|
| **Public** | Information approved for unauthenticated public consumption. | Marketing docs, public API documentation, software versions. | S3 / CloudFront | SSE-S3 |
| **Internal** | Data for Argus employees and automated platform operations. | Service health, platform deployment metrics, release tags. | CloudWatch, S3, RDS | KMS (AWS managed) |
| **Confidential** | Customer infrastructure metadata and topology descriptions. | AWS Resource ARNs, VPC CIDRs, security group rules, findings. | PostgreSQL, Neo4j, Redis | KMS (Customer Managed Key) |
| **Restricted** | Sensitive security secrets, tokens, and audit trails. | OIDC signing keys, STS session tokens, hash-chained audit logs. | AWS Secrets Manager, S3 Object Lock | KMS (Dedicated CMK with rotation) |

---

## 2. Retention Periods

| Data Category | Retention Period | Deletion Mechanism |
|---|---|---|
| **Audit Logs** | 7 years (immutable) | S3 Object Lock retention policy; compliance mode. |
| **Resource Topology Snapshots** | 90 days active, 1 year archive | S3 lifecycle transition to Glacier Flexible Retrieval. |
| **Live Graph (Neo4j)** | Current state + 7 days delta | Deleted nodes tombstoned and purged after 7 days. |
| **Event Outbox Records** | 14 days post-publish | Automated daily worker cleanup job. |
| **CloudWatch Application Logs** | 90 days (prod) / 14 days (dev) | CloudWatch Log Group expiration policy. |
| **Ephemeral Idempotency Records** | 24 hours | Redis TTL eviction (`EXPIRE`). |
| **Tenant Deprovisioning** | 30 days grace period | Soft delete on day 0; hard cryptographic wipe on day 30. |
