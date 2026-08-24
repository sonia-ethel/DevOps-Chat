# © 2024–2026 TOURE Arnaud Patrick
# Licensed under the MIT License

# app/models/__init__.py

from sqlalchemy.orm import declarative_base
Base = declarative_base()

from .user import User
from .user_aws_credentials import UserAWSCredentials
from .session import Session
from .provider import Provider
from .deployment import Deployment
from .ami import Ami
from .instance import Instance
from .message import Message
from .chat import Chat
from .execution import Execution
from .ansible_report import AnsibleReport
from .terraform_report import TerraformReport
from .audit_report import AuditReport
from .execution_log import ExecutionLog
from .kubernetes_report import KubernetesReport
from .resource_action_log import ResourceActionLog
from .intent import Intent

# OK Nouveaux modèles pour les fichiers générés
from .generated_terraform_file import GeneratedTerraformFile
from .generated_playbook import GeneratedPlaybook
from .generated_audit_file import GeneratedAuditFile
from .generated_kubernetes_manifest import GeneratedKubernetesManifest
from .generated_inventory_file import GeneratedInventoryFile
from .generated_private_key import GeneratedPrivateKey

# OK Modèles pour le monitoring et audit
from .metrics_snapshot import MetricsSnapshot
from .audit_snapshot import AuditSnapshot

# OK Async task system
from .async_task import AsyncTask, AsyncTaskLog

# OK Plan-based execution system (new architecture)
from .plan import Plan, PlanExecution, PlanPhase

# OK Monitoring metrics storage
from .metrics_snapshot import MetricsSnapshot