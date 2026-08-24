"""
P0.4 & P0.5 Chat Intent Handlers

Handlers pour les intents "vpc_check" (P0.4) et "create_infrastructure" (P0.5)
Intégrés dans le flow chat pour permettre aux utilisateurs d':
  - P0.4: Vérifier le statut de leur VPC/subnets
  - P0.5: Créer de l'infrastructure de base (VPC, instances, etc.)
"""

import logging
import json
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


def detect_vpc_check_intent(text: str) -> bool:
    """
    Détecte si l'utilisateur demande une vérification VPC.
    
    Exemples:
    - "Vérifier mon VPC"
    - "Quel est l'état de mon VPC ?"
    - "Check my VPC health"
    - "Santé VPC"
    """
    vpc_keywords = [
        "vpc", "réseau", "network", "subnet", "santé", "health",
        "état", "status", "vérif", "check", "diag", "diagnostic",
        "infrastructure", "disponibil", "availability"
    ]
    
    text_lower = text.lower()
    matching_keywords = sum(1 for kw in vpc_keywords if kw in text_lower)
    return matching_keywords >= 2


def detect_create_infrastructure_intent(text: str) -> bool:
    """
    Détecte si l'utilisateur demande de créer de l'infrastructure.
    
    Exemples:
    - "Crée-moi 2 instances Ubuntu"
    - "Create infrastructure with 3 instances"
    - "Créer mon infrastructure de base"
    - "Mettre en place des VMs"
    """
    create_keywords = [
        "créer", "create", "crée", "setup", "mettre en place",
        "lancer", "launch", "boot", "provision", "construire"
    ]
    
    resource_keywords = [
        "instance", "vm", "serveur", "server", "infrastructure",
        "vpc", "subnet", "réseau", "machine", "resource"
    ]
    
    text_lower = text.lower()
    has_create = any(kw in text_lower for kw in create_keywords)
    has_resource = any(kw in text_lower for kw in resource_keywords)
    
    return has_create and has_resource


def detect_ssm_check_intent(text: str) -> bool:
    """
    Détecte si l'utilisateur demande une vérification SSM.
    
    Exemples:
    - "Vérifie si SSM est opérationnel"
    - "Check SSM status"
    - "Est-ce que SSM fonctionne ?"
    - "Vérifier SSM sur mes VM"
    """
    ssm_keywords = ["ssm", "systems manager", "agent"]
    check_keywords = ["vérif", "check", "test", "status", "état", "opérationnel", "fonctionne"]
    
    text_lower = text.lower()
    has_ssm = any(kw in text_lower for kw in ssm_keywords)
    has_check = any(kw in text_lower for kw in check_keywords)
    
    return has_ssm and has_check


def extract_create_infra_params(text: str) -> Dict[str, Any]:
    """
    Extrait les paramètres pour créer l'infrastructure.
    
    Returns:
        {
            "instance_count": int (default 1),
            "instance_type": str (default "t3.micro"),
            "ubuntu_version": str (default "22.04"),
            "region": str (default "eu-north-1")
        }
    """
    text_lower = text.lower()
    params = {
        "instance_count": 1,
        "instance_type": "t3.micro",
        "ubuntu_version": "22.04",
        "region": "eu-north-1"
    }
    
    # Extract instance count
    import re
    count_match = re.search(r'(\d+)\s+(instance|vm|serveur|machine)', text_lower)
    if count_match:
        count = int(count_match.group(1))
        if 1 <= count <= 5:
            params["instance_count"] = count
    
    # Extract Ubuntu version
    if "24.04" in text or "noble" in text_lower:
        params["ubuntu_version"] = "24.04"
    elif "20.04" in text or "focal" in text_lower:
        params["ubuntu_version"] = "20.04"
    # Default to 22.04
    
    # Extract instance type
    if "t3.small" in text or "small" in text_lower:
        params["instance_type"] = "t3.small"
    elif "t3.medium" in text or "medium" in text_lower:
        params["instance_type"] = "t3.medium"
    elif "t3.large" in text or "large" in text_lower:
        params["instance_type"] = "t3.large"
    # Default to t3.micro
    
    # Extract region
    if "eu-west" in text_lower or "ireland" in text_lower:
        params["region"] = "eu-west-1"
    elif "us-east" in text_lower or "virginia" in text_lower:
        params["region"] = "us-east-1"
    elif "us-west" in text_lower or "california" in text_lower:
        params["region"] = "us-west-2"
    # Default to eu-north-1
    
    return params


