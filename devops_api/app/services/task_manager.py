# © 2024–2026 TOURE Arnaud Patrick
# Licensed under the MIT License

# app/services/task_manager.py

import logging
import uuid
import json
import asyncio
import re
import time
from datetime import datetime, timezone
from typing import Dict, Any, Callable, Optional, List
from sqlalchemy.orm import Session
from app import models

logger = logging.getLogger(__name__)


class TaskManager:
    """
    Gestionnaire de tâches asynchrones pour les opérations longues (Terraform, Ansible, etc.)
    """
    
    def __init__(self):
        self._running_tasks: Dict[str, asyncio.Task] = {}
    
    async def create_task(
        self,
        task_type: str,
        user_id: int,
        session_id: int,
        task_data: Dict[str, Any],
        db: Session
    ) -> str:
        """
        Crée une nouvelle tâche asynchrone et retourne l'ID de la tâche immédiatement.
        """
        task_id = str(uuid.uuid4())
        
        # Créer l'enregistrement en base
        async_task = models.AsyncTask(
            task_id=task_id,
            task_type=task_type,
            status="pending",
            progress_percentage=0.0,
            current_step="Initialisation...",
            user_id=user_id,
            session_id=session_id,
            task_data=json.dumps(task_data),
            created_at=datetime.now(timezone.utc)
        )
        
        db.add(async_task)
        db.commit()
        db.refresh(async_task)
        
        # Log initial
        initial_log = models.AsyncTaskLog(
            task_id=async_task.id,
            level="info",
            message=f" Tâche {task_type} créée et en attente d'exécution",
            step_name="created",
            progress_percentage=0.0
        )
        db.add(initial_log)
        db.commit()
        
        logger.info(f"Created async task {task_id} of type {task_type} for user {user_id}")
        
        return task_id
    
    async def start_task_execution(
        self,
        task_id: str,
        execution_func: Callable,
        db: Session,
        *args,
        **kwargs
    ):
        """
        Démarre l'exécution asynchrone d'une tâche.
        """
        async_task = db.query(models.AsyncTask).filter_by(task_id=task_id).first()
        if not async_task:
            logger.error(f"Task {task_id} not found for execution")
            return
        
        # Marquer comme en cours
        async_task.status = "running"
        async_task.started_at = datetime.now(timezone.utc)
        async_task.updated_at = datetime.now(timezone.utc)
        async_task.current_step = "Démarrage de l'exécution..."
        async_task.progress_percentage = 5.0
        
        start_log = models.AsyncTaskLog(
            task_id=async_task.id,
            level="info",
            message=" Démarrage de l'exécution de la tâche",
            step_name="execution_started",
            progress_percentage=5.0
        )
        db.add(start_log)
        db.commit()
        
        # Créer un wrapper pour l'exécution avec gestion d'erreur
        async def task_wrapper():
            try:
                # Exécuter la fonction avec le progress callback
                progress_callback = self._create_progress_callback(task_id, db)
                result = await execution_func(progress_callback=progress_callback, *args, **kwargs)
                
                # Marquer comme terminé avec succès
                await self._mark_task_completed(task_id, result, db)
                
            except Exception as e:
                logger.exception(f"Task {task_id} failed with error: {str(e)}")
                await self._mark_task_failed(task_id, str(e), db)
        
        # Lancer la tâche en arrière-plan
        task = asyncio.create_task(task_wrapper())
        self._running_tasks[task_id] = task
        
        logger.info(f"Started execution of task {task_id}")
    
    def _create_progress_callback(self, task_id: str, db: Session):
        """
        Crée un callback amélioré pour les updates de progression avec support des sous-étapes.
        """
        last_update_time = 0
        
        def enhanced_progress_callback(
            step_name: str,
            message: str,
            progress_percentage: float = None,
            level: str = "info",
            # Nouvelles fonctionnalités
            substeps: List[Dict] = None,
            resource_info: Dict = None,
            estimated_duration: int = None,
            metadata: Dict = None
        ):
            nonlocal last_update_time
            
            try:
                # Éviter les mises à jour trop fréquentes (max 2 updates/sec)
                current_time = time.time()
                if current_time - last_update_time < 0.5:
                    return
                
                async_task = db.query(models.AsyncTask).filter_by(task_id=task_id).first()
                if not async_task:
                    logger.warning(f"Task {task_id} not found for progress update")
                    return
                
                # Mettre à jour la tâche principale
                async_task.current_step = message
                async_task.updated_at = datetime.now(timezone.utc)
                if progress_percentage is not None:
                    async_task.progress_percentage = min(100.0, max(0.0, progress_percentage))
                
                # Construire les données étendues pour le frontend
                extended_data = {}
                if substeps:
                    extended_data['substeps'] = substeps
                if resource_info:
                    extended_data['resource_info'] = resource_info
                if estimated_duration:
                    extended_data['estimated_duration'] = estimated_duration
                if metadata:
                    extended_data['metadata'] = metadata
                
                # Stocker les données étendues dans le champ task_data
                if extended_data:
                    try:
                        current_task_data = json.loads(async_task.task_data or '{}')
                        current_task_data['substep_details'] = extended_data
                        async_task.task_data = json.dumps(current_task_data)
                    except (json.JSONDecodeError, TypeError):
                        # En cas d'erreur, créer une nouvelle structure
                        async_task.task_data = json.dumps({'substep_details': extended_data})
                
                # Ajouter le log principal
                progress_log = models.AsyncTaskLog(
                    task_id=async_task.id,
                    level=level,
                    message=message,
                    step_name=step_name,
                    progress_percentage=progress_percentage
                )
                db.add(progress_log)
                
                # Ajouter des logs détaillés pour les sous-étapes
                if substeps:
                    for i, substep in enumerate(substeps):
                        substep_log = models.AsyncTaskLog(
                            task_id=async_task.id,
                            level="info",
                            message=f"Sous-étape: {substep.get('name', 'Unknown')} - {substep.get('status', 'pending')}",
                            step_name=f"{step_name}_substep_{i}",
                            progress_percentage=substep.get('progress', 0)
                        )
                        db.add(substep_log)
                
                # Log pour les ressources créées
                if resource_info and resource_info.get('action') == 'created':
                    resource_log = models.AsyncTaskLog(
                        task_id=async_task.id,
                        level="success",
                        message=f" Ressource créée: {resource_info.get('resource_type', 'Unknown')} '{resource_info.get('resource_name', 'Unknown')}'" + 
                                (f" en {resource_info.get('duration', 'N/A')}s" if resource_info.get('duration') else ""),
                        step_name=f"{step_name}_resource_created",
                        progress_percentage=progress_percentage
                    )
                    db.add(resource_log)
                
                db.commit()
                last_update_time = current_time
                
                # Log amélioré
                extra_info = ""
                if resource_info:
                    extra_info += f" | Ressource: {resource_info.get('resource_type', 'Unknown')}"
                if estimated_duration:
                    extra_info += f" | ETA: {estimated_duration}s"
                if substeps:
                    extra_info += f" | Sous-étapes: {len(substeps)}"
                    
                logger.debug(f"Task {task_id} progress: {progress_percentage}% - {message}{extra_info}")
                
            except Exception as e:
                logger.error(f"Failed to update progress for task {task_id}: {str(e)}")
        
        return enhanced_progress_callback
    
    async def _mark_task_completed(self, task_id: str, result: Any, db: Session):
        """
        Marque une tâche comme terminée avec succès.
        """
        async_task = db.query(models.AsyncTask).filter_by(task_id=task_id).first()
        if not async_task:
            return
        
        async_task.status = "completed"
        async_task.progress_percentage = 100.0
        async_task.current_step = "Tâche terminée avec succès"
        async_task.completed_at = datetime.now(timezone.utc)
        async_task.updated_at = datetime.now(timezone.utc)
        
        if result:
            logger.info(f"Task {task_id}: result type={type(result)}, result={result}")
            try:
                serialized = json.dumps(result, default=str)
                logger.info(f"Task {task_id}: serialized successfully, length={len(serialized)}")
                async_task.result_data = serialized
            except Exception as e:
                logger.error(f"Task {task_id}: serialization failed: {e}", exc_info=True)
                async_task.result_data = json.dumps({"error": str(e), "result_type": str(type(result))})
        
        completion_log = models.AsyncTaskLog(
            task_id=async_task.id,
            level="success",
            message=" Tâche terminée avec succès",
            step_name="completed",
            progress_percentage=100.0
        )
        db.add(completion_log)
        db.commit()
        
        # Nettoyer la référence de tâche en cours
        if task_id in self._running_tasks:
            del self._running_tasks[task_id]
        
        logger.info(f"Task {task_id} completed successfully")
    
    async def _mark_task_failed(self, task_id: str, error_message: str, db: Session):
        """
        Marque une tâche comme échouée.
        """
        async_task = db.query(models.AsyncTask).filter_by(task_id=task_id).first()
        if not async_task:
            return
        
        async_task.status = "failed"
        async_task.current_step = f"Erreur: {error_message}"
        async_task.completed_at = datetime.now(timezone.utc)
        async_task.updated_at = datetime.now(timezone.utc)
        async_task.error_message = error_message
        
        error_log = models.AsyncTaskLog(
            task_id=async_task.id,
            level="error",
            message=f" Tâche échouée: {error_message}",
            step_name="failed"
        )
        db.add(error_log)
        db.commit()
        
        # Nettoyer la référence de tâche en cours
        if task_id in self._running_tasks:
            del self._running_tasks[task_id]
        
        logger.error(f"Task {task_id} failed: {error_message}")
    
    def get_running_tasks(self) -> Dict[str, str]:
        """
        Retourne la liste des tâches en cours d'exécution.
        """
        return {task_id: "running" for task_id in self._running_tasks.keys()}
    
    def is_task_running(self, task_id: str) -> bool:
        """
        Vérifie si une tâche est en cours d'exécution.
        """
        return task_id in self._running_tasks

    @staticmethod
    def parse_terraform_output_for_progress(output_line: str) -> Optional[Dict]:
        """
        Parse la sortie Terraform pour extraire les informations de progression des ressources.
        """
        patterns = {
            'creating': r'(\w+\.\w+): Creating\.\.\.',
            'created': r'(\w+\.\w+): Creation complete after (\d+)s',
            'modifying': r'(\w+\.\w+): Modifying\.\.\.',
            'modified': r'(\w+\.\w+): Modifications complete after (\d+)s',
            'destroying': r'(\w+\.\w+): Destroying\.\.\.',
            'destroyed': r'(\w+\.\w+): Destruction complete after (\d+)s',
            'refreshing': r'(\w+\.\w+): Refreshing state\.\.\.'
        }
        
        for action, pattern in patterns.items():
            match = re.search(pattern, output_line)
            if match:
                resource_full_name = match.group(1)
                resource_parts = resource_full_name.split('.')
                resource_type = resource_parts[0] if resource_parts else 'unknown'
                resource_name = resource_parts[1] if len(resource_parts) > 1 else 'unknown'
                
                result = {
                    'action': action,
                    'resource_type': resource_type,
                    'resource_name': resource_name,
                    'resource_full_name': resource_full_name
                }
                
                if action in ['created', 'modified', 'destroyed'] and len(match.groups()) > 1:
                    result['duration'] = int(match.group(2))
                    
                return result
        
        return None

    @staticmethod
    def estimate_remaining_time(step_name: str, progress_percentage: float) -> Optional[int]:
        """
        Estime le temps restant basé sur l'étape actuelle et le pourcentage de progression.
        """
        # Durées estimées par étape (en secondes)
        step_durations = {
            'initialization': 15,
            'validation': 20,
            'planning': 30,
            'networking': 45,
            'security_groups': 20,
            'compute': 60,
            'storage': 20,
            'finalization': 15
        }
        
        # Mapping des noms d'étapes du backend vers nos étapes
        step_mapping = {
            'terraform_init': 'initialization',
            'terraform_validate': 'validation',
            'terraform_plan': 'planning',
            'terraform_apply': 'compute',  # Par défaut
            'génération': 'planning',
            'déploiement': 'compute',
            'finalisation': 'finalization'
        }
        
        # Trouver l'étape correspondante
        mapped_step = None
        for backend_step, frontend_step in step_mapping.items():
            if backend_step.lower() in step_name.lower():
                mapped_step = frontend_step
                break
        
        # Estimation basée sur le pourcentage de progression global
        if progress_percentage < 10:
            mapped_step = 'initialization'
        elif progress_percentage < 20:
            mapped_step = 'validation'
        elif progress_percentage < 30:
            mapped_step = 'planning'
        elif progress_percentage < 50:
            mapped_step = 'networking'
        elif progress_percentage < 60:
            mapped_step = 'security_groups'
        elif progress_percentage < 80:
            mapped_step = 'compute'
        elif progress_percentage < 90:
            mapped_step = 'storage'
        else:
            mapped_step = 'finalization'
        
        if mapped_step and mapped_step in step_durations:
            # Calcul simple : temps total estimé - temps écoulé
            total_estimated = sum(step_durations.values())
            elapsed_estimated = (progress_percentage / 100) * total_estimated
            remaining = max(0, total_estimated - elapsed_estimated)
            return int(remaining)
        
        return None

    @staticmethod
    def create_aws_deployment_substeps(progress_percentage: float) -> List[Dict]:
        """
        Crée une liste de sous-étapes pour le déploiement AWS basée sur le pourcentage actuel.
        """
        substeps = [
            {"name": "Initialisation Terraform", "status": "completed" if progress_percentage > 10 else ("in_progress" if progress_percentage >= 0 else "pending")},
            {"name": "Validation configuration", "status": "completed" if progress_percentage > 20 else ("in_progress" if progress_percentage >= 10 else "pending")},
            {"name": "Planification ressources", "status": "completed" if progress_percentage > 30 else ("in_progress" if progress_percentage >= 20 else "pending")},
            {"name": "Création VPC", "status": "completed" if progress_percentage > 40 else ("in_progress" if progress_percentage >= 30 else "pending")},
            {"name": "Configuration subnets", "status": "completed" if progress_percentage > 45 else ("in_progress" if progress_percentage >= 40 else "pending")},
            {"name": "Groupes de sécurité", "status": "completed" if progress_percentage > 60 else ("in_progress" if progress_percentage >= 50 else "pending")},
            {"name": "Lancement instance EC2", "status": "completed" if progress_percentage > 80 else ("in_progress" if progress_percentage >= 60 else "pending")},
            {"name": "Configuration stockage", "status": "completed" if progress_percentage > 90 else ("in_progress" if progress_percentage >= 80 else "pending")},
            {"name": "Récupération outputs", "status": "completed" if progress_percentage >= 100 else ("in_progress" if progress_percentage >= 90 else "pending")}
        ]
        
        return substeps


# Instance globale du gestionnaire de tâches
task_manager = TaskManager()