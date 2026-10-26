from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Language = Literal["en", "ml", "hi"]
IrrigationType = Literal["drip", "sprinkler", "flood", "canal", "rainfed", "other"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RegisterIn(BaseModel):
    phone: str = Field(min_length=10, max_length=15, pattern=r"^\+?\d+$")
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=6, max_length=72)
    language: Language = "en"


class LoginIn(BaseModel):
    phone: str
    password: str


class UserOut(ORM):
    id: int
    phone: str
    name: str
    language: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    language: Language | None = None


class CropCycleIn(BaseModel):
    crop: str
    variety: str | None = None
    sowing_date: date


class CropCycleOut(ORM):
    id: int
    crop: str
    variety: str | None
    sowing_date: date
    status: str


class SoilIn(BaseModel):
    sampled_on: date | None = None
    nitrogen: float | None = Field(default=None, ge=0)
    phosphorus: float | None = Field(default=None, ge=0)
    potassium: float | None = Field(default=None, ge=0)
    ph: float | None = Field(default=None, ge=0, le=14)
    organic_carbon: float | None = Field(default=None, ge=0)
    ec: float | None = Field(default=None, ge=0)
    source: Literal["soil_health_card", "manual"] = "soil_health_card"


class SoilOut(ORM):
    id: int
    sampled_on: date
    nitrogen: float | None
    phosphorus: float | None
    potassium: float | None
    ph: float | None
    organic_carbon: float | None
    ec: float | None
    source: str


class FarmIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    state: str
    district: str | None = None
    area_ha: float | None = Field(default=None, gt=0)
    irrigation_type: IrrigationType = "other"


class FarmOut(ORM):
    id: int
    name: str
    lat: float
    lon: float
    state: str
    district: str | None
    area_ha: float | None
    irrigation_type: str
    active_cycle: CropCycleOut | None
    latest_soil: SoilOut | None


class RecommendationOut(ORM):
    id: int
    rule_id: str
    action_type: str
    title: str
    rationale: str
    signals: dict
    score: float
    rank: int
    status: str
    generated_at: datetime


class FeedbackIn(BaseModel):
    action: Literal["accept", "reject", "done"]
    outcome_note: str | None = Field(default=None, max_length=2000)
    rating: int | None = Field(default=None, ge=1, le=5)


class ChatIn(BaseModel):
    text: str = Field(default="", max_length=4000)
    image_base64: str | None = None
    image_mime: str = "image/jpeg"
    farm_id: int | None = None


class ChatOut(BaseModel):
    answer: str
    query_id: int
