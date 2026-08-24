"""
ÉTAPE 3 — Real Security Group Terraform for configure-only.

Implémente une seule action: ouvrir/fermer des ports sur un SG existant.
Idempotent via Terraform state management.
"""
import logging
import os
import subprocess
from pathlib import Path
from typing import List, Dict

logger = logging.getLogger(__name__)


def build_sg_terraform_config(
    sg_id: str,
    vpc_id: str,
    ports_to_open: List[int],
    protocol: str = "tcp",
    cidr_blocks: List[str] = None
) -> str:
    """
    Générer une configuration Terraform pour mettre à jour un SG.
    
    ONE case only: ajouter des règles ingress pour les ports spécifiés.
    Idempotent: Terraform gérera si les règles existent déjà.
    
    Args:
        sg_id: ID du security group existant (ex: sg-12345678)
        vpc_id: ID du VPC
        ports_to_open: Liste de ports à ouvrir (ex: [80, 443, 8000])
        protocol: Protocole TCP/UDP (defaut: tcp)
        cidr_blocks: CIDR blocks autorisés (defaut: 0.0.0.0/0)
    
    Returns:
        Contenu du fichier main.tf
    """
    if not cidr_blocks:
        cidr_blocks = ["0.0.0.0/0"]  # Par défaut, ouvert au monde
    
    cidr_list = ','.join([f'"{c}"' for c in cidr_blocks])
    port_rules = []
    
    # Générer une règle d'ingress par port
    for port in ports_to_open:
        rule = f"""
  # Port {port}/{protocol}
  ingress {{
    from_port   = {port}
    to_port     = {port}
    protocol    = "{protocol}"
    cidr_blocks = [{cidr_list}]
  }}"""
        port_rules.append(rule)
    
    # Configuration Terraform minimal
    tf_config = f"""
# ÉTAPE 3 — Security Group Update (Configure-Only)
# Scope: ONE case only - add ingress rules for specified ports
# Idempotent: Terraform will skip if rules already exist
# Generated: configure-only service

terraform {{
  required_providers {{
    aws = {{
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }}
  }}
}}

provider "aws" {{
  # Credentials injected via environment variables
  # AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
}}

# Référencer le SG existant (read-only)
data "aws_security_group" "existing" {{
  id = "{sg_id}"
}}

# Update: ajouter les règles ingress (idempotent)
resource "aws_security_group_rule" "allow_ports" {{
  for_each = {{"""

    for port in ports_to_open:
        tf_config += f'\n    "port_{port}" = {{\n      port = {port}\n    }}'
    
    tf_config += """
  }

  type              = "ingress"
  from_port         = each.value.port
  to_port           = each.value.port
  protocol          = "tcp"
  cidr_blocks       = [""" + cidr_list + """]
  security_group_id = data.aws_security_group.existing.id
}

# Output le SG mis à jour
output "security_group" {
  value = {
    id            = data.aws_security_group.existing.id
    name          = data.aws_security_group.existing.name
    vpc_id        = data.aws_security_group.existing.vpc_id
    ingress_rules = aws_security_group_rule.allow_ports
  }
}
"""
    
    return tf_config


def execute_sg_terraform(
    tf_dir: Path,
    aws_access_key: str,
    aws_secret_key: str,
    region: str = "eu-north-1"
) -> tuple[int, str, str]:
    """
    Exécute Terraform pour mettre à jour le SG.
    
    Args:
        tf_dir: Répertoire contenant main.tf
        aws_access_key: AWS Access Key
        aws_secret_key: AWS Secret Key
        region: Région AWS
    
    Returns:
        (exit_code, stdout, stderr)
    """
    logger.info(" [SG Terraform] Exécution pour %s", tf_dir)
    
    # Définir les variables d'environnement AWS
    env = os.environ.copy()
    env['AWS_ACCESS_KEY_ID'] = aws_access_key
    env['AWS_SECRET_ACCESS_KEY'] = aws_secret_key
    env['AWS_DEFAULT_REGION'] = region
    
    # terraform init
    for cmd in [
        ["terraform", "init"],
        ["terraform", "validate"],
        ["terraform", "plan", "-out=tfplan"],
        ["terraform", "apply", "-auto-approve", "tfplan"],
    ]:
        logger.debug("  -> %s", ' '.join(cmd))
        proc = subprocess.Popen(
            cmd,
            cwd=str(tf_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env
        )
        stdout, stderr = proc.communicate(timeout=300)
        
        if proc.returncode != 0:
            logger.error(" Terraform failed: %s", stderr)
            return proc.returncode, stdout, stderr
    
    logger.info(" [SG Terraform] Succès")
    return 0, "SG updated successfully", ""


def handle_sg_terraform(
    sg_id: str,
    vpc_id: str,
    ports_to_open: List[int],
    work_dir: Path,
    aws_access_key: str,
    aws_secret_key: str,
    region: str = "eu-north-1"
) -> dict:
    """
    Orchestrateur principal pour ÉTAPE 3.
    
    Générer + exécuter la config Terraform pour ouvrir des ports sur un SG.
    
    Args:
        sg_id: ID du security group
        vpc_id: ID du VPC
        ports_to_open: Ports à ouvrir
        work_dir: Répertoire de travail
        aws_access_key: AWS credentials
        aws_secret_key: AWS credentials
        region: Région AWS
    
    Returns:
        Dict avec résultats
    """
    if not sg_id or sg_id == "sg-default":
        return {
            "status": "skip",
            "reason": "No valid security_group_id found. Track SG IDs in Instance model.",
            "ports_requested": ports_to_open
        }
    
    tf_dir = work_dir / "terraform_sg"
    tf_dir.mkdir(parents=True, exist_ok=True)
    
    # Générer config
    tf_content = build_sg_terraform_config(sg_id, vpc_id, ports_to_open)
    (tf_dir / "main.tf").write_text(tf_content)
    logger.info(" Generated Terraform config at %s/main.tf", tf_dir)
    
    # Exécuter
    code, out, err = execute_sg_terraform(tf_dir, aws_access_key, aws_secret_key, region)
    
    return {
        "status": "completed" if code == 0 else "failed",
        "sg_id": sg_id,
        "vpc_id": vpc_id,
        "ports_opened": ports_to_open,
        "terraform_dir": str(tf_dir),
        "exit_code": code,
        "stdout": out[-500:] if out else "",
        "stderr": err[-500:] if err else "",
    }
