import os
import tempfile
from datetime import datetime, timedelta, timezone

# must be set before app modules read settings; TEST_DATABASE_URL lets you run against Postgres
_tmpdir = tempfile.mkdtemp(prefix="agrisathi-test-")
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{_tmpdir}/test.db")
os.environ["OPENAI_API_KEY"] = ""
os.environ["DATA_GOV_API_KEY"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.ingestion import weather  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


def make_forecast(
    now: datetime | None = None,
    hours: int = 168,
    temp: float = 24.0,
    rh: float = 70.0,
    rain_prob: float = 20.0,
    rain_mm: float = 0.0,
    soil_moisture: float = 0.25,
    humid_hours: int = 0,
    humid_rh: float = 92.0,
) -> dict:
    """An Open-Meteo-shaped payload (IST) with constant conditions; the first
    `humid_hours` hours get `humid_rh` humidity to drive the pest model."""
    now = now or datetime.now(timezone.utc)
    offset = 19800  # IST
    start = (now + timedelta(seconds=offset)).replace(tzinfo=None, minute=0, second=0, microsecond=0)
    times = [(start + timedelta(hours=i)).isoformat(timespec="minutes") for i in range(hours)]
    per_hour_rain = rain_mm / 48
    hourly = {
        "time": times,
        "temperature_2m": [temp] * hours,
        "relative_humidity_2m": [humid_rh if i < humid_hours else rh for i in range(hours)],
        "precipitation_probability": [rain_prob] * hours,
        "precipitation": [per_hour_rain if i < 48 else 0.0 for i in range(hours)],
        "soil_moisture_3_to_9cm": [soil_moisture] * hours,
        "et0_fao_evapotranspiration": [0.15] * hours,
    }
    days = sorted({t[:10] for t in times})[:7]
    daily = {
        "time": days,
        "weather_code": [61 if rain_prob >= 60 else 2] * len(days),
        "temperature_2m_max": [temp + 4] * len(days),
        "temperature_2m_min": [temp - 4] * len(days),
        "precipitation_sum": [rain_mm / 2] * len(days),
        "precipitation_probability_max": [rain_prob] * len(days),
    }
    return {"utc_offset_seconds": offset, "timezone": "Asia/Kolkata", "hourly": hourly, "daily": daily}


@pytest.fixture
def forecast(monkeypatch):
    """Replaces the Open-Meteo call; tests set `forecast.payload`."""

    class Stub:
        payload = make_forecast()
        calls = 0

    def fake_fetch(lat, lon):
        Stub.calls += 1
        return Stub.payload

    monkeypatch.setattr(weather, "fetch_forecast", fake_fetch)
    return Stub


@pytest.fixture
def client():
    return TestClient(app)


def register(client, phone="9876500001", password="secret123", name="Test Farmer"):
    resp = client.post("/api/auth/register", json={"phone": phone, "password": password, "name": name})
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}
