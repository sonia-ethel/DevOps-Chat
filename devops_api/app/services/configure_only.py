import os
import subprocess
import json
import re
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple, Dict

import boto3

from sqlalchemy.orm import Session

from app.models.instance import Instance
from app.models.session import Session as DbSession
from app.services.aws_credentials_service import get_user_aws_credentials
from app.services.task_router import route_config_request
from app.services.os_aware_commands import build_os_aware_commands
from app.utils.crypto import decrypt

logger = logging.getLogger(__name__)

SSM_BLOCK_MESSAGE = (
    "SSM-first mode activé\n"
    "DAC exécute les actions système via AWS Systems Manager (SSM) afin d’éviter SSH et les clés privées.\n\n"
    "Aucune instance SSM Online n’a été détectée.\n\n"
    "Pour rendre une VM gérable :\n"
    "attachez un rôle IAM AmazonSSMManagedInstanceCore\n"
    "assurez la connectivité SSM (NAT ou VPC Endpoints)\n"
    "Puis relancez la synchronisation."
)


def build_nginx_ssm_script(listen_port: int) -> str:
        """Build a bash script to install nginx, switch listen port, and emit JSON result with marker."""
        return f"""set -e

PORT={listen_port}
SERVICE_NAME="nginx"  # Default service name for nginx

if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y
    apt-get install -y nginx
elif command -v yum >/dev/null 2>&1; then
    yum install -y nginx
else
    echo "NO_PACKAGE_MANAGER"
    exit 1
fi

# Ajuster le port d'écoute
if [ -f /etc/nginx/sites-available/default ]; then
    sed -i "s/listen 80 default_server;/listen $PORT default_server;/g" /etc/nginx/sites-available/default || true
    sed -i "s/listen \\[::\\]:80 default_server;/listen [::]:$PORT default_server;/g" /etc/nginx/sites-available/default || true
else
    cat > /etc/nginx/conf.d/dac-default.conf <<EOF
server {{
        listen $PORT default_server;
        listen [::]:$PORT default_server;
        root /usr/share/nginx/html;
        index index.html;
}}
EOF
fi

# Ouvrir le port local si possible
if command -v ufw >/dev/null 2>&1; then
    ufw allow $PORT/tcp || true
elif command -v firewall-cmd >/dev/null 2>&1; then
    firewall-cmd --permanent --add-port=$PORT/tcp || true
    firewall-cmd --reload || true
fi

systemctl enable --now "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

# Collecter les données de vérification
NGINX_VERSION=$(nginx -v 2>&1)
SERVICE_STATUS=$(systemctl is-active "$SERVICE_NAME" 2>/dev/null || echo "unknown")
LISTEN_RAW=$(ss -lntp | grep ":$PORT" | head -n 1 || echo "not_listening")

# Logs lisibles pour debugging (envoyés sur stdout pour visibilité)
echo "Installation nginx terminée"
echo "Version: $NGINX_VERSION"
echo "Service $SERVICE_NAME: $SERVICE_STATUS"
echo "Port $PORT: $LISTEN_RAW"

# JSON structuré avec marqueur DAC_RESULT_JSON:
if [ "$SERVICE_STATUS" = "active" ] && echo "$LISTEN_RAW" | grep -q ":$PORT"; then
    STATUS=\"success\"
else
    STATUS=\"failed\"
fi

DAC_RESULT_JSON: {{\"status\":\"$STATUS\",\"app\":\"nginx\",\"installed_version\":\"$NGINX_VERSION\",\"service_name\":\"$SERVICE_NAME\",\"service_status\":\"$SERVICE_STATUS\",\"requested_port\":$PORT,\"chosen_port\":$PORT,\"checks\":{{\"service_active\":$([ \"$SERVICE_STATUS\" = \"active\" ] && echo true || echo false),\"port_listening\":$(echo \"$LISTEN_RAW\" | grep -q \":$PORT\" && echo true || echo false)}}}}
"""


