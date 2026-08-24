# app/utils/file_utils.py
import os
import re
import unicodedata
from datetime import datetime
from typing import Optional, Tuple
import logging
import uuid  # <-- ajouté

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app import models
from app.utils.crypto import encrypt
from app.paths import GENERATED_ROOT as BASE_DIR

logger = logging.getLogger(__name__)

# ---------------------------
# Helpers noms / slug
# ---------------------------
def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")

def _slugify(s: str) -> str:
    s = _strip_accents(s or "").lower().strip()
    s = re.sub(r"[^a-z0-9._-]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "user"

def _user_slug_from_db(user_id: int) -> str:
    db = SessionLocal()
    try:
        u = db.query(models.User).filter_by(id=user_id).first()
        if not u:
            return f"user-{user_id}"
        base = u.email.split("@")[0] if getattr(u, "email", None) else (getattr(u, "username", None) or f"user-{user_id}")
        return _slugify(base)
    finally:
        db.close()

def _session_subdir(user_id: int, session_id: int, when: Optional[datetime] = None) -> str:
    """
    generated_files/<user>/<YYYY-MM-DD>/s<session_id>
    """
    when = when or datetime.utcnow()
    user_slug = _user_slug_from_db(user_id)
    return os.path.join(user_slug, when.strftime("%Y-%m-%d"), f"s{session_id}")

# ---------------------------
# Helpers Fichiers
# ---------------------------
def ensure_directory(path: str, private: bool = False):
    """
    Crée le dossier si nécessaire. Si 'private' est True (ex: private_keys),
    applique des permissions strictes 0700 au répertoire.
    """
    os.makedirs(path, exist_ok=True)
    try:
        if private:
            # 0700 pour empêcher toute écriture/lecture d'autres utilisateurs
            os.chmod(path, 0o700)
    except Exception as e:
        logger.warning(f"Impossible d'ajuster les permissions du dossier {path}: {e}")

def _is_private_keys_subdir(subdir: str) -> bool:
    # on considère 'private_keys' s'il est dans le chemin (compat sous-dossiers)
    parts = os.path.normpath(subdir).split(os.sep)
    return "private_keys" in parts

def save_file(content: str, subdir: str, filename: str) -> str:
    """
    Sauvegarde un fichier.
    - Pour les clés privées: dossier 0700, fichier 0400 après écriture.
      Si le fichier existe déjà (ex: 0400), on met temporairement 0600 pour l'écraser proprement.
    """
    folder_path = os.path.join(BASE_DIR, subdir)
    is_private = _is_private_keys_subdir(subdir)
    ensure_directory(folder_path, private=is_private)

    full_path = os.path.join(folder_path, filename)
    ensure_directory(os.path.dirname(full_path), private=is_private)

    # Si c'est une clé privée et que le fichier existe en lecture seule (0400),
    # on repasse temporairement en 0600 pour permettre l'écrasement.
    if is_private and os.path.exists(full_path):
        try:
            os.chmod(full_path, 0o600)
        except Exception as e:
            logger.warning(f"Impossible de mettre {full_path} en 0600 avant écriture: {e}")

    # Écriture (écrasement si existant)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)

    # permissions strictes pour clés privées
    if is_private:
        try:
            os.chmod(full_path, 0o400)
        except Exception as e:
            logger.warning(f"Impossible de mettre {full_path} en 0400 après écriture: {e}")

    return full_path

def detect_ssh_user_and_basename(file_path: str) -> Tuple[str, str]:
    if not file_path:
        return "ubuntu", "host"
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    ssh_user = "ubuntu"
    return ssh_user, base_name

# ---------------------------
# Création + persistance (paths lisibles)
#   BASE_DIR/<user>/<YYYY-MM-DD>/s<session>/(terraform|ansible|inventories|kubernetes|audits|private_keys)/
# ---------------------------
def create_and_store_terraform_file(
    user_id: int,
    session_id: int,
    filename: str,
    content: str,
    ssh_user: Optional[str] = None,
    base_name: Optional[str] = None,
):
    from app.models.generated_terraform_file import GeneratedTerraformFile

    base_subdir = os.path.join(_session_subdir(user_id, session_id), "terraform")
    path = save_file(content, base_subdir, filename)
    det_ssh_user, det_base_name = detect_ssh_user_and_basename(path)
    ssh_user = ssh_user or det_ssh_user
    base_name = base_name or det_base_name

    db = SessionLocal()
    try:
        tf_file = GeneratedTerraformFile(
            user_id=user_id,
            session_id=session_id,
            file_path=path,
            ssh_user=ssh_user,
            base_name=base_name,
            created_at=datetime.utcnow(),
        )
        db.add(tf_file)
        db.commit()
        db.refresh(tf_file)
        return tf_file
    finally:
        db.close()

def create_and_store_playbook(
    user_id: int,
    session_id: int,
    filename: str,
    content: str,
    ssh_user: Optional[str] = None,
):
    from app.models.generated_playbook import GeneratedPlaybook

    base_subdir = os.path.join(_session_subdir(user_id, session_id), "ansible")
    path = save_file(content, base_subdir, filename)
    det_ssh_user, _ = detect_ssh_user_and_basename(path)
    ssh_user = ssh_user or det_ssh_user

    db = SessionLocal()
    try:
        pb = GeneratedPlaybook(
            user_id=user_id,
            session_id=session_id,
            file_path=path,
            ssh_user=ssh_user,
            created_at=datetime.utcnow(),
        )
        db.add(pb)
        db.commit()
        db.refresh(pb)
        return pb
    finally:
        db.close()

def create_and_store_inventory(user_id: int, session_id: int, filename: str, content: str):
    """
    Écrit l'inventaire et l'enregistre en BDD avec un 'filename' **non nul**.
    """
    from app.models.generated_inventory_file import GeneratedInventoryFile

    base_subdir = os.path.join(_session_subdir(user_id, session_id), "inventories")

    # --- Assurer un filename sûr & non nul
    if not filename or not str(filename).strip():
        filename = f"inventory_{uuid.uuid4().hex[:8]}.ini"
    filename = os.path.basename(str(filename).strip())
    if not filename.lower().endswith(".ini"):
        filename = f"{filename}.ini"

    # --- Sauvegarde disque
    path = save_file(content, base_subdir, filename)

    # --- Persistance BDD (avec filename obligatoire)
    db = SessionLocal()
    try:
        inv = GeneratedInventoryFile(
            user_id=user_id,
            session_id=session_id,
            filename=filename,        # <-- plus jamais NULL
            file_path=path,
            created_at=datetime.utcnow(),
        )
        db.add(inv)
        db.commit()
        db.refresh(inv)
        return inv
    finally:
        db.close()

def create_and_store_kube_manifest(user_id: int, session_id: int, filename: str, content: str):
    from app.models.generated_kubernetes_manifest import GeneratedKubernetesManifest

    base_subdir = os.path.join(_session_subdir(user_id, session_id), "kubernetes")
    path = save_file(content, base_subdir, filename)
    db = SessionLocal()
    try:
        manifest = GeneratedKubernetesManifest(
            user_id=user_id,
            session_id=session_id,
            file_path=path,
            created_at=datetime.utcnow(),
        )
        db.add(manifest)
        db.commit()
        db.refresh(manifest)
        return manifest
    finally:
        db.close()

def create_and_store_audit_file(user_id: int, session_id: int, filename: str, content: str):
    from app.models.generated_audit_file import GeneratedAuditFile

    base_subdir = os.path.join(_session_subdir(user_id, session_id), "audits")
    path = save_file(content, base_subdir, filename)
    db = SessionLocal()
    try:
        audit = GeneratedAuditFile(
            user_id=user_id,
            session_id=session_id,
            file_path=path,
            created_at=datetime.utcnow(),
        )
        db.add(audit)
        db.commit()
        db.refresh(audit)
        return audit
    finally:
        db.close()

def create_and_store_private_key(user_id: int, session_id: int, filename: str, private_key_str: str):
    """
    - Écrit la clé **en clair** sur disque (permissions 0400) pour SSH/Ansible.
    - Stocke **la version chiffrée** en base (content).
    - Supporte la réécriture même si une clé existe déjà en 0400.
    """
    from app.models.generated_private_key import GeneratedPrivateKey

    encrypted_key = encrypt(private_key_str)
    base_subdir = os.path.join(_session_subdir(user_id, session_id), "private_keys")
    path = save_file(private_key_str, base_subdir, filename)  # save_file gère chmod 0600 -> write -> 0400

    db = SessionLocal()
    try:
        private_key = GeneratedPrivateKey(
            user_id=user_id,
            session_id=session_id,
            file_path=path,           # chemin vers la version en clair (utilisable)
            content=encrypted_key,    # contenu chiffré en base
            fingerprint=None,
            created_at=datetime.utcnow(),
        )
        db.add(private_key)
        db.commit()
        db.refresh(private_key)
        return private_key
    finally:
        db.close()

# ---------------------------
# Utilitaires Exécutions
# ---------------------------
def _find_latest_file_recursive(root_dir: str) -> Optional[str]:
    if not os.path.isdir(root_dir):
        return None
    latest_path = None
    latest_mtime = -1.0
    for cur, _dirs, files in os.walk(root_dir):
        for f in files:
            p = os.path.join(cur, f)
            try:
                m = os.path.getmtime(p)
                if m > latest_mtime:
                    latest_mtime = m
                    latest_path = p
            except Exception:
                continue
    return latest_path

def load_latest_generated_file(subdir: str) -> Optional[str]:
    """
    Recherche récursive du dernier fichier modifié sous BASE_DIR/**/<subdir>.
    Exemple: subdir="inventories", on balaie tous les sous-dossiers utilisateurs/sessions.
    """
    latest = None
    latest_mtime = -1.0
    for cur, dirs, files in os.walk(BASE_DIR):
        if os.path.basename(cur) == subdir:
            cand = _find_latest_file_recursive(cur)
            if cand:
                m = os.path.getmtime(cand)
                if m > latest_mtime:
                    latest_mtime = m
                    latest = cand
    return latest

def load_latest_inventory(inventory_id: int, db: Session, user: models.User) -> Optional[str]:
    if inventory_id:
        inv = db.query(models.GeneratedInventoryFile).filter_by(id=inventory_id, user_id=user.id).first()
        return inv.file_path if inv else None
    # fallback: chercher récursivement tout dossier "inventories"
    return load_latest_generated_file("inventories")

def retrieve_file_path_from_db_id(file_id: int, engine: str, db: Session, user: models.User) -> Optional[str]:
    if engine == "terraform":
        file = db.query(models.GeneratedTerraformFile).filter_by(id=file_id, user_id=user.id).first()
    elif engine == "ansible":
        file = db.query(models.GeneratedPlaybook).filter_by(id=file_id, user_id=user.id).first()
    elif engine == "audit":
        file = db.query(models.GeneratedAuditFile).filter_by(id=file_id, user_id=user.id).first()
    elif engine == "kubernetes":
        file = db.query(models.GeneratedKubernetesManifest).filter_by(id=file_id, user_id=user.id).first()
    else:
        return None
    return file.file_path if file else None

def get_generated_file_path(file_id: int, engine: str, db: Session, user: models.User) -> Optional[str]:
    return retrieve_file_path_from_db_id(file_id, engine, db, user)

# ---------------------------
# Clé privée (exécution)
# ---------------------------
def get_latest_private_key_path() -> str:
    """
    Retourne le **chemin** de la dernière clé privée (en clair) pour SSH/Ansible.
    """
    from app.models.generated_private_key import GeneratedPrivateKey
    db = SessionLocal()
    try:
        latest = db.query(GeneratedPrivateKey).order_by(GeneratedPrivateKey.created_at.desc()).first()
        if not latest or not latest.file_path or not os.path.exists(latest.file_path):
            raise FileNotFoundError("Aucune clé privée utilisable trouvée.")
        return latest.file_path
    finally:
        db.close()

# ---------------------------
# Helpers lecture
# ---------------------------
def get_k8s_manifest_content(file_path: str) -> str:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        raise Exception(f"Erreur lors de la lecture du manifeste Kubernetes : {e}")

def get_private_key_content(file_path: str) -> str:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        raise Exception(f"Erreur lors de la lecture de la clé privée : {e}")

def get_inventory_file_path(inventory_path: str) -> str:
    if not inventory_path or not os.path.exists(inventory_path):
        raise Exception(f"Fichier d'inventaire introuvable : {inventory_path}")
    return inventory_path
