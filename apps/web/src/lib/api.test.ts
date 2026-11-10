import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiFetch } from "@/lib/api";

interface FakeResponseInit {
  status?: number;
  contentType?: string;
  body?: unknown;
}

function fakeResponse({
  status = 200,
  contentType = "application/json",
  body = {},
}: FakeResponseInit) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 404 ? "Not Found" : "",
    headers: new Headers({ "content-type": contentType }),
    json: async () => body,
  } as unknown as Response;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("apiFetch", () => {
  it("sends correlation and accept headers and returns JSON", async () => {
    const fetchMock = vi.fn().mockResolvedValue(fakeResponse({ body: { api_version: "v1" } }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await apiFetch<{ api_version: string }>("/api/v1/meta");

    expect(result.api_version).toBe("v1");
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Record<string, string>;
    expect(headers["x-request-id"]).toMatch(/^req_web_/);
    expect(headers.accept).toBe("application/json");
    expect(init.method).toBe("GET");
  });

  it("requires an idempotency key for mutations", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiFetch("/api/v1/actions", { method: "POST", body: {} })).rejects.toMatchObject({
      status: 400,
      problem: expect.objectContaining({
        type: expect.stringContaining("idempotency-key-required"),
      }),
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("forwards the idempotency key and body", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(fakeResponse({ status: 201, body: { id: "act_1" } }));
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch("/api/v1/actions", {
      method: "POST",
      body: { action: "stop-instance" },
      idempotencyKey: "plan-12345678",
    });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect((init.headers as Record<string, string>)["idempotency-key"]).toBe("plan-12345678");
    expect(init.body).toBe(JSON.stringify({ action: "stop-instance" }));
  });

  it("maps RFC 9457 problems onto ApiError", async () => {
    const problem = {
      type: "https://errors.argus.example.com/not-found",
      title: "Not Found",
      status: 404,
      detail: "No such account.",
      request_id: "req_1",
      errors: [],
    };
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          fakeResponse({ status: 404, contentType: "application/problem+json", body: problem }),
        ),
    );

    await expect(apiFetch("/api/v1/accounts/nope")).rejects.toBeInstanceOf(ApiError);
    await expect(apiFetch("/api/v1/accounts/nope")).rejects.toMatchObject({
      status: 404,
      message: "No such account.",
    });
  });

  it("synthesises a problem for non-JSON failures", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(fakeResponse({ status: 502, contentType: "text/html", body: "" })),
    );

    await expect(apiFetch("/api/v1/meta")).rejects.toMatchObject({
      status: 502,
      problem: expect.objectContaining({ type: expect.stringContaining("client-error") }),
    });
  });

  it("reports unreachable APIs as 503 instead of throwing a transport error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("ECONNREFUSED")));

    await expect(apiFetch("/api/v1/meta")).rejects.toMatchObject({
      status: 503,
      problem: expect.objectContaining({ type: expect.stringContaining("network-error") }),
    });
  });
});
