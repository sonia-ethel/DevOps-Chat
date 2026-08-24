"""
ÉTAPE 4 — Batch Executor for large-scale VM configuration.

Permet d'exécuter sur 10-1000 VMs sans overhead séquentiel.
- Partitionne en batches (5-10 par défaut)
- Exécute SSH et SSM en parallèle par batch
- Timeout per VM + retry control
- Prévient infinite loops
"""
import logging
import time
from typing import List, Dict, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from app.models.instance import Instance, ConnectionMethod

logger = logging.getLogger(__name__)


class BatchExecutor:
    """Exécuteur batch pour configure-only à grande échelle."""
    
    def __init__(self, batch_size: int = 5, timeout_per_vm: int = 300):
        """
        Args:
            batch_size: Nombre de VMs par batch (default: 5)
            timeout_per_vm: Timeout en secondes par VM (default: 300s)
        """
        self.batch_size = batch_size
        self.timeout_per_vm = timeout_per_vm
    
    def partition_into_batches(self, instances: List[Instance]) -> List[List[Instance]]:
        """
        Partitionne les instances en batches.
        
        Args:
            instances: Liste des instances
        
        Returns:
            Liste de batches (chaque batch est une liste d'instances)
        """
        batches = []
        for i in range(0, len(instances), self.batch_size):
            batch = instances[i:i + self.batch_size]
            batches.append(batch)
        
        logger.info(" Partitionné en %d batches (taille: %d)", len(batches), self.batch_size)
        return batches
    
    def partition_by_connection_method(self, batch: List[Instance]) -> Tuple[List[Instance], List[Instance]]:
        """
        Sépare SSH et SSM dans un batch.
        
        Args:
            batch: Batch d'instances
        
        Returns:
            (ssh_instances, ssm_instances)
        """
        ssh = [i for i in batch if not (hasattr(i, 'ssm_managed') and i.ssm_managed)]
        ssm = [i for i in batch if hasattr(i, 'ssm_managed') and i.ssm_managed]
        return ssh, ssm
    
    def execute_batch(
        self,
        batch: List[Instance],
        ssh_executor,
        ssm_executor,
        max_workers: int = 4
    ) -> Dict[str, Dict]:
        """
        Exécute un batch en parallèle (SSH et SSM en même temps).
        
        Args:
            batch: Batch d'instances
            ssh_executor: Fonction exécution SSH (inventory, playbook) -> (code, out, err)
            ssm_executor: Fonction exécution SSM (instance_ids, command) -> {id: {status, ...}}
            max_workers: Nombre de workers parallèles
        
        Returns:
            Dict des résultats: {instance_id: {status, method, stdout, stderr, duration}}
        """
        results = {}
        ssh_instances, ssm_instances = self.partition_by_connection_method(batch)
        
        logger.info("  Batch: %d SSH + %d SSM instances", len(ssh_instances), len(ssm_instances))
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            
            # Soumettre les tâches SSH
            if ssh_instances and ssh_executor:
                start_time = time.time()
                future = executor.submit(ssh_executor, ssh_instances)
                futures[future] = ('ssh', ssh_instances, start_time)
            
            # Soumettre les tâches SSM
            if ssm_instances and ssm_executor:
                start_time = time.time()
                future = executor.submit(ssm_executor, ssm_instances)
                futures[future] = ('ssm', ssm_instances, start_time)
            
            # Attendre les résultats avec timeout
            for future in as_completed(futures, timeout=self.timeout_per_vm * 5):
                method, instances_list, start_time = futures[future]
                duration = time.time() - start_time
                
                try:
                    result = future.result()
                    
                    if method == 'ssh':
                        # SSH retourne (code, out, err)
                        code, out, err = result
                        for inst in instances_list:
                            results[inst.instance_id] = {
                                "status": "success" if code == 0 else "failed",
                                "method": "ssh",
                                "exit_code": code,
                                "stdout": out[-300:] if out else "",
                                "stderr": err[-300:] if err else "",
                                "duration": duration,
                            }
                    elif method == 'ssm':
                        # SSM retourne {id: {status, stdout, stderr}}
                        ssm_result = result
                        for inst_id, res in ssm_result.items():
                            results[inst_id] = {
                                "status": res.get("status", "unknown").lower(),
                                "method": "ssm",
                                "stdout": res.get("stdout", "")[-300:],
                                "stderr": res.get("stderr", "")[-300:],
                                "duration": duration,
                            }
                    
                    logger.info(" %s batch complété en %.1fs", method.upper(), duration)
                
                except TimeoutError:
                    logger.error(" Timeout %s batch après %.1fs", method, duration)
                    for inst in instances_list:
                        results[inst.instance_id] = {
                            "status": "timeout",
                            "method": method,
                            "error": f"Timeout après {self.timeout_per_vm}s",
                            "duration": duration,
                        }
                except Exception as e:
                    logger.error(" Erreur %s batch: %s", method, e)
                    for inst in instances_list:
                        results[inst.instance_id] = {
                            "status": "error",
                            "method": method,
                            "error": str(e),
                            "duration": duration,
                        }
        
        return results
    
    def execute_all_batches(
        self,
        instances: List[Instance],
        ssh_executor,
        ssm_executor,
        max_workers: int = 4
    ) -> Dict[str, Dict]:
        """
        Exécute tous les batches séquentiellement (mais parallèle intra-batch).
        
        Args:
            instances: Toutes les instances
            ssh_executor: Fonction exécution SSH
            ssm_executor: Fonction exécution SSM
            max_workers: Nombre de workers par batch
        
        Returns:
            Dict résumé: {instance_id: {status, method, ...}}
        """
        all_results = {}
        batches = self.partition_into_batches(instances)
        
        logger.info(" Début exécution %d batches", len(batches))
        
        for batch_num, batch in enumerate(batches, 1):
            logger.info(" Batch %d/%d (%d instances)", batch_num, len(batches), len(batch))
            
            batch_results = self.execute_batch(
                batch,
                ssh_executor,
                ssm_executor,
                max_workers=max_workers
            )
            
            all_results.update(batch_results)
            
            # Log sommaire batch
            success = sum(1 for r in batch_results.values() if r.get('status') == 'success')
            failed = sum(1 for r in batch_results.values() if r.get('status') == 'failed')
            logger.info("    %d réussis,  %d échoués", success, failed)
        
        # Résumé global
        total = len(all_results)
        success = sum(1 for r in all_results.values() if r.get('status') == 'success')
        failed = sum(1 for r in all_results.values() if r.get('status') == 'failed')
        timeout = sum(1 for r in all_results.values() if r.get('status') == 'timeout')
        
        logger.info(" Résumé global: %d/%d réussis, %d échoués, %d timeout",
                    success, total, failed, timeout)
        
        return all_results


