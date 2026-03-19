import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path


SENSITIVE_FIELD_MARKERS = (
    "token",
    "password",
    "secret",
    "api_key",
    "authorization",
)


def _mask_sensitive_value(value: object) -> object:
    text = str(value)
    if not text:
        return value
    if len(text) <= 8:
        return "*" * len(text)
    return f"{text[:3]}***{text[-3:]}"


def _sanitize_field(name: str, value: object) -> object:
    lowered = name.lower()
    if any(marker in lowered for marker in SENSITIVE_FIELD_MARKERS):
        return _mask_sensitive_value(value)
    if lowered in {"user_id", "actor_user_id"} and value:
        return _mask_sensitive_value(value)
    return value


class StructuredJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "component": record.name,
            "event_name": getattr(record, "event_name", record.getMessage()),
            "message": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
            "service": os.environ.get("OBSERVABILITY_SERVICE_NAME", "backend-api"),
            "environment": os.environ.get("APP_ENVIRONMENT", "dev"),
        }

        for key in [
            "request_id",
            "correlation_id",
            "action",
            "entity_type",
            "entity_id",
            "actor_user_id",
            "actor_role",
            "event_type",
            "session_id",
            "path",
            "method",
            "status_code",
            "duration_ms",
            "user_id",
            "exchange",
            "market_type",
            "environment",
            "reason_code",
            "connection_id",
            "new_health",
            "old_health",
        ]:
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = _sanitize_field(key, value)

        for key, value in record.__dict__.items():
            if key in payload:
                continue
            if key.startswith("_"):
                continue
            if key in {
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "exc_info",
                "exc_text",
                "stack_info",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
            }:
                continue
            payload[key] = _sanitize_field(key, value)

        if record.exc_info:
            exc_type = record.exc_info[0].__name__ if record.exc_info[0] else "Exception"
            exc_message = str(record.exc_info[1])[:500]
            payload["exception"] = {"type": exc_type, "message": exc_message}

        return json.dumps(payload, ensure_ascii=False)


def configure_structured_logging(level: int = logging.INFO):
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    log_file_path = Path(
        os.environ.get("OBSERVABILITY_LOG_FILE")
        or (Path(__file__).resolve().parents[1] / "logs" / "backend_observability.log")
    )
    log_file_path.parent.mkdir(parents=True, exist_ok=True)

    root_logger.handlers.clear()

    stdout_handler = logging.StreamHandler()
    file_handler = logging.FileHandler(log_file_path, encoding="utf-8")

    root_logger.addHandler(stdout_handler)
    root_logger.addHandler(file_handler)

    formatter = StructuredJsonFormatter()
    for handler in root_logger.handlers:
        handler.setFormatter(formatter)
