from __future__ import annotations

ALLOWED_QUOTES = {"USDT", "USDC"}


class InvalidSymbol(ValueError):
    pass


def extract_quote(symbol: str | None) -> str | None:
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        return None
    for quote in sorted(ALLOWED_QUOTES, key=len, reverse=True):
        if normalized.endswith(quote) and len(normalized) > len(quote):
            return quote
    return None


def is_allowed_quote(symbol: str | None) -> bool:
    return extract_quote(symbol) in ALLOWED_QUOTES


def validate_symbol(
    symbol: str | None,
    *,
    missing_error_code: str = "symbol_empty",
    invalid_error_code: str = "unsupported_quote_asset",
) -> str:
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        raise InvalidSymbol(missing_error_code)
    if not is_allowed_quote(normalized):
        raise InvalidSymbol(invalid_error_code)
    return normalized


def normalize_symbol(
    symbol: str | None,
    *,
    missing_error_code: str = "symbol_empty",
    invalid_error_code: str = "unsupported_quote_asset",
) -> str:
    return validate_symbol(
        symbol,
        missing_error_code=missing_error_code,
        invalid_error_code=invalid_error_code,
    )


def filter_allowed_symbols(symbols: list[str] | tuple[str, ...] | set[str] | None) -> list[str]:
    normalized: list[str] = []
    for symbol in symbols or []:
        candidate = str(symbol or "").strip().upper()
        if not candidate:
            continue
        if is_allowed_quote(candidate):
            normalized.append(candidate)
    return sorted(set(normalized))


def allowed_quotes_list() -> list[str]:
    return sorted(ALLOWED_QUOTES)
