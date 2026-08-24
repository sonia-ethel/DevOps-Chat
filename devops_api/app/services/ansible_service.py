# app/services/ansible_service.py
import logging
import os
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from typing import Tuple, List

from app.paths import LOGS_DIR
from app.models.execution_log import ExecutionLog
from app.services.ansible_validate import validate_ansible_playbook as _validate_ansible_playbook
from app.utils.file_utils import create_and_store_playbook
from app.security.safe_subprocess import run_safe_command

logger = logging.getLogger(__name__)


# 
# Validation (ré-export) – pour que les autres modules puissent importer depuis
# app.services.ansible_service sans changer leurs imports.
# 
def validate_ansible_playbook(yaml_str: str) -> str:
    """
    Valide/normalise un playbook YAML. Ré-export de app.services.ansible_validate.
    Retourne du YAML nettoyé/valide (avec newline final).
    """
    return _validate_ansible_playbook(yaml_str).rstrip() + "\n"


# 
# Génération de playbook (compat legacy) – désormais aligne le stockage via
# create_and_store_playbook pour respecter l’arborescence :
# generated/<user>/<YYYY-MM-DD>/s<session>/ansible/<fichier>.yml
# 
async def generate_ansible_playbook(
    instructions: str,
    session_id: int,
    user_id: int,
    user_email: str
) -> Tuple[str, int]:
    """
    LEGACY COMPAT: génère et stocke un playbook Ansible en s’appuyant sur
    create_and_store_playbook() (nouvelle arborescence + persistence DB).
    Retourne (file_path, playbook_id).
    """
    logger.info(" [Ansible] Début de la génération du playbook...")
    ansible_code = (instructions or "").strip()

    # Garde-fou taille (évite de stocker un pavé si GPT déraille)
    MAX_BYTES = 512_000  # ~500 KB
    if len(ansible_code.encode("utf-8")) > MAX_BYTES:
        raise ValueError("Playbook trop volumineux (>500KB). Réessaie avec une demande plus ciblée.")

    #  Validation YAML (ré-export local)
    logger.info(" [Ansible] Validation YAML en cours...")
    ansible_code_cleaned = validate_ansible_playbook(ansible_code)
    logger.info(" [Ansible] YAML validé.")

    #  Nom de fichier lisible (le chemin final sera géré par file_utils)
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M")
    safe_username = (user_email or "user").split("@")[0].replace(".", "_")
    filename = f"ansible_{safe_username}_s{session_id}_{timestamp}.yml"

    #  Écriture disque + DB via utilitaire centralisé
    pb = create_and_store_playbook(
        user_id=user_id,
        session_id=session_id,
        filename=filename,
        content=ansible_code_cleaned
    )

    logger.info(" [Ansible] Playbook enregistré et persisté: %s", pb.file_path)
    return pb.file_path, pb.id


async def generate_audit_playbook(
    instructions: str,
    session_id: int,
    user_id: int,
    tools: List[str]
) -> Tuple[str, int]:
    """
    LEGACY COMPAT: génère un playbook Ansible d’audit (ex: lynis) et le stocke
    via create_and_store_playbook() (même arborescence centrale).
    Retourne (file_path, playbook_id).
    """
    tools = tools or []
    logger.info(" [Audit] Génération du playbook | outils=%s", ",".join(tools))

    ansible_code = (instructions or "").strip()
    MAX_BYTES = 512_000  # ~500 KB
    if len(ansible_code.encode("utf-8")) > MAX_BYTES:
        raise ValueError("Playbook d'audit trop volumineux (>500KB).")

    # Validation YAML + newline final (via ré-export)
    ansible_code_cleaned = validate_ansible_playbook(ansible_code)

    # Nom de fichier sûr (slug minimal pour les outils)
    def slug(s: str) -> str:
        return "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in (s or "").lower()).strip("-_") or "audit"

    tools_str = slug("_".join(tools)) if tools else "audit"
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M")
    filename = f"audit_{tools_str}_s{session_id}_{timestamp}.yml"

    pb = create_and_store_playbook(
        user_id=user_id,
        session_id=session_id,
        filename=filename,
        content=ansible_code_cleaned
    )

    logger.info(" [Audit] Playbook généré et stocké: %s", pb.file_path)
    return pb.file_path, pb.id


