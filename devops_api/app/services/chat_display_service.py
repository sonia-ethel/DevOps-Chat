"""
Service de formatage des messages du chat pour tous les flows (création, configuration, audit)
Fournit des fonctions réutilisables pour afficher les étapes, résultats et erreurs
"""

import json
from typing import Dict, List, Optional, Any
from datetime import datetime


class ChatDisplayService:
    """Service centralisé pour le formatage des messages du chat"""

    # ========================================================================
    # CRÉATION D'INFRASTRUCTURE (TERRAFORM)
    # ========================================================================

    @staticmethod
    def format_infra_creation_start(instance_count: int, region: str = "", instance_type: str = "") -> str:
        """Affichage au lancement de la création d'infrastructure"""
        lines = [
            " **Création d'infrastructure Terraform en cours...**",
            f" Instances à créer: {instance_count}",
        ]
        if instance_type:
            lines.append(f"  Type d'instance: {instance_type}")
        if region:
            lines.append(f" Région: {region}")
        
        lines.extend([
            "",
            " Cela peut prendre **2-3 minutes** pour provisionner sur AWS...",
            " Le statut se met à jour automatiquement en temps réel",
        ])
        return "\n".join(lines)

    @staticmethod
    def format_infra_creation_complete(task_data: Dict[str, Any]) -> str:
        """Affichage des résultats finaux de création infrastructure"""
        lines = [" **Création d'infrastructure terminée !**", ""]
        
        # Résumé global
        if "result" in task_data:
            result = task_data["result"]
            if isinstance(result, dict):
                if "instances" in result:
                    instances = result.get("instances", [])
                    lines.append(f" **Instances créées:** {len(instances)}")
                    lines.append("")
                    
                    # Détails par instance
                    for inst in instances:
                        instance_id = inst.get("id", "N/A")
                        ip = inst.get("public_ip", "N/A")
                        state = inst.get("state", "N/A")
                        state_emoji = "" if state == "running" else ""
                        lines.append(f"  {state_emoji} **{instance_id}** | IP: {ip} | État: {state}")
                    lines.append("")
                    
                    lines.append(" **Informations de connexion:**")
                    lines.append("```")
                    lines.append("ssh -i /chemin/vers/key.pem ubuntu@<PUBLIC_IP>")
                    lines.append("```")
        
        lines.extend([
            "",
            " Prochaines étapes:",
            "• Configuration des services: `Installe nginx sur toutes les machines`",
            "• Audit de sécurité: `Lance un audit lynis`",
            "• Gestion des ressources: `liste des ressources`"
        ])
        return "\n".join(lines)

    @staticmethod
    def format_infra_creation_error(error_msg: str, phase: str = "") -> str:
        """Affichage d'erreur création infrastructure"""
        lines = [" **Erreur lors de la création d'infrastructure**", ""]
        if phase:
            lines.append(f" Phase: {phase}")
        lines.extend([
            f"  Détail: {error_msg[:200]}",
            "",
            " Suggestions:",
            "• Vérifiez vos credentials AWS",
            "• Vérifiez les quotas AWS (limites de ressources)",
            "• Réessayez avec `créer` ou modifiez les paramètres",
        ])
        return "\n".join(lines)

    # ========================================================================
    # CONFIGURATION (ANSIBLE)
    # ========================================================================

    @staticmethod
    def format_configure_start(instances: List[Dict], packages: List[str]) -> str:
        """Affichage au lancement de la configuration"""
        lines = [
            "  **Configuration en cours...**",
            f" Packages à installer: {', '.join(packages)}",
            f"  Instances à configurer: {len(instances)}",
            "",
            " Exécution via Ansible en cours...",
        ]
        for i, inst in enumerate(instances[:5], 1):  # Afficher max 5
            ip = inst.get("ip", "N/A")
            instance_id = inst.get("instance_id", "N/A")
            lines.append(f"  {i}. {instance_id} ({ip})")
        
        if len(instances) > 5:
            lines.append(f"  ... et {len(instances) - 5} autres")
        
        return "\n".join(lines)

    @staticmethod
    def format_configure_complete(results: Dict[str, Any]) -> str:
        """Affichage des résultats finaux de configuration"""
        lines = [" **Configuration terminée !**", ""]
        
        # Résumé global
        total = len(results.get("results_by_instance", {}))
        success = sum(1 for r in results.get("results_by_instance", {}).values() if r.get("status") == "success")
        failed = total - success
        
        lines.append(f" **Résultats:** {success}/{total} instances configurées avec succès")
        
        if failed > 0:
            lines.append(f"  {failed} instance(s) en erreur")
        
        lines.append("")
        lines.append(" **Détails par instance:**")
        
        for instance_id, result in results.get("results_by_instance", {}).items():
            status = result.get("status", "unknown")
            status_emoji = "" if status == "success" else ""
            
            lines.append(f"\n  {status_emoji} **{instance_id}**")
            
            if "packages_installed" in result:
                packages = result.get("packages_installed", [])
                for pkg in packages[:3]:
                    lines.append(f"     • {pkg.get('name', 'unknown')} v{pkg.get('version', 'N/A')}")
                if len(packages) > 3:
                    lines.append(f"     ... et {len(packages) - 3} autres packages")
            
            if "services_started" in result:
                services = result.get("services_started", [])
                if services:
                    lines.append(f"      Services démarrés: {', '.join(services[:3])}")
            
            if "error" in result and result["error"]:
                lines.append(f"       Erreur: {result['error'][:100]}")
        
        lines.extend([
            "",
            " Actions suivantes:",
            "• Vérifier les services: `Liste des ressources`",
            "• Faire un audit: `Lance un audit de sécurité`",
            "• Configurer plus: `Installe docker et compose`"
        ])
        
        return "\n".join(lines)

    @staticmethod
    def format_configure_error(error_msg: str, instance_id: str = "") -> str:
        """Affichage d'erreur configuration"""
        lines = [" **Erreur lors de la configuration**", ""]
        if instance_id:
            lines.append(f"  Instance: {instance_id}")
        lines.extend([
            f"  Détail: {error_msg[:200]}",
            "",
            " Suggestions:",
            "• Vérifiez la connectivité SSH aux instances",
            "• Vérifiez les credentials SSH",
            "• Vérifiez que les instances ont Ansible d'installé",
            "• Réessayez avec `lancer`",
        ])
        return "\n".join(lines)

    # ========================================================================
    # AUDIT (LYNIS / AUDITD / OSQUERY)
    # ========================================================================

    @staticmethod
    def format_audit_start(tool: str, instances: List[Dict]) -> str:
        """Affichage au lancement d'un audit"""
        tool_emoji = {
            "lynis": " ",
            "auditd": "",
            "osquery": "",
            "windows-auditpol": "",
        }.get(tool, "")
        
        lines = [
            f"{tool_emoji} **Audit de sécurité en cours** ({tool.upper()})",
            f"  Instances à auditer: {len(instances)}",
            "",
            " Collecte des données en cours...",
        ]
        
        for i, inst in enumerate(instances[:5], 1):
            ip = inst.get("ip", "N/A")
            instance_id = inst.get("instance_id", "N/A")
            lines.append(f"  {i}. {instance_id} ({ip})")
        
        if len(instances) > 5:
            lines.append(f"  ... et {len(instances) - 5} autres")
        
        return "\n".join(lines)

    @staticmethod
    def format_audit_complete(results: Dict[str, Any], tool: str = "lynis") -> str:
        """Affichage des résultats finaux d'audit"""
        tool_emoji = {
            "lynis": " ",
            "auditd": "",
            "osquery": "",
            "windows-auditpol": "",
        }.get(tool, "")
        
        lines = [
            f"{tool_emoji} **Audit de sécurité terminé !**",
            f"Outil: {tool.upper()}",
            ""
        ]
        
        # Résumé global
        total_instances = len(results.get("results_by_instance", {}))
        success_count = sum(1 for r in results.get("results_by_instance", {}).values() if r.get("status") == "success")
        
        lines.append(f" **Résultats:** {success_count}/{total_instances} instances auditées avec succès")
        lines.append("")
        
        # Détails par instance
        lines.append(" **Détails de sécurité par instance:**")
        
        for instance_id, result in results.get("results_by_instance", {}).items():
            status = result.get("status", "unknown")
            status_emoji = "" if status == "success" else ""
            
            lines.append(f"\n  {status_emoji} **{instance_id}**")
            
            # Afficher les issues de sécurité
            if "security_issues" in result:
                issues = result.get("security_issues", [])
                if issues:
                    lines.append(f"      Issues trouvées: {len(issues)}")
                    for issue in issues[:3]:
                        severity = issue.get("severity", "unknown").upper()
                        title = issue.get("title", "Unknown issue")
                        lines.append(f"        [{severity}] {title[:60]}")
                    if len(issues) > 3:
                        lines.append(f"        ... et {len(issues) - 3} autres issues")
                else:
                    lines.append("      Aucune issue critique détectée")
            
            # Statistiques d'audit
            if "audit_stats" in result:
                stats = result.get("audit_stats", {})
                if stats:
                    lines.append(f"      Statistiques:")
                    for stat_key, stat_value in stats.items():
                        lines.append(f"        • {stat_key}: {stat_value}")
            
            # Erreur si présente
            if "error" in result and result["error"]:
                lines.append(f"       Erreur: {result['error'][:80]}")
        
        lines.extend([
            "",
            " Analyse de sécurité:",
            "• Consultez le rapport complet pour plus de détails",
            "• Vérifiez les recommandations de sécurité",
            "",
            " Actions recommandées:",
            "• Corriger les issues critiques immédiatement",
            "• Mettre en place des patches de sécurité",
            "• Revoir les politiques d'accès",
        ])
        
        return "\n".join(lines)

    @staticmethod
    def format_audit_error(error_msg: str, instance_id: str = "", tool: str = "lynis") -> str:
        """Affichage d'erreur audit"""
        tool_emoji = {
            "lynis": " ",
            "auditd": "",
            "osquery": "",
            "windows-auditpol": "",
        }.get(tool, "")
        
        lines = [
            f" **Erreur lors de l'audit de sécurité** ({tool.upper()})",
            ""
        ]
        if instance_id:
            lines.append(f"  Instance: {instance_id}")
        
        lines.extend([
            f"  Détail: {error_msg[:200]}",
            "",
            " Suggestions:",
            f"• Vérifiez que {tool} est installé sur les instances",
            "• Vérifiez la connectivité SSH aux instances",
            "• Vérifiez les droits d'accès (sudo nécessaire)",
            "• Réessayez avec `lancer`",
        ])
        
        return "\n".join(lines)

    # ========================================================================
    # MÉTHODES GÉNÉRIQUES
    # ========================================================================

    @staticmethod
    def format_step_info(step: str, description: str, details: Optional[Dict] = None) -> str:
        """Affichage générique d'une étape"""
        lines = [f" **{step}**", f"   {description}"]
        
        if details:
            for key, value in details.items():
                if isinstance(value, (list, dict)):
                    lines.append(f"   • {key}: {json.dumps(value)[:80]}")
                else:
                    lines.append(f"   • {key}: {value}")
        
        return "\n".join(lines)

    @staticmethod
    def format_progress(current: int, total: int, phase: str = "") -> str:
        """Affichage de la progression"""
        percent = (current / total * 100) if total > 0 else 0
        bar_filled = int(percent / 5)  # 20 segments
        bar_empty = 20 - bar_filled
        bar = "" * bar_filled + "" * bar_empty
        
        lines = [
            f" **Progression: {percent:.0f}%** [{bar}]",
            f"   {current}/{total} étapes complétées"
        ]
        
        if phase:
            lines.insert(1, f"   Phase: {phase}")
        
        return "\n".join(lines)

    @staticmethod
    def format_confirmation_prompt(action: str, details: List[str]) -> str:
        """Affichage de demande de confirmation"""
        lines = [
            f"  **Confirmation requise pour {action}**",
            ""
        ]
        
        for detail in details:
            lines.append(f"  • {detail}")
        
        lines.extend([
            "",
            " Tapez `oui` pour continuer ou `annuler` pour abandonner"
        ])
        
        return "\n".join(lines)

    @staticmethod
    def format_success_summary(action: str, count: int, items: Optional[List[str]] = None) -> str:
        """Affichage de succès avec résumé"""
        lines = [f" **{action} réussi(s)** ({count})"]
        
        if items:
            for item in items[:10]:  # Max 10 items
                lines.append(f"    {item}")
            if len(items) > 10:
                lines.append(f"   ... et {len(items) - 10} autres")
        
        return "\n".join(lines)

    @staticmethod
    def format_error_summary(action: str, count: int, errors: Optional[List[str]] = None) -> str:
        """Affichage d'erreur avec résumé"""
        lines = [f" **{count} erreur(s) lors de {action}**"]
        
        if errors:
            for error in errors[:5]:  # Max 5 erreurs
                lines.append(f"     {error[:100]}")
            if len(errors) > 5:
                lines.append(f"   ... et {len(errors) - 5} autres erreurs")
        
        return "\n".join(lines)


# Instance globale pour accès facile
chat_display = ChatDisplayService()