def build_apache_ssm_script(listen_port: int) -> str:
        """Build a bash script to install Apache, switch listen port, and emit JSON result with marker.
        Handles OS differences: apache2 (Debian/Ubuntu) vs httpd (RHEL/Amazon Linux)."""
        return f"""set -e

PORT={listen_port}

# Detect OS to determine package and service names
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS_ID="$ID"
else
    OS_ID="unknown"
fi

# Install Apache with OS-specific package name
if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y
    apt-get install -y apache2
    PKG_NAME="apache2"
    SERVICE_NAME="apache2"
elif command -v yum >/dev/null 2>&1; then
    yum install -y httpd
    PKG_NAME="httpd"
    SERVICE_NAME="httpd"
else
    echo "NO_PACKAGE_MANAGER"
    exit 1
fi

echo "Detected OS: $OS_ID, Package: $PKG_NAME, Service: $SERVICE_NAME"

# Ajuster le port d'écoute selon la distribution
if [ "$OS_ID" = "ubuntu" ] || [ "$OS_ID" = "debian" ]; then
    # Debian/Ubuntu: /etc/apache2/ports.conf
    if [ -f /etc/apache2/ports.conf ]; then
        sed -i "s/Listen 80/Listen $PORT/" /etc/apache2/ports.conf 2>/dev/null || true
    fi
    # Also update default vhost
    if [ -f /etc/apache2/sites-available/000-default.conf ]; then
        sed -i "s/<VirtualHost \\*:80>/<VirtualHost *:$PORT>/" /etc/apache2/sites-available/000-default.conf || true
    fi
else
    # RHEL/Amazon Linux: /etc/httpd/conf/httpd.conf
    if [ -f /etc/httpd/conf/httpd.conf ]; then
        sed -i "s/Listen 80/Listen $PORT/" /etc/httpd/conf/httpd.conf 2>/dev/null || true
    fi
fi

# Ouvrir le port local si possible
if command -v ufw >/dev/null 2>&1; then
    ufw allow $PORT/tcp || true
elif command -v firewall-cmd >/dev/null 2>&1; then
    firewall-cmd --permanent --add-port=$PORT/tcp || true
    firewall-cmd --reload || true
fi

# Enable and start service using the correct service name
systemctl enable --now "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

# Collecter les données de vérification
if [ "$SERVICE_NAME" = "apache2" ]; then
    APACHE_VERSION=$(apache2 -v 2>&1 | head -n1 || echo "unknown")
else
    APACHE_VERSION=$(httpd -v 2>&1 | head -n1 || echo "unknown")
fi

SERVICE_STATUS=$(systemctl is-active "$SERVICE_NAME" 2>/dev/null || echo "unknown")
LISTEN_RAW=$(ss -lntp | grep ":$PORT" | head -n 1 || echo "not_listening")

# Logs lisibles pour debugging (envoyés sur stdout pour visibilité)
echo "Installation Apache terminée"
echo "Package: $PKG_NAME"
echo "Service: $SERVICE_NAME"
echo "Version: $APACHE_VERSION"
echo "Service status: $SERVICE_STATUS"
echo "Port $PORT: $LISTEN_RAW"

# JSON structuré avec marqueur DAC_RESULT_JSON:
if [ "$SERVICE_STATUS" = "active" ] && echo "$LISTEN_RAW" | grep -q ":$PORT"; then
    STATUS=\"success\"
else
    STATUS=\"failed\"
fi

DAC_RESULT_JSON: {{\"status\":\"$STATUS\",\"app\":\"apache\",\"installed_version\":\"$APACHE_VERSION\",\"service_name\":\"$SERVICE_NAME\",\"service_status\":\"$SERVICE_STATUS\",\"requested_port\":$PORT,\"chosen_port\":$PORT,\"checks\":{{\"service_active\":$([ \"$SERVICE_STATUS\" = \"active\" ] && echo true || echo false),\"port_listening\":$(echo \"$LISTEN_RAW\" | grep -q \":$PORT\" && echo true || echo false)}}}}
"""


