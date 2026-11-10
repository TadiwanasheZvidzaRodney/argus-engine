"""Translate domain and framework exceptions into RFC 9457 responses."""

from __future__ import annotations

from typing import Any

from argus_core.errors import (
    PROBLEM_BASE_URI,
    PROBLEM_CONTENT_TYPE,
    ArgusError,
    FieldError,
    Problem,
)
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

_ARROW_POINTER = "/"


def _problem_response(
    problem: Problem,
    *,
    request: Request,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    state = request.scope.get("state") or {}
    enriched = problem.model_copy(
        update={
            "instance": request.url.path,
            "request_id": state.get("request_id"),
            "trace_id": state.get("trace_id"),
        }
    )
    return JSONResponse(
        status_code=enriched.status,
        content=enriched.model_dump(mode="json", exclude_none=True),
        media_type=PROBLEM_CONTENT_TYPE,
        headers=headers,
    )


def _pointer(loc: tuple[str | int, ...]) -> str:
    parts = [str(item).replace("~", "~0").replace("/", "~1") for item in loc if item != "body"]
    return _ARROW_POINTER + _ARROW_POINTER.join(parts) if parts else _ARROW_POINTER


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ArgusError)
    async def handle_argus_error(request: Request, exc: ArgusError) -> JSONResponse:
        return _problem_response(exc.to_problem(), request=request, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = [
            FieldError(
                pointer=_pointer(tuple(item.get("loc", ()))),
                code=str(item.get("type", "invalid")),
                detail=str(item.get("msg", "invalid value")),
            )
            for item in exc.errors()
        ]
        problem = Problem(
            type=f"{PROBLEM_BASE_URI}/validation-failed",
            title="Validation Failed",
            status=422,
            detail="One or more fields are invalid.",
            errors=errors,
        )
        return _problem_response(problem, request=request)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        codes: dict[int, str] = {
            400: "bad-request",
            401: "unauthorized",
            403: "forbidden",
            404: "not-found",
            405: "method-not-allowed",
            409: "conflict",
            413: "payload-too-large",
            415: "unsupported-media-type",
            429: "rate-limited",
        }
        problem = Problem(
            type=f"{PROBLEM_BASE_URI}/{codes.get(exc.status_code, 'http-error')}",
            title=str(exc.detail) if exc.status_code < 500 else "Server Error",
            status=exc.status_code,
            detail=str(exc.detail),
        )
        return _problem_response(problem, request=request)

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        from argus_core.logging import get_logger

        get_logger("argus_api.errors").exception("unhandled exception", exc_info=exc)
        problem = Problem(
            type=f"{PROBLEM_BASE_URI}/internal-error",
            title="Internal Server Error",
            status=500,
            detail="An unexpected error occurred. Quote the request id when contacting support.",
        )
        return _problem_response(problem, request=request)


def problem_payload(problem: Problem) -> dict[str, Any]:
    """Expose the wire shape for tests and OpenAPI components."""
    return problem.model_dump(mode="json", exclude_none=True)
