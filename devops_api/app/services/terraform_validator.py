# app/services/terraform_validator.py
import logging
import re
import subprocess
import os
from typing import Tuple, Optional, Dict, Any, List

from app.database import SessionLocal
from app.models.ami import Ami

logger = logging.getLogger(__name__)


def build_clean_terraform(terraform_code: str, credentials: dict) -> Tuple[str, str]:
    """
    Nettoie/fiabilise le code Terraform généré.

    - Détecte le provider.
    - Traite **toutes** les ressources compute (aws_instance / azurerm_linux_virtual_machine / google_compute_instance) :
        • (AWS) Remplace l'AMI placeholder par la dernière AMI DB (distro + région).
        • Déplace les commandes shell "perdues" vers un bloc user_data propre.
        • Supprime les doublons de user_data et n’en garde qu’un seul (heredoc si possible).
        • Ajoute/merge tags/labels { os_family, distro }.
    - Ajoute des outputs **suffixés par ressource** pour éviter les collisions.
    - Corrige une faute fréquente: vpc_id = aws_vpc.this.id -> aws_vpc.<nom>.id (si détectable).
    - Retourne (terraform_code_clean, ssh_user_suggested) — ssh_user = premier user détecté utile pour l’exécution Ansible.
    """
    code = (terraform_code or "").strip()
    if not code:
        return code, "ubuntu"

    provider = _detect_provider(code)
    # Petite correction opportuniste sur des SG mal référencés
    code = _fix_sg_vpc_refs(code)

    # Liste de TOUTES les ressources compute
    computes = _find_compute_resources(code)
    if not computes:
        logger.debug("build_clean_terraform: aucune ressource compute détectée (infra-only).")
        # rien à faire ; ssh_user par défaut raisonnable
        return code, "ubuntu"

    # on conservera le premier ssh_user raisonnable
    suggested_ssh_user = None

    region = (credentials or {}).get("region", "eu-west-1")

    # Traiter CHAQUE ressource compute
    for rtype, rname in computes:
        # déduire distro + ssh_user en se basant sur le nom de ressource et son corps
        distro, ssh_user = _deduce_distro_ssh_user_for_resource(code, provider, rtype, rname)
        if not suggested_ssh_user:
            suggested_ssh_user = ssh_user

        # (AWS) Remplacer AMI placeholder dans CE bloc uniquement
        if provider == "aws" and rtype == "aws_instance":
            try:
                ami_id = _get_latest_ami_id(distro, region)
                if ami_id:
                    code = _replace_ami_in_resource(code, rtype, rname, ami_id)
                else:
                    logger.warning(f"Aucune AMI trouvée pour distro={distro}, region={region} ; {rname} garde son AMI telle quelle.")
            except Exception as e:
                logger.warning(f"Echec récupération AMI ({distro}/{region}) pour {rname}: {e}. On continue.")

        # Déplacer les commandes shell -> user_data (dans CE bloc)
        code = _move_shell_to_user_data(code, rtype, rname)

        # Dédupliquer et nettoyer les user_data (CE bloc)
        code = _dedupe_user_data_block(code, rtype, rname)

        # Merge tags/labels os_family + distro (CE bloc)
        os_family = "windows" if distro.lower() == "windows" else "linux"
        code = _merge_os_tags_or_labels(code, rtype, rname, {"os_family": os_family, "distro": distro.lower()})

    # Outputs suffixés par ressource (évite toute collision entre ubuntu/debian…)
    code = _ensure_outputs_many(code, provider, computes)

    return code, (suggested_ssh_user or "ubuntu")


# ---------- Helpers de détection / parsing ----------

def _detect_provider(code: str) -> str:
    m = re.search(r'provider\s+"(\w+)"', code, re.I)
    p = (m.group(1).lower() if m else "aws")
    if p == "gcp":
        p = "google"
    return p


