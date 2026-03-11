from fastapi import APIRouter, Depends

from deps import get_current_user
from models import User
from schemas import MarketTickerResponse
from services.live_mode_service import get_market_ticker

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/ticker", response_model=MarketTickerResponse)
def market_ticker(symbol: str = "BTCUSDT", _: User = Depends(get_current_user)):
    return MarketTickerResponse(**get_market_ticker(symbol.upper()))