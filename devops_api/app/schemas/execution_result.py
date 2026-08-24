"""
Modèles pour les résultats d'installation.

Structure standard pour stocker et communiquer les résultats.
"""
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from enum import Enum


class CheckStatus(str, Enum):
    """Statut d'un check"""
    PASSED = "passed"
    FAILED = "failed"
    UNKNOWN = "unknown"


class InstallCheckResult(BaseModel):
    """Résultat d'un check unitaire"""
    type: str  # service_active, port_listening, http_get, command, file_exists
    description: str
    status: CheckStatus
    expected: Optional[str] = None
    actual: Optional[str] = None
    error: Optional[str] = None


class InstanceInstallationResult(BaseModel):
    """Résultat d'installation pour UNE instance"""
    instance_id: str
    app: str
    
    # Demande vs. réalité
    requested_port: Optional[int] = None
    chosen_port: Optional[int] = None
    requested_version: Optional[str] = None
    installed_version: Optional[str] = None
    
    # Statut global
    status: str  # "installed", "failed", "partial"
    reason: Optional[str] = None
    
    # Fallbacks appliqués
    fallbacks_applied: List[Dict[str, str]] = Field(default_factory=list)
    # Ex: [{"type": "port", "original": "8080", "chosen": "8081"}]
    
    # Checks
    checks: List[InstallCheckResult] = Field(default_factory=list)
    
    # Output
    stdout: str = ""
    stderr: str = ""
    exit_code: Optional[int] = None
    
    # Durée
    duration_seconds: float = 0.0
    
    # Timestamp
    executed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExecutionResult(BaseModel):
    """Résultat complet d'une exécution"""
    task_id: str
    intent_type: str  # install, configure, upgrade
    
    # Global
    status: str  # completed, failed, partial, cancelled
    total_duration_seconds: float = 0.0
    
    # Par instance
    instances: Dict[str, InstanceInstallationResult]
    
    # Résumé
    success_count: int = 0
    failure_count: int = 0
    
    # Timestamp
    completed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ChatResultMessage(BaseModel):
    """Message final pour le chat avec résultats"""
    state: str
    message: str  # Message lisible pour l'utilisateur
    execution_result: ExecutionResult  # Payload structuré complet
    install_summary: str  # Texte court pour affichage rapide
