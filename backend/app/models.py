from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(200))
    language: Mapped[str] = mapped_column(String(5), default="en")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    farms: Mapped[list["Farm"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Farm(Base):
    __tablename__ = "farms"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    state: Mapped[str] = mapped_column(String(60))
    district: Mapped[str | None] = mapped_column(String(60))
    area_ha: Mapped[float | None] = mapped_column(Float)
    irrigation_type: Mapped[str] = mapped_column(String(20), default="other")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="farms")
    crop_cycles: Mapped[list["CropCycle"]] = relationship(
        back_populates="farm", cascade="all, delete-orphan", order_by="CropCycle.id"
    )
    soil_readings: Mapped[list["SoilReading"]] = relationship(
        back_populates="farm", cascade="all, delete-orphan", order_by="SoilReading.id"
    )
    weather_snapshots: Mapped[list["WeatherSnapshot"]] = relationship(cascade="all, delete-orphan")

    @property
    def active_cycle(self) -> "CropCycle | None":
        active = [c for c in self.crop_cycles if c.status == "active"]
        return active[-1] if active else None

    @property
    def latest_soil(self) -> "SoilReading | None":
        return max(self.soil_readings, key=lambda s: (s.sampled_on, s.id)) if self.soil_readings else None


class CropCycle(Base):
    __tablename__ = "crop_cycles"

    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farms.id", ondelete="CASCADE"), index=True)
    crop: Mapped[str] = mapped_column(String(40))
    variety: Mapped[str | None] = mapped_column(String(60))
    sowing_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    farm: Mapped[Farm] = relationship(back_populates="crop_cycles")
    recommendations: Mapped[list["Recommendation"]] = relationship(
        back_populates="crop_cycle", cascade="all, delete-orphan"
    )


class SoilReading(Base):
    __tablename__ = "soil_readings"

    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farms.id", ondelete="CASCADE"), index=True)
    sampled_on: Mapped[date] = mapped_column(Date)
    nitrogen: Mapped[float | None] = mapped_column(Float)  # available N, kg/ha
    phosphorus: Mapped[float | None] = mapped_column(Float)  # available P, kg/ha
    potassium: Mapped[float | None] = mapped_column(Float)  # available K, kg/ha
    ph: Mapped[float | None] = mapped_column(Float)
    organic_carbon: Mapped[float | None] = mapped_column(Float)  # %
    ec: Mapped[float | None] = mapped_column(Float)  # dS/m
    source: Mapped[str] = mapped_column(String(30), default="soil_health_card")

    farm: Mapped[Farm] = relationship(back_populates="soil_readings")


class WeatherSnapshot(Base):
    __tablename__ = "weather_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farms.id", ondelete="CASCADE"), index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    payload: Mapped[dict] = mapped_column(JSON)


class MarketPrice(Base):
    __tablename__ = "market_prices"
    __table_args__ = (UniqueConstraint("state", "market", "commodity", "variety", "arrival_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    state: Mapped[str] = mapped_column(String(60), index=True)
    district: Mapped[str] = mapped_column(String(60))
    market: Mapped[str] = mapped_column(String(100))
    commodity: Mapped[str] = mapped_column(String(60), index=True)
    variety: Mapped[str] = mapped_column(String(60), default="")
    arrival_date: Mapped[date] = mapped_column(Date, index=True)
    min_price: Mapped[float] = mapped_column(Float)  # Rs/quintal
    max_price: Mapped[float] = mapped_column(Float)
    modal_price: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(20), default="agmarknet")


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)
    crop_cycle_id: Mapped[int] = mapped_column(ForeignKey("crop_cycles.id", ondelete="CASCADE"), index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    rule_id: Mapped[str] = mapped_column(String(60), index=True)
    action_type: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(200))
    rationale: Mapped[str] = mapped_column(Text)
    signals: Mapped[dict] = mapped_column(JSON, default=dict)
    score: Mapped[float] = mapped_column(Float)
    rank: Mapped[int] = mapped_column(Integer)
    # shown -> accepted/rejected/done; expired when superseded by a newer run
    status: Mapped[str] = mapped_column(String(20), default="shown")

    crop_cycle: Mapped[CropCycle] = relationship(back_populates="recommendations")
    feedback: Mapped[list["Feedback"]] = relationship(back_populates="recommendation", cascade="all, delete-orphan")


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    recommendation_id: Mapped[int] = mapped_column(ForeignKey("recommendations.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(10))  # accept | reject | done
    outcome_note: Mapped[str | None] = mapped_column(Text)
    rating: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    recommendation: Mapped[Recommendation] = relationship(back_populates="feedback")


class Query(Base):
    __tablename__ = "queries"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    farm_id: Mapped[int | None] = mapped_column(ForeignKey("farms.id", ondelete="SET NULL"))
    text: Mapped[str] = mapped_column(Text, default="")
    had_image: Mapped[bool] = mapped_column(Boolean, default=False)
    answer: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
