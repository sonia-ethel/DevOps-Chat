# app/services/plan_builder.py
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import re
import unicodedata
import hashlib

from app import models
from app.services.intent_parser import parse_intent  # parseur déterministe (dataclasses)

# 
# Orchestration Terraform (ordre des domaines infra)
# 
ORDER: Dict[str, int] = {
    "cloud_network": 10,
    "identity_access": 20,
    "storage": 30,
    "database": 40,
    "container_orchestration": 50,
    "compute": 60,
    "balancer_gateway": 70,
    "cdn": 80,
    # NOTE: selon stratégie (ACM DNS vs TLS sur VM), dns_tls peut être déplacé plus tôt.
    "dns_tls": 90,
    "observability": 100,
    "queue_stream": 110,
}
INFRA_DOMAIN_SET = set(ORDER.keys())


def _order_key(domain: str) -> int:
    # Domaines non répertoriés -> en fin de plan mais avant observability/queue_stream par défaut
    return ORDER.get(domain, 95)


# 
# Helpers pour chemins lisibles: generated/<user>/<YYYY-MM-DD>/s<session>/…
# 
def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")

def _slugify(s: str) -> str:
    s = _strip_accents(s or "").lower().strip()
    s = re.sub(r"[^a-z0-9._-]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "user"

def _hash8(s: str) -> str:
    return hashlib.sha1((s or "").encode()).hexdigest()[:8]

def _plan_base_subdir(db: Session, session_id: int) -> str:
    """Retourne le sous-dossier lisible pour une session: <user>/<YYYY-MM-DD>/s<session>"""
    session = db.query(models.Session).filter(models.Session.id == session_id).first()
    if not session:
        return f"unknown/{datetime.now(timezone.utc).strftime('%Y-%m-%d')}/s{session_id}"

    user = db.query(models.User).filter(models.User.id == session.user_id).first()
    email_or_name = (user.email.split("@")[0] if user and user.email else (getattr(user, "username", None) or f"user-{session.user_id}"))
    user_slug = _slugify(email_or_name)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"{user_slug}/{date_str}/s{session_id}"


# 
# Extraction specs "create"
# 
def _extract_create_specs(prompt: str) -> Optional[Dict[str, Any]]:
    """
    Extrait (provider, vms) depuis le prompt de l'intent 'create' via parse_intent().
    Retourne None si rien d'exploitable.
    """
    parsed = parse_intent(prompt)
    if not parsed or not parsed.actions:
        return None

    create_actions = [a for a in parsed.actions if a.type == "create"]
    if not create_actions:
        return None

    ca = create_actions[0]
    vms = [{"os": vm.os, "count": vm.count} for vm in (ca.vms or [])]
    if not vms and not ca.provider:
        return None

    return {"provider": (ca.provider or "aws"), "vms": vms}


# 
# Build plan (regroupe les domaines infra par sous-prompt)
# 
def build_plan(db: Session, session_id: int) -> Dict[str, Any]:
    q = (
        db.query(models.Intent)
        .filter(models.Intent.session_id == session_id)
        .order_by(models.Intent.created_at.asc())
    )

    #  Si la colonne d’état existe, on ne garde que les intents à traiter (pending/failed)
    #    -> évite de regénérer ce qui a déjà été produit dans la même session.
    if hasattr(models.Intent, "generation_status"):
        from sqlalchemy import or_
        try:
            # Enum côté modèle -> compare via .in_
            q = q.filter(models.Intent.generation_status.in_(["pending", "failed"]))
        except Exception:
            # Si l'enum diffère, fallback: on prend tout (compat)
            pass

    intents: List[models.Intent] = q.all()

    base_subdir = _plan_base_subdir(db, session_id)  # ex: arnaud/2025-09-10/s1
    plan: List[Dict[str, Any]] = []
    vm_specs: List[Dict[str, Any]] = []

    # Rien à faire ?
    if not intents:
        return {
            "status": "empty",
            "engine": "multi",
            "plan": [],
            "message": "Aucun intent en attente pour cette session (déjà générés ou inexistants).",
            "vm_specs": None,
        }

    # 1) Intents "create" -> step Terraform 'compute' (fichier unique par intent)
    for it in intents:
        if it.intent_type != "create":
            continue

        specs = _extract_create_specs(it.prompt or "")
        if not specs:
            continue  # Rien d'exploitable

        vm_specs.append({
            "provider": specs.get("provider") or "aws",
            "vms": specs.get("vms", []),  # [{os, count}]
        })

        #  Fichier unique par intent pour éviter l'écrasement
        tf_name = f"compute_{it.id}.tf"

        plan.append({
            "type": "terraform",
            "domain": "compute",
            "path": f"generated/{base_subdir}/terraform/{tf_name}",
            "meta": {
                "provider": specs.get("provider") or "aws",
                "vms": specs.get("vms", []),
                "representative_intent_id": it.id,
                "intent_ids": [it.id],
            },
        })

    # 2) Intents "configure" -> on REGROUPE les domaines infra par sous-prompt (même it.prompt)
    #    Exemple: "… via alb + route53" -> un seul step Terraform (infra_bundle) pour {balancer_gateway, dns_tls}
    #    On conserve aussi un intent représentatif pour l'appel de génération.
    infra_groups: Dict[str, Dict[str, Any]] = {}
    system_needed = False

    for it in intents:
        if it.intent_type != "configure":
            continue

        mode = (it.configure_mode or "mixed").lower()
        domain = (it.configure_domain or "").lower()

        if mode in ("system", "mixed"):
            system_needed = True

        if mode in ("infra", "mixed") and domain in INFRA_DOMAIN_SET:
            key = (it.prompt or "").strip() or f"intent-{it.id}"  # sous-prompt tel qu’enregistré
            grp = infra_groups.setdefault(key, {
                "domains": set(),
                "intent_ids": set(),
                "representative_intent_id": it.id,  # le 1er rencontré sert de représentant
                "prompt": it.prompt,
            })
            grp["domains"].add(domain)
            grp["intent_ids"].add(it.id)

    # 3) Transformer les groupes infra -> steps Terraform
    #    - un seul step par sous-prompt
    #    - domain = 'infra_bundle' si >1, sinon le domaine réel
    #    - path unique (ex: infra_<slug>.tf) pour éviter collisions entre bundles
    for key, grp in infra_groups.items():
        domains_sorted = sorted(list(grp["domains"]), key=_order_key)
        is_bundle = len(domains_sorted) > 1
        out_domain = "infra_bundle" if is_bundle else domains_sorted[0]

        #  Nom de fichier unique & stable:
        #    - bundle: "infra_<slugPrompt>_<h8>.tf"
        #    - single: "<domain>_<intentId>.tf"
        if is_bundle:
            slug = _slugify(key)[:24]
            h8 = _hash8(key)
            out_filename = f"infra_{slug}_{h8}.tf"
        else:
            out_filename = f"{out_domain}_{grp['representative_intent_id']}.tf"

        plan.append({
            "type": "terraform",
            "domain": out_domain,
            "path": f"generated/{base_subdir}/terraform/{out_filename}",
            "meta": {
                "domains": domains_sorted,                     #  ex: ["balancer_gateway","dns_tls"]
                "representative_intent_id": grp["representative_intent_id"],
                "intent_ids": sorted(list(grp["intent_ids"])),
                "prompt_key": key,
            },
        })

    # 4) Étape Ansible à la fin si nécessaire (ex. system_service)
    if system_needed:
        plan.append({
            "type": "ansible",
            "domain": "system_service",
            "path": f"generated/{base_subdir}/ansible/system_service.yml",
        })

    # 5) Numérotation
    for i, step in enumerate(plan, start=1):
        step["step"] = i

    # Si au final on n'a rien (ex. tous les intents create/configure non exploitables)
    if not plan:
        return {
            "status": "empty",
            "engine": "multi",
            "plan": [],
            "message": "Aucun step à générer (intents non exploitables ou déjà générés).",
            "vm_specs": vm_specs or None,
        }

    return {
        "status": "success",
        "engine": "multi",
        "plan": plan,
        "message": "Toujours Terraform d’abord, puis Ansible. Les domaines infra cités dans la même phrase sont regroupés. Les fichiers Terraform sont uniques par step.",
        "vm_specs": vm_specs or None,
    }
