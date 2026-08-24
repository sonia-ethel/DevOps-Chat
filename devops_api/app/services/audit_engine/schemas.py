"""
Audit Engine - Schemas
Définit les structures de données pour les audits
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Literal
from datetime import datetime


class AuditFinding(BaseModel):
    """Un finding d'audit (problème détecté)"""
    severity: Literal["critical", "high", "medium", "low", "info"]
    title: str
    description: Optional[str] = None
    recommendation: Optional[str] = None


class InstanceAuditResult(BaseModel):
    """Résultat d'audit pour une instance"""
    instance_id: str
    os: str
    status: Literal["success", "partial", "failed"]
    findings: List[AuditFinding] = []
    metrics: Dict[str, Any] = {}
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    error: Optional[str] = None


class AuditSummary(BaseModel):
    """Résumé des résultats d'audit"""
    instances_total: int
    ok: int = 0
    failed: int = 0
    critical_findings: int = 0
    high_findings: int = 0
    medium_findings: int = 0
    low_findings: int = 0

    @property
    def instances_ok(self) -> int:
        return self.ok

    @property
    def instances_failed(self) -> int:
        return self.failed


class AuditResult(BaseModel):
    """Résultat global d'un audit"""
    action: str = "audit"
    audit_type: Literal["ops_health", "security_basic", "lynis", "full"]
    status: Literal["success", "partial", "failed"]
    summary: AuditSummary
    instances: List[InstanceAuditResult]
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    task_id: Optional[str] = None


class AuditPlan(BaseModel):
    """Plan d'audit (avant exécution)"""
    audit_type: str
    instances_count: int
    instance_ids: List[str]
    recipe_names: List[str]
    checks: List[str]
    impact: str = "read-only"
    estimated_duration_seconds: int
    commands_preview: List[str] = []
