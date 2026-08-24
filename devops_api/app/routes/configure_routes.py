# app/routes/configure_routes.py

from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from app import models, database
from app.auth import get_current_user
import json
import os
from typing import Optional

router = APIRouter(tags=["Configuration manuelle"])

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/configure")
def configure_manual_execution(
    session_id: int = Body(...),
    task_type: str = Body(..., description="ansible | audit | kubernetes"),
    file_id: str = Body(..., description="UUID du fichier généré stocké en base"),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    """
     Enregistre une exécution manuelle à partir d’un fichier généré (Ansible, Audit, Kubernetes)
    """

    # Vérifier session
    session = (
        db.query(models.Session)
        .filter(models.Session.id == session_id, models.Session.user_id == user.id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session introuvable.")

    # Déterminer la classe cible selon le type
    file_model = {
        "ansible": models.GeneratedPlaybook,
        "audit": models.GeneratedAudit,
        "kubernetes": models.GeneratedKubernetesFile
    }.get(task_type)

    if not file_model:
        raise HTTPException(status_code=400, detail="task_type invalide.")

    # Récupérer le fichier
    file_obj = db.query(file_model).filter(
        file_model.id == file_id,
        file_model.user_id == user.id
    ).first()

    if not file_obj:
        raise HTTPException(status_code=404, detail="Fichier non trouvé ou non autorisé.")

    # Création exécution
    execution = models.Execution(
        user_id=user.id,
        session_id=session.id,
        task_type=task_type,
        status="pending",
        target_file=file_obj.file_path,
        extra_data=json.dumps({
            "mode": "manual",
            "file_id": file_id
        })
    )
    db.add(execution)
    db.commit()

    return {
        "status": "success",
        "engine": task_type,
        "execution_id": execution.id,
        "message": f"{task_type.capitalize()} personnalisé prêt à être exécuté."
    }