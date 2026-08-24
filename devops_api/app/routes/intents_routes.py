# app/routes/intents_routes.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any

from pydantic import BaseModel

from app import models, database
from app.auth import get_current_user
from app.schemas import IntentCreate, IntentResponse  # legacy schema (avec intent_type)
# Parseur multi-intents qui renvoie des actions avec a.raw (sous-prompt)
from app.services.intent_parser import parse_intent

router = APIRouter()


def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ===== Nouveau schéma sans intent_type NI runtime pour les flux multi-intents =====
class PromptOnly(BaseModel):
    session_id: int
    prompt: str


# ===== Helper: inférer le runtime depuis type/mode détectés par le parseur =====
def _infer_runtime(intent_type: Optional[str], mode: Optional[str]) -> str:
    it = (intent_type or "").lower()
    md = (mode or "").lower()

    if it == "create":
        return "infra"            # Terraform (compute)
    if it == "configure":
        if md == "system":
            return "system"       # Ansible
        if md in {"infra", "mixed"}:
            return "infra"        # Terraform (infra ou partie infra du mixed)
        # par défaut, on considère que c'est de l'infra si le mode est inconnu
        return "infra"
    if it == "audit":
        return "system"           # Ansible (lynis/auditd)
    if it == "kubernetes":
        return "kubernetes"
    return "infra"


# --- Endpoint legacy (1 seule intent) : on le garde tel quel ---
@router.post(
    "/intents/create",
    tags=["Deprecated"],
    summary="Ajouter une intention à une session (legacy: 1 seule intent)",
    response_model=IntentResponse
)
def create_intent(
    intent: IntentCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    session = db.query(models.Session).filter_by(
        id=intent.session_id,
        user_id=user.id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session non trouvée.")

    existing = db.query(models.Intent).filter_by(
        session_id=intent.session_id,
        intent_type=intent.intent_type,
        prompt=intent.prompt
    ).first()
    if existing:
        return existing

    # Enrichit configure_* si besoin (le prompt reste celui fourni)
    domain = mode = None
    if intent.intent_type == "configure":
        parsed = parse_intent(intent.prompt)
        cfg = next((a for a in (parsed.actions or []) if getattr(a, "type", None) == "configure"), None)
        if cfg:
            domain = (getattr(cfg, "domains", None) or [None])[0]
            mode = getattr(cfg, "mode", None)

    new_intent = models.Intent(
        session_id=intent.session_id,
        intent_type=intent.intent_type,
        prompt=intent.prompt,               # legacy : conserve le prompt complet
        runtime=(intent.runtime or _infer_runtime(intent.intent_type, mode)),
        configure_domain=domain,
        configure_mode=mode,
    )
    db.add(new_intent)
    db.commit()
    db.refresh(new_intent)
    return new_intent


# --- Détection sans création (preview/debug) ---
@router.post(
    "/intents/detect",
    tags=["Intents"],
    summary="Détecter les intentions (multi-intents) sans créer",
)
def detect_intents_preview(
    intent: PromptOnly,
    user: models.User = Depends(get_current_user)
):
    parsed = parse_intent(intent.prompt)
    actions: List[Dict[str, Any]] = []
    for a in (parsed.actions or []):
        itype = getattr(a, "type", None)
        mode = getattr(a, "mode", None)
        inferred_runtime = _infer_runtime(itype, mode)
        actions.append({
            "type": itype,
            "provider": getattr(a, "provider", None),
            "vms": [{"os": vm.os, "count": vm.count} for vm in (getattr(a, "vms", None) or [])],
            "domains": getattr(a, "domains", None),
            "mode": mode,
            "runtime": inferred_runtime,  #  ajouté
            "raw": (getattr(a, "raw", None) or intent.prompt).strip(),  # sous-prompt extrait ou fallback
        })
    return {
        "actions": actions,
        "raw": parsed.raw,  # prompt complet
    }


# --- Nouveau : créer 1..N intents depuis un prompt (enregistrant le sous-prompt) ---
@router.post(
    "/intents/create_from_prompt",
    tags=["Intents"],
    summary="Créer plusieurs intentions (multi-intents) depuis un prompt (segmenté)",
    response_model=List[IntentResponse]
)
def create_intents_from_prompt(
    intent: PromptOnly,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    session = db.query(models.Session).filter_by(
        id=intent.session_id,
        user_id=user.id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session non trouvée.")

    parsed = parse_intent(intent.prompt)
    if not parsed.actions:
        raise HTTPException(status_code=422, detail="Aucune intention détectée dans le prompt.")

    created: List[models.Intent] = []

    for a in parsed.actions:
        itype = getattr(a, "type", None)  # "create" | "configure" | "audit" | "kubernetes"
        subprompt = (getattr(a, "raw", "") or intent.prompt).strip()  # sous-prompt
        mode = getattr(a, "mode", None)
        inferred_runtime = _infer_runtime(itype, mode)

        if itype == "configure":
            domains = getattr(a, "domains", None) or [None]

            for d in domains:
                # déduplication par (session, type, sous-prompt, domaine, mode)
                existing = db.query(models.Intent).filter_by(
                    session_id=intent.session_id,
                    intent_type=itype,
                    prompt=subprompt,
                    configure_domain=d,
                    configure_mode=mode,
                ).first()
                if existing:
                    created.append(existing)
                    continue

                obj = models.Intent(
                    session_id=intent.session_id,
                    intent_type=itype,
                    prompt=subprompt,           # enregistre le sous-prompt ciblé
                    runtime=inferred_runtime,   #  runtime auto
                    configure_domain=d,
                    configure_mode=mode,
                )
                db.add(obj)
                created.append(obj)
            continue

        # create / audit / kubernetes
        existing = db.query(models.Intent).filter_by(
            session_id=intent.session_id,
            intent_type=itype,
            prompt=subprompt
        ).first()
        if existing:
            created.append(existing)
            continue

        obj = models.Intent(
            session_id=intent.session_id,
            intent_type=itype,
            prompt=subprompt,                # enregistre le sous-prompt ciblé
            runtime=inferred_runtime,        #  runtime auto
        )
        db.add(obj)
        created.append(obj)

    db.commit()
    for o in created:
        db.refresh(o)

    return created


@router.get(
    "/intents/by_session/{session_id}",
    tags=["Intents"],
    summary="Lister les intentions d'une session",
    response_model=list[IntentResponse]
)
def list_intents_by_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    session = db.query(models.Session).filter_by(
        id=session_id,
        user_id=user.id
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Session non trouvée.")

    return session.intents
