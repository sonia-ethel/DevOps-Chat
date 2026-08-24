# © 2024–2026 TOURE Arnaud Patrick
# Licensed under the MIT License

# =============================================================
# Imports et dépendances
# Rôle : Importation des modules nécessaires
# =============================================================

import logging
import asyncio
import time
import uuid
import json
import re
import httpx
import os
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from app.services.gpt_service import analyze_intent
from app import paths
from sqlalchemy.orm import Session
from app import models, database
from app.security.rate_limit import limiter
from app.auth import get_current_user
from app.services.chat_service import detect_intent_type, detect_intent_and_action, extract_params_from_text
from app.services.aws_credentials_service import get_user_aws_credentials, has_user_aws_credentials, validate_aws_credentials
from app.services.aws_sync_service import sync_aws_instances_to_db
from app.services.p04_p05_chat_intents import detect_ssm_check_intent
from app.services.detect_intent_catalog import detect_intent_with_catalog
from app.services.config_catalog import get_action_by_id
from app.services import execution_service
from app.services.free_chat_service import handle_free_chat_message
from app.schemas.schemas import ChatMessageRequest
from app.schemas.understanding_schema import UnderstandingDisplay
from app.settings import settings


def parse_json_response(text: str) -> dict:
    """Safely parse JSON from GPT response (handles markdown blocks, prefixes, etc.)."""
    if not text:
        raise ValueError("empty response")
    
    # 1) Retirer les fences markdown ```json ... ```
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    
    # 2) Si le modèle a préfixé par "json"
    if cleaned.lower().startswith("json"):
        cleaned = cleaned[4:].strip()
    
    # 3) Extraire le premier bloc {...}
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("no_json_object_found")
    
    return json.loads(cleaned[start:end+1])

DAC_HELP_MESSAGE = (
    "Bienvenue dans DevOps-as-a-Chat (DAC).\n"
    "Voici ce que je peux faire :\n"
    "- create : créer une infrastructure (AWS/Azure/GCP)\n"
    "- configure : installer/configurer des services (nginx, docker, ufw...)\n"
    "- audit : audit sécurité (lynis/auditd)\n"
    "- monitoring : collecter un snapshot de métriques\n"
    "- ssm status : diagnostic SSM + bootstrap\n"
    "- vpc status : diagnostic VPC / endpoints\n"
    "- liste des ressources : inventaire et synchronisation\n"
    "- supprimer : mode suppression\n"
    "- annuler : revenir au menu\n"
    "Décris ta demande en une phrase."
)

# Initialize router
router = APIRouter()
logger = logging.getLogger(__name__)

# Free Chat is now handled by /chat/message endpoint only
# DAC mode is the only mode for /chat_creation/chat_message


def _audit_recipe_names_from_text(text_value: str) -> list[str]:
    text_lower = (text_value or "").lower()
    if "lynis" in text_lower:
        return ["lynis"]
    return ["ops_health", "security_basic"]

# =============================================================
# Fonction de récupération de session DB
# Rôle : Fournir une session à la base de données pour les routes
# =============================================================

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

# =============================================================
#  Bloc 1 — Route principale : /chat_message
# =============================================================
#  Fonction d'exécution asynchrone d'infrastructure 
# Rôle : Exécution en arrière-plan via TaskManager
# =============================================================

async def execute_infrastructure_creation(
    intent_id: int,
    session_id: int,
    user_id: int,
    auth_header: str,
    chat_id: int | None = None,
    progress_callback=None,
    db_session=None
):
    """
    Fonction d'exécution asynchrone pour la création d'infrastructure.
    Cette fonction est appelée par le TaskManager en arrière-plan.
    """
    # Réouvrir la session DB pour le thread asynchrone
    db = database.SessionLocal()
    try:
        # Étape 1: Génération du fichier
        if progress_callback:
            progress_callback("generation_start", " Génération du fichier d'infrastructure", 10.0)
            
        async with httpx.AsyncClient(timeout=120.0) as client:
            generate_resp = await client.post(
                f"{settings.BACKEND_BASE_URL}/generate",
                json={
                    "session_id": session_id,
                    "intent_id": intent_id,
                    "auto_create_executions": True
                },
                headers={
                    "Authorization": auth_header,
                    "Idempotency-Key": f"dac-generate-s{session_id}-i{intent_id}",
                }
            )
            
        if generate_resp.status_code != 200:
            raise Exception(f"Erreur génération: {generate_resp.text}")

        json_data = generate_resp.json()
        
        # Vérifier le statut de la génération
        status = json_data.get("status")
        if status == "empty":
            raise Exception(json_data.get("message") or "Aucune étape détectée pour cette session")
        if status == "partial":
            errors = json_data.get("errors") or []
            details = " | ".join(str(e) for e in errors[:3]) if errors else json_data.get("message")
            raise Exception(details or "Génération partielle sans exécution créée")
        
        # Récupérer les exécutions créées automatiquement
        executions_created = json_data.get("executions_created", [])
        
        if not executions_created:
            errors = json_data.get("errors") or []
            details = " | ".join(str(e) for e in errors[:3]) if errors else json_data.get("message")
            raise Exception(details or "Aucune exécution créée par /generate")
        
        # Prendre la première exécution (normalement il n'y en a qu'une pour un intent simple)
        first_exec = executions_created[0]
        execution_id = first_exec.get("execution_id")
        file_id = first_exec.get("file_id")
        engine = first_exec.get("engine", "terraform")
        
        if not execution_id:
            raise Exception("execution_id manquant dans la réponse")
        
        if progress_callback:
            progress_callback("generation_complete", f" Fichier {engine} généré (ID: {file_id})", 20.0)
            progress_callback("execution_ready", f" Exécution créée (ID: {execution_id})", 30.0)
        
        if progress_callback:
            progress_callback("execution_ready", " Exécution prête", 30.0)

        # Étape 3: Exécution (partie longue avec Terraform)
        if progress_callback:
            progress_callback("execution_start", " Démarrage du déploiement", 35.0)

        # Récupérer l'exécution créée
        execution = db.query(models.Execution).filter_by(id=execution_id, user_id=user_id).first()
        if not execution:
            raise Exception("Execution introuvable après création")

        # Récupérer les credentials depuis le provider
        provider = db.query(models.Provider).filter_by(session_id=session_id).first()
        if not provider:
            raise Exception("Aucun provider associé")

        from app.utils.crypto import decrypt
        credentials = json.loads(decrypt(provider.encrypted_credentials))

        # Utiliser run_execution_by_id() pour passer par les handlers unifiés
        from app.services.execution_handlers import run_execution_by_id
        
        result = await run_execution_by_id(
            db=db,
            execution_id=execution_id,
            user_id=user_id,
        )

        return {
            "execution_id": execution_id,
            "result": result,
            "success": True
        }
        
    except Exception as e:
        if progress_callback:
            progress_callback("execution_error", f" Erreur: {str(e)}", None, "error")
        try:
            bg_session = db.query(models.Session).filter_by(id=session_id, user_id=user_id).first()
            bg_chat = db.query(models.Chat).filter_by(id=chat_id, session_id=session_id).first() if chat_id else None
            if not bg_chat:
                bg_chat = (
                    db.query(models.Chat)
                    .filter_by(session_id=session_id)
                    .order_by(models.Chat.created_at.desc())
                    .first()
                )
            if bg_session:
                bg_session.state = "awaiting_intent"
                bg_session.session_temp_data = None
            if bg_chat:
                db.add(models.Message(
                    session_id=session_id,
                    chat_id=bg_chat.id,
                    sender="bot",
                    text=f"Erreur création Terraform: {str(e)[:300]}\nTu peux corriger la demande puis relancer.",
                    extra={"state": "awaiting_intent", "error": str(e)[:500]},
                ))
            db.commit()
        except Exception as notify_error:
            db.rollback()
            logger.error(f"[CREATE_BACKGROUND_ERROR_NOTIFY_FAILED] {notify_error}")
        raise e
    finally:
        db.close()


# =============================================================
# Handler pour intent CONFIGURE - Nouveau système avec catalogue
# =============================================================

def handle_configure_intent(
    user: models.User,
    db: Session,
    chat: models.Chat,
    session: models.Session,
    text: str,
    detected_intent,  # DetectedIntent object
    send_bot_message,  # Function to send messages
) -> dict:
    """
    Gère l'intent "configure" avec le nouveau système catalogue.
    
    Cas 1: Action reconnue -> store pending_action et aller sélection VM
    Cas 2: Pas d'action + pas de last_action -> "Que veux-tu configurer?"
    Cas 3: Pas d'action + last_action existe -> "Relancer la dernière config?"
    Cas 4: Action ambigue -> Lister les candidates
    """
    from app.services.configure_only import get_available_instances_for_user
    
    # Cas 4: Action ambiguë
    if detected_intent.is_ambiguous():
        candidates_text = "\n".join([
            f"  • {c['label']} (`{c['id']}`)"
            for c in detected_intent.action_candidates[:3]
        ])
        return send_bot_message(
            f" Configuration ambiguë. Tu veux:\n{candidates_text}\n\nPrécise lequel.",
            "awaiting_intent"
        )
    
    # Cas 1: Action reconnue
    if detected_intent.action_id:
        action = get_action_by_id(detected_intent.action_id)
        if not action:
            return send_bot_message(
                f" Action inconnue: {detected_intent.action_id}",
                "awaiting_intent"
            )
        
        if not has_user_aws_credentials(user.id, db):
            return redirect_credentials_message()
        
        # Sync AWS
        try:
            creds_model = get_user_aws_credentials(user.id, db)
            if creds_model:
                from app.utils.crypto import decrypt
                aws_access = creds_model.access_key_id
                aws_secret = decrypt(creds_model.secret_access_key_encrypted)
                region = creds_model.region or "eu-north-1"
                
                sync_aws_instances_to_db(
                    db=db,
                    session_id=session.id,
                    aws_access_key=aws_access,
                    aws_secret_key=aws_secret,
                    region=region,
                )
        except Exception as e:
            logger.warning(f"[CONFIGURE] AWS sync skipped: {e}")
        
        available = get_available_instances_for_user(db, user.id)
        if not available:
            return send_bot_message(
                "Aucune instance disponible. Crée ou démarre des instances puis réessaie.",
                "awaiting_intent",
            )
        
        # Déterminer le type d'exécution automatiquement
        exec_type = action.execution_type()  # "installation", "configuration", "hardening"
        
        # Store pending configure action dans la session
        session.state = "awaiting_instance_selection"
        session.session_temp_data = json.dumps({
            "pending_intent": "configure",
            "pending_action_id": detected_intent.action_id,
            "pending_params": detected_intent.params or {},
            "original_text": text,
            "execution_type": exec_type,
        })
        db.commit()
        
        logger.info(f"[CONFIGURE] Action reconnue: {detected_intent.action_id} (type={exec_type})")
        
        # Afficher ce que DAC a compris
        understanding = UnderstandingDisplay(
            intent="configure",
            action=action.label,
            targets=None,  # En attente
        )
        understanding_line = f"\n\n__{understanding.to_text()}__"
        
        return send_bot_message(
            f"**{exec_type.capitalize()}**: {action.label}\n\nSélectionne les VM (ou 'toutes'):{understanding_line}",
            "awaiting_instance_selection",
            {"available_instances": available},
        )
    
    # Cas 2 & 3: Pas d'action
    # Vérifier s'il y a une action précédente
    last_action_data = json.loads(session.session_temp_data or "{}")
    last_action_id = last_action_data.get("pending_action_id")
    
    if last_action_id:
        # Cas 3: Relancer la dernière config
        last_action = get_action_by_id(last_action_id)
        if last_action:
            return send_bot_message(
                f" Relancer la dernière configuration: {last_action.label}?\n\nréponds 'oui' ou précise une autre config.",
                "awaiting_intent"
            )
    
    # Cas 2: Aucune action, aucun contexte -> proposer des suggestions
    categories = get_categories()
    suggested = get_suggested_actions(limit=6)
    
    suggestions_text = "**Que veux-tu configurer?**\n\n"
    for action in suggested:
        suggestions_text += f"  • **{action.label}** — {action.description}\n"
    
    suggestions_text += "\n\nOu décris ce que tu veux faire (ex: 'installer nginx', 'durcir ssh')."
    
    # Afficher compréhension
    understanding = UnderstandingDisplay(
        intent="configure",
        action=None,
        targets=None,
    )
    understanding_line = f"\n\n__{understanding.to_text()}__"
    
    return send_bot_message(
        suggestions_text + understanding_line,
        "awaiting_intent"
    )


# =============================================================
# Wrapper pour configure task (appelé par execution handler)
# =============================================================

