# app/services/ansible_inventory.py
import logging
import os
import uuid
from typing import Optional, List, Tuple, Dict, Any

from sqlalchemy.orm import Session

from app import models  # si tu ne l'utilises pas ailleurs, tu peux le retirer
from app.utils.crypto import decrypt
from app.utils.file_utils import (
    _session_subdir,            # helper interne -> "<user>/<YYYY-MM-DD>/s<session>"
    create_and_store_inventory, # persistance standardisée (chemin + DB)
    save_file,                  # applique 0700 sur dir private_keys et 0400 sur la clé
)

logger = logging.getLogger(__name__)


def _write_pem_for_inventory(user_id: int, session_id: int, pem_str: str, suffix: str, idx: int) -> str:
    """
    Écrit une clé privée PEM pour l'inventaire dans:
      generated_files/<user>/<YYYY-MM-DD>/s<session>/private_keys/invkey_<suffix>_<idx>.pem
    Permissions gérées par save_file: dossier 0700, fichier 0400.
    Retourne le chemin ABSOLU.
    """
    subdir = os.path.join(_session_subdir(user_id, session_id), "private_keys")
    filename = f"invkey_{suffix}_{idx}.pem"
    return save_file(pem_str, subdir, filename)

# Valeurs par défaut raisonnables suivant la distro
USER_BY_DISTRO = {
    "ubuntu": "ubuntu",
    "debian": "debian",       # selon image: parfois "admin"
    "amzn": "ec2-user",
    "amazon-linux": "ec2-user",
    "rhel": "ec2-user",
    "redhat": "ec2-user",
    "centos": "ec2-user",
    "rocky": "ec2-user",
    "sles": "ec2-user",
    "suse": "ec2-user",
    "unknown": "ec2-user",
    "windows": "Administrator",
}


def generate_inventory_from_executions(
    *,
    instances: List[Dict[str, Any]],
    user_id: int,
    db: Session,
    session_id: int,
    intent_id: Optional[int] = None
) -> Tuple[str, int]:
    """
    Construit un inventaire INI à partir d'une liste d'instances:

    instances: [
      {
        "name": str,
        "ip": str (clair),
        "os_family": "linux"|"windows",
        "distro": str,
        "ssh_user": str (optionnel),
        "private_key": str (PEM clair ou chiffré - on tentera decrypt),
        "ssh_port": int (optionnel),
        "runtime": "ssh"|"winrm"|... (optionnel),
        # Windows:
        "win_password": str (clair ou chiffré),
        "win_password_encrypted": bool
      }, ...
    ]
    Retourne: (inventory_path_absolu, inventory_db_id)
    """
    if not session_id:
        raise ValueError("session_id est requis.")

    short = uuid.uuid4().hex[:8]
    inventory_filename = f"inventory_{short}.ini"

    linux_lines: List[str] = []
    windows_lines: List[str] = []

    for idx, inst in enumerate(instances, start=1):
        # Nom d'hôte (fallback sur IP si besoin)
        host_name = (inst.get("name") or "").strip()
        ip = str(inst.get("ip") or "").strip()

        if not ip:
            logger.warning("⏭ Hôte ignoré: IP manquante (name=%r)", host_name or f"target{idx}")
            continue

        if not host_name:
            host_name = ip.replace(".", "_")

        os_family = (inst.get("os_family") or "linux").lower()
        distro = (inst.get("distro") or "unknown").lower()
        runtime = (inst.get("runtime") or "").lower() or None

        if os_family == "windows":
            # --- Windows via WinRM (HTTPS 5986)
            ansible_user = inst.get("ssh_user") or USER_BY_DISTRO["windows"]
            win_password = inst.get("win_password")

            # si chiffré -> decrypt
            if win_password and inst.get("win_password_encrypted", False):
                try:
                    win_password = decrypt(win_password)
                except Exception:
                    pass  # déjà en clair

            # Échapper simples quotes si besoin
            if win_password:
                win_password = str(win_password).replace("'", "''")

            parts = [
                host_name,
                f"ansible_host={ip}",
                "ansible_connection=winrm",
                "ansible_port=5986",
                "ansible_winrm_scheme=https",
                "ansible_winrm_transport=ntlm",
                "ansible_winrm_server_cert_validation=ignore",
                f"ansible_user={ansible_user}",
            ]
            if win_password:
                parts.append(f"ansible_password='{win_password}'")
            if runtime:
                parts.append(f"runtime={runtime}")
            parts.append(f"os_family={os_family}")
            parts.append(f"distro={distro}")

            windows_lines.append(" ".join(parts))

        else:
            # --- Linux via SSH
            ansible_user = inst.get("ssh_user") or USER_BY_DISTRO.get(distro, "ec2-user")

            # Clé privée: on attend souvent du PEM clair; on tente decrypt à tout hasard
            key_path_part = ""
            pem = inst.get("private_key")
            if pem:
                try:
                    pem_clair = decrypt(pem)
                except Exception:
                    pem_clair = pem  # déjà en clair

                pem_path = _write_pem_for_inventory(user_id, session_id, pem_clair, short, idx)
                key_path_part = f"ansible_ssh_private_key_file={pem_path}"

            parts = [
                host_name,
                f"ansible_host={ip}",
                f"ansible_user={ansible_user}",
            ]
            if key_path_part:
                parts.append(key_path_part)

            # Désactive la vérif de host key pour éviter les UNREACHABLE au 1er run
            parts.append("ansible_ssh_common_args='-o StrictHostKeyChecking=no'")

            # Port SSH custom
            ssh_port = inst.get("ssh_port")
            if ssh_port:
                parts.append(f"ansible_port={ssh_port}")

            # Interpréteur Python explicite pour distros qui n'ont pas /usr/bin/python par défaut
            if distro in {"amzn", "amazon-linux", "rhel", "redhat", "centos", "rocky", "sles", "suse", "debian"}:
                parts.append("ansible_python_interpreter=/usr/bin/python3")

            if runtime:
                parts.append(f"runtime={runtime}")
            parts.append(f"os_family={os_family}")
            parts.append(f"distro={distro}")

            linux_lines.append(" ".join(parts))

    # Construction INI
    content_lines: List[str] = []
    if linux_lines:
        content_lines.append("[linux]")
        content_lines.extend(linux_lines)
        content_lines.append("")
    if windows_lines:
        content_lines.append("[windows]")
        content_lines.extend(windows_lines)
        content_lines.append("")

    if not content_lines:
        # aucun hôte catégorisé: fallback unique
        content_lines = ["[targets]"]
        # on ne remet pas les headers linux/windows, seulement les lignes brutes si dispo

    inventory_content = "\n".join(content_lines).rstrip() + "\n"

    # Persistance (écrit le fichier et crée la ligne DB)
    inv = create_and_store_inventory(
        user_id=user_id,
        session_id=session_id,
        filename=inventory_filename,
        content=inventory_content
    )

    # Attacher l'intent si présent
    if intent_id:
        try:
            inv.intent_id = intent_id
            db.add(inv)
            db.commit()
            db.refresh(inv)
        except Exception:
            db.rollback()

    return inv.file_path, inv.id
