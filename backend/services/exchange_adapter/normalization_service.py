ERROR_CODE_TAXONOMY = {
    "insufficient_margin": {"aliases": {"INSUFFICIENT_BALANCE", "INSUFFICIENT_MARGIN", "51008"}, "severity": "high"},
    "invalid_signature": {"aliases": {"INVALID_SIGNATURE", "-1022", "50113"}, "severity": "high"},
    "rate_limit": {"aliases": {"RATE_LIMIT", "429", "TOO_MANY_REQUESTS", "50011"}, "severity": "medium"},
    "order_rejected": {"aliases": {"ORDER_REJECTED", "-2010", "51000"}, "severity": "medium"},
}


def normalize_error_code(raw_code: str | int | None) -> dict:
    candidate = str(raw_code or "").upper().strip()
    for normalized, payload in ERROR_CODE_TAXONOMY.items():
        if candidate in payload["aliases"]:
            return {
                "normalized_error": normalized,
                "severity": payload["severity"],
                "raw_code": candidate,
            }
    return {
        "normalized_error": "unknown",
        "severity": "low",
        "raw_code": candidate,
    }


def normalize_leverage_rule(exchange: str, requested_leverage: int) -> dict:
    exchange_key = str(exchange or "").lower().strip()
    max_leverage = 10 if exchange_key in {"bybit", "okx", "binance"} else 5
    final_leverage = min(max(int(requested_leverage or 1), 1), max_leverage)
    return {
        "exchange": exchange_key,
        "requested_leverage": int(requested_leverage or 1),
        "final_leverage": int(final_leverage),
        "max_leverage": int(max_leverage),
    }