def _find_compute_resources(code: str) -> List[Tuple[str, str]]:
    res: List[Tuple[str, str]] = []
    for rtype in ("aws_instance", "azurerm_linux_virtual_machine", "google_compute_instance"):
        for m in re.finditer(rf'resource\s+"{rtype}"\s+"([^"]+)"', code, flags=re.I):
            res.append((rtype, m.group(1)))
    return res


def _resource_block_span(code: str, resource_type: str, resource_name: str) -> Optional[Tuple[int, int, str, str, str]]:
    """
    Retourne (start, end, head, body, tail) pour le bloc de la ressource demandée.
    """
    pat = rf'(resource\s+"{re.escape(resource_type)}"\s+"{re.escape(resource_name)}"\s*{{)(.*?)(\n}})'
    m = re.search(pat, code, flags=re.DOTALL)
    if not m:
        return None
    return m.start(), m.end(), m.group(1), m.group(2), m.group(3)


def _resource_has_count(code: str, resource_type: str, resource_name: str) -> bool:
    span = _resource_block_span(code, resource_type, resource_name)
    if not span:
        return False
    _, _, _, body, _ = span
    return bool(re.search(r'^\s*count\s*=\s*\d+', body, flags=re.MULTILINE))


def _deduce_distro_ssh_user_for_resource(code: str, provider: str, resource_type: str, resource_name: str) -> Tuple[str, str]:
    """
    Déduit distro + ssh_user en s'aidant :
    - du **nom de ressource** (ex: *_debian, *_ubuntu, *_windows, *_amzn, *_centos, *_rocky, *_rhel)
    - des tags/labels 'Name' ou autres présents dans le bloc
    - d’un fallback par provider
    """
    # heuristique via le nom
    rn = resource_name.lower()
    if "debian" in rn:
        name_hint = "debian"
    elif "ubuntu" in rn:
        name_hint = "ubuntu"
    elif "windows" in rn:
        name_hint = "windows"
    elif "amzn" in rn or "amazon" in rn:
        name_hint = "amazon-linux"
    elif "centos" in rn:
        name_hint = "centos"
    elif "rocky" in rn:
        name_hint = "rocky"
    elif "rhel" in rn or "redhat" in rn:
        name_hint = "rhel"
    else:
        name_hint = None

    # lire le corps pour des indices
    span = _resource_block_span(code, resource_type, resource_name)
    body = span[3] if span else ""

    tag_name = None
    mname = re.search(r'Name\s*=\s*"([^"]+)"', body)
    if mname:
        tag_name = mname.group(1).lower()

    def guess_from_text(txt: Optional[str]) -> Optional[str]:
        if not txt:
            return None
        t = txt.lower()
        for key in ("debian", "ubuntu", "windows", "amzn", "amazon", "centos", "rocky", "rhel", "redhat"):
            if key in t:
                return {"amzn": "amazon-linux", "amazon": "amazon-linux", "redhat": "rhel"}.get(key, key)
        return None

    distro = guess_from_text(tag_name) or name_hint or "ubuntu"
    distro = distro.lower()

    # ssh user par distro/provider
    ssh_user_map = {
        "debian": "admin",
        "ubuntu": "ubuntu",
        "windows": "Administrator",
        "amazon-linux": "ec2-user",
        "centos": "centos",
        "rocky": "rocky",
        "rhel": "ec2-user",
    }
    ssh_user = ssh_user_map.get(distro, "ubuntu")

    if provider == "azure" and ssh_user == "ubuntu":
        ssh_user = "azureuser"
    elif provider == "google" and ssh_user == "ubuntu":
        ssh_user = "ubuntu"

    return distro, ssh_user


# ---------- AMI / user_data / tags ----------

def _normalize_distro_for_db(distro: str) -> str:
    """
    Normalise la valeur de 'distribution' pour matcher ce qui est stocké en BDD.
    - Ton script d’update insère 'amazon' (pas 'amazon-linux')
    - On harmonise ici pour éviter les misses.
    """
    d = (distro or "").lower().strip()
    mapping = {
        "amazon-linux": "amazon",
        "amzn": "amazon",
        "redhat": "rhel",
    }
    return mapping.get(d, d)


