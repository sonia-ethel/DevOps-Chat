# app/routes/generate_routes.py
from fastapi import APIRouter, Depends, HTTPException, Body, Request
from sqlalchemy.orm import Session
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import json

from app import models, database
from app.auth import get_current_user
from app.security.rate_limit import limiter
from app.services.idempotency_service import (
    check_or_create_idempotency_key,
    mark_idempotency_completed,
    mark_idempotency_failed,
    extract_idempotency_key
)

# Planificateur (Terraform -> Ansible)
from app.services.plan_builder import build_plan

# Réutilise les générateurs unitaires existants
from app.routes.generate_terraform import generate_terraform as _generate_terraform
from app.routes.generate_ansible import generate_ansible as _generate_ansible

router = APIRouter()

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---------- Helpers ----------
def _get_session_checked(db: Session, user: models.User, session_id: int) -> models.Session:
    session = (
        db.query(models.Session)
        .filter(models.Session.id == session_id, models.Session.user_id == user.id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session introuvable ou non autorisée.")
    return session

def _get_intent_by_id_checked(db: Session, user: models.User, intent_id: int) -> models.Intent:
    intent = (
        db.query(models.Intent)
        .filter(models.Intent.id == intent_id)
        .join(models.Session)
        .filter(models.Session.user_id == user.id)
        .first()
    )
    if not intent:
        raise HTTPException(status_code=404, detail="Intent introuvable ou non autorisé.")
    return intent

def _find_intent_for_step_simple(
    db: Session,
    session_id: int,
    engine_type: str,
    domain: Optional[str],
) -> Optional[models.Intent]:
    """
    Sélectionne un intent par défaut (sans bundle) :
    - Terraform + domain == compute   -> intent_type=create
    - Terraform + domain != compute   -> intent_type=configure & mode in (infra,mixed) & configure_domain=domain
    - Ansible                         -> intent_type=configure & mode in (system,mixed) [+ filtre domain si fourni]
    """
    q = (
        db.query(models.Intent)
        .filter(models.Intent.session_id == session_id)
        .order_by(models.Intent.created_at.asc())
    )

    if engine_type == "terraform":
        if (domain or "").lower() == "compute":
            return q.filter(models.Intent.intent_type == "create").first()
        return (
            q.filter(
                models.Intent.intent_type == "configure",
                models.Intent.configure_mode.in_(["infra", "mixed"]),
                models.Intent.configure_domain == (domain or "").lower(),
            )
            .first()
        )

    if engine_type == "ansible":
        q = q.filter(
            models.Intent.intent_type == "configure",
            models.Intent.configure_mode.in_(["system", "mixed"]),
        )
        if domain:
            q = q.filter(models.Intent.configure_domain == domain.lower())
        return q.first()

    return None


def _create_execution_record(
    db: Session,
    user: models.User,
    *,
    session_id: int,
    intent_id: Optional[int],
    engine: str,               # "terraform" | "ansible"
    target_file_id: int,       # id en base du fichier généré (GeneratedTerraformFile/GeneratedPlaybook)
    task_type: Optional[str] = None,  # alias engine si le modèle l’attend
    extra_data: Optional[dict] = None,
    status: str = "pending"
) -> models.Execution:
    """
    Crée **une** exécution en base, liée à un fichier généré précis.
    On ne devine plus “le dernier fichier” : on pointe explicitement sur target_file_id.
    """
    payload_extra = json.dumps(extra_data or {})
    # Compat : certaines bases ont un champ 'engine', d'autres 'task_type' — on remplit ce qui existe.
    exec_kwargs = dict(
        user_id=user.id,
        session_id=session_id,
        status=status,
        target_file=target_file_id,
        extra_data=payload_extra,
        intent_id=intent_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    if hasattr(models.Execution, "task_type"):
        exec_kwargs["task_type"] = task_type or engine
    if hasattr(models.Execution, "engine"):
        exec_kwargs["engine"] = engine

    exec_obj = models.Execution(**exec_kwargs)
    db.add(exec_obj)
    db.commit()
    db.refresh(exec_obj)
    return exec_obj


# ---------- 1) Plan sec (pour affichage front) ----------
@router.post(
    "/generate/plan",
    tags=["Génération"],
    summary="Construire le plan d’orchestration (Terraform -> Ansible) pour une session"
)
def generate_plan(
    session_id: int = Body(..., description="ID de la session"),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> Dict[str, Any]:
    _get_session_checked(db, user, session_id)
    return build_plan(db, session_id=session_id)

# ---------- 2) Orchestration complète sous /generate ----------
@router.post(
    "/generate",
    tags=["Génération"],
    summary="Générer tous les artefacts d’une session (orchestration Terraform -> Ansible)",
)
@limiter.limit("10/minute")
async def generate_all(
    request: Request,
    session_id: Optional[int] = Body(None, description="ID de la session"),
    intent_id: Optional[int] = Body(None, description="(Optionnel) ID d'un intent pour déduire la session"),
    auto_create_executions: bool = Body(True, description="Créer automatiquement une exécution par artefact généré, dans l'ordre du plan."),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> Dict[str, Any]:
    #  P0.5 — IDEMPOTENCE CHECK
    idempotency_key = extract_idempotency_key(dict(request.headers))
    if not idempotency_key:
        raise HTTPException(
            status_code=400,
            detail="Header Idempotency-Key obligatoire pour /generate"
        )
    
    # Vérifier ou créer la clé d'idempotence
    idempotency_result = check_or_create_idempotency_key(
        db=db,
        user_id=user.id,
        idempotency_key=idempotency_key,
        scope="generate"
    )
    
    # Si déjà complétée, retourner la réponse mise en cache
    if idempotency_result.is_duplicate and idempotency_result.cached_response:
        return idempotency_result.cached_response
    
    # Compat : si on reçoit intent_id (ancien front), on en déduit la session
    if not session_id:
        if not intent_id:
            raise HTTPException(status_code=400, detail="session_id ou intent_id requis.")
        intent = (
            db.query(models.Intent)
            .filter(models.Intent.id == intent_id)
            .join(models.Session)
            .filter(models.Session.user_id == user.id)
            .first()
        )
        if not intent:
            raise HTTPException(status_code=404, detail="Intent introuvable ou non autorisé.")
        session_id = intent.session_id

    _get_session_checked(db, user, session_id)

    # 1) Construire le plan
    plan_resp = build_plan(db, session_id=session_id)
    steps: List[Dict[str, Any]] = plan_resp.get("plan", [])
    if not steps:
        return {
            "status": "empty",
            "engine": "multi",
            "message": "Aucune étape détectée pour cette session. Ajoutez des intents puis reconstruisez le plan.",
            "plan": [],
        }

    results: List[Dict[str, Any]] = []
    errors: List[str] = []
    executions_created: List[Dict[str, Any]] = []

    # 2) Parcours & génération
    for step in steps:
        engine_type = step.get("type")          # "terraform" | "ansible"
        domain = (step.get("domain") or "").lower()  # "compute", "infra_bundle", "dns_tls", "system_service", ...
        step_no = step.get("step")
        meta = step.get("meta", {}) or {}
        target_path = step.get("path")  # ex: generated/<user>/<date>/sX/terraform/infra.tf

        intent: Optional[models.Intent] = None
        bundle_domains: Optional[List[str]] = None

        if engine_type == "terraform":
            if domain == "compute":
                # Intent create
                intent = _find_intent_for_step_simple(db, session_id, engine_type, domain)
            elif domain == "infra_bundle":
                # Groupe de domaines infra -> un seul intent représentatif
                rep_intent_id = meta.get("representative_intent_id")
                if not rep_intent_id:
                    # fallback: premier intent configure infra/mixed
                    intent = _find_intent_for_step_simple(db, session_id, engine_type, "cloud_network")
                else:
                    intent = _get_intent_by_id_checked(db, user, rep_intent_id)
                bundle_domains = meta.get("domains", [])
            else:
                # Domaine infra simple
                intent = _find_intent_for_step_simple(db, session_id, engine_type, domain)
                bundle_domains = [domain]

        elif engine_type == "ansible":
            intent = _find_intent_for_step_simple(db, session_id, engine_type, domain)

        if not intent:
            msg = f"Aucun intent mappé pour l'étape {step_no} [{engine_type}:{domain}]."
            errors.append(msg)
            results.append({
                "step": step_no,
                "type": engine_type,
                "domain": domain,
                "status": "skipped",
                "reason": msg,
            })
            continue

        try:
            if engine_type == "terraform":
                # _generate_terraform accepte bundle_domains + target_path
                gen = await _generate_terraform(
                    intent_id=intent.id,
                    db=db,
                    user=user,
                    bundle_domains=bundle_domains,     # ex: ["balancer_gateway","dns_tls"] ou ["dns_tls"]
                    target_path=target_path            # ex: generated/<user>/<date>/sX/terraform/infra.tf
                )
            elif engine_type == "ansible":
                gen = await _generate_ansible(intent_id=intent.id, db=db, user=user)
            else:
                raise HTTPException(status_code=400, detail=f"Moteur inconnu: {engine_type}")

            # Enregistre le résultat
            results.append({
                "step": step_no,
                "type": engine_type,
                "domain": domain,
                "status": "success",
                "intent_id": intent.id,
                "result": gen,
            })

            # Auto-create executions: UNE exécution **par artefact généré**
            if auto_create_executions and gen.get("status") == "success":
                if engine_type == "terraform":
                    tf_id = gen.get("terraform_file_id")
                    if tf_id:
                        exec_obj = _create_execution_record(
                            db, user,
                            session_id=session_id,
                            intent_id=intent.id,
                            engine="terraform",
                            target_file_id=tf_id,
                            task_type="terraform",
                            extra_data={
                                "path": gen.get("filename"),
                                "bundle_domains": gen.get("bundle_domains"),
                                "session_id": session_id,
                                "intent_id": intent.id,
                                "domain": domain,
                                "step": step_no,
                            },
                            status="pending"
                        )
                        executions_created.append({
                            "step": step_no,
                            "engine": "terraform",
                            "execution_id": exec_obj.id,
                            "file_id": tf_id,
                            "path": gen.get("filename"),
                        })

                elif engine_type == "ansible":
                    pb_id = gen.get("playbook_id")
                    if pb_id:
                        exec_obj = _create_execution_record(
                            db, user,
                            session_id=session_id,
                            intent_id=intent.id,
                            engine="ansible",
                            target_file_id=pb_id,
                            task_type="ansible",
                            extra_data={
                                "path": gen.get("filename"),
                                "runtime": gen.get("runtime"),
                                "session_id": session_id,
                                "intent_id": intent.id,
                                "domain": domain,
                                "step": step_no,
                            },
                            status="pending"
                        )
                        executions_created.append({
                            "step": step_no,
                            "engine": "ansible",
                            "execution_id": exec_obj.id,
                            "file_id": pb_id,
                            "path": gen.get("filename"),
                        })

        except HTTPException as e:
            db.rollback()
            errors.append(f"Étape {step_no} ({engine_type}:{domain}) échouée: {e.detail}")
            results.append({
                "step": step_no,
                "type": engine_type,
                "domain": domain,
                "status": "error",
                "intent_id": intent.id if intent else None,
                "error": e.detail,
            })
        except Exception as e:
            db.rollback()
            errors.append(f"Étape {step_no} ({engine_type}:{domain}) échouée: {str(e)}")
            results.append({
                "step": step_no,
                "type": engine_type,
                "domain": domain,
                "status": "error",
                "intent_id": intent.id if intent else None,
                "error": str(e),
            })

    # 3) Statut global
    base_payload = {
        "plan": steps,
        "results": results,
        "executions_created": executions_created,  #  liste des exécutions créées (une par artefact)
    }

    if errors:
        error_response = {
            **base_payload,
            "status": "partial",
            "engine": "multi",
            "message": "Génération partielle : certaines étapes ont échoué.",
            "errors": errors,
            "next": [
                "Vérifiez les erreurs listées.",
                "Les exécutions 'pending' ont été créées pour les artefacts valides.",
                "Appliquez-les dans l’ordre des steps (Terraform d’abord, puis Ansible).",
            ],
            }
        #  P0.5 — Mark idempotency completed
        mark_idempotency_completed(
            db=db,
            user_id=user.id,
            idempotency_key=idempotency_key,
            scope="generate",
            response_body=error_response
        )
        return error_response

    success_response = {
        **base_payload,
        "status": "success",
        "engine": "multi",
        "message": "Artefacts générés **et** exécutions créées (une par fichier). Terraform d’abord, puis Ansible.",
        "next": [
            "Lancez /executions/{execution_id}/execute pour chaque exécution, dans l’ordre des 'step'.",
        ],
        }

    #  P0.5 — Mark idempotency completed
    mark_idempotency_completed(
        db=db,
        user_id=user.id,
        idempotency_key=idempotency_key,
        scope="generate",
        response_body=success_response
    )

    return success_response

# ---------- 3) Alias legacy (facultatif) ----------
@router.post(
    "/generate/mixed",
    tags=["Génération"],
    summary="(Legacy) Orchestrer un intent MIXED (alias vers /generate)"
)
async def generate_mixed_legacy(
    intent_id: int = Body(..., description="ID de l'intention MIXED"),
    auto_create_executions: bool = Body(True, description="Créer automatiquement des exécutions pour chaque artefact."),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> Dict[str, Any]:
    # Redirige vers /generate en déduisant la session via intent_id (compat front historique)
    return await generate_all(session_id=None, intent_id=intent_id, auto_create_executions=auto_create_executions, db=db, user=user)
