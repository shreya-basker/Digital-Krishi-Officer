from app.engine import kb
from app.models import SoilReading


def rate_nutrient(name: str, value: float | None) -> str | None:
    if value is None:
        return None
    t = kb.soil_thresholds()[name]
    if value < t["low_below"]:
        return "low"
    if value > t["high_above"]:
        return "high"
    return "medium"


def rate_ph(value: float | None) -> str | None:
    if value is None:
        return None
    t = kb.soil_thresholds()["ph"]
    if value < t["acidic_below"]:
        return "acidic"
    if value > t["alkaline_above"]:
        return "alkaline"
    return "neutral"


def soil_levels(reading: SoilReading | None) -> dict[str, str | None]:
    if reading is None:
        return {"n_level": None, "p_level": None, "k_level": None, "oc_level": None, "ph_level": None}
    return {
        "n_level": rate_nutrient("nitrogen", reading.nitrogen),
        "p_level": rate_nutrient("phosphorus", reading.phosphorus),
        "k_level": rate_nutrient("potassium", reading.potassium),
        "oc_level": rate_nutrient("organic_carbon", reading.organic_carbon),
        "ph_level": rate_ph(reading.ph),
    }