def format_vpc_status_response(diagnostics: Dict[str, Any]) -> str:
    """
    Formate la réponse de diagnostic VPC pour affichage en chat.
    """
    if diagnostics.get("status") == "error":
        return f"[Error] VPC: {diagnostics.get('summary', 'Erreur inconnue')}"
    
    summary = diagnostics.get("summary", "")
    
    # Format VPC list
    vpcs_info = []
    for vpc in diagnostics.get("vpcs", []):
        vpc_id = vpc.get("vpc_id", "unknown")
        subnet_count = vpc.get("total_subnets", 0)
        is_dac = "[DAC]" if vpc.get("dac_managed") else "[Non-DAC]"
        vpcs_info.append(f"  • {vpc_id}: {subnet_count} subnets [{is_dac}]")
    
    vpcs_text = "\n".join(vpcs_info) if vpcs_info else "  Aucun VPC trouvé"
    
    warnings_text = ""
    if diagnostics.get("warnings"):
        warnings_text = "\n[Warnings:]\n" + "\n".join(
            f"  {w}" for w in diagnostics["warnings"]
        )
    
    return f"""{summary}

 **VPCs disponibles:**
{vpcs_text}
{warnings_text}

 Tu peux maintenant créer des instances avec: "Crée-moi X instances Ubuntu"
"""


def format_infra_creation_response(creation_result: Dict[str, Any]) -> str:
    """
    Formate la réponse de création d'infrastructure pour affichage en chat.
    """
    if creation_result.get("status") == "error":
        return f"[Error] creation: {creation_result.get('summary', 'Erreur inconnue')}"
    
    vpc = creation_result.get("vpc", {})
    instances = creation_result.get("instances", [])
    subnets = creation_result.get("subnets", [])
    
    # Format instances list
    instances_text = ""
    for inst in instances:
        instance_id = inst.get("instance_id", "unknown")
        private_ip = inst.get("private_ip", "N/A")
        state = inst.get("state", "pending")
        instances_text += f"    • {instance_id}: {private_ip} [{state}]\n"
    
    subnets_text = "\n".join(
        f"    • {s.get('subnet_id')}: {s.get('cidr')} ({s.get('az')})"
        for s in subnets
    )
    
    summary = creation_result.get("summary", "Infrastructure créée")
    
    return f"""{summary}

 **Infrastructure créée:**
  • VPC: {vpc.get('vpc_id')} ({vpc.get('cidr')})
  • Subnets:
{subnets_text}

[Instances:]
{instances_text}

[Next Steps:]
  1. Attendre le démarrage complet (1-2 minutes)
  2. Vérifier SSM avec: "Vérifie SSM"
  3. Configurer avec: "Configure NGINX sur mes instances"
"""


# ============================================================================
#  Fonctions helper pour intégration au chat flow
# ============================================================================

def should_handle_vpc_check(detected_intent: str, text: str) -> bool:
    """Détermine si ce message doit être traité comme vpc_check."""
    return detected_intent == "vpc_check" or detect_vpc_check_intent(text)


def should_handle_create_infra(detected_intent: str, text: str) -> bool:
    """Détermine si ce message doit être traité comme create_infrastructure."""
    return detected_intent == "create_infrastructure" or detect_create_infrastructure_intent(text)
