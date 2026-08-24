# ============================================================
# Étape 3 & 4 — Pipeline unique orchestré par run_execution_by_id()
# ============================================================

import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models
from app.utils.extra_data_utils import get_extra, set_extra
from app.services.execution_logger import log_execution_event
from app.services.execution_service import run_execution, get_execution_logger
from app.utils.execution_progress import update_execution_progress

logger = logging.getLogger(__name__)

async def run_terraform_execution(
    db: Session,
    execution: models.Execution,
    user_id: int,
) -> dict:
    """
    Handler Terraform : découpe du bloc if execution.task_type == "terraform" de executions_routes.py
    Logique : cherche file, provider, credentials, run_execution, persiste instances, génère inventaire.
    """
    from app.routes.executions_routes import _persist_instances_if_create
    from app.utils.crypto import encrypt, decrypt
    from app.utils.file_utils import get_latest_private_key_path
    from app.services.ansible_inventory import generate_inventory_from_executions
    
    log = get_execution_logger(execution.id, "terraform")
    log.info("[Handler] Terraform execution started")
    
    extra_data = get_extra(execution)
    update_execution_progress(db, execution.id, 10, "Préparation Terraform…", "preparing")
    
    # Lookup terraform file
    terraform_file = (
        db.query(models.GeneratedTerraformFile)
        .filter_by(id=execution.target_file, user_id=user_id)
        .first()
    )
    if not terraform_file:
        raise Exception("Fichier Terraform non trouvé.")
    
    # Lookup provider
    provider = (
        db.query(models.Provider)
        .filter_by(session_id=execution.session_id, user_id=user_id)
        .order_by(models.Provider.created_at.desc())
        .first()
    )
    if not provider:
        raise Exception("Aucun provider associé.")
    
    credentials = json.loads(decrypt(provider.encrypted_credentials))
    
    # Determine intent type
    intent_type: Optional[str] = None
    if getattr(execution, "intent_id", None):
        intent_row = db.query(models.Intent).filter_by(id=execution.intent_id).first()
        if intent_row:
            intent_type = (intent_row.intent_type or "").lower()
    
    update_execution_progress(db, execution.id, 30, "Exécution Terraform…", "running")
    
    # Run terraform
    result = await run_execution(
        engine="terraform",
        file_id=execution.target_file,
        credentials=credentials,
        db=db,
        execution_id=execution.id,
        user_id=user_id
    )
    
    update_execution_progress(db, execution.id, 70, "Traitement des instances…", "processing")
    
    # Persist instances if create
    _persist_instances_if_create(
        db=db,
        intent_type=intent_type,
        session_id=execution.session_id,
        provider_name=provider.provider_name,
        instances_result=result.get("instances"),
    )
    
    update_execution_progress(db, execution.id, 80, "Génération d'inventaire…", "finalizing")
    
    # Generate auto inventory (MIXED)
    try:
        db_instances = db.query(models.Instance).filter_by(session_id=execution.session_id).all()
        if db_instances:
            from app.services.ansible_inventory import generate_inventory_from_executions
            items = []
            for inst in db_instances:
                is_win = (inst.os_family or "").lower() == "windows" or (inst.distro or "").lower() == "windows"
                items.append({
                    "name":        inst.name or inst.hostname or inst.instance_id,
                    "ip":          decrypt(inst.public_ip) if inst.public_ip else None,
                    "os_family":   "windows" if is_win else "linux",
                    "distro":      (inst.distro or "unknown").lower(),
                    "ssh_user":    "Administrator" if is_win else (inst.ssh_user or "ubuntu"),
                    "private_key": None if is_win else (decrypt(inst.ssh_private_key) if inst.ssh_private_key else None),
                    "ssh_port":    None,
                    "runtime":     "winrm" if is_win else "ssh",
                })
            inv_path, inv_id = generate_inventory_from_executions(
                instances=items,
                user_id=user_id,
                db=db,
                session_id=execution.session_id,
                intent_id=getattr(execution, "intent_id", None)
            )
            extra_data["generated_inventory_id"] = inv_id
            extra_data["generated_inventory_path"] = inv_path
            set_extra(execution, extra_data)
            db.commit()
    except Exception as e:
        logger.warning(f"Impossible de générer l'inventaire auto (MIXED): {e}")
    
    log.info("[Handler] Terraform execution completed")
    return {"status": "ok", **(result or {})}