async def _start_configure_task_wrapper(
    db: Session,
    user_id: int,
    instances,
    original_text: str,
    session_id: int | None = None,
):
    """
    Wrapper global pour _start_configure_task (normalement nested dans chat_message).
    Permet d'appeler depuis execution_handlers sans dépendance circulaire.
    
    Exécute le workflow SSM complet:
    1. Diagnostic SSM
    2. Bootstrap si nécessaire
    3. Re-diagnostic
    4. Configuration si tout OK
    """
    from pathlib import Path
    from app.services.configure_dispatcher import dispatch_configure
    from app.services.aws_credentials_service import get_user_aws_credentials
    from app.services.ssm_diagnostics import run_ssm_diagnostic
    from app.services.bootstrap_ssm import bootstrap_ssm_attach_profile, wait_for_ssm_online
    
    # Setup logger first (before any potential use)
    logger = logging.getLogger(__name__)
    
    #  TRACE: Générer un trace_id unique pour cette configuration
    trace_id = uuid.uuid4().hex[:12]  # UUID court (12 caractères)
    logger.info(f"[TRACE:{trace_id}] Configuration workflow started")

    base_dir = Path(os.path.join(os.path.dirname(__file__), "../../generated_files")).resolve()

    def _normalize_aws_creds(creds_model_or_dict):
        if not creds_model_or_dict:
            return None

        # dict form
        if isinstance(creds_model_or_dict, dict):
            return {
                "access_key_id": creds_model_or_dict.get("AWS_ACCESS_KEY_ID") or creds_model_or_dict.get("access_key_id"),
                "secret_access_key": creds_model_or_dict.get("AWS_SECRET_ACCESS_KEY") or creds_model_or_dict.get("secret_access_key"),
                "region": creds_model_or_dict.get("region") or "eu-north-1",
            }

        # model form (SQLAlchemy)
        from app.utils.crypto import decrypt
        access_key = getattr(creds_model_or_dict, "access_key_id", None) or getattr(creds_model_or_dict, "encrypted_access_key", None)
        secret_enc = getattr(creds_model_or_dict, "secret_access_key_encrypted", None) or getattr(creds_model_or_dict, "encrypted_secret_key", None)

        # si access_key est chiffré chez toi, adapte ici; sinon laisse tel quel
        if access_key and isinstance(access_key, str) and access_key.startswith("gAAAA"):
            access_key = decrypt(access_key)

        secret_key = decrypt(secret_enc) if secret_enc else None
        region = getattr(creds_model_or_dict, "region", None) or "eu-north-1"

        return {"access_key_id": access_key, "secret_access_key": secret_key, "region": region}

    aws_credentials = get_user_aws_credentials(user_id, db)
    aws_creds_for_config = _normalize_aws_creds(aws_credentials)

    def _summarize_diag(diag: dict, instances_list):
        diag = diag or {}
        online_ids = {d.get("instance_id") for d in diag.get("online_instances", []) if d.get("instance_id")}
        blocked_map = {b.get("instance_id"): b.get("block_reason", "UNKNOWN") for b in diag.get("blocked_instances", []) if b.get("instance_id")}
        summary = []
        for inst in instances_list:
            iid = inst.instance_id
            summary.append({
                "instance_id": iid,
                "ssm_managed": bool(getattr(inst, "ssm_managed", False) or iid in online_ids),
                "ssm_online": iid in online_ids,
                "reason": None if iid in online_ids else blocked_map.get(iid, "UNKNOWN"),
            })
        return summary
    
    def _run_ssm_diag(uid: int, session_db: Session):
        creds_model = get_user_aws_credentials(uid, session_db)
        if not creds_model:
            return {}, None
        creds = _normalize_aws_creds(creds_model)
        if not creds:
            return {}, None
        return run_ssm_diagnostic(
            db=session_db,
            region=creds.get("region") or "eu-north-1",
            aws_access_key=creds.get("access_key_id"),
            aws_secret_key=creds.get("secret_access_key"),
        ), None

    # Diagnostic SSM pour les instances sélectionnées
    instance_ids = [inst.instance_id for inst in instances]

    if not aws_creds_for_config:
        return {
            "result": {"status": "blocked", "message": "Credentials AWS manquantes"},
            "success": False
        }

    logger.info(f"[TRACE:{trace_id}] [CONFIGURE_WRAPPER] Diagnostic SSM pour {len(instance_ids)} instances")

    diag, _ = _run_ssm_diag(user_id, db)
    diag = diag or {}
    diag_summary = _summarize_diag(diag, instances)

    online_ids = {d.get("instance_id") for d in diag.get("online_instances", []) if d.get("instance_id")}
    blocked = {b.get("instance_id"): b.get("block_reason") for b in diag.get("blocked_instances", []) if b.get("instance_id")}

    selected_online = {iid for iid in instance_ids if iid in online_ids}
    selected_blocked = {iid: blocked.get(iid, "UNKNOWN") for iid in instance_ids if iid not in online_ids}

    # Marquer les instances online pour SSM
    for inst in instances:
        if inst.instance_id in selected_online:
            setattr(inst, "ssm_managed", True)

    bootstrap_result = None
    diag_after_summary = diag_summary

    # Bootstrap SSM si nécessaire
    if selected_blocked:
        logger.info(f"[TRACE:{trace_id}] [CONFIGURE_WRAPPER] Bootstrap SSM pour {len(selected_blocked)} instances")
        try:
            bootstrap_result = bootstrap_ssm_attach_profile(
                instance_ids=list(selected_blocked.keys()),
                region=aws_creds_for_config.get('region') or 'eu-north-1',
                aws_access_key=aws_creds_for_config.get('access_key_id'),
                aws_secret_key=aws_creds_for_config.get('secret_access_key'),
            )

            poll_states = wait_for_ssm_online(
                instance_ids=list(selected_blocked.keys()),
                region=aws_creds_for_config.get('region') or 'eu-north-1',
                aws_access_key=aws_creds_for_config.get('access_key_id'),
                aws_secret_key=aws_creds_for_config.get('secret_access_key'),
                attempts=6,
                delay_seconds=20,
            )
            logger.info(f"[TRACE:{trace_id}] [CONFIGURE_WRAPPER] Bootstrap complété. États: {poll_states}")
        except Exception as e:
            logger.warning(f"[TRACE:{trace_id}] [CONFIGURE_WRAPPER] Bootstrap failed: {e}")
            bootstrap_result = {"status": "failed", "error": str(e)}

        # Re-diagnostic après bootstrap
        diag_after, _ = _run_ssm_diag(user_id, db)
        diag_after = diag_after or {}
        diag_after_summary = _summarize_diag(diag_after, instances)
        online_ids = {d.get("instance_id") for d in diag_after.get("online_instances", []) if d.get("instance_id")}
        blocked = {b.get("instance_id"): b.get("block_reason") for b in diag_after.get("blocked_instances", []) if b.get("instance_id")}
        selected_online = {iid for iid in instance_ids if iid in online_ids}
        selected_blocked = {iid: blocked.get(iid, "UNKNOWN") for iid in instance_ids if iid not in online_ids}

        for inst in instances:
            if inst.instance_id in selected_online:
                setattr(inst, "ssm_managed", True)

        if selected_blocked:
            logger.warning(f"[TRACE:{trace_id}] [CONFIGURE_WRAPPER] SSM toujours KO après bootstrap: {selected_blocked}")
            return {
                "result": {
                    "status": "blocked",
                    "message": "SSM toujours KO après bootstrap",
                    "blocked_instances": selected_blocked,
                    "diagnostic": diag_after_summary,
                    "bootstrap": bootstrap_result,
                },
                "success": False,
            }

    # Configuration si tout online
    if len(selected_online) != len(instance_ids):
        logger.warning(f"[TRACE:{trace_id}] [CONFIGURE_WRAPPER] SSM non confirmé pour toutes les instances")
        return {
            "result": {
                "status": "blocked",
                "message": "SSM non confirmé online pour toutes les instances",
                "online": list(selected_online),
                "diagnostic": diag_summary,
            },
            "success": False,
        }

    logger.info(f"[TRACE:{trace_id}] [CONFIGURE_WRAPPER] Toutes les instances online, lancement configuration")
    
    # Appel configuration finale via dispatch_configure (route intelligemment vers Installer ou Ansible)
    configure_result = dispatch_configure(
        trace_id=trace_id,
        text=original_text,
        instances=instances,
        base_dir=base_dir,
        aws_credentials=aws_creds_for_config,
        db_session=db,
        session_id=session_id,
        user_id=user_id,
    )

    # Interpréter le résultat (dispatch_configure retourne "status" + "mode")
    # WARN VALIDATION STRICTE: Ne JAMAIS marquer "success" si dispatcher a échoué
    is_success = False
    
    # Vérifier d'abord si le dispatcher a retourné une erreur ou un statut failure
    if configure_result.get("error") or configure_result.get("status") in ("failed", "blocked", None):
        is_success = False
        logger.error(f"[TRACE:{trace_id}] [CONFIGURE_WRAPPER] Dispatcher failed: status={configure_result.get('status')} error={configure_result.get('error')}")
    elif configure_result.get("status") == "blocked":
        is_success = False
    elif "batch_execution" in configure_result:
        summary = configure_result["batch_execution"].get("summary", {})
        is_success = summary.get("success", 0) > 0 and summary.get("failed", 0) == 0
    elif configure_result.get("status") in ("success",):
        # Pour installer_configure: status doit être explicitement "success"
        is_success = True
    elif configure_result.get("status") == "partial":
        # Partial est acceptable si au moins un succès et pas d'erreur global
        is_success = not configure_result.get("error")
    else:
        # Par défaut: échoué (sûr que dangereux)
        is_success = False

    return {
        "result": configure_result,
        "success": is_success,
        "details": f"Diagnostic: {len(selected_online)}/{len(instance_ids)} online, Bootstrap: {'Yes' if bootstrap_result else 'No'}",
        "trace_id": trace_id,
    }


# =============================================================
# Fonction principale de gestion des messages
# Rôle : Gestion intelligente du chat selon l'état de la session
# =============================================================

