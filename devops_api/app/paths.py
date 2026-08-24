# app/paths.py
import os
import logging

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

GENERATED_ROOT = os.getenv(
    "GENERATED_ROOT",
    os.path.join(BASE_DIR, "..", "generated_files")
)
GENERATED_ROOT = os.path.abspath(GENERATED_ROOT)

SUBDIRS = [
    "tf",
    "playbooks",
    "kubernetes",
    "logs",
    "private_keys",
    "audits",
    "monitoring",
    "inventories",
]

TF_DIR = os.path.join(GENERATED_ROOT, "tf")
PLAYBOOKS_DIR = os.path.join(GENERATED_ROOT, "playbooks")
K8S_DIR = os.path.join(GENERATED_ROOT, "kubernetes")
LOGS_DIR = os.path.join(GENERATED_ROOT, "logs")
PRIVATE_KEYS_DIR = os.path.join(GENERATED_ROOT, "private_keys")
AUDITS_DIR = os.path.join(GENERATED_ROOT, "audits")
MONITORING_DIR = os.path.join(GENERATED_ROOT, "monitoring")
INVENTORIES_DIR = os.path.join(GENERATED_ROOT, "inventories")

def _touch_gitignore(path: str) -> None:
    try:
        gi = os.path.join(path, ".gitignore")
        if not os.path.exists(gi):
            with open(gi, "w") as f:
                f.write("*\n!.gitignore\n")
    except Exception:
        pass

def safe_join(subdir: str, filename: str) -> str:
    base = os.path.join(GENERATED_ROOT, subdir)
    full = os.path.abspath(os.path.join(base, filename))
    if not full.startswith(os.path.abspath(base) + os.sep):
        raise ValueError("Chemin invalide (path traversal).")
    return full

def ensure_dirs() -> None:
    try:
        os.makedirs(GENERATED_ROOT, exist_ok=True)
        try:
            os.chmod(GENERATED_ROOT, 0o750)
        except Exception:
            pass

        for sub in SUBDIRS:
            p = os.path.join(GENERATED_ROOT, sub)
            os.makedirs(p, exist_ok=True)
            _touch_gitignore(p)

        try:
            os.chmod(PRIVATE_KEYS_DIR, 0o700)
        except Exception:
            pass

        logger.info(f"[paths] Dossiers prêts: {GENERATED_ROOT}")
    except PermissionError:
        logger.warning(
            f"[paths] Permission refusée pour {GENERATED_ROOT}. "
            "Le disque persistant n'est peut-être pas monté."
        )
    except Exception as e:
        logger.error(f"[paths] Erreur création des dossiers: {e}")
