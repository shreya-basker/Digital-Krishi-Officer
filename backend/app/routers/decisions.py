from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import services
from app.db import get_db
from app.engine.explain import DISCLAIMER
from app.engine.features import signal_cards
from app.ingestion.weather import daily_summary
from app.models import CropCycle, Farm, Feedback, Recommendation, User
from app.schemas import FeedbackIn, RecommendationOut
from app.security import get_current_user, get_owned_farm

router = APIRouter(tags=["decisions"])

FEEDBACK_STATUS = {"accept": "accepted", "reject": "rejected", "done": "done"}


@router.get("/farms/{farm_id}/signals")
def farm_signals(farm_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    farm = get_owned_farm(db, user, farm_id)
    state = services.farm_state(db, farm)
    return {
        "signals": signal_cards(state.context),
        "context": state.context.as_dict(),
        "forecast": daily_summary(state.forecast) if state.forecast else [],
        "weather_fetched_at": state.weather_fetched_at,
    }


@router.get("/farms/{farm_id}/recommendations")
def farm_recommendations(
    farm_id: int, refresh: bool = False, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    farm = get_owned_farm(db, user, farm_id)
    cycle = services.require_cycle(farm)
    recs = services.current_recommendations(db, cycle)
    if refresh or not recs:
        recs = services.generate_recommendations(db, farm, user.language)
    return {
        "recommendations": [RecommendationOut.model_validate(r) for r in recs],
        "disclaimer": DISCLAIMER,
    }


@router.post("/recommendations/{rec_id}/feedback", response_model=RecommendationOut)
def recommendation_feedback(
    rec_id: int, body: FeedbackIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    rec = db.get(Recommendation, rec_id)
    if rec is None or rec.crop_cycle.farm.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recommendation not found")
    db.add(Feedback(recommendation_id=rec.id, **body.model_dump()))
    rec.status = FEEDBACK_STATUS[body.action]
    db.commit()
    return rec


@router.get("/evaluation/summary")
def evaluation_summary(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Planned-evaluation metrics from slide 11 that the prototype can already measure."""
    rows = db.execute(
        select(Recommendation.rule_id, Recommendation.action_type, Recommendation.status, func.count())
        .group_by(Recommendation.rule_id, Recommendation.action_type, Recommendation.status)
    ).all()
    by_rule: dict[str, dict] = {}
    for rule_id, action_type, rec_status, n in rows:
        entry = by_rule.setdefault(
            rule_id, {"rule_id": rule_id, "action_type": action_type, "shown": 0, "accepted": 0, "rejected": 0, "done": 0}
        )
        if rec_status in ("accepted", "rejected", "done"):
            entry[rec_status] += n
        entry["shown"] += n  # every generated recommendation was shown at least once
    for entry in by_rule.values():
        responded = entry["accepted"] + entry["rejected"] + entry["done"]
        entry["acceptance_rate"] = round((entry["accepted"] + entry["done"]) / responded, 2) if responded else None
    ratings = db.execute(select(func.avg(Feedback.rating), func.count(Feedback.rating))).one()
    totals = {k: sum(e[k] for e in by_rule.values()) for k in ("shown", "accepted", "rejected", "done")}
    responded = totals["accepted"] + totals["rejected"] + totals["done"]
    return {
        "totals": totals,
        "acceptance_rate": round((totals["accepted"] + totals["done"]) / responded, 2) if responded else None,
        "average_rating": round(float(ratings[0]), 2) if ratings[0] is not None else None,
        "ratings": ratings[1],
        "active_crop_cycles": db.scalar(select(func.count(CropCycle.id)).where(CropCycle.status == "active")),
        "farms": db.scalar(select(func.count(Farm.id))),
        "by_rule": sorted(by_rule.values(), key=lambda e: e["shown"], reverse=True),
    }
