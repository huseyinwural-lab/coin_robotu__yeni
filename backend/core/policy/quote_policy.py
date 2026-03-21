from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path


def _trading_config_path() -> Path:
    override_path = os.environ.get("TRADING_CONFIG_PATH")
    if override_path:
        return Path(override_path)
    return Path(__file__).resolve().parents[3] / "config" / "trading.json"


@lru_cache(maxsize=1)
def _load_allowed_quotes() -> tuple[str, ...]:
    config_path = _trading_config_path()
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    quote_assets = payload.get("allowed_quote_assets")
    if not isinstance(quote_assets, list):
        raise ValueError("trading_config_allowed_quote_assets_required")
    normalized: list[str] = []
    seen: set[str] = set()
    for item in quote_assets:
        candidate = str(item or "").strip().upper()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        normalized.append(candidate)
    if not normalized:
        raise ValueError("trading_config_allowed_quote_assets_empty")
    return tuple(normalized)


ALLOWED_QUOTES_SEQUENCE = _load_allowed_quotes()
ALLOWED_QUOTES = set(ALLOWED_QUOTES_SEQUENCE)


class InvalidSymbol(ValueError):
    pass


def extract_quote(symbol: str | None) -> str | None:
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        return None
    for quote in sorted(ALLOWED_QUOTES_SEQUENCE, key=len, reverse=True):
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
    return list(ALLOWED_QUOTES_SEQUENCE)
