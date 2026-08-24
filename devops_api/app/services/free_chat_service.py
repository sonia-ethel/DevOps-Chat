# app/services/free_chat_service.py
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app import models
from app.services.chat_service import generate_free_chat_response
from app.utils.logging_utils import ensure_timezone_aware

logger = logging.getLogger(__name__)

DEFAULT_TITLES = {"Nouveau chat", "Chat initial", "Chat de découverte", "Nouveau Chat"}

async def handle_free_chat_message(
    *,
    db: Session,
    user: models.User,
    session_id: int,
    chat_id: int,
    text: str,
):
    logger.info(f"[free_chat_service] START: session={session_id} chat={chat_id} user={user.id}")
    
    # 1) Validate session belongs to user
    session = db.query(models.Session).filter_by(id=session_id, user_id=user.id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # 2) Validate chat belongs to session
    chat = db.query(models.Chat).filter_by(id=chat_id, session_id=session_id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    # 3) count messages (for auto rename)
    message_count = db.query(models.Message).filter_by(chat_id=chat_id).count()
    is_first_message = message_count == 0

    #  NOTE: User message is already persisted by the endpoint (chat_creation_routes.py)
    # This handler only persists the bot response
    # Fetch the user message from DB (it was just persisted by the endpoint)
    user_message = db.query(models.Message).filter_by(
        chat_id=chat_id,
        sender="user",
        text=text,
    ).order_by(models.Message.created_at.desc()).first()
    
    if not user_message:
        raise RuntimeError(f"User message not found in DB (chat={chat_id}, text={text[:30]})")

    # 5) generate bot response
    bot_text = await generate_free_chat_response(user_message=text)

    # 6) persist bot msg (only the bot response)
    bot_message = models.Message(
        session_id=session_id,
        chat_id=chat_id,
        sender="bot",
        text=bot_text
    )
    db.add(bot_message)
    db.flush()

    # 7) auto rename
    if is_first_message and (chat.name in DEFAULT_TITLES):
        auto_title = text[:40] if len(text) <= 40 else text[:37] + "..."
        chat.name = auto_title

    db.commit()
    # user_message already in session, no need to refresh
    db.refresh(bot_message)
    db.refresh(chat)

    logger.info(f"[free_chat_service] message persisted: user_msg={user_message.id} bot_msg={bot_message.id}")

    # Standardiser la réponse pour qu'elle soit compatible avec le front (style DAC)
    return {
        "status": "ok",
        "mode": "free",
        "chat_id": chat.id,
        "session_id": session.id,
        "chat_title": chat.name,
        "is_first_message": is_first_message,
        # Messages array (pour compatibilité avec front qui attend messages)
        "messages": [
            {
                "id": user_message.id,
                "chat_id": user_message.chat_id,
                "session_id": user_message.session_id,
                "sender": "user",
                "text": user_message.text,
                "created_at": ensure_timezone_aware(user_message.created_at).isoformat() if user_message.created_at else None,
            },
            {
                "id": bot_message.id,
                "chat_id": bot_message.chat_id,
                "session_id": bot_message.session_id,
                "sender": "bot",
                "text": bot_message.text,
                "created_at": ensure_timezone_aware(bot_message.created_at).isoformat() if bot_message.created_at else None,
            },
        ],
        # Champs legacy (si front les utilise)
        "bot_message": bot_message.text,
        "user_message": {
            "id": user_message.id,
            "chat_id": user_message.chat_id,
            "session_id": user_message.session_id,
            "sender": user_message.sender,
            "text": user_message.text,
            "created_at": ensure_timezone_aware(user_message.created_at).isoformat() if user_message.created_at else None,
        },
    }
