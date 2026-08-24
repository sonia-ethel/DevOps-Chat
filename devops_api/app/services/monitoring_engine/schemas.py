"""
Monitoring Engine - Schemas
Définit les structures de données pour le monitoring
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Literal
from datetime import datetime, timezone


class InstanceMetrics(BaseModel):
    """Métriques d'une instance"""
    instance_id: str
    cpu_percent: Optional[float] = None
    mem_used_percent: Optional[float] = None
    disk_used_percent: Optional[float] = None
    load_1: Optional[float] = None
    load_5: Optional[float] = None
    load_15: Optional[float] = None
    uptime: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: Literal["success", "partial", "failed"] = "success"
    error: Optional[str] = None


class MetricsSummary(BaseModel):
    """Résumé des métriques collectées"""
    instances_total: int
    ok: int = 0
    failed: int = 0
    avg_cpu: Optional[float] = None
    avg_mem: Optional[float] = None
    avg_disk: Optional[float] = None

    @property
    def instances_ok(self) -> int:
        return self.ok

    @property
    def instances_failed(self) -> int:
        return self.failed

    @property
    def avg_cpu_percent(self) -> Optional[float]:
        return self.avg_cpu

    @property
    def avg_mem_used_percent(self) -> Optional[float]:
        return self.avg_mem

    @property
    def avg_disk_used_percent(self) -> Optional[float]:
        return self.avg_disk


class MetricsSnapshot(BaseModel):
    """Snapshot de métriques pour plusieurs instances"""
    action: str = "metrics_snapshot"
    status: Literal["success", "partial", "failed"]
    summary: MetricsSummary
    instances: List[InstanceMetrics]
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    task_id: Optional[str] = None


class MonitoringPlan(BaseModel):
    """Plan de monitoring (avant exécution)"""
    monitoring_type: str = "metrics_snapshot"
    instances_count: int
    instance_ids: List[str]
    metrics: List[str] = ["CPU", "Memory", "Disk", "Load", "Uptime"]
    impact: str = "read-only"
    estimated_duration: str
    estimated_duration_seconds: int
