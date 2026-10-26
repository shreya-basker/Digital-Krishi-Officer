"""Weather + modelled soil moisture from Open-Meteo (free, no API key)."""

from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Farm, WeatherSnapshot

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
HOURLY_VARS = [
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation_probability",
    "precipitation",
    "soil_moisture_3_to_9cm",
    "et0_fao_evapotranspiration",
]
DAILY_VARS = [
    "weather_code",
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "precipitation_probability_max",
]

# WMO weather interpretation codes, grouped
_WMO = [
    ((0,), "Clear", "☀️"),
    ((1, 2), "Partly cloudy", "⛅"),
    ((3,), "Cloudy", "☁️"),
    ((45, 48), "Fog", "🌫️"),
    ((51, 53, 55, 56, 57), "Drizzle", "🌦️"),
    ((61, 63, 65, 66, 67, 80, 81, 82), "Rain", "🌧️"),
    ((71, 73, 75, 77, 85, 86), "Snow", "❄️"),
    ((95, 96, 99), "Thunderstorm", "⛈️"),
]


class WeatherUnavailable(Exception):
    pass


def describe_code(code: int | None) -> tuple[str, str]:
    for codes, label, icon in _WMO:
        if code in codes:
            return label, icon
    return "Unknown", "🌡️"


def fetch_forecast(lat: float, lon: float) -> dict:
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(HOURLY_VARS),
        "daily": ",".join(DAILY_VARS),
        "timezone": "auto",
        "forecast_days": 7,
    }
    resp = httpx.get(OPEN_METEO_URL, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_forecast(db: Session, farm: Farm) -> tuple[dict, datetime]:
    """Cached forecast for a farm; falls back to the last snapshot if the API is down."""
    latest = db.scalar(
        select(WeatherSnapshot)
        .where(WeatherSnapshot.farm_id == farm.id)
        .order_by(WeatherSnapshot.fetched_at.desc())
        .limit(1)
    )
    now = datetime.now(timezone.utc)
    if latest and _aware(latest.fetched_at) > now - timedelta(minutes=settings.weather_cache_minutes):
        return latest.payload, _aware(latest.fetched_at)
    try:
        payload = fetch_forecast(farm.lat, farm.lon)
    except httpx.HTTPError as exc:
        if latest:
            return latest.payload, _aware(latest.fetched_at)
        raise WeatherUnavailable(str(exc)) from exc
    snapshot = WeatherSnapshot(farm_id=farm.id, fetched_at=now, payload=payload)
    db.add(snapshot)
    db.commit()
    return payload, now


def _aware(dt: datetime) -> datetime:
    # SQLite drops tzinfo; values are always stored as UTC
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def hourly_rows(payload: dict, now: datetime, hours: int) -> list[dict]:
    """Hourly forecast rows from the current local hour onward."""
    hourly = payload["hourly"]
    offset = timedelta(seconds=payload.get("utc_offset_seconds", 0))
    local_now = (now.astimezone(timezone.utc) + offset).replace(tzinfo=None, minute=0, second=0, microsecond=0)
    rows = []
    for i, t in enumerate(hourly["time"]):
        if datetime.fromisoformat(t) < local_now:
            continue
        rows.append({var: (hourly.get(var) or [None] * len(hourly["time"]))[i] for var in ["time", *HOURLY_VARS]})
        if len(rows) == hours:
            break
    return rows


def daily_summary(payload: dict) -> list[dict]:
    daily = payload["daily"]
    days = []
    for i, d in enumerate(daily["time"]):
        label, icon = describe_code(daily["weather_code"][i])
        days.append(
            {
                "date": d,
                "weekday": datetime.fromisoformat(d).strftime("%a"),
                "label": label,
                "icon": icon,
                "t_max": daily["temperature_2m_max"][i],
                "t_min": daily["temperature_2m_min"][i],
                "rain_mm": daily["precipitation_sum"][i],
                "rain_prob": daily["precipitation_probability_max"][i],
            }
        )
    return days
