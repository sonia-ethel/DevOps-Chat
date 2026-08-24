"""
Monitoring Engine - Runner
Exécute la collecte de métriques via SSM
"""
import logging
import json
from typing import List, Dict, Any
from datetime import datetime, timezone

from app.services.monitoring_engine.schemas import (
    MetricsSnapshot,
    InstanceMetrics,
    MetricsSummary,
    MonitoringPlan
)
from app.services.monitoring_engine.recipes import get_monitoring_recipe
from app.services.ssm_executor import SSMExecutor

logger = logging.getLogger(__name__)


class MonitoringRunner:
    """Exécute la collecte de métriques sur des instances"""

    def __init__(
        self,
        db=None,
        ssm_executor: SSMExecutor | None = None,
        region: str = "us-east-1",
    ):
        self.region = region
        self.db = db
        self.ssm_executor = ssm_executor
    
    def create_plan(self, monitoring_type: str, instance_ids: List[str]) -> MonitoringPlan:
        """Crée un plan de monitoring"""
        recipe = get_monitoring_recipe(monitoring_type)
        if not recipe:
            raise ValueError(f"Unknown monitoring type: {monitoring_type}")

        estimated_seconds = max(20, len(instance_ids) * 10)
        duration = f"{estimated_seconds}s" if estimated_seconds < 60 else f"{estimated_seconds // 60}min"

        return MonitoringPlan(
            monitoring_type=monitoring_type,
            instances_count=len(instance_ids),
            instance_ids=instance_ids,
            metrics=recipe.metrics,
            estimated_duration=duration,
            estimated_duration_seconds=estimated_seconds,
        )
    
    async def collect_metrics(
        self,
        monitoring_type: str,
        instance_ids: List[str],
        task_id: str | None = None,
    ) -> MetricsSnapshot:
        """
        Collecte les métriques des instances
        
        Args:
            monitoring_type: Type de monitoring (metrics_snapshot)
            instance_ids: Liste des instance IDs
            task_id: ID de la tâche (optionnel)
        
        Returns:
            MetricsSnapshot avec métriques complètes
        """
        if not self.ssm_executor:
            raise ValueError("SSM executor manquant pour le monitoring")

        logger.info(
            "[MONITORING_START] type=%s instances=%d task_id=%s",
            monitoring_type,
            len(instance_ids),
            task_id,
        )

        recipe = get_monitoring_recipe(monitoring_type)
        if not recipe:
            raise ValueError(f"Unknown monitoring type: {monitoring_type}")
        
        instance_metrics = []
        summary = MetricsSummary(instances_total=len(instance_ids))
        
        # Pour calculer les moyennes
        cpu_values = []
        mem_values = []
        disk_values = []
        
        for instance_id in instance_ids:
            try:
                metrics = await self._collect_instance_metrics(instance_id, recipe)
                instance_metrics.append(metrics)
                
                if metrics.status == "success":
                    summary.ok += 1
                    
                    # Collecter pour moyennes
                    if metrics.cpu_percent is not None:
                        cpu_values.append(metrics.cpu_percent)
                    if metrics.mem_used_percent is not None:
                        mem_values.append(metrics.mem_used_percent)
                    if metrics.disk_used_percent is not None:
                        disk_values.append(metrics.disk_used_percent)
                else:
                    summary.failed += 1
            
            except Exception as e:
                logger.error(f"[MONITORING_ERROR] instance={instance_id} error={str(e)}")
                summary.failed += 1
                instance_metrics.append(
                    InstanceMetrics(
                        instance_id=instance_id,
                        status="failed",
                        error=str(e)
                    )
                )
        
        # Calculer moyennes
        if cpu_values:
            summary.avg_cpu = round(sum(cpu_values) / len(cpu_values), 1)
        if mem_values:
            summary.avg_mem = round(sum(mem_values) / len(mem_values), 1)
        if disk_values:
            summary.avg_disk = round(sum(disk_values) / len(disk_values), 1)
        
        # Determine overall status
        if summary.ok == summary.instances_total:
            overall_status = "success"
        elif summary.ok > 0:
            overall_status = "partial"
        else:
            overall_status = "failed"
        
        snapshot = MetricsSnapshot(
            status=overall_status,
            summary=summary,
            instances=instance_metrics,
            task_id=task_id,
        )
        
        logger.info(f"[MONITORING_COMPLETE] task_id={task_id} status={overall_status} ok={summary.ok}/{summary.instances_total}")
        
        return snapshot
    
    async def _collect_instance_metrics(self, instance_id: str, recipe) -> InstanceMetrics:
        """Collecte les métriques d'une instance unique"""
        logger.info(f"[MONITORING_INSTANCE] instance={instance_id} recipe={recipe.name}")
        
        # Execute all commands
        outputs = {}
        
        for cmd_name, cmd in recipe.commands.items():
            try:
                logger.debug("[MONITORING_CMD] instance=%s cmd=%s", instance_id, cmd_name)
                exec_result = self.ssm_executor.execute_command(
                    instance_ids=[instance_id],
                    command=cmd,
                    timeout=60,
                )
                outputs[cmd_name] = exec_result.get(instance_id, {}).get("stdout", "")
            except Exception as e:
                logger.warning(
                    "[MONITORING_CMD_ERROR] instance=%s cmd=%s error=%s",
                    instance_id,
                    cmd_name,
                    str(e),
                )
                outputs[cmd_name] = f"ERROR: {str(e)}"
        
        # Parse metrics
        try:
            parsed = recipe.parser_func(outputs)
            
            metrics = InstanceMetrics(
                instance_id=instance_id,
                cpu_percent=parsed.get("cpu_percent"),
                mem_used_percent=parsed.get("mem_used_percent"),
                disk_used_percent=parsed.get("disk_used_percent"),
                load_1=parsed.get("load_1"),
                load_5=parsed.get("load_5"),
                load_15=parsed.get("load_15"),
                uptime=parsed.get("uptime"),
                status="success"
            )
        
        except Exception as e:
            logger.error(f"[MONITORING_PARSE_ERROR] instance={instance_id} error={str(e)}")
            metrics = InstanceMetrics(
                instance_id=instance_id,
                status="failed",
                error=str(e)
            )
        
        return metrics


