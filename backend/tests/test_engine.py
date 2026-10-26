from datetime import date, datetime, timedelta, timezone

import pytest

from app.engine import fusion, ranker
from app.engine.features import build_context, rain_outlook
from app.ingestion.crop_stage import crop_stage
from app.ingestion.market import compute_trend
from app.models import CropCycle, SoilReading
from tests.conftest import make_forecast

NOW = datetime(2026, 10, 26, 6, 0, tzinfo=timezone.utc)
TODAY = date(2026, 10, 26)
RISING = {"trend": "rising", "pct_change": 12.0, "latest_modal": 1650, "source": "sample", "slope_per_day": 14, "days": 14}


def tomato(days=50):
    return CropCycle(crop="tomato", sowing_date=TODAY - timedelta(days=days))


def soil(n=230, p=18, k=190, ph=6.8):
    return SoilReading(sampled_on=TODAY, nitrogen=n, phosphorus=p, potassium=k, ph=ph, organic_carbon=0.6)


def context(cycle=None, irrigation="drip", soil_reading="default", price=RISING, **weather):
    weather = {"rain_prob": 85, "rain_mm": 8, "soil_moisture": 0.25, "humid_hours": 8, **weather}
    return build_context(
        cycle or tomato(),
        irrigation,
        soil() if soil_reading == "default" else soil_reading,
        make_forecast(now=NOW, **weather),
        price,
        NOW,
        TODAY,
    )


def rule_ids(ctx):
    return [a.candidate.rule_id for a in ranker.rank(fusion.evaluate(ctx))]


def test_slide_10_worked_example():
    """Tomato, low N, adequate moisture, high rain chance, flowering, moderate pest risk, rising price."""
    ctx = context()
    assert (ctx.crop_stage, ctx.n_level, ctx.soil_moisture_level) == ("flowering", "low", "adequate")
    assert (ctx.rain_outlook, ctx.pest_risk, ctx.price_trend) == ("high", "moderate", "rising")

    assert rule_ids(ctx)[:4] == ["delay_irrigation_rain", "apply_nitrogen", "pest_moderate", "market_rising"]


def test_rationale_is_rendered_from_context():
    top = ranker.rank(fusion.evaluate(context()))[0].candidate
    assert top.title == "Delay irrigation"
    assert "85% chance" in top.rationale
    assert top.signals == {"irrigation_type": "drip", "soil_moisture_level": "adequate", "rain_outlook": "high"}


def test_dry_soil_without_rain_means_irrigate_now():
    ids = rule_ids(context(soil_moisture=0.10, rain_prob=10, rain_mm=0))
    assert "irrigate_now" in ids
    assert "delay_irrigation_rain" not in ids


def test_dry_soil_with_rain_coming_means_light_irrigation_only():
    ids = rule_ids(context(soil_moisture=0.10))
    assert "irrigate_light_before_rain" in ids
    assert "irrigate_now" not in ids


def test_heavy_rain_postpones_nitrogen():
    ids = rule_ids(context(rain_mm=40))
    assert "postpone_fertiliser_heavy_rain" in ids
    assert "apply_nitrogen" not in ids


def test_rainfed_farms_get_no_irrigation_scheduling():
    ids = rule_ids(context(irrigation="rainfed", soil_moisture=0.10, rain_prob=10, rain_mm=0))
    assert not {"irrigate_now", "delay_irrigation_rain", "irrigate_light_before_rain"} & set(ids)


def test_missing_soil_test_asks_for_it_and_skips_nutrient_advice():
    ids = rule_ids(context(soil_reading=None))
    assert "add_soil_test" in ids
    assert "apply_nitrogen" not in ids


def test_long_humid_spell_is_high_risk_and_suppresses_moderate():
    ctx = context(humid_hours=30)
    assert ctx.pest_risk == "high"
    assert "Late blight" in ctx.pest_threats
    ids = rule_ids(ctx)
    assert "pest_high" in ids and "pest_moderate" not in ids


def test_harvest_window_with_falling_prices():
    falling = {**RISING, "trend": "falling", "pct_change": -9.0}
    ids = rule_ids(context(cycle=tomato(days=95), price=falling))
    assert "harvest_window_falling" in ids


def test_no_weather_still_produces_soil_and_market_advice():
    ctx = build_context(tomato(), "drip", soil(), None, RISING, NOW, TODAY)
    assert ctx.rain_outlook is None and ctx.pest_risk is None
    ids = rule_ids(ctx)
    assert "apply_nitrogen" in ids and "market_rising" in ids
    assert "delay_irrigation_rain" not in ids


def test_feedback_prior_reorders_actions():
    candidates = fusion.evaluate(context())
    assert ranker.feedback_prior(0, 0) == 1.0
    # farmers keep rejecting "delay irrigation" and accepting nitrogen advice
    counts = {"delay_irrigation_rain": (0, 20), "apply_nitrogen": (20, 20)}
    ranked = [a.candidate.rule_id for a in ranker.rank(candidates, counts)]
    assert ranked.index("apply_nitrogen") < ranked.index("delay_irrigation_rain")


@pytest.mark.parametrize(
    "days, stage, harvest_in",
    [(0, "establishment", 75), (30, "vegetative", 45), (50, "flowering", 25), (80, "fruiting", 0), (500, "harvest", 0)],
)
def test_crop_stage_calendar(days, stage, harvest_in):
    s = crop_stage("tomato", TODAY - timedelta(days=days), TODAY)
    assert (s.key, s.days_to_harvest_window) == (stage, harvest_in)


@pytest.mark.parametrize("prob, mm, outlook", [(85, 0, "high"), (10, 12, "high"), (45, 0, "moderate"), (10, 0.5, "low")])
def test_rain_outlook(prob, mm, outlook):
    assert rain_outlook(prob, mm) == outlook


def test_price_trend_slope():
    start = date(2026, 10, 1)
    rising = [(start + timedelta(days=i), 1000 * 1.01**i) for i in range(14)]
    flat = [(start + timedelta(days=i), 1000 + (5 if i % 2 else -5)) for i in range(14)]
    assert compute_trend(rising)["trend"] == "rising"
    assert compute_trend(flat)["trend"] == "flat"
    assert compute_trend(rising[:2]) is None
