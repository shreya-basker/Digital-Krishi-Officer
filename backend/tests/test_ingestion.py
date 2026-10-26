import json
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import func, select

from app.db import SessionLocal
from app.ingestion import market
from app.ingestion.weather import daily_summary, hourly_rows
from app.models import MarketPrice
from tests.conftest import make_forecast

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_agmarknet_records_skips_malformed_rows():
    records = json.loads((FIXTURES / "agmarknet_tomato_karnataka.json").read_text())["records"]
    rows = market.parse_agmarknet_records(records)
    assert len(rows) == 2
    assert rows[0] == {
        "state": "Karnataka", "district": "Kolar", "market": "Kolar", "commodity": "Tomato", "variety": "Local",
        "arrival_date": date(2026, 10, 25), "min_price": 1200.0, "max_price": 1800.0, "modal_price": 1500.0,
    }


def test_upsert_prices_updates_existing_rows():
    records = json.loads((FIXTURES / "agmarknet_tomato_karnataka.json").read_text())["records"]
    rows = market.parse_agmarknet_records(records)
    with SessionLocal() as db:
        assert market.upsert_prices(db, rows, "agmarknet") == 2
        rows[0]["modal_price"] = 1600.0
        assert market.upsert_prices(db, rows, "agmarknet") == 0
        kolar = db.scalar(select(MarketPrice).where(MarketPrice.market == "Kolar"))
        assert kolar.modal_price == 1600.0


def test_sample_prices_are_idempotent():
    with SessionLocal() as db:
        first = market.ensure_sample_prices(db)
        assert first > 0
        assert market.ensure_sample_prices(db) == 0
        assert db.scalar(select(func.count(MarketPrice.id))) == first


def test_hourly_rows_start_at_the_current_local_hour():
    now = datetime(2026, 10, 26, 6, 30, tzinfo=timezone.utc)  # 12:00 IST
    payload = make_forecast(now=datetime(2026, 10, 26, 0, 0, tzinfo=timezone.utc))  # series starts 05:00 IST
    rows = hourly_rows(payload, now, 48)
    assert rows[0]["time"] == "2026-10-26T12:00"
    assert len(rows) == 48


def test_daily_summary_labels_weather_codes():
    days = daily_summary(make_forecast(rain_prob=80))
    assert days[0]["label"] == "Rain" and days[0]["icon"] == "🌧️"
    assert len(days) == 7
