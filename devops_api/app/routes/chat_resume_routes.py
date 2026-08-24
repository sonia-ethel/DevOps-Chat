from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, database
from app.auth import get_current_user

router = APIRouter(prefix="/chats", tags=["Chat"])

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/{chat_id}/resume", summary="Reprendre un chat: renvoie session_id + état")
def resume_chat(
    chat_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    chat = db.query(models.Chat).filter_by(id=chat_id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat introuvable")

    session = db.query(models.Session).filter_by(id=chat.session_id, user_id=user.id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session introuvable pour ce chat")

    state = session.state or "awaiting_intent"
    mode = getattr(session, "mode", None) or "dac"

    # Règle simple: on désactive seulement si exécution en cours
    can_chat = state not in {"executing", "running", "in_progress"}

    return {
        "chat_id": chat.id,
        "session_id": session.id,
        "session_state": state,
        "session_mode": mode,
        "can_chat": can_chat,
    }
