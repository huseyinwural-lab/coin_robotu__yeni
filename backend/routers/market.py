from fastapi import APIRouter, Depends, HTTPException, Query, status

from deps import get_current_user
from models import User
from schemas import MarketTickerResponse
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