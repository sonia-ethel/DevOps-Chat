"""
 Dashboard Routes - Endpoints pour le monitoring et la visualisation
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
import logging
import time

from app import database
from app import models
from app.auth import get_current_user
from app.services.monitoring_engine import MonitoringRunner, MONITORING_RECIPES
from app.services.ssm_executor import SSMExecutor
from app.utils.crypto import decrypt
from app.services.aws_credentials_service import get_user_aws_credentials

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/instances")
async def list_instances_with_metrics(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
     Liste toutes les instances de l'utilisateur avec leurs dernières métriques
    
    Retourne:
    - instance_id
    - ip
    - state
    - last_metrics (si disponibles)
    - last_metrics_timestamp
    """
    # Récupérer toutes les instances de l'utilisateur
    user_sessions = (
        db.query(models.Session)
        .filter(models.Session.user_id == current_user.id)
        .all()
    )
    
    session_ids = [s.id for s in user_sessions]
    
    instances = (
        db.query(models.Instance)
        .filter(models.Instance.session_id.in_(session_ids))
        .all()
    )
    
    result = []
    for instance in instances:
        # Récupérer les dernières métriques depuis la DB si stockées
        # TODO: Implémenter le modèle MetricsSnapshot dans models.py
        # Pour l'instant, retourner les infos de base
        result.append({
            "instance_id": instance.instance_id,
            "ip": instance.ip,
            "state": getattr(instance, "state", "unknown"),
            "ssh_user": instance.ssh_user,
            "provider": instance.provider,
            "last_metrics": None,  # À implémenter
            "last_metrics_timestamp": None,
        })
    
    return {
        "success": True,
        "instances": result,
        "total": len(result),
    }


