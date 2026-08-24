# app/routes/generate_ansible.py
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from app import models, database
from app.auth import get_current_user
from app.services.gpt_service import generate_instructions_from_gpt
from app.services.ansible_service import validate_ansible_playbook
from app.services.intent_parser import parse_intent
from app.utils.file_utils import create_and_store_playbook

import os
import re
import uuid
from typing import Optional, Union, Set

router = APIRouter()


def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _os_hints_from_session(db: Session, session_id: int) -> Set[str]:
    """
    Déduit les familles d'OS présentes/attendues sans dépendre d'un modèle Instance.
    1) Regarde le dernier inventaire généré de la session.
    2) Sinon, déduit depuis le dernier intent 'create'.
    """
    fam: Set[str] = set()

    # 1) Inventaire le plus récent de la session
    inv = (
        db.query(models.GeneratedInventoryFile)
        .filter_by(session_id=session_id)
        .order_by(models.GeneratedInventoryFile.created_at.desc())
        .first()
    )
    if inv and inv.file_path and os.path.exists(inv.file_path):
        try:
            with open(inv.file_path, "r", encoding="utf-8") as f:
                inv_txt = f.read()
        except Exception:
            inv_txt = ""

        low = inv_txt.lower()
        if ("winrm" in low) or ("ansible_connection=winrm" in low):
            fam.add("windows")
        if re.search(r"\bubuntu\b|\bdebian\b", low):
            fam.add("debian/ubuntu")
        if re.search(r"\brhel\b|\bredhat\b|\bcentos\b|\brocky\b", low):
            fam.add("rhel/centos/rocky")
        if re.search(r"\bamazon\b|\bamzn\b", low):
            fam.add("amazon linux")
        if re.search(r"\bsles\b|\bsuse\b", low):
            fam.add("sles/suse")

    if fam:
        return fam

    # 2) Fallback : déduction depuis le dernier intent 'create'
    cr = (
        db.query(models.Intent)
        .filter_by(session_id=session_id, intent_type="create")
        .order_by(models.Intent.created_at.desc())
        .first()
    )
    if cr:
        try:
            parsed = parse_intent(cr.prompt)
            for a in (parsed.actions or []):
                if getattr(a, "type", None) == "create":
                    for vm in (getattr(a, "vms", None) or []):
                        o = (getattr(vm, "os", "") or "").lower()
                        if "windows" in o:
                            fam.add("windows")
                        elif "ubuntu" in o or "debian" in o:
                            fam.add("debian/ubuntu")
                        elif any(k in o for k in ["rhel", "redhat", "centos", "rocky"]):
                            fam.add("rhel/centos/rocky")
                        elif "amazon" in o or "amzn" in o:
                            fam.add("amazon linux")
                        elif "sles" in o or "suse" in o:
                            fam.add("sles/suse")
        except Exception:
            pass

    return fam


