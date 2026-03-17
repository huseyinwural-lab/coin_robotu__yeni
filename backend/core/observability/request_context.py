from __future__ import annotations

from contextvars import ContextVar


request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")
session_id_ctx: ContextVar[str] = ContextVar("session_id", default="")
request_path_ctx: ContextVar[str] = ContextVar("request_path", default="")
request_method_ctx: ContextVar[str] = ContextVar("request_method", default="")


def set_request_context(*, request_id: str, session_id: str, path: str, method: str):
    request_id_ctx.set(request_id)
    session_id_ctx.set(session_id)
    request_path_ctx.set(path)
    request_method_ctx.set(method)


def clear_request_context():
    request_id_ctx.set("")
    session_id_ctx.set("")
    request_path_ctx.set("")
    request_method_ctx.set("")


def get_request_context() -> dict:
    return {
        "request_id": request_id_ctx.get("") or None,
        "session_id": session_id_ctx.get("") or None,
        "route": request_path_ctx.get("") or None,
        "method": request_method_ctx.get("") or None,
    }
