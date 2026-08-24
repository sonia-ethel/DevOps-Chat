"""
ÉTAPE 5 — Per-Instance Reporting for configure-only.

Génère des rapports détaillés par instance:
- Status (success/failed/timeout)
- Méthode utilisée (ssh/ssm)
- Stdout/stderr
- Durée
- Global status summary
"""
import logging
import json
from typing import Dict, List
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Génère les rapports pour configure-only."""
    
    @staticmethod
    def generate_per_instance_report(
        batch_results: Dict[str, Dict],
        instances_info: Dict[str, str] = None
    ) -> Dict:
        """
        Génère un rapport détaillé par instance.
        
        Args:
            batch_results: Résultats du batch executor {id: {status, method, ...}}
            instances_info: Info supplémentaire par instance {id: {name, provider, ...}}
        
        Returns:
            Dict avec rapport structuré
        """
        if instances_info is None:
            instances_info = {}
        
        per_instance = {}
        
        for instance_id, result in batch_results.items():
            info = instances_info.get(instance_id, {})
            
            per_instance[instance_id] = {
                "instance_id": instance_id,
                "name": info.get('name', 'unknown'),
                "status": result.get('status', 'unknown'),
                "method": result.get('method', 'unknown'),
                "exit_code": result.get('exit_code', -1),
                "stdout": result.get('stdout', ''),
                "stderr": result.get('stderr', ''),
                "duration_seconds": result.get('duration', 0),
                "error": result.get('error', ''),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        
        return per_instance
    
    @staticmethod
    def generate_summary_report(batch_results: Dict[str, Dict]) -> Dict:
        """
        Génère un résumé global d'exécution.
        
        Args:
            batch_results: Résultats du batch executor
        
        Returns:
            Dict avec résumé global
        """
        total = len(batch_results)
        success = sum(1 for r in batch_results.values() if r.get('status') == 'success')
        failed = sum(1 for r in batch_results.values() if r.get('status') == 'failed')
        timeout = sum(1 for r in batch_results.values() if r.get('status') == 'timeout')
        error = sum(1 for r in batch_results.values() if r.get('status') == 'error')
        
        success_rate = (success / total * 100) if total > 0 else 0
        
        # Agréger les méthodes utilisées
        ssh_count = sum(1 for r in batch_results.values() if r.get('method') == 'ssh')
        ssm_count = sum(1 for r in batch_results.values() if r.get('method') == 'ssm')
        
        # Statistiques de durée
        durations = [r.get('duration', 0) for r in batch_results.values()]
        min_duration = min(durations) if durations else 0
        max_duration = max(durations) if durations else 0
        avg_duration = sum(durations) / len(durations) if durations else 0
        total_duration = sum(durations)
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "total_instances": total,
            "succeeded": success,
            "failed": failed,
            "timeout": timeout,
            "error": error,
            "success_rate_percent": round(success_rate, 2),
            "methods": {
                "ssh": ssh_count,
                "ssm": ssm_count,
            },
            "duration": {
                "min_seconds": round(min_duration, 2),
                "max_seconds": round(max_duration, 2),
                "avg_seconds": round(avg_duration, 2),
                "total_seconds": round(total_duration, 2),
            },
            "status": "success" if failed == 0 and timeout == 0 else "partial_success" if success > 0 else "failed",
        }
    
    @staticmethod
    def save_report_to_file(
        report: Dict,
        output_dir: Path,
        report_name: str = "configure_only_report"
    ) -> Path:
        """
        Sauvegarde le rapport en JSON.
        
        Args:
            report: Rapport à sauvegarder
            output_dir: Répertoire de sortie
            report_name: Nom du rapport (sans extension)
        
        Returns:
            Chemin du fichier généré
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        
        report_file = output_dir / f"{report_name}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info(" Rapport sauvegardé: %s", report_file)
        
        return report_file
    
    @staticmethod
    def format_report_as_text(
        per_instance: Dict,
        summary: Dict
    ) -> str:
        """
        Formate le rapport en texte lisible.
        
        Args:
            per_instance: Rapport par instance
            summary: Résumé global
        
        Returns:
            String texte formaté
        """
        lines = []
        
        # En-tête
        lines.append("=" * 80)
        lines.append("CONFIGURE-ONLY EXECUTION REPORT")
        lines.append("=" * 80)
        lines.append("")
        
        # Résumé
        lines.append("SUMMARY")
        lines.append("-" * 80)
        lines.append(f"Timestamp:              {summary.get('timestamp', 'N/A')}")
        lines.append(f"Total Instances:        {summary.get('total_instances', 0)}")
        lines.append(f"Status:                 {summary.get('status', 'unknown').upper()}")
        lines.append(f"Success Rate:           {summary.get('success_rate_percent', 0)}%")
        lines.append("")
        lines.append(f"Succeeded:              {summary.get('succeeded', 0)}")
        lines.append(f"Failed:                 {summary.get('failed', 0)}")
        lines.append(f"Timeout:                {summary.get('timeout', 0)}")
        lines.append(f"Error:                  {summary.get('error', 0)}")
        lines.append("")
        lines.append(f"SSH Instances:          {summary.get('methods', {}).get('ssh', 0)}")
        lines.append(f"SSM Instances:          {summary.get('methods', {}).get('ssm', 0)}")
        lines.append("")
        
        # Durée
        duration = summary.get('duration', {})
        lines.append(f"Duration (min):         {duration.get('min_seconds', 0)}s")
        lines.append(f"Duration (max):         {duration.get('max_seconds', 0)}s")
        lines.append(f"Duration (avg):         {duration.get('avg_seconds', 0)}s")
        lines.append(f"Duration (total):       {duration.get('total_seconds', 0)}s")
        lines.append("")
        
        # Détails par instance
        lines.append("PER-INSTANCE DETAILS")
        lines.append("-" * 80)
        
        # Grouper par status
        by_status = {}
        for inst_id, inst_report in per_instance.items():
            status = inst_report.get('status', 'unknown')
            if status not in by_status:
                by_status[status] = []
            by_status[status].append(inst_report)
        
        for status in ['success', 'failed', 'timeout', 'error']:
            instances = by_status.get(status, [])
            if instances:
                lines.append(f"\n{status.upper()} ({len(instances)})")
                for inst in instances:
                    lines.append(f"  - {inst.get('instance_id')} ({inst.get('name')})")
                    lines.append(f"    Method: {inst.get('method')}, Duration: {inst.get('duration_seconds')}s")
                    if inst.get('error'):
                        lines.append(f"    Error: {inst.get('error')[:100]}")
        
        lines.append("")
        lines.append("=" * 80)
        
        return "\n".join(lines)


def generate_complete_report(
    batch_results: Dict[str, Dict],
    instances_info: Dict[str, str] = None,
    output_dir: Path = None,
    format_text: bool = True
) -> Dict:
    """
    Orchestrateur: génère rapport JSON + texte optionnel.
    
    Args:
        batch_results: Résultats du batch executor
        instances_info: Infos supplémentaires par instance
        output_dir: Répertoire de sauvegarde (optionnel)
        format_text: Générer aussi un rapport texte lisible
    
    Returns:
        Dict complet avec per_instance, summary, text_report (optionnel)
    """
    gen = ReportGenerator()
    
    per_instance = gen.generate_per_instance_report(batch_results, instances_info)
    summary = gen.generate_summary_report(batch_results)
    
    report = {
        "per_instance": per_instance,
        "summary": summary,
    }
    
    if format_text:
        text_report = gen.format_report_as_text(per_instance, summary)
        report["text_report"] = text_report
    
    if output_dir:
        gen.save_report_to_file(report, output_dir)
    
    return report
