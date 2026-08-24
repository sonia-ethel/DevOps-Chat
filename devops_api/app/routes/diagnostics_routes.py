"""
Routes de diagnostic pour le module Configure-Only
"""
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from app import database, models
from app.auth import get_current_user
from app.services.ssm_diagnostics import run_ssm_diagnostic
from app.routes.user_credentials_routes import get_aws_credentials_for_user
from app.utils.crypto import decrypt_aws_secret
from app.services.bootstrap_ssm import bootstrap_ssm_attach_profile, wait_for_ssm_online
from typing import Dict, Any, List

router = APIRouter()


def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/configure_only", response_model=Dict[str, Any])
async def get_configure_only_diagnostics(db: Session = Depends(get_db)):
    """
    ##  Diagnostics du module Configure-Only
    
    Retourne les statistiques pour le module de configuration d'infrastructure:
    - Nombre total d'instances
    - Répartition SSH vs SSM
    - Taille des batches
    - Mode par défaut
    
    ###  Réponse:
    ```json
    {
      "total_instances": 8,
      "ssm_managed_count": 6,
      "ssh_count": 2,
      "batch_size_default": 5,
      "execution_mode": "configure_only",
      "connection_methods": {
        "ssm": 6,
        "ssh": 2
      }
    }
    ```
    """
    # Count total instances
    total = db.query(models.Instance).count()
    
    # Count SSM-managed instances
    ssm_count = db.query(models.Instance).filter(
        models.Instance.ssm_managed == True
    ).count()
    
    # Count SSH instances
    ssh_count = db.query(models.Instance).filter(
        models.Instance.connection_method == 'ssh'
    ).count()
    
    # Count instances with VPC configuration
    vpc_count = db.query(models.Instance).filter(
        models.Instance.vpc_id.isnot(None),
        models.Instance.subnet_id.isnot(None)
    ).count()
    
    # Connection methods breakdown
    connection_methods = {}
    for method in ['ssh', 'ssm']:
        count = db.query(models.Instance).filter(
            models.Instance.connection_method == method
        ).count()
        if count > 0:
            connection_methods[method] = count
    
    return {
        "total_instances": total,
        "ssm_managed_count": ssm_count,
        "ssh_count": ssh_count,
        "vpc_configured_count": vpc_count,
        "batch_size_default": 5,
        "execution_mode": "configure_only",
        "connection_methods": connection_methods,
        "features": {
            "batch_executor": True,
            "ssm_support": True,
            "terraform_sg": True,
            "per_instance_reporting": True,
            "idempotent_operations": True
        }
    }


@router.get("/ssm", response_model=Dict[str, Any])
async def get_ssm_diagnostics(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    """
    ##  Diagnostics SSM complet
    
    Retourne un diagnostic détaillé de l'état SSM:
    - Nombre d'instances DB vs AWS
    - Instances SSM Online vs Blocked
    - Raisons de blocage (IAM, agent, réseau, permissions)
    - Vérification des permissions IAM
    
    ###  Réponse:
    ```json
    {
      "total_instances_db": 6,
      "total_instances_aws": 6,
      "total_ssm_managed_db": 6,
      "total_ssm_online_aws": 3,
      "online_instances": [...],
      "blocked_instances": [
        {"instance_id": "i-xxx", "block_reason": "NO_IAM_PROFILE"}
      ],
      "permissions_check": {"status": "ok"},
      "summary": " SSM ready: 3/6 instances online"
    }
    ```
    """
    # Get AWS credentials
    creds = get_aws_credentials_for_user(user.id, db)
    if not creds:
        raise HTTPException(status_code=400, detail="AWS credentials required for SSM diagnostics")
    
    # Decrypt secret
    decrypted_secret = decrypt_aws_secret(creds.secret_access_key_encrypted)
    
    # Run diagnostic
    result = run_ssm_diagnostic(
        db=db,
        region=creds.region or "eu-north-1",
        aws_access_key=creds.access_key_id,
        aws_secret_key=decrypted_secret
    )
    return result

@router.post("/ssm/bootstrap", response_model=Dict[str, Any])
async def bootstrap_ssm_endpoint(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    """
    Lance un bootstrap SSM (attach IAM profile) sur une liste d'instances existantes.

    - Ne remplace pas un profile IAM existant différent (sécurité).
    - Poll PingStatus (6×, 20s) pour vérifier si une instance passe Online.
    - Retourne diagnostic avant/après.
    """
    instance_ids: List[str] = payload.get("instance_ids") or []
    if not instance_ids:
        raise HTTPException(status_code=400, detail="instance_ids requis")

    creds = get_aws_credentials_for_user(user.id, db)
    if not creds:
        raise HTTPException(status_code=400, detail="AWS credentials required for SSM diagnostics")
    decrypted_secret = decrypt_aws_secret(creds.secret_access_key_encrypted)

    diag_before = run_ssm_diagnostic(
        db=db,
        region=creds.region or "eu-north-1",
        aws_access_key=creds.access_key_id,
        aws_secret_key=decrypted_secret,
    )

    bootstrap_result = bootstrap_ssm_attach_profile(
        instance_ids=instance_ids,
        region=creds.region or "eu-north-1",
        aws_access_key=creds.access_key_id,
        aws_secret_key=decrypted_secret,
    )

    poll_states = wait_for_ssm_online(
        instance_ids=instance_ids,
        region=creds.region or "eu-north-1",
        aws_access_key=creds.access_key_id,
        aws_secret_key=decrypted_secret,
        attempts=6,
        delay_seconds=20,
    )

    diag_after = run_ssm_diagnostic(
        db=db,
        region=creds.region or "eu-north-1",
        aws_access_key=creds.access_key_id,
        aws_secret_key=decrypted_secret,
    )

    return {
        "before": diag_before,
        "bootstrap": bootstrap_result,
        "poll_states": poll_states,
        "after": diag_after,
    }
    return result
