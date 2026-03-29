from fastapi import APIRouter, Depends, HTTPException, Query, status

from deps import get_current_user
from models import User
from schemas import MarketTickerResponse
from services.indicator_screener.market_data_provider import BinanceMarketDataProvider, MarketDataProviderError
from services.live_mode_service import get_market_ticker
from services.quote_asset_policy import normalize_quote_symbol

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/ticker", response_model=MarketTickerResponse)
def market_ticker(symbol: str = Query(...), _: User = Depends(get_current_user)):
    try:
        validated_symbol = normalize_quote_symbol(
            symbol,
            missing_error_code="symbol_required",
            invalid_error_code="invalid_quote_asset",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return MarketTickerResponse(**get_market_ticker(validated_symbol))


@router.get("/candles")
def market_candles(
    symbol: str = Query(...),
    timeframe: str = Query(default="1h", pattern="^(5m|15m|1h|4h|1d)$"),
    market_type: str = Query(default="futures", pattern="^(spot|futures)$"),
    limit: int = Query(default=180, ge=80, le=500),
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    try:
        validated_symbol = normalize_quote_symbol(
            symbol,
            missing_error_code="symbol_required",
            invalid_error_code="invalid_quote_asset",
        )
        provider = BinanceMarketDataProvider()
        return provider.fetch_candles(
            exchange="binance",
            market_type=market_type,
            symbol=validated_symbol,
            timeframe=timeframe,
            candle_limit=limit,
        )
    except (ValueError, MarketDataProviderError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc