# app/routes/inventories_routes.py
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any

from app import models, database
from app.auth import get_current_user
from app.services.ansible_inventory import generate_inventory_from_executions
from app.utils.crypto import decrypt

router = APIRouter()


def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post(
    "/inventories/generate",
    tags=["Ansible - Inventaire"],
    summary="Générer un fichier d'inventaire Ansible à partir d'instances OU d'une liste d'hôtes"
)
def generate_inventory(
    instance_ids: Optional[List[int]] = Body(
        None, embed=True, description="IDs d'instances BDD à inclure"
    ),
    hosts: Optional[List[Dict[str, Any]]] = Body(
        None, embed=True,
        description="Hôtes libres: {ip, name?, ssh_user?, os_family?, distro?, private_key?, runtime?, win_password?}"
    ),
    session_id: Optional[int] = Body(None, embed=True),
    intent_id: Optional[int] = Body(None, embed=True),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    """
    Sources:
      - instance_ids: récupère depuis la BDD (IP/clé potentiellement chiffrées)
      - hosts: entrées libres (IP en clair, clé optionnelle)
    Règles:
      - ssh_user défaut: ubuntu ; os_family défaut: linux ; distro défaut: unknown
      - session_id: requis (déduit des instances si non fourni et cohérentes)
      - runtime: si intent_id fourni, appliqué en défaut
    """
    items: List[Dict[str, Any]] = []

    # ----- 0) Runtime par défaut depuis l'intent (optionnel) -----
    runtime_default: Optional[str] = None
    if intent_id:
        intent = db.query(models.Intent).filter_by(id=intent_id).first()
        if not intent or intent.session.user_id != user.id:
            raise HTTPException(status_code=403, detail="Intent non autorisé.")
        runtime_default = getattr(intent, "runtime", None)

    # ----- 1) Flux "instances BDD" -----
    if instance_ids:
        instances = db.query(models.Instance).filter(
            models.Instance.id.in_(instance_ids),
            models.Instance.session.has(user_id=user.id)
        ).all()
        if not instances:
            raise HTTPException(status_code=404, detail="Aucune instance trouvée pour les IDs fournis.")

        # Déduire session_id si absent + vérifier unicité de session
        sess_ids = {inst.session_id for inst in instances}
        if len(sess_ids) > 1:
            raise HTTPException(status_code=400, detail="Toutes les instances doivent appartenir à la même session.")
        if session_id is None:
            session_id = next(iter(sess_ids))

        for inst in instances:
            # IP peut être chiffrée en base
            try:
                ip = decrypt(inst.public_ip) if inst.public_ip else None
            except Exception:
                ip = inst.public_ip

            if not ip:
                # on ignore les entrées sans IP
                continue

            item = {
                "name":        inst.name or inst.hostname or f"instance-{inst.id}",
                "ip":          ip,
                "ssh_user":    (inst.ssh_user or "ubuntu"),
                "private_key": getattr(inst, "ssh_private_key", None),  # chiffrée gérée côté service
                "os_family":   (inst.os_family or "linux").lower(),
                "distro":      (inst.distro or "unknown").lower(),
                "runtime":     getattr(inst, "runtime", None) or runtime_default,
            }

            # Support Windows: password optionnel (clair ou chiffré)
            if item["os_family"] == "windows":
                win_pwd = getattr(inst, "win_password", None)
                if win_pwd:
                    item["win_password"] = win_pwd
                    item["win_password_encrypted"] = getattr(inst, "win_password_encrypted", False)

            items.append(item)

    # ----- 2) Flux "hosts libres" -----
    if hosts:
        for idx, h in enumerate(hosts, start=1):
            ip = str(h.get("ip", "")).strip()
            if not ip:
                continue

            name = (h.get("name") or f"host-{idx}").strip()
            ssh_user = (h.get("ssh_user") or "ubuntu").strip()
            os_family = str(h.get("os_family") or "linux").lower().strip()
            distro = str(h.get("distro") or "unknown").lower().strip()
            runtime = (h.get("runtime") or runtime_default)

            item = {
                "name": name,
                "ip": ip,
                "ssh_user": ssh_user,
                "private_key": h.get("private_key"),
                "os_family": os_family,
                "distro": distro,
                "runtime": runtime,
            }

            # Support Windows libre (password optionnel)
            if os_family == "windows":
                if "win_password" in h and h["win_password"]:
                    item["win_password"] = h["win_password"]
                    item["win_password_encrypted"] = h.get("win_password_encrypted", False)

            items.append(item)

    # ----- 3) session_id requis à ce stade -----
    if session_id is None:
        raise HTTPException(status_code=400, detail="session_id est requis (ou déductible des instances).")

    if not items:
        raise HTTPException(
            status_code=400,
            detail="Aucune source fournie. Passez 'instance_ids' et/ou 'hosts'."
        )

    # ----- 4) Génération finale -----
    inventory_path, inventory_id = generate_inventory_from_executions(
        instances=items,
        user_id=user.id,
        db=db,
        session_id=session_id,
        intent_id=intent_id
    )

    return {
        "status": "success",
        "inventory_path": inventory_path,
        "inventory_id": inventory_id,
        "count": len(items),
        "message": "Inventaire généré.",
    }
