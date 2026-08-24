"""
Exécuteur SSM pour configure-only.

Permet d'exécuter des commandes shell sur des instances AWS via Systems Manager.
- Pas de clés SSH requises
- Pas de port 22 ouvert nécessaire
- Exécution sécurisée et auditée
"""
import logging
import boto3
import time
from typing import Dict, Tuple, List
from app.utils.crypto import decrypt_aws_secret

logger = logging.getLogger(__name__)


class SSMExecutor:
    """
    Exécute des commandes shell via AWS Systems Manager.
    """
    
    def __init__(self, aws_access_key: str, aws_secret_key: str, region: str = "eu-north-1"):
        """
        Initialise le client SSM.
        
        Args:
            aws_access_key: AWS Access Key ID
            aws_secret_key: AWS Secret Access Key (décrypté)
            region: Région AWS
        """
        self.ssm_client = boto3.client(
            'ssm',
            region_name=region,
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key
        )
        self.region = region
        logger.info(" SSM Executor initialisé (région: %s)", region)
    
    def execute_command(
        self,
        instance_ids: List[str],
        command: str,
        timeout: int = 300,
        poll_interval: int = 2
    ) -> Dict[str, Dict]:
        """
        Envoie une commande shell et attends le résultat.
        
        Args:
            instance_ids: Liste des IDs d'instances AWS
            command: Commande shell à exécuter (ex: "sudo apt update")
            timeout: Timeout total en secondes
            poll_interval: Intervalle de polling en secondes
            
        Returns:
            Dict avec résultats par instance:
            {
                "i-xxx": {
                    "status": "success|failed",
                    "command_id": "...",
                    "stdout": "...",
                    "stderr": "...",
                    "stdout_tail": "...",
                    "stderr_tail": "...",
                    "duration_seconds": 12.3
                },
                "i-yyy": {"status": "failed", "stderr": "..."}
            }
        """
        logger.info(" SSM execute_command: %d instances, cmd: %s", len(instance_ids), command[:50])
        
        # Envoyer la commande
        try:
            response = self.ssm_client.send_command(
                InstanceIds=instance_ids,
                DocumentName="AWS-RunShellScript",
                Parameters={"commands": [command]},
                TimeoutSeconds=timeout
            )
            command_id = response['Command']['CommandId']
            logger.info(" Commande envoyée: %s", command_id)
        except Exception as e:
            logger.error(" Erreur send_command: %s", e)
            return {iid: {"status": "Failed", "error": str(e)} for iid in instance_ids}
        
        # Attendre les résultats
        results = {}
        start_time = time.time()

        def _tail_lines(text: str, max_lines: int = 30) -> str:
            if not text:
                return ""
            lines = text.splitlines()
            if len(lines) <= max_lines:
                return text
            return "\n".join(lines[-max_lines:])

        def _normalize_status(raw_status: str) -> str:
            if raw_status == "Success":
                return "success"
            return "failed"
        
        while time.time() - start_time < timeout:
            all_done = True
            
            for instance_id in instance_ids:
                if instance_id in results:
                    continue  # Déjà traité
                
                try:
                    response = self.ssm_client.get_command_invocation(
                        CommandId=command_id,
                        InstanceId=instance_id
                    )
                    
                    status = response['Status']
                    
                    if status in ['Success', 'Failed', 'Cancelled', 'TimedOut', 'Cancelling']:
                        # Commande terminée
                        stdout_full = response.get('StandardOutputContent', '') or ""
                        stderr_full = response.get('StandardErrorContent', '') or ""
                        duration_seconds = response.get('ExecutionElapsedTime')
                        if duration_seconds is None:
                            duration_seconds = round(time.time() - start_time, 3)

                        results[instance_id] = {
                            "status": _normalize_status(status),
                            "command_id": command_id,
                            "stdout": stdout_full,
                            "stderr": stderr_full,
                            "stdout_tail": _tail_lines(stdout_full, 30),
                            "stderr_tail": _tail_lines(stderr_full, 30),
                            "duration_seconds": duration_seconds,
                        }
                        logger.info(" Instance %s: %s", instance_id, status)
                    else:
                        # Encore en cours (InProgress, Pending)
                        all_done = False
                except Exception as e:
                    logger.warning(" Erreur get_command_invocation pour %s: %s", instance_id, e)
                    all_done = False
            
            if all_done:
                logger.info(" Toutes les commandes terminées")
                break
            
            time.sleep(poll_interval)
        
        # Timeout
        if not all_done:
            for instance_id in instance_ids:
                if instance_id not in results:
                    results[instance_id] = {
                        "status": "failed",
                        "command_id": command_id,
                        "stdout": "",
                        "stderr": "",
                        "stdout_tail": "",
                        "stderr_tail": "",
                        "duration_seconds": round(time.time() - start_time, 3),
                        "error": f"Timeout après {timeout}s",
                    }
            logger.warning(" Timeout atteint pour certaines instances")
        
        return results


def execute_via_ssm(
    aws_access_key: str,
    aws_secret_key: str,
    instance_ids: List[str],
    command: str,
    region: str = "eu-north-1"
) -> Dict[str, Dict]:
    """
    Exécute une commande via SSM sur les instances spécifiées.
    
    Fonction de commodité pour l'intégration dans configure-only.
    
    Args:
        aws_access_key: AWS Access Key ID
        aws_secret_key: AWS Secret Access Key (décrypté)
        instance_ids: Liste des IDs d'instances
        command: Commande à exécuter
        region: Région AWS
        
    Returns:
        Dict des résultats par instance
    """
    executor = SSMExecutor(aws_access_key, aws_secret_key, region)
    return executor.execute_command(instance_ids, command)