async def run_ansible_execution(
    db: Session,
    execution: models.Execution,
    user_id: int,
) -> dict:
    """
    Handler Ansible : découpe du bloc elif execution.task_type == "ansible" de executions_routes.py
    Logique : lookup playbook, check inventory, ensure prereqs, run_execution.
    """
    from app.routes.executions_routes import _ensure_ansible_prereqs, _instances_to_candidates
    
    log = get_execution_logger(execution.id, "ansible")
    log.info("[Handler] Ansible execution started")
    
    extra_data = get_extra(execution)
    update_execution_progress(db, execution.id, 10, "Préparation Ansible…", "preparing")
    
    inventory_path = extra_data.get("inventory_path") or extra_data.get("generated_inventory_path")
    
    # Lookup playbook
    playbook = (
        db.query(models.GeneratedPlaybook)
        .filter_by(id=execution.target_file, user_id=user_id)
        .first()
    )
    if not playbook:
        raise Exception("Playbook non trouvé.")
    
    # Pre-flight: Ansible collections & deps
    try:
        update_execution_progress(db, execution.id, 30, "Vérification des dépendances…", "preparing")
        _ensure_ansible_prereqs(inventory_path)
    except Exception as e:
        logger.warning(f"Pré-flight Ansible échoué: {e}")
    
    if not inventory_path:
        candidates = _instances_to_candidates(db, execution.session_id)
        # Return special response for inventory selection
        raise Exception(f"inventory_required: {json.dumps(candidates)}")
    
    update_execution_progress(db, execution.id, 50, "Exécution Ansible…", "running")
    result = await run_execution(
        engine="ansible",
        file_id=playbook.id,
        instances=None,
        extra_args={
            "inventory_path": inventory_path,
            "playbook_path": playbook.file_path,
        },
        db=db,
        execution_id=execution.id,
        user_id=user_id,
    )
    
    log.info("[Handler] Ansible execution completed")
    return {"status": "ok", **(result or {})}


async def run_kubernetes_execution(
    db: Session,
    execution: models.Execution,
    user_id: int,
) -> dict:
    """
    Handler Kubernetes : découpe du bloc elif execution.task_type == "kubernetes" de executions_routes.py
    Logique : lookup manifest, lookup provider, decrypt creds, run_execution.
    """
    from app.utils.crypto import decrypt
    from app.utils.file_utils import get_k8s_manifest_content
    
    log = get_execution_logger(execution.id, "kubernetes")
    log.info("[Handler] Kubernetes execution started")
    
    update_execution_progress(db, execution.id, 10, "Préparation Kubernetes…", "preparing")
    
    # Lookup manifest
    k8s_manifest = (
        db.query(models.GeneratedKubernetesManifest)
        .filter_by(id=execution.target_file, user_id=user_id)
        .first()
    )
    if not k8s_manifest:
        raise Exception("Manifest Kubernetes non trouvé.")
    
    # Lookup provider
    provider = (
        db.query(models.Provider)
        .filter_by(session_id=execution.session_id, user_id=user_id)
        .order_by(models.Provider.created_at.desc())
        .first()
    )
    if not provider:
        raise Exception("Aucun provider associé.")
    
    credentials = json.loads(decrypt(provider.encrypted_credentials))
    manifest_content = get_k8s_manifest_content(k8s_manifest.file_path)
    
    update_execution_progress(db, execution.id, 50, "Déploiement Kubernetes…", "running")
    
    # Run kubernetes
    result = await run_execution(
        engine="kubernetes",
        file_id=None,
        credentials=credentials,
        extra_args={"manifest": manifest_content},
        db=db,
        execution_id=execution.id,
        user_id=user_id
    )
    
    log.info("[Handler] Kubernetes execution completed")
    return {"status": "ok", **(result or {})}


