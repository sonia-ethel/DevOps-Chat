"""
Service de planification d'exécution.

Orchestre:
1. Parsing d'intention
2. Sélection d'instances
3. Construction du plan (preview)
4. Exécution
5. Suivi de progression
"""
import logging
from typing import List, Optional, Tuple, Dict
from datetime import datetime
from .installer_engine import (
    InstallerEngine, 
    create_installation_request_from_text,
    InstallationPlan
)
from ..schemas.execution_plan import (
    ExecutionPlanPreview,
    InstallationAction,
    ConfigurationAction,
    InstanceTarget,
    FallbackExplanation,
    ChatState
)

logger = logging.getLogger(__name__)


class ExecutionPlanner:
    """
    Service de planification d'exécution.
    
    Responsabilités:
    1. Parser l'intention de l'utilisateur
    2. Récupérer les instances disponibles
    3. Construire un plan lisible (ExecutionPlanPreview)
    4. Gérer la state machine du chat
    """
    
    def __init__(self):
        self.engine = InstallerEngine()
        self.logger = logger
    
    def parse_intent(self, user_message: str) -> Tuple[str, Dict]:
        """
        Parse un message utilisateur pour extraire l'intention.
        
        Returns:
            (intent_type, parsed_details)
            intent_type: "install", "configure", "upgrade"
            parsed_details: {
                "action": "installe nginx",
                "port": 8080 (optional),
                "version": "1.24" (optional),
                "apps": ["nginx"],
            }
        """
        user_lower = user_message.lower()
        
        # Déterminer le type d'intention
        if any(w in user_lower for w in ["installe", "install", "deploy"]):
            intent_type = "install"
        elif any(w in user_lower for w in ["configure", "config", "setup"]):
            intent_type = "configure"
        elif any(w in user_lower for w in ["upgrade", "update"]):
            intent_type = "upgrade"
        else:
            intent_type = "install"  # Default
        
        # Extraire les détails
        import re
        
        # Apps mentionnées
        apps = []
        from .installer_engine.app_recipes import list_recipes
        for app in list_recipes():
            if app in user_lower:
                apps.append(app)
        
        # Port
        port_match = re.search(r'port\s+(\d+)', user_lower)
        port = int(port_match.group(1)) if port_match else None
        
        # Version
        version_match = re.search(r'version\s+([0-9.]+)', user_lower)
        version = version_match.group(1) if version_match else None
        
        return intent_type, {
            "action": user_message,
            "port": port,
            "version": version,
            "apps": apps,
        }
    
    def sync_instances_from_aws(self, user_id: str) -> List[InstanceTarget]:
        """
        Synchronise les instances depuis AWS et retourne celles de l'utilisateur.
        
        Doit être appelé depuis les routes (qui ont la session AWS).
        Pour MVP: retourner une liste simulée ou depuis la DB.
        """
        # TODO: Implémenter la vraie sync AWS
        # Pour l'instant, retourner une liste demo
        return [
            InstanceTarget(
                instance_id="i-0123456789abcdef0",
                name="Web-Server-1",
                os="ubuntu",
                state="running"
            ),
            InstanceTarget(
                instance_id="i-0123456789abcdef1",
                name="Web-Server-2",
                os="amzn",
                state="running"
            ),
        ]
    
    def build_plan_preview(
        self,
        intent_type: str,
        parsed_intent: Dict,
        selected_instances: List[str],
        instance_map: Dict[str, InstanceTarget]
    ) -> ExecutionPlanPreview:
        """
        Construit un plan d'exécution lisible (preview).
        
        Args:
            intent_type: "install" ou "configure"
            parsed_intent: résultat de parse_intent()
            selected_instances: liste d'IDs d'instances sélectionnées
            instance_map: dict instance_id -> InstanceTarget
        
        Returns:
            ExecutionPlanPreview lisible et intelligible
        """
        self.logger.info(f"Building plan for {intent_type}: {parsed_intent}")
        
        # Cibles
        targets = [
            instance_map[iid] for iid in selected_instances
            if iid in instance_map
        ]
        
        installations = []
        configurations = []
        total_duration = 0
        impacts = {}
        potential_issues = []
        
        # ====== Si "install" intention ======
        if intent_type == "install" and parsed_intent.get("apps"):
            for app in parsed_intent["apps"]:
                # Créer une request via Installer Engine
                request_text = f"installe {app}"
                if parsed_intent.get("port"):
                    request_text += f" sur port {parsed_intent['port']}"
                
                try:
                    self.logger.info(f"Creating request from text: {request_text}")
                    request = create_installation_request_from_text(
                        request_text,
                        instances=selected_instances
                    )
                    self.logger.info(f"Request created: {request}")
                    
                    # Créer le plan d'installation
                    self.logger.info(f"Creating installation plan...")
                    install_plan = self.engine.create_plan(request)
                    self.logger.info(f"Installation plan: {install_plan}")
                    
                    if install_plan:
                        # Convertir en action lisible
                        action = self._plan_to_action(app, install_plan, parsed_intent)
                        installations.append(action)
                        total_duration += action.estimated_duration_seconds
                        
                        # Ajouter les fallbacks potentiels aux issues
                        for fallback in action.fallbacks:
                            if fallback.likelihood in ["likely", "possible"]:
                                potential_issues.append(
                                    f"[{app}] {fallback.type}: {fallback.reason}"
                                )
                        
                        # Impacts (dict str->str, pas list)
                        if install_plan.ports_needed:
                            port_str = str(action.port or "80")
                            current_ports = impacts.get("ports_modified", "")
                            impacts["ports_modified"] = f"{current_ports}, {port_str}".lstrip(", ") if current_ports else port_str
                        current_services = impacts.get("systemd_services", "")
                        impacts["systemd_services"] = f"{current_services}, {app}".lstrip(", ") if current_services else app
                    
                except Exception as e:
                    import traceback
                    self.logger.error(f"Error building plan for {app}: {e}")
                    self.logger.error(traceback.format_exc())
                    potential_issues.append(f" Erreur lors de la planification de {app}: {str(e)}")
        # ====== Si "configure" intention ======
        # Pour MVP: configurations SSM standard (nginx config, security, etc.)
        # À implémenter selon les besoins
        
        # Human-readable summary
        summary_parts = [
            f" Plan d'exécution",
            f" Intent: {intent_type}",
            f" Instances: {len(targets)} ({', '.join(i.instance_id for i in targets)})",
        ]
        
        if installations:
            summary_parts.append(f" Installations:")
            for inst in installations:
                port_str = f" (port {inst.port})" if inst.port else ""
                summary_parts.append(f"   {inst.app}{port_str}")
        
        if configurations:
            summary_parts.append(f" Configurations:")
            for conf in configurations:
                summary_parts.append(f"   {conf.description}")
        
        summary_parts.append(f" Durée estimée: {total_duration}s")
        
        if potential_issues:
            summary_parts.append(f"   Avertissements:")
            for issue in potential_issues[:3]:  # Top 3
                summary_parts.append(f"   • {issue}")
        
        human_readable = "\n".join(summary_parts)
        
        # Construire l'objet preview
        preview = ExecutionPlanPreview(
            intent=intent_type,
            target_instances=targets,
            instance_count=len(targets),
            installations=installations,
            configurations=configurations,
            total_estimated_duration_seconds=total_duration,
            impacts=impacts,
            potential_issues=potential_issues,
            human_readable_summary=human_readable
        )
        
        self.logger.info(f"Plan built: {preview.plan_id}")
        return preview
    
    def _plan_to_action(
        self,
        app_name: str,
        install_plan: InstallationPlan,
        parsed_intent: Dict
    ) -> InstallationAction:
        """Convertit un InstallationPlan en InstallationAction lisible."""
        
        # Extraire les fallbacks potentiels
        fallbacks = []
        
        # Fallback port
        requested_port = parsed_intent.get("port")
        if requested_port:
            fallbacks.append(FallbackExplanation(
                type="port",
                original=f"port {requested_port}",
                fallback="8081, 8082, 8083",
                reason="Le port demandé peut être occupé",
                likelihood="possible",
                example="Port 80 déjà utilisé par un autre service"
            ))
        
        # Fallback package (pour Amazon Linux extras)
        if install_plan.app.name == "nginx":
            fallbacks.append(FallbackExplanation(
                type="package",
                original="nginx (package standard)",
                fallback="amazon-linux-extras nginx1",
                reason="Amazon Linux requiert l'activation des extras",
                likelihood="likely" if "amzn" in [os for os in install_plan.os_matrix.keys()] else "rare",
                example="On Amazon Linux: 'amazon-linux-extras enable nginx1' puis 'yum install -y nginx'"
            ))
        
        # Fallback service failed
        fallbacks.append(FallbackExplanation(
            type="service",
            original="Restart service",
            fallback="Collecte logs + restore minimal config + retry",
            reason="Le service peut échouer au démarrage",
            likelihood="possible",
            example="NGINX config invalid -> revert à config minimale"
        ))
        
        # Pre-steps et post-steps à partir de la première stratégie
        first_strategy = next(iter(install_plan.os_matrix.values()))
        
        action = InstallationAction(
            app=app_name,
            port=requested_port,
            port_candidates=install_plan.app.config.port_candidates,
            version=parsed_intent.get("version"),
            fallbacks=fallbacks,
            pre_steps=first_strategy.pre_steps,
            post_steps=first_strategy.post_steps,
            estimated_duration_seconds=45
        )
        
        return action
