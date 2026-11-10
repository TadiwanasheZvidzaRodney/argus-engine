import { describe, expect, it } from "vitest";
import Ajv from "ajv";

import { isProblemDetails, type EventEnvelope, type ProblemDetails } from "../src/index";
import eventSchema from "../schemas/event-envelope.v1.json";
import auditSchema from "../schemas/audit-event.v1.json";

const envelope: EventEnvelope<{ change: string }> = {
  id: "evt_01M72X6SCN01VTGZVS0Z5KKYC0",
  type: "argus.resource.changed.v1",
  source: "argus.discovery",
  tenant_id: "tnt_0190c3a1-0000-7000-8000-000000000000",
  account_id: "123456789012",
  region: "us-east-1",
  subject: "arn:aws:ec2:us-east-1:123456789012:instance/i-0abc",
  time: "2026-11-10T12:00:00Z",
  idempotency_key: "aws-config:123456789012:us-east-1:v3",
  trace_id: "4bf92f3577b34da6a3ce929d0e0e4736",
  schema_version: "1.0",
  data: { change: "MODIFIED" },
};

const audit = {
  id: "0190c3a1-0000-7000-8000-000000000001",
  tenant_id: "tnt_0190c3a1-0000-7000-8000-000000000000",
  actor_type: "user",
  actor_id: "user_123",
  action: "tenant.connected",
  resource_type: "aws_account",
  resource_id: "123456789012",
  metadata: {},
  prev_hash: null,
  hash: "0".repeat(64),
  created_at: "2026-11-10T12:00:00Z",
};

describe("event envelope v1", () => {
  it("accepts the documented example", () => {
    const validate = new Ajv({ strict: false }).compile(eventSchema);
    expect(validate.errors).toBeNull();
    expect(validate(envelope)).toBe(true);
  });

  it("rejects a tenant id that is not tnt_ + uuid7", () => {
    const validate = new Ajv({ strict: false }).compile(eventSchema);
    expect(validate({ ...envelope, tenant_id: "8c1d0b0e-0000-7000-8000-000000000000" })).toBe(
      false,
    );
  });

  it("rejects an unknown event type", () => {
    const validate = new Ajv({ strict: false }).compile(eventSchema);
    expect(validate({ ...envelope, type: "argus.resource.exploded.v1" })).toBe(false);
  });

  it("rejects extra top-level fields", () => {
    const validate = new Ajv({ strict: false }).compile(eventSchema);
    expect(validate({ ...envelope, sneaky: true })).toBe(false);
  });
});

describe("audit event v1", () => {
  it("accepts a sealed record", () => {
    const validate = new Ajv({ strict: false }).compile(auditSchema);
    expect(validate.errors).toBeNull();
    expect(validate(audit)).toBe(true);
  });

  it("requires a sha256 hash", () => {
    const validate = new Ajv({ strict: false }).compile(auditSchema);
    expect(validate({ ...audit, hash: "not-a-hash" })).toBe(false);
  });
});

describe("problem details", () => {
  it("narrows RFC 9457 payloads", () => {
    const problem: ProblemDetails = {
      type: "https://errors.argus.example.com/not-found",
      title: "Not Found",
      status: 404,
      detail: "No such resource.",
      request_id: "req_1",
      errors: [],
    };
    expect(isProblemDetails(problem)).toBe(true);
    expect(isProblemDetails({ title: "nope" })).toBe(false);
    expect(isProblemDetails(null)).toBe(false);
  });
});
