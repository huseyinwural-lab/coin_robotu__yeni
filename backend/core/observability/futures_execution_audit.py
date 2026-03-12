from datetime import datetime, timezone


def build_futures_execution_audit_event(*, action: str, symbol: str, status: str, details: dict) -> dict:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "symbol": symbol,
        "status": status,
        "details": details,
    }
