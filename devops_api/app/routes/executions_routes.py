# © 2024–2026 TOURE Arnaud Patrick
# Licensed under the MIT License

# app/routes/executions_routes.py

from datetime import datetime
import asyncio
from typing import List, Optional, Dict, Any, Tuple
import json
import logging
import os
import traceback
import shlex
import sys

from fastapi import APIRouter, Depends, HTTPException, Query, Body, Request
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app import models, database
from app.auth import get_current_user, SECRET_KEY, ALGORITHM
from app.services.execution_service import run_execution
from app.utils.crypto import decrypt, encrypt
from app.utils.extra_data_utils import get_extra, set_extra
from app.utils.file_utils import (
    get_latest_private_key_path,
    load_latest_inventory,
    retrieve_file_path_from_db_id,
    detect_ssh_user_and_basename,
)
from app.utils.file_utils import get_generated_file_path  # utilisé par k8s
from app.models.execution_log import ExecutionLog
from app.security.safe_subprocess import run_safe_command
from app.utils.execution_progress import update_execution_progress
from app.services.idempotency_service import (
    check_or_create_idempotency_key,
    mark_idempotency_completed,
    mark_idempotency_failed,
    extract_idempotency_key
)

logger = logging.getLogger(__name__)

router = APIRouter()


def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _get_user_from_token(token: str, db: Session) -> models.User | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        subject = payload.get("sub")
        if subject is None:
            return None
    except JWTError:
        return None

    # Try numeric id first
    try:
        if isinstance(subject, (int, float)) or (isinstance(subject, str) and subject.isdigit()):
            user_id = int(subject)
            user = db.query(models.User).filter(models.User.id == user_id).first()
            if user:
                return user
    except Exception:
        pass

    if isinstance(subject, str):
        return db.query(models.User).filter(models.User.email == subject).first()

    return None


# -----------------------------
# Helpers
# -----------------------------
def _safe_decrypt(val: Optional[str]) -> Optional[str]:
    """
    Décrypte une valeur éventuellement chiffrée.
    - Retourne None si vide ou si le déchiffrement échoue.
    - Évite de propager un blob chiffré dans des fichiers .pem (libcrypto error).
    """
    try:
        if not val:
            return None
        plain = decrypt(val)
        if not plain or not str(plain).strip():
            return None
        return plain
    except Exception:
        return None


def _instances_to_candidates(db: Session, session_id: int) -> List[Dict[str, Any]]:
    insts = db.query(models.Instance).filter_by(session_id=session_id).all()
    cand: List[Dict[str, Any]] = []
    for i in insts:
        cand.append({
            "id": i.id,
            "name": i.name or i.hostname or i.instance_id,
            "public_ip": decrypt(i.public_ip) if i.public_ip else None,
            "ssh_user": i.ssh_user or "ubuntu",
            "os_family": (i.os_family or "linux").lower(),
            "distro": (i.distro or "unknown").lower(),
            "instance_id": i.instance_id,
        })
    return [c for c in cand if c["public_ip"]]


def _build_inventory_from_selection(
    db: Session,
    user_id: int,
    session_id: int,
    selected_instance_ids: List[int]
) -> Optional[Dict[str, Any]]:
    db_instances = (
        db.query(models.Instance)
        .filter(
            models.Instance.session_id == session_id,
            models.Instance.id.in_(selected_instance_ids),
        )
        .all()
    )
    if not db_instances:
        return None

    from app.services import ansible_inventory as _ai
    items = []
    for inst in db_instances:
        is_win = (inst.os_family or "").lower() == "windows" or (inst.distro or "").lower() == "windows"
        items.append({
            "name":        inst.name or inst.hostname or inst.instance_id,
            "ip":          decrypt(inst.public_ip) if inst.public_ip else None,
            "os_family":   "windows" if is_win else "linux",
            "distro":      (inst.distro or "unknown").lower(),
            "ssh_user":    "Administrator" if is_win else (inst.ssh_user or "ubuntu"),
            # Clé privée uniquement pour SSH (Linux). WinRM n'en a pas besoin.  en clair !
            "private_key": None if is_win else _safe_decrypt(inst.ssh_private_key),
            "ssh_port":    None,
            "runtime":     "winrm" if is_win else "ssh",
        })
    inv_path, inv_id = _ai.generate_inventory_from_executions(
        instances=items, user_id=user_id, db=db, session_id=session_id, intent_id=None
    )
    return {"inventory_path": inv_path, "inventory_id": inv_id}