@router.post("/chat_message", tags=["Chat"], summary="Messagerie intelligente pilotée par état de session")
@limiter.limit("20/minute")
async def chat_message(
    payload: ChatMessageRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    from app.utils.logging_utils import redact_secrets
    
    logger = logging.getLogger(__name__)
    logger.info("chat_message payload: %s", redact_secrets(payload.dict()))

    #  Extraction des données envoyées par le frontend
    session_id = payload.session_id
    chat_id = payload.chat_id
    sender = payload.sender
    text = payload.text

    #  Vérification de la session utilisateur
    session = db.query(models.Session).filter_by(id=session_id, user_id=user.id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session non trouvée.")
    
    #  Récupération ou auto-création du chat lié à la session
    if not chat_id:
        # Auto-create chat au lieu de 400
        chat = models.Chat(
            session_id=session.id,
            title="Nouveau Chat",
            created_at=datetime.now(timezone.utc)
        )
        db.add(chat)
        db.commit()
        db.refresh(chat)
        chat_id = chat.id
        logger.info(f" Chat auto-créé avec ID: {chat_id}")
    else:
        chat = db.query(models.Chat).filter_by(id=chat_id, session_id=session.id).first()
        if not chat:
            raise HTTPException(status_code=404, detail="Chat introuvable pour cette session.")

    #  LOG: Vérification du mode (debug)
    logger.info(f"[chat_message] mode check: chat.mode={getattr(chat,'mode',None)} session.mode={getattr(session,'mode',None)} session.state={session.state}")

    # ============================================================================
    #  P0.6 — Always persist user message upfront (Étape 2 - Free Chat persistance)
    # ============================================================================
    user_message = models.Message(
        session_id=session_id,
        chat_id=chat_id,
        sender=sender,
        text=text,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user_message)
    db.commit()

    #  EARLY RETURN: Si la session est en mode free, on délègue au service dédié
    # IMPORTANT: VÉRIFIER session.mode qui est la SOURCE DE VÉRITÉ, pas chat.mode
    # Ceci doit être AVANT toute logique DAC (GLOBAL_OVERRIDE, intent detection, session.state, etc.)
    if session.mode == "free":
        logger.info(f"[chat_message] -> Delegating to FREE CHAT service (session.mode='free')")
        return await handle_free_chat_message(
            db=db,
            user=user,
            session_id=session_id,
            chat_id=chat_id,
            text=text,
        )
    
     #  Fonction utilitaire : envoyer un message du bot
    def send_bot_message(bot_text, state, extra: dict | None = None):
        # Préfixe le welcome si nécessaire (jamais bloquant)
        try:
            if welcome_needed:
                bot_text = DAC_HELP_MESSAGE + "\n\n" + bot_text
        except NameError:
            pass  # welcome_needed peut ne pas être défini dans certains contextes
        
        # ============================================================================
        #  P0.6 — State Consistency (Étape 3): Update session.state before returning
        # ============================================================================
        session.state = state
        db.commit()
        
        # Préparer extra pour la DB et l'API: inclure state et available_instances
        db_extra = {"state": state}
        if extra:
            db_extra.update(extra)
        
        payload = {
            "message": bot_text,
            "state": state,
            "chat_id": chat.id,
            "session_state": state,    #  Now returns the state parameter, not session.state
            "session_mode": session.mode,      #  AJOUT
            "extra": db_extra  #  Envoyer extra comme un objet imbriqué pour frontend
        }
        
        db.add(models.Message(
            session_id=session.id,
            chat_id=chat.id,
            sender="bot",
            text=bot_text,
            extra=db_extra  # Persister state + extra en DB
        ))
        db.commit()
        return payload


    # =============================================================
    #  EXPIRATION SOFT des flows (MVP)
    # - Si on a un state != awaiting_intent et que la dernière activité date "trop"
    #   on reset.
    # NOTE: idéalement ajouter un champ DB state_updated_at.
    # =============================================================
    import time

    FLOW_TIMEOUT_SECONDS = 60 * 60 * 24  # 24h

    def _get_flow_ts(sess: models.Session) -> int | None:
        try:
            d = json.loads(sess.session_temp_data or "{}")
            return int(d.get("__flow_ts")) if isinstance(d, dict) and d.get("__flow_ts") else None
        except Exception:
            return None

    def _set_flow_ts(sess: models.Session):
        try:
            d = json.loads(sess.session_temp_data or "{}")
            if not isinstance(d, dict):
                d = {}
        except Exception:
            d = {}
        d["__flow_ts"] = int(time.time())
        sess.session_temp_data = json.dumps(d)

    # Si flow actif + ts trop ancien => reset
    if session.state not in {"awaiting_intent"}:
        ts = _get_flow_ts(session)
        if ts and (int(time.time()) - ts) > FLOW_TIMEOUT_SECONDS:
            session.state = "awaiting_intent"
            session.session_temp_data = None
            db.commit()
            # message non bloquant
            return send_bot_message(
                "Ton étape précédente a expiré. Retour au menu.\n\n" + DAC_HELP_MESSAGE,
                "awaiting_intent",
                {"expired": True}
            )

    # Mettre à jour le timestamp à chaque message
    _set_flow_ts(session)
    db.commit()

    #  DAC-first initialization: chat_creation is always DAC mode
    if not getattr(session, 'mode', None):
        session.mode = "dac"
    
    # Force DAC-only behavior for this endpoint
    # Force a clean DAC state (never free_chat here)
    if not session.state or session.state in {"free_chat", "free"}:
        session.state = "awaiting_intent"
    
    db.commit()

    # OK User message already persisted upfront (ligne 341-348)
    # No need to persist again here

    #  Nettoyage du message
    command = text.strip().lower()
    auth_header = request.headers.get("authorization")

    # =============================================================
    # ÉTAPE B — ACTIONS UI (priorité absolue, avant détection d'intention)
    # =============================================================
    
    # AUDIT: Sélection d'instances via UI checkbox
    if payload.action == "confirm_audit_instances" and payload.selected_instances:
        # Permettre aussi awaiting_audit_confirmation si le plan a déjà été montré mais user relance
        if session.state not in {"awaiting_audit_instance_selection", "awaiting_audit_confirmation"}:
            logger.warning(
                f"[AUDIT_UI_SELECTION] État inattendu: {session.state} (attendu awaiting_audit_instance_selection)",
                extra={"session_id": session.id, "user_id": user.id, "state": session.state}
            )
            return send_bot_message("Sélection inattendue. Relance 'audit'.", "awaiting_intent")

        try:
            # Charger les instances depuis DB
            instances = (
                db.query(models.Instance)
                .join(models.Session, models.Instance.session_id == models.Session.id)
                .filter(models.Session.user_id == user.id)
                .filter(models.Instance.id.in_(payload.selected_instances))
                .all()
            )
            if not instances:
                return send_bot_message("Aucune instance trouvée pour ces IDs.", "awaiting_audit_instance_selection")

            instance_ids = [i.instance_id for i in instances]
            logger.info(f"[AUDIT_UI_SELECTION] Instances sélectionnées: {instance_ids}")

            # Construire le plan d'audit
            from app.services.audit_engine import AuditRunner, AUDIT_RECIPES

            audit_source_text = json.loads(session.session_temp_data or "{}").get("original_text", "")
            runner = AuditRunner(db=db, ssm_executor=None)
            audit_plan = runner.create_plan(
                instance_ids=instance_ids,
                recipe_names=_audit_recipe_names_from_text(audit_source_text),
            )

            # Stocker le plan
            session.state = "awaiting_audit_confirmation"
            session.session_temp_data = json.dumps({
                "plan": audit_plan.dict(),
                "original_text": audit_source_text,
            })
            db.commit()

            # Formater le message du plan
            duration_sec = audit_plan.estimated_duration_seconds or 60
            duration_min = duration_sec // 60
            duration_display = f"{duration_min}m" if duration_min > 0 else f"{duration_sec}s"
            plan_msg = (
                f" **Plan d'audit**\n\n"
                f" **Durée estimée: ~{duration_display}**\n"
                f" Instances: {audit_plan.instances_count}\n"
                f" Recettes: {', '.join(audit_plan.recipe_names)}\n\n"
                f"**Commandes à exécuter** (par instance):\n"
            )
            for recipe_name in audit_plan.recipe_names:
                recipe = AUDIT_RECIPES.get(recipe_name)
                if recipe:
                    plan_msg += f"\n• **{recipe_name}**: {len(recipe.commands)} commandes\n"
                    for cmd_name in list(recipe.commands.keys())[:3]:
                        plan_msg += f"  - `{cmd_name}`\n"
                    if len(recipe.commands) > 3:
                        plan_msg += f"  - ... et {len(recipe.commands) - 3} autres\n"

            plan_msg += "\n Tape **'ok'** ou **'lancer'** pour confirmer, ou **'annuler'** pour abandonner."

            return send_bot_message(plan_msg, "awaiting_audit_confirmation")

        except Exception as e:
            logger.exception(
                "[AUDIT_UI_SELECTION_ERROR] Échec lors de la sélection d'instances pour audit (UI)",
                extra={"session_id": session.id, "user_id": user.id, "selected_instances": payload.selected_instances}
            )
            return send_bot_message(
                f" Erreur lors de la sélection: {str(e)[:200]}",
                "awaiting_intent"
            )

    # MONITORING: Sélection d'instances via UI checkbox
    if payload.action == "confirm_monitoring_instances" and payload.selected_instances:
        # Permettre aussi awaiting_monitoring_confirmation si le plan a déjà été montré mais user relance
        if session.state not in {"awaiting_monitoring_instance_selection", "awaiting_monitoring_confirmation"}:
            logger.warning(
                f"[MONITORING_UI_SELECTION] État inattendu: {session.state} (attendu awaiting_monitoring_instance_selection)",
                extra={"session_id": session.id, "user_id": user.id, "state": session.state}
            )
            return send_bot_message("Sélection inattendue. Relance 'monitoring'.", "awaiting_intent")

        try:
            # Charger les instances depuis DB
            instances = (
                db.query(models.Instance)
                .join(models.Session, models.Instance.session_id == models.Session.id)
                .filter(models.Session.user_id == user.id)
                .filter(models.Instance.id.in_(payload.selected_instances))
                .all()
            )
            if not instances:
                return send_bot_message("Aucune instance trouvée pour ces IDs.", "awaiting_monitoring_instance_selection")

            instance_ids = [i.instance_id for i in instances]
            logger.info(f"[MONITORING_UI_SELECTION] Instances sélectionnées: {instance_ids}")

            # Construire le plan de monitoring
            from app.services.monitoring_engine import MonitoringRunner, MONITORING_RECIPES

            runner = MonitoringRunner(db=db, ssm_executor=None)
            monitoring_plan = runner.create_plan(
                monitoring_type="metrics_snapshot",
                instance_ids=instance_ids,
            )

            # Stocker le plan
            session.state = "awaiting_monitoring_confirmation"
            session.session_temp_data = json.dumps({
                "plan": monitoring_plan.dict(),
                "original_text": json.loads(session.session_temp_data or "{}").get("original_text", ""),
            })
            db.commit()

            # Formater le message du plan
            duration_sec = monitoring_plan.estimated_duration_seconds or 30
            duration_min = duration_sec // 60
            duration_display = f"{duration_min}m" if duration_min > 0 else f"{duration_sec}s"
            plan_msg = (
                f" **Plan de monitoring**\n\n"
                f" **Durée estimée: ~{duration_display}**\n"
                f" Instances: {monitoring_plan.instances_count}\n"
                f" Type: {monitoring_plan.monitoring_type}\n\n"
            )

            plan_msg += "\n Tape **'ok'** ou **'lancer'** pour confirmer, ou **'annuler'** pour abandonner."

            return send_bot_message(plan_msg, "awaiting_monitoring_confirmation")

        except Exception as e:
            logger.exception(
                "[MONITORING_UI_SELECTION_ERROR] Échec lors de la sélection d'instances pour monitoring (UI)",
                extra={"session_id": session.id, "user_id": user.id, "selected_instances": payload.selected_instances}
            )
            return send_bot_message(
                f" Erreur lors de la sélection: {str(e)[:200]}",
                "awaiting_intent"
            )

    # CONFIGURATION: Sélection d'instances via UI checkbox
    if payload.action == "confirm_instances" and payload.selected_instances:
        # Permettre aussi awaiting_confirmation si le plan a déjà été montré
        if session.state not in {"awaiting_instance_selection", "awaiting_confirmation"}:
            logger.warning(
                f"[CONFIGURE_UI_SELECTION] État inattendu: {session.state} (attendu awaiting_instance_selection)",
                extra={"session_id": session.id, "user_id": user.id, "state": session.state}
            )
            return send_bot_message("Sélection inattendue. Relance 'configure'.", "awaiting_intent")

        try:
            # Charger les instances depuis DB
            instance_rows = (
                db.query(models.Instance, models.Session)
                .join(models.Session, models.Instance.session_id == models.Session.id)
                .filter(models.Session.user_id == user.id)
                .filter(models.Instance.id.in_(payload.selected_instances))
                .all()
            )
            instances = [row[0] for row in instance_rows]
            if not instances:
                return send_bot_message("Aucune instance trouvée pour ces IDs.", "awaiting_instance_selection")

            instance_ids = [i.instance_id for i in instances]
            logger.info(f"[CONFIGURE_UI_SELECTION] Instances sélectionnées: {instance_ids}")

            # Lancer le workflow strict: diagnostic SSM -> (bootstrap) -> re-diagnostic -> configuration
            data = json.loads(session.session_temp_data or "{}")
            original_text = data.get("original_text", text)
            
            # Créer Execution pour configure et lancer via background task
            execution = models.Execution(
                user_id=user.id,
                session_id=session.id,
                task_type="configure",
                status="pending",
                extra_data=json.dumps({
                    "instances": [{"id": inst.id, "instance_id": inst.instance_id} for inst in instances],
                    "original_text": original_text,
                    "progress": 0,
                    "progress_message": "En attente de lancement",
                    "progress_phase": "pending",
                }),
            )
            db.add(execution)
            db.commit()
            db.refresh(execution)
            logger.info("[CONFIGURE_EXEC_CREATED] execution_id=%s", execution.id)

            session.state = "executing"
            session.session_temp_data = json.dumps({
                "execution_id_db": execution.id,
                "original_text": original_text,
            })
            db.commit()

            from app.services.execution_handlers import run_execution_by_id

            # Exécution SYNCHRONE: renvoyer un retour complet
            result = await run_execution_by_id(
                db=db,
                execution_id=execution.id,
                user_id=user.id,
            )

            inner_result = result.get("result", {}) if isinstance(result, dict) else {}
            trace_id = result.get("trace_id") or inner_result.get("trace_id")
            app_name = inner_result.get("app") or inner_result.get("mode") or "unknown"

            success_count = 0
            failed_count = 0
            if isinstance(inner_result, dict):
                if "summary" in inner_result:
                    summary = inner_result.get("summary", {})
                    success_count = summary.get("success", 0)
                    failed_count = summary.get("failed", 0)
                elif "batch_execution" in inner_result:
                    summary = inner_result.get("batch_execution", {}).get("summary", {})
                    success_count = summary.get("success", 0)
                    failed_count = summary.get("failed", 0) + summary.get("timeout", 0)

            summary_text = (
                f"Configuration terminée: success={success_count} failed={failed_count}. "
                f"Application: {app_name}. "
                f"Trace: {trace_id or 'n/a'}"
            )

            details_lines = []
            show_details = failed_count > 0

            if isinstance(inner_result, dict) and inner_result.get("mode") == "installer_configure":
                for r in inner_result.get("results", []):
                    inst_label = r.get("instance_name") or r.get("instance_id")
                    status = r.get("status")
                    service = r.get("service_name") or "service"
                    port = r.get("chosen_port")
                    version = r.get("installed_version")
                    if status == "success":
                        details_lines.append(
                            f"{inst_label}: OK. service={service}, port={port}, version={version}"
                        )
                    else:
                        stderr_tail = r.get("stderr_tail") or ""
                        stdout_tail = r.get("stdout_tail") or ""
                        tail = stderr_tail or stdout_tail
                        tail_msg = f"\nstdout/stderr: {tail}" if tail else ""
                        details_lines.append(
                            f"{inst_label}: ÉCHEC. service={service}, port={port}, version={version}. "
                            f"error={r.get('error')}.{tail_msg}"
                        )
            elif isinstance(inner_result, dict) and "batch_execution" in inner_result:
                per_instance = inner_result.get("batch_execution", {}).get("per_instance_results", {})
                for inst_id, r in per_instance.items():
                    status = r.get("status")
                    stderr_tail = r.get("stderr_tail") or ""
                    stdout_tail = r.get("stdout_tail") or ""
                    tail = stderr_tail or stdout_tail
                    if status == "success":
                        details_lines.append(f"{inst_id}: OK.")
                    else:
                        tail_msg = f"\nstdout/stderr: {tail}" if tail else ""
                        details_lines.append(
                            f"{inst_id}: ÉCHEC. error={r.get('error')}.{tail_msg}"
                        )

            details_text = "Détails:\n" + "\n".join(details_lines) if details_lines else ""

            payload = send_bot_message(
                summary_text,
                "awaiting_intent",
                {"configure_result": result, "trace_id": trace_id}
            )

            if show_details and details_text:
                db.add(models.Message(
                    session_id=session.id,
                    chat_id=chat.id,
                    sender="bot",
                    text=details_text,
                    extra={"state": "awaiting_intent", "trace_id": trace_id}
                ))
                db.commit()

            return payload

        except Exception as e:
            logger.exception(
                "[CONFIGURE_UI_SELECTION_ERROR] Échec lors de la sélection d'instances pour configuration (UI)",
                extra={"session_id": session.id, "user_id": user.id, "selected_instances": payload.selected_instances}
            )
            return send_bot_message(
                f" Erreur lors de la sélection: {str(e)[:200]}",
                "awaiting_intent"
            )

    # =============================================================
    #  GLOBAL INTENT OVERRIDE (UX): permet de changer de flow depuis n'importe quel état
    # Sauf si une exécution est en cours
    # =============================================================

    PRIMARY_INTENTS = {"create", "configure", "audit", "monitoring"}
    PRIMARY_FAST = {"LIST_RESOURCES", "ENTER_DELETION", "DEBUG", "CANCEL", "SHOW_MENU"}

    def try_fast_commands(command: str) -> str | None:
        """
        Détecte les commandes rapides (menu, aide, annuler, etc).
        Retourne la clé rapide ou None si pas de match.
        """
        cmd = (command or "").strip().lower()
        
        if cmd in {"liste des ressources", "list resources", "list", "ressources"}:
            return "LIST_RESOURCES"
        
        if cmd in {"supprimer", "deletion mode", "delete", "enter deletion"}:
            return "ENTER_DELETION"
        
        if cmd in {"debug", "debug mode", "debug on"}:
            return "DEBUG"
        
        if cmd in {"annuler", "cancel", "quit", "exit"}:
            return "CANCEL"
        
        if cmd in {"menu", "help", "aide", "?"}:
            return "SHOW_MENU"
        
        return None

    def _is_executing_state(state: str | None) -> bool:
        return (state or "") in {"executing", "running", "in_progress"}

    def _detect_primary_intent_simple(cmd: str) -> str | None:
        """
        Détection simple par mots-clés/synonymes (robuste et rapide).
        IMPORTANT: volontairement permissif.
        
        SÉCURITÉ: Rejette les textes qui ressemblent à du JSON pour éviter
        les injections via payload malveillant dans le champ text.
        """
        c = (cmd or "").strip().lower()
        
        #  SÉCURITÉ: Rejeter les textes qui ressemblent à du JSON
        if c.startswith("{") or c.startswith("["):
            logger.warning(f"[INTENT_DETECTION] JSON detecté dans text, rejet: {c[:50]}")
            return None

        # audit
        audit_keywords = {
            "audit", "auditer", "audite", "security audit", "audit sécurité", "securite", "sécurité",
            "lynis", "auditd", "hardening check", "compliance"
        }
        if any(k in c for k in audit_keywords):
            return "audit"

        # monitoring
        monitoring_keywords = {
            "monitoring", "monitor", "metrics", "métriques", "metriques", "cpu", "ram", "mémoire",
            "snapshot", "collect", "collecter", "collecte", "load", "uptime"
        }
        if any(k in c for k in monitoring_keywords):
            return "monitoring"

        # configure
        configure_keywords = {
            "configure", "configuration", "configurer", "installer", "installation", "install",
            "setup", "déployer", "deployer", "nginx", "docker", "ufw", "fail2ban"
        }
        if any(k in c for k in configure_keywords):
            return "configure"

        # create
        create_keywords = {
            "create", "créer", "creer", "provision", "provisionner", "infra", "infrastructure",
            "vm", "instance", "instances", "serveur", "server", "terraform"
        }
        if any(k in c for k in create_keywords):
            return "create"

        return None

    def _reset_to_awaiting_intent_for_new_flow(target_intent: str):
        """
        Reset propre avant de repartir sur un nouveau workflow.
        """
        session.state = "awaiting_intent"
        # garde le texte utilisateur en mémoire si besoin, sinon None
        session.session_temp_data = None
        db.commit()
        logger.info(f"[GLOBAL_OVERRIDE] Reset -> awaiting_intent, target_intent={target_intent}")

    # 1) détecter fast_command tôt (tu l'as déjà)
    fast_command = try_fast_commands(command)

    # 2) si tâche en cours : on ne reroute pas
    if _is_executing_state(session.state):
        # On laisse passer les commandes utiles (menu/list/debug/cancel)
        if fast_command not in PRIMARY_FAST and _detect_primary_intent_simple(command):
            return send_bot_message(
                "Une tâche est en cours d'exécution. Attends la fin ou tape 'annuler' pour revenir au menu.",
                session.state
            )

    # 3) override: si on est dans un état de flow (pas awaiting_intent) et qu'on détecte une intention principale
    #    MAIS: skip si payload.action est présent OU si texte ressemble à du JSON
    
    # ÉTAPE C — Sécurité: empêcher override sur JSON ou actions UI
    cmd_stripped = (command or "").strip()
    is_json_like = cmd_stripped.startswith("{") and cmd_stripped.endswith("}")
    has_ui_action = payload.action is not None  # Si UI action définie -> pas d'override
    
    # Ne déclencher l'override que si: pas de JSON, pas d'action UI, et intention détectée
    if is_json_like or has_ui_action:
        detected_primary = None
    else:
        detected_primary = _detect_primary_intent_simple(command)
    
    if detected_primary and session.state not in {"awaiting_intent"} and fast_command not in PRIMARY_FAST:
        if session.state == "awaiting_create_params":
            detected_primary = None
        else:
            # On change de flow immédiatement
            _reset_to_awaiting_intent_for_new_flow(detected_primary)
            # message UX clair (pas obligatoire mais recommandé)
            return send_bot_message(
                f"Changement de demande détecté: **{detected_primary}**.\n"
                "Je repars sur ce workflow.\n\n"
                + DAC_HELP_MESSAGE,
                "awaiting_intent",
                {"forced_intent": detected_primary}
            )


    # Hard rule: this endpoint is DAC-only
    session.mode = "dac"
    if not session.state:
        session.state = "awaiting_intent"
    if session.state in {"free", "free_chat"}:
        session.state = "awaiting_intent"
    db.commit()

   
    def _has_bot_welcome(chat_id: int) -> bool:
        """Check if welcome message has already been sent for this chat."""
        return (
            db.query(models.Message)
            .filter(models.Message.chat_id == chat_id)
            .filter(models.Message.sender == "bot")
            .filter(models.Message.text.ilike("%Bienvenue dans DevOps-as-a-Chat (DAC)%"))
            .first()
            is not None
        )

    def redirect_credentials_message():
        """Redirect user to credentials configuration."""
        return send_bot_message(
            "Credentials AWS manquantes. Redirection vers la configuration des credentials.",
            "awaiting_intent",
            {"requires_credentials": True, "redirect_to": "credentials"}
        )

    #  FAST COMMANDS — Router before GPT/state machine
    fast_command = try_fast_commands(command)
    
    # 1) Fast command ENTER_DAC (button)
    if fast_command == "ENTER_DAC":
        # Si pas de credentials, on ne rentre pas en DAC (UX: redirect)
        if not has_user_aws_credentials(user.id, db):
            session.state = "awaiting_intent"
            db.commit()
            return redirect_credentials_message()

        # Credentials OK : activation DAC
        session.mode = "dac"
        session.state = "awaiting_intent"
        session.session_temp_data = None
        db.commit()

        # Optionnel mais recommandé: déclencher la sync AWS->DB pour remplir le panneau droite
        try:
            creds = get_user_aws_credentials(user.id, db)
            if creds:
                from app.utils.crypto import decrypt
                # Normaliser les credentials
                if hasattr(creds, "encrypted_access_key"):
                    aws_access = decrypt(creds.encrypted_access_key)
                    aws_secret = decrypt(creds.encrypted_secret_key)
                    region = getattr(creds, "region", None) or "eu-north-1"
                else:
                    aws_access = creds.get("access_key_id") or creds.get("AWS_ACCESS_KEY_ID")
                    aws_secret = creds.get("secret_access_key") or creds.get("AWS_SECRET_ACCESS_KEY")
                    region = creds.get("region") or "eu-north-1"

                sync_aws_instances_to_db(
                    db=db,
                    session_id=session.id,
                    aws_access_key=aws_access,
                    aws_secret_key=aws_secret,
                    region=region,
                )
        except Exception as e:
            logger.warning(f"[ENTER_DAC] AWS sync skipped: {e}")

        return send_bot_message(DAC_HELP_MESSAGE, "awaiting_intent")

    # 2) Calcul du flag welcome_needed (jamais bloquant)
    welcome_needed = (
        session.mode == "dac"
        and has_user_aws_credentials(user.id, db)
        and not _has_bot_welcome(chat.id)
    )
    
    if fast_command == "LIST_RESOURCES":
        # Vérifier les credentials avant de lister
        if not has_user_aws_credentials(user.id, db):
            return redirect_credentials_message()
        
        # -> Exécuter directement sans GPT
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{settings.BACKEND_BASE_URL}/resources/list_all_resources",
                    params={"session_id": session.id},
                    headers={"Authorization": auth_header}
                )
        except Exception as e:
            return send_bot_message(f"Erreur lors de la récupération : {str(e)}", session.state)
        
        if resp.status_code != 200:
            return send_bot_message(f"Erreur backend : {resp.text}", session.state)
        
        data = resp.json()
        database_resources = data.get("database_resources", [])
        cloud_resources = data.get("cloud_resources", [])
        summary = data.get("summary", {})
        
        if not database_resources and not cloud_resources:
            return send_bot_message("Aucune ressource trouvée.", session.state)
        
        lines = ["Découverte complète des ressources AWS\n"]
        lines.append(f"Résumé: {summary.get('total_unique', 0)} ressources uniques trouvées")
        lines.append(f"   • Base de données: {summary.get('total_db', 0)} instances")
        lines.append(f"   • Découvertes AWS: {summary.get('total_cloud', 0)} instances")
        
        if summary.get('aws_discovery_success'):
            lines.append("   • Synchronisation AWS réussie\n")
        else:
            lines.append("   • Découverte AWS indisponible\n")
        
        if cloud_resources:
            lines.append("Instances AWS (temps réel):")
            for r in cloud_resources:
                state_text = "running" if r.get('state') == 'running' else "stopped" if r.get('state') == 'stopped' else "unknown"
                ip_display = r.get('public_ip', 'Pas d\'IP publique')
                lines.append(f"   {r.get('instance_id', 'N/A')} | État: {state_text} | IP: {ip_display}")
            lines.append("")
        
        if database_resources:
            lines.append("Instances trackées localement:")
            for r in database_resources:
                lines.append(f"   {r['instance_id']} | IP: {r.get('public_ip', 'N/A')} | User: {r['ssh_user']} | Provider: {r['provider']}")
            lines.append("")
        
        return send_bot_message("\n".join(lines), session.state)
    
    elif fast_command == "CANCEL":
        # Reset complet du flow (important)
        session.state = "awaiting_intent"
        session.session_temp_data = None
        db.commit()
        return send_bot_message(
            "Étape annulée. Retour au point de départ.\n\n" + DAC_HELP_MESSAGE,
            "awaiting_intent",
            {"cancelled": True}
        )
    
    elif fast_command == "ENTER_DELETION":
        session.state = "deletion_mode"
        db.commit()
        return send_bot_message(
            " **Mode suppression activé**\n\n"
            "Quelles ressources voulez-vous supprimer? (ex: instance-1, instance-2)\n\n"
            "ou tapez `lister` pour voir toutes les ressources.",
            "deletion_mode"
        )
    
    elif fast_command == "DEBUG":
        # Simple debug info
        return send_bot_message(
            f" **État de la session:**\n"
            f"   Session ID: {session.id}\n"
            f"   État: {session.state}\n"
            f"   Mode: {session.mode}\n"
            f"   Provider: {session.provider or 'non configuré'}\n"
            f"   Chat ID: {chat.id}",
            session.state
        )

    # Helpers pour le flux configure
    from app.services.configure_only import get_available_instances_for_user

    def _format_block_summary(diag: dict) -> str:
        reasons = {}
        for b in diag.get("blocked_instances", []):
            reason = b.get("block_reason", "UNKNOWN")
            reasons[reason] = reasons.get(reason, 0) + 1
        if not reasons:
            return "Aucun détail de blocage disponible."
        parts = [f"{count}× {reason}" for reason, count in reasons.items()]
        return ", ".join(parts)

    def _resolve_selected_instance_ids(text_value: str) -> list[int]:
        available = get_available_instances_for_user(db, user.id)  # list[dict] avec "id"
        if not available:
            return []
        t = (text_value or "").strip().lower()
        if t in {"toutes", "all", "*"}:
            return [a["id"] for a in available]
        nums = [int(n) for n in re.findall(r"\d+", t)]
        picked = []
        for n in nums:
            if 1 <= n <= len(available):
                picked.append(available[n - 1]["id"])
        return picked

    # ÉTAPE 5A: Traiter confirm_audit_instances directement (sans résolution de texte)
    if session.state == "awaiting_audit_instance_selection" and payload.action == "confirm_audit_instances" and payload.selected_instances:
        try:
            instance_rows = (
                db.query(models.Instance, models.Session)
                .join(models.Session, models.Instance.session_id == models.Session.id)
                .filter(models.Session.user_id == user.id)
                .filter(models.Instance.id.in_(payload.selected_instances))
                .all()
            )
            instances = [row[0] for row in instance_rows]
            if not instances:
                return send_bot_message("Aucune instance trouvée pour ces IDs.", "awaiting_intent")

            instance_ids = [i.instance_id for i in instances]
            logger.info(f"[AUDIT_SELECTION] Instances sélectionnées (ÉTAPE 4): {instance_ids}")

            # Créer le plan d'audit
            from app.services.audit_engine import AuditRunner, AUDIT_RECIPES

            audit_source_text = json.loads(session.session_temp_data or "{}").get("original_text", text)
            runner = AuditRunner(db=db, ssm_executor=None)
            audit_plan = runner.create_plan(
                instance_ids=instance_ids,
                recipe_names=_audit_recipe_names_from_text(audit_source_text),
            )

            # Stocker le plan dans session_temp_data
            session.state = "awaiting_audit_confirmation"
            session.session_temp_data = json.dumps({
                "plan": audit_plan.dict(),
                "original_text": audit_source_text,
            })
            db.commit()

            # Formater et afficher le plan avec durée estimée améliorée
            duration_sec = audit_plan.estimated_duration_seconds or 60
            duration_min = duration_sec // 60
            duration_display = f"{duration_min}m" if duration_min > 0 else f"{duration_sec}s"
            plan_msg = (
                f" **Plan d'audit**\n\n"
                f" **Durée estimée: ~{duration_display}**\n"
                f" Instances: {audit_plan.instances_count}\n"
                f" Recettes: {', '.join(audit_plan.recipe_names)}\n\n"
                f"**Commandes à exécuter** (par instance):\n"
            )
            for recipe_name in audit_plan.recipe_names:
                recipe = AUDIT_RECIPES.get(recipe_name)
                if recipe:
                    plan_msg += f"\n• **{recipe_name}**: {len(recipe.commands)} commandes\n"
                    for cmd_name in list(recipe.commands.keys())[:3]:
                        plan_msg += f"  - `{cmd_name}`\n"
                    if len(recipe.commands) > 3:
                        plan_msg += f"  - ... et {len(recipe.commands) - 3} autres\n"

            plan_msg += "\n Tape **'ok'** ou **'lancer'** pour confirmer, ou **'annuler'** pour abandonner."

            return send_bot_message(plan_msg, "awaiting_audit_confirmation")
        
        except Exception as e:
            logger.exception(
                "[AUDIT_SELECTION_ERROR] Échec lors de la sélection d'instances pour audit (ÉTAPE 5A)",
                extra={"session_id": session.id, "user_id": user.id, "selected_instances": payload.selected_instances}
            )
            return send_bot_message(
                f" Erreur lors de la sélection: {str(e)[:200]}",
                "awaiting_intent"
            )

    # ÉTAPE 5B: Traiter confirm_monitoring_instances directement (sans résolution de texte)
    if session.state == "awaiting_monitoring_instance_selection" and payload.action == "confirm_monitoring_instances" and payload.selected_instances:
        try:
            instance_rows = (
                db.query(models.Instance, models.Session)
                .join(models.Session, models.Instance.session_id == models.Session.id)
                .filter(models.Session.user_id == user.id)
                .filter(models.Instance.id.in_(payload.selected_instances))
                .all()
            )
            instances = [row[0] for row in instance_rows]
            if not instances:
                return send_bot_message("Aucune instance trouvée pour ces IDs.", "awaiting_intent")

            instance_ids = [i.instance_id for i in instances]
            logger.info(f"[MONITORING_SELECTION] Instances sélectionnées (ÉTAPE 4): {instance_ids}")

            # Créer le plan de monitoring
            from app.services.monitoring_engine import MonitoringRunner, MONITORING_RECIPES
            
            runner = MonitoringRunner(db=db, ssm_executor=None)
            monitoring_plan = runner.create_plan(
                monitoring_type="metrics_snapshot",
                instance_ids=instance_ids,
            )

            # Stocker le plan dans session_temp_data
            session.state = "awaiting_monitoring_confirmation"
            session.session_temp_data = json.dumps({
                "plan": monitoring_plan.dict(),
                "original_text": session.session_temp_data or text,
            })
            db.commit()

            # Formater et afficher le plan avec durée estimée améliorée
            duration_sec = monitoring_plan.estimated_duration_seconds or 30
            duration_min = duration_sec // 60
            duration_display = f"{duration_min}m" if duration_min > 0 else f"{duration_sec}s"
            plan_msg = (
                f" **Plan de monitoring**\n\n"
                f" **Durée estimée: ~{duration_display}**\n"
                f" Instances: {monitoring_plan.instances_count}\n"
                f" Type: {monitoring_plan.monitoring_type}\n\n"
            )

            plan_msg += "\n Tape **'ok'** ou **'lancer'** pour confirmer, ou **'annuler'** pour abandonner."

            return send_bot_message(plan_msg, "awaiting_monitoring_confirmation")
        
        except Exception as e:
            logger.exception(
                "[MONITORING_SELECTION_ERROR] Échec lors de la sélection d'instances pour monitoring (ÉTAPE 5B)",
                extra={"session_id": session.id, "user_id": user.id, "selected_instances": payload.selected_instances}
            )
            return send_bot_message(
                f" Erreur lors de la sélection: {str(e)[:200]}",
                "awaiting_intent"
            )

    # =============================================================
    #  AUDIT: Sélection d'instances pour audit
    # =============================================================
    if session.state == "awaiting_audit_instance_selection" and not payload.action:
        try:
            available = get_available_instances_for_user(db, user.id)
            if not available:
                return send_bot_message(
                    "Aucune instance disponible. Démarre ou crée des instances puis réessaye.",
                    "awaiting_intent",
                )

            picked_ids = _resolve_selected_instance_ids(text)
            if not picked_ids:
                return send_bot_message(
                    "Sélection invalide. Réponds par 'all', 'toutes', ou des numéros (1,3,5).",
                    "awaiting_audit_instance_selection"
                )

            instances = (
                db.query(models.Instance)
                .join(models.Session, models.Instance.session_id == models.Session.id)
                .filter(models.Session.user_id == user.id)
                .filter(models.Instance.id.in_(picked_ids))
                .all()
            )
            instance_ids = [i.instance_id for i in instances]
            logger.info(f"[AUDIT_SELECTION] Instances sélectionnées: {instance_ids}")

            # Créer le plan d'audit
            from app.services.audit_engine import AuditRunner, AUDIT_RECIPES

            audit_source_text = json.loads(session.session_temp_data or "{}").get("original_text", text)
            runner = AuditRunner(db=db, ssm_executor=None)
            audit_plan = runner.create_plan(
                instance_ids=instance_ids,
                recipe_names=_audit_recipe_names_from_text(audit_source_text),
            )

            # Stocker le plan dans session_temp_data
            session.state = "awaiting_audit_confirmation"
            session.session_temp_data = json.dumps({
                "plan": audit_plan.dict(),
                "original_text": audit_source_text,
            })
            db.commit()

            # Formater et afficher le plan avec durée estimée améliorée
            duration_sec = audit_plan.estimated_duration_seconds or 60
            duration_min = duration_sec // 60
            duration_display = f"{duration_min}m" if duration_min > 0 else f"{duration_sec}s"
            plan_msg = (
                f" **Plan d'audit**\n\n"
                f" **Durée estimée: ~{duration_display}**\n"
                f" Instances: {audit_plan.instances_count}\n"
                f" Recettes: {', '.join(audit_plan.recipe_names)}\n\n"
                f"**Commandes à exécuter** (par instance):\n"
            )
            for recipe_name in audit_plan.recipe_names:
                recipe = AUDIT_RECIPES.get(recipe_name)
                if recipe:
                    plan_msg += f"\n• **{recipe_name}**: {len(recipe.commands)} commandes\n"
                    for cmd_name in list(recipe.commands.keys())[:3]:
                        plan_msg += f"  - `{cmd_name}`\n"
                    if len(recipe.commands) > 3:
                        plan_msg += f"  - ... et {len(recipe.commands) - 3} autres\n"

            plan_msg += "\n Tape **'ok'** ou **'lancer'** pour confirmer, ou **'annuler'** pour abandonner."

            return send_bot_message(plan_msg, "awaiting_audit_confirmation")
        
        except Exception as e:
            logger.exception(
                "[AUDIT_SELECTION_ERROR] Échec lors de la sélection d'instances pour audit (texte)",
                extra={"session_id": session.id, "user_id": user.id, "text": text}
            )
            return send_bot_message(
                f" Erreur lors de la sélection: {str(e)[:200]}",
                "awaiting_intent"
            )

    # =============================================================
    #  MONITORING: Sélection d'instances pour monitoring
    # =============================================================
    if session.state == "awaiting_monitoring_instance_selection" and not payload.action:
        try:
            available = get_available_instances_for_user(db, user.id)
            if not available:
                return send_bot_message(
                    "Aucune instance disponible. Démarre ou crée des instances puis réessaye.",
                    "awaiting_intent",
                )

            picked_ids = _resolve_selected_instance_ids(text)
            if not picked_ids:
                return send_bot_message(
                    "Sélection invalide. Réponds par 'all', 'toutes', ou des numéros (1,3,5).",
                    "awaiting_monitoring_instance_selection"
                )

            instances = (
                db.query(models.Instance)
                .join(models.Session, models.Instance.session_id == models.Session.id)
                .filter(models.Session.user_id == user.id)
                .filter(models.Instance.id.in_(picked_ids))
                .all()
            )
            instance_ids = [i.instance_id for i in instances]
            logger.info(f"[MONITORING_SELECTION] Instances sélectionnées: {instance_ids}")

            # Créer le plan de monitoring
            from app.services.monitoring_engine import MonitoringRunner, MONITORING_RECIPES
            
            runner = MonitoringRunner(db=db, ssm_executor=None)
            monitoring_plan = runner.create_plan(
                monitoring_type="metrics_snapshot",
                instance_ids=instance_ids,
            )

            # Stocker le plan dans session_temp_data
            session.state = "awaiting_monitoring_confirmation"
            session.session_temp_data = json.dumps({
                "plan": monitoring_plan.dict(),
                "original_text": json.loads(session.session_temp_data or "{}").get("original_text", text),
            })
            db.commit()

            # Formater et afficher le plan avec durée estimée améliorée
            duration_sec = monitoring_plan.estimated_duration_seconds or 30
            duration_min = duration_sec // 60
            duration_display = f"{duration_min}m" if duration_min > 0 else f"{duration_sec}s"
            recipe = MONITORING_RECIPES.get(monitoring_plan.monitoring_type)
            plan_msg = (
                f" **Plan de monitoring**\n\n"
                f" **Durée estimée: ~{duration_display}**\n"
                f" Instances: {monitoring_plan.instances_count}\n"
                f" Recette: {monitoring_plan.monitoring_type}\n\n"
            )
            if recipe:
                plan_msg += f"**Métriques collectées** (par instance):\n"
                for cmd_name in recipe.commands.keys():
                    plan_msg += f"  - `{cmd_name}`\n"

            plan_msg += "\n Tape **'ok'** ou **'lancer'** pour confirmer, ou **'annuler'** pour abandonner."

            return send_bot_message(plan_msg, "awaiting_monitoring_confirmation")
        
        except Exception as e:
            logger.exception(
                "[MONITORING_SELECTION_ERROR] Échec lors de la sélection d'instances pour monitoring (texte)",
                extra={"session_id": session.id, "user_id": user.id, "text": text}
            )
            return send_bot_message(
                f" Erreur lors de la sélection: {str(e)[:200]}",
                "awaiting_intent"
            )

    # =============================================================
    #  AUDIT: Confirmation et exécution
    # =============================================================
    if session.state == "awaiting_audit_confirmation":
        confirm_keywords = {"oui", "yes", "ok", "go", "lancer", "lance"}
        deny_keywords = {"non", "no", "stop", "cancel", "annuler"}

        if command in deny_keywords:
            session.state = "awaiting_intent"
            session.session_temp_data = None
            db.commit()
            return send_bot_message(" Audit annulé.", "awaiting_intent")

        if command not in confirm_keywords:
            return send_bot_message(
                "Réponds par **'ok'** pour lancer l'audit, ou **'annuler'** pour abandonner.",
                "awaiting_audit_confirmation"
            )

        # Préparer l'exécution audit via workflow Execution
        data = json.loads(session.session_temp_data or "{}")
        plan_data = data.get("plan", {})
        instance_ids = plan_data.get("instance_ids", [])
        recipe_names = plan_data.get("recipe_names", []) or ["ops_health"]

        creds = get_user_aws_credentials(user.id, db)
        if not creds:
            return send_bot_message(
                "AWS credentials manquants. Ajoute-les via /user/aws-credentials.",
                "awaiting_intent"
            )

        # Handle creds format (Dict or model object) — region uniquement
        if isinstance(creds, dict):
            region = creds.get("region", "eu-north-1")
        else:
            region = getattr(creds, "region", None) or "eu-north-1"

        execution = models.Execution(
            user_id=user.id,
            session_id=session.id,
            task_type="audit",
            status="pending",
            extra_data=json.dumps({
                "session_id": session.id,
                "region": region,
                "instance_ids": instance_ids,
                "recipe_names": recipe_names,
                "progress": 0,
                "progress_message": "En attente de lancement",
                "progress_phase": "pending",
            }),
        )
        db.add(execution)
        db.commit()
        db.refresh(execution)
        logger.info("[AUDIT_EXEC_CREATED] execution_id=%s", execution.id)

        session.state = "executing"
        session.session_temp_data = json.dumps({
            "execution_id_db": execution.id,
            "plan": plan_data,
            "original_text": data.get("original_text", ""),
        })
        db.commit()

        from app.services.execution_handlers import run_execution_by_id

        async def _run_audit_background():
            bg_db = database.SessionLocal()
            try:
                bg_session = bg_db.query(models.Session).filter_by(id=session.id).first()
                bg_chat = bg_db.query(models.Chat).filter_by(id=chat.id).first()
                if not bg_session or not bg_chat:
                    return

                # Utiliser run_execution_by_id() pour passer par les handlers unifiés
                result = await run_execution_by_id(
                    db=bg_db,
                    execution_id=execution.id,
                    user_id=user.id,
                )

                audit_result = result.get("audit_result") or {}
                report_path = result.get("report_path")

                status = audit_result.get("status", "unknown")
                summary = audit_result.get("summary", {})
                instances = audit_result.get("instances", [])

                result_msg = f" **Audit terminé** ({status})\n\n"
                if status in {"failed", "partial"}:
                    result_msg += (
                        "Note: l'audit DAC passe par AWS SSM. Si des VM échouent, vérifie "
                        "que l'agent SSM est online, que le rôle IAM contient "
                        "AmazonSSMManagedInstanceCore, et que les credentials AWS sont valides.\n\n"
                    )
                result_msg += " **Résumé global**:\n"
                result_msg += f"  • Total instances: {summary.get('instances_total', len(instances))}\n"
                result_msg += f"  •  OK: {summary.get('ok', 0)}\n"
                result_msg += f"  •  Failed: {summary.get('failed', 0)}\n"

                severity_counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0}
                for inst_result in instances:
                    for finding in inst_result.get("findings", []) or []:
                        severity = (finding.get("severity") or "").upper()
                        if severity in severity_counts:
                            severity_counts[severity] += 1

                total_findings = sum(severity_counts.values())
                result_msg += f"  •  Total findings: {total_findings}\n"
                if severity_counts["CRITICAL"] > 0:
                    result_msg += f"     CRITICAL: {severity_counts['CRITICAL']}\n"
                if severity_counts["HIGH"] > 0:
                    result_msg += f"     HIGH: {severity_counts['HIGH']}\n"
                if severity_counts["MEDIUM"] > 0:
                    result_msg += f"     MEDIUM: {severity_counts['MEDIUM']}\n"
                if severity_counts["LOW"] > 0:
                    result_msg += f"     LOW: {severity_counts['LOW']}\n"
                if severity_counts["INFO"] > 0:
                    result_msg += f"     INFO: {severity_counts['INFO']}\n"

                result_msg += "\n"
                result_msg += " **Détail par instance**:\n\n"
                for i, instance_result in enumerate(instances, 1):
                    result_msg += f"** Instance {i}: {instance_result.get('instance_id', 'n/a')}** ({instance_result.get('status', 'n/a')})\n"

                    findings = instance_result.get("findings", []) or []
                    if findings:
                        by_severity = {}
                        for finding in findings:
                            by_severity.setdefault(finding.get("severity"), []).append(finding)

                        result_msg += f"  Findings: {len(findings)}\n"
                        for severity in ["critical", "high", "medium", "low", "info"]:
                            if severity in by_severity:
                                icon = "" if severity == "critical" else "" if severity == "high" else "" if severity == "medium" else "" if severity == "low" else ""
                                result_msg += f"    {icon} {severity.upper()}: {len(by_severity[severity])}\n"
                                for j, finding in enumerate(by_severity[severity][:3], 1):
                                    title = finding.get("title", "")
                                    result_msg += f"      {j}. {title}\n"
                                    desc = finding.get("description")
                                    if desc:
                                        short_desc = desc[:100] + "..." if len(desc) > 100 else desc
                                        result_msg += f"         -> {short_desc}\n"
                                if len(by_severity[severity]) > 3:
                                    result_msg += f"      ... et {len(by_severity[severity]) - 3} autres\n"
                    else:
                        result_msg += "   Aucun finding\n"

                    result_msg += "\n"

                result_msg += " **Sauvegardé**: JSON + DB\n"
                if report_path:
                    result_msg += f" Rapport: {report_path}\n"
                result_msg += " Détails: GET /dashboard/audits/history"

                bg_session.state = "awaiting_intent"
                bg_session.session_temp_data = None
                bg_db.commit()

                bg_db.add(models.Message(
                    session_id=bg_session.id,
                    chat_id=bg_chat.id,
                    sender="bot",
                    text=result_msg,
                    extra={
                        "state": "awaiting_intent",
                        "audit_result": audit_result,
                        "report_path": report_path,
                        "execution_id_db": execution.id,
                        "execution_type": "audit",
                    },
                ))
                bg_db.commit()
            except Exception as e:
                logger.exception("[AUDIT_BACKGROUND_ERROR] %s", str(e))
                try:
                    bg_session = bg_db.query(models.Session).filter_by(id=session.id).first()
                    bg_chat = bg_db.query(models.Chat).filter_by(id=chat.id).first()
                    if bg_session and bg_chat:
                        bg_session.state = "awaiting_intent"
                        bg_session.session_temp_data = None
                        bg_db.add(models.Message(
                            session_id=bg_session.id,
                            chat_id=bg_chat.id,
                            sender="bot",
                            text=f" Erreur audit: {str(e)[:200]}",
                            extra={"state": "awaiting_intent"},
                        ))
                        bg_db.commit()
                except Exception:
                    bg_db.rollback()
            finally:
                bg_db.close()

        asyncio.create_task(_run_audit_background())

        logger.info(
            "[AUDIT_RESPONSE] Returning to frontend: execution_id_db=%s",
            execution.id,
        )

        return send_bot_message(
            "Audit lancé.",
            "executing",
            {
                "execution_id_db": execution.id,
                "execution_type": "audit",
            },
        )

    # =============================================================
    #  MONITORING: Confirmation et exécution
    # =============================================================
    if session.state == "awaiting_monitoring_confirmation":
        confirm_keywords = {"oui", "yes", "ok", "go", "lancer", "lance"}
        deny_keywords = {"non", "no", "stop", "cancel", "annuler"}

        if command in deny_keywords:
            session.state = "awaiting_intent"
            session.session_temp_data = None
            db.commit()
            return send_bot_message(" Monitoring annulé.", "awaiting_intent")

        if command not in confirm_keywords:
            return send_bot_message(
                "Réponds par **'ok'** pour lancer la collecte, ou **'annuler'** pour abandonner.",
                "awaiting_monitoring_confirmation"
            )

        # Créer Execution pour monitoring et lancer via run_execution_by_id()
        data = json.loads(session.session_temp_data or "{}")
        plan_data = data.get("plan", {})
        
        execution = models.Execution(
            user_id=user.id,
            session_id=session.id,
            task_type="monitoring",
            status="pending",
            extra_data=json.dumps({
                "session_id": session.id,
                "plan": plan_data,
                "progress": 0,
                "progress_message": "En attente de lancement",
                "progress_phase": "pending",
            }),
        )
        db.add(execution)
        db.commit()
        db.refresh(execution)
        logger.info("[MONITORING_EXEC_CREATED] execution_id=%s", execution.id)

        session.state = "executing"
        session.session_temp_data = json.dumps({
            "execution_id_db": execution.id,
            "plan": plan_data,
        })
        db.commit()

        from app.services.execution_handlers import run_execution_by_id

        async def _run_monitoring_background():
            bg_db = database.SessionLocal()
            try:
                # Utiliser run_execution_by_id() pour passer par les handlers unifiés
                result = await run_execution_by_id(
                    db=bg_db,
                    execution_id=execution.id,
                    user_id=user.id,
                )

                metrics_snapshot = result.get("metrics_snapshot", {})
                snapshot_path = result.get("snapshot_path", "")
                summary = metrics_snapshot.get("summary", {})
                instances = metrics_snapshot.get("instances", [])

                result_msg = f" **Monitoring AWS - Résultats**\n\n"
                result_msg += f" **Résumé global**:\n"
                result_msg += f"  • Total instances: {summary.get('instances_total', 0)}\n"
                result_msg += f"  • OK OK: {summary.get('instances_ok', 0)}\n"
                result_msg += f"  • ERR Failed: {summary.get('instances_failed', 0)}\n\n"

                # Afficher les détails de chaque instance
                if instances:
                    result_msg += f" **Détails par instance**:\n\n"
                    for inst in instances:
                        inst_id = inst.get('instance_id', 'N/A')
                        status = inst.get('status', 'unknown')
                        metrics = inst.get('metrics', {})
                        
                        status_icon = "OK" if status == "ok" else "ERR"
                        result_msg += f"{status_icon} **{inst_id}**\n"
                        
                        if metrics:
                            cpu = metrics.get('cpu_usage', 'N/A')
                            mem_used = metrics.get('memory_used_mb', 'N/A')
                            mem_total = metrics.get('memory_total_mb', 'N/A')
                            disk_used = metrics.get('disk_used_gb', 'N/A')
                            disk_total = metrics.get('disk_total_gb', 'N/A')
                            
                            result_msg += f"  • CPU: {cpu}%\n"
                            result_msg += f"  • RAM: {mem_used}/{mem_total} MB\n"
                            result_msg += f"  • Disk: {disk_used}/{disk_total} GB\n"
                        
                        result_msg += "\n"

                result_msg += f" **Snapshot sauvegardé**: `{snapshot_path.split('/')[-1]}`\n"
                result_msg += f" Chemin complet: `{snapshot_path}`"

                # Mettre à jour le chat avec le résultat
                final_msg = models.Message(
                    chat_id=chat.id,
                    session_id=session.id,
                    sender="bot",
                    text=result_msg,
                    extra=json.dumps({
                        "state": "awaiting_intent",
                        "metrics_snapshot": metrics_snapshot,
                        "snapshot_path": snapshot_path,
                    }),
                )
                bg_db.add(final_msg)

                bg_session = bg_db.query(models.Session).filter_by(id=session.id).first()
                if bg_session:
                    bg_session.state = "awaiting_intent"
                    bg_session.session_temp_data = json.dumps({})
                
                bg_db.commit()

            except Exception as e:
                logger.exception("[MONITORING_BACKGROUND_ERROR] Monitoring execution failed")
                final_msg = models.Message(
                    chat_id=chat.id,
                    session_id=session.id,
                    sender="bot",
                    text=f" Erreur monitoring: {str(e)[:200]}",
                    extra=json.dumps({"state": "awaiting_intent"}),
                )
                bg_db.add(final_msg)
                
                bg_session = bg_db.query(models.Session).filter_by(id=session.id).first()
                if bg_session:
                    bg_session.state = "awaiting_intent"
                    bg_session.session_temp_data = json.dumps({})
                
                bg_db.commit()
            finally:
                bg_db.close()

        asyncio.create_task(_run_monitoring_background())

        return send_bot_message(
            " Monitoring lancé… Collecte en cours.",
            "executing",
            {"execution_id_db": execution.id, "execution_id": execution.id}
        )
        
        session.state = "awaiting_intent"
        session.session_temp_data = None
        db.commit()
        
        return send_bot_message(
            result_msg,
            "awaiting_intent",
            {"metrics": metrics_snapshot.dict(), "snapshot_path": snapshot_path},
        )

    # Support text-based selection when awaiting_instance_selection
    if session.state == "awaiting_instance_selection" and not payload.action:
        #  Forcer une sync AWS->BDD avant d'interpréter la sélection
        try:
            creds_model = get_user_aws_credentials(user.id, db)
            if creds_model:
                from app.utils.crypto import decrypt
                # Normaliser les credentials
                if hasattr(creds_model, "encrypted_access_key"):
                    aws_access = decrypt(creds_model.encrypted_access_key)
                    aws_secret = decrypt(creds_model.encrypted_secret_key)
                    region = getattr(creds_model, "region", None) or "eu-north-1"
                else:
                    aws_access = creds_model.get("access_key_id") or creds_model.get("AWS_ACCESS_KEY_ID")
                    aws_secret = creds_model.get("secret_access_key") or creds_model.get("AWS_SECRET_ACCESS_KEY")
                    region = creds_model.get("region") or "eu-north-1"
                sync_aws_instances_to_db(
                    db=db,
                    session_id=session.id,
                    aws_access_key=aws_access,
                    aws_secret_key=aws_secret,
                    region=region,
                )
        except Exception as e:
            logger.warning(f" AWS sync skipped (awaiting_instance_selection): {e}")

        # Recharger les instances filtrées et résoudre la sélection
        available_after_sync = get_available_instances_for_user(db, user.id)
        if not available_after_sync:
            return send_bot_message(
                "Aucune instance AWS disponible après synchronisation. Crée ou démarre des instances puis relance la commande.",
                "awaiting_intent",
            )

        picked_ids = _resolve_selected_instance_ids(text)
        if not picked_ids:
            return send_bot_message("Aucune instance sélectionnée. Réponds par 'toutes' ou '1,2'.", "awaiting_instance_selection")
        instances = (
            db.query(models.Instance)
            .join(models.Session, models.Instance.session_id == models.Session.id)
            .filter(models.Session.user_id == user.id)
            .filter(models.Instance.id.in_(picked_ids))
            .all()
        )
        if not instances:
            return send_bot_message("Aucune instance trouvée pour ces IDs.", "awaiting_instance_selection")
        original_text = session.session_temp_data or text
        # Start strict workflow - create Execution and background task
        execution = models.Execution(
            user_id=user.id,
            session_id=session.id,
            task_type="configure",
            status="pending",
            extra_data=json.dumps({
                "instances": [{"id": inst.id, "instance_id": inst.instance_id} for inst in instances],
                "original_text": original_text,
                "progress": 0,
                "progress_message": "En attente de lancement",
                "progress_phase": "pending",
            }),
        )
        db.add(execution)
        db.commit()
        db.refresh(execution)
        logger.info("[CONFIGURE_EXEC_CREATED] execution_id=%s", execution.id)

        session.state = "executing"
        session.session_temp_data = None
        db.commit()

        from app.services.execution_handlers import run_execution_by_id

        async def _run_configure_background_task3():
            bg_db = database.SessionLocal()
            try:
                # Utiliser run_execution_by_id pour passer par la pipeline unifiée
                result = await run_execution_by_id(
                    db=bg_db,
                    execution_id=execution.id,
                    user_id=user.id,
                )
                
                # Format et save résultat au chat
                # VALIDATION: Ne pas forcer "success" si le résultat montre un échec
                is_success = result.get("success", False)
                
                # Pour installer_configure: vérifier aussi le status du résultat
                if not is_success and "result" in result:
                    inner_result = result.get("result", {})
                    if isinstance(inner_result, dict):
                        # Vérifier batch_execution summary pour configure_only
                        if "batch_execution" in inner_result:
                            summary = inner_result.get("batch_execution", {}).get("summary", {})
                            success_count = summary.get("success", 0)
                            failed_count = summary.get("failed", 0)
                            total_count = summary.get("total", 0)
                            is_success = success_count > 0 and failed_count == 0
                        # Vérifier status pour installer_configure
                        elif "status" in inner_result:
                            is_success = inner_result.get("status") in ["success", "partial"]
                
                # Construire le message avec le bon emoji/statut
                if is_success:
                    result_msg = f"OK **Configuration terminée avec succès**\n\n"
                    result_msg += f"OK Configuration appliquée avec succès\n"
                    if result.get("details"):
                        result_msg += f"\n **Détails**:\n{result.get('details')}\n"
                else:
                    # Afficher erreur ou échec partiel
                    result_msg = f"ERR **Configuration échouée ou incomplète**\n\n"
                    
                    # Chercher le message d'erreur le plus pertinent
                    error_msg = None
                    inner_result = result.get("result", {})
                    
                    if isinstance(inner_result, dict):
                        # Pour configure_only: batch_execution avec per_instance_results
                        if "batch_execution" in inner_result:
                            summary = inner_result.get("batch_execution", {}).get("summary", {})
                            failed_count = summary.get("failed", 0)
                            timeout_count = summary.get("timeout", 0)
                            error_msg = f"Résultats: {summary.get('success', 0)} succès, {failed_count} échoués, {timeout_count} timeouts"
                        # Pour installer_configure
                        elif "status" in inner_result:
                            status = inner_result.get("status")
                            error_msg = f"Status: {status}. Voir les logs d'exécution pour plus de détails."
                    
                    if not error_msg:
                        error_msg = inner_result.get('message', 'Unknown error') if isinstance(inner_result, dict) else 'Erreur inconnue'
                    
                    result_msg += f"ERR Erreur: {error_msg}\n"
                    if result.get("details"):
                        result_msg += f"\n **Détails**:\n{result.get('details')}\n"

                final_msg = models.Message(
                    chat_id=chat.id,
                    session_id=session.id,
                    sender="bot",
                    text=result_msg,
                    extra=json.dumps({"state": "awaiting_intent", "configure_result": result}),
                )
                bg_db.add(final_msg)

                bg_session = bg_db.query(models.Session).filter_by(id=session.id).first()
                if bg_session:
                    bg_session.state = "awaiting_intent"
                    bg_session.session_temp_data = None
                
                bg_db.commit()
            except Exception as e:
                logger.exception("[CONFIGURE_BACKGROUND_ERROR] Configuration execution failed")
                final_msg = models.Message(
                    chat_id=chat.id,
                    session_id=session.id,
                    sender="bot",
                    text=f"ERR Erreur configure: {str(e)[:200]}",
                    extra=json.dumps({"state": "awaiting_intent"}),
                )
                bg_db.add(final_msg)
                
                bg_session = bg_db.query(models.Session).filter_by(id=session.id).first()
                if bg_session:
                    bg_session.state = "awaiting_intent"
                    bg_session.session_temp_data = None
                
                bg_db.commit()
            finally:
                bg_db.close()

        asyncio.create_task(_run_configure_background_task3())
        return send_bot_message("Diagnostic SSM en cours avant configuration.", "executing", {"execution_id_db": execution.id})

    # =============================================================
    #  Bloc 2 — Détection d’intention (awaiting_intent)
    # Rôle : analyse GPT + fallback (create, configure, audit, kubernetes)
    # =============================================================

    if session.state == "awaiting_ssm_fix_confirm":
        data = {}
        try:
            data = json.loads(session.session_temp_data or "{}")
        except Exception:
            data = {}

        confirm_keywords = {"oui", "yes", "ok", "go", "configure ssm", "configurer ssm", "lance"}
        fallback_keywords = {"ansible", "fallback ansible"}
        deny_keywords = {"non", "no", "stop", "cancel"}

        if command in fallback_keywords and data.get("resume_intent") == "configure":
            # Lancer configuration via Ansible (SSH) sur la sélection précédente
            selected_ids = data.get("selected_instance_ids", [])
            if not selected_ids:
                return send_bot_message("Aucune sélection d'instances en mémoire.", "awaiting_intent")

            instance_rows = (
                db.query(models.Instance, models.Session)
                .join(models.Session, models.Instance.session_id == models.Session.id)
                .filter(models.Session.user_id == user.id)
                .filter(models.Instance.id.in_(selected_ids))
                .all()
            )
            instances = [row[0] for row in instance_rows]
            if not instances:
                return send_bot_message("Aucune instance trouvée pour exécuter Ansible.", "awaiting_intent")

            base_dir = Path(os.path.join(os.path.dirname(__file__), "../../generated_files")).resolve()
            original_text = data.get("original_text", text)
            ansible_results = handle_configure_via_ansible(original_text, instances, base_dir)

            session.state = "awaiting_intent"
            session.session_temp_data = None
            db.commit()

            return send_bot_message(
                "Configuration lancée via Ansible (fallback).",
                "awaiting_intent",
                {"results": ansible_results},
            )

        if command in confirm_keywords:
            creds = get_user_aws_credentials(user.id, db)
            if not creds:
                return send_bot_message(
                    "AWS credentials manquants. Ajoutez-les via /user/aws-credentials.",
                    "awaiting_intent",
                )

            blocked = data.get("blocked_instances") or []
            instance_ids = [b.get("instance_id") for b in blocked if b.get("instance_id")]

            if not instance_ids:
                diag, err = _run_ssm_diag(user.id, db)
                if diag:
                    instance_ids = [b.get("instance_id") for b in diag.get("blocked_instances", []) if b.get("instance_id")]

            if not instance_ids:
                session.state = "awaiting_intent"
                db.commit()
                return send_bot_message("Aucune instance à bootstrap. Relance une sync, ou recrée via DAC.", "awaiting_intent")

            # Normaliser credentials avant utilisation
            creds_normalized = {}
            if hasattr(creds, "encrypted_access_key"):
                from app.utils.crypto import decrypt
                creds_normalized = {
                    "access_key_id": decrypt(creds.encrypted_access_key),
                    "secret_access_key": decrypt(creds.encrypted_secret_key),
                    "region": getattr(creds, "region", None) or "eu-north-1"
                }
            else:
                creds_normalized = {
                    "access_key_id": creds.get("access_key_id") or creds.get("AWS_ACCESS_KEY_ID"),
                    "secret_access_key": creds.get("secret_access_key") or creds.get("AWS_SECRET_ACCESS_KEY"),
                    "region": creds.get("region") or "eu-north-1"
                }

            bootstrap_result = bootstrap_ssm_attach_profile(
                instance_ids=instance_ids,
                region=creds_normalized.get("region") or "eu-north-1",
                aws_access_key=creds_normalized.get("access_key_id"),
                aws_secret_key=creds_normalized.get("secret_access_key"),
            )

            if bootstrap_result.get("blocked_instances"):
                session.state = "awaiting_intent"
                db.commit()
                return send_bot_message(
                    "Certaines instances ont déjà un profile IAM différent. Pas de remplacement automatique."
                    " Supprimez le profil existant manuellement ou recréez via DAC (SSM-ready).",
                    "awaiting_intent",
                    {"bootstrap_result": bootstrap_result},
                )

            # Poll PingStatus after attach (up to ~2 minutes)
            poll_states = wait_for_ssm_online(
                instance_ids=instance_ids,
                region=creds_normalized.get("region") or "eu-north-1",
                aws_access_key=creds_normalized.get("access_key_id"),
                aws_secret_key=creds_normalized.get("secret_access_key"),
                attempts=6,
                delay_seconds=20,
            )

            diag_after, err = _run_ssm_diag(user.id, db)
            session.state = "awaiting_intent"
            db.commit()

            if diag_after and diag_after.get("total_ssm_online_aws", 0) > 0:
                resume_intent = data.get("resume_intent", "configure")
                original_text = data.get("original_text", text)

                if resume_intent == "configure":
                    #  Synchroniser AWS -> DB avant la sélection d'instances
                    try:
                        creds_model = get_user_aws_credentials(user.id, db)
                        if creds_model:
                            from app.utils.crypto import decrypt
                            aws_access = decrypt(creds_model.encrypted_access_key)
                            aws_secret = decrypt(creds_model.encrypted_secret_key)
                            region = getattr(creds_model, "region", None) or "eu-north-1"
                            sync_aws_instances_to_db(
                                db=db,
                                session_id=session.id,
                                aws_access_key=aws_access,
                                aws_secret_key=aws_secret,
                                region=region,
                            )
                    except Exception as e:
                        logger.warning(f" AWS sync skipped (configure resume): {e}")

                    available = get_available_instances_for_user(db, user.id)
                    session.state = "awaiting_instance_selection"
                    session.session_temp_data = json.dumps({"original_text": original_text})
                    db.commit()
                    return send_bot_message(
                        "SSM OK . Sélectionne les VM à configurer.",
                        "awaiting_instance_selection",
                        {"available_instances": available, "diagnostic": diag_after, "bootstrap_result": bootstrap_result, "poll_states": poll_states},
                    )

                if resume_intent == "audit":
                    session.state = "awaiting_audit_tool"
                    db.commit()
                    return send_bot_message(
                        "SSM OK . Quel outil d’audit veux-tu ? (lynis / auditd)",
                        "awaiting_audit_tool",
                        {"diagnostic": diag_after, "bootstrap_result": bootstrap_result, "poll_states": poll_states},
                    )

                return send_bot_message(
                    "SSM OK . Relance ta commande.",
                    "awaiting_intent",
                    {"diagnostic": diag_after, "bootstrap_result": bootstrap_result, "poll_states": poll_states},
                )

            # Toujours bloqué
            summary = _format_block_summary(diag_after or {})
            return send_bot_message(
                "SSM toujours bloqué après tentative de bootstrap.\n"
                f"Raison: {summary}\n"
                "Options: recréer via DAC (SSM-ready), activer VPC endpoints SSM/EC2Messages/SSMMessages, ou basculer en SSH (fallback).",
                "awaiting_intent",
                {"diagnostic": diag_after, "bootstrap_result": bootstrap_result, "poll_states": poll_states},
            )

        if command in deny_keywords:
            session.state = "awaiting_intent"
            db.commit()
            return send_bot_message(
                "Compris. Options: recréer via DAC (SSM-ready), ajouter endpoints SSM, ou fallback SSH.",
                "awaiting_intent",
            )

        return send_bot_message("Réponds par 'oui' pour configurer SSM, ou 'non' pour annuler.", "awaiting_ssm_fix_confirm")

    if session.state == "awaiting_create_params":
        session.request_text = text
        session.session_temp_data = json.dumps({
            "original_text": text,
            "intent_type": "create",
        })
        db.commit()
        return send_bot_message(
            "Paramètres CREATE reçus. Je peux générer le Terraform. Tape `ok` pour confirmer ou `annuler`.",
            "awaiting_create_confirmation",
            {"intent_type": "create", "request_text": text},
        )

    if session.state == "awaiting_create_confirmation":
        if command in {"annuler", "cancel", "non", "no"}:
            session.state = "awaiting_intent"
            session.session_temp_data = None
            db.commit()
            return send_bot_message("Création annulée.", "awaiting_intent")

        if command not in {"ok", "oui", "yes", "go", "lancer"}:
            return send_bot_message(
                "Réponds par `ok` pour générer Terraform ou `annuler`.",
                "awaiting_create_confirmation",
            )

        data = json.loads(session.session_temp_data or "{}")
        original_text = data.get("original_text", session.request_text or text)
        intent = models.Intent(
            session_id=session.id,
            intent_type="create",
            prompt=original_text,
            runtime="terraform",
        )
        db.add(intent)
        db.commit()
        db.refresh(intent)

        aws_creds = get_user_aws_credentials(user.id, db)
        if not aws_creds:
            session.state = "awaiting_intent"
            session.session_temp_data = None
            db.commit()
            return send_bot_message(
                "Credentials AWS manquantes. Configure-les puis relance la création.",
                "awaiting_intent",
                {"requires_credentials": True, "redirect_to": "credentials"},
            )

        valid_aws, aws_validation = validate_aws_credentials(aws_creds)
        if not valid_aws:
            session.state = "awaiting_intent"
            session.session_temp_data = None
            db.commit()
            return send_bot_message(
                aws_validation.get("message", "Credentials AWS invalides. Configure-les puis relance."),
                "awaiting_intent",
                {"requires_credentials": True, "redirect_to": "credentials", "aws_validation": aws_validation},
            )

        from app.services.provider_service import get_or_create_provider
        provider = get_or_create_provider(user.id, "aws", aws_creds, session.id, db)
        from app.utils.crypto import encrypt
        provider.encrypted_credentials = encrypt(aws_creds)
        session.provider = "aws"
        db.commit()

        auth_header = request.headers.get("authorization")
        if not auth_header:
            session.state = "awaiting_intent"
            db.commit()
            return send_bot_message("Token d'authentification manquant.", "awaiting_intent")

        from app.services.task_manager import TaskManager
        task_manager = TaskManager()
        task_id = await task_manager.create_task(
            task_type="terraform",
            user_id=user.id,
            session_id=session.id,
            task_data={
                "intent_id": intent.id,
                "intent_type": "terraform",
                "session_id": session.id,
                "user_id": user.id,
            },
            db=db,
        )
        await task_manager.start_task_execution(
            task_id=task_id,
            execution_func=execute_infrastructure_creation,
            db=db,
            intent_id=intent.id,
            session_id=session.id,
            user_id=user.id,
            auth_header=auth_header,
            chat_id=chat.id,
        )
        session.state = "executing"
        session.session_temp_data = json.dumps({"task_id": task_id, "intent_id": intent.id})
        db.commit()
        return send_bot_message(
            "Création Terraform lancée en arrière-plan.",
            "executing",
            {"task_id": task_id, "intent_id": intent.id},
        )

    if session.state == "awaiting_intent":
        # Priorité 1: menu/help
        if fast_command == "SHOW_MENU":
            # On ne return plus le welcome seul, la commande continue
            pass

        # ============================================================================
        #  P0.5.1 — SSM Status Check Intent (priority check before generic intent detection)
        # ============================================================================
        logger.info(f"Testing SSM check for: {text[:50]}")
        if detect_ssm_check_intent(text):
            logger.info(" SSM check intent detected!")
            # Get AWS credentials
            creds = get_user_aws_credentials(user.id, db)
            if not creds:
                return send_bot_message(
                    " Pas de credentials AWS configurées.\n\n"
                    "Configure tes credentials AWS d'abord ou contacte l'admin.",
                    "awaiting_intent"
                )
            
            try:
                # Run SSM diagnostics
                diag, diag_err = _run_ssm_diag(user.id, db)
                
                if diag_err:
                    return send_bot_message(
                        f" Erreur lors du diagnostic SSM: {diag_err}",
                        "awaiting_intent"
                    )
                
                if not diag:
                    return send_bot_message(
                        " Impossible de récupérer le diagnostic SSM.",
                        "awaiting_intent"
                    )
                
                # Format response
                total_online = diag.get("total_ssm_online_aws", 0)
                total_instances = diag.get("total_instances_aws", 0)
                summary = diag.get("summary", "Diagnostic SSM effectué")
                
                if total_online == 0:
                    blocked_summary = _format_block_summary(diag)
                    session.state = "awaiting_ssm_fix_confirm"
                    session.session_temp_data = json.dumps({
                        "resume_intent": "ssm_check",
                        "original_text": text,
                        "blocked_instances": diag.get("blocked_instances", []),
                    })
                    db.commit()
                    
                    return send_bot_message(
                        f" Diagnostic SSM:\n{summary}\n"
                        f"Blocages: {blocked_summary}\n\n"
                        "Souhaites-tu que je configure automatiquement SSM sur ces VM ? (réponds 'oui')",
                        "awaiting_ssm_fix_confirm",
                        {"diagnostic": diag}
                    )
                else:
                    response_text = (
                        f" Diagnostic SSM:\n"
                        f"• Instances AWS trouvées: {total_instances}\n"
                        f"• Instances SSM online: {total_online}\n"
                        f"• {summary}"
                    )
                    return send_bot_message(response_text, "awaiting_intent", {"diagnostic": diag})
            
            except Exception as e:
                logger.error(f"SSM diagnostic failed: {e}")
                return send_bot_message(
                    f" Erreur lors du diagnostic SSM: {str(e)[:100]}",
                    "awaiting_intent"
                )
        
        # ============================================================================
        #  Intent Detection: Utilise le catalogue deterministe (config_catalog)
        # ============================================================================
        detected_intent = detect_intent_with_catalog(
            text=text,
            last_action_id=json.loads(session.session_temp_data or "{}").get("pending_action_id"),
        )
        
        session.request_text = text
        db.commit()
        
        # Log détection
        logger.info(f"[INTENT_DETECTION] type={detected_intent.intent_type}, action={detected_intent.action_id}, confidence={detected_intent.confidence:.2f}")
        
        # Routage selon le type d'intent détecté
        if detected_intent.intent_type == "create":
            return send_bot_message(
                "Intent create détectée. Donne une phrase complète: AWS, Ubuntu 22.04, t3.micro, eu-north-1, nginx.",
                "awaiting_create_params"
            )
        
        elif detected_intent.intent_type == "audit":
            if not has_user_aws_credentials(user.id, db):
                return redirect_credentials_message()
            
            available = get_available_instances_for_user(db, user.id)
            if not available:
                return send_bot_message(
                    "Aucune instance disponible. Crée ou démarre des instances puis réessaie.",
                    "awaiting_intent",
                )
            
            session.state = "awaiting_audit_instance_selection"
            session.session_temp_data = json.dumps({"original_text": text})
            db.commit()
            
            return send_bot_message(
                "Sélectionne les VM à auditer (ou 'toutes'):",
                "awaiting_audit_instance_selection",
                {"available_instances": available},
            )
        
        elif detected_intent.intent_type == "monitoring":
            if not has_user_aws_credentials(user.id, db):
                return redirect_credentials_message()
            
            available = get_available_instances_for_user(db, user.id)
            if not available:
                return send_bot_message(
                    "Aucune instance disponible. Crée ou démarre des instances puis réessaie.",
                    "awaiting_intent",
                )
            
            session.state = "awaiting_monitoring_instance_selection"
            session.session_temp_data = json.dumps({"original_text": text})
            db.commit()
            
            return send_bot_message(
                "Sélectionne les VM à monitorer (ou 'toutes'):",
                "awaiting_monitoring_instance_selection",
                {"available_instances": available},
            )
        
        elif detected_intent.intent_type == "configure":
            return handle_configure_intent(
                user=user,
                db=db,
                chat=chat,
                session=session,
                text=text,
                detected_intent=detected_intent,
                send_bot_message=send_bot_message,
            )
        
        elif detected_intent.intent_type == "free_chat":
            # Passer au free_chat handler
            pass
        
        # Fallback si rien ne match
        return send_bot_message(
            "Je n'ai pas compris l'intention. Essaie: 'créer', 'configurer', 'auditer' ou 'monitorer'.",
            "awaiting_intent"
        )
        # Fallback si rien ne match
        return send_bot_message(
            "Je n'ai pas compris l'intention. Essaie: 'créer', 'configurer', 'auditer' ou 'monitorer'.",
            "awaiting_intent"
        )

    #  ANTI-SILENCE FINAL
    # Si aucune branche n'a matched, on retourne un message guidé avec l'état courant
    logger.warning(f"[ANTI_SILENCE] No branch matched. session_id={session.id}, state={session.state}, text={text[:50]}")

    state_help = {
        "awaiting_instance_selection": "Tu es dans **Configuration -> sélection d'instances**. Réponds par `toutes` ou `1,3`.",
        "awaiting_audit_instance_selection": "Tu es dans **Audit -> sélection d'instances**. Réponds par `toutes` ou `1,3`.",
        "awaiting_audit_confirmation": "Tu es dans **Audit -> confirmation**. Réponds par `ok` pour lancer, ou `annuler`.",
        "awaiting_monitoring_instance_selection": "Tu es dans **Monitoring -> sélection d'instances**. Réponds par `toutes` ou `1,3`.",
        "awaiting_monitoring_confirmation": "Tu es dans **Monitoring -> confirmation**. Réponds par `ok` pour lancer, ou `annuler`.",
        "awaiting_ssm_fix_confirm": "Tu es dans **SSM -> confirmation bootstrap**. Réponds par `oui` ou `non`.",
        "deletion_mode": "Tu es dans **Suppression**. Donne des IDs, ou tape `lister`.",
    }
    hint = state_help.get(session.state, "Décris ta demande en une phrase.")

    return send_bot_message(
        "Je n'ai pas compris ta demande dans ce contexte.\n\n"
        f"État actuel: **{session.state}**\n"
        f"Aide: {hint}\n\n"
        "Tu peux aussi taper: `annuler`, `liste des ressources`, `audit`, `monitoring`, `configure`, `create`.",
        session.state
    )
