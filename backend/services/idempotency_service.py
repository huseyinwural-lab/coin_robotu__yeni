from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


def _clean_string(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split()).lower()


def _normalize_number(value: Any) -> str:
    if value is None:
        return "0"
    try:
        return format(float(value), ".8f")
    except (TypeError, ValueError):
        return "0"


def _normalize_timestamp_window(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, (int, float)):
        dt = datetime.fromtimestamp(float(value), tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%MZ")

    text = str(value).strip()
    if not text:
        return ""

    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return _clean_string(text)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%MZ")


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def build_execution_idempotency_key(*, user_id: str, payload: dict[str, Any], normalized_payload: dict[str, Any] | None = None) -> str:
    normalized_payload = normalized_payload or {}

    source_event_id = (
        payload.get("source_event_id")
        or (payload.get("scanner_signal_snapshot") or {}).get("signal_id")
        or payload.get("source_ref_id")
        or ""
    )
    timestamp_window = payload.get("timestamp_window") or payload.get("normalized_timestamp_window")
    if not timestamp_window:
        timestamp_window = payload.get("timestamp") or (payload.get("scanner_signal_snapshot") or {}).get("timestamp")

    quantity = (
        normalized_payload.get("size")
        if normalized_payload.get("size") is not None
        else payload.get("size")
        if payload.get("size") is not None
        else normalized_payload.get("position_size_value")
        if normalized_payload.get("position_size_value") is not None
        else payload.get("position_size_value")
    )

    canonical_payload = {
        "user_id": _clean_string(user_id),
        "symbol": _clean_string(normalized_payload.get("symbol") or payload.get("symbol")),
        "side": _clean_string(normalized_payload.get("side") or payload.get("side")),
        "order_type": _clean_string(normalized_payload.get("order_type") or payload.get("order_type")),
        "quantity": _normalize_number(quantity),
        "strategy_source_id": _clean_string(
            normalized_payload.get("strategy_binding")
            or payload.get("strategy_binding")
            or payload.get("strategy")
            or payload.get("source_type")
        ),
        "source_event_id": _clean_string(source_event_id),
        "timestamp_window": _normalize_timestamp_window(timestamp_window),
        "intent_type": _clean_string(normalized_payload.get("intent_type") or payload.get("intent_type") or "OPEN_POSITION"),
        "market_type": _clean_string(normalized_payload.get("market_type") or payload.get("market_type") or "spot"),
    }

    canonical_json = _canonical_json(canonical_payload)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