async def run_audit_execution(
    db: Session,
    execution: models.Execution,
    user_id: int,
) -> dict:
    """
    Handler Audit : appel direct à run_execution(engine="audit")
    Option A : pas de background, juste run_execution direct (+ logging via log_execution_event)
    """
    log = get_execution_logger(execution.id, "audit")
    log.info("[Handler] Audit execution started")
    
    result = await run_execution(
        engine="audit",
        db=db,
        execution_id=execution.id,
        user_id=user_id,
    )
    
    log.info("[Handler] Audit execution completed")
    return result


async def run_monitoring_execution(
    db: Session,
    execution: models.Execution,
    user_id: int,
) -> dict:
    """Handler Monitoring : collecte de métriques via MonitoringRunner"""
    from app.services.monitoring_engine import MonitoringRunner, MonitoringPlan, save_metrics_snapshot
    from app.services.ssm_executor import SSMExecutor
    from app.utils.crypto import decrypt
    from app.paths import MONITORING_DIR
    
    log = get_execution_logger(execution.id, "monitoring")
    log.info("[Handler] Monitoring execution started")
    
    extra_data = get_extra(execution)
    update_execution_progress(db, execution.id, 10, "Préparation monitoring…", "preparing")
    
    # Extract monitoring parameters
    plan_data = extra_data.get("plan", {})
    monitoring_type = plan_data.get("monitoring_type", "metrics_snapshot")
    instance_ids = plan_data.get("instance_ids", [])
    session_id = extra_data.get("session_id") or execution.session_id
    
    if not instance_ids:
        raise Exception("Aucune instance pour monitoring")
    
    # Get AWS credentials
    creds = db.query(models.UserAWSCredentials).filter_by(user_id=user_id).first()
    if not creds:
        raise Exception("AWS credentials manquants")
    
    if isinstance(creds, dict):
        aws_access = creds.get("AWS_ACCESS_KEY_ID")
        aws_secret = creds.get("AWS_SECRET_ACCESS_KEY")
        region = creds.get("region", "eu-north-1")
    else:
        aws_access = creds.access_key_id
        aws_secret = decrypt(creds.secret_access_key_encrypted)
        region = getattr(creds, "region", None) or "eu-north-1"
    
    update_execution_progress(db, execution.id, 30, "Collecte des métriques…", "running")
    
    ssm_executor = SSMExecutor(
        aws_access_key=aws_access,
        aws_secret_key=aws_secret,
        region=region,
    )
    
    runner = MonitoringRunner(db=db, ssm_executor=ssm_executor)
    plan = MonitoringPlan(**plan_data)
    
    metrics_snapshot = await runner.collect_metrics(
        monitoring_type=monitoring_type,
        instance_ids=instance_ids,
        task_id=None,
    )
    
    update_execution_progress(db, execution.id, 80, "Sauvegarde des résultats…", "finalizing")
    
    snapshot_path = save_metrics_snapshot(
        metrics_snapshot,
        output_dir=MONITORING_DIR,
        db=db,
        session_id=session_id,
        user_id=user_id
    )
    
    extra_data["metrics_snapshot"] = metrics_snapshot.dict()
    extra_data["snapshot_path"] = snapshot_path
    set_extra(execution, extra_data)
    db.commit()
    
    log.info("[Handler] Monitoring execution completed")
    return {
        "status": "ok",
        "snapshot_path": snapshot_path,
        "metrics_snapshot": metrics_snapshot.dict(),
    }