def _get_latest_ami_id(distro: str, region: str) -> Optional[str]:
    db = SessionLocal()
    try:
        distro_db = _normalize_distro_for_db(distro)
        ami = (
            db.query(Ami)
            .filter(Ami.distribution == distro_db, Ami.region == region)
            .order_by(Ami.created_at.desc())
            .first()
        )
        return ami.ami_id if ami else None
    finally:
        db.close()


def _replace_ami_in_resource(code: str, resource_type: str, resource_name: str, ami_id: str) -> str:
    span = _resource_block_span(code, resource_type, resource_name)
    if not span:
        return code
    start, end, head, body, tail = span
    # remplace seulement la première occurrence de ami = "..."
    if re.search(r'\bami\s*=\s*"(.*?)"', body):
        body = re.sub(r'\bami\s*=\s*"(.*?)"', f'ami = "{ami_id}"', body, count=1)
    else:
        # si pas d'attribut ami (cas rares), on l'insère
        body = body.rstrip("\n") + f'\n  ami = "{ami_id}"\n'
    return code[:start] + head + body + tail + code[end:]


def _move_shell_to_user_data(code: str, resource_type: str, resource_name: str) -> str:
    """
    Déplace des lignes shell (apt, yum, dnf, docker, systemctl, etc.) du corps de la ressource
    vers un heredoc user_data. N'ajoute PAS de doublon si user_data existe déjà.
    """
    span = _resource_block_span(code, resource_type, resource_name)
    if not span:
        return code
    start, end, head, body, tail = span

    shell_cmd_re = re.compile(r'^\s*(apt-get|apt|yum|dnf|echo|docker|systemctl|ufw|curl|wget|git)\s+', re.IGNORECASE)
    lines = body.splitlines()
    shell_cmds, keep = [], []
    for ln in lines:
        if shell_cmd_re.match(ln.strip()) and "user_data" not in ln:
            shell_cmds.append(ln.strip())
        else:
            keep.append(ln)

    if not shell_cmds:
        return code

    script = "\n".join(shell_cmds)
    if not script.lstrip().startswith("#!"):
        script = "#!/bin/bash\n" + script

    has_user_data = any(re.search(r'^\s*user_data\s*=', l) for l in keep)
    if not has_user_data:
        keep.append("  user_data = <<-EOF\n" + script + "\n  EOF")
        body_joined = "\n".join(keep)
    else:
        body_joined = "\n".join(keep)
        m = re.search(r'(user_data\s*=\s*<<-?EOF\s*)(.*?)(\n\s*EOF)', body_joined, flags=re.DOTALL)
        if m:
            before, existing, after = m.group(1), m.group(2), m.group(3)
            if not existing.strip().startswith("#!"):
                existing = "#!/bin/bash\n" + existing.lstrip()
            existing = existing.rstrip() + "\n" + script
            body_joined = body_joined[:m.start()] + before + existing + after + body_joined[m.end():]
        else:
            body_joined = re.sub(
                r'^\s*user_data\s*=\s*".*?"\s*$',
                "  user_data = <<-EOF\n" + script + "\n  EOF",
                body_joined,
                flags=re.MULTILINE
            )

    return code[:start] + head + body_joined + tail + code[end:]