# --- Helper: persistance d'instances UNIQUEMENT en CREATE --------------------
def _persist_instances_if_create(
    *,
    db: Session,
    intent_type: Optional[str],
    session_id: int,
    provider_name: str,
    instances_result: Optional[List[Dict[str, Any]]]
) -> None:
    """
    Enregistre des instances UNIQUEMENT si intent_type == 'create'.
    Ignore totalement en 'configure' (ALB/DNS/etc.).
    Saute toute entrée sans public_ip pour respecter le NOT NULL.
    """
    if (intent_type or "").lower() != "create":
        return  #  configure -> on ne touche pas à la BDD 'instances'

    if not instances_result:
        return

    rows: List[models.Instance] = []

    for inst in instances_result:
        instance_id = inst.get("instance_id")
        public_ip   = inst.get("public_ip")  # requis (NOT NULL en BDD)
        if not instance_id or not public_ip:
            # On saute les entrées incomplètes
            continue

        # Détermination OS/distro + user
        distro    = (inst.get("distro") or "").lower() or None
        os_family = (inst.get("os_family") or ("windows" if ((distro or "").find("windows") >= 0) else "linux")).lower()
        is_win    = os_family == "windows"

        ssh_user = inst.get("ssh_user") or ("Administrator" if is_win else "ubuntu")
        ssh_key  = inst.get("ssh_private_key")  # peut être None (ex: Windows)

        # Jamais NULL côté BDD
        encrypted_key = encrypt(ssh_key) if ssh_key else encrypt("")
        encrypted_ip  = encrypt(public_ip)

        # Évite les doublons par (instance_id, session_id)
        exists = db.query(models.Instance).filter_by(
            instance_id=instance_id, session_id=session_id
        ).first()
        if exists:
            continue

        rows.append(models.Instance(
            instance_id=instance_id,
            session_id=session_id,
            provider=provider_name.lower(),
            public_ip=encrypted_ip,          # NOT NULL
            private_ip=None,
            ssh_user=ssh_user,
            ssh_private_key=encrypted_key,   # jamais NULL
            name=inst.get("name") or f"{provider_name}-vm-{(instance_id or '')[:6]}",
            status="running",
            os_family=os_family,
            distro=distro,
            hostname=inst.get("hostname"),
        ))

    if not rows:
        return

    db.add_all(rows)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


# -----------------------------
# Pré-flight Ansible (collections & deps)
# -----------------------------
def _run(cmd: List[str]) -> Tuple[int, str, str]:
    """Exécute une commande système de manière sûre (sans shell injection)."""
    try:
        # Seul binaire autorisé ici: ansible-galaxy (pour collections)
        if cmd and cmd[0] == "ansible-galaxy":
            result = run_safe_command(cmd, timeout_seconds=600)
            return result.returncode, result.stdout.strip(), result.stderr.strip()
        else:
            return 1, "", f"Command not allowed: {cmd[0] if cmd else 'unknown'}"
    except Exception as e:
        return 1, "", str(e)

def _inventory_has_windows(inventory_path: Optional[str]) -> bool:
    if not inventory_path or not os.path.exists(inventory_path):
        return False
    try:
        with open(inventory_path, "r", encoding="utf-8") as f:
            content = f.read().lower()
        # Heuristiques simples
        if "ansible_connection=winrm" in content:
            return True
        if "[windows" in content:
            return True
    except Exception:
        pass
    return False

def _ensure_python_dep(pkg: str) -> None:
    rc, _, _ = _run([sys.executable, "-m", "pip", "show", pkg])
    if rc != 0:
        logger.info(f" [Ansible] Installation pip du paquet '{pkg}'…")
        rc2, out2, err2 = _run([sys.executable, "-m", "pip", "install", "--quiet", pkg])
        if rc2 != 0:
            logger.warning(f" [Ansible] Impossible d’installer {pkg}: {err2 or out2}")