# 
# Exécution du playbook
# 
async def run_ansible(
    playbook_path: str,
    inventory_path: str,
    db: Session,
    execution_id: int,
    user_id: int,
    timeout_seconds: int = 3600
) -> dict:
    logger.info(" [Ansible] Lancement de l'exécution du playbook...")
    logger.info(f" [Ansible] Playbook : {playbook_path}")
    logger.info(f" [Ansible] Inventaire : {inventory_path}")

    if not os.path.exists(playbook_path):
        raise FileNotFoundError(f"Le playbook '{playbook_path}' n'existe pas.")
    if not os.path.exists(inventory_path):
        raise FileNotFoundError(f"L'inventaire '{inventory_path}' n'existe pas.")

    # Détecte présence de Windows (WinRM) dans l'inventaire
    try:
        with open(inventory_path, "r", encoding="utf-8") as _f:
            inv_txt = _f.read().lower()
    except Exception:
        inv_txt = ""
    has_windows = ("ansible_connection=winrm" in inv_txt) or ("[windows]" in inv_txt)

    # Log démarrage
    db.add(ExecutionLog(
        execution_id=execution_id,
        event="started",
        message=" Exécution Ansible démarrée.",
        created_at=datetime.utcnow()
    ))
    db.commit()

    # Commande Ansible
    cmd = ["ansible-playbook", "-i", inventory_path, "-v", playbook_path]
    # Pour SSH (Linux) on désactive le check hôte via --ssh-extra-args
    if not has_windows:
        cmd = [
            "ansible-playbook",
            "-i", inventory_path,
            "--ssh-extra-args", "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null",
            "-v",
            playbook_path
        ]

    # Environnement (désactive aussi côté Ansible)
    env = os.environ.copy()
    env["ANSIBLE_HOST_KEY_CHECKING"] = "False"

    logger.info(f" [Ansible] Commande : {' '.join(cmd)}")

    result = run_safe_command(cmd, env=env, timeout_seconds=timeout_seconds)

    logs: List[str] = []
    if result.stdout:
        logs = result.stdout.split("\n")
    
    important_prefixes = ("TASK", "ok:", "changed:", "fatal:", "FAILED!", "UNREACHABLE!", "ERROR!")
    batch: List[str] = []
    BATCH_SIZE = 20

    try:
        for line in logs:
            if not line:
                continue
            lstrip = line.strip()
            if lstrip.startswith(important_prefixes):
                logger.info(lstrip)
                batch.append(lstrip)
                if len(batch) >= BATCH_SIZE:
                    db.bulk_save_objects([
                        ExecutionLog(
                            execution_id=execution_id,
                            event="stream",
                            message=msg,
                            created_at=datetime.utcnow()
                        ) for msg in batch
                    ])
                    db.commit()
                    batch.clear()

        # vidage restant
        if batch:
            db.bulk_save_objects([
                ExecutionLog(
                    execution_id=execution_id,
                    event="stream",
                    message=msg,
                    created_at=datetime.utcnow()
                ) for msg in batch
            ])
            db.commit()

        if result.returncode != 0:
            all_logs = "\n".join(logs)
            db.add(ExecutionLog(
                execution_id=execution_id,
                event="failed",
                message=f" Erreur Ansible (rc={result.returncode})\n{all_logs[-4000:]}",
                created_at=datetime.utcnow()
            ))
            db.commit()
            raise Exception(f"Erreur Ansible (rc={result.returncode})")

    finally:
        if process.stdout:
            process.stdout.close()

    #  Sauvegarde des logs complets (-> LOGS_DIR unifié)
    os.makedirs(LOGS_DIR, exist_ok=True)
    log_path = os.path.join(LOGS_DIR, f"{execution_id}.log")
    all_logs = "".join(logs)
    with open(log_path, "w", encoding="utf-8") as log_file:
        log_file.write(all_logs)

    rc = process.returncode
    if rc != 0:
        db.add(ExecutionLog(
            execution_id=execution_id,
            event="failed",
            message=f" Erreur Ansible (rc={rc}):\n{all_logs[-4000:]}",
            created_at=datetime.utcnow()
        ))
        db.commit()
        raise Exception(f"Erreur Ansible rc={rc}")

    db.add(ExecutionLog(
        execution_id=execution_id,
        event="completed",
        message=" Exécution Ansible terminée avec succès.",
        created_at=datetime.utcnow()
    ))
    db.commit()

    logger.info(f" [Ansible] Logs stockés: {log_path}")
    return {
        "rc": rc,
        "status": "completed",
        "logs": all_logs,
        "log_file": log_path,
        "stdout": all_logs,
        "stderr": ""
    }
