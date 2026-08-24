from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from app import models, database
from app.auth import get_current_user
from datetime import datetime, timezone
from app.schemas import RenameChatRequest 
from app.schemas import ChatInfo
from app.utils.logging_utils import ensure_timezone_aware
import logging
import json

logger = logging.getLogger(__name__)


router = APIRouter(tags=["Chat"])

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

#  MODELES Pydantic pour les réponses

class StartChatRequest(BaseModel):
    session_id: Optional[int] = None  # Si fourni, créer chat pour session existante
    request_text: Optional[str] = "Nouvelle session de chat"
    description: Optional[str] = "Session initialisée via start_chat"
    provider: Optional[str] = "aws"
    chat_name: Optional[str] = "Nouveau Chat"

class StartChatResponse(BaseModel):
    session_id: int
    chat_id: int
    state: str
    mode: str
    message: str

class RenameChatResponse(BaseModel):
    message: str


class MessageInfo(BaseModel):
    id: int
    chat_id: int
    session_id: int
    sender: str
    text: str
    created_at: str
    extra: Optional[dict] = None  # JSON field for available_instances, state, etc.

class GetMessagesResponse(BaseModel):
    chat_id: int
    session_id: int
    session_state: str
    session_mode: str
    messages: List[MessageInfo]

class SessionStateResponse(BaseModel):
    session_id: int
    state: str

class SwitchToDACRequest(BaseModel):
    session_id: int

class SwitchToDACResponse(BaseModel):
    success: bool
    mode: str
    state: str
    message: str