def _dedupe_user_data_block(code: str, resource_type: str, resource_name: str) -> str:
    """
    Si plusieurs user_data sont présents dans la même ressource, n'en garde qu'un :
    - priorité au heredoc ; sinon on garde le premier rencontré.
    - supprime les user_data = "" vides.
    """
    span = _resource_block_span(code, resource_type, resource_name)
    if not span:
        return code
    start, end, head, body, tail = span

    # Supprimer les user_data = "" vides
    body = re.sub(r'^\s*user_data\s*=\s*""\s*$', "", body, flags=re.MULTILINE)

    # Collecter tous les user_data
    ud_spans = list(re.finditer(r'^\s*user_data\s*=\s*(<<-?EOF\b.*?\bEOF\s*$|".*?")', body, flags=re.DOTALL | re.MULTILINE))
    if len(ud_spans) <= 1:
        return code[:start] + head + body + tail + code[end:]

    # Sélectionner celui à garder
    heredoc_idx = None
    for i, m in enumerate(ud_spans):
        if m.group(1).startswith("<<"):
            heredoc_idx = i
            break
    keep_idx = heredoc_idx if heredoc_idx is not None else 0

    keep_start, keep_end = ud_spans[keep_idx].span()
    keep_block = body[keep_start:keep_end]

    pieces = []
    last = 0
    for i, m in enumerate(ud_spans):
        s, e = m.span()
        if i == keep_idx:
            pieces.append(body[last:s])
            pieces.append(keep_block)
        else:
            pieces.append(body[last:s])
        last = e
    pieces.append(body[last:])

    new_body = "".join(pieces)
    return code[:start] + head + new_body + tail + code[end:]


def _merge_os_tags_or_labels(code: str, resource_type: str, resource_name: str, kv: dict) -> str:
    """
    Merge des métadonnées (os_family, distro) dans tags (AWS/Azure) ou labels (GCP).
    """
    block_name = "labels" if resource_type == "google_compute_instance" else "tags"
    span = _resource_block_span(code, resource_type, resource_name)
    if not span:
        return code
    start, end, head, body, tail = span

    # 1) Bloc multilignes
    pat_block = rf'({block_name}\s*{{)(.*?)(\n\s*}})'
    b = re.search(pat_block, body, flags=re.DOTALL)
    if b:
        inside = b.group(2)
        for k, v in kv.items():
            kv_pat = rf'(^\s*{re.escape(k)}\s*=\s*")[^"]*(")'
            if re.search(kv_pat, inside, flags=re.MULTILINE):
                inside = re.sub(kv_pat, rf'\1{v}\2', inside, flags=re.MULTILINE)
            else:
                if not inside.endswith("\n"):
                    inside += "\n"
                inside += f'  {k} = "{v}"\n'
        body = body[:b.start(2)] + inside + body[b.end(2):]
    else:
        # 2) Inline { ... } ou 3) créer inline
        pat_inline = rf'({block_name}\s*=\s*{{)(.*?)(}})'
        bi = re.search(pat_inline, body, flags=re.DOTALL)
        if bi:
            inside = bi.group(2)
            for k, v in kv.items():
                kv_pat = rf'(\b{re.escape(k)}\s*=\s*")[^"]*(")'
                if re.search(kv_pat, inside):
                    inside = re.sub(kv_pat, rf'\1{v}\2', inside)
                else:
                    inside = inside.rstrip()
                    if inside and not inside.strip().endswith(","):
                        inside += ","
                    inside += f' {k} = "{v}"'
            body = body[:bi.start(2)] + inside + body[bi.end(2):]
        else:
            # créer inline
            insert = f'\n  {block_name} = {{ os_family = "{kv["os_family"]}", distro = "{kv["distro"]}" }}\n'
            body = body.rstrip("\n") + insert

    return code[:start] + head + body + tail + code[end:]


# ---------- Outputs ----------

