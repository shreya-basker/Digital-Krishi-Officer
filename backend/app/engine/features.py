"""Builds one normalised FarmContext from all signal sources (the "one farm decision" input)."""

from dataclasses import asdict, dataclass, field
from datetime import date, datetime

from app.engine import kb
from app.engine.pest_risk import PestRisk, PestRiskModel, WeatherRulePestModel
from app.ingestion.crop_stage import crop_stage
from app.ingestion.soil import soil_levels
from app.ingestion.weather import hourly_rows
from app.models import CropCycle, SoilReading

HEAVY_RAIN_MM = 20


@dataclass
class FarmContext:
    crop: str
    crop_label: str
    irrigation_type: str
    # crop
    crop_stage: str | None = None
    crop_stage_label: str | None = None
    crop_day: int | None = None
    days_to_harvest_window: int | None = None
    in_harvest_window: bool = False
    nitrogen_window: bool = False
    # weather (next 48 h)
    rain_prob_48h: float | None = None
    rain_mm_48h: float | None = None
    rain_outlook: str | None = None  # low | moderate | high
    heavy_rain_48h: bool = False
    temp_max_48h: float | None = None
    temp_min_48h: float | None = None
    # soil
    soil_moisture: float | None = None
    soil_moisture_level: str | None = None  # dry | adequate | wet
    n_level: str | None = None
    p_level: str | None = None
    k_level: str | None = None
    oc_level: str | None = None
    ph_level: str | None = None
    # pest / disease
    pest_risk: str | None = None
    pest_risk_score: float | None = None
    pest_threats: list[str] = field(default_factory=list)
    # market
    price_trend: str | None = None
    price_pct_change: float | None = None
    latest_modal_price: float | None = None
    price_source: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def rain_outlook(prob: float | None, mm: float | None) -> str | None:
    if prob is None and mm is None:
        return None
    prob, mm = prob or 0, mm or 0
    if prob >= 70 or mm >= 10:
        return "high"
    if prob >= 40 or mm >= 2:
        return "moderate"
    return "low"


def moisture_level(crop: str, value: float | None) -> str | None:
    if value is None:
        return None
    t = kb.crop(crop)["soil_moisture"]
    if value < t["dry_below"]:
        return "dry"
    if value > t["wet_above"]:
        return "wet"
    return "adequate"


def build_context(
    cycle: CropCycle,
    irrigation_type: str,
    soil: SoilReading | None,
    weather: dict | None,
    price: dict | None,
    now: datetime,
    today: date | None = None,
    pest_model: PestRiskModel | None = None,
) -> FarmContext:
    today = today or now.date()
    ctx = FarmContext(crop=cycle.crop, crop_label=kb.crop(cycle.crop)["label"], irrigation_type=irrigation_type)

    stage = crop_stage(cycle.crop, cycle.sowing_date, today)
    ctx.crop_stage, ctx.crop_stage_label, ctx.crop_day = stage.key, stage.label, stage.day
    ctx.days_to_harvest_window = stage.days_to_harvest_window
    ctx.in_harvest_window, ctx.nitrogen_window = stage.in_harvest_window, stage.nitrogen_window

    for key, value in soil_levels(soil).items():
        setattr(ctx, key, value)

    if weather:
        hours72 = hourly_rows(weather, now, 72)
        next48 = hours72[:48]
        probs = [r["precipitation_probability"] for r in next48 if r["precipitation_probability"] is not None]
        rain = [r["precipitation"] for r in next48 if r["precipitation"] is not None]
        temps = [r["temperature_2m"] for r in next48 if r["temperature_2m"] is not None]
        ctx.rain_prob_48h = max(probs) if probs else None
        ctx.rain_mm_48h = round(sum(rain), 1) if rain else None
        ctx.rain_outlook = rain_outlook(ctx.rain_prob_48h, ctx.rain_mm_48h)
        ctx.heavy_rain_48h = (ctx.rain_mm_48h or 0) >= HEAVY_RAIN_MM
        ctx.temp_max_48h = max(temps) if temps else None
        ctx.temp_min_48h = min(temps) if temps else None
        moisture = next((r["soil_moisture_3_to_9cm"] for r in next48 if r["soil_moisture_3_to_9cm"] is not None), None)
        ctx.soil_moisture = moisture
        ctx.soil_moisture_level = moisture_level(cycle.crop, moisture)

        risk: PestRisk | None = (pest_model or WeatherRulePestModel()).assess(cycle.crop, stage.key, hours72)
        if risk:
            ctx.pest_risk, ctx.pest_risk_score, ctx.pest_threats = risk.level, risk.score, risk.threats

    if price:
        ctx.price_trend = price["trend"]
        ctx.price_pct_change = price["pct_change"]
        ctx.latest_modal_price = price["latest_modal"]
        ctx.price_source = price["source"]
    return ctx


def signal_cards(ctx: FarmContext) -> list[dict]:
    """The five signal summaries shown next to the recommendations."""

    def fmt(v, suffix=""):
        return "—" if v is None else f"{v:g}{suffix}"

    weather_value = {"high": "Rain likely", "moderate": "Some rain possible", "low": "Mostly dry"}.get(
        ctx.rain_outlook, "Unavailable"
    )
    soil_bits = [f"N {ctx.n_level}" if ctx.n_level else None, f"P {ctx.p_level}" if ctx.p_level else None,
                 f"K {ctx.k_level}" if ctx.k_level else None]
    market_value = {"rising": "Price rising", "falling": "Price falling", "flat": "Price steady"}.get(
        ctx.price_trend, "No market data"
    )
    return [
        {
            "key": "weather",
            "label": "Weather",
            "value": weather_value,
            "detail": f"Rain chance {fmt(ctx.rain_prob_48h, '%')}, {fmt(ctx.rain_mm_48h, ' mm')} in 48 h; "
            f"{fmt(ctx.temp_min_48h, '°C')}–{fmt(ctx.temp_max_48h, '°C')}",
        },
        {
            "key": "soil",
            "label": "Soil",
            "value": f"Moisture {ctx.soil_moisture_level}" if ctx.soil_moisture_level else "Moisture unknown",
            "detail": ", ".join(b for b in soil_bits if b) or "Add Soil Health Card values",
        },
        {
            "key": "crop",
            "label": "Crop",
            "value": f"{ctx.crop_label}: {ctx.crop_stage_label}",
            "detail": f"Day {ctx.crop_day}"
            + (" · in harvest window" if ctx.in_harvest_window
               else f" · harvest window in {ctx.days_to_harvest_window} days"),
        },
        {
            "key": "pest",
            "label": "Pest / disease",
            "value": f"{ctx.pest_risk.capitalize()} risk" if ctx.pest_risk else "Unknown",
            "detail": ", ".join(ctx.pest_threats) or "No weather-favoured threats",
        },
        {
            "key": "market",
            "label": "Market",
            "value": market_value,
            "detail": (
                f"₹{ctx.latest_modal_price:g}/quintal, {ctx.price_pct_change:+g}% over 14 days"
                + (" (sample data)" if ctx.price_source == "sample" else "")
            )
            if ctx.latest_modal_price is not None
            else "No mandi prices for this state and crop",
        },
    ]