async def run_configure_execution(
    db: Session,
    execution: models.Execution,
    user_id: int,
) -> dict:
    """Handler Configure : configuration de services via ansible/scripts avec workflow SSM"""
    log = get_execution_logger(execution.id, "configure")
    log.info("[Handler] Configure execution started")
    
    extra_data = get_extra(execution)
    update_execution_progress(db, execution.id, 10, "Préparation configuration…", "preparing")
    
    # Extract instances from extra_data (stored as [{"id": X, "instance_id": Y}, ...])
    instances_data = extra_data.get("instances", [])
    original_text = extra_data.get("original_text", "")
    
    if not instances_data:
        raise Exception("Aucune instance pour configuration")
    
    # Load actual Instance objects from DB
    instance_ids_list = [inst_data["id"] for inst_data in instances_data]
    instances = db.query(models.Instance).filter(models.Instance.id.in_(instance_ids_list)).all()
    
    if not instances:
        raise Exception("Instances non trouvées en DB")
    
    log.info(f"Configure instances: {[i.instance_id for i in instances]}")
    
    update_execution_progress(db, execution.id, 50, "Exécution du workflow SSM + configuration…", "running")
    
    # Import and call _start_configure_task from chat_creation_routes
    # This function does: SSM diagnostic -> bootstrap if needed -> configure
    from app.routes.chat_creation_routes import _start_configure_task_wrapper
    
    result = await _start_configure_task_wrapper(
        db=db,
        user_id=user_id,
        instances=instances,
        original_text=original_text,
        session_id=execution.session_id,
    )
    
    update_execution_progress(db, execution.id, 90, "Finalisation configuration…", "finalizing")
    log.info(f"Configure result: success={result.get('success')}")
    
    return result
    
    update_execution_progress(db, execution.id, 90, "Finalisation…", "finalizing")
    
    log.info("[Handler] Configure execution completed")
    return {"status": "ok", **(result or {})}


async def run_installer_execution(
    db: Session,
    execution: models.Execution,
    user_id: int,
) -> dict:
    """
    Handler Installer : exécute le nouveau pipeline installer_engine.
    
    extra_data contient:
    {
        "intent_type": "install|configure|upgrade",
        "apps": ["nginx"],
        "requested_port": 8080,
        "instance_ids": ["i-..."],
        "execution_mode": "mvp_local|ssm",
    }
    
    Utilise ExecutionRunner + ExecutionPlanner du nouveau moteur.
    """
    from app.services.execution_runner import ExecutionRunner
    from app.services.execution_planner import ExecutionPlanner
    
    log = get_execution_logger(execution.id, "installer")
    log.info("[Handler] Installer execution started")
    
    extra_data = get_extra(execution)
    update_execution_progress(db, execution.id, 10, "Préparation installation…", "preparing")
    
    # Extract installer parameters
    intent_type = extra_data.get("intent_type", "install")
    apps = extra_data.get("apps") or []
    requested_port = extra_data.get("requested_port")
    instance_ids = extra_data.get("instance_ids") or []
    execution_mode = extra_data.get("execution_mode", "mvp_local")
    
    if not apps:
        raise Exception("Aucune application à installer (apps vide).")
    if not instance_ids:
        raise Exception("Aucune instance cible (instance_ids vide).")
    
    # Log phase installer
    log_execution_event(
        db=db,
        execution_id=execution.id,
        user_id=user_id,
        event="phase",
        message=f"Installation {intent_type} des apps: {', '.join(apps)}"
    )
    
    # MVP: Pour l'instant, on utilise le moteur local
    # Production: Appeler SSMExecutor.execute_command() via ExecutionRunner
    try:
        update_execution_progress(db, execution.id, 30, "Création du plan d'installation…", "preparing")
        
        planner = ExecutionPlanner()
        runner = ExecutionRunner(db=db, execution_id=execution.id, user_id=user_id)
        
        # Créer le plan
        plan = planner.create_plan(
            intent_type=intent_type,
            apps=apps,
            port=requested_port,
            instance_ids=instance_ids,
        )
        log.info(f"[Handler] Installer plan created: {len(plan.steps)} steps")
        
        update_execution_progress(db, execution.id, 50, f"Installation des {len(plan.steps)} étapes…", "running")
        
        # Exécuter le plan
        result = await runner.execute_installation(plan=plan, execution_mode=execution_mode)
        
        update_execution_progress(db, execution.id, 90, "Finalisation…", "finalizing")
        
        # Convertir ExecutionResult en dict
        result_dict = {
            "status": result.status if hasattr(result, 'status') else "completed",
            "summary": result.summary if hasattr(result, 'summary') else "Installation complétée",
            "instances_updated": result.instances_updated if hasattr(result, 'instances_updated') else [],
            "errors": result.errors if hasattr(result, 'errors') else [],
        }
        
        log.info(f"[Handler] Installer execution completed: {result_dict['status']}")
        return result_dict
        
    except Exception as e:
        log.error(f"[Handler] Installer execution failed: {e}", exc_info=True)
        raise


# ============================================================
# Point d'entrée unique : run_execution_by_id()
# ============================================================

