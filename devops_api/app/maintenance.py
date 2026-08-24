# app/maintenance.py
import os, time, logging
from datetime import datetime
from typing import Iterable
from app.paths import GENERATED_ROOT, LOGS_DIR, SUBDIRS

log = logging.getLogger(__name__)

# Env (avec valeurs par défaut raisonnables)
RETENTION_DAYS = int(os.getenv("FILE_RETENTION_DAYS", "7"))
MAX_DISK_GB    = float(os.getenv("MAX_DISK_USAGE_GB", "8"))
CHECK_EVERY_S  = int(os.getenv("JANITOR_INTERVAL_SECONDS", "1800"))  # 30 min
MAX_LOG_SIZE_B = int(os.getenv("MAX_LOG_SIZE_BYTES", str(10 * 1024 * 1024)))  # 10MB
LOG_BACKUPS    = int(os.getenv("LOG_BACKUPS", "5"))

def _iter_files(root: str) -> Iterable[str]:
    for dp, _, files in os.walk(root):
        for f in files:
            yield os.path.join(dp, f)

def rotate_log_file(path: str) -> None:
    """Rotation simple: .1, .2, ... jusqu’à LOG_BACKUPS."""
    try:
        if not os.path.exists(path) or os.path.getsize(path) <= MAX_LOG_SIZE_B:
            return
        # Décale les backups
        for i in range(LOG_BACKUPS, 0, -1):
            old = f"{path}.{i}"
            older = f"{path}.{i+1}"
            if os.path.exists(old):
                if i == LOG_BACKUPS:
                    try: os.remove(old)
                    except Exception: pass
                else:
                    try: os.replace(old, older)
                    except Exception: pass
        # Renomme le courant en .1 puis recrée fichier vide
        try: os.replace(path, f"{path}.1")
        except Exception: pass
        try: open(path, "w").close()
        except Exception: pass
        log.info(f"[rotate] {path}")
    except Exception as e:
        log.warning(f"[rotate] erreur sur {path}: {e}")

def janitor_once() -> None:
    """Un passage de ménage: suppression vieux fichiers + quota + rotation logs."""
    now = datetime.now()

    # 1) Retention par âge
    removed = 0
    for f in _iter_files(GENERATED_ROOT):
        try:
            age_days = (now - datetime.fromtimestamp(os.path.getmtime(f))).days
            if age_days > RETENTION_DAYS:
                os.remove(f)
                removed += 1
        except Exception:
            pass
    if removed:
        log.info(f"[janitor] {removed} fichiers supprimés (> {RETENTION_DAYS} j)")

    # 2) Quota disque
    all_files = [p for p in _iter_files(GENERATED_ROOT)]
    total_gb = sum((os.path.getsize(p) for p in all_files), 0) / (1024**3)
    if total_gb > MAX_DISK_GB:
        log.warning(f"[janitor] {total_gb:.2f}GB utilisés (> {MAX_DISK_GB}GB). Purge…")
        # supprime les plus anciens jusqu’à repasser sous le quota
        all_files.sort(key=lambda p: os.path.getmtime(p))  # plus anciens d’abord
        while total_gb > MAX_DISK_GB and all_files:
            p = all_files.pop(0)
            try:
                sz = os.path.getsize(p) / (1024**3)
                os.remove(p)
                total_gb -= sz
                log.info(f"[janitor] supprimé: {p}")
            except Exception:
                pass

    # 3) Rotation des logs seulement
    if os.path.isdir(LOGS_DIR):
        for p in _iter_files(LOGS_DIR):
            rotate_log_file(p)

def janitor_loop(blocking: bool = False) -> None:
    """Boucle périodique; à lancer en thread de fond."""
    try:
        while True:
            janitor_once()
            if blocking:
                time.sleep(CHECK_EVERY_S)
                continue
            # si non-blocking, on sort après un passage
            break
    except Exception as e:
        log.error(f"[janitor] erreur: {e}")