# Helper pour sauvegarder le snapshot
def save_metrics_snapshot(snapshot: MetricsSnapshot, output_dir: str = "generated_files/monitoring", db = None, session_id: int = None, user_id: int = None):
    """Sauvegarde le snapshot de métriques dans un fichier JSON et en base de données"""
    import os
    
    os.makedirs(output_dir, exist_ok=True)
    
    task_id = snapshot.task_id or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"metrics_{task_id}.json"
    filepath = os.path.join(output_dir, filename)
    
    with open(filepath, "w") as f:
        json.dump(snapshot.dict(), f, indent=2)
    
    logger.info(f"[MONITORING_SNAPSHOT] Saved to {filepath}")
    
    # Enregistrer en base de données si db est fourni
    if db and user_id:
        try:
            from app import models
            
            metrics_record = models.MetricsSnapshot(
                task_id=str(task_id),
                session_id=session_id,
                user_id=user_id,
                instances_total=snapshot.summary.instances_total,
                instances_ok=snapshot.summary.instances_ok,
                instances_failed=snapshot.summary.instances_failed,
                avg_cpu_percent=snapshot.summary.avg_cpu_percent,
                avg_mem_used_percent=snapshot.summary.avg_mem_used_percent,
                avg_disk_used_percent=snapshot.summary.avg_disk_used_percent,
                status=snapshot.status,
                full_data=json.dumps(snapshot.dict()),
            )
            db.add(metrics_record)
            db.commit()
            logger.info(f"[MONITORING_DB] Metrics snapshot recorded in DB: id={metrics_record.id}")
        except Exception as e:
            logger.warning(f"[MONITORING_DB] Failed to save metrics to DB: {e}")
    return filepath