def _has_ansible_collection(collection_fqcn: str) -> bool:
    # Test direct via ansible-doc (plus fiable pour une ressource précise)
    test_symbol = "ansible.windows.win_chocolatey" if collection_fqcn == "ansible.windows" else None
    if test_symbol:
        rc, _out, _err = _run(["ansible-doc", test_symbol])
        return rc == 0
    # Sinon, vérifie la prés. globale
    rc, out, _err = _run(["ansible-galaxy", "collection", "list"])
    return rc == 0 and (collection_fqcn in out)

def _install_ansible_collections(collections: List[str]) -> None:
    if not collections:
        return
    cmd = ["ansible-galaxy", "collection", "install", "--force"] + collections
    logger.info(f" [Ansible] Installation des collections manquantes: {' '.join(collections)}")
    rc, out, err = _run(cmd)
    if rc != 0:
        logger.warning(f" [Ansible] Échec installation collections ({rc})\nSTDOUT:\n{out}\nSTDERR:\n{err}")

def _ensure_ansible_prereqs(inventory_path: Optional[str]) -> None:
    windows_needed = _inventory_has_windows(inventory_path)

    # 1) Collections nécessaires
    required = ["ansible.posix", "community.general"]
    if windows_needed:
        required += ["ansible.windows", "community.windows"]

    to_install: List[str] = []
    for col in required:
        if not _has_ansible_collection(col):
            to_install.append(col)

    if to_install:
        _install_ansible_collections(to_install)

    # 2) Deps Python pour WinRM
    if windows_needed:
        _ensure_python_dep("pywinrm")
        _ensure_python_dep("requests-ntlm")


