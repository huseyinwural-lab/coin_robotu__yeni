import csv
import io
import json
import os
from datetime import datetime, timezone

import requests
from sqlalchemy.orm import Session

from core.users.user_exchange_connector import decrypt_exchange_secret, encrypt_exchange_secret
from db import redis_client
from models import ExternalProviderCredential, SymbolSelectionWatchlist
from services.indicator_screener.market_data_provider import BinanceMarketDataProvider, MarketDataProviderError


ALLOWED_SOURCES = {"crypto", "stock"}
ALLOWED_MODES = {"all_market_symbols", "top_volume", "manual_selection"}
MODE_ALIASES = {
    "all_exchange": "all_market_symbols",
    "top_active_50": "top_volume",
    "top_active_100": "top_volume",
    "custom_list": "manual_selection",
    "bot_scope": "manual_selection",
}
ALPHA_PROVIDER_KEY = "alpha_vantage"


def _safe_float(value, fallback: float | None = None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _normalize_source(source: str | None) -> str:
    candidate = str(source or "crypto").strip().lower()
    return candidate if candidate in ALLOWED_SOURCES else "crypto"


def _normalize_mode(mode: str | None) -> str:
    candidate = str(mode or "all_market_symbols").strip().lower()
    candidate = MODE_ALIASES.get(candidate, candidate)
    return candidate if candidate in ALLOWED_MODES else "all_market_symbols"


def _normalize_symbol_list(symbols: list[str] | str | None) -> list[str]:
    if isinstance(symbols, list):
        raw = symbols
    elif isinstance(symbols, str):
        raw = symbols.split(",")
    else:
        raw = []
    normalized = [str(item).strip().upper() for item in raw if str(item).strip()]
    return list(dict.fromkeys(normalized))


def _cache_get(key: str):
    raw = redis_client.get(key)
    if not raw:
        return None
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw) if isinstance(raw, str) else None
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def _cache_set(key: str, payload: dict, ttl_seconds: int):
    redis_client.set(key, json.dumps(payload))
    if hasattr(redis_client, "expire"):
        redis_client.expire(key, ttl_seconds)


def get_alpha_vantage_key(db: Session) -> str:
    row = db.query(ExternalProviderCredential).filter(ExternalProviderCredential.provider == ALPHA_PROVIDER_KEY).first()
    if row and row.api_key_encrypted:
        try:
            return decrypt_exchange_secret(row.api_key_encrypted)
        except Exception:
            return ""
    return str(os.environ.get("ALPHA_VANTAGE_KEY") or "")


def upsert_alpha_vantage_key(db: Session, api_key: str) -> ExternalProviderCredential:
    normalized_key = api_key.strip()
    row = db.query(ExternalProviderCredential).filter(ExternalProviderCredential.provider == ALPHA_PROVIDER_KEY).first()
    if row is None:
        row = ExternalProviderCredential(provider=ALPHA_PROVIDER_KEY)
        db.add(row)
    row.api_key_encrypted = encrypt_exchange_secret(normalized_key)
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row


def provider_config_summary(db: Session) -> dict:
    key = get_alpha_vantage_key(db)
    if not key:
        return {"has_alpha_vantage_key": False, "key_hint": None}
    key_hint = f"{key[:4]}...{key[-4:]}" if len(key) >= 8 else "****"
    return {"has_alpha_vantage_key": True, "key_hint": key_hint}


def _crypto_universe_rows(exchange: str, market_type: str, quote_asset_filter: str = "ALL") -> list[dict]:
    provider = BinanceMarketDataProvider()
    payload = provider.get_tradable_symbols(exchange=exchange, market_type=market_type)
    if not payload.get("rows"):
        payload = provider.get_tradable_symbols(exchange=exchange, market_type=market_type, force_refresh=True)
    rows: list[dict] = []
    for row in payload.get("rows", []):
        if not bool(row.get("is_tradable", False)):
            continue
        quote_asset = str(row.get("quote_asset") or "").upper()
        if quote_asset_filter not in {"ALL", ""} and quote_asset != quote_asset_filter:
            continue
        rows.append(
            {
                "symbol": str(row.get("symbol") or "").upper(),
                "source": "crypto",
                "exchange": exchange,
                "market_type": market_type,
                "quote_asset": quote_asset,
                "volume_24h": _safe_float(row.get("volume_24h")),
                "is_tradable": bool(row.get("is_tradable", False)),
                "company_name": None,
                "sector": None,
            }
        )
    rows.sort(key=lambda item: (-(item.get("volume_24h") or 0), item.get("symbol")))
    return rows


def _alpha_listing_rows(key: str, exchanges: list[str]) -> list[dict]:
    cache_key = f"symbol_selector:alpha_listing:{'-'.join(sorted(exchanges))}"
    cached = _cache_get(cache_key)
    if cached:
        return cached.get("rows") or []

    response = requests.get(
        "https://www.alphavantage.co/query",
        params={"function": "LISTING_STATUS", "apikey": key},
        timeout=30,
    )
    response.raise_for_status()
    text = response.text
    if text.strip().startswith("{"):
        return []

    rows: list[dict] = []
    reader = csv.DictReader(io.StringIO(text))
    allowed = {item.strip().upper() for item in exchanges}
    for row in reader:
        exchange = str(row.get("exchange") or "").strip().upper()
        asset_type = str(row.get("assetType") or "").strip().upper()
        status = str(row.get("status") or "").strip().upper()
        if status != "ACTIVE" or asset_type != "STOCK":
            continue
        if allowed and exchange not in allowed:
            continue
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        rows.append(
            {
                "symbol": symbol,
                "source": "stock",
                "exchange": exchange,
                "market_type": "equity",
                "quote_asset": "USD",
                "volume_24h": None,
                "is_tradable": True,
                "company_name": str(row.get("name") or "") or None,
                "sector": None,
            }
        )

    rows.sort(key=lambda item: item.get("symbol"))
    _cache_set(cache_key, {"rows": rows}, ttl_seconds=60 * 60 * 6)
    return rows