@router.get("/instances/{instance_id}/metrics")
async def get_instance_metrics(
    instance_id: str,
    collect_fresh: bool = True,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
     Récupère les métriques d'une instance spécifique
    
    Args:
        instance_id: ID de l'instance AWS (ex: i-0abc123...)
        collect_fresh: Si True, collecte de nouvelles métriques via SSM (défaut: True)
    
    Retourne:
        - instance_id
        - metrics: {cpu_percent, mem_used_percent, disk_used_percent, load_1, load_5, load_15, uptime}
        - timestamp
        - status: success/failed
    """
    # Vérifier que l'instance appartient à l'utilisateur
    user_sessions = (
        db.query(models.Session)
        .filter(models.Session.user_id == current_user.id)
        .all()
    )
    session_ids = [s.id for s in user_sessions]
    
    instance = (
        db.query(models.Instance)
        .filter(models.Instance.session_id.in_(session_ids))
        .filter(models.Instance.instance_id == instance_id)
        .first()
    )
    
    if not instance:
        raise HTTPException(
            status_code=404,
            detail=f"Instance {instance_id} non trouvée ou n'appartient pas à l'utilisateur"
        )
    
    if not collect_fresh:
        # TODO: Retourner les dernières métriques depuis la DB
        return {
            "success": True,
            "instance_id": instance_id,
            "metrics": None,
            "timestamp": None,
            "status": "no_cached_metrics",
            "message": "Aucune métrique en cache. Utilisez collect_fresh=true."
        }
    
    # Collecter de nouvelles métriques via SSM
    creds = get_user_aws_credentials(current_user.id, db)
    if not creds:
        raise HTTPException(
            status_code=400,
            detail="AWS credentials manquants. Ajoutez-les via /user/aws-credentials"
        )
    
    ssm_executor = SSMExecutor(
        aws_access_key=decrypt(creds.encrypted_access_key),
        aws_secret_key=decrypt(creds.encrypted_secret_key),
        region=getattr(creds, "region", None) or "eu-north-1",
    )
    
    runner = MonitoringRunner(db=db, ssm_executor=ssm_executor)
    
    # Créer un plan pour une seule instance
    plan = runner.create_plan(
        monitoring_type="metrics_snapshot",
        instance_ids=[instance_id],
    )
    
    # Exécuter la collecte
    try:
        snapshot = await runner.collect_metrics(
            monitoring_type=plan.monitoring_type,
            instance_ids=plan.instance_ids,
        )
        
        instance_metrics = next((inst for inst in snapshot.instances if inst.instance_id == instance_id), None)

        if not instance_metrics:
            return {
                "success": False,
                "instance_id": instance_id,
                "metrics": None,
                "timestamp": snapshot.timestamp,
                "status": "failed",
                "message": "Échec de la collecte de métriques"
            }
        
        return {
            "success": True,
            "instance_id": instance_id,
            "metrics": instance_metrics.dict(),
            "timestamp": snapshot.timestamp,
            "status": "success"
        }
    
    except Exception as e:
        logger.error(f" Erreur collecte métriques pour {instance_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la collecte: {str(e)}"
        )


@router.get("/instances/{instance_id}/audit")
async def get_instance_audit(
    instance_id: str,
    run_fresh: bool = False,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
     Récupère le dernier audit d'une instance
    
    Args:
        instance_id: ID de l'instance AWS
        run_fresh: Si True, lance un nouvel audit (défaut: False)
    
    Retourne:
        - instance_id
        - findings: liste des findings par sévérité
        - timestamp
        - status
    """
    # Vérifier que l'instance appartient à l'utilisateur
    user_sessions = (
        db.query(models.Session)
        .filter(models.Session.user_id == current_user.id)
        .all()
    )
    session_ids = [s.id for s in user_sessions]
    
    instance = (
        db.query(models.Instance)
        .filter(models.Instance.session_id.in_(session_ids))
        .filter(models.Instance.instance_id == instance_id)
        .first()
    )
    
    if not instance:
        raise HTTPException(
            status_code=404,
            detail=f"Instance {instance_id} non trouvée"
        )
    
    if not run_fresh:
        # TODO: Retourner le dernier audit depuis la DB
        return {
            "success": True,
            "instance_id": instance_id,
            "findings": [],
            "timestamp": None,
            "status": "no_cached_audit",
            "message": "Aucun audit en cache. Utilisez run_fresh=true."
        }
    
    # Exécuter un nouvel audit
    from app.services.audit_engine import AuditRunner
    
    creds = get_user_aws_credentials(current_user.id, db)
    if not creds:
        raise HTTPException(
            status_code=400,
            detail="AWS credentials manquants"
        )
    
    ssm_executor = SSMExecutor(
        aws_access_key=decrypt(creds.encrypted_access_key),
        aws_secret_key=decrypt(creds.encrypted_secret_key),
        region=getattr(creds, "region", None) or "eu-north-1",
    )
    
    runner = AuditRunner(db=db, ssm_executor=ssm_executor)
    plan = runner.create_plan(
        instance_ids=[instance_id],
        recipe_names=["ops_health", "security_basic"],
    )
    
    # Note: Dashboard audit n'utilise pas SSE, mais on passe un task_id pour cohérence
    dashboard_task_id = f"dashboard-audit-{instance_id}-{int(time.time())}"
    
    try:
        audit_result = await runner.run_audit(
            plan=plan,
            user_id=current_user.id,
            session_id=instance.session_id,
            task_id=dashboard_task_id,
        )
        
        # Trouver les findings de cette instance
        instance_findings = []
        for inst in audit_result.instances:
            if inst.instance_id == instance_id:
                instance_findings = [f.dict() for f in inst.findings]
                break
        
        return {
            "success": True,
            "instance_id": instance_id,
            "findings": instance_findings,
            "timestamp": audit_result.timestamp,
            "status": audit_result.status
        }
    
    except Exception as e:
        logger.error(f" Erreur audit pour {instance_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de l'audit: {str(e)}"
        )


# =============================================================
#  Endpoints pour le Monitoring
# =============================================================

@router.get("/metrics/history")
async def get_metrics_history(
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
     Récupère l'historique des snapshots de métriques de l'utilisateur
    
    Paramètres:
    - limit: nombre de snapshots à retourner (défaut: 10)
    
    Retourne une liste des snapshots les plus récents avec:
    - id, task_id, session_id
    - instances_total, instances_ok, instances_failed
    - avg_cpu_percent, avg_mem_used_percent, avg_disk_used_percent
    - status, created_at
    """
    try:
        snapshots = (
            db.query(models.MetricsSnapshot)
            .filter(models.MetricsSnapshot.user_id == current_user.id)
            .order_by(models.MetricsSnapshot.created_at.desc())
            .limit(limit)
            .all()
        )
        
        if not snapshots:
            return {
                "success": True,
                "count": 0,
                "snapshots": [],
                "message": "Aucun snapshot de métriques trouvé"
            }
        
        snapshot_list = []
        for snapshot in snapshots:
            import json
            full_data = json.loads(snapshot.full_data) if snapshot.full_data else {}
            
            snapshot_list.append({
                "id": snapshot.id,
                "task_id": snapshot.task_id,
                "session_id": snapshot.session_id,
                "instances_total": snapshot.instances_total,
                "instances_ok": snapshot.instances_ok,
                "instances_failed": snapshot.instances_failed,
                "avg_cpu_percent": snapshot.avg_cpu_percent,
                "avg_mem_used_percent": snapshot.avg_mem_used_percent,
                "avg_disk_used_percent": snapshot.avg_disk_used_percent,
                "status": snapshot.status,
                "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
                "instances": full_data.get("instances", []) if full_data else []
            })
        
        return {
            "success": True,
            "count": len(snapshot_list),
            "snapshots": snapshot_list
        }
    
    except Exception as e:
        logger.error(f" Erreur lors de la récupération de l'historique: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la récupération de l'historique: {str(e)}"
        )


@router.get("/metrics/{snapshot_id}")
async def get_metrics_detail(
    snapshot_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
     Récupère les détails complets d'un snapshot de métriques
    
    Paramètres:
    - snapshot_id: ID du snapshot
    
    Retourne les données complètes du snapshot avec toutes les instances
    """
    try:
        snapshot = (
            db.query(models.MetricsSnapshot)
            .filter(
                models.MetricsSnapshot.id == snapshot_id,
                models.MetricsSnapshot.user_id == current_user.id
            )
            .first()
        )
        
        if not snapshot:
            raise HTTPException(
                status_code=404,
                detail="Snapshot de métriques non trouvé"
            )
        
        import json
        full_data = json.loads(snapshot.full_data) if snapshot.full_data else {}
        
        return {
            "success": True,
            "snapshot": {
                "id": snapshot.id,
                "task_id": snapshot.task_id,
                "session_id": snapshot.session_id,
                "user_id": snapshot.user_id,
                "instances_total": snapshot.instances_total,
                "instances_ok": snapshot.instances_ok,
                "instances_failed": snapshot.instances_failed,
                "avg_cpu_percent": snapshot.avg_cpu_percent,
                "avg_mem_used_percent": snapshot.avg_mem_used_percent,
                "avg_disk_used_percent": snapshot.avg_disk_used_percent,
                "status": snapshot.status,
                "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
                "full_data": full_data
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f" Erreur lors de la récupération du détail: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la récupération du détail: {str(e)}"
        )


# =============================================================
#  Endpoints pour les Audits
# =============================================================

@router.get("/audits/history")
async def get_audits_history(
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
     Récupère l'historique des snapshots d'audits de l'utilisateur
    
    Paramètres:
    - limit: nombre de snapshots à retourner (défaut: 10)
    
    Retourne une liste des snapshots les plus récents avec:
    - id, session_id
    - instances_total, instances_ok, instances_failed
    - critical_count, high_count, medium_count, low_count, info_count
    - status, created_at
    """
    try:
        snapshots = (
            db.query(models.AuditSnapshot)
            .filter(models.AuditSnapshot.user_id == current_user.id)
            .order_by(models.AuditSnapshot.created_at.desc())
            .limit(limit)
            .all()
        )
        
        if not snapshots:
            return {
                "success": True,
                "count": 0,
                "snapshots": [],
                "message": "Aucun snapshot d'audit trouvé"
            }
        
        snapshot_list = []
        for snapshot in snapshots:
            import json
            full_data = json.loads(snapshot.full_data) if snapshot.full_data else {}
            
            snapshot_list.append({
                "id": snapshot.id,
                "session_id": snapshot.session_id,
                "user_id": snapshot.user_id,
                "instances_total": snapshot.instances_total,
                "instances_ok": snapshot.instances_ok,
                "instances_failed": snapshot.instances_failed,
                "critical_count": snapshot.critical_count,
                "high_count": snapshot.high_count,
                "medium_count": snapshot.medium_count,
                "low_count": snapshot.low_count,
                "info_count": snapshot.info_count,
                "total_findings": (
                    snapshot.critical_count + 
                    snapshot.high_count + 
                    snapshot.medium_count + 
                    snapshot.low_count + 
                    snapshot.info_count
                ),
                "status": snapshot.status,
                "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
            })
        
        return {
            "success": True,
            "count": len(snapshot_list),
            "snapshots": snapshot_list
        }
    
    except Exception as e:
        logger.error(f" Erreur lors de la récupération de l'historique: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la récupération de l'historique: {str(e)}"
        )


@router.get("/audits/{snapshot_id}")
async def get_audit_snapshot_detail(
    snapshot_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
     Récupère les détails complets d'un snapshot d'audit
    
    Retourne les données complètes du snapshot avec toutes les instances et findings
    """
    try:
        snapshot = (
            db.query(models.AuditSnapshot)
            .filter(
                models.AuditSnapshot.id == snapshot_id,
                models.AuditSnapshot.user_id == current_user.id
            )
            .first()
        )
        
        if not snapshot:
            raise HTTPException(
                status_code=404,
                detail="Snapshot d'audit non trouvé"
            )
        
        import json
        full_data = json.loads(snapshot.full_data) if snapshot.full_data else {}
        
        return {
            "success": True,
            "snapshot": {
                "id": snapshot.id,
                "session_id": snapshot.session_id,
                "user_id": snapshot.user_id,
                "instances_total": snapshot.instances_total,
                "instances_ok": snapshot.instances_ok,
                "instances_failed": snapshot.instances_failed,
                "critical_count": snapshot.critical_count,
                "high_count": snapshot.high_count,
                "medium_count": snapshot.medium_count,
                "low_count": snapshot.low_count,
                "info_count": snapshot.info_count,
                "status": snapshot.status,
                "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
                "full_data": full_data
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f" Erreur lors de la récupération du détail: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la récupération du détail: {str(e)}"
        )
