# Argus Engine — Event Conventions (v1)

> **Status:** Ratified in Phase 0  
> **Schema Definition:** `packages/python/argus-core/src/argus_core/events.py`  
> **Exported JSON Schema:** `packages/contracts/schemas/event-envelope.v1.json`

---

## 1. Envelope Specification

Every internal and external event published across SQS, EventBridge, or Redis lists adheres to the CloudEvents-compatible `EventEnvelope` model:

```json
{
  "id": "evt_01M72X0XRJW6258F801883YZDH",
  "type": "argus.resource.changed.v1",
  "source": "argus.discovery",
  "tenant_id": "tnt_0190c3a1-0000-7000-8000-000000000001",
  "account_id": "123456789012",
  "region": "us-east-1",
  "subject": "arn:aws:ec2:us-east-1:123456789012:instance/i-0abc1234def",
  "time": "2026-11-10T12:00:00Z",
  "idempotency_key": "aws-config:123456789012:us-east-1:v3",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "schema_version": "1.0",
  "data": {
    "change_type": "UPDATE",
    "resource_type": "AWS::EC2::Instance"
  }
}
```

### Required Fields:
- `id`: Unique, time-ordered ULID prefixed with `evt_`.
- `type`: Reverse-domain format `argus.<domain>.<action>.v<version>`.
- `source`: Producer namespace (e.g. `argus.discovery`, `argus.action-engine`, `argus.worker`).
- `tenant_id`: Mandatory tenant prefix `tnt_` followed by UUIDv7.
- `time`: RFC 3339 UTC timestamp with timezone.
- `idempotency_key`: Deduplication key stable across producer retries.
- `schema_version`: String literal `"1.0"`.
- `data`: Typed JSON payload defined per event type.

---

## 2. Event Types Vocabulary (v1)

| Event Type | Producer | Description |
|---|---|---|
| `argus.resource.discovered.v1` | Discovery Worker | A new AWS resource was ingested into the graph |
| `argus.resource.changed.v1` | Sync Worker | Existing resource attributes or relationships changed |
| `argus.resource.deleted.v1` | Sync Worker | Resource was terminated or removed from AWS |
| `argus.sync.completed.v1` | Sync Worker | Periodic or on-demand reconciliation completed |
| `argus.finding.detected.v1` | Security Engine | Misconfiguration or attack path detected |
| `argus.action.requested.v1` | Action API | Operator requested an infrastructure action plan |
| `argus.action.approved.v1` | Action API | Required approval received for an action |
| `argus.action.executed.v1` | Action Engine | Action completed execution via MCP sandbox |
| `argus.action.failed.v1` | Action Engine | Action failed or triggered automatic rollback |
| `argus.cost.updated.v1` | Cost Worker | Daily or monthly cost aggregation updated |
| `argus.audit.appended.v1` | Audit Service | Audit log entry written and hash chained |
| `argus.worker.heartbeat.v1` | Worker Daemon | Health and liveness heartbeat |

---

## 3. Delivery Guarantees, DLQs, and Poison Pills

1. **At-Least-Once Delivery:** Consumers must be idempotent. The combination of `tenant_id` and `idempotency_key` ensures duplicate messages are discarded safely.
2. **Dead-Letter Queue (DLQ):** Messages failing processing after 5 retry attempts are routed to `argus-events-dlq`.
3. **Poison Pill Isolation:** Malformed payloads that fail JSON Schema validation are logged at `ERROR` level with their payload hash and routed immediately to DLQ without retries.
