"""
Schémas JSON standard pour l'Installer Engine de DAC.

Ces schémas garantissent la cohérence pour TOUTES les installations
(nginx, apache, docker, redis, postgresql, etc.)
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime, timezone


# ============================================================================
# A) InstallationRequest - Entrée du moteur
# ============================================================================

class AppConfig(BaseModel):
    """Configuration spécifique de l'application"""
    requested_port: Optional[int] = None
    allow_port_fallback: bool = True
    port_candidates: List[int] = Field(default_factory=lambda: [8080, 8081, 8082, 8083, 8084])
    healthcheck_path: str = "/"
    healthcheck_expected: str = "200"
    extra: Dict[str, Any] = Field(default_factory=dict)  # Config app-specific


class AppSpec(BaseModel):
    """Spécification de l'application à installer"""
    name: str = Field(..., description="Nom de l'app (nginx, apache, docker...)")
    requested_version: Optional[str] = None
    channel: str = "stable"  # stable, latest, edge
    features: List[str] = Field(default_factory=lambda: ["service"])
    config: AppConfig = Field(default_factory=AppConfig)


class RetryPolicy(BaseModel):
    """Politique de retry"""
    max_attempts: int = 2
    backoff_seconds: int = 5


class ExecutionSpec(BaseModel):
    """Spécification d'exécution"""
    method: Literal["ssm", "ssh", "ansible"] = "ssm"
    timeout_seconds: int = 600
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)


class InstallationPolicy(BaseModel):
    """Politique d'installation"""
    fallback_to_standard_version: bool = True
    allow_repo_enable: bool = True
    allow_service_restart: bool = True
    strict: bool = False
    idempotent: bool = True  # Ne pas casser si déjà installé


class InstallationRequest(BaseModel):
    """Request standard pour toute installation"""
    request_id: str = Field(default_factory=lambda: __import__('uuid').uuid4().hex)
    intent: Literal["install", "configure", "upgrade", "validate"] = "install"
    app: AppSpec
    execution: ExecutionSpec = Field(default_factory=ExecutionSpec)
    policy: InstallationPolicy = Field(default_factory=InstallationPolicy)
    instances: List[str] = Field(default_factory=list)  # Instance IDs


# ============================================================================
# B) InstallationPlan - Sortie de l'analyse/planification
# ============================================================================

class OSStrategy(BaseModel):
    """Stratégie d'installation pour un OS donné"""
    install_strategy: str  # apt, yum, amazon-linux-extras+yum, dnf, zypper
    package: str
    pre_steps: List[str] = Field(default_factory=list)
    post_steps: List[str] = Field(default_factory=list)
    version_command: Optional[str] = None  # Pour vérifier version installée


class Check(BaseModel):
    """Check de validation"""
    type: Literal["service_active", "port_listening", "http_get", "command", "file_exists"]
    description: str = ""
    # Paramètres variables selon le type
    service: Optional[str] = None
    port: Optional[str] = None  # Peut être "chosen_port" (dynamique)
    url: Optional[str] = None
    command: Optional[str] = None
    file_path: Optional[str] = None
    expected: Optional[str] = None


class AutoFix(BaseModel):
    """Auto-fix en cas d'échec"""
    if_condition: str  # port_in_use, service_failed, config_invalid
    action: str
    description: str = ""


class InstallationPlan(BaseModel):
    """Plan d'installation généré par l'engine"""
    plan_id: str = Field(default_factory=lambda: __import__('uuid').uuid4().hex)
    app: AppSpec
    os_matrix: Dict[str, OSStrategy]  # ubuntu, debian, amzn, rhel, centos, fedora
    checks: List[Check]
    auto_fixes: List[AutoFix]
    ports_needed: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def steps_count(self) -> int:
        return len(getattr(self, "steps", []) or [])


# ============================================================================
# C) InstallationResult - Sortie finale standard
# ============================================================================

class Fallback(BaseModel):
    """Fallback effectué"""
    type: str  # port, version, method
    reason: str
    original: Any
    chosen: Any


class InstallationSummary(BaseModel):
    """Résumé global de l'installation"""
    app: str
    requested_version: Optional[str]
    installed_version: Optional[str]
    requested_port: Optional[int]
    chosen_port: Optional[int]
    fallbacks: List[Fallback] = Field(default_factory=list)


class OSInfo(BaseModel):
    """Info OS de l'instance"""
    id: str  # ubuntu, debian, amzn, rhel, centos, fedora
    version: str
    pretty_name: str = ""


class CheckResult(BaseModel):
    """Résultat d'un check"""
    name: str
    passed: bool
    details: str = ""


class Artifact(BaseModel):
    """Artifact généré"""
    name: str
    type: str  # config, log, report
    path: str
    size_bytes: Optional[int] = None


class InstanceResult(BaseModel):
    """Résultat par instance"""
    instance_id: str
    status: Literal["success", "failed", "skipped", "already_installed"]
    os: Optional[OSInfo] = None
    actions_taken: List[str] = Field(default_factory=list)
    checks: Dict[str, bool] = Field(default_factory=dict)
    check_details: List[CheckResult] = Field(default_factory=list)
    artifacts: List[Artifact] = Field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0
    error: Optional[str] = None


class InstallationResult(BaseModel):
    """Résultat final standard (pour toutes les apps)"""
    task_id: str
    status: Literal["completed", "partial", "failed"]
    summary: InstallationSummary
    instances: List[InstanceResult]
    errors: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