def validate_ssm_success(stdout: str, stderr: str) -> Tuple[bool, str]:
    """
    Valide que SSM a réellement exécuté quelque chose (ultra-critique).
    
    Retourne (is_valid, error_reason).
    """
    # Critères d'invalidation
    if not stdout or not stdout.strip():
        return False, "SSM Success mais stdout VIDE - script probable non exécuté"
    
    # Si stdout est < 20 chars et aucune sortie substantielle
    if len(stdout.strip()) < 20:
        return False, f"SSM Success mais sortie très courte ({len(stdout)} chars) - probable script vide"
    
    # Si on a des marqueurs DAC, au moins un doit être présent
    has_dac_markers = "__DAC_PROOF_" in stdout
    
    # Critères de validité
    valid_indicators = [
        "__DAC_PROOF_" in stdout,  # Marqueurs DAC
        "systemctl" in stdout.lower(),  # Service management
        "service" in stdout.lower(),
        "running" in stdout.lower(),
        "active" in stdout.lower(),
        "installed" in stdout.lower(),
        "install" in stdout.lower(),
        "configured" in stdout.lower(),
        "port" in stdout.lower() and any(c.isdigit() for c in stdout),
    ]
    
    if not any(valid_indicators):
        return False, f"SSM Success mais stdout ne contient aucun indicateur d'action ({len(stdout)} chars de logs génériques)"
    
    return True, ""


def parse_proof_output(stdout: str, listen_port: int) -> Dict[str, str | bool]:
        """Parse SSM stdout to extract result - try JSON first, fallback to markers."""
        # Essayer d'abord le JSON structuré avec marqueur DAC_RESULT_JSON:
        if stdout:
            lines = stdout.strip().split('\n')
            for line in reversed(lines):
                line = line.strip()
                if line.startswith('DAC_RESULT_JSON:'):
                    json_str = line[len('DAC_RESULT_JSON:'):].strip()
                    try:
                        data = json.loads(json_str)
                        # Convertir au format attendu
                        checks = data.get("checks", {})
                        return {
                            "nginx_version": data.get("installed_version"),
                            "service_status": data.get("service_status"),
                            "listen_check": f":{data.get('chosen_port')}",
                            "listen_port": listen_port,
                            "ok": data.get("status") == "success" and checks.get("service_active") and checks.get("port_listening"),
                        }
                    except json.JSONDecodeError:
                        pass
        
        # Fallback: anciens marqueurs __DAC_PROOF_*
        proof = {
                "nginx_version": None,
                "service_status": None,
                "listen_check": None,
                "listen_port": listen_port,
        }

        for line in (stdout or "").splitlines():
                if line.startswith("__DAC_PROOF_NGINX_VERSION="):
                        proof["nginx_version"] = line.split("=", 1)[1]
                elif line.startswith("__DAC_PROOF_SERVICE="):
                        proof["service_status"] = line.split("=", 1)[1]
                elif line.startswith("__DAC_PROOF_LISTEN="):
                        proof["listen_check"] = line.split("=", 1)[1]

        listen_ok = proof["listen_check"] and f":{listen_port}" in proof["listen_check"]
        service_ok = proof["service_status"] == "active"
        proof["ok"] = bool(listen_ok and service_ok)
        return proof


def get_available_instances_for_user(db: Session, user_id: int) -> List[dict]:
    creds = get_user_aws_credentials(user_id, db)
    region = (creds or {}).get("region")
    if not region:
        region = None
    rows = (
        db.query(Instance, DbSession)
        .join(DbSession, Instance.session_id == DbSession.id)
        .filter(DbSession.user_id == user_id)
        .all()
    )
    result = []
    for inst, sess in rows:
        # Filtre strict: instances AWS réelles et synchronisées
        if not inst.instance_id or not inst.instance_id.startswith("i-"):
            continue
        if inst.provider != "aws":
            continue
        if inst.status and inst.status.lower() not in {"running"}:
            continue
        if region is None:
            continue
        # Déchiffrer l'IP publique
        try:
            public_ip = decrypt(inst.public_ip) if inst.public_ip else None
        except:
            public_ip = inst.public_ip  # Si échec déchiffrement, garder tel quel
        
        result.append({
            "id": inst.id,
            "instance_id": inst.instance_id,
            "name": inst.name or inst.instance_id,
            "public_ip": public_ip,
            "provider": inst.provider,
            "region": region,
            "status": inst.status or "unknown",
            "ssh_user": inst.ssh_user,
            "connection_method": getattr(inst, "connection_method", None),
            "ssm_managed": bool(getattr(inst, "ssm_managed", False)),
        })
    return result


