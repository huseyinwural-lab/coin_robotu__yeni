from dataclasses import asdict, dataclass
from datetime import datetime, timezone


def _parse_ts(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            return None
    return None


@dataclass
class MicrostructureSnapshot:
    symbol: str
    timestamp: str
    best_bid: float
    best_ask: float
    mid_price: float
    spread_bps: float
    bid_depth_top_n: float
    ask_depth_top_n: float
    depth_imbalance: float
    top_of_book_size: float
    recent_trade_volume: float
    recent_trade_count: int
    short_window_volatility: float
    quote_update_rate: float
    liquidity_gap_score: float
    price_jump_score: float
    stale_data: bool


def build_microstructure_snapshot(
    *,
    symbol: str,
    ticker_payload: dict,
    spread_payload: dict,
    orderbook_payload: dict,
    trade_stats_payload: dict,
    stale_after_seconds: int = 30,
) -> dict:
    now = datetime.now(timezone.utc)
    latest_ts = max(
        [
            ts
            for ts in [
                _parse_ts(ticker_payload.get("updated_at")),
                _parse_ts(spread_payload.get("updated_at")),
                _parse_ts(orderbook_payload.get("updated_at")),
                _parse_ts(trade_stats_payload.get("updated_at")),
            ]
            if ts is not None
        ],
        default=None,
    )
    stale_data = True
    if latest_ts is not None:
        stale_data = (now - latest_ts).total_seconds() > stale_after_seconds

    best_bid = float(spread_payload.get("top_bid") or orderbook_payload.get("best_bid") or 0.0)
    best_ask = float(spread_payload.get("top_ask") or orderbook_payload.get("best_ask") or 0.0)
    mid_price = ((best_bid + best_ask) / 2) if best_bid > 0 and best_ask > 0 else float(ticker_payload.get("last_price") or 0.0)

    spread_bps = float(spread_payload.get("spread_bps") or 0.0)
    if spread_bps <= 0 and best_bid > 0 and best_ask > 0:
        spread_bps = ((best_ask - best_bid) / best_ask) * 10_000

    bid_depth_top_n = float(orderbook_payload.get("bid_depth_top_n") or trade_stats_payload.get("bid_depth_top_n") or 0.0)
    ask_depth_top_n = float(orderbook_payload.get("ask_depth_top_n") or trade_stats_payload.get("ask_depth_top_n") or 0.0)
    if bid_depth_top_n <= 0 or ask_depth_top_n <= 0:
        quote_volume = float(ticker_payload.get("quote_volume") or 0.0)
        synthetic_depth = max(quote_volume / 1500, 1.0)
        if bid_depth_top_n <= 0:
            bid_depth_top_n = synthetic_depth
        if ask_depth_top_n <= 0:
            ask_depth_top_n = synthetic_depth

    total_depth = bid_depth_top_n + ask_depth_top_n
    depth_imbalance = ((bid_depth_top_n - ask_depth_top_n) / total_depth) if total_depth > 0 else 0.0
    top_of_book_size = float(orderbook_payload.get("top_of_book_size") or min(bid_depth_top_n, ask_depth_top_n))

    recent_trade_volume = float(trade_stats_payload.get("recent_trade_volume") or ticker_payload.get("quote_volume") or 0.0)
    recent_trade_count = int(trade_stats_payload.get("recent_trade_count") or 0)
    if recent_trade_count <= 0:
        recent_trade_count = int(max(recent_trade_volume / max(mid_price, 1.0), 0))

    short_window_volatility = float(trade_stats_payload.get("short_window_volatility") or 0.0)
    quote_update_rate = float(trade_stats_payload.get("quote_update_rate") or 0.0)
    if quote_update_rate <= 0:
        quote_update_rate = float(trade_stats_payload.get("estimated_quote_update_rate") or max(recent_trade_count / 30, 0.1))

    liquidity_gap_score = min(100.0, max(0.0, spread_bps * 0.9 + (40 / max(top_of_book_size, 0.5))))
    price_jump_score = min(100.0, max(0.0, short_window_volatility * 6000 + abs(depth_imbalance) * 30))

    snapshot = MicrostructureSnapshot(
        symbol=symbol.upper(),
        timestamp=now.isoformat(),
        best_bid=round(best_bid, 8),
        best_ask=round(best_ask, 8),
        mid_price=round(mid_price, 8),
        spread_bps=round(spread_bps, 4),
        bid_depth_top_n=round(bid_depth_top_n, 6),
        ask_depth_top_n=round(ask_depth_top_n, 6),
        depth_imbalance=round(depth_imbalance, 6),
        top_of_book_size=round(top_of_book_size, 6),
        recent_trade_volume=round(recent_trade_volume, 4),
        recent_trade_count=recent_trade_count,
        short_window_volatility=round(short_window_volatility, 6),
        quote_update_rate=round(quote_update_rate, 4),
        liquidity_gap_score=round(liquidity_gap_score, 4),
        price_jump_score=round(price_jump_score, 4),
        stale_data=stale_data,
    )
    return asdict(snapshot)