EXECUTION_HANDLERS = {
    "terraform": run_terraform_execution,
    "ansible": run_ansible_execution,
    "kubernetes": run_kubernetes_execution,
    "audit": run_audit_execution,
    "monitoring": run_monitoring_execution,
    "configure": run_configure_execution,
    "installer": run_installer_execution,
}


async def run_execution_by_id(
    db: Session,
    execution_id: int,
    user_id: int,
) -> dict:
    """
    Point d'entrée UNIQUE pour exécuter une tâche.
    
    Charge l'execution, valide le propriétaire, délègue au handler spécialisé.
    Gère status=running, completed, failed.
    Logs d'événements via log_execution_event.
    
    Args:
        db: Session DB
        execution_id: ID de l'exécution à lancer
        user_id: ID de l'utilisateur propriétaire
    
    Returns:
        dict résumé du résultat
    
    Raises:
        HTTPException si execution non trouvée ou erreur lors de l'exécution
    """
    log = get_execution_logger(execution_id, "run_execution_by_id")
    log.info("[run_execution_by_id] Starting for execution_id=%s, user_id=%s", execution_id, user_id)
    
    # Load execution & validate ownership
    execution = db.query(models.Execution).filter_by(id=execution_id, user_id=user_id).first()
    if not execution:
        raise HTTPException(status_code=404, detail="Execution introuvable ou propriétaire incorrect.")
    
    # Mark as running
    extra_data = get_extra(execution)
    
    try:
        # Log: started
        log_execution_event(
            db=db,
            execution_id=execution_id,
            user_id=user_id,
            event="started",
            message=f"Exécution {execution.task_type} démarrée via run_execution_by_id"
        )
        
        execution.status = "running"
        execution.updated_at = datetime.utcnow()
        extra_data["progress"] = 0
        extra_data["progress_phase"] = "running"
        set_extra(execution, extra_data)
        db.commit()
        
        # Get handler
        handler = EXECUTION_HANDLERS.get(execution.task_type)
        if not handler:
            raise Exception(f"Type d'exécution non supporté: {execution.task_type}")
        
        # Run handler
        log.info("[run_execution_by_id] Calling handler for %s", execution.task_type)
        result = await handler(db=db, execution=execution, user_id=user_id)
        
        # WARN CRITICAL: Vérifier que le handler n'a pas retourné une erreur/failure
        # Certains handlers retournent {"status": "failed", "error": ...} sans lever d'exception
        handler_status = None
        if isinstance(result, dict):
            handler_status = result.get("status")
            handler_error = result.get("error")
        
        if handler_status in ("failed", "blocked"):
            # Le handler a échoué silencieusement - c'est une erreur
            error_msg = handler_error or f"Handler returned status={handler_status}"
            raise Exception(f"[Handler Failed] {error_msg}")
        
        # Mark as completed (seulement si le handler n'a pas échoué)
        execution.status = "completed"
        execution.updated_at = datetime.utcnow()
        extra_data = get_extra(execution)
        extra_data["progress"] = 100
        extra_data["progress_phase"] = "done"
        set_extra(execution, extra_data)
        db.commit()
        
        # Log: completed
        log_execution_event(
            db=db,
            execution_id=execution_id,
            user_id=user_id,
            event="completed",
            message=f"Exécution {execution.task_type} complétée avec succès"
        )
        
        log.info("[run_execution_by_id] Execution completed successfully")
        return result
        
    except Exception as e:
        # Mark as failed
        log.error("[run_execution_by_id] Error: %s", str(e), exc_info=True)
        
        execution.status = "failed"
        execution.updated_at = datetime.utcnow()
        extra_data = get_extra(execution)
        extra_data["progress_phase"] = "failed"
        extra_data["error"] = str(e)
        set_extra(execution, extra_data)
        db.commit()
        
        # Log: failed
        try:
            log_execution_event(
                db=db,
                execution_id=execution_id,
                user_id=user_id,
                event="failed",
                message=str(e)
            )
        except Exception as log_err:
            log.warning("[run_execution_by_id] Error logging failure: %s", log_err)
        
        raise HTTPException(status_code=500, detail=f"Erreur exécution : {str(e)}")
