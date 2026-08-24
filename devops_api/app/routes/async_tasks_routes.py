# app/routes/async_tasks_routes.py

import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app import models, database
from app.auth import get_current_user
import json
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

router = APIRouter()

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/tasks/{task_id}/status", tags=["Async Tasks"], summary="Get task status for polling")
async def get_task_status(
    task_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    """
    Endpoint de polling pour récupérer le statut d'une tâche asynchrone.
    Utilisé par le frontend pour suivre l'avancement en temps réel.
    """
    task = db.query(models.AsyncTask).filter_by(
        task_id=task_id, 
        user_id=user.id
    ).first()
    
    if not task:
        raise HTTPException(status_code=404, detail=f"Tâche {task_id} introuvable")
    
    # Récupération des logs de progression les plus récents
    recent_logs = (
        db.query(models.AsyncTaskLog)
        .filter_by(task_id=task.id)
        .order_by(models.AsyncTaskLog.timestamp.desc())
        .limit(10)
        .all()
    )
    
    # Parse task_data and result_data JSON
    task_data = {}
    result_data = {}
    try:
        if task.task_data:
            task_data = json.loads(task.task_data)
        if task.result_data:
            result_data = json.loads(task.result_data)
    except json.JSONDecodeError:
        logger.warning(f"Invalid JSON in task {task_id} data fields")
    
    # Extraire les détails de sous-étapes s'ils existent
    substep_details = task_data.get('substep_details', {}) if task_data else {}
    
    return {
        "task_id": task.task_id,
        "status": task.status,  # pending, running, completed, failed, cancelled
        "progress_percentage": task.progress_percentage,
        "current_step": task.current_step,
        "task_type": task.task_type,
        
        # Timestamps
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        
        # Error handling
        "error_message": task.error_message,
        
        # Progress logs pour affichage temps réel
        "recent_logs": [
            {
                "timestamp": log.timestamp.isoformat(),
                "level": log.level,
                "message": log.message,
                "step_name": log.step_name,
                "progress_percentage": log.progress_percentage
            } for log in recent_logs
        ],
        
        # Task and result data
        "task_data": task_data,
        "result_data": result_data,
        
        # Execution info if available
        "execution_id": task.execution_id,
        
        # Nouvelles fonctionnalités pour l'amélioration UX
        "substep_details": substep_details,
        "estimated_completion": substep_details.get('estimated_duration'),
        "resource_info": substep_details.get('resource_info'),
        "metadata": substep_details.get('metadata', {})
    }


@router.get("/tasks", tags=["Async Tasks"], summary="List user's async tasks")
async def list_user_tasks(
    status: str = Query(None, description="Filter by status"),
    limit: int = Query(20, description="Max number of tasks to return"),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    """
    Liste les tâches asynchrones de l'utilisateur.
    Utile pour debugging et monitoring.
    """
    query = db.query(models.AsyncTask).filter_by(user_id=user.id)
    
    if status:
        query = query.filter_by(status=status)
    
    tasks = (
        query.order_by(models.AsyncTask.created_at.desc())
        .limit(limit)
        .all()
    )
    
    return {
        "tasks": [
            {
                "task_id": task.task_id,
                "status": task.status,
                "task_type": task.task_type,
                "progress_percentage": task.progress_percentage,
                "current_step": task.current_step,
                "created_at": task.created_at.isoformat() if task.created_at else None,
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                "error_message": task.error_message
            } for task in tasks
        ]
    }


@router.post("/tasks/{task_id}/cancel", tags=["Async Tasks"], summary="Cancel a running task")
async def cancel_task(
    task_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    """
    Annule une tâche en cours d'exécution.
    Note: L'implémentation réelle de l'annulation dépend du type de tâche.
    """
    task = db.query(models.AsyncTask).filter_by(
        task_id=task_id, 
        user_id=user.id
    ).first()
    
    if not task:
        raise HTTPException(status_code=404, detail=f"Tâche {task_id} introuvable")
    
    if task.status not in ["pending", "running"]:
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot cancel task with status '{task.status}'"
        )
    
    # Mark task as cancelled
    task.status = "cancelled"
    task.completed_at = datetime.now(timezone.utc)
    task.updated_at = datetime.now(timezone.utc)
    task.error_message = "Task cancelled by user"
    
    # Add cancellation log
    cancel_log = models.AsyncTaskLog(
        task_id=task.id,
        level="warning",
        message=" Tâche annulée par l'utilisateur",
        step_name="cancelled"
    )
    db.add(cancel_log)
    db.commit()
    
    logger.info(f"Task {task_id} cancelled by user {user.id}")
    
    return {
        "task_id": task_id,
        "status": "cancelled",
        "message": "Tâche annulée avec succès"
    }


@router.get("/tasks/{task_id}/logs", tags=["Async Tasks"], summary="Get detailed task logs")
async def get_task_logs(
    task_id: str,
    limit: int = Query(100, description="Max number of log entries"),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    """
    Récupère l'historique complet des logs d'une tâche.
    Utile pour debugging des erreurs.
    """
    task = db.query(models.AsyncTask).filter_by(
        task_id=task_id, 
        user_id=user.id
    ).first()
    
    if not task:
        raise HTTPException(status_code=404, detail=f"Tâche {task_id} introuvable")
    
    logs = (
        db.query(models.AsyncTaskLog)
        .filter_by(task_id=task.id)
        .order_by(models.AsyncTaskLog.timestamp.asc())
        .limit(limit)
        .all()
    )
    
    return {
        "task_id": task_id,
        "total_logs": len(logs),
        "logs": [
            {
                "timestamp": log.timestamp.isoformat(),
                "level": log.level,
                "message": log.message,
                "step_name": log.step_name,
                "progress_percentage": log.progress_percentage
            } for log in logs
        ]
    }