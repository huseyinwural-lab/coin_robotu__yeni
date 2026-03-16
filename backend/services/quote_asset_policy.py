from __future__ import annotations

ALLOWED_QUOTE_ASSETS = {"USDT", "USDC"}


def extract_quote_asset(symbol: str | None) -> str | None:
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        return None
    for quote_asset in sorted(ALLOWED_QUOTE_ASSETS, key=len, reverse=True):
        if normalized.endswith(quote_asset) and len(normalized) > len(quote_asset):
            return quote_asset
    return None


def is_allowed_quote_symbol(symbol: str | None) -> bool:
    return extract_quote_asset(symbol) in ALLOWED_QUOTE_ASSETS


def normalize_quote_symbol(
    symbol: str | None,
    *,
    field_name: str = "symbol",
    missing_error_code: str | None = None,
    invalid_error_code: str | None = None,
) -> str:
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        raise ValueError(missing_error_code or f"{field_name}_required")
    if not is_allowed_quote_symbol(normalized):
        raise ValueError(invalid_error_code or "invalid_quote_asset")
    return normalized


def filter_allowed_quote_symbols(symbols: list[str] | tuple[str, ...] | set[str]) -> list[str]:
    normalized = []
    for symbol in symbols or []:
        candidate = str(symbol or "").strip().upper()
        if not candidate:
            continue
        if is_allowed_quote_symbol(candidate):
            normalized.append(candidate)
    return sorted(set(normalized))


def allowed_quote_assets_list() -> list[str]:
    return sorted(ALLOWED_QUOTE_ASSETS)
