"""Pest / disease risk. Phase 1 is a weather-rule model; a trained model can replace it
by implementing PestRiskModel."""

from dataclasses import dataclass, field
from typing import Protocol

from app.engine import kb

WINDOW_HOURS = 72
HIGH_RATIO = 1.5
MODERATE_RATIO = 0.6


@dataclass
class PestRisk:
    level: str  # low | moderate | high
    score: float  # 0..1
    threats: list[str] = field(default_factory=list)


class PestRiskModel(Protocol):
    def assess(self, crop: str, stage: str | None, hourly: list[dict]) -> PestRisk | None: ...


def _favourable(row: dict, threat: dict) -> bool:
    t, rh = row.get("temperature_2m"), row.get("relative_humidity_2m")
    if t is None or rh is None:
        return False
    return (
        threat.get("t_min", -99) <= t <= threat.get("t_max", 99)
        and rh >= threat.get("rh_min", 0)
        and rh <= threat.get("rh_max", 100)
    )


class WeatherRulePestModel:
    def assess(self, crop: str, stage: str | None, hourly: list[dict]) -> PestRisk | None:
        threats = kb.pests().get(crop)
        if not threats or not hourly:
            return None
        window = hourly[:WINDOW_HOURS]
        best_ratio, named = 0.0, []
        for threat in threats:
            hours = sum(_favourable(row, threat) for row in window)
            ratio = hours / threat["hours"]
            if ratio >= MODERATE_RATIO:
                named.append(threat["name"])
            best_ratio = max(best_ratio, ratio)
        level = "high" if best_ratio >= HIGH_RATIO else "moderate" if best_ratio >= MODERATE_RATIO else "low"
        return PestRisk(level=level, score=round(min(best_ratio / HIGH_RATIO, 1.0), 2), threats=named)