@router.post(
    "/generate/ansible",
    tags=["Génération"],
    summary="Générer un playbook Ansible à partir d’un intent (mode system/mixed)."
)
async def post_generate_ansible(
    intent_id: int = Body(..., description="ID de l'intention existante"),
    target_path: Optional[str] = Body(None, description="Nom de fichier suggéré par le plan (ex: system_service.yml)"),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return await generate_ansible(intent_id=intent_id, target_path=target_path, db=db, user=user)


async def generate_ansible(
    intent_id: int,
    target_path: Optional[Union[str, os.PathLike]] = None,
    db: Session = None,
    user: models.User = None,
):
    # 1) Intent sécurisé (appartenance à l’utilisateur via la session)
    intent = (
        db.query(models.Intent)
        .filter(models.Intent.id == intent_id)
        .join(models.Session)
        .filter(models.Session.user_id == user.id)
        .first()
    )
    if not intent:
        raise HTTPException(status_code=404, detail="Intent introuvable ou non autorisé.")
    if (intent.intent_type or "").lower() != "configure":
        raise HTTPException(status_code=400, detail="Cette route ne gère que les intents de type 'configure'.")

    # 2) Mode & domaine (priorité DB, fallback parseur)
    mode = (intent.configure_mode or "").strip().lower()
    domain = (intent.configure_domain or "").strip().lower()
    if not mode or not domain:
        try:
            parsed = parse_intent(intent.prompt)
            cfg = next((a for a in (parsed.actions or []) if getattr(a, "type", "") == "configure"), None)
            if cfg:
                mode = mode or (getattr(cfg, "mode", "") or "").strip().lower()
                doms = getattr(cfg, "domains", None) or []
                if doms:
                    domain = domain or (doms[0] or "").strip().lower()
        except Exception:
            pass

    mode = mode or "system"
    domain = domain or "system_service"

    # Uniquement system|mixed ici (infra => Terraform)
    if mode == "infra":
        raise HTTPException(status_code=400, detail="Le mode 'infra' doit être généré via Terraform.")
    if mode not in ("system", "mixed"):
        raise HTTPException(status_code=400, detail=f"Mode incompatible: {mode}. Autorisés: system|mixed.")

    allowed_domains = {"system_service", "system_firewall"}
    if domain not in allowed_domains:
        raise HTTPException(
            status_code=400,
            detail=f"Domaine Ansible non supporté: {domain}. Autorisés: {sorted(allowed_domains)}"
        )

    # 3) Indices d'OS supplémentaire depuis l’inventaire (pour enrichir le prompt)
    inventory_hint = ""
    inv = (
        db.query(models.GeneratedInventoryFile)
        .filter_by(session_id=intent.session.id, user_id=user.id)
        .order_by(models.GeneratedInventoryFile.created_at.desc())
        .first()
    )
    if inv and inv.file_path and os.path.exists(inv.file_path):
        try:
            with open(inv.file_path, "r", encoding="utf-8") as f:
                inv_txt = f.read()
        except Exception:
            inv_txt = ""
        low = inv_txt.lower()
        detected = []
        if ("winrm" in low) or ("ansible_connection=winrm" in low):
            detected.append("windows")
        if re.search(r"\bubuntu\b|\bdebian\b", low):
            detected.append("debian/ubuntu")
        if re.search(r"\brhel\b|\bredhat\b|\bcentos\b|\brocky\b", low):
            detected.append("rhel/centos/rocky")
        if re.search(r"\bamazon\b|\bamzn\b", low):
            detected.append("amazon linux")
        if re.search(r"\bsles\b|\bsuse\b", low):
            detected.append("sles/suse")
        if detected:
            inventory_hint = " | OS détectés: " + ", ".join(detected)

    # 4) RUNTIME
    runtime = (intent.runtime or "system").strip().lower()
    if runtime == "docker":
        runtime_rules = (
            " RUNTIME=DOCKER : Installer Docker (si absent) puis réaliser la configuration "
            "via les modules community.docker.* (pas de config directe de l'hôte hors install Docker)."
        )
    elif runtime == "k8s":
        runtime_rules = (
            " RUNTIME=K8S : Utiliser kubernetes.core.k8s / kubernetes.core.helm pour appliquer la configuration."
        )
    else:
        runtime_rules = " RUNTIME=SYSTEM : Configurer directement les hôtes (packages natifs + services)."

    # 5) Prompt GPT (YAML pur multi-OS, strict)
    prompt = (
        "Tu es un assistant DevOps ULTRA-expert en Ansible.\n"
        f"{runtime_rules}\n"
        f"{inventory_hint}\n\n"
        " Objectif : Générer un **playbook YAML pur** (sans markdown, sans commentaires) "
        "qui applique la tâche suivante, en s'adaptant automatiquement à chaque hôte :\n"
        f"{intent.prompt}\n\n"
        " Contraintes de sortie (OBLIGATOIRES) :\n"
        "- YAML strict uniquement, aucune explication, aucun balisage Markdown.\n"
        "- Un seul play :\n"
        "  - - hosts: all\n"
        "  - gather_facts: true\n"
        "  - become: true au niveau play ; toutes les tâches Windows doivent avoir become: false.\n"
        "  - tasks: avec des name: clairs et uniques.\n"
        "- Utiliser les FQCN pour tous les modules (ansible.builtin.apt/dnf/yum/zypper/package, "
        "community.docker.*, ansible.windows.*, kubernetes.core.*).\n"
        "- Une seule action par tâche ; si deux actions sont nécessaires, créer deux tâches.\n"
        "- Idempotent et rejouable : creates:/removes:/when:/loop: si pertinent.\n"
        "- CRITIQUE — Structure des tâches : register, ignore_errors, changed_when, when, loop, retries, delay "
        "doivent être au même niveau que le module et name: (niveau tâche). Interdit de les placer dans "
        "les paramètres du module.\n\n"
        " Routage par OS/Distro :\n"
        "- Utiliser les facts (ansible_os_family, ansible_distribution, ansible_distribution_major_version).\n"
        "- Windows : ansible.windows.* exclusivement (choco si nécessaire), become: false.\n"
        "- Debian/Ubuntu : ansible.builtin.apt (installer iproute2 et python3-pip si nécessaire).\n"
        "- RHEL/CentOS/Rocky : ansible.builtin.dnf ou ansible.builtin.yum selon la version.\n"
        "- Amazon Linux : AL2023 -> dnf, AL2 -> yum.\n"
        "- SLES/SUSE : ansible.builtin.zypper.\n\n"
        " Vérification dynamique des ports (standardisée) :\n"
        "- Pour chaque port publié (Docker/Nginx/services), ajouter une détection de port libre P, P+100, P+200, "
        "P+300, P+400 (Linux via ss/netstat, Windows via PowerShell) ; définir port_P via set_fact.\n"
        "- Remapper toutes les publications pour utiliser {{ port_P }} (ex: 127.0.0.1:{{ port_80 }}:80/tcp).\n"
        '- Taguer ces tâches: ["port-guard-P"].\n\n'
        " Docker :\n"
        "- community.docker.docker_container avec restart_policy: always ; pas de network_mode: host.\n"
        "- Capturer les logs avec register + ignore_errors: true, changed_when: false.\n\n"
        " Services & validations :\n"
        "- Valider la config avant restart (ex: nginx -t).\n"
        "- En cas d’échec : systemctl status / journalctl -xeu / logs conteneur avec register + debug.\n"
        "- daemon_reload: true si nécessaire.\n\n"
        " Timeouts :\n"
        "- Toute commande shell/command doit inclure timeout 30s.\n\n"
        " Sortie attendue : YAML pur uniquement, sans texte ni ```."
    )

    # 5.1) Limiter explicitement aux OS détectés sur la session
    os_hints = _os_hints_from_session(db, intent.session.id)
    if os_hints:
        allowed = ", ".join(sorted(os_hints))
        prompt += (
            "\n\n Spécification d'OS: "
            f"Ne génère des tâches QUE pour ces familles détectées dans cette session: {allowed}. "
            "N'ajoute aucune tâche pour d'autres OS."
        )

    # 6) Génération -> nettoyage -> validation
    try:
        gpt_response = await generate_instructions_from_gpt(prompt)
    except Exception as e:
        if hasattr(models.Intent, "generation_status"):
            intent.generation_status = "failed"
            if hasattr(models.Intent, "generation_error"):
                intent.generation_error = f"gpt_error: {e}"
            db.commit()
        raise

    ansible_code = (gpt_response or "").strip()
    if ansible_code.startswith("```"):
        ansible_code = (
            ansible_code.replace("```yaml", "")
            .replace("```yml", "")
            .replace("```", "")
            .strip()
        )

    if not ansible_code or "hosts:" not in ansible_code:
        if hasattr(models.Intent, "generation_status"):
            intent.generation_status = "failed"
            if hasattr(models.Intent, "generation_error"):
                intent.generation_error = "invalid_ansible_from_gpt"
            db.commit()
        raise HTTPException(status_code=500, detail="Réponse Ansible invalide:\n" + (gpt_response or ""))

    # Valide/patch via service
    patched = validate_ansible_playbook(ansible_code)
    final_code = patched or ansible_code

    # 7) Sauvegarde (respecte target_path si fourni -> on ne garde que le basename)
    safe_username = user.email.split("@")[0].replace(".", "_")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M")
    short_uuid = str(uuid.uuid4())[:6]

    if target_path:
        base = os.path.basename(os.fspath(target_path))
        filename = base if base.endswith((".yml", ".yaml")) else f"{base}.yml"
    else:
        filename = f"ansible_{safe_username}_s{intent.session.id}_{timestamp}_{short_uuid}.yml"

    playbook = create_and_store_playbook(
        user_id=user.id,
        session_id=intent.session.id,
        filename=filename,
        content=final_code
    )

    # 8) Marquer l’intent comme généré si la colonne existe
    if hasattr(models.Intent, "generation_status"):
        intent.generation_status = "generated"
        if hasattr(models.Intent, "generated_at"):
            intent.generated_at = datetime.now(timezone.utc)
        if hasattr(models.Intent, "generation_error"):
            intent.generation_error = None
        db.commit()

    return {
        "status": "success",
        "engine": "ansible",
        "domain": domain,
        "runtime": (intent.runtime or "system").lower(),
        "playbook_id": playbook.id,
        "filename": playbook.file_path,
        "message": " Playbook Ansible multi-OS généré et stocké. Exécute-le via /executions/create."
    }
