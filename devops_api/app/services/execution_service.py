# © 2024–2026 TOURE Arnaud Patrick
# Licensed under the MIT License

# app/services/execution_service.py
import os
import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.paths import LOGS_DIR, AUDITS_DIR
from app import models
from app.services import (
    terraform_service,
    ansible_service,
    kubernetes_service,
)
from app.services.audit_engine import AuditRunner, save_audit_report
from app.services.aws_credentials_service import get_user_aws_credentials
from app.services.ssm_executor import SSMExecutor
from app.utils.crypto import decrypt  # encrypt non nécessaire ici désormais
from app.utils.execution_progress import update_execution_progress
from app.utils.extra_data_utils import get_extra, set_extra
from app.services.execution_logger import log_execution_event

logger = logging.getLogger(__name__)


def get_execution_logger(execution_id: Optional[int], engine: str) -> logging.Logger:
    """
    Crée (si besoin) un logger orienté fichier pour une exécution donnée.
    Évite les handlers en double et désactive la propagation.
    """
    os.makedirs(LOGS_DIR, exist_ok=True)
    eid = execution_id if execution_id is not None else "unknown"
    log_file_name = f"execution_{eid}_{engine}.log"
    log_path = os.path.join(LOGS_DIR, log_file_name)

    name = f"execution_{eid}_{engine}"
    ex_logger = logging.getLogger(name)
    ex_logger.setLevel(logging.INFO)
    ex_logger.propagate = False

    if not any(isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", None) == log_path
               for h in ex_logger.handlers):
        file_handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        file_handler.setFormatter(formatter)
        ex_logger.addHandler(file_handler)

    return ex_logger


