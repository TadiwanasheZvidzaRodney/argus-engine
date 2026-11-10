"""RFC 9457 problem details shared by the API and WebSocket gateway."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

PROBLEM_CONTENT_TYPE = "application/problem+json"
PROBLEM_BASE_URI = "https://errors.argus.example.com"


class FieldError(BaseModel):
    """A single invalid input, addressed by JSON Pointer."""

    model_config = ConfigDict(frozen=True)

    pointer: str = Field(description="JSON Pointer to the offending field, e.g. /targets/0")
    code: str = Field(description="Stable machine-readable reason code")
    detail: str


class Problem(BaseModel):
    """RFC 9457 problem document, extended with trace correlation."""

    model_config = ConfigDict(frozen=True)

    type: str = Field(default=f"{PROBLEM_BASE_URI}/internal-error")
    title: str = "Internal Server Error"
    status: int = 500
    detail: str | None = None
    instance: str | None = None
    trace_id: str | None = None
    request_id: str | None = None
    errors: list[FieldError] = Field(default_factory=list)


class ArgusError(Exception):
    """Base class for errors that map onto a problem document.

    Services raise these instead of ``HTTPException`` so that the status code,
    the stable ``code``, and the client-facing detail are defined once, in the
    domain, and rendered consistently at the edge.
    """

    status_code: int = 500
    code: str = "internal-error"
    title: str = "Internal Server Error"
    detail: str | None = "An unexpected error occurred."

    def __init__(
        self,
        detail: str | None = None,
        *,
        code: str | None = None,
        errors: list[FieldError] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.detail = detail or self.detail
        self.code = code or self.code
        self.errors = errors or []
        self.headers = headers or {}
        super().__init__(self.detail)

    def to_problem(self) -> Problem:
        return Problem(
            type=f"{PROBLEM_BASE_URI}/{self.code}",
            title=self.title,
            status=self.status_code,
            detail=self.detail,
            errors=self.errors,
        )


class BadRequest(ArgusError):
    status_code = 400
    code = "bad-request"
    title = "Bad Request"


class Unauthorized(ArgusError):
    status_code = 401
    code = "unauthorized"
    title = "Unauthorized"
    detail = "Authentication is required."


class Forbidden(ArgusError):
    status_code = 403
    code = "forbidden"
    title = "Forbidden"
    detail = "You do not have permission to perform this action."


class NotFound(ArgusError):
    status_code = 404
    code = "not-found"
    title = "Not Found"
    detail = "The requested resource does not exist."


class Conflict(ArgusError):
    status_code = 409
    code = "conflict"
    title = "Conflict"


class IdempotencyConflict(Conflict):
    code = "idempotency-key-reuse"
    title = "Idempotency Key Reused"
    detail = "The Idempotency-Key was already used with a different request payload."


class IdempotencyInProgress(Conflict):
    code = "idempotency-request-in-flight"
    title = "Request Already In Progress"
    detail = "A request with this Idempotency-Key is still being processed."


class PayloadTooLarge(ArgusError):
    status_code = 413
    code = "payload-too-large"
    title = "Payload Too Large"


class UnprocessableEntity(ArgusError):
    status_code = 422
    code = "validation-failed"
    title = "Validation Failed"
    detail = "One or more fields are invalid."

    def __init__(
        self, detail: str | None = None, *, errors: list[FieldError] | None = None, **kwargs: Any
    ) -> None:
        super().__init__(detail, errors=errors, **kwargs)


class RateLimited(ArgusError):
    status_code = 429
    code = "rate-limited"
    title = "Too Many Requests"
    detail = "Request rate limit exceeded."

    def __init__(self, retry_after_seconds: int = 1, **kwargs: Any) -> None:
        super().__init__(headers={"Retry-After": str(retry_after_seconds)}, **kwargs)


class ServiceUnavailable(ArgusError):
    status_code = 503
    code = "service-unavailable"
    title = "Service Unavailable"
    detail = "A dependency is unavailable. Retry with backoff."
