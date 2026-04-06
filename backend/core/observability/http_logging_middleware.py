from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware

from core.observability.request_context import clear_request_context, set_request_context
from services.observability_service import record_http_observation

logger = logging.getLogger("http.access")


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
        except Exception:
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
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