# -----------------------------
# Créer / mettre à jour une exécution
# -----------------------------
@router.post("/executions/create", tags=["Executions"], summary="Créer ou mettre à jour une exécution")
def create_execution(
    request: Request,
    session_id: int = Query(..., description="Identifiant de la session concernée"),
    engine: str = Query(..., description="Type d’exécution : terraform, ansible, audit, kubernetes"),
    file_id: int = Query(None, description="ID du fichier généré (Terraform, playbook ou manifest)"),
    inventory_id: int = Query(None, description="ID de l’inventaire Ansible, si applicable"),
    selected_instance_ids: Optional[List[int]] = Body(
        None,
        embed=True,
        description="Liste d'IDs BDD d'instances à cibler (Ansible/Audit)",
    ),
    recipe_names: Optional[List[str]] = Body(
        None,
        embed=True,
        description="Recettes audit (ex: ['ops_health','security_basic'])",
    ),
    region: Optional[str] = Body(
        None,
        embed=True,
        description="Région AWS pour l'audit (ex: eu-north-1)",
    ),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    #  P0.5 — IDEMPOTENCE CHECK
    idempotency_key = extract_idempotency_key(dict(request.headers))
    if not idempotency_key:
        raise HTTPException(
            status_code=400,
            detail="Header Idempotency-Key obligatoire pour /executions/create"
        )
    
    # Vérifier ou créer la clé d'idempotence
    idempotency_result = check_or_create_idempotency_key(
        db=db,
        user_id=user.id,
        idempotency_key=idempotency_key,
        scope="execution.create"
    )
    
    # Si déjà complétée, retourner l'exécution existante
    if idempotency_result.is_duplicate and idempotency_result.cached_response:
        return idempotency_result.cached_response
    
    session = db.query(models.Session).filter_by(id=session_id, user_id=user.id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session introuvable.")

    latest_intent = (
        db.query(models.Intent)
        .filter_by(session_id=session.id)
        .order_by(models.Intent.created_at.desc())
        .first()
    )
    intent_id = latest_intent.id if latest_intent else None

    # --- Fichier cible (id + path)
    file_path = None
    if not file_id:
        if engine == "terraform":
            file_obj = (
                db.query(models.GeneratedTerraformFile)
                .filter_by(session_id=session_id, user_id=user.id)
                .order_by(models.GeneratedTerraformFile.created_at.desc())
                .first()
            )
        elif engine == "ansible":
            file_obj = (
                db.query(models.GeneratedPlaybook)
                .filter_by(session_id=session_id, user_id=user.id)
                .order_by(models.GeneratedPlaybook.created_at.desc())
                .first()
            )
        elif engine == "audit":
            file_obj = None
        elif engine == "kubernetes":
            file_obj = (
                db.query(models.GeneratedKubernetesManifest)
                .filter_by(session_id=session_id, user_id=user.id)
                .order_by(models.GeneratedKubernetesManifest.created_at.desc())
                .first()
            )
        else:
            file_obj = None

        if not file_obj and engine != "audit":
            raise HTTPException(status_code=400, detail="Aucun fichier cible trouvé ou fourni.")
        if file_obj:
            file_id = file_obj.id
            file_path = file_obj.file_path
    else:
        file_path = retrieve_file_path_from_db_id(file_id, engine, db, user)
        if not file_path and engine != "audit":
            raise HTTPException(status_code=400, detail="Fichier cible introuvable.")

    # --- Inventaire (path + id) + auto-ad-hoc si selection
    inventory_path = None
    selected_inventory_id = inventory_id

    if engine in ["ansible"]:
        if selected_instance_ids:
            built = _build_inventory_from_selection(db, user.id, session_id, selected_instance_ids)
            if not built:
                raise HTTPException(status_code=400, detail="Aucune instance correspondante à selected_instance_ids.")
            inventory_path = built["inventory_path"]
            selected_inventory_id = built["inventory_id"]
        elif inventory_id:
            inventory_path = load_latest_inventory(inventory_id, db, user)
        else:
            if intent_id:
                inventory = (
                    db.query(models.GeneratedInventoryFile)
                    .filter_by(intent_id=intent_id, user_id=user.id)
                    .order_by(models.GeneratedInventoryFile.created_at.desc())
                    .first()
                )
            else:
                inventory = (
                    db.query(models.GeneratedInventoryFile)
                    .filter_by(user_id=user.id)
                    .order_by(models.GeneratedInventoryFile.created_at.desc())
                    .first()
                )
            if inventory:
                inventory_path = inventory.file_path
                selected_inventory_id = inventory.id

    # --- Extra data cohérente
    extra_data: Dict[str, Any] = {}
    if file_path:
        extra_data["path"] = file_path

    if engine in ["ansible"]:
        if inventory_path:
            extra_data["inventory_path"] = inventory_path
            if selected_inventory_id:
                extra_data["inventory_id"] = selected_inventory_id
        if selected_instance_ids:
            extra_data["selected_instance_ids"] = selected_instance_ids
    elif engine == "audit":
        instance_ids: List[str] = []
        if selected_instance_ids:
            instances = (
                db.query(models.Instance)
                .filter(models.Instance.id.in_(selected_instance_ids))
                .all()
            )
            instance_ids = [inst.instance_id for inst in instances if inst.instance_id]

        extra_data.update({
            "session_id": session_id,
            "region": region or "eu-north-1",
            "instance_ids": instance_ids,
            "recipe_names": recipe_names or ["ops_health"],
            "progress": 0,
            "progress_message": "En attente de lancement",
            "progress_phase": "pending",
        })
    elif engine == "kubernetes":
        extra_data["manifest_path"] = file_path
    elif engine == "terraform":
        extra_data["terraform_file_id"] = file_id

    #  Dernière clé privée disponible (chemin uniquement)
    try:
        private_key_path = get_latest_private_key_path()
        if private_key_path:
            extra_data["private_key_path"] = private_key_path
    except Exception as e:
        logger.warning(f"Impossible de récupérer la clé privée: {e}")

    # Déduire ssh_user/base_name depuis le fichier terraform (utile pour affichage)
    ssh_user, base_name = detect_ssh_user_and_basename(file_path if engine == "terraform" else None)
    extra_data["ssh_user"] = ssh_user
    extra_data["base_name"] = base_name

    # --- Upsert exécution (clé: user+session+type+target_file)
    existing_exec = (
        db.query(models.Execution)
        .filter_by(user_id=user.id, session_id=session.id, task_type=engine, target_file=file_id)
        .first()
    )

    if existing_exec:
        existing_exec.status = "pending"
        set_extra(existing_exec, extra_data)
        existing_exec.intent_id = intent_id
        existing_exec.inventory_id = selected_inventory_id
        existing_exec.updated_at = datetime.utcnow()
        db.commit()

        resp = {
            "execution_id": existing_exec.id,
            "target_file": file_id,
            "message": f" Exécution {engine} mise à jour avec succès."
        }
    else:
        execution = models.Execution(
            user_id=user.id,
            session_id=session.id,
            task_type=engine,
            status="pending",
            target_file=file_id,
            extra_data=extra_data,
            intent_id=intent_id,
            inventory_id=selected_inventory_id
        )
        db.add(execution)
        db.commit()
        db.refresh(execution)

        resp = {
            "execution_id": execution.id,
            "target_file": file_id,
            "message": f" Nouvelle exécution {engine} créée avec succès."
        }

    if engine in ["ansible"] and not extra_data.get("inventory_path"):
        resp.update({
            "status": "inventory_required",
            "candidates": _instances_to_candidates(db, session_id),
            "hint": "Construisez un inventaire (via sélection d’instances) puis relancez l’exécution.",
        })

    return resp


# -----------------------------
# Lancer une exécution
# -----------------------------
@router.post("/executions/{execution_id}/execute", tags=["Executions"], summary="Lancer une exécution")
async def execute_execution(
    request: Request,
    execution_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    #  P0.5 — IDEMPOTENCE CHECK
    idempotency_key = extract_idempotency_key(dict(request.headers))
    if not idempotency_key:
        raise HTTPException(
            status_code=400,
            detail="Header Idempotency-Key obligatoire pour /executions/{id}/execute"
        )
    
    # Vérifier ou créer la clé d'idempotence
    idempotency_result = check_or_create_idempotency_key(
        db=db,
        user_id=user.id,
        idempotency_key=idempotency_key,
        scope="execution.execute"
    )
    
    # Si déjà complétée, retourner le résultat mis en cache
    if idempotency_result.is_duplicate and idempotency_result.cached_response:
        return idempotency_result.cached_response
    
    logger.info(f" Exécution demandée : ID = {execution_id} pour l'utilisateur {user.id}")

    execution = db.query(models.Execution).filter_by(id=execution_id, user_id=user.id).first()
    if not execution:
        raise HTTPException(status_code=404, detail="Execution introuvable.")

    logger.info(f" Execution récupérée : type = {execution.task_type}, fichier cible = {execution.target_file}")

    # ============================================================
    # Thin controller : déléguer au service
    # ============================================================
    try:
        from app.services.execution_handlers import run_execution_by_id
        
        result = await run_execution_by_id(
            db=db,
            execution_id=execution_id,
            user_id=user.id
        )
        
        # P0.5 — MARK COMPLETED
        response = {"status": "ok", **(result or {})}
        mark_idempotency_completed(db, user.id, idempotency_key, "execution.execute", execution.id, json.dumps(response))
        return response

    except HTTPException as e:
        # Re-raise HTTP exceptions avec idempotency mark
        mark_idempotency_failed(db, user.id, idempotency_key, "execution.execute", str(e.detail))
        raise
    except Exception as e:
        # Other exceptions
        mark_idempotency_failed(db, user.id, idempotency_key, "execution.execute", str(e))
        raise HTTPException(status_code=500, detail=f"Erreur exécution : {str(e)}")


@router.get("/executions/{execution_id}", tags=["Executions"], summary="Voir une exécution")
def get_execution(
    execution_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    execution = db.query(models.Execution).filter_by(id=execution_id, user_id=user.id).first()
    if not execution:
        raise HTTPException(status_code=404, detail="Execution introuvable.")

    file_path = retrieve_file_path_from_db_id(execution.target_file, execution.task_type, db, user)
    target_file_name = os.path.basename(file_path) if file_path else None

    extra_data = get_extra(execution)

    # Extract progress tracking (Étape 4)
    progress = extra_data.get("progress", 0)
    progress_message = extra_data.get("progress_message")
    
    # If completed, ensure progress is 100%
    if execution.status == "completed" and (progress is None or progress < 100):
        progress = 100
        progress_message = progress_message or "Terminé"

    return {
        "execution_id": execution.id,
        "task_type": execution.task_type,
        "status": execution.status,
        "target_file": target_file_name,
        "inventory_path": os.path.basename(extra_data.get("inventory_path")) if extra_data.get("inventory_path") else None,
        "manifest_path": os.path.basename(extra_data.get("manifest_path")) if extra_data.get("manifest_path") else None,
        "logs": [log.message for log in execution.execution_logs],
        "created_at": execution.created_at.isoformat() if execution.created_at else None,
        "updated_at": execution.updated_at.isoformat() if execution.updated_at else None,
        "progress": progress,
        "progress_message": progress_message
    }
