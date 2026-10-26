"""Loads sample mandi prices and a demo farmer. Run from backend/: python -m app.seed"""

from datetime import date, timedelta

from sqlalchemy import select

from app.db import SessionLocal
from app.ingestion.market import ensure_sample_prices
from app.models import CropCycle, Farm, SoilReading, User
from app.security import hash_password

# local demo login only
DEMO_PHONE = "9000000001"
DEMO_PASSWORD = "demo1234"


def main() -> None:
    db = SessionLocal()
    try:
        added = ensure_sample_prices(db)
        print(f"Sample mandi prices: {added} rows added")

        if db.scalar(select(User).where(User.phone == DEMO_PHONE)):
            print(f"Demo farmer already exists (phone {DEMO_PHONE})")
            return
        user = User(phone=DEMO_PHONE, name="Demo Farmer", language="en", password_hash=hash_password(DEMO_PASSWORD))
        # the slide-10 example: tomato at flowering on low-nitrogen soil near Bengaluru
        farm = Farm(
            user=user, name="Yelahanka plot", lat=13.1007, lon=77.5963, state="Karnataka",
            district="Bangalore", area_ha=0.8, irrigation_type="drip",
        )
        farm.crop_cycles.append(CropCycle(crop="tomato", variety="Arka Rakshak", sowing_date=date.today() - timedelta(days=50)))
        farm.soil_readings.append(
            SoilReading(sampled_on=date.today() - timedelta(days=30), nitrogen=230, phosphorus=18, potassium=190,
                        ph=6.8, organic_carbon=0.55, source="soil_health_card")
        )
        db.add(user)
        db.commit()
        print(f"Demo farmer created: phone {DEMO_PHONE}, password {DEMO_PASSWORD}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
