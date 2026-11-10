from __future__ import annotations

from argus_core.errors import (
    FieldError,
    IdempotencyConflict,
    NotFound,
    Problem,
    RateLimited,
    UnprocessableEntity,
)

SECRET = "test-secret"


def test_not_found_renders_problem_document() -> None:
    problem = NotFound("Account not connected.").to_problem()
    assert isinstance(problem, Problem)
    assert problem.status == 404
    assert problem.type == "https://errors.argus.example.com/not-found"
    assert problem.detail == "Account not connected."
    assert problem.model_dump()["title"] == "Not Found"


def test_validation_problem_carries_field_errors() -> None:
    error = UnprocessableEntity(
        errors=[
            FieldError(pointer="/account_id", code="invalid-format", detail="must be 12 digits")
        ]
    )
    problem = error.to_problem()
    assert problem.status == 422
    assert problem.errors[0].pointer == "/account_id"


def test_rate_limit_sets_retry_after() -> None:
    limiter = RateLimited(retry_after_seconds=7)
    assert limiter.headers == {"Retry-After": "7"}


def test_idempotency_conflict_has_stable_code() -> None:
    assert IdempotencyConflict().to_problem().type.endswith("/idempotency-key-reuse")