def _alpha_top_active_rows(key: str) -> list[dict]:
    cache_key = "symbol_selector:alpha_top_active"
    cached = _cache_get(cache_key)
    if cached:
        return cached.get("rows") or []

    response = requests.get(
        "https://www.alphavantage.co/query",
        params={"function": "TOP_GAINERS_LOSERS", "apikey": key},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json() if "application/json" in response.headers.get("content-type", "") else {}
    active_rows: list[dict] = []
    for row in payload.get("most_actively_traded") or []:
        symbol = str(row.get("ticker") or "").strip().upper()
        if not symbol:
            continue
        active_rows.append(
            {
                "symbol": symbol,
                "source": "stock",
                "exchange": "US",
                "market_type": "equity",
                "quote_asset": "USD",
                "volume_24h": _safe_float(row.get("volume")),
                "is_tradable": True,
                "company_name": None,
                "sector": None,
            }
        )
    _cache_set(cache_key, {"rows": active_rows}, ttl_seconds=60 * 10)
    return active_rows


def resolve_symbol_universe(
    db: Session,
    *,
    source: str,
    exchange: str,
    market_type: str,
    mode: str,
    selected_symbols: list[str] | str | None,
    query: str = "",
    quote_asset_filter: str = "ALL",
) -> dict:
    normalized_source = _normalize_source(source)
    normalized_mode = _normalize_mode(mode)
    custom_symbols = _normalize_symbol_list(selected_symbols)
    search = str(query or "").strip().upper()
    warnings: list[str] = []
    skipped_symbols: list[dict] = []

    rows: list[dict] = []
    has_provider_key = True

    if normalized_source == "crypto":
        try:
            rows = _crypto_universe_rows(exchange=exchange, market_type=market_type, quote_asset_filter=quote_asset_filter)
        except MarketDataProviderError as exc:
            rows = []
            warnings.append(str(exc))
    else:
        alpha_key = get_alpha_vantage_key(db)
        has_provider_key = bool(alpha_key)
        if not alpha_key:
            warnings.append("alpha_vantage_key_missing")
        else:
            if normalized_mode in {"all_market_symbols", "manual_selection"}:
                rows = _alpha_listing_rows(alpha_key, exchanges=["NASDAQ", "NYSE"])
            else:
                rows = _alpha_top_active_rows(alpha_key)

    if search:
        rows = [row for row in rows if search in str(row.get("symbol", "")) or search in str(row.get("company_name", ""))]

    selected: list[str] = []
    if normalized_mode == "top_volume":
        selected = [row["symbol"] for row in rows[:100]]
    elif normalized_mode == "manual_selection":
        available = {row["symbol"] for row in rows}
        for symbol in custom_symbols:
            if symbol in available or normalized_source == "stock":
                selected.append(symbol)
            else:
                skipped_symbols.append({"symbol": symbol, "reason": "not_found_in_universe"})
    else:
        selected = [row["symbol"] for row in rows]

    selected = list(dict.fromkeys(selected))
    return {
        "source": normalized_source,
        "mode": normalized_mode,
        "exchange": exchange,
        "market_type": market_type,
        "rows": rows,
        "selected_symbols": selected,
        "skipped_symbols": skipped_symbols,
        "warnings": warnings,
        "has_provider_key": has_provider_key,
    }


def list_symbol_watchlists(db: Session, user_id: str, source: str | None = None) -> list[SymbolSelectionWatchlist]:
    query = db.query(SymbolSelectionWatchlist).filter(SymbolSelectionWatchlist.user_id == user_id)
    normalized_source = _normalize_source(source) if source else None
    if normalized_source:
        query = query.filter(SymbolSelectionWatchlist.source == normalized_source)
    return query.order_by(SymbolSelectionWatchlist.updated_at.desc()).all()


def create_symbol_watchlist(
    db: Session,
    *,
    user_id: str,
    name: str,
    source: str,
    exchange: str,
    market_type: str,
    symbols: list[str],
) -> SymbolSelectionWatchlist:
    row = SymbolSelectionWatchlist(
        user_id=user_id,
        name=name.strip(),
        source=_normalize_source(source),
        exchange=(exchange or "binance").strip().lower(),
        market_type=(market_type or "spot").strip().lower(),
        symbols=_normalize_symbol_list(symbols),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_symbol_watchlist(
    db: Session,
    *,
    watchlist_id: str,
    user_id: str,
    name: str,
    symbols: list[str],
) -> SymbolSelectionWatchlist:
    row = (
        db.query(SymbolSelectionWatchlist)
        .filter(SymbolSelectionWatchlist.id == watchlist_id, SymbolSelectionWatchlist.user_id == user_id)
        .first()
    )
    if row is None:
        raise ValueError("watchlist_not_found")

    row.name = name.strip()
    row.symbols = _normalize_symbol_list(symbols)
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row


def delete_symbol_watchlist(db: Session, *, watchlist_id: str, user_id: str) -> bool:
    row = (
        db.query(SymbolSelectionWatchlist)
        .filter(SymbolSelectionWatchlist.id == watchlist_id, SymbolSelectionWatchlist.user_id == user_id)
        .first()
    )
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True
