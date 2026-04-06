from __future__ import annotations

import logging
import time
import uuid

from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError, TimeoutError as SQLAlchemyTimeoutError
from starlette.middleware.base import BaseHTTPMiddleware

from core.observability.request_context import clear_request_context, set_request_context
from services.observability_service import record_http_observation

logger = logging.getLogger("http.access")

RETRYABLE_DB_ERROR_HINTS = (
    "pooler timeout",
    "timeout expired",
    "queuepool limit",
    "too many connections",
    "connection pool",
    "could not obtain a connection",
    "ssl connection has been closed unexpectedly",
    "server closed the connection unexpectedly",
    "connection to server at",
    "could not connect to server",
    "connection refused",
    "connection reset by peer",
    "broken pipe",
)


def _is_retryable_db_error(exc: Exception) -> bool:
    if isinstance(exc, SQLAlchemyTimeoutError):
        return True
    if isinstance(exc, OperationalError):
        return True
    normalized = str(exc or "").strip().lower()
    return any(hint in normalized for hint in RETRYABLE_DB_ERROR_HINTS)


def _db_retryable_response(request_id: str) -> JSONResponse:
    payload = {
        "detail": "SERVICE_UNAVAILABLE",
        "code": "DB_POOL_TIMEOUT",
        "retryable": True,
        "error_class": "infra_error",
        "trace_id": request_id,
    }
    return JSONResponse(status_code=503, content=payload, headers={"X-Request-ID": request_id})


class RequestObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        started = time.perf_counter()
        request_id = (request.headers.get("X-Request-ID") or "").strip() or str(uuid.uuid4())
        session_id = (request.headers.get("X-Session-ID") or "").strip()

        set_request_context(
            request_id=request_id,
            session_id=session_id,
            path=request.url.path,
            method=request.method,
        )
        request.state.request_id = request_id

        try:
            response = await call_next(request)
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            response.headers["X-Request-ID"] = request_id
            logger.info(
                "http_request_completed",
                extra={
                    "request_id": request_id,
                    "correlation_id": request_id,
                    "event_type": "http_request",
                    "path": request.url.path,
                    "method": request.method,
                    "status_code": response.status_code,
                    "duration_ms": elapsed_ms,
                    "session_id": session_id or None,
                },
            )
            record_http_observation(
                path=request.url.path,
                method=request.method,
                status_code=response.status_code,
                duration_ms=elapsed_ms,
            )
            return response
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            if _is_retryable_db_error(exc):
                logger.error(
                    "http_request_db_retryable_failure",
                    extra={
                        "request_id": request_id,
                        "correlation_id": request_id,
                        "event_type": "http_request",
                        "path": request.url.path,
                        "method": request.method,
                        "duration_ms": elapsed_ms,
                        "status_code": 503,
                        "session_id": session_id or None,
                    },
                )
                record_http_observation(
                    path=request.url.path,
                    method=request.method,
                    status_code=503,
                    duration_ms=elapsed_ms,
                )
                return _db_retryable_response(request_id)

            logger.exception(
                "http_request_failed",
                extra={
                    "request_id": request_id,
                    "correlation_id": request_id,
                    "event_type": "http_request",
                    "path": request.url.path,
                    "method": request.method,
                    "duration_ms": elapsed_ms,
                    "session_id": session_id or None,
                },
            )
            record_http_observation(
                path=request.url.path,
                method=request.method,
                status_code=500,
                duration_ms=elapsed_ms,
            )
            raise
        finally:
            clear_request_context()
