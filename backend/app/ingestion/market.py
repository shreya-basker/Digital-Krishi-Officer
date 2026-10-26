"""Mandi prices: live from data.gov.in (Agmarknet) when a key is set, otherwise sample data."""

import csv
import zlib
from datetime import date, datetime, timedelta

import httpx
import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import BACKEND_DIR, settings
from app.models import MarketPrice

AGMARKNET_URL = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
SAMPLE_CSV = BACKEND_DIR / "seed" / "mandi_sample.csv"
SAMPLE_DAYS = 21
TREND_WINDOW_DAYS = 14
# % change over the window beyond which the trend counts as rising / falling
TREND_THRESHOLD_PCT = 5.0
LIVE_REFRESH_HOURS = 6

_last_live_refresh: dict[tuple[str, str], datetime] = {}


def parse_agmarknet_records(records: list[dict]) -> list[dict]:
    rows = []
    for r in records:
        try:
            rows.append(
                {
                    "state": r["state"],
                    "district": r["district"],
                    "market": r["market"],
                    "commodity": r["commodity"],
                    "variety": r.get("variety") or "",
                    "arrival_date": datetime.strptime(r["arrival_date"], "%d/%m/%Y").date(),
                    "min_price": float(r["min_price"]),
                    "max_price": float(r["max_price"]),
                    "modal_price": float(r["modal_price"]),
                }
            )
        except (KeyError, ValueError):
            continue  # skip malformed rows rather than failing the whole batch
    return rows


def fetch_live(state: str, commodity: str) -> list[dict]:
    params = {
        "api-key": settings.data_gov_api_key,
        "format": "json",
        "limit": 500,
        "filters[state.keyword]": state,
        "filters[commodity]": commodity,
    }
    resp = httpx.get(AGMARKNET_URL, params=params, timeout=20)
    resp.raise_for_status()
    return parse_agmarknet_records(resp.json().get("records", []))


def upsert_prices(db: Session, rows: list[dict], source: str) -> int:
    added = 0
    for row in rows:
        existing = db.scalar(
            select(MarketPrice).where(
                MarketPrice.state == row["state"],
                MarketPrice.market == row["market"],
                MarketPrice.commodity == row["commodity"],
                MarketPrice.variety == row["variety"],
                MarketPrice.arrival_date == row["arrival_date"],
            )
        )
        if existing:
            for k in ("min_price", "max_price", "modal_price"):
                setattr(existing, k, row[k])
            existing.source = source
        else:
            db.add(MarketPrice(source=source, **row))
            added += 1
    db.commit()
    return added


def _noise(*parts) -> float:
    # deterministic +-2% wobble so sample series look realistic but are reproducible
    return (zlib.crc32("|".join(map(str, parts)).encode()) % 401 - 200) / 10000


def ensure_sample_prices(db: Session, today: date | None = None) -> int:
    """Synthesise the last SAMPLE_DAYS of prices from the sample CSV (idempotent)."""
    today = today or date.today()
    start = today - timedelta(days=SAMPLE_DAYS - 1)
    have = set(
        db.execute(
            select(MarketPrice.market, MarketPrice.commodity, MarketPrice.arrival_date).where(
                MarketPrice.source == "sample", MarketPrice.arrival_date >= start
            )
        ).all()
    )
    added = 0
    with open(SAMPLE_CSV, encoding="utf-8") as f:
        for base in csv.DictReader(f):
            for i in range(SAMPLE_DAYS):
                day = start + timedelta(days=i)
                if (base["market"], base["commodity"], day) in have:
                    continue
                # anchor today's price at base_price and walk backwards along the trend
                factor = (1 + float(base["daily_change_pct"]) / 100) ** (i - (SAMPLE_DAYS - 1))
                modal = round(float(base["base_price"]) * factor * (1 + _noise(base["market"], base["commodity"], day)))
                db.add(
                    MarketPrice(
                        state=base["state"],
                        district=base["district"],
                        market=base["market"],
                        commodity=base["commodity"],
                        variety="",
                        arrival_date=day,
                        min_price=round(modal * 0.85),
                        max_price=round(modal * 1.12),
                        modal_price=modal,
                        source="sample",
                    )
                )
                added += 1
    db.commit()
    return added


def refresh_prices(db: Session, state: str, commodity: str) -> None:
    """Pull live prices at most every LIVE_REFRESH_HOURS; always keep sample data available."""
    if settings.data_gov_api_key:
        key = (state, commodity)
        last = _last_live_refresh.get(key)
        if last is None or datetime.now() - last > timedelta(hours=LIVE_REFRESH_HOURS):
            try:
                upsert_prices(db, fetch_live(state, commodity), source="agmarknet")
                _last_live_refresh[key] = datetime.now()
            except httpx.HTTPError:
                pass  # fall through to whatever is stored
    ensure_sample_prices(db)


def _source_rows(db: Session, state: str, commodity: str, since: date) -> list[MarketPrice]:
    rows = db.scalars(
        select(MarketPrice).where(
            MarketPrice.state == state, MarketPrice.commodity == commodity, MarketPrice.arrival_date >= since
        )
    ).all()
    # prefer real Agmarknet data whenever there is any for this window
    live = [r for r in rows if r.source == "agmarknet"]
    return live or list(rows)


def latest_prices(db: Session, state: str, commodity: str, today: date | None = None) -> list[MarketPrice]:
    today = today or date.today()
    rows = _source_rows(db, state, commodity, today - timedelta(days=TREND_WINDOW_DAYS))
    latest: dict[str, MarketPrice] = {}
    for r in rows:
        if r.market not in latest or r.arrival_date > latest[r.market].arrival_date:
            latest[r.market] = r
    return sorted(latest.values(), key=lambda r: r.market)


def price_trend(db: Session, state: str, commodity: str, today: date | None = None) -> dict | None:
    today = today or date.today()
    rows = _source_rows(db, state, commodity, today - timedelta(days=TREND_WINDOW_DAYS - 1))
    return compute_trend([(r.arrival_date, r.modal_price) for r in rows], source=rows[0].source if rows else None)


def compute_trend(points: list[tuple[date, float]], source: str | None = None) -> dict | None:
    """Least-squares slope of the daily mean modal price."""
    by_day: dict[date, list[float]] = {}
    for d, price in points:
        by_day.setdefault(d, []).append(price)
    if len(by_day) < 3:
        return None
    days = sorted(by_day)
    x = np.array([(d - days[0]).days for d in days], dtype=float)
    y = np.array([np.mean(by_day[d]) for d in days])
    slope, intercept = np.polyfit(x, y, 1)
    fitted_start, fitted_end = intercept, intercept + slope * x[-1]
    pct = float((fitted_end - fitted_start) / fitted_start * 100) if fitted_start else 0.0
    direction = "rising" if pct >= TREND_THRESHOLD_PCT else "falling" if pct <= -TREND_THRESHOLD_PCT else "flat"
    return {
        "trend": direction,
        "pct_change": round(pct, 1),
        "slope_per_day": round(float(slope), 2),
        "latest_modal": round(float(y[-1])),
        "days": len(days),
        "source": source,
    }