#  Créer un nouveau chat lié à une session
@router.post("/start_chat", response_model=StartChatResponse, summary="Créer un nouveau chat + session pour l'utilisateur connecté")
def start_chat(
    payload: StartChatRequest = Body(default_factory=StartChatRequest),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    logger.info(f" start_chat appelé pour user_id={user.id}, payload={payload}")
    data = payload or StartChatRequest()
    provider = (data.provider or "aws").lower()

    # Si session_id est fourni, utiliser la session existante
    if data.session_id:
        session = db.query(models.Session).filter(
            models.Session.id == data.session_id,
            models.Session.user_id == user.id
        ).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session non trouvée")
    else:
        # Créer une nouvelle session
        session = models.Session(
            user_id=user.id,
            state="awaiting_intent",  # Démarrer en DAC awaiting_intent
            mode="dac",  # Initialiser en mode DAC pour le chat_message route
            provider=provider,
            request_text=data.request_text,
            description=data.description,
            created_at=datetime.now(timezone.utc),
        )
        db.add(session)
        db.commit()
        db.refresh(session)

    # Créer le chat associé
    chat = models.Chat(
        session_id=session.id,
        name=data.chat_name or "Nouveau Chat",
        chat_mode="dac",  # Initialiser en mode DAC
        created_at=datetime.now(timezone.utc)
    )
    db.add(chat)
    db.commit()
    db.refresh(chat)

    return {
        "session_id": session.id,
        "chat_id": chat.id,
        "state": session.state,
        "mode": session.mode,
        "message": " Mode DAC activé. Tu peux maintenant configurer l'infrastructure AWS. Décris ta demande!"
    }

#  Renommer un chat


@router.post("/rename_chat", summary="Renommer un chat")
def rename_chat(
    payload: RenameChatRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    chat = (
        db.query(models.Chat)
        .join(models.Session)
        .filter(models.Chat.id == payload.chat_id, models.Session.user_id == user.id)
        .first()
    )

    if not chat:
        raise HTTPException(status_code=404, detail="Chat introuvable.")

    chat.name = payload.new_name
    db.commit()
    db.refresh(chat)

    return {"message": f"Chat renommé en '{chat.name}'"}

#  Lister les chats d'une session
@router.get("/list_chats", response_model=List[ChatInfo], summary="Lister tous les chats d'une session")
def list_chats(
    session_id: int = Query(..., description="ID de la session"),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    session = db.query(models.Session).filter_by(id=session_id, user_id=user.id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session non trouvée.")

    chats = db.query(models.Chat).filter_by(session_id=session.id).order_by(models.Chat.created_at.desc()).all()

    return [
        ChatInfo(chat_id=c.id, name=c.name, created_at=ensure_timezone_aware(c.created_at).isoformat())
        for c in chats
    ]

#  Récupérer les messages d'un chat
@router.get("/get_messages", response_model=GetMessagesResponse, summary="Récupérer tous les messages d'un chat")
def get_messages(
    chat_id: int = Query(..., description="ID du chat"),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"[GET /chats/get_messages] START - user_id={user.id}, chat_id={chat_id}")
    
    chat = (
        db.query(models.Chat)
        .join(models.Session)
        .filter(models.Chat.id == chat_id, models.Session.user_id == user.id)
        .first()
    )
    
    if not chat:
        logger.error(f"[GET /chats/get_messages] Chat {chat_id} not found for user {user.id}")
        raise HTTPException(status_code=404, detail="Chat non trouvé.")
    
    logger.info(f"[GET /chats/get_messages] Chat found: {chat.id}, session_id={chat.session_id}, name='{chat.name}'")

    messages = db.query(models.Message).filter_by(chat_id=chat.id).order_by(models.Message.created_at).all()
    logger.info(f"[GET /chats/get_messages] Found {len(messages)} messages for chat {chat_id}")
    for m in messages:
        logger.info(f"  - Message id={m.id}, sender={m.sender}, text_len={len(m.text)}, created_at={m.created_at}")

    # Ajout récupération session
    session = db.query(models.Session).filter_by(id=chat.session_id, user_id=user.id).first()
    session_state = getattr(session, "state", None) or "awaiting_intent"
    session_mode = getattr(session, "mode", None) or "dac"

    return {
        "chat_id": chat.id,
        "session_id": chat.session_id,
        "session_state": session_state,
        "session_mode": session_mode,
        "messages": [
            MessageInfo(
                id=m.id,
                chat_id=chat.id,
                session_id=chat.session_id,
                sender=m.sender,
                text=m.text,
                created_at=ensure_timezone_aware(m.created_at).isoformat(),
                extra=json.loads(m.extra) if m.extra and isinstance(m.extra, str) else m.extra
            )
            for m in messages
        ]
    }

from fastapi import Path

@router.delete("/{chat_id}", summary="Supprimer un chat (et ses messages)")
def delete_chat(
    chat_id: int = Path(..., description="ID du chat à supprimer"),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    chat = (
        db.query(models.Chat)
        .join(models.Session)
        .filter(models.Chat.id == chat_id, models.Session.user_id == user.id)
        .first()
    )

    if not chat:
        raise HTTPException(status_code=404, detail="Chat introuvable.")

    session_id = chat.session_id

    #  Supprimer aussi les messages liés
    db.query(models.Message).filter_by(chat_id=chat.id).delete()

    db.delete(chat)
    db.commit()

    #  Récupérer les chats restants de l'utilisateur (triés par date desc)
    remaining_chats = (
        db.query(models.Chat)
        .join(models.Session, models.Session.id == models.Chat.session_id)
        .filter(models.Session.user_id == user.id)
        .order_by(models.Chat.created_at.desc())
        .all()
    )

    remaining_count = len(remaining_chats)

    next_chat_payload = None

    if remaining_count == 0:
        #  Aucun chat restant -> auto-créer un chat par défaut
        new_chat = models.Chat(
            session_id=session_id,
            name="Nouveau Chat",
            created_at=datetime.now(timezone.utc),
        )
        db.add(new_chat)
        db.commit()
        db.refresh(new_chat)

        next_chat_payload = {
            "id": new_chat.id,
            "name": new_chat.name,
            "session_id": new_chat.session_id,
            "created_at": ensure_timezone_aware(new_chat.created_at).isoformat(),
        }
    else:
        #  Des chats restent -> choisir le plus récent
        next_chat = remaining_chats[0]
        next_chat_payload = {
            "id": next_chat.id,
            "name": next_chat.name,
            "session_id": next_chat.session_id,
            "created_at": ensure_timezone_aware(next_chat.created_at).isoformat(),
        }

    return {
        "deleted": True,
        "deleted_chat_id": chat_id,
        "remaining_chats_count": remaining_count,
        "next_chat": next_chat_payload,
    }


@router.get("/list_all_chats", response_model=List[ChatInfo], summary="Lister tous les chats de l'utilisateur")
def list_all_chats(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    chats = (
        db.query(models.Chat)
        .join(models.Session)
        .filter(models.Session.user_id == user.id)
        .order_by(models.Chat.created_at.desc())
        .all()
    )

    return [
        {
            "chat_id": c.id,
            "name": c.name,
            "session_id": c.session_id,
            "created_at": ensure_timezone_aware(c.created_at).isoformat() if c.created_at else None,
            # le mode vient TOUJOURS de la session
            "mode": c.session.mode,
        }
        for c in chats
    ]





@router.get("/get_session_state", response_model=SessionStateResponse, summary="Obtenir l'état actuel d'une session")
def get_session_state(
    session_id: int = Query(..., description="ID de la session"),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    session = db.query(models.Session).filter_by(id=session_id, user_id=user.id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session non trouvée.")

#  Passer de Free Chat à DAC (Distributed Audit & Configure)
@router.post("/switch_to_dac", response_model=SwitchToDACResponse, summary="Passer du mode Free Chat au mode DAC")
def switch_to_dac(
    payload: SwitchToDACRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    from app.services.aws_credentials_service import has_user_aws_credentials
    
    session = db.query(models.Session).filter_by(id=payload.session_id, user_id=user.id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session non trouvée.")
    
    # Vérifier que les credentials AWS existent
    if not has_user_aws_credentials(user.id, db):
        raise HTTPException(
            status_code=400,
            detail="Credentials AWS manquantes. Ajoutez-les via /user/aws-credentials avant d'activer le mode DAC."
        )
    
    # Passer au mode DAC
    session.mode = "dac"
    session.state = "awaiting_provider"  # État initial pour DAC workflow
    db.commit()
    db.refresh(session)
    
    return {
        "success": True,
        "mode": session.mode,
        "state": session.state,
        "message": "Mode DAC activated! You can now use advanced AWS features."
    }

    return {"session_id": session.id, "state": session.state}

#  /  ROUTE DE BASCULEMENT MODE (UNIQUE + SOURCE DE VÉRITÉ)
@router.post("/{chat_id}/switch_mode", summary="Basculer le mode du chat (free/dac) — SOURCE DE VÉRITÉ")
def switch_chat_mode(
    chat_id: int,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """
    Route unique pour basculer le mode d'un chat.
    Met à jour chat.mode + session.mode + session.state.
    SOURCE DE VÉRITÉ côté backend.
    """
    mode = payload.get("mode")
    
    logger.info(f"[switch_mode] START: chat_id={chat_id} mode={mode} user={user.id}")
    
    if mode not in ("free", "dac"):
        logger.error(f"[switch_mode] Invalid mode: {mode}")
        raise HTTPException(status_code=400, detail="Invalid mode (must be 'free' or 'dac')")
    
    # Vérifier que le chat existe et appartient à l'utilisateur
    chat = (
        db.query(models.Chat)
        .join(models.Session)
        .filter(models.Chat.id == chat_id, models.Session.user_id == user.id)
        .first()
    )
    
    if not chat:
        logger.error(f"[switch_mode] Chat not found: {chat_id} for user {user.id}")
        raise HTTPException(status_code=404, detail="Chat not found")
    
    session = chat.session
    
    # SOURCE DE VÉRITÉ: mise à jour atomique
    logger.info(f"[switch_mode] Updating: chat.chat_mode={mode}, session.mode={mode}")
    chat.chat_mode = mode
    session.mode = mode
    
    # RESET ÉTAT SI FREE
    if mode == "free":
        session.state = "free_chat"
        session.current_intent = None
        logger.info(f"[switch_mode] FREE MODE: reset state=free_chat, current_intent=None")
    else:
        # DAC: reset à awaiting_intent
        session.state = "awaiting_intent"
        logger.info(f"[switch_mode] DAC MODE: reset state=awaiting_intent")
    
    db.commit()
    db.refresh(chat)
    db.refresh(session)
    
    logger.info(f"[switch_mode] Success: chat.chat_mode={chat.chat_mode}, session.mode={session.mode}, state={session.state}")
    
    return {
        "status": "ok",
        "chat_id": chat.id,
        "chat_mode": chat.chat_mode,
        "session_mode": session.mode,
        "session_state": session.state,
    }