def generate_inventory_from_instances(instances: List[Instance], work_dir: Path) -> Tuple[str, List[str]]:
    ansible_dir = work_dir / "ansible"
    keys_dir = ansible_dir / "keys"
    ansible_dir.mkdir(parents=True, exist_ok=True)
    keys_dir.mkdir(parents=True, exist_ok=True)

    key_files = []
    lines = ["# Generated inventory for configure-only", "", "[selected_instances]"]

    for idx, inst in enumerate(instances, start=1):
        # Déchiffrer l'IP et la clé privée
        from app.utils.crypto import decrypt
        try:
            public_ip = decrypt(inst.public_ip)
            private_key = decrypt(inst.ssh_private_key)
        except Exception as e:
            print(f"Erreur déchiffrement instance {inst.id}: {e}")
            # Fallback : utiliser tel quel si pas chiffré
            public_ip = inst.public_ip
            private_key = inst.ssh_private_key
        
        key_path = keys_dir / f"instance_{inst.id}.pem"
        key_path.write_text(private_key)
        os.chmod(key_path, 0o600)
        key_files.append(str(key_path))
        lines.append(
            f"instance{idx} ansible_host={public_ip} ansible_user={inst.ssh_user} "
            f"ansible_ssh_private_key_file={key_path}"
        )

    lines.extend([
        "",
        "[selected_instances:vars]",
        "ansible_python_interpreter=/usr/bin/python3",
        "ansible_ssh_common_args=-o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null",
        "",
    ])

    inventory_file = ansible_dir / "inventory.ini"
    inventory_file.write_text("\n".join(lines))
    return str(inventory_file), key_files


def build_playbook_from_reqs(ansible_reqs: List[dict]) -> str:
    tasks = [
        "- name: Configure instances",
        "  hosts: selected_instances",
        "  become: true",
        "  gather_facts: yes",
        "  vars:",
        "    ansible_connection_retries: 10",
        "  tasks:",
        "    - name: Update apt cache",
        "      apt:",
        "        update_cache: yes",
        "      when: ansible_os_family == 'Debian'",
    ]

    lower_reqs = " ".join([r.get("keyword", "") for r in ansible_reqs]).lower()

    if "nginx" in lower_reqs:
        tasks.extend([
            "    - name: Install nginx",
            "      apt:",
            "        name: nginx",
            "        state: present",
            "      when: ansible_os_family == 'Debian'",
            "",
            "    - name: Ensure nginx running",
            "      service:",
            "        name: nginx",
            "        state: started",
            "        enabled: yes",
        ])

    if "ufw" in lower_reqs or "firewall" in lower_reqs:
        tasks.extend([
            "    - name: Allow 80/443",
            "      ufw:",
            "        rule: allow",
            "        port: '80'",
            "    - name: Allow 22",
            "      ufw:",
            "        rule: allow",
            "        port: '22'",
            "    - name: Enable UFW",
            "      ufw:",
            "        state: enabled",
            "        policy: allow",
        ])

    tasks.append("")
    return "\n".join(["---"] + tasks)




def build_terraform_update_config(sg_id: str, terraform_reqs: List[dict], ports: List[int]) -> str:
    """Generate minimal Terraform update config for security group rules."""
    lines = [
        'terraform {',
        '  required_version = ">= 1.0"',
        '  required_providers {',
        '    aws = {',
        '      source  = "hashicorp/aws"',
        '      version = "~> 5.0"',
        '    }',
        '  }',
        '}',
        '',
        'variable "aws_region" {',
        '  default = "eu-north-1"',
        '}',
        '',
        'provider "aws" {',
        '  region = var.aws_region',
        '}',
        '',
        f'data "aws_security_group" "target" {{',
        f'  id = "{sg_id}"',
        '}',
        '',
    ]

    for port in ports:
        safe_port = port
        lines.extend([
            f'resource "aws_security_group_rule" "allow_port_{safe_port}" {{',
            f'  type              = "ingress"',
            f'  from_port         = {safe_port}',
            f'  to_port           = {safe_port}',
            f'  protocol          = "tcp"',
            f'  cidr_blocks       = ["0.0.0.0/0"]',
            f'  security_group_id = data.aws_security_group.target.id',
            f'}}',
            f'',
        ])

    return "\n".join(lines)


def run_terraform_update(tf_dir: Path, env: dict) -> tuple[int, str, str]:
    """Run terraform init, plan, apply in update directory."""
    env_copy = os.environ.copy()
    env_copy.update(env)

    for cmd in [
        ["terraform", "init"],
        ["terraform", "plan", "-out=tfplan"],
        ["terraform", "apply", "-auto-approve", "tfplan"],
    ]:
        proc = subprocess.Popen(cmd, cwd=str(tf_dir), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env_copy)
        stdout, stderr = proc.communicate(timeout=300)
        if proc.returncode != 0:
            return proc.returncode, stdout, stderr

    return 0, "Terraform update completed", ""


