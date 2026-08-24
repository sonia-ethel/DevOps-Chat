# © 2024–2026 TOURE Arnaud Patrick
# Licensed under the MIT License

from fastapi import APIRouter, Depends, HTTPException, Query
from app.models.user import User
from sqlalchemy.orm import Session
from app import models, database
from app.auth import get_current_user
from datetime import datetime, timezone
from pydantic import BaseModel
from typing import Optional
from app import schemas
import json
from typing import List

router = APIRouter()

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Création de session
@router.post(
    "/sessions/create",
    tags=["Sessions"],
    summary="Créer une nouvelle session",
    response_model=schemas.SessionResponse
)
def create_session(
    payload: schemas.SessionCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    """
    ##  Créer une session

    Permet à l'utilisateur de créer une **nouvelle session de configuration**, sans provider associé. Le provider pourra être ajouté ensuite via `/providers/create`.

    ###  Authentification requise : oui (JWT)

    ###  Corps de la requête (JSON) :
    ```json
    {
      "request_text": "Déployer 2 machines Ubuntu",
      "description": "Test de génération Terraform"
    }
    ```

    ###  Réponse :
    ```json
    {
      "id": 5,
      "user_id": 1,
      "state": "ready",
      "request_text": "Déployer 2 machines Ubuntu",
      "description": "Test de génération Terraform",
      "created_at": "2025-07-21T15:32:00"
    }
    ```

    ###  Erreurs possibles :
    - 401 : Utilisateur non authentifié
    """
    session = models.Session(
        user_id=user.id,
        state="awaiting_intent",
        request_text=payload.request_text,
        description=payload.description,
        created_at=datetime.now(timezone.utc)
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    return session


# Nouvelle route sécurisée — récupère les instances de l'utilisateur connecté
@router.get(
    "/sessions/available-instances",
    tags=["Sessions"],
    summary="Lister les instances prêtes à être configurées"
)
def get_available_instances(
    session_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    instances = (
        db.query(models.Instance)
        .join(models.Session)
        .filter(
            models.Session.user_id == user.id,
            models.Instance.session_id == session_id
        )
        .all()
    )

    result = []
    for inst in instances:
        result.append({
            "id": inst.id,
            "instance_id": inst.instance_id,
            "ip": inst.public_ip,
            "ssh_user": inst.ssh_user,
            "private_key": inst.ssh_private_key,
            "ssm_managed": bool(getattr(inst, "ssm_managed", False)),
            "connection_method": str(inst.connection_method) if getattr(inst, "connection_method", None) else None,
        })

    return result


# Récupérer toutes les sessions de l'utilisateur connecté


@router.get(
    "/sessions/list",
    tags=["Sessions"],
    summary="Lister les sessions de l'utilisateur connecté",
    response_model=List[schemas.SessionResponse]
)
def list_user_sessions(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    return (
        db.query(models.Session)
        .filter_by(user_id=user.id)
        .order_by(models.Session.created_at.desc())
        .all()
    )

@router.get(
    "/sessions/or-create",
    tags=["Sessions"],
    summary="Obtenir ou créer la session Free Chat de l'utilisateur",
    response_model=schemas.SessionResponse
)
def get_or_create_session(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    """
     GET ou CREATE Session
    
    Logique:
    1. Chercher la session "Free Chat" la plus récente de l'user
    2. Si existe -> la retourner
    3. Si n'existe pas -> en créer une nouvelle avec state="free"
    
    Cet endpoint garantit que chaque utilisateur authentifié a TOUJOURS une session.
    
    Appelé par le frontend au démarrage (ou avant d'utiliser Free Chat).
    Élimine le besoin de créer manuellement une session.
    
    ### Réponse:
    ```json
    {
      "id": 42,
      "user_id": 1,
      "state": "free",
      "mode": "free",
      "created_at": "2026-01-28T10:30:00"
    }
    ```
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # 1⃣ Chercher session existante (la plus récente)
    existing_session = db.query(models.Session).filter_by(
        user_id=user.id
    ).order_by(models.Session.created_at.desc()).first()
    
    if existing_session:
        logger.info(f"[SessionMgr] Found existing session {existing_session.id} for user {user.id}")
        return existing_session
    
    # Créer nouvelle session si absent
    logger.info(f"[SessionMgr] Creating new Free Chat session for user {user.id}")
    new_session = models.Session(
        user_id=user.id,
        state="free",
        mode="free",
        request_text="Free Chat Mode",
        created_at=datetime.now(timezone.utc)
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    
    logger.info(f"[SessionMgr] Created new session {new_session.id}")
    return new_session


@router.get("/sessions/{session_id}", tags=["Sessions"])
def get_session_by_id(
    session_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    """
     Retourne la session demandée si elle existe et appartient à l'utilisateur.
    """
    session = db.query(models.Session).filter_by(id=session_id, user_id=user.id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session introuvable.")

    return {
        "id": session.id,
        "request_text": session.request_text,
        "provider": session.provider,
        "state": session.state,
        "created_at": session.created_at,
    }


@router.patch("/sessions/{session_id}/state")
def update_session_state(
    session_id: int, 
    state: str = Query(..., description="New state for the session"), 
    db: Session = Depends(get_db), 
    user: User = Depends(get_current_user)
):
    session = db.query(models.Session).filter_by(id=session_id, user_id=user.id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session introuvable")
    session.state = state
    db.commit()
    return {"success": True, "state": state}
