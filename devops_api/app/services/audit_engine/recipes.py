"""
Audit Engine - Recipes
Définit les recettes d'audit (commandes + parsing)
"""
from typing import Dict, List, Any
import re


class AuditRecipe:
    """Recette d'audit"""
    
    def __init__(
        self,
        name: str,
        description: str,
        checks: List[str],
        commands: Dict[str, str],
        parser_func: callable = None
    ):
        self.name = name
        self.description = description
        self.checks = checks
        self.commands = commands
        self.parser_func = parser_func or self._default_parser
    
    def _default_parser(self, outputs: Dict[str, str], os_type: str) -> Dict[str, Any]:
        """Parser par défaut - retourne juste les outputs bruts"""
        return {
            "raw_outputs": outputs,
            "findings": [],
            "metrics": {}
        }


# Recipe: OPS_HEALTH - Santé de la machine
def parse_ops_health(outputs: Dict[str, str], os_type: str) -> Dict[str, Any]:
    """Parse les résultats de l'audit ops_health"""
    findings = []
    metrics = {}
    
    # Parse CPU/Memory/Disk
    if "cpu_mem" in outputs:
        cpu_output = outputs["cpu_mem"]
        # Extraction simple du CPU usage (ligne idle)
        cpu_match = re.search(r'%Cpu.*?(\d+\.\d+)\s*id', cpu_output)
        if cpu_match:
            idle = float(cpu_match.group(1))
            cpu_used = 100 - idle
            metrics["cpu_percent"] = round(cpu_used, 1)
            
            if cpu_used > 90:
                findings.append({
                    "severity": "high",
                    "title": f"CPU usage très élevé ({cpu_used:.1f}%)",
                    "recommendation": "Investiguer les processus consommateurs"
                })
    
    # Parse Memory
    if "memory" in outputs:
        mem_output = outputs["memory"]
        # Format: total used free
        mem_match = re.search(r'Mem:\s+(\d+)\s+(\d+)\s+(\d+)', mem_output)
        if mem_match:
            total = int(mem_match.group(1))
            used = int(mem_match.group(2))
            if total > 0:
                mem_percent = (used / total) * 100
                metrics["mem_used_percent"] = round(mem_percent, 1)
                
                if mem_percent > 90:
                    findings.append({
                        "severity": "medium",
                        "title": f"Mémoire usage élevé ({mem_percent:.1f}%)",
                        "recommendation": "Vérifier les processus mémoire"
                    })
    
    # Parse Disk
    if "disk" in outputs:
        disk_output = outputs["disk"]
        # Format df: Filesystem Size Used Avail Use% Mounted
        for line in disk_output.split('\n'):
            if '/' in line and line.strip().endswith('/'):
                parts = line.split()
                if len(parts) >= 5:
                    use_str = parts[4].replace('%', '')
                    if use_str.isdigit():
                        disk_percent = int(use_str)
                        metrics["disk_used_percent"] = disk_percent
                        
                        if disk_percent > 90:
                            findings.append({
                                "severity": "high",
                                "title": f"Disque presque plein ({disk_percent}%)",
                                "recommendation": "Libérer de l'espace disque"
                            })
                        elif disk_percent > 80:
                            findings.append({
                                "severity": "medium",
                                "title": f"Disque usage élevé ({disk_percent}%)",
                                "recommendation": "Surveiller l'espace disque"
                            })
    
    # Check failed services
    if "failed_services" in outputs:
        failed = outputs["failed_services"].strip()
        if failed and "No" not in failed:
            findings.append({
                "severity": "high",
                "title": "Services en échec détectés",
                "description": failed[:200],
                "recommendation": "Vérifier avec 'systemctl status <service>'"
            })
    
    # Check open ports
    if "open_ports" in outputs:
        ports_output = outputs["open_ports"]
        port_count = len([line for line in ports_output.split('\n') if 'LISTEN' in line])
        metrics["open_ports_count"] = port_count
        
        if port_count > 20:
            findings.append({
                "severity": "low",
                "title": f"Nombreux ports ouverts ({port_count})",
                "recommendation": "Vérifier les services exposés"
            })
    
    # Check reboot required
    if "reboot_required" in outputs:
        if "reboot" in outputs["reboot_required"].lower():
            findings.append({
                "severity": "medium",
                "title": "Redémarrage système requis",
                "recommendation": "Planifier un reboot de maintenance"
            })
    
    return {
        "findings": findings,
        "metrics": metrics
    }


