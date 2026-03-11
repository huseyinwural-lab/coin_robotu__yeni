from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db import get_db
from deps import get_current_user
from models import BacktestResultCard, User
from schemas import BacktestResultCardResponse

router = APIRouter(prefix="/backtest", tags=["backtest"])


@router.get("/cards", response_model=list[BacktestResultCardResponse])
def list_backtest_cards(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(BacktestResultCard).order_by(BacktestResultCard.updated_at.desc()).all()