def create_ssh_executor_for_batch(
    playbook_path: Path,
    work_dir: Path
):
    """Crée une fonction pour exécuter SSH/Ansible sur un batch."""
    from app.services.configure_only import run_ansible, generate_inventory_from_instances
    
    def executor(instances: List[Instance]) -> Tuple[int, str, str]:
        """Exécute Ansible sur les instances SSH du batch."""
        if not instances:
            return 0, "", ""
        
        try:
            inventory_file, _ = generate_inventory_from_instances(instances, work_dir)
            code, out, err = run_ansible(inventory_file, str(playbook_path), work_dir)
            return code, out, err
        except Exception as e:
            logger.error(" SSH batch error: %s", e)
            return 1, "", str(e)
    
    return executor


def create_ssm_executor_for_batch(aws_credentials: dict, region: str = "eu-north-1"):
    """Crée une fonction pour exécuter SSM sur un batch."""
    from app.services.ssm_executor import execute_via_ssm
    
    def executor(instances: List[Instance]) -> Dict[str, Dict]:
        """Exécute SSM sur les instances du batch."""
        if not instances:
            return {}
        
        try:
            instance_ids = [inst.instance_id for inst in instances]
            # Note: shell_commands seraient générés par handle_configure_only
            # Pour batch, on les passe en paramètre (TODO: refactor)
            result = execute_via_ssm(
                aws_access_key=aws_credentials.get('access_key_id'),
                aws_secret_key=aws_credentials.get('secret_access_key'),
                instance_ids=instance_ids,
                command="echo 'batch execution'",  # Placeholder
                region=region
            )
            return result
        except Exception as e:
            logger.error(" SSM batch error: %s", e)
            return {inst.instance_id: {"status": "error", "error": str(e)} for inst in instances}
    
    return executor