OPS_HEALTH_RECIPE = AuditRecipe(
    name="ops_health",
    description="Santé opérationnelle de la machine",
    checks=[
        "CPU/Memory/Disk usage",
        "Services en échec",
        "Ports ouverts",
        "Reboot requis"
    ],
    commands={
        "cpu_mem": "top -bn1 | head -20",
        "memory": "free -m",
        "disk": "df -h /",
        "load": "cat /proc/loadavg",
        "failed_services": "systemctl --failed --no-pager || echo 'No systemd'",
        "open_ports": "ss -lntup 2>/dev/null || netstat -lntup 2>/dev/null || echo 'No ss/netstat'",
        "reboot_required": "[ -f /var/run/reboot-required ] && echo 'Reboot required' || echo 'No reboot needed'"
    },
    parser_func=parse_ops_health
)


# Recipe: SECURITY_BASIC - Hygiène sécurité
def parse_security_basic(outputs: Dict[str, str], os_type: str) -> Dict[str, Any]:
    """Parse les résultats de l'audit security_basic"""
    findings = []
    metrics = {}
    
    # Check SSH config
    if "sshd_config" in outputs:
        ssh_config = outputs["sshd_config"]
        
        if "PermitRootLogin yes" in ssh_config or "PermitRootLogin without-password" not in ssh_config:
            if "PermitRootLogin yes" in ssh_config:
                findings.append({
                    "severity": "critical",
                    "title": "SSH root login activé",
                    "description": "PermitRootLogin yes trouvé dans sshd_config",
                    "recommendation": "Mettre PermitRootLogin à 'no' ou 'without-password'"
                })
        
        if "PasswordAuthentication yes" in ssh_config:
            findings.append({
                "severity": "high",
                "title": "Authentification SSH par mot de passe activée",
                "description": "PasswordAuthentication yes",
                "recommendation": "Privilégier l'authentification par clé SSH uniquement"
            })
    
    # Check firewall
    if "firewall_status" in outputs:
        fw_output = outputs["firewall_status"]
        
        if "inactive" in fw_output.lower() or "not running" in fw_output.lower():
            findings.append({
                "severity": "critical",
                "title": "Firewall désactivé",
                "description": "Aucun firewall actif détecté",
                "recommendation": "Activer ufw, iptables ou firewalld"
            })
        elif "active" in fw_output.lower():
            metrics["firewall_enabled"] = True
        else:
            findings.append({
                "severity": "medium",
                "title": "Status firewall inconnu",
                "recommendation": "Vérifier manuellement la configuration firewall"
            })
    
    # Check sudo users
    if "sudo_users" in outputs:
        sudo_output = outputs["sudo_users"]
        sudo_count = len([line for line in sudo_output.split('\n') if line.strip() and not line.startswith('#')])
        metrics["sudo_users_count"] = sudo_count
        
        if sudo_count > 5:
            findings.append({
                "severity": "medium",
                "title": f"Nombreux utilisateurs sudo ({sudo_count})",
                "recommendation": "Vérifier les accès sudo sont justifiés"
            })
    
    # Check open ports (security perspective)
    if "open_ports_detailed" in outputs:
        ports_output = outputs["open_ports_detailed"]
        
        # Check for common risky ports
        risky_ports = {
            "23": "Telnet (non sécurisé)",
            "21": "FTP (non sécurisé)",
            "3389": "RDP",
            "5432": "PostgreSQL (exposé)",
            "3306": "MySQL (exposé)",
            "27017": "MongoDB (exposé)"
        }
        
        for port, service in risky_ports.items():
            if f":{port}" in ports_output or f" {port} " in ports_output:
                findings.append({
                    "severity": "high",
                    "title": f"Port {port} ouvert - {service}",
                    "recommendation": f"Fermer le port {port} ou restreindre l'accès"
                })
    
    return {
        "findings": findings,
        "metrics": metrics
    }


