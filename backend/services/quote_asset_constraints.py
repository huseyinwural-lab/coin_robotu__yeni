from __future__ import annotations

from core.policy.quote_policy import allowed_quotes_list

INVALID_QUOTE_ASSET_ERROR_CODE = "INVALID_QUOTE_ASSET"

_INVALID_QUOTE_ALIASES = {
    "invalid_quote_asset",
    "unsupported_quote_asset",
    "quote_asset_mismatch",
    INVALID_QUOTE_ASSET_ERROR_CODE,
}


def allowed_quote_assets() -> list[str]:
    return [str(item).upper() for item in allowed_quotes_list()]


def invalid_quote_asset_message() -> str:
    quotes = allowed_quote_assets()
    if len(quotes) >= 2:
        return f"Quote asset must be {quotes[0]} or {quotes[1]}"
    if len(quotes) == 1:
        return f"Quote asset must be {quotes[0]}"
    return "Quote asset is not allowed"


def is_invalid_quote_asset_code(code: str | None) -> bool:
    normalized = str(code or "").strip()
    if not normalized:
        return False
    return normalized.lower() in {item.lower() for item in _INVALID_QUOTE_ALIASES}


def normalize_reason_code(code: str | None) -> str:
    normalized = str(code or "").strip()
    if not normalized:
        return "UNKNOWN"
    if is_invalid_quote_asset_code(normalized):
        return INVALID_QUOTE_ASSET_ERROR_CODE
    return normalized.upper()


def build_invalid_quote_asset_detail(symbol: str | None) -> dict:
    return {
        "error_code": INVALID_QUOTE_ASSET_ERROR_CODE,
        "message": invalid_quote_asset_message(),
        "state_snapshot": {
            "symbol": str(symbol or "").strip().upper(),
            "allowed_quote_assets": allowed_quote_assets(),
        },
    }
