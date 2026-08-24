"""FastAPI application — the only place an HTTP error is constructed.

Every non-2xx response goes through one of the handlers below and comes out
in one envelope (skill sections 8.3–8.4). Routes raise domain exceptions;
nothing else in the codebase imports `HTTPException` or builds an error
dict, which is what keeps the error contract consistent as endpoints grow.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from biet_engine import __version__ as engine_version
from biet_engine.exceptions import EngineError

from .constants.errors import ErrorCode
from .exceptions import BietError
from .schemas.scenario import ErrorDetail, ErrorResponse
from .services.resolution import UnresolvedParameterError

log = logging.getLogger("biet")

#: The dev server origins the Vite frontend runs on. Not a wildcard: this is
#: an internal tool, and `*` with credentials is rejected by browsers anyway.
DEV_ORIGINS = (
    "http://localhost:5173", "http://127.0.0.1:5173",
    "http://localhost:4173", "http://127.0.0.1:4173",
)

REQUEST_ID_HEADER = "X-Request-ID"


def _error(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    *,
    field: str | None = None,
    context: dict[str, object] | None = None,
    details: list[ErrorDetail] | None = None,
) -> JSONResponse:
    """The single constructor of an error response."""
    body = ErrorResponse(
        error=ErrorDetail(code=code, message=message, field=field, context=context),
        details=details or [],
        request_id=getattr(request.state, "request_id", "unknown"),
    )
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))


def create_app() -> FastAPI:
    app = FastAPI(
        title="BIET",
        version=engine_version,
        description=(
            "Budget Impact Estimation Tool — indication-specific, multi-country, "
            "ISPOR-aligned budget impact under explicit uncertainty."
        ),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(DEV_ORIGINS),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[REQUEST_ID_HEADER, "Location"],
    )

    @app.middleware("http")
    async def request_id(
        request: Request, call_next: Callable[[Request], Awaitable[JSONResponse]],
    ) -> JSONResponse:
        """One id per request, echoed in the header and in every error body —
        a user reporting a problem quotes it and it resolves to the log line."""
        rid = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex[:16]
        request.state.request_id = rid
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = rid
        return response

    # ------------------------------------------------------------- handlers

    @app.exception_handler(BietError)
    async def _domain(request: Request, exc: BietError) -> JSONResponse:
        log.warning("domain_error code=%s path=%s", exc.code, request.url.path)
        return _error(
            request, exc.status_code, exc.code, exc.message, context=exc.context,
        )

    @app.exception_handler(UnresolvedParameterError)
    async def _unresolved(
        request: Request, exc: UnresolvedParameterError,
    ) -> JSONResponse:
        """A missing input is the user's to fix — a market with no seeded
        price, say — so it is a 422 naming the parameter, not a 500."""
        log.warning("unresolved path=%s param=%s", request.url.path, exc.path)
        return _error(
            request, 422, ErrorCode.UNRESOLVED_PARAMETER, str(exc),
            field=exc.path, context={"country_code": exc.country_code},
        )

    @app.exception_handler(EngineError)
    async def _engine(request: Request, exc: EngineError) -> JSONResponse:
        """Engine errors are almost always bad input, not bugs."""
        log.warning("engine_error code=%s path=%s", exc.code, request.url.path)
        return _error(request, 422, exc.code, str(exc))

    @app.exception_handler(RequestValidationError)
    async def _pydantic(
        request: Request, exc: RequestValidationError,
    ) -> JSONResponse:
        details = [
            ErrorDetail(
                code=ErrorCode.VALIDATION_FAILED, message=e["msg"],
                field=".".join(str(p) for p in e["loc"][1:]),
            )
            for e in exc.errors()
        ]
        return _error(
            request, 422, ErrorCode.VALIDATION_FAILED,
            "Request validation failed.", details=details,
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled path=%s", request.url.path)
        # Never leak an internal message or stack trace to a client.
        return _error(
            request, 500, ErrorCode.INTERNAL, "An internal error occurred.",
        )

    # ------------------------------------------------------------- routes

    from .routes import exports, reference, scenarios

    app.include_router(scenarios.router)
    app.include_router(reference.router)
    app.include_router(exports.router)

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok", "engine_version": engine_version}

    return app


app = create_app()
