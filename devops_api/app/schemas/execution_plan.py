"""
Schémas pour la planification et exécution.

ExecutionPlan: Représentation lisible d'un plan avant exécution.
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Literal
from datetime import datetime


class FallbackExplanation(BaseModel):
    """Explication d'un fallback potentiel"""
    type: Literal["port", "package", "service", "config"]
    original: str
    fallback: str
    reason: str
    likelihood: Literal["likely", "possible", "rare"] = "possible"
    example: Optional[str] = None


class InstallationAction(BaseModel):
    """Une action d'installation lisible"""
    app: str
    port: Optional[int] = None
    port_candidates: List[int] = Field(default_factory=list)
    version: Optional[str] = None
    fallbacks: List[FallbackExplanation] = Field(default_factory=list)
    pre_steps: List[str] = Field(default_factory=list)
    post_steps: List[str] = Field(default_factory=list)
    estimated_duration_seconds: int = 30


class ConfigurationAction(BaseModel):
    """Une action de configuration standard SSM"""
    type: str  # "nginx_config", "security", "monitoring", etc.
    description: str
    commands: List[str] = Field(default_factory=list)
    estimated_duration_seconds: int = 15


class InstanceTarget(BaseModel):
    """Instance cible"""
    instance_id: str
    name: Optional[str] = None
    os: str  # ubuntu, amzn, rhel, etc.
    state: str  # running
    can_execute: bool = True
    reason_if_disabled: Optional[str] = None


class ExecutionPlanPreview(BaseModel):
    """Plan d'exécution à présenter à l'utilisateur (preview)"""
    plan_id: str = Field(default_factory=lambda: __import__('uuid').uuid4().hex)
    
    # Ce qu'on va faire
    intent: Literal["install", "configure", "upgrade"]
    
    # Où on le fait
    target_instances: List[InstanceTarget]
    instance_count: int  # Facilite la lecture
    
    # Installation actions (via Installer Engine)
    installations: List[InstallationAction] = Field(default_factory=list)
    
    # Configuration actions (via SSM normal)
    configurations: List[ConfigurationAction] = Field(default_factory=list)
    
    # Estimations
    total_estimated_duration_seconds: int
    
    # Lisibilité: impacts
    impacts: Dict[str, str] = Field(default_factory=dict)  # "systemd_services": "nginx, docker", "ports_modified": "8080, 3000"
    
    # Risques potentiels
    potential_issues: List[str] = Field(default_factory=list)
    
    # Texte lisible pour affichage
    human_readable_summary: str
    
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ChatState(BaseModel):
    """État de la conversation pour le chat"""
    state: Literal[
        "awaiting_intent",
        "awaiting_instance_selection",
        "building_plan",
        "awaiting_confirmation",
        "executing",
        "completed",
        "failed",
        "cancelled"
    ]
    
    # Context de la session
    current_intent_text: Optional[str] = None
    current_plan_id: Optional[str] = None
    current_task_id: Optional[str] = None
    selected_instances: List[str] = Field(default_factory=list)
    
    # Pour affichage
    message_to_user: str = ""
    next_action: str = ""  # "select_instances", "confirm_plan", "monitor_task"
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class CancellationRequest(BaseModel):
    """Demande d'annulation"""
    task_id: str
    reason: Optional[str] = None
    requested_at: datetime = Field(default_factory=datetime.utcnow)


class TaskStatusWithPlan(BaseModel):
    """Statut d'une task avec le plan associé"""
    task_id: str
    status: str  # pending, running, completed, failed, cancelled
    phase: str  # "diagnostic", "bootstrap", "installation", "configuration", "verification"
    progress_percent: int
    plan: Optional[ExecutionPlanPreview] = None
    current_instance: Optional[str] = None
    current_action: Optional[str] = None
    
    # Logs courts (dernières lignes)
    recent_logs: List[str] = Field(default_factory=list)
    
    # Résultats partiels (si certaines instances finies)
    partial_results: Dict[str, Dict] = Field(default_factory=dict)  # instance_id -> result
    
    estimated_remaining_seconds: Optional[int] = None
    created_at: datetime
    updated_at: datetime
