from __future__ import annotations

from core.policy.quote_policy import (
    ALLOWED_QUOTES,
    InvalidSymbol,
    allowed_quotes_list,
    extract_quote,
    filter_allowed_symbols,
    is_allowed_quote,
    normalize_symbol,
)

ALLOWED_QUOTE_ASSETS = set(ALLOWED_QUOTES)


def extract_quote_asset(symbol: str | None) -> str | None:
    return extract_quote(symbol)


def is_allowed_quote_symbol(symbol: str | None) -> bool:
    return is_allowed_quote(symbol)


def normalize_quote_symbol(
    symbol: str | None,
    *,
    field_name: str = "symbol",
    missing_error_code: str | None = None,
    invalid_error_code: str | None = None,
) -> str:
    try:
        return normalize_symbol(
            symbol,
            missing_error_code=missing_error_code or f"{field_name}_required",
            invalid_error_code=invalid_error_code or "invalid_quote_asset",
        )
    except InvalidSymbol as exc:
        raise ValueError(str(exc)) from exc


def filter_allowed_quote_symbols(symbols: list[str] | tuple[str, ...] | set[str]) -> list[str]:
    return filter_allowed_symbols(symbols)


def allowed_quote_assets_list() -> list[str]:
    return allowed_quotes_list()
