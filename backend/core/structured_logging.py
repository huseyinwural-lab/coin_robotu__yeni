import json
import logging
from datetime import datetime, timezone


class StructuredJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
            "service": "backend-api",
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
        ]:
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


def configure_structured_logging(level: int = logging.INFO):
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    if not root_logger.handlers:
        root_logger.addHandler(logging.StreamHandler())

    formatter = StructuredJsonFormatter()
    for handler in root_logger.handlers:
        handler.setFormatter(formatter)
