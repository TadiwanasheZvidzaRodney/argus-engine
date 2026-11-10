import { PROBLEM_CONTENT_TYPE, isProblemDetails, type ProblemDetails } from "@argus/contracts";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

export class ApiError extends Error {
  readonly status: number;
  readonly problem: ProblemDetails;

  constructor(problem: ProblemDetails) {
    super(problem.detail ?? problem.title);
    this.name = "ApiError";
    this.status = problem.status;
    this.problem = problem;
  }
}

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  idempotencyKey?: string;
  timeoutMs?: number;
}

function correlationId(): string {
  const cryptoApi = globalThis.crypto;
  if (cryptoApi && "randomUUID" in cryptoApi) return `req_web_${cryptoApi.randomUUID()}`;
  return `req_web_${Date.now().toString(36)}`;
}

async function readProblem(response: Response, requestId: string): Promise<ProblemDetails> {
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes(PROBLEM_CONTENT_TYPE)) {
    try {
      const parsed: unknown = await response.json();
      if (isProblemDetails(parsed)) return parsed;
    } catch {
      // Fall through to the synthetic problem below.
    }
  }
  return {
    type: "https://errors.argus.example.com/client-error",
    title: response.statusText || "Request failed",
    status: response.status,
    detail: `The API returned ${response.status}.`,
    request_id: requestId,
  };
}

/**
 * Fetch wrapper for the Argus API.
 *
 * Always sends a correlation id, parses RFC 9457 problems into `ApiError`, and
 * never caches topology reads. Mutations require an explicit idempotency key.
 */
export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, idempotencyKey, timeoutMs = 10_000, headers, ...rest } = options;
  const method = (rest.method ?? (body === undefined ? "GET" : "POST")).toUpperCase();
  const requestId = correlationId();

  const requestHeaders: Record<string, string> = {
    accept: "application/json",
    "x-request-id": requestId,
    ...(headers as Record<string, string> | undefined),
  };
  if (body !== undefined) requestHeaders["content-type"] = "application/json";
  if (idempotencyKey) requestHeaders["idempotency-key"] = idempotencyKey;
  if (method !== "GET" && method !== "HEAD" && !idempotencyKey) {
    throw new ApiError({
      type: "https://errors.argus.example.com/idempotency-key-required",
      title: "Idempotency-Key Required",
      status: 400,
      detail: "Mutating requests must supply an idempotency key.",
      request_id: requestId,
    });
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...rest,
      method,
      headers: requestHeaders,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
      cache: "no-store",
    });
  } catch (error) {
    throw new ApiError({
      type: "https://errors.argus.example.com/network-error",
      title: "API Unreachable",
      status: 503,
      detail: error instanceof Error ? error.message : "The API could not be reached.",
      request_id: requestId,
    });
  } finally {
    clearTimeout(timer);
  }

  if (!response.ok) {
    throw new ApiError(await readProblem(response, requestId));
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
