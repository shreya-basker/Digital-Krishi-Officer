from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.engine import kb
from app.models import CropCycle, Farm, SoilReading, User
from app.schemas import CropCycleIn, CropCycleOut, FarmIn, FarmOut, SoilIn, SoilOut
from app.security import get_current_user, get_owned_farm

router = APIRouter(tags=["farms"])


@router.get("/crops")
def list_crops():
    return [{"key": key, "label": c["label"]} for key, c in kb.crops().items()]


@router.get("/farms", response_model=list[FarmOut])
def list_farms(user: User = Depends(get_current_user)):
    return user.farms


@router.post("/farms", response_model=FarmOut, status_code=status.HTTP_201_CREATED)
def create_farm(body: FarmIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    farm = Farm(user_id=user.id, **body.model_dump())
    db.add(farm)
    db.commit()
    return farm


@router.get("/farms/{farm_id}", response_model=FarmOut)
def get_farm(farm_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return get_owned_farm(db, user, farm_id)


@router.put("/farms/{farm_id}", response_model=FarmOut)
def update_farm(farm_id: int, body: FarmIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    farm = get_owned_farm(db, user, farm_id)
    for field, value in body.model_dump().items():
        setattr(farm, field, value)
    db.commit()
    return farm


@router.post("/farms/{farm_id}/crop-cycles", response_model=CropCycleOut, status_code=status.HTTP_201_CREATED)
def start_crop_cycle(
    farm_id: int, body: CropCycleIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    farm = get_owned_farm(db, user, farm_id)
    if body.crop not in kb.crops():
        raise HTTPException(422, f"Unsupported crop '{body.crop}'")
    if body.sowing_date > date.today():
        raise HTTPException(422, "Sowing date cannot be in the future")
    # one active crop per farm: starting a new cycle closes the previous one
    for cycle in farm.crop_cycles:
        if cycle.status == "active":
            cycle.status = "closed"
    cycle = CropCycle(farm_id=farm.id, **body.model_dump())
    db.add(cycle)
    db.commit()
    return cycle


@router.post("/farms/{farm_id}/soil", response_model=SoilOut, status_code=status.HTTP_201_CREATED)
def add_soil_reading(farm_id: int, body: SoilIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    farm = get_owned_farm(db, user, farm_id)
    data = body.model_dump()
    data["sampled_on"] = data["sampled_on"] or date.today()
    reading = SoilReading(farm_id=farm.id, **data)
    db.add(reading)
    db.commit()
    return reading
