import base64
import binascii

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import llm, services
from app.db import get_db
from app.models import Query, User
from app.schemas import ChatIn, ChatOut
from app.security import get_current_user, get_owned_farm

router = APIRouter(tags=["chat"])

MAX_IMAGE_BYTES = 5 * 1024 * 1024


@router.post("/chat", response_model=ChatOut)
def chat(body: ChatIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    text = body.text.strip()
    if not text and not body.image_base64:
        raise HTTPException(422, "Type a question or upload an image")
    if body.image_base64:
        try:
            size = len(base64.b64decode(body.image_base64, validate=True))
        except binascii.Error:
            raise HTTPException(422, "Image is not valid base64")
        if size > MAX_IMAGE_BYTES:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Image must be under 5 MB")

    farm_context = None
    if body.farm_id is not None:
        farm = get_owned_farm(db, user, body.farm_id)
        ctx, recs = None, []
        if farm.active_cycle:
            ctx = services.farm_state(db, farm).context
            recs = services.current_recommendations(db, farm.active_cycle)
        farm_context = services.context_for_chat(farm, ctx, recs)

    answer = llm.chat(text, body.image_base64, body.image_mime, farm_context, user.language)
    query = Query(user_id=user.id, farm_id=body.farm_id, text=text, had_image=bool(body.image_base64), answer=answer)
    db.add(query)
    db.commit()
    return ChatOut(answer=answer, query_id=query.id)


@router.get("/chat/history")
def chat_history(limit: int = 20, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Query).where(Query.user_id == user.id).order_by(Query.created_at.desc()).limit(min(limit, 100))
    ).all()
    return [
        {"id": q.id, "text": q.text, "had_image": q.had_image, "answer": q.answer, "created_at": q.created_at}
        for q in reversed(rows)
    ]