SECURITY_BASIC_RECIPE = AuditRecipe(
    name="security_basic",
    description="Hygiène de sécurité basique",
    checks=[
        "Configuration SSH (root login, passwords)",
        "Status firewall",
        "Utilisateurs sudo",
        "Ports ouverts sensibles"
    ],
    commands={
        "sshd_config": "grep -E '(PermitRootLogin|PasswordAuthentication)' /etc/ssh/sshd_config 2>/dev/null || echo 'Cannot read sshd_config'",
        "firewall_status": "ufw status 2>/dev/null || systemctl status firewalld 2>/dev/null || iptables -L -n 2>/dev/null | head -5 || echo 'No firewall detected'",
        "sudo_users": "grep -E '^%sudo|^%wheel' /etc/sudoers 2>/dev/null; grep -E '^[^#].*ALL=\\(ALL\\)' /etc/sudoers 2>/dev/null || echo 'Cannot read sudoers'",
        "open_ports_detailed": "ss -lntup 2>/dev/null || netstat -lntup 2>/dev/null || echo 'No ss/netstat'"
    },
    parser_func=parse_security_basic
)


def parse_lynis(outputs: Dict[str, str], os_type: str) -> Dict[str, Any]:
    """Parse un audit Lynis si l'outil est déjà présent sur la VM."""
    findings = []
    metrics = {}
    output = outputs.get("lynis_audit", "")

    if "LYNIS_NOT_INSTALLED" in output:
        findings.append({
            "severity": "medium",
            "title": "Lynis n'est pas installé",
            "description": "Installez lynis sur la VM puis relancez l'audit.",
            "recommendation": "Installer lynis via apt/dnf/yum selon la distribution."
        })
        return {"findings": findings, "metrics": metrics}

    index_match = re.search(r"Hardening index\s*:\s*(\d+)", output, re.IGNORECASE)
    if index_match:
        hardening_index = int(index_match.group(1))
        metrics["hardening_index"] = hardening_index
        if hardening_index < 60:
            findings.append({
                "severity": "high",
                "title": f"Hardening index Lynis faible ({hardening_index})",
                "recommendation": "Analyser les recommandations Lynis et durcir la configuration."
            })

    warning_count = len(re.findall(r"\[WARNING\]", output))
    if warning_count:
        findings.append({
            "severity": "medium",
            "title": f"{warning_count} avertissement(s) Lynis détecté(s)",
            "recommendation": "Consulter le rapport Lynis complet dans les détails d'audit."
        })

    return {"findings": findings, "metrics": metrics}


LYNIS_RECIPE = AuditRecipe(
    name="lynis",
    description="Audit de sécurité Lynis",
    checks=["Lynis audit system", "Hardening index", "Warnings"],
    commands={
        "lynis_audit": "if command -v lynis >/dev/null 2>&1; then sudo lynis audit system --quick --no-colors 2>&1 || true; else echo 'LYNIS_NOT_INSTALLED'; fi"
    },
    parser_func=parse_lynis
)


# Registry de toutes les recipes
AUDIT_RECIPES = {
    "ops_health": OPS_HEALTH_RECIPE,
    "security_basic": SECURITY_BASIC_RECIPE,
    "lynis": LYNIS_RECIPE,
}


def get_audit_recipe(audit_type: str) -> AuditRecipe:
    """Récupère une recipe par nom"""
    return AUDIT_RECIPES.get(audit_type)
