"""Orchestration: data layer -> intelligence layer -> stored recommendations."""

from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import case, func, select, update
from sqlalchemy.orm import Session

from app.engine import explain, fusion, kb, ranker
from app.engine.features import FarmContext, build_context
from app.ingestion import market, weather
from app.models import CropCycle, Farm, Recommendation

TOP_N = 8


@dataclass
class FarmState:
    context: FarmContext
    forecast: dict | None
    weather_fetched_at: datetime | None


def require_cycle(farm: Farm) -> CropCycle:
    cycle = farm.active_cycle
    if cycle is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Add the crop you are growing to this farm first")
    return cycle


def farm_state(db: Session, farm: Farm, now: datetime | None = None) -> FarmState:
    now = now or datetime.now(timezone.utc)
    cycle = require_cycle(farm)
    try:
        forecast, fetched_at = weather.get_forecast(db, farm)
    except weather.WeatherUnavailable:
        forecast, fetched_at = None, None
    commodity = kb.crop(cycle.crop)["market_name"]
    market.refresh_prices(db, farm.state, commodity)
    price = market.price_trend(db, farm.state, commodity)
    ctx = build_context(cycle, farm.irrigation_type, farm.latest_soil, forecast, price, now)
    return FarmState(context=ctx, forecast=forecast, weather_fetched_at=fetched_at)


def feedback_counts(db: Session) -> dict[str, tuple[int, int]]:
    """(accepted, responded) per rule across all farms — the learning signal for the ranker."""
    rows = db.execute(
        select(
            Recommendation.rule_id,
            func.sum(case((Recommendation.status.in_(["accepted", "done"]), 1), else_=0)),
            func.count(Recommendation.id),
        )
        .where(Recommendation.status.in_(["accepted", "rejected", "done"]))
        .group_by(Recommendation.rule_id)
    ).all()
    return {rule_id: (int(acc or 0), int(total)) for rule_id, acc, total in rows}


def generate_recommendations(db: Session, farm: Farm, language: str) -> list[Recommendation]:
    state = farm_state(db, farm)
    cycle = require_cycle(farm)
    candidates = fusion.evaluate(state.context)
    ranked = explain.localise(ranker.rank(candidates, feedback_counts(db), top_n=TOP_N), language)

    # supersede the previous run's untouched recommendations
    db.execute(
        update(Recommendation)
        .where(Recommendation.crop_cycle_id == cycle.id, Recommendation.status == "shown")
        .values(status="expired")
    )
    now = datetime.now(timezone.utc)
    recs = [
        Recommendation(
            crop_cycle_id=cycle.id,
            generated_at=now,
            rule_id=a.candidate.rule_id,
            action_type=a.candidate.action_type,
            title=a.candidate.title,
            rationale=a.candidate.rationale,
            signals=a.candidate.signals,
            score=a.score,
            rank=a.rank,
        )
        for a in ranked
    ]
    db.add_all(recs)
    db.commit()
    return recs


def current_recommendations(db: Session, cycle: CropCycle) -> list[Recommendation]:
    latest = db.scalar(select(func.max(Recommendation.generated_at)).where(Recommendation.crop_cycle_id == cycle.id))
    if latest is None:
        return []
    return list(
        db.scalars(
            select(Recommendation)
            .where(Recommendation.crop_cycle_id == cycle.id, Recommendation.generated_at == latest)
            .order_by(Recommendation.rank)
        )
    )


def context_for_chat(farm: Farm, ctx: FarmContext | None, recs: list[Recommendation]) -> str:
    lines = [f"Location: {farm.district + ', ' if farm.district else ''}{farm.state}, India "
             f"(lat {farm.lat:.3f}, lon {farm.lon:.3f}); irrigation: {farm.irrigation_type}"]
    if ctx:
        lines += [
            f"Crop: {ctx.crop_label}, {ctx.crop_stage_label} stage, day {ctx.crop_day}",
            f"Soil: moisture {ctx.soil_moisture_level or 'unknown'}, N {ctx.n_level or 'unknown'}, "
            f"P {ctx.p_level or 'unknown'}, K {ctx.k_level or 'unknown'}, pH {ctx.ph_level or 'unknown'}",
            f"Weather next 48h: rain chance {ctx.rain_prob_48h}%, rain {ctx.rain_mm_48h} mm, "
            f"temperature {ctx.temp_min_48h}-{ctx.temp_max_48h} C",
            f"Pest/disease risk: {ctx.pest_risk or 'unknown'} ({', '.join(ctx.pest_threats) or 'none named'})",
            f"Market: {ctx.price_trend or 'unknown'} trend, {ctx.price_pct_change}% over 14 days, "
            f"modal Rs {ctx.latest_modal_price}/quintal",
        ]
    if recs:
        lines.append("Current ranked recommendations: " + "; ".join(f"{r.rank}. {r.title}" for r in recs))
    return "\n".join(lines)
