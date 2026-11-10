/**
 * Wire contracts for Argus Engine.
 *
 * Source of truth: packages/python/argus-core/src/argus_core/events.py
 * Regenerate JSON Schemas with `pnpm contracts`; this file is reviewed by hand
 * against the schema diff (CI runs `pnpm contracts:check`).
 */

export const API_VERSION = "v1" as const;
export const PROBLEM_CONTENT_TYPE = "application/problem+json" as const;

export type EventType =
  | "argus.resource.discovered.v1"
  | "argus.resource.changed.v1"
  | "argus.resource.deleted.v1"
  | "argus.sync.completed.v1"
  | "argus.finding.detected.v1"
  | "argus.action.requested.v1"
  | "argus.action.approved.v1"
  | "argus.action.executed.v1"
  | "argus.action.failed.v1"
  | "argus.cost.updated.v1"
  | "argus.audit.appended.v1"
  | "argus.worker.heartbeat.v1";

export type ActorType = "user" | "system" | "service";

/** CloudEvents-compatible internal event envelope. */
export interface EventEnvelope<TData = Record<string, unknown>> {
  id: string;
  type: EventType;
  source: string;
  tenant_id: string;
  account_id?: string | null;
  region?: string | null;
  subject?: string | null;
  time: string;
  idempotency_key: string;
  trace_id?: string | null;
  schema_version: "1.0";
  data: TData;
}

/** Append-only, hash-chained audit record. */
export interface AuditEvent {
  id: string;
  tenant_id: string;
  actor_type: ActorType;
  actor_id?: string | null;
  action: string;
  resource_type?: string | null;
  resource_id?: string | null;
  request_id?: string | null;
  trace_id?: string | null;
  source_ip?: string | null;
  user_agent?: string | null;
  before_hash?: string | null;
  after_hash?: string | null;
  metadata: Record<string, unknown>;
  prev_hash?: string | null;
  hash: string;
  created_at: string;
}

export interface FieldError {
  pointer: string;
  code: string;
  detail: string;
}

/** RFC 9457 problem document, as returned by every failing request. */
export interface ProblemDetails {
  type: string;
  title: string;
  status: number;
  detail?: string | null;
  instance?: string | null;
  trace_id?: string | null;
  request_id?: string | null;
  errors?: FieldError[];
}

/** Cursor-paginated collection envelope. */
export interface Page<T> {
  items: T[];
  next_cursor: string | null;
  has_more: boolean;
}

export interface ServiceMeta {
  service: string;
  version: string;
  commit: string;
  env: string;
  api_version: typeof API_VERSION;
  capabilities: string[];
  server_time: string;
}

export function isProblemDetails(value: unknown): value is ProblemDetails {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Partial<ProblemDetails>;
  return typeof candidate.type === "string" && typeof candidate.status === "number";
}
