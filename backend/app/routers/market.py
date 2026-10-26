from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.engine import kb
from app.ingestion import market
from app.models import MarketPrice

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/options")
def market_options(db: Session = Depends(get_db)):
    market.ensure_sample_prices(db)
    states = db.scalars(select(MarketPrice.state).distinct().order_by(MarketPrice.state)).all()
    commodities = [{"crop": key, "label": c["label"], "commodity": c["market_name"]} for key, c in kb.crops().items()]
    return {"states": states, "commodities": commodities}


@router.get("/prices")
def market_prices(state: str, commodity: str, db: Session = Depends(get_db)):
    market.refresh_prices(db, state, commodity)
    rows = market.latest_prices(db, state, commodity)
    return {
        "state": state,
        "commodity": commodity,
        "trend": market.price_trend(db, state, commodity),
        "prices": [
            {
                "market": r.market,
                "district": r.district,
                "variety": r.variety,
                "arrival_date": r.arrival_date,
                "min_price": r.min_price,
                "max_price": r.max_price,
                "modal_price": r.modal_price,
                "source": r.source,
            }
            for r in rows
        ],
    }
