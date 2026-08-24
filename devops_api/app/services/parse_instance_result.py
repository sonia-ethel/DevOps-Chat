import logging
import json
from app import models
from app.utils.crypto import encrypt
from app.utils.extra_data_utils import get_extra

logger = logging.getLogger(__name__)

# Mapping user SSH par distro (fallback si ssh_user absent)
USER_BY_DISTRO = {
    "ubuntu": "ubuntu",
    "debian": "admin",          # parfois "debian" selon AMI
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


def _tf_list(value):
    """Accepte Terraform output style {"value":[...]} | list | str | None -> list"""
    if value is None:
        return []
    if isinstance(value, dict) and "value" in value:
        value = value["value"]
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return [value]
    return []


def _pick_first_key(dct, *candidates):
    for k in candidates:
        if k in dct and dct[k] is not None:
            return dct[k]
    return None


def _collect_ids(outputs: dict, keyword: str) -> set[str]:
    """
    Balaye les outputs et récupère tous les IDs présents dans les clés 'instance_ids_*'
    contenant <keyword> (ex: 'ubuntu', 'debian', 'windows', 'rocky'...).
    """
    s = set()
    for k, v in (outputs or {}).items():
        lk = (k or "").lower()
        if lk.startswith("instance_ids_") and keyword in lk:
            s.update(_tf_list(v))
    return s


def parse_instance_result(
    db,
    execution: models.Execution,
    terraform_outputs: dict,
    session: models.Session,
    ssh_user: str,
    private_key: str,
):
    """
    Parse les résultats Terraform et enregistre/maj chaque instance dans `Instance`.
    - Supporte provider {aws, azure, google}
    - Déduit os_family/distro à partir des outputs (instance_ids_*), sinon fallback
    - Ne met JAMAIS NULL dans ssh_private_key (chaîne vide chiffrée pour Windows/WinRM)
    - Associe IPID via le zip(instance_ids, public_ips) si disponible
    """
    logger.info(" [DB] Début parse_instance_result")
    logger.info(" [DB] Terraform outputs keys: %s", list(terraform_outputs.keys()))
    
    extra = get_extra(execution)
    provider = (extra.get("provider") or extra.get("provider_name") or "aws").lower()
    if provider == "gcp":
        provider = "google"
    
    logger.info("  [DB] Provider: %s", provider)

    # IDs & IPs globaux (génériques + par provider)
    ids = _tf_list(_pick_first_key(
        terraform_outputs,
        "instance_ids", "instance_id",       # génériques
        "vm_ids",                            # azure
        "ids"                                # fallback
    ))
    ips = _tf_list(_pick_first_key(
        terraform_outputs,
        "public_ips", "public_ip",           # génériques/AWS
        "instance_ips",                      # AWS outputs alternatif
        "nat_ips",                           # google
        "ip_addresses"                       # azure
    ))

    logger.info(" [DB] Instance IDs extraits: %s", ids)
    logger.info(" [DB] IPs extraites: %s", ips)
    
    # Exception si outputs vides
    if not ids:
        raise ValueError(" Terraform outputs ne contient aucun instance_id. Outputs: " + str(terraform_outputs))
    if not ips:
        raise ValueError(" Terraform outputs ne contient aucune IP. Outputs: " + str(terraform_outputs))
    
    # Mapping ID -> IP quand c'est possible (même ordre dans tes outputs actuels)
    id_to_ip = {}
    if ids and ips:
        for i, _id in enumerate(ids):
            if i < len(ips):
                id_to_ip[_id] = ips[i]
    
    logger.info(" [DB] Mapping ID->IP: %s", id_to_ip)

    # Sets d'IDs par distro/OS déduits des noms d'outputs
    ubuntu_ids = _collect_ids(terraform_outputs, "ubuntu")
    debian_ids = _collect_ids(terraform_outputs, "debian")
    windows_ids = _collect_ids(terraform_outputs, "windows")
    rhel_ids = (
        _collect_ids(terraform_outputs, "rhel")
        | _collect_ids(terraform_outputs, "redhat")
        | _collect_ids(terraform_outputs, "centos")
        | _collect_ids(terraform_outputs, "rocky")
    )
    amzn_ids = (
        _collect_ids(terraform_outputs, "amzn")
        | _collect_ids(terraform_outputs, "amazon-linux")
        | _collect_ids(terraform_outputs, "amazon")
    )
    sles_ids = _collect_ids(terraform_outputs, "sles") | _collect_ids(terraform_outputs, "suse")

    # Optionnels: familles/distros/runtimes explicites (si tu les exposes un jour)
    os_families = _tf_list(_pick_first_key(terraform_outputs, "os_family", "os_families"))
    distros     = _tf_list(_pick_first_key(terraform_outputs, "distro", "distros"))
    runtimes    = _tf_list(_pick_first_key(terraform_outputs, "runtime", "runtimes"))

    # Fallback depuis extra_data
    default_os_family = (extra.get("os_family") or "").lower() or None
    default_distro    = (extra.get("distro") or "").lower() or None
    default_runtime   = (extra.get("runtime") or "").lower() or None

    max_len = max(len(ids), len(ips), len(os_families), len(distros), len(runtimes), 1)

    def at(lst, i, default=None):
        try:
            return lst[i]
        except Exception:
            return default

    for idx in range(max_len):
        instance_id = at(ids, idx)
        public_ip   = id_to_ip.get(instance_id, at(ips, idx))

        # Fallbacks depuis tableaux explicites (peu utilisés pour l’instant)
        os_family   = (at(os_families, idx, default_os_family) or default_os_family or "").lower() or None
        distro      = (at(distros, idx, default_distro) or default_distro or "").lower() or None
        runtime     = (at(runtimes, idx, default_runtime) or default_runtime or "").lower() or None

        # Déduction depuis l'appartenance par ID aux groupes instance_ids_*
        if instance_id in windows_ids:
            distro = "windows"
            os_family = "windows"
        elif instance_id in ubuntu_ids:
            distro = "ubuntu"
            os_family = os_family or "linux"
        elif instance_id in debian_ids:
            distro = "debian"
            os_family = os_family or "linux"
        elif instance_id in rhel_ids:
            distro = distro or "rhel"
            os_family = os_family or "linux"
        elif instance_id in amzn_ids:
            distro = "amazon-linux"
            os_family = os_family or "linux"
        elif instance_id in sles_ids:
            distro = "sles"
            os_family = os_family or "linux"
        else:
            # derniers fallback si rien de détecté
            os_family = os_family or "linux"
            distro = distro or "unknown"

        # runtime par défaut
        if not runtime:
            runtime = "winrm" if os_family == "windows" else "ssh"

        # ssh_user final : param > mapping distro > défaut
        effective_ssh_user = ssh_user or USER_BY_DISTRO.get(distro or "unknown", "ec2-user")
        if os_family == "windows":
            effective_ssh_user = USER_BY_DISTRO["windows"]

        # Clé privée à stocker :
        # - Linux/SSH : clé fournie sinon vide
        # - Windows/WinRM : pas de clé -> chaîne vide (jamais NULL)
        key_to_store = "" if os_family == "windows" else (private_key or "")

        # skip si id ou ip manquant
        if not instance_id or not public_ip:
            logger.warning("⏭ Instance ignorée (id/ip manquant) idx=%s id=%s ip=%s", idx, instance_id, public_ip)
            continue

        enc_ip  = encrypt(public_ip)
        enc_key = encrypt(key_to_store)

        existing = db.query(models.Instance).filter_by(
            instance_id=instance_id,
            session_id=session.id
        ).first()

        name_value = f"{provider}-instance-{session.id}-{execution.id}-{idx}"

        if existing:
            logger.info(" [DB] Maj instance: %s", instance_id)
            existing.provider = provider
            existing.public_ip = enc_ip
            existing.ssh_user = effective_ssh_user
            existing.ssh_private_key = enc_key
            existing.name = name_value
            if hasattr(existing, "status"):
                existing.status = "running"
            if hasattr(existing, "os_family") and os_family:
                existing.os_family = os_family
            if hasattr(existing, "distro") and distro:
                existing.distro = distro
            if hasattr(existing, "runtime") and runtime:
                existing.runtime = runtime
            #  ÉTAPE 1 — Instances Terraform avec clés = SSH
            if hasattr(existing, "connection_method"):
                existing.connection_method = "ssh"  # Terraform provisionne avec clés
                existing.ssm_managed = False  # Non SSM par défaut pour Terraform
        else:
            logger.info(" [DB] Nouvelle instance: %s", instance_id)
            fields = dict(
                instance_id=instance_id,
                session_id=session.id,
                provider=provider,
                public_ip=enc_ip,
                ssh_user=effective_ssh_user,
                ssh_private_key=enc_key,   # jamais NULL
                name=name_value,
            )
            if hasattr(models.Instance, "status"):
                fields["status"] = "running"
            if hasattr(models.Instance, "os_family") and os_family:
                fields["os_family"] = os_family
            if hasattr(models.Instance, "distro") and distro:
                fields["distro"] = distro
            if hasattr(models.Instance, "runtime") and runtime:
                fields["runtime"] = runtime
            #  ÉTAPE 1 — Instances Terraform avec clés = SSH
            if hasattr(models.Instance, "connection_method"):
                fields["connection_method"] = "ssh"  # Terraform provisionne avec clés
                fields["ssm_managed"] = False  # Non SSM par défaut pour Terraform

            db.add(models.Instance(**fields))

    instances_processed = max_len
    logger.info(" [DB] Instances traitées: %d", instances_processed)
    logger.info(" [DB] Commit des instances en cours...")
    db.commit()
    logger.info(" [DB] Commit réussi! %d instances enregistrées", instances_processed)