async def run_execution(
    engine: str,
    file_id: Optional[int] = None,
    credentials: Optional[dict] = None,
    instances: Optional[List[Any]] = None,  # réservé si un jour on cible des hôtes en direct
    extra_args: Optional[Dict[str, Any]] = None,
    db: Optional[Session] = None,
    execution_id: Optional[int] = None,
    user_id: Optional[int] = None,
    progress_callback=None,
) -> dict:
    """
    Point d'entrée unique pour exécuter Terraform, Ansible, Kubernetes ou Audit.

    Convention de retour (best-effort, selon moteur) :
      {
        "instances": [ ... ],     # Terraform peut renvoyer les VMs créées (IP, key, user…)
        "logs": "string|dict",    # sortie textuelle utile
        "summary": "string"       # résumé humain
      }

    Préconditions côté routes :
      - Inventaire Ansible/Audit préparé avant (ou ad-hoc) et passé via extra_args["inventory_path"]
      - Kubernetes reçoit le CONTENU du manifest via extra_args["manifest"]
      - Credentials Terraform peuvent être résolus côté service si non fournis ici
    """
    log = get_execution_logger(execution_id, engine)
    log.info("[Execution] Start")
    log.info("[Execution] user_id=%s | execution_id=%s | engine=%s", user_id, execution_id, engine)

    # Log événement de démarrage
    if db and user_id and execution_id:
        try:
            log_execution_event(
                db=db,
                execution_id=execution_id,
                user_id=user_id,
                event="started",
                message=f"Exécution {engine} démarrée"
            )
        except Exception as e:
            log.warning(f"[Execution] Erreur log_execution_event: {e}")

    try:
        # TERRAFORM
        if engine == "terraform":
            log.info("[Execution] Terraform engine selected.")
            if not file_id:
                raise Exception("file_id manquant pour Terraform.")
            if not db or user_id is None:
                raise Exception("Contexte DB/user manquant pour Terraform.")

            # Log phase terraform
            if db and user_id and execution_id:
                try:
                    log_execution_event(
                        db=db,
                        execution_id=execution_id,
                        user_id=user_id,
                        event="phase",
                        message="Préparation Terraform"
                    )
                except Exception as e:
                    log.warning(f"[Execution] Erreur log phase: {e}")

            # Optionnel: credentials non nécessaires si terraform_service sait les récupérer
            if not credentials:
                log.info("[Execution] Credentials not provided (Terraform service should resolve if needed).")

            result = await terraform_service.run_terraform(
                file_id=file_id,
                db=db,
                execution_id=execution_id,
                user_id=user_id,
                progress_callback=progress_callback,
            )

            # Normalisation très légère du retour
            out = result or {}
            if "summary" not in out:
                out["summary"] = "Terraform terminé."
            log.info("[Execution] Terraform execution completed.")
            
            # Log événement de fin
            if db and user_id and execution_id:
                try:
                    log_execution_event(
                        db=db,
                        execution_id=execution_id,
                        user_id=user_id,
                        event="completed",
                        message=out.get("summary", "Terraform terminé")
                    )
                except Exception as e:
                    log.warning(f"[Execution] Erreur log completed: {e}")
            
            return out

        # ANSIBLE
        elif engine == "ansible":
            log.info("[Execution] Ansible engine selected.")
            if not db or user_id is None:
                raise Exception("Contexte DB/user manquant pour Ansible.")

            # Log phase ansible
            if db and user_id and execution_id:
                try:
                    log_execution_event(
                        db=db,
                        execution_id=execution_id,
                        user_id=user_id,
                        event="phase",
                        message="Préparation Ansible"
                    )
                except Exception as e:
                    log.warning(f"[Execution] Erreur log phase: {e}")

            inv_path = (extra_args or {}).get("inventory_path")
            if not inv_path or not os.path.exists(inv_path):
                raise Exception("Chemin d'inventaire invalide pour Ansible (absent ou fichier inexistant).")

            if not file_id:
                raise Exception("file_id manquant pour Ansible.")
            playbook_model = (
                db.query(models.GeneratedPlaybook)
                .filter_by(id=file_id, user_id=user_id)
                .first()
            )
            if not playbook_model or not playbook_model.file_path:
                raise Exception("Playbook Ansible introuvable en base.")

            result = await ansible_service.run_ansible(
                playbook_path=playbook_model.file_path,
                inventory_path=inv_path,
                db=db,
                execution_id=execution_id,
                user_id=user_id,
            )

            out = result or {}
            if "summary" not in out:
                out["summary"] = "Ansible terminé."
            log.info("[Execution] Ansible execution completed.")
            
            # Log événement de fin
            if db and user_id and execution_id:
                try:
                    log_execution_event(
                        db=db,
                        execution_id=execution_id,
                        user_id=user_id,
                        event="completed",
                        message=out.get("summary", "Ansible terminé")
                    )
                except Exception as e:
                    log.warning(f"[Execution] Erreur log completed: {e}")
            
            return out

        # ============================================================
        #  KUBERNETES
        # ============================================================
        elif engine == "kubernetes":
            log.info(" Moteur Kubernetes sélectionné.")
            if not db or user_id is None:
                raise Exception("Contexte DB/user manquant pour Kubernetes.")

            # Log phase kubernetes
            if db and user_id and execution_id:
                try:
                    log_execution_event(
                        db=db,
                        execution_id=execution_id,
                        user_id=user_id,
                        event="phase",
                        message="Déploiement Kubernetes"
                    )
                except Exception as e:
                    log.warning(f"[Execution] Erreur log phase: {e}")

            if not extra_args or "manifest" not in extra_args:
                raise Exception("Contenu du manifest manquant (extra_args['manifest']).")

            manifest_content = extra_args["manifest"]

            result = await kubernetes_service.deploy_kubernetes(
                manifest=manifest_content,
                db=db,
                execution_id=execution_id,
                user_id=user_id,
            )

            out = result or {}
            if "summary" not in out:
                out["summary"] = "Déploiement Kubernetes terminé."
            log.info("[Execution] Kubernetes deployment completed.")
            
            # Log événement de fin
            if db and user_id and execution_id:
                try:
                    log_execution_event(
                        db=db,
                        execution_id=execution_id,
                        user_id=user_id,
                        event="completed",
                        message=out.get("summary", "Kubernetes terminé")
                    )
                except Exception as e:
                    log.warning(f"[Execution] Erreur log completed: {e}")
            
            return out

        # ============================================================
        #  AUDIT (SSM-first)
        # ============================================================
        elif engine == "audit":
            log.info(" Moteur Audit sélectionné (SSM-first).")
            if not db or user_id is None:
                raise Exception("Contexte DB/user manquant pour Audit.")
            if not execution_id:
                raise Exception("execution_id manquant pour Audit.")

            execution_obj = db.query(models.Execution).filter_by(id=execution_id).first()
            if not execution_obj:
                raise Exception("Execution introuvable pour Audit.")

            # Log phase audit
            if db and user_id and execution_id:
                try:
                    log_execution_event(
                        db=db,
                        execution_id=execution_id,
                        user_id=user_id,
                        event="phase",
                        message="Préparation Audit SSM"
                    )
                except Exception as e:
                    log.warning(f"[Execution] Erreur log phase: {e}")

            extra_data = get_extra(execution_obj)

            instance_ids = extra_data.get("instance_ids") or []
            recipe_names = extra_data.get("recipe_names") or ["ops_health"]
            region = extra_data.get("region") or "eu-north-1"
            session_id = extra_data.get("session_id") or execution_obj.session_id

            if not instance_ids:
                execution_obj.status = "failed"
                extra_data["error"] = "No instance_ids provided"
                set_extra(execution_obj, extra_data)
                execution_obj.updated_at = datetime.utcnow()
                db.commit()
                update_execution_progress(db, execution_id, 100, "Échec: aucune instance", "finalizing")
                return {"summary": "Audit échoué: aucune instance."}

            creds = get_user_aws_credentials(user_id, db)
            if not creds:
                execution_obj.status = "failed"
                extra_data["error"] = "AWS credentials manquants"
                set_extra(execution_obj, extra_data)
                execution_obj.updated_at = datetime.utcnow()
                db.commit()
                update_execution_progress(db, execution_id, 100, "Échec: AWS credentials manquants", "finalizing")
                return {"summary": "Audit échoué: AWS credentials manquants."}

            if isinstance(creds, dict):
                aws_access = creds.get("AWS_ACCESS_KEY_ID")
                aws_secret = creds.get("AWS_SECRET_ACCESS_KEY")
                region = creds.get("region", region)
            else:
                aws_access = decrypt(creds.encrypted_access_key)
                aws_secret = decrypt(creds.encrypted_secret_key)
                region = getattr(creds, "region", None) or region

            update_execution_progress(db, execution_id, 5, "Préparation audit…", "preparing")

            ssm_executor = SSMExecutor(
                aws_access_key=aws_access,
                aws_secret_key=aws_secret,
                region=region,
            )

            runner = AuditRunner(db=db, ssm_executor=ssm_executor)
            plan = runner.create_plan(instance_ids=instance_ids, recipe_names=recipe_names)

            update_execution_progress(db, execution_id, 20, "Connexion…", "running")

            audit_result = await runner.run_audit(
                plan=plan,
                user_id=user_id,
                session_id=session_id,
                task_id=None,
                execution_id_db=execution_id,
            )

            report_path = save_audit_report(
                audit_result,
                output_dir=AUDITS_DIR,
                db=db,
                session_id=session_id,
                user_id=user_id,
            )

            execution_obj.status = "completed" if audit_result.status in ("success", "partial") else "failed"
            extra_data["audit_status"] = audit_result.status
            extra_data["result_summary"] = audit_result.summary.dict()
            extra_data["report_path"] = report_path
            set_extra(execution_obj, extra_data)
            execution_obj.updated_at = datetime.utcnow()
            db.commit()

            final_message = "Terminé" if execution_obj.status == "completed" else "Échec"
            update_execution_progress(db, execution_id, 100, final_message, "finalizing")

            out = {
                "summary": "Audit terminé.",
                "audit_result": audit_result.dict(),
                "report_path": report_path,
            }
            log.info("[Execution] Audit execution completed.")
            
            # Log événement de fin
            if db and user_id and execution_id:
                try:
                    event_type = "completed" if execution_obj.status == "completed" else "failed"
                    log_execution_event(
                        db=db,
                        execution_id=execution_id,
                        user_id=user_id,
                        event=event_type,
                        message=f"Audit {execution_obj.status}: {audit_result.status}"
                    )
                except Exception as e:
                    log.warning(f"[Execution] Erreur log completed: {e}")
            return out

        # ============================================================
        #  Inconnu
        # ============================================================
        else:
            raise Exception(f"Moteur '{engine}' non supporté.")

    except Exception as e:
        log.error("[Execution] Error during execution: %s", str(e), exc_info=True)
        
        # Log événement d'erreur
        if db and user_id and execution_id:
            try:
                log_execution_event(
                    db=db,
                    execution_id=execution_id,
                    user_id=user_id,
                    event="failed",
                    message=str(e)
                )
            except Exception as log_err:
                log.warning(f"[Execution] Erreur log failed: {log_err}")
        
        # On expose un message contextualisé, le stack est déjà en fichier
        raise HTTPException(status_code=500, detail=f"Erreur exécution : {str(e)}")