def run_ansible(inventory_file: str, playbook_file: str, work_dir: Path) -> tuple[int, str, str]:
    cmd = ["ansible-playbook", playbook_file, "-i", inventory_file, "-vvv"]
    proc = subprocess.Popen(cmd, cwd=str(work_dir), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stdout, stderr = proc.communicate(timeout=900)
    return proc.returncode, stdout, stderr


def fetch_ssm_ping_status(instance_ids: List[str], aws_credentials: dict | None) -> Dict[str, str]:
    """Retourne {instance_id: PingStatus}."""
    if not instance_ids or not aws_credentials:
        return {}

    region = aws_credentials.get('region', 'eu-north-1') if aws_credentials else 'eu-north-1'
    try:
        ssm = boto3.client(
            'ssm',
            region_name=region,
            aws_access_key_id=aws_credentials.get('access_key_id'),
            aws_secret_access_key=aws_credentials.get('secret_access_key'),
        )
        statuses: Dict[str, str] = {}
        paginator = ssm.get_paginator('describe_instance_information')
        for page in paginator.paginate():
            for info in page.get('InstanceInformationList', []):
                statuses[info.get('InstanceId')] = info.get('PingStatus')
        return {iid: statuses.get(iid) for iid in instance_ids}
    except Exception as e:
        logger.warning(" Impossible de récupérer le statut SSM: %s", e)
        return {}


def preflight_check_ssm_permissions(aws_credentials: dict | None, region: str = "eu-north-1") -> Dict[str, any]:
    """
    Preflight check: verify SSM permissions before execution.
    
    Returns:
        {"status": "ok|failed", "error": "...", "suggestion": "..."}
    """
    if not aws_credentials:
        return {
            "status": "failed",
            "error": "AWS credentials not provided",
            "suggestion": "Configure AWS credentials via /user/aws-credentials"
        }
    
    try:
        ssm = boto3.client(
            'ssm',
            region_name=region,
            aws_access_key_id=aws_credentials.get('access_key_id'),
            aws_secret_access_key=aws_credentials.get('secret_access_key'),
        )
        # Test minimal permission
        ssm.describe_instance_information(MaxResults=5)
        return {"status": "ok"}
    except Exception as e:
        from botocore.exceptions import ClientError
        if isinstance(e, ClientError):
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_msg = e.response.get('Error', {}).get('Message', str(e))
            
            if error_code == "AccessDeniedException":
                return {
                    "status": "failed",
                    "error": f"IAM permissions denied: {error_msg}",
                    "suggestion": "Grant IAM permissions: ssm:DescribeInstanceInformation, ssm:SendCommand, ssm:GetCommandInvocation"
                }
        
        return {
            "status": "failed",
            "error": str(e),
            "suggestion": "Check AWS credentials and IAM permissions"
        }


def handle_configure_only(text: str, instances: List[Instance], base_dir: Path, aws_credentials: dict = None) -> dict:
    """
    Exécute la configuration sur les instances sélectionnées.
    
    Flow:
    1. Terraform (si needed) -> met à jour l'infrastructure AWS
    2. VM Config (Ansible SSH ou SSM) -> configure les instances
        ÉTAPE 4: Batch execution pour scale (10-1000 VMs)
    3. Reporting
    
    Args:
        text: Description de la configuration demandée
        instances: Instances à configurer
        base_dir: Répertoire de base pour les fichiers générés
        aws_credentials: Dict avec AWS credentials pour SSM (optionnel)
    """
    plan = route_config_request(text)
    work_dir = base_dir / f"configure_only_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    work_dir.mkdir(parents=True, exist_ok=True)

    results = {"plan": plan.model_dump()}
    requested_ports = extract_ports_from_text(text)
    listen_port = requested_ports[0] if requested_ports else 8080
    
    # Preflight check: SSM permissions
    if plan.needs_ansible and aws_credentials:
        perm_check = preflight_check_ssm_permissions(aws_credentials, aws_credentials.get('region', 'eu-north-1'))
        if perm_check["status"] != "ok":
            results.update({
                "status": "blocked",
                "reason": "insufficient_ssm_permissions",
                "message": f"{SSM_BLOCK_MESSAGE}\\n\\nDétails: {perm_check.get('error')}\\n{perm_check.get('suggestion', '')}",
                "permissions_check": perm_check,
            })
            return results
    
    # SSM-first: blocage immédiat si pas d'instances SSM-manageables
    if plan.needs_ansible:
        non_ssm = [inst for inst in instances if not (hasattr(inst, 'ssm_managed') and inst.ssm_managed)]
        if non_ssm:
            results.update({
                "status": "blocked",
                "reason": "ssm_required",
                "message": SSM_BLOCK_MESSAGE,
                "non_ssm_instance_ids": [inst.instance_id for inst in non_ssm],
            })
            return results

    # Étape Terraform (cloud) AVANT SSM (ordre strict Terraform -> sync -> SSM)
    if plan.needs_terraform:
        logger.info(" Exécution Terraform SG pour %d instances (ordre avant SSM)", len(instances))
        ports = requested_ports or [listen_port]

        sg_ids = set()
        vpc_ids = set()
        for inst in instances:
            if hasattr(inst, 'security_group_id') and inst.security_group_id:
                sg_ids.add(inst.security_group_id)
            if hasattr(inst, 'vpc_id') and inst.vpc_id:
                vpc_ids.add(inst.vpc_id)

        if not sg_ids:
            logger.warning("  Aucun SG ID trouvé dans les instances")
            results["terraform"] = {
                "status": "skipped",
                "reason": "No security_group_id found in instances. Track from AWS sync.",
                "instances_processed": len(instances),
                "ports_requested": ports,
            }
        else:
            from app.services.sg_terraform_service import handle_sg_terraform

            sg_id = list(sg_ids)[0]
            vpc_id = list(vpc_ids)[0] if vpc_ids else None

            tf_result = handle_sg_terraform(
                sg_id=sg_id,
                vpc_id=vpc_id,
                ports_to_open=ports,
                work_dir=work_dir,
                aws_access_key=aws_credentials.get('access_key_id') if aws_credentials else None,
                aws_secret_key=aws_credentials.get('secret_access_key') if aws_credentials else None,
                region=aws_credentials.get('region', 'eu-north-1') if aws_credentials else 'eu-north-1'
            )

            results["terraform"] = tf_result

    # Étape SSM (VM config) — exclusif, aucune exécution SSH par défaut
    if plan.needs_ansible:
        if not aws_credentials:
            results.update({
                "status": "blocked",
                "reason": "missing_aws_credentials",
                "message": SSM_BLOCK_MESSAGE,
            })
            return results

        from app.services.batch_executor import BatchExecutor
        from app.services.ssm_executor import execute_via_ssm

        instance_ids = [inst.instance_id for inst in instances]
        ping_status = fetch_ssm_ping_status(instance_ids, aws_credentials)
        online_ids = [iid for iid, status in ping_status.items() if status == "Online"]

        if not online_ids:
            results.update({
                "status": "blocked",
                "reason": "no_ssm_online",
                "message": SSM_BLOCK_MESSAGE,
                "ssm_online": 0,
                "ssm_total": len(instance_ids),
            })
            return results

        online_instances = [inst for inst in instances if inst.instance_id in online_ids]

        # Build OS-aware commands (detect OS family from first instance)
        os_family = "linux"  # Default
        if online_instances:
            first_os = getattr(online_instances[0], 'os_family', 'linux') or 'linux'
            os_family = first_os.lower()
        
        # Detect application type from keywords
        contains_nginx = any("nginx" in (req.get("keyword", "").lower()) for req in plan.ansible_reqs)
        contains_apache = any(word in (req.get("keyword", "").lower()) for word in ["apache", "apache2", "httpd"] for req in plan.ansible_reqs)
        
        if contains_nginx:
            shell_commands = build_nginx_ssm_script(listen_port)
        elif contains_apache:
            shell_commands = build_apache_ssm_script(listen_port)
        else:
            shell_commands = build_os_aware_commands(os_family, plan.ansible_reqs)
        playbook_content = build_playbook_from_reqs(plan.ansible_reqs)
        playbook_path = work_dir / "configure.yml"
        playbook_path.write_text(playbook_content)

        batch_executor = BatchExecutor(batch_size=5, timeout_per_vm=300)

        def ssm_executor(batch_instances):
            if not batch_instances:
                return {}
            ids = [inst.instance_id for inst in batch_instances]
            return execute_via_ssm(
                aws_access_key=aws_credentials.get('access_key_id'),
                aws_secret_key=aws_credentials.get('secret_access_key'),
                instance_ids=ids,
                command=shell_commands,
                region=aws_credentials.get('region', 'eu-north-1')
            )

        batch_results = batch_executor.execute_all_batches(
            online_instances,
            ssh_executor=None,  # SSH interdit par défaut
            ssm_executor=ssm_executor,
            max_workers=4
        )

        # VALIDATION CRITIQUE: Vérifier stdout non-vide + marqueurs de succès
        # On doit faire ça AVANT de générer le summary
        proofs = {}
        for inst in online_instances:
            inst_id = inst.instance_id
            res = batch_results.get(inst_id, {})
            
            # SSM success + vérification stdout
            if res.get("method") == "ssm" and res.get("status") == "success":
                stdout = res.get("stdout", "")
                stderr = res.get("stderr", "")
                
                # Valider que le script a réellement exécuté quelque chose
                is_valid, error_msg = validate_ssm_success(stdout, stderr)
                
                if not is_valid:
                    logger.warning(
                        "[CONFIGURE_ONLY] Instance %s: %s", 
                        inst_id, error_msg
                    )
                    # Marquer comme échoué si validation échoue
                    res["status"] = "failed"
                    res["validation_error"] = error_msg
                else:
                    proof = parse_proof_output(stdout, listen_port)
                    proof["ssm_status"] = res.get("status")
                    proofs[inst_id] = proof
                    logger.info("[CONFIGURE_ONLY] Instance %s: validation OK", inst_id)
            elif res.get("method") == "ssm":
                # Autres status (failed, timeout, error)
                logger.warning(
                    "[CONFIGURE_ONLY] Instance %s: SSM status=%s", 
                    inst_id, res.get("status")
                )

        # NOW: Générer le summary APRÈS validation
        results["batch_execution"] = {
            "playbook": str(playbook_path),
            "batch_size": batch_executor.batch_size,
            "shell_command": shell_commands[:150] + "..." if len(shell_commands) > 150 else shell_commands,
            "per_instance_results": batch_results,
            "summary": {
                "total": len(batch_results),
                "success": sum(1 for r in batch_results.values() if r.get('status') == 'success'),
                "failed": sum(1 for r in batch_results.values() if r.get('status') == 'failed'),
                "timeout": sum(1 for r in batch_results.values() if r.get('status') == 'timeout'),
            }
        }

        results["proofs"] = {
            "listen_port": listen_port,
            "per_instance": proofs,
        }

    if "batch_execution" in results:
        logger.info(" Génération du rapport ÉTAPE 5")
        from app.services.report_generator import generate_complete_report

        batch_results = results["batch_execution"]["per_instance_results"]

        instances_info = {}
        for inst in instances:
            instances_info[inst.instance_id] = {
                "name": inst.name or inst.instance_id,
                "provider": inst.provider,
                "connection_method": str(inst.connection_method) if hasattr(inst, 'connection_method') else "unknown"
            }

        report = generate_complete_report(
            batch_results,
            instances_info=instances_info,
            output_dir=work_dir / "reports",
            format_text=True
        )

        results["report"] = {
            "summary": report["summary"],
            "text_report_preview": report.get("text_report", "")[:500],
            "full_report_saved": str(work_dir / "reports"),
        }

        if "text_report" in report:
            logger.info("\n%s", report["text_report"])

    return results


def handle_configure_via_ansible(text: str, instances: List[Instance], base_dir: Path) -> dict:
    """
    Fallback Ansible (SSH) quand SSM n'est pas disponible.

    - Génère un inventaire SSH à partir des instances (IP/clé/ssh_user)
    - Construit un playbook minimal selon les besoins (ex: nginx 8080)
    - Exécute ansible-playbook et retourne un rapport synthétique
    """
    plan = route_config_request(text)
    work_dir = base_dir / f"configure_ansible_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    work_dir.mkdir(parents=True, exist_ok=True)

    # Terraform éventuel pour règles SG si nécessaire (même logique que SSM-first)
    results: Dict[str, any] = {"plan": plan.model_dump(), "method": "ansible"}

    if plan.needs_terraform:
        logger.info(" [Ansible Fallback] Exécution Terraform SG avant SSH")
        ports = extract_ports_from_text(text) or [80, 443]

        sg_ids = set()
        vpc_ids = set()
        for inst in instances:
            if hasattr(inst, 'security_group_id') and inst.security_group_id:
                sg_ids.add(inst.security_group_id)
            if hasattr(inst, 'vpc_id') and inst.vpc_id:
                vpc_ids.add(inst.vpc_id)

        if sg_ids:
            from app.services.sg_terraform_service import handle_sg_terraform
            sg_id = list(sg_ids)[0]
            vpc_id = list(vpc_ids)[0] if vpc_ids else None

            tf_result = handle_sg_terraform(
                sg_id=sg_id,
                vpc_id=vpc_id,
                ports_to_open=ports,
                work_dir=work_dir,
                aws_access_key=None,
                aws_secret_key=None,
                region='eu-north-1'
            )
            results["terraform"] = tf_result
        else:
            results["terraform"] = {
                "status": "skipped",
                "reason": "No security_group_id found in instances.",
            }

    # Générer inventaire + playbook, puis exécuter via Ansible SSH
    inv_file, key_files = generate_inventory_from_instances(instances, work_dir)
    playbook_content = build_playbook_from_reqs(plan.ansible_reqs)
    playbook_path = work_dir / "configure.yml"
    playbook_path.write_text(playbook_content)

    rc, out, err = run_ansible(inv_file, str(playbook_path), work_dir)
    status = "completed" if rc == 0 else "failed"

    # Résultats minimalistes (pas de parsing détaillé ici)
    results["ansible"] = {
        "status": status,
        "rc": rc,
        "stdout_preview": out[:1000] if out else "",
        "stderr_preview": err[:1000] if err else "",
        "inventory": inv_file,
        "playbook": str(playbook_path),
    }

    return results


def build_shell_commands_from_reqs(ansible_reqs: dict) -> str:
    """
    Convertit les requirements Ansible en commandes shell pour SSM.
    
    Args:
        ansible_reqs: Dict avec {'install_packages': [...], 'enable_services': [...], ...}
    
    Returns:
        String avec commandes shell séparées par '; '
    """
    commands = []
    
    # Si ansible_reqs est une liste, prendre le premier élément ou dict vide
    if isinstance(ansible_reqs, list):
        ansible_reqs = ansible_reqs[0] if ansible_reqs else {}
    
    # Déterminer le gestionnaire de paquets (par défaut apt pour Ubuntu)
    pkg_mgr = ansible_reqs.get('package_manager', 'apt')
    
    # Installer les paquets
    if ansible_reqs.get('install_packages'):
        pkg_list = ' '.join(ansible_reqs['install_packages'])
        if pkg_mgr == 'apt':
            commands.append(f"apt-get update && apt-get install -y {pkg_list}")
        elif pkg_mgr == 'yum':
            commands.append(f"yum install -y {pkg_list}")
    
    # Démarrer/activer les services
    for service in ansible_reqs.get('enable_services', []):
        commands.append(f"systemctl start {service} && systemctl enable {service}")
    
    # Tâches personnalisées (génériques)
    for task in ansible_reqs.get('custom_tasks', []):
        if isinstance(task, dict) and 'shell' in task:
            commands.append(task['shell'])
        elif isinstance(task, str):
            commands.append(task)
    
    return ' ; '.join(commands) if commands else "echo 'No commands to execute'"


def extract_ports_from_text(text: str) -> list:
    """
    Extrait les numéros de ports d'un texte (ex: 80, 443, 8000, etc).
    
    Args:
        text: Texte contenant potentiellement des numéros de ports
    
    Returns:
        Liste de ports trouvés (ou liste vide)
    """
    # Cherche des patterns comme "port 80", "80", "443", etc
    pattern = r'\b(?:port\s+)?(\d{2,5})\b'
    matches = re.findall(pattern, text, re.IGNORECASE)
    
    # Filtrer les ports valides (1-65535)
    valid_ports = []
    for m in matches:
        port = int(m)
        if 1 <= port <= 65535:
            valid_ports.append(port)
    
    return list(set(valid_ports))  # Remove duplicates