def _ensure_outputs_many(code: str, provider: str, computes: List[Tuple[str, str]]) -> str:
    """
    Ajoute des outputs par ressource, suffixés par le nom de ressource (pour éviter les collisions).
    Ex: public_ips_arnaudgif_s1_instance_debian, instance_ids_arnaudgif_s1_instance_ubuntu, etc.
    """
    for rtype, rname in computes:
        has_count = _resource_has_count(code, rtype, rname)

        if provider == "aws" and rtype == "aws_instance":
            outputs = {
                f"public_ips_{rname}": (
                    f'output "public_ips_{rname}" {{\n  value = [for i in aws_instance.{rname} : i.public_ip]\n}}'
                    if has_count else
                    f'output "public_ips_{rname}" {{\n  value = aws_instance.{rname}.public_ip\n}}'
                ),
                f"instance_ids_{rname}": (
                    f'output "instance_ids_{rname}" {{\n  value = [for i in aws_instance.{rname} : i.id]\n}}'
                    if has_count else
                    f'output "instance_ids_{rname}" {{\n  value = aws_instance.{rname}.id\n}}'
                ),
            }
        elif provider == "azure" and rtype == "azurerm_linux_virtual_machine":
            outputs = {
                f"ip_addresses_{rname}": (
                    f'output "ip_addresses_{rname}" {{\n  value = [for i in azurerm_linux_virtual_machine.{rname} : i.public_ip_address]\n}}'
                    if has_count else
                    f'output "ip_addresses_{rname}" {{\n  value = azurerm_linux_virtual_machine.{rname}.public_ip_address\n}}'
                ),
                f"vm_ids_{rname}": (
                    f'output "vm_ids_{rname}" {{\n  value = [for i in azurerm_linux_virtual_machine.{rname} : i.id]\n}}'
                    if has_count else
                    f'output "vm_ids_{rname}" {{\n  value = azurerm_linux_virtual_machine.{rname}.id\n}}'
                ),
            }
        elif provider == "google" and rtype == "google_compute_instance":
            outputs = {
                f"nat_ips_{rname}": (
                    f'output "nat_ips_{rname}" {{\n  value = [for i in google_compute_instance.{rname} : i.network_interface[0].access_config[0].nat_ip]\n}}'
                    if has_count else
                    f'output "nat_ips_{rname}" {{\n  value = google_compute_instance.{rname}.network_interface[0].access_config[0].nat_ip\n}}'
                ),
                f"instance_ids_{rname}": (
                    f'output "instance_ids_{rname}" {{\n  value = [for i in google_compute_instance.{rname} : i.id]\n}}'
                    if has_count else
                    f'output "instance_ids_{rname}" {{\n  value = google_compute_instance.{rname}.id\n}}'
                ),
            }
        else:
            continue

        for name, block in outputs.items():
            # remplace si existe, sinon ajoute
            if re.search(rf'output\s+"{re.escape(name)}"\s*{{.*?}}', code, flags=re.DOTALL):
                code = re.sub(rf'output\s+"{re.escape(name)}"\s*{{.*?}}', block, code, flags=re.DOTALL)
            else:
                code += f"\n\n{block}"

    return code


# ---------- Fixes opportunistes ----------

def _fix_sg_vpc_refs(code: str) -> str:
    """
    Si on trouve vpc_id = aws_vpc.this.id mais qu'aucune ressource aws_vpc "this" n'existe,
    et qu'il existe une seule ressource aws_vpc "<name>", on remplace ".this" par ".<name>".
    """
    if "aws_vpc.this.id" not in code:
        return code

    vpc_names = re.findall(r'resource\s+"aws_vpc"\s+"([^"]+)"', code)
    if not vpc_names:
        return code

    unique_names = [n for n in vpc_names if n != "this"]
    if len(unique_names) == 1 and "this" not in vpc_names:
        correct = unique_names[0]
        code = code.replace("aws_vpc.this.id", f"aws_vpc.{correct}.id")
    return code


# ---------- Validation terraform CLI ----------

def validate_terraform_file(tf_path: str) -> str:
    """
    Exécute `terraform init -backend=false` puis `terraform validate` dans le dossier du fichier.
    Retourne la sortie si OK, sinon lève une Exception.
    """
    exec_dir = os.path.dirname(tf_path)

    init_proc = subprocess.run(
        ["terraform", "init", "-backend=false", "-input=false", "-no-color"],
        cwd=exec_dir, text=True, capture_output=True
    )
    if init_proc.returncode != 0:
        raise Exception(f" Terraform init failed:\n{(init_proc.stderr or init_proc.stdout)}")

    val_proc = subprocess.run(
        ["terraform", "validate", "-no-color"],
        cwd=exec_dir, text=True, capture_output=True
    )
    if val_proc.returncode != 0:
        raise Exception(f" Terraform validation failed:\n{(val_proc.stderr or val_proc.stdout)}")

    return val_proc.stdout.strip()
