from __future__ import annotations

from core.policy.quote_policy import ALLOWED_QUOTES

INVALID_QUOTE_ASSET_ERROR_CODE = "INVALID_QUOTE_ASSET"
INVALID_QUOTE_ASSET_MESSAGE = "Quote asset must be USDT or USDC"

_INVALID_QUOTE_ALIASES = {
    "invalid_quote_asset",
    "unsupported_quote_asset",
    "quote_asset_mismatch",
    INVALID_QUOTE_ASSET_ERROR_CODE,
}


def allowed_quote_assets() -> list[str]:
    return sorted({str(item).upper() for item in ALLOWED_QUOTES})


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
        "message": INVALID_QUOTE_ASSET_MESSAGE,
        "state_snapshot": {
            "symbol": str(symbol or "").strip().upper(),
            "allowed_quote_assets": allowed_quote_assets(),
        },
    }
