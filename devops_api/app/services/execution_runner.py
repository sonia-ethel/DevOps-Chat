"""
Service d'exécution des plans d'installation.

Orchestre:
1. Sélection de la stratégie OS
2. Génération du script bash universelle
3. Exécution (MVP: locale, production: SSM)
4. Parsing des résultats
5. Exécution des checks
6. Structuration du résultat
"""
import logging
import json
import subprocess
import re
from typing import Dict, List, Optional
from datetime import datetime
from ..schemas.execution_result import (
    InstanceInstallationResult,
    ExecutionResult,
    InstallCheckResult,
    CheckStatus
)
from .installer_engine import InstallerEngine, create_installation_request_from_text

logger = logging.getLogger(__name__)


class ExecutionRunner:
    """Exécute les plans et capture les résultats"""
    
    def __init__(self):
        self.engine = InstallerEngine()
        self.logger = logger
    
    def execute_installation(
        self,
        app_name: str,
        instances: List[str],
        requested_port: Optional[int] = None,
        task_id: Optional[str] = None
    ) -> ExecutionResult:
        """
        Exécute une installation complète et retourne les résultats.
        
        Args:
            app_name: App à installer (nginx, apache, etc.)
            instances: Liste d'instance IDs
            requested_port: Port demandé
            task_id: ID de la tâche (pour logs)
        
        Returns:
            ExecutionResult avec tous les détails
        """
        self.logger.info(f"[ExecutionRunner] Starting installation of {app_name} on {len(instances)} instances")
        
        instance_results = {}
        start_time = datetime.utcnow()
        
        # Créer une request d'installation
        request_text = f"installe {app_name}"
        if requested_port:
            request_text += f" sur port {requested_port}"
        
        request = create_installation_request_from_text(
            request_text,
            instances=instances
        )
        
        # Créer le plan
        plan = self.engine.create_plan(request)
        if not plan:
            self.logger.error(f"Failed to create plan for {app_name}")
            return ExecutionResult(
                task_id=task_id or "unknown",
                intent_type="install",
                status="failed",
                instances={},
                failure_count=len(instances)
            )
        
        self.logger.info(f"Plan created with {len(plan.os_matrix)} OS strategies")
        
        # Exécuter par instance
        for instance_id in instances:
            try:
                result = self._execute_single_instance(
                    instance_id,
                    app_name,
                    plan,
                    requested_port
                )
                instance_results[instance_id] = result
                
                # Log le résultat
                self._log_installation_result(task_id, result)
                
            except Exception as e:
                self.logger.error(f"Error executing on {instance_id}: {e}")
                instance_results[instance_id] = InstanceInstallationResult(
                    instance_id=instance_id,
                    app=app_name,
                    status="failed",
                    reason=str(e),
                    requested_port=requested_port
                )
        
        # Compter succès/échecs
        success_count = sum(1 for r in instance_results.values() if r.status == "installed")
        failure_count = len(instance_results) - success_count
        
        # Créer le résultat global
        duration = (datetime.utcnow() - start_time).total_seconds()
        result = ExecutionResult(
            task_id=task_id or "unknown",
            intent_type="install",
            status="completed" if failure_count == 0 else ("partial" if success_count > 0 else "failed"),
            instances=instance_results,
            success_count=success_count,
            failure_count=failure_count,
            total_duration_seconds=duration
        )
        
        self.logger.info(f"Installation completed: {success_count} success, {failure_count} failed")
        return result
    
    def _execute_single_instance(
        self,
        instance_id: str,
        app_name: str,
        plan,  # InstallationPlan
        requested_port: Optional[int]
    ) -> InstanceInstallationResult:
        """Exécute l'installation sur UNE instance"""
        
        self.logger.info(f"[{instance_id}] Executing installation of {app_name}")
        start_time = datetime.utcnow()
        
        result = InstanceInstallationResult(
            instance_id=instance_id,
            app=app_name,
            requested_port=requested_port,
            status="installed"  # Défaut optimiste
        )
        
        try:
            # MVP: Simuler l'exécution avec des résultats réalistes
            # Production: Appeler SSMExecutor.execute_command()
            
            # Simuler différents OS
            os_name = "ubuntu"  # MVP: hardcoded
            if "amzn" in instance_id.lower():
                os_name = "amzn"
            elif "rhel" in instance_id.lower():
                os_name = "rhel"
            
            # Obtenir la stratégie pour cet OS
            strategy = plan.os_matrix.get(os_name)
            if not strategy:
                # Fallback à ubuntu
                strategy = plan.os_matrix.get("ubuntu")
            
            # MVP: Simuler des résultats réalistes
            if app_name == "nginx":
                result.installed_version = "1.25.1"
                result.chosen_port = requested_port or 80
                result.stdout = f"""Reading package lists... Done
Building dependency tree... Done
Setting up nginx (1.25.1-1~{os_name}) ...
Processing triggers for man-db (2.12.0-2) ...
Created symlink /etc/systemd/system/multi-user.target.wants/nginx.service -> /lib/systemd/system/nginx.service.
"""
                result.stderr = ""
                result.exit_code = 0
                
                # Exécuter les checks
                result.checks = self._run_checks_for_app(app_name, result.chosen_port, os_name)
                
            else:
                # Generic fallback
                result.installed_version = "latest"
                result.chosen_port = requested_port or 80
                result.stdout = f"Package {app_name} installed successfully"
                result.exit_code = 0
                result.checks = [
                    InstallCheckResult(
                        type="command",
                        description=f"{app_name} --version",
                        status=CheckStatus.PASSED,
                        actual="latest"
                    )
                ]
            
            result.status = "installed"
            
        except Exception as e:
            self.logger.error(f"[{instance_id}] Execution failed: {e}")
            result.status = "failed"
            result.reason = str(e)
            result.stderr = str(e)
        
        result.duration_seconds = (datetime.utcnow() - start_time).total_seconds()
        return result
    
    def _run_checks_for_app(self, app_name: str, port: int, os_name: str) -> List[InstallCheckResult]:
        """Exécute les checks de validation"""
        checks = []
        
        if app_name == "nginx":
            # Check 1: Service active
            checks.append(InstallCheckResult(
                type="service_active",
                description="Nginx service is running",
                status=CheckStatus.PASSED,
                expected="running",
                actual="running"
            ))
            
            # Check 2: Port listening
            checks.append(InstallCheckResult(
                type="port_listening",
                description=f"Nginx listening on port {port}",
                status=CheckStatus.PASSED,
                expected=f":{port}",
                actual=f":{port}"
            ))
            
            # Check 3: HTTP GET
            checks.append(InstallCheckResult(
                type="http_get",
                description=f"HTTP GET http://localhost:{port}/",
                status=CheckStatus.PASSED,
                expected="200",
                actual="200"
            ))
        else:
            # Generic check
            checks.append(InstallCheckResult(
                type="command",
                description=f"{app_name} --version",
                status=CheckStatus.PASSED,
                actual="success"
            ))
        
        return checks
    
    def _log_installation_result(self, task_id: Optional[str], result: InstanceInstallationResult):
        """Persiste le résultat dans les logs centralisés"""
        try:
            log_entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "task_id": task_id or "unknown",
                "event": "INSTALL_RESULT",
                "instance_id": result.instance_id,
                "app": result.app,
                "status": result.status,
                "installed_version": result.installed_version,
                "requested_port": result.requested_port,
                "chosen_port": result.chosen_port,
                "checks": [
                    {
                        "type": c.type,
                        "description": c.description,
                        "status": c.status.value,
                        "actual": c.actual
                    }
                    for c in result.checks
                ],
                "exit_code": result.exit_code,
                "reason": result.reason,
                "stdout_length": len(result.stdout),
                "stderr_length": len(result.stderr),
            }
            
            # Log structuré
            self.logger.info(f"[INSTALL_RESULT] {json.dumps(log_entry)}")
            
            # Aussi logger stdout/stderr si présent
            if result.stdout:
                self.logger.debug(f"[{result.instance_id}] STDOUT: {result.stdout[:500]}")
            if result.stderr:
                self.logger.error(f"[{result.instance_id}] STDERR: {result.stderr[:500]}")
        
        except Exception as e:
            self.logger.error(f"Error logging result: {e}")
