from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import CropCycle, Farm, Feedback, Query, Recommendation, User
from app.schemas import LoginIn, RegisterIn, TokenOut, UserOut, UserUpdate
from app.security import create_token, get_current_user, hash_password, verify_password

router = APIRouter(tags=["auth"])


@router.post("/auth/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.phone == body.phone)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Phone number already registered")
    user = User(phone=body.phone, name=body.name, language=body.language, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    return TokenOut(access_token=create_token(user.id), user=UserOut.model_validate(user))


@router.post("/auth/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.phone == body.phone))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong phone number or password")
    return TokenOut(access_token=create_token(user.id), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.put("/me", response_model=UserOut)
def update_me(body: UserUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(user, field, value)
    db.commit()
    return user


@router.get("/me/stats")
def my_stats(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    my_recs = (
        select(Recommendation.id)
        .join(CropCycle)
        .join(Farm)
        .where(Farm.user_id == user.id)
    )
    responded = db.scalar(
        select(func.count(func.distinct(Feedback.recommendation_id))).where(Feedback.recommendation_id.in_(my_recs))
    )
    accepted = db.scalar(
        select(func.count(Recommendation.id)).where(
            Recommendation.id.in_(my_recs), Recommendation.status.in_(["accepted", "done"])
        )
    )
    return {
        "queries": db.scalar(select(func.count(Query.id)).where(Query.user_id == user.id)),
        "open_recommendations": db.scalar(
            select(func.count(Recommendation.id)).where(
                Recommendation.id.in_(my_recs), Recommendation.status.in_(["shown", "accepted"])
            )
        ),
        "responded_recommendations": responded,
        "acceptance_rate": round(accepted / responded, 2) if responded else None,
    }
