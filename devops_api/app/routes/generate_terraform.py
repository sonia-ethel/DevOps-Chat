# © 2024–2026 TOURE Arnaud Patrick
# Licensed under the MIT License

# app/routes/generate_terraform.py

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from typing import List, Optional

from app import models, database
from app.auth import get_current_user
from app.services.gpt_service import generate_instructions_from_gpt
from app.services.terraform_validator import build_clean_terraform
from app.services.intent_parser import parse_intent
from app.utils.crypto import encrypt, decrypt
from app.utils.file_utils import create_and_store_terraform_file, create_and_store_private_key

import json
import paramiko
import io
import re
import uuid
import os

router = APIRouter()


def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------- Validations structurelles AWS (anti-erreurs courantes) ----------
def _ensure_not_example_or_zone_creation(tf_text: str):
    if "example.com" in tf_text:
        raise HTTPException(status_code=400, detail="Validation Terraform: 'example.com' est réservé par AWS. Utilise un domaine réel.")
    if re.search(r'resource\s+"aws_route53_zone"\s+"', tf_text):
        raise HTTPException(
            status_code=400,
            detail='Validation Terraform: création de Route53 zone interdite dans ce flux. Utilise data "aws_route53_zone" pour une zone EXISTANTE.'
        )


def _validate_aws_lb_requirements(tf_text: str):
    """
    Validation robuste pour aws_lb :
    - OK si:
        * subnets = [ ... ] avec >= 2 entrées littérales, OU
        * subnets = data.aws_subnets.<label>.ids (sans crochets), OU
        * subnets = <expression dynamique> (var./local./concat/tolist/flatten), OU
        * >= 2 blocs subnet_mapping { ... }
    - Exige toujours security_groups.
    Le parsing lit le bloc complet par comptage d’accolades.
    """
    import re

    pat = re.compile(r'resource\s+"aws_lb"\s+"[^"]+"\s*{', re.I)
    i = 0
    while True:
        m = pat.search(tf_text, i)
        if not m:
            break

        # extraire le corps complet du bloc aws_lb {...}
        j, depth = m.end(), 1
        while j < len(tf_text) and depth > 0:
            if tf_text[j] == "{":
                depth += 1
            elif tf_text[j] == "}":
                depth -= 1
            j += 1
        body = tf_text[m.end():j-1]

        # 1) Vérifier subnets OU subnet_mapping (>= 2)
        #    - accepter forme avec crochets: subnets = [ ... ]
        #    - accepter forme sans crochets: subnets = data.aws_subnets.<label>.ids
        sub_m = re.search(r'\bsubnets\s*=\s*(\[[^\]]+\]|[^\n]+)', body, flags=re.S)
        ok_subnets = False
        if sub_m:
            expr = sub_m.group(1).strip()
            if expr.startswith("["):
                content = expr.strip()[1:-1].strip()
                # contenu dynamique ? (impossible de compter proprement : on accepte)
                if re.search(r'(data\.aws_subnets\.[^.]+\.ids|var\.|local\.|concat\s*\(|tolist\s*\(|flatten\s*\()', content):
                    ok_subnets = True
                else:
                    # comptage d'entrées littérales séparées par virgule
                    entries = [e.strip() for e in content.split(",") if e.strip()]
                    ok_subnets = len(entries) >= 2
            else:
                # assignation sans crochets : on accepte si c'est manifestement une liste/expr dynamique
                if re.search(r'(data\.aws_subnets\.[^.]+\.ids|var\.|local\.|concat\s*\(|tolist\s*\(|flatten\s*\()', expr):
                    ok_subnets = True
                else:
                    ok_subnets = False  # ex: "aws_subnet.a.id" tout seul -> pas une liste
        if not ok_subnets:
            # alternative valide: au moins 2 blocs subnet_mapping { ... }
            num_mappings = len(re.findall(r'\bsubnet_mapping\s*{', body))
            if num_mappings < 2:
                raise HTTPException(
                    status_code=400,
                    detail="Validation Terraform: aws_lb doit fournir `subnets` (2 AZ) ou au moins deux blocs `subnet_mapping`."
                )

        # 2) Exiger security_groups (liste d'ids SG)
        if not re.search(r'\bsecurity_groups\s*=', body):
            raise HTTPException(
                status_code=400,
                detail="Validation Terraform: aws_lb sans 'security_groups'."
            )

        i = j


def _validate_aws_tg_requirements(tf_text: str):
    import re
    pat = re.compile(r'resource\s+"aws_lb_target_group"\s+"[^"]+"\s*{', re.I)
    i = 0
    while True:
        m = pat.search(tf_text, i)
        if not m:
            break
        j, depth = m.end(), 1
        while j < len(tf_text) and depth > 0:
            if tf_text[j] == "{":
                depth += 1
            elif tf_text[j] == "}":
                depth -= 1
            j += 1
        body = tf_text[m.end():j-1]
        if not re.search(r'\bvpc_id\s*=', body):
            raise HTTPException(status_code=400, detail="Validation Terraform: aws_lb_target_group sans 'vpc_id'.")
        i = j


def _validate_aws_route53_records(tf_text: str):
    # Interdire CNAME et A sans alias (on veut un ALIAS A vers l'ALB)
    for m in re.finditer(r'resource\s+"aws_route53_record"\s+"[^"]+"\s*{([^}]*)}', tf_text, flags=re.S):
        block = m.group(1)
        is_cname = re.search(r'\btype\s*=\s*"CNAME"', block)
        if is_cname:
            raise HTTPException(status_code=400, detail="Validation Terraform: Route53 CNAME interdit ici. Utilise un ALIAS A vers l'ALB.")
        is_a = re.search(r'\btype\s*=\s*"A"', block)
        if is_a:
            has_alias = re.search(r'\balias\s*{[^}]+}', block, flags=re.S)
            if not has_alias:
                raise HTTPException(
                    status_code=400,
                    detail="Validation Terraform: Record A sans 'alias { ... }'. Utilise un ALIAS A vers l'ALB (dns_name & zone_id)."
                )


def _validate_tf_aws_sane(tf_text: str):
    _ensure_not_example_or_zone_creation(tf_text)
    _validate_aws_lb_requirements(tf_text)
    _validate_aws_tg_requirements(tf_text)
    _validate_aws_route53_records(tf_text)


# ---------- Validation type d'intent (anti-mélange create/configure) ----------
def _validate_tf_type(tf_text: str, intent_type: str, single_domain: Optional[str] = None, bundle_domains: Optional[List[str]] = None):
    """ Empêche les ressources hors scope selon le type d'intent, avec exceptions contrôlées. """
    bundle_domains = bundle_domains or []
    if intent_type == "create":
        # CREATE = compute uniquement (pas de réseau / LB / DNS)
        forbidden_create = [
            'resource "aws_vpc"',
            'resource "aws_subnet"',
            'resource "aws_internet_gateway"',
            'resource "aws_route_table"',
            'resource "aws_route_table_association"',
            'resource "aws_lb"',
            'resource "aws_lb_target_group"',
            'resource "aws_lb_listener"',
            'resource "aws_route53_record"',
        ]
        if any(s in tf_text for s in forbidden_create):
            raise HTTPException(status_code=400, detail="CREATE = compute uniquement. Réseau (VPC/Subnets/IGW/Route), ALB et DNS interdits.")
    if intent_type == "configure":
        # CONFIGURE = pas de compute
        if any(s in tf_text for s in ['resource "aws_instance"', 'resource "aws_key_pair"']):
            raise HTTPException(status_code=400, detail="CONFIGURE = pas d'instances ni de clé SSH (réservé à CREATE).")
        # Réseau: autorisé SEULEMENT si le domaine comprend un ALB (balancer_gateway), car prérequis
        contains_balancer = (single_domain == "balancer_gateway") or ("balancer_gateway" in bundle_domains)
        if not contains_balancer:
            forbidden_net = [
                'resource "aws_vpc"',
                'resource "aws_subnet"',
                'resource "aws_internet_gateway"',
                'resource "aws_route_table"',
                'resource "aws_route_table_association"',
            ]
            if any(s in tf_text for s in forbidden_net):
                raise HTTPException(status_code=400, detail="CONFIGURE (hors ALB) = réutilisation du réseau existant (data sources), pas de création réseau.")


# ---------- Helpers d’édition HCL ----------
def _strip_resource_blocks(tf_text: str, type_name: str) -> str:
    """Supprime toutes les ressources Terraform du type donné (gestion d'accolades)."""
    pattern = re.compile(rf'resource\s+"{type_name}"\s+"[^"]+"\s*{{', re.I)
    out = []
    i = 0
    while True:
        m = pattern.search(tf_text, i)
        if not m:
            out.append(tf_text[i:])
            break
        start = m.start()
        out.append(tf_text[i:start])
        # trouver la fin du block par comptage d'accolades
        j = m.end()
        depth = 1
        while j < len(tf_text) and depth > 0:
            if tf_text[j] == "{":
                depth += 1
            elif tf_text[j] == "}":
                depth -= 1
            j += 1
        i = j  # skip block
    return "".join(out)


def _strip_route53_out_of_scope(tf_text: str, intent_type: str, single_domain: Optional[str], bundle_domains: Optional[List[str]]) -> str:
    """Supprime les records Route53 sauf si le domaine dns_tls est explicitement demandé."""
    bundle_domains = bundle_domains or []
    allow_route53 = (intent_type == "configure") and (single_domain == "dns_tls" or "dns_tls" in bundle_domains)
    if not allow_route53 and 'resource "aws_route53_record"' in tf_text:
        tf_text = _strip_resource_blocks(tf_text, "aws_route53_record")
    return tf_text


def _ensure_network_for_alb_if_missing(tf_text: str, label_prefix: str, name_prefix: str, region: str) -> str:
    """Ajoute un VPC minimal + 2 subnets publics + IGW + RT si aucun VPC/subnet n'est référencé (ni data ni resource)."""
    has_vpc_res = 'resource "aws_vpc"' in tf_text
    has_vpc_data = re.search(r'\bdata\s+"aws_vpc"\s+"', tf_text) is not None
    has_subnet_any = ('resource "aws_subnet"' in tf_text) or (re.search(r'\bdata\s+"aws_subnet', tf_text) is not None) or ('data "aws_subnets"' in tf_text)
    if has_vpc_res or has_vpc_data or has_subnet_any:
        return tf_text

    network = f'''
resource "aws_vpc" "{label_prefix}_vpc" {{
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags = {{ Name = "{name_prefix}-vpc" }}
}}

resource "aws_internet_gateway" "{label_prefix}_igw" {{
  vpc_id = aws_vpc.{label_prefix}_vpc.id
  tags   = {{ Name = "{name_prefix}-igw" }}
}}

resource "aws_subnet" "{label_prefix}_subnet_a" {{
  vpc_id                  = aws_vpc.{label_prefix}_vpc.id
  cidr_block              = "10.0.1.0/24"
  map_public_ip_on_launch = true
  availability_zone       = "{region}a"
  tags = {{ Name = "{name_prefix}-subnet-a" }}
}}

resource "aws_subnet" "{label_prefix}_subnet_b" {{
  vpc_id                  = aws_vpc.{label_prefix}_vpc.id
  cidr_block              = "10.0.2.0/24"
  map_public_ip_on_launch = true
  availability_zone       = "{region}b"
  tags = {{ Name = "{name_prefix}-subnet-b" }}
}}

resource "aws_route_table" "{label_prefix}_public_rt" {{
  vpc_id = aws_vpc.{label_prefix}_vpc.id
  route {{
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.{label_prefix}_igw.id
  }}
  tags = {{ Name = "{name_prefix}-public-rt" }}
}}

resource "aws_route_table_association" "{label_prefix}_subnet_a_association" {{
  subnet_id      = aws_subnet.{label_prefix}_subnet_a.id
  route_table_id = aws_route_table.{label_prefix}_public_rt.id
}}

resource "aws_route_table_association" "{label_prefix}_subnet_b_association" {{
  subnet_id      = aws_subnet.{label_prefix}_subnet_b.id
  route_table_id = aws_route_table.{label_prefix}_public_rt.id
}}
'''.lstrip()

    tf_text = tf_text.rstrip() + "\n\n" + network

    # Réécrire les références ALB/TG pour utiliser ce réseau
    tf_text = re.sub(
        r'(resource\s+"aws_lb"\s+"[^"]+"\s*{[^}]*?)subnets\s*=\s*\[[^\]]*\]',
        rf'\1subnets = [aws_subnet.{label_prefix}_subnet_a.id, aws_subnet.{label_prefix}_subnet_b.id]',
        tf_text,
        flags=re.DOTALL,
    )
    tf_text = re.sub(
        r'(resource\s+"aws_lb_target_group"\s+"[^"]+"\s*{[^}]*?)vpc_id\s*=\s*([^\s}\n]+)',
        rf'\1vpc_id = aws_vpc.{label_prefix}_vpc.id',
        tf_text,
        flags=re.DOTALL,
    )
    return tf_text


# ---------- Fix ALB minimal (subnets/SG) et TG.vpc_id si manquants ----------
def _inject_or_replace_alb_requirements(tf_text: str, label_prefix: str, name_prefix: str, region: str) -> str:
    """
    Garantit que chaque aws_lb a :
      - subnets = [aws_subnet.<a>.id, aws_subnet.<b>.id]
      - security_groups = [aws_security_group.<label_prefix>_alb_sg.id]
    et que chaque aws_lb_target_group a :
      - vpc_id = aws_vpc.<label_prefix>_vpc.id

    Idempotent : n'écrase pas si déjà présent.
    """
    import re

    # 0) SG pour l'ALB si absent
    sg_label = f'{label_prefix}_alb_sg'
    if f'resource "aws_security_group" "{sg_label}"' not in tf_text:
        sg_block = f'''
resource "aws_security_group" "{sg_label}" {{
  name        = "{name_prefix}-alb-sg"
  description = "ALB SG: allow 80"
  vpc_id      = aws_vpc.{label_prefix}_vpc.id

  ingress {{
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }}

  egress {{
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }}

  tags = {{ Name = "{name_prefix}-alb-sg" }}
}}
'''.lstrip()
        tf_text = tf_text.rstrip() + "\n\n" + sg_block

    def _patch_blocks(hcl: str, res_type: str, ensure: callable) -> str:
        """Parcourt les blocks resource res_type et permet d'injecter des attributs au besoin (avec comptage d'accolades)."""
        pat = re.compile(rf'resource\s+"{res_type}"\s+"[^"]+"\s*{{', re.I)
        out, i = [], 0
        while True:
            m = pat.search(hcl, i)
            if not m:
                out.append(hcl[i:])
                break
            out.append(hcl[i:m.end()])
            j, depth = m.end(), 1
            while j < len(hcl) and depth > 0:
                if hcl[j] == "{": depth += 1
                elif hcl[j] == "}": depth -= 1
                j += 1
            body = hcl[m.end():j-1]
            body = ensure(body)
            out.append(body)
            out.append("}")
            i = j
        return "".join(out)

    # 1) aws_lb : subnets + security_groups si manquants
    def _ensure_lb(body: str) -> str:
        if "subnets" not in body:
            body = f'\n  subnets = [aws_subnet.{label_prefix}_subnet_a.id, aws_subnet.{label_prefix}_subnet_b.id]\n' + body.lstrip()
        if "security_groups" not in body:
            body = f'\n  security_groups = [aws_security_group.{label_prefix}_alb_sg.id]\n' + body.lstrip()
        return body

    tf_text = _patch_blocks(tf_text, "aws_lb", _ensure_lb)

    # 2) aws_lb_target_group : vpc_id si manquant
    def _ensure_tg(body: str) -> str:
        if "vpc_id" not in body:
            body = f'\n  vpc_id = aws_vpc.{label_prefix}_vpc.id\n' + body.lstrip()
        return body

    tf_text = _patch_blocks(tf_text, "aws_lb_target_group", _ensure_tg)

    return tf_text


def _inject_or_replace_alb_requirements_using_data(tf_text: str, label_prefix: str, name_prefix: str) -> str:
    """
    Mode 'data' (réseau existant) en adopt-or-create pour le SG de l'ALB :
    - data.aws_security_groups.alb (filters: tag:Name + vpc-id)
    - resource aws_security_group <label_prefix>_alb_sg avec count conditionnel
    - locals.alb_sg_id qui choisit data.ids[0] ou resource[0].id
    - aws_lb: subnets = data.aws_subnets.default.ids, security_groups = [local.alb_sg_id]
    - aws_lb_target_group: vpc_id = data.aws_vpc.default.id
    """
    import re

    # 1) data aws_security_groups "alb" correctement filtré (ou normalisé)
    if not re.search(r'\bdata\s+"aws_security_groups"\s+"alb"\s*{', tf_text):
        tf_text += (
            '\n\ndata "aws_security_groups" "alb" {\n'
            '  filter {\n'
            '    name   = "tag:Name"\n'
            f'    values = ["{name_prefix}-alb-sg"]\n'
            '  }\n'
            '  filter {\n'
            '    name   = "vpc-id"\n'
            '    values = [data.aws_vpc.default.id]\n'
            '  }\n'
            '}\n'
        )
    else:
        tf_text = _aws_fix_alb_sg_data_filters(tf_text, name_prefix)

    # 2) resource aws_security_group "<label>_alb_sg" avec count conditionnel
    sg_label = f'{label_prefix}_alb_sg'
    if f'resource "aws_security_group" "{sg_label}"' not in tf_text:
        tf_text += (
            f'\n\nresource "aws_security_group" "{sg_label}" {{\n'
            f'  count = length(data.aws_security_groups.alb.ids) > 0 ? 0 : 1\n'
            f'  name  = "{name_prefix}-alb-sg"\n'
            f'  vpc_id = data.aws_vpc.default.id\n\n'
            f'  ingress {{\n'
            f'    from_port   = 80\n'
            f'    to_port     = 80\n'
            f'    protocol    = "tcp"\n'
            f'    cidr_blocks = ["0.0.0.0/0"]\n'
            f'  }}\n\n'
            f'  egress {{\n'
            f'    from_port   = 0\n'
            f'    to_port     = 0\n'
            f'    protocol    = "-1"\n'
            f'    cidr_blocks = ["0.0.0.0/0"]\n'
            f'  }}\n'
            f'}}\n'
        )

    # 3) locals alb_sg_id (data ou resource[0])
    if not re.search(r'\blocals\s*{[^}]*\balb_sg_id\b', tf_text, re.S):
        tf_text += (
            '\n\nlocals {\n'
            f'  alb_sg_id = length(data.aws_security_groups.alb.ids) > 0\n'
            f'    ? data.aws_security_groups.alb.ids[0]\n'
            f'    : aws_security_group.{sg_label}[0].id\n'
            '}\n'
        )

    # 4) Patch des blocs aws_lb et aws_lb_target_group
    def _patch(hcl: str, res_type: str, ensure):
        pat = re.compile(rf'resource\s+"{res_type}"\s+"[^"]+"\s*{{', re.I)
        out, i = [], 0
        while True:
            m = pat.search(hcl, i)
            if not m:
                out.append(hcl[i:])
                break
            out.append(hcl[i:m.end()])
            j, depth = m.end(), 1
            while j < len(hcl) and depth > 0:
                if hcl[j] == "{": depth += 1
                elif hcl[j] == "}": depth -= 1
                j += 1
            body = hcl[m.end():j-1]
            out.append(ensure(body))
            out.append("}")
            i = j
        return "".join(out)

    def _ensure_lb(body: str) -> str:
        # uniformise security_groups sur local.alb_sg_id
        if "security_groups" in body:
            body = re.sub(r'(security_groups\s*=\s*)\[[^\]]*\]', r'\1[local.alb_sg_id]', body, flags=re.S)
        else:
            body = '\n  security_groups = [local.alb_sg_id]\n' + body.lstrip()
        if "subnets" not in body:
            body = '\n  subnets = data.aws_subnets.default.ids\n' + body.lstrip()
        return body

    def _ensure_tg(body: str) -> str:
        if "vpc_id" not in body:
            body = '\n  vpc_id = data.aws_vpc.default.id\n' + body.lstrip()
        return body

    tf_text = _patch(tf_text, "aws_lb", _ensure_lb)
    tf_text = _patch(tf_text, "aws_lb_target_group", _ensure_tg)

    # 5) (sécurité) si la ressource SG a un count, remplace toute ref '.id' par '[0].id'
    m = re.search(rf'resource\s+"aws_security_group"\s+"{sg_label}"\s*{{(.*?)}}', tf_text, flags=re.S)
    if m and re.search(r'\bcount\s*=', m.group(1)):
        tf_text = re.sub(
            rf'\baws_security_group\.{re.escape(sg_label)}\.id\b',
            rf'aws_security_group.{sg_label}[0].id',
            tf_text
        )

    return tf_text




# ---------- Injection des outputs (AWS) ----------
def _infer_distro_from_label(lbl: str) -> str:
    l = lbl.lower()
    if "windows" in l: return "windows"
    if "ubuntu" in l:  return "ubuntu"
    if "debian" in l:  return "debian"
    if "centos" in l:  return "centos"
    if "rocky" in l:   return "rocky"
    if "amzn" in l or "amazon" in l: return "amazon-linux"
    if "rhel" in l or "redhat" in l: return "rhel"
    return "unknown"


def _infer_family_from_distro(d: str) -> str:
    return "windows" if d == "windows" else "linux"


def _ensure_outputs_aws(tf_text: str) -> str:
    low = tf_text.lower()
    need_ids = 'output "instance_ids"' not in low
    need_ips = 'output "public_ips"' not in low
    need_dist = 'output "distros"' not in low
    need_fam = 'output "os_families"' not in low

    if not (need_ids or need_ips or need_dist or need_fam):
        return tf_text

    labels = re.findall(r'resource\s+"aws_instance"\s+"([a-z0-9_]+)"\s*{', tf_text, flags=re.I)
    if not labels:
        return tf_text

    id_exprs  = [f'aws_instance.{n}[*].id' for n in labels]
    ip_exprs  = [f'aws_instance.{n}[*].public_ip' for n in labels]
    dist_expr = [f'[for _ in aws_instance.{n} : "{_infer_distro_from_label(n)}"]' for n in labels]
    fam_expr  = [f'[for _ in aws_instance.{n} : "{_infer_family_from_distro(_infer_distro_from_label(n))}"]' for n in labels]

    outputs = []
    if need_ids:
        outputs.append(
            "output \"instance_ids\" {\n  value = concat(\n    "
            + ",\n    ".join(id_exprs)
            + "\n  )\n}\n"
        )
    if need_ips:
        outputs.append(
            "output \"public_ips\" {\n  value = concat(\n    "
            + ",\n    ".join(ip_exprs)
            + "\n  )\n}\n"
        )
    if need_dist:
        outputs.append(
            "output \"distros\" {\n  value = concat(\n    "
            + ",\n    ".join(dist_expr)
            + "\n  )\n}\n"
        )
    if need_fam:
        outputs.append(
            "output \"os_families\" {\n  value = concat(\n    "
            + ",\n    ".join(fam_expr)
            + "\n  )\n}\n"
        )

    tf_text = tf_text.rstrip() + "\n\n" + "\n".join(outputs)
    return tf_text

# ---------- Patches post-génération HCL (AWS v5 + noms ALB/TG) ----------
def _aws_fix_deprecations_and_names(tf_text: str, name_prefix: str) -> str:
    """
    - Remplace 'data "aws_subnet_ids"' -> 'data "aws_subnets"' (AWS provider v5+)
    - Corrige/insère 'name' sur aws_lb / aws_lb_target_group:
        * caractères autorisés: [A-Za-z0-9-] (pas d'underscore)
        * longueur max 32
    """
    import re

    # 1) aws_subnet_ids -> aws_subnets
    tf_text = tf_text.replace('data "aws_subnet_ids"', 'data "aws_subnets"')

    def _sanitize_name(val: str) -> str:
        cleaned = re.sub(r'[^A-Za-z0-9-]', '-', val.replace('_', '-'))
        return cleaned[:32]

    def _fix_name_attribute(block_type: str, hcl: str) -> str:
        pattern = re.compile(r'(resource\s+"%s"\s+"[^"]+"\s*{)(.*?)}' % block_type, re.S)
        def repl(m):
            head, body = m.group(1), m.group(2)
            nm = re.search(r'\bname\s*=\s*"([^"]*)"', body)
            if nm:
                fixed = _sanitize_name(nm.group(1))
                body = re.sub(r'\bname\s*=\s*"[^"]*"', f'name = "{fixed}"', body)
            else:
                # injecter un name si absent
                default_name = _sanitize_name(f"{name_prefix}-{'alb' if block_type=='aws_lb' else 'tg'}")
                body = f'\n  name = "{default_name}"\n' + body.lstrip()
            return f"{head}{body}}}"
        return pattern.sub(repl, hcl)

    for t in ("aws_lb", "aws_lb_target_group"):
        tf_text = _fix_name_attribute(t, tf_text)

    return tf_text

def _make_balancer_gateway_prompt(name_prefix: str, label_prefix: str, region: str) -> str:
    """
    Génère un prompt HCL 'adopt-or-create' pour un ALB HTTP public et son TG:
      - Réutilise un SG existant si trouvé (data aws_security_groups avec filters), sinon le crée.
      - Noms ALB/TG avec suffixe déterministe (hash) pour éviter les collisions si l'état TF n'a pas l'historique.
    """
    template = r"""
Tu es un assistant DevOps **strict** spécialisé Terraform. Ta mission : produire **UNIQUEMENT** du HCL brut (pas de Markdown, pas de commentaires, pas de texte avant/après). Si tu n'es pas sûr d'un champ, **n'invente rien** et **omets-le**.

========================
CONTEXTE (tu ne dois PAS l’imprimer)
========================
- Provider: AWS (region = <region>)
- Domaine: balancer_gateway (configure)
- Les instances cibles existent DÉJÀ, avec le tag: Name = "<name_prefix>_instance".
- On réutilise le **VPC par défaut** via data sources. **AUCUNE** création de VPC/Subnet/IGW/Route.
- On veut un **ALB public** (HTTP:80) qui pointe un **Target Group HTTP:80** (target_type = "instance") avec toutes les instances taguées "<name_prefix>_instance".

========================
RÈGLES DE NOMMAGE (OBLIGATOIRE)
========================
- Labels Terraform (2e identifiant après le type) : minuscules/chiffres/underscores **seulement**. **Jamais** de tiret. Exemple : `aws_lb "<label_prefix>_alb"`.
- Attributs AWS `name` et tags `Name` : **tirets** (`-`) uniquement, pas d’underscore, longueur **≤ 32**.
- Pour éviter les collisions, ajoute un suffixe déterministe basé sur un hash du préfixe (ex: `${substr(sha1("<name_prefix>"),0,6)}`).

========================
INTERDITS (REFUSE-LES, N’EN GÉNÈRE PAS)
========================
- **Interdits**: `aws_instance`, `aws_key_pair`, `aws_vpc`, `aws_subnet`, `aws_internet_gateway`, `aws_route_table`,
  `aws_route_table_association`, `aws_route53_*`, `module`, `variable`.
- **Commentaires** et **Markdown** interdits.

========================
OBLIGATIONS (TU DOIS LES RESPECTER)
========================
1) **provider "aws"** (region = <region>).

2) **data sources réseau (VPC par défaut seulement)** :
   - `data "aws_vpc" "default" { default = true }`
   - `data "aws_subnets" "default" { filter { name = "vpc-id" values = [data.aws_vpc.default.id] } }`

3) **data "aws_instances" "targets"** : filtrer `tag:Name = "<name_prefix>_instance"`.

4) **Security Group (adopt-or-create)** :
   - `data "aws_security_groups" "alb"` avec **filters**:
     `
     data "aws_security_groups" "alb" {
       filter {
         name   = "tag:Name"
         values = ["<name_prefix>-alb-sg"]
       }
       filter {
         name   = "vpc-id"
         values = [data.aws_vpc.default.id]
       }
     }
     `
   - `resource "aws_security_group" "<label_prefix>_alb_sg"` avec `count = length(data.aws_security_groups.alb.ids) > 0 ? 0 : 1`,
     ingress 80/tcp ouvert, egress all, `name = "<name_prefix>-alb-sg"`, `tags = { Name = "<name_prefix>-alb-sg" }`,
     `vpc_id = data.aws_vpc.default.id`.
   - **locals** :
     `
     locals {
       alb_sg_id = length(data.aws_security_groups.alb.ids) > 0 ? data.aws_security_groups.alb.ids[0] : aws_security_group.<label_prefix>_alb_sg[0].id
     }
     `

5) **Target Group (HTTP:80)** :
   - `resource "aws_lb_target_group" "<label_prefix>_tg"` :
     - `name = "<name_prefix>-tg-${substr(sha1("<name_prefix>"),0,6)}"`
     - `port = 80`, `protocol = "HTTP"`, `target_type = "instance"`, `vpc_id = data.aws_vpc.default.id`.

6) **ALB public** :
   - `resource "aws_lb" "<label_prefix>_alb"` :
     - `name = "<name_prefix>-alb-${substr(sha1("<name_prefix>"),0,6)}"`
     - `internal = false`, `load_balancer_type = "application"`
     - `security_groups = [local.alb_sg_id]`
     - `subnets = data.aws_subnets.default.ids`

7) **Listener 80** :
   - `resource "aws_lb_listener" "http"` : `load_balancer_arn = aws_lb.<label_prefix>_alb.arn`, `port = 80`, `protocol = "HTTP"`,
     `default_action { type = "forward", target_group_arn = aws_lb_target_group.<label_prefix>_tg.arn }`.

8) **Attachements des cibles** :
   - `resource "aws_lb_target_group_attachment" "<label_prefix>_tg_att"` :
     - `count = length(data.aws_instances.targets.ids)`
     - `target_group_arn = aws_lb_target_group.<label_prefix>_tg.arn`
     - `target_id = data.aws_instances.targets.ids[count.index]`
     - `port = 80`

9) **outputs** (et UNIQUEMENT ceux-là) :
   - `output "alb_arn"      { value = aws_lb.<label_prefix>_alb.arn }`
   - `output "alb_dns_name" { value = aws_lb.<label_prefix>_alb.dns_name }`
   - `output "tg_arn"       { value = aws_lb_target_group.<label_prefix>_tg.arn }`

========================
ORDRE DE SORTIE (EXACTEMENT dans cet ordre, rien d’autre)
========================
1) provider "aws"
2) data "aws_vpc" "default"
3) data "aws_subnets" "default"
4) data "aws_instances" "targets"
5) data "aws_security_groups" "alb"
6) resource "aws_security_group" "<label_prefix>_alb_sg"
7) locals { alb_sg_id = ... }
8) resource "aws_lb_target_group" "<label_prefix>_tg"
9) resource "aws_lb" "<label_prefix>_alb"
10) resource "aws_lb_listener" "http"
11) resource "aws_lb_target_group_attachment" "<label_prefix>_tg_att"
12) outputs (alb_arn, alb_dns_name, tg_arn)

========================
RENDU FINAL
========================
- **Imprime UNIQUEMENT** le HCL (pas de commentaires, pas d’explications, pas de Markdown).
- Respecte strictement les labels et les valeurs indiquées.
"""
    return (
        template
        .replace("<name_prefix>", name_prefix)
        .replace("<label_prefix>", label_prefix)
        .replace("<region>", region)
    )




def _harmonize_sg_and_vpc(tf_text: str, label_prefix: str) -> str:
    """
    Si on a créé le SG '..._alb_sg' en resource, force l'ALB à l'utiliser
    (remplace toute référence data.aws_security_group.*.id).
    """
    import re
    sg_label = f'{label_prefix}_alb_sg'
    has_sg_res = f'resource "aws_security_group" "{sg_label}"' in tf_text
    if has_sg_res:
        tf_text = re.sub(
            r'(security_groups\s*=\s*)\[[^\]]*data\.aws_security_group\.[^\]]+\.id[^\]]*\]',
            rf'\1[aws_security_group.{sg_label}.id]',
            tf_text,
            flags=re.DOTALL,
        )
    return tf_text

def _aws_fix_alb_sg_data_filters(tf_text: str, name_prefix: str) -> str:
    """
    Réécrit TOUT bloc `data "aws_security_groups" "alb" { ... }` en version saine
    (filters 'tag:Name' + 'vpc-id'), avec comptage d’accolades pour ne rien laisser traîner.
    Idempotent.
    """

    pat = re.compile(r'data\s+"aws_security_groups"\s+"alb"\s*{', re.I)
    i, out = 0, []
    while True:
        m = pat.search(tf_text, i)
        if not m:
            out.append(tf_text[i:])
            break

        # tout ce qu'il y a avant le bloc
        out.append(tf_text[i:m.start()])

        # trouver la fin du bloc par comptage d'accolades
        j, depth = m.end(), 1
        while j < len(tf_text) and depth > 0:
            if tf_text[j] == "{":
                depth += 1
            elif tf_text[j] == "}":
                depth -= 1
            j += 1

        # remplacer le bloc entier par une version correcte
        replacement = (
            'data "aws_security_groups" "alb" {\n'
            '  filter {\n'
            '    name   = "tag:Name"\n'
            f'    values = ["{name_prefix}-alb-sg"]\n'
            '  }\n'
            '  filter {\n'
            '    name   = "vpc-id"\n'
            '    values = [data.aws_vpc.default.id]\n'
            '  }\n'
            '}\n'
        )
        out.append(replacement)
        i = j  # reprendre après le bloc original

    return "".join(out)

def _force_vpc_default_true(tf_text: str) -> str:
    import re
    pat = re.compile(r'data\s+"aws_vpc"\s+"default"\s*{', re.I)
    i, out = 0, []
    while True:
        m = pat.search(tf_text, i)
        if not m:
            out.append(tf_text[i:])
            break
        out.append(tf_text[i:m.end()])
        # sauter proprement le corps actuel
        j, depth = m.end(), 1
        while j < len(tf_text) and depth > 0:
            if tf_text[j] == "{": depth += 1
            elif tf_text[j] == "}": depth -= 1
            j += 1
        # remettre un bloc minimal correct
        out.append('\n  default = true\n}\n')
        i = j
    return "".join(out)

# --- TG adopt-or-create (aucun import global requis) -------------------------

def _hash6(s: str) -> str:
    import hashlib
    return hashlib.sha1(s.encode()).hexdigest()[:6]


def _aws_find_existing_tg(decrypted_credentials: dict, region: str, name_prefix: str) -> dict:
    """
    Essaie de retrouver un TG existant côté AWS pour ce préfixe :
      - "<name_prefix>-tg-<hash6>"
      - "<name_prefix>-tg" (legacy)
    Retourne: {"exists": bool, "name": str|None, "arn": str|None}
    Si boto3 indisponible ou VS Code n’utilise pas le bon interpréteur -> fallback create-only.
    """
    try:
        import boto3  # lazy import pour éviter les soucis d'éditeur
        from botocore.exceptions import ClientError
    except Exception:
        return {"exists": False, "name": None, "arn": None}

    session = boto3.Session(
        aws_access_key_id=decrypted_credentials.get("aws_access_key_id"),
        aws_secret_access_key=decrypted_credentials.get("aws_secret_access_key"),
        aws_session_token=decrypted_credentials.get("aws_session_token"),
        region_name=region,
    )
    elb = session.client("elbv2")

    candidates = [
        f"{name_prefix}-tg-{_hash6(name_prefix)}",
        f"{name_prefix}-tg",
    ]

    for name in candidates:
        try:
            resp = elb.describe_target_groups(Names=[name])
            tgs = (resp or {}).get("TargetGroups") or []
            if tgs:
                tg = tgs[0]
                return {"exists": True, "name": tg.get("TargetGroupName"), "arn": tg.get("TargetGroupArn")}
        except Exception as e:
            # Ignore not-found; pour le reste on passe en create
            try:
                from botocore.exceptions import ClientError  # type: ignore
                if isinstance(e, ClientError):
                    code = (e.response or {}).get("Error", {}).get("Code")
                    if code in {"TargetGroupNotFound", "TargetGroupNotFoundException"}:
                        continue
            except Exception:
                pass
            break

    return {"exists": False, "name": None, "arn": None}


def _patch_tg_adopt_or_create(tf_text: str, label_prefix: str, name_prefix: str, tg_info: dict) -> str:
    """
    Adopte un TG existant (data + local.tg_arn) sinon crée un TG avec nom unique (<prefix>-tg-<hash6>),
    et remplace toutes les références vers local.tg_arn (listeners/attachments/outputs). Idempotent.
    """
    import re

    tg_label = f"{label_prefix}_tg"
    hashed_name = f"{name_prefix}-tg-{_hash6(name_prefix)}"

    def _ensure_block(pattern: str, block: str, hcl: str) -> str:
        if re.search(pattern, hcl, flags=re.S):
            return hcl
        return hcl.rstrip() + "\n\n" + block.strip() + "\n"

    def _neutralize_tg_resource(hcl: str) -> str:
        # Ajoute count=0 sur la ressource TG pour éviter de créer si on adopte
        pat = re.compile(
            r'(resource\s+"aws_lb_target_group"\s+"' + re.escape(tg_label) + r'"\s*\{)(.*?)}',
            re.S,
        )
        def repl(m):
            head, body = m.group(1), m.group(2)
            if not re.search(r"\bcount\s*=", body):
                body = "\n  count = 0\n" + body.lstrip()
            return f"{head}{body}}}"
        return pat.sub(repl, hcl)

    def _force_tg_name(hcl: str) -> str:
        # Force un nom unique et déterministe sur la ressource TG
        pat = re.compile(
            r'(resource\s+"aws_lb_target_group"\s+"' + re.escape(tg_label) + r'"\s*\{)(.*?)}',
            re.S,
        )
        def repl(m):
            head, body = m.group(1), m.group(2)
            if re.search(r"\bname\s*=", body):
                body = re.sub(r'\bname\s*=\s*"[^"]*"', f'name = "{hashed_name}"', body)
            else:
                body = f'\n  name = "{hashed_name}"\n' + body.lstrip()
            return f"{head}{body}}}"
        return pat.sub(repl, hcl)

    # 1) Adopter si existant, sinon préparer création avec nom unique
    if tg_info and tg_info.get("exists"):
        adopt_block = f'''
data "aws_lb_target_group" "adopt" {{
  name = "{tg_info["name"]}"
}}
'''.strip()
        tf_text = _ensure_block(r'\bdata\s+"aws_lb_target_group"\s+"adopt"\b', adopt_block, tf_text)

        local_block = '''
locals {
  tg_arn = data.aws_lb_target_group.adopt.arn
}
'''.strip()
        tf_text = _ensure_block(r'\blocals\s*{[^}]*\btg_arn\b', local_block, tf_text)

        tf_text = _neutralize_tg_resource(tf_text)
    else:
        tf_text = _force_tg_name(tf_text)
        local_block = f'''
locals {{
  tg_arn = aws_lb_target_group.{tg_label}.arn
}}
'''.strip()
        tf_text = _ensure_block(r'\blocals\s*{[^}]*\btg_arn\b', local_block, tf_text)

    # 2) Normaliser toutes les refs -> local.tg_arn
    tf_text = re.sub(r'\baws_lb_target_group\.' + re.escape(tg_label) + r'\.arn\b', 'local.tg_arn', tf_text)
    tf_text = re.sub(r'(target_group_arn\s*=\s*)([^\n}]+)', r'\1local.tg_arn', tf_text)

    # 3) Output tg_arn -> local.tg_arn
    if re.search(r'output\s+"tg_arn"\s*{', tf_text):
        tf_text = re.sub(r'(output\s+"tg_arn"\s*{[^}]*value\s*=\s*)([^\n}]+)', r'\1local.tg_arn', tf_text)
    else:
        tf_text += '\n\noutput "tg_arn" {\n  value = local.tg_arn\n}\n'

    return tf_text
# ---------------------------------------------------------------------------




@router.post(
    "/generate/terraform",
    tags=["Génération"],
    summary="Générer un fichier Terraform (create ou configure). Supporte bundle_domains + target_path."
)
async def generate_terraform(
    intent_id: int = Body(..., description="ID de l'intention existante"),
    bundle_domains: Optional[List[str]] = Body(None, description="(configure) Domaines infra à générer ensemble dans un seul fichier (ex: ['balancer_gateway','dns_tls'])."),
    target_path: Optional[str] = Body(None, description="Chemin cible suggéré depuis le plan (basename utilisé comme nom de fichier)."),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    # 1) Charger l’intent (+ session + contrôle d’accès)
    intent = (
        db.query(models.Intent)
        .filter(models.Intent.id == intent_id)
        .join(models.Session)
        .filter(models.Session.user_id == user.id)
        .first()
    )
    if not intent:
        raise HTTPException(status_code=404, detail="Intention introuvable ou non autorisée.")

    session = intent.session
    session_id = session.id
    intent_type = (intent.intent_type or "").lower()

    # Préfixe de nommage lisible pour toutes les ressources
    safe_username = user.email.split("@")[0].replace(".", "_")
    name_prefix = f"{safe_username}-s{session_id}"
    # Label Terraform safe (pas de tirets, minuscules + underscores)
    label_prefix = re.sub(r"[^a-z0-9_]", "_", name_prefix.lower()).replace("-", "_")

    # 2) Parser le prompt (détection provider/VMs si besoin)
    parsed = parse_intent(intent.prompt)

    # ---------- Détection robuste du provider ----------
    provider_name = None

    if intent_type == "create":
        create_actions = [a for a in (parsed.actions or []) if a.type == "create"]
        if create_actions:
            provider_name = (create_actions[0].provider or None)
    else:
        provider_name = next((a.provider for a in (parsed.actions or []) if getattr(a, "provider", None)), None)

    if not provider_name and getattr(session, "provider", None):
        provider_name = session.provider

    if not provider_name:
        last_provider = (
            db.query(models.Provider)
            .filter(
                models.Provider.user_id == user.id,
                models.Provider.session_id == session_id,
            )
            .order_by(models.Provider.created_at.desc())
            .first()
        )
        if last_provider:
            provider_name = last_provider.provider_name

    provider_name = (provider_name or "").lower().strip()
    if not provider_name:
        return {
            "status": "provider_required",
            "message": "Aucun provider détecté. Ajoutez un provider à la session (/providers) ou mentionnez-le dans le prompt (ex: aws)."
        }

    # 3) Charger les credentials du provider détecté
    provider = (
        db.query(models.Provider)
        .filter(
            models.Provider.user_id == user.id,
            models.Provider.session_id == session_id,
            models.Provider.provider_name.ilike(provider_name)
        )
        .order_by(models.Provider.created_at.desc())
        .first()
    )
    if not provider:
        raise HTTPException(
            status_code=400,
            detail=f"Aucun provider '{provider_name}' trouvé pour cette session."
        )

    decrypted_credentials = json.loads(decrypt(provider.encrypted_credentials))
    region = decrypted_credentials.get("region", "eu-west-1")
    school_mode = os.getenv("DAC_SCHOOL_MODE", "false").lower() in {"1", "true", "yes", "on"}
    if school_mode and provider_name != "aws":
        raise HTTPException(
            status_code=400,
            detail="Mode école DAC: seul AWS est autorisé pour le déploiement réel.",
        )

    # 4) Spécs VMs (uniquement pour 'create')
    vm_specs = []
    instance_count = 0
    if intent_type == "create":
        create_actions = [a for a in parsed.actions if a.type == "create"]
        if create_actions:
            action = create_actions[0]
            vm_specs = action.vms or []
            instance_count = sum(vm.count for vm in vm_specs) if vm_specs else 1
        if school_mode:
            max_instances = int(os.getenv("DAC_SCHOOL_MAX_INSTANCES", "1"))
            if instance_count > max_instances:
                raise HTTPException(
                    status_code=400,
                    detail=f"Mode école DAC: maximum {max_instances} VM par création.",
                )

    # 5) Gestion des modes en configure (+ domaine)
    mode = (intent.configure_mode or "").lower() if intent_type == "configure" else None
    single_domain = (intent.configure_domain or "").lower() if intent_type == "configure" else None

    if intent_type == "configure":
        if mode == "system":
            raise HTTPException(
                status_code=400,
                detail="Cette route génère du Terraform. Pour le mode 'system', utilisez la génération Ansible."
            )
        if mode == "mixed" and not bundle_domains:
            raise HTTPException(
                status_code=400,
                detail="Le mode 'mixed' nécessite un plan en 2 étapes (Terraform -> Ansible). Utilisez l’orchestrateur /generate (multi) ou fournissez bundle_domains."
            )
        mode = mode or "infra"


    # --- [ADOPT/CREATE - PRECHECK TG] -------------------------------------------
    tg_info = None

    # S'assurer que provider_l existe ici (provider_name est déjà en lowercase plus haut)
    provider_l = provider_name

    if (
        provider_l == "aws"
        and intent_type == "configure"
        and (
            (single_domain == "balancer_gateway")
            or (bundle_domains and "balancer_gateway" in bundle_domains)
        )
    ):
        # Cherche un TG existant côté AWS pour ce préfixe (ex: "<prefix>-tg-<hash6>" ou legacy "<prefix>-tg")
        tg_info = _aws_find_existing_tg(decrypted_credentials, region, name_prefix)
    # ---------------------------------------------------------------------------


    # 6) Génération clé SSH — **UNIQUEMENT pour 'create'**
    private_key_str = None
    public_key_str = None
    if intent_type == "create":
        key = paramiko.RSAKey.generate(2048)
        private_key_io = io.StringIO()
        key.write_private_key(private_key_io)
        private_key_str = private_key_io.getvalue()
        public_key_str = f"{key.get_name()} {key.get_base64()}"
        private_key_filename = f"id_rsa_{session_id}.pem"
        create_and_store_private_key(
            user_id=user.id,
            session_id=session_id,
            filename=private_key_filename,
            private_key_str=private_key_str
        )

    # 7) Préparation COMMON prompt header
    base_requirements = (
        "Tu es un assistant DevOps expert en Terraform.\n"
        "Génère un fichier STRICTEMENT en HCL (HashiCorp Configuration Language), sans Markdown ni commentaires.\n\n"
        "Règles globales:\n"
        f"- Toutes les ressources et tags 'Name' doivent utiliser le préfixe '{name_prefix}'.\n"
        "- Pas de modules externes. Code minimal, lisible, exécutable.\n"
        "- Pour Route53: ne JAMAIS créer de 'aws_route53_zone'. Utiliser 'data \"aws_route53_zone\"' pour une zone publique EXISTANTE et créer un record **A ALIAS** (pas de CNAME, pas de 'records = [\"1.2.3.4\"]').\n"
    )

    cloud_header_map = {
        "aws": f"- Provider: aws (region = {region})\n",
        "azure": f"- Provider: azurerm (location = {region})\n",
        "gcp": "- Provider: google (zone = europe-west1-b)\n",
    }
    provider_l = provider_name.lower()
    cloud_header = cloud_header_map.get(provider_l)
    if not cloud_header:
        raise HTTPException(status_code=400, detail=f"Provider non supporté : {provider_name}")

    # --- Détails par domaine (helper) ---
    def _domain_detail(provider_lcl: str, domain: str, inferred_zone: str) -> str:
        if domain == "cloud_network":
            if provider_lcl == "aws":
                return (
                    "- Domaine: cloud_network (AWS)\n"
                    "- Réseau géré par intents dédiés; ne pas l'inclure dans CREATE compute.\n"
                    "- Outputs: vpc_id, public_subnet_ids.\n"
                )
            if provider_lcl == "azure":
                return "- Domaine: cloud_network (Azure)\n- VNet/Subnets via intent dédié.\n"
            return "- Domaine: cloud_network (GCP)\n- VPC/subnets via intent dédié.\n"

        if domain == "dns_tls":
            if provider_lcl == "aws":
                return (
                    "- Domaine: dns_tls (AWS)\n"
                    "- Utiliser data \"aws_route53_zone\" pour une zone publique EXISTANTE.\n"
                    "- Créer un record **A ALIAS** 'www' (ou var.record_name) vers l'ALB.\n"
                    "- Outputs: zone_name, (optionnel) record_fqdn.\n"
                )
            if provider_lcl == "azure":
                return "- Domaine: dns_tls (Azure)\n- Record A si endpoint existe.\n"
            return "- Domaine: dns_tls (GCP)\n- Cloud DNS zone existante.\n"

        if domain == "balancer_gateway":
            if provider_lcl == "aws":
                 return (
                    "- Domaine: balancer_gateway (AWS)\n"
                    "- IMPORTANT: Ne crée AUCUN record Route53 dans ce fichier.\n"
                    "- Réutiliser un réseau existant via data sources; SI ABSENT, créer un VPC minimal + 2 subnets publics (AZ a/b).\n"
                    "- ALB public + SG (80 autorisé), TG HTTP:80 (target_type=instance), Listener 80.\n"
                    "- Dans aws_lb: fournis 'subnets' (2 subnets, 2 AZ) et 'security_groups'; dans aws_lb_target_group: 'vpc_id' est OBLIGATOIRE.\n"
                    f"- Récupérer les instances via data \"aws_instances\" filtré par tag Name = \"{name_prefix}_instance\" et attacher via aws_lb_target_group_attachment.\n"
                    "- Outputs: alb_arn, alb_dns_name, tg_arn.\n"
                )
            if provider_lcl == "azure":
                return "- Domaine: balancer_gateway (Azure)\n- LB public minimal.\n"
            return "- Domaine: balancer_gateway (GCP)\n- HTTP LB minimal.\n"

        if domain == "storage":
            if provider_lcl == "aws":
                return "- Domaine: storage (AWS)\n- S3 bucket 's3-<prefix>' SSE-S3.\n"
            if provider_lcl == "azure":
                return "- Domaine: storage (Azure)\n- Storage Account + container.\n"
            return "- Domaine: storage (GCP)\n- GCS bucket.\n"

        if domain == "database":
            if provider_lcl == "aws":
                return "- Domaine: database (AWS)\n- RDS Postgres minimal.\n"
            if provider_lcl == "azure":
                return "- Domaine: database (Azure)\n- Flexible Server Postgres.\n"
            return "- Domaine: database (GCP)\n- Cloud SQL Postgres.\n"

        if domain == "observability":
            if provider_lcl == "aws":
                return "- Domaine: observabilité (AWS)\n- CloudWatch Log Group + alarm CPU.\n"
            if provider_lcl == "azure":
                return "- Domaine: observabilité (Azure)\n- Log Analytics Workspace.\n"
            return "- Domaine: observabilité (GCP)\n- Logging minimal.\n"

        if domain == "identity_access":
            if provider_lcl == "aws":
                return "- Domaine: identity_access (AWS)\n- IAM role + policy lecture S3.\n"
            if provider_lcl == "azure":
                return "- Domaine: identity_access (Azure)\n- App Registration + SP.\n"
            return "- Domaine: identity_access (GCP)\n- Service account + binding viewer.\n"

        if domain == "queue_stream":
            if provider_lcl == "aws":
                return "- Domaine: queue_stream (AWS)\n- SQS + SNS.\n"
            if provider_lcl == "azure":
                return "- Domaine: queue_stream (Azure)\n- Service Bus + queue.\n"
            return "- Domaine: queue_stream (GCP)\n- Pub/Sub topic + subscription.\n"

        if domain == "cdn":
            if provider_lcl == "aws":
                return "- Domaine: cdn (AWS)\n- CloudFront minimal.\n"
            if provider_lcl == "azure":
                return "- Domaine: cdn (Azure)\n- Front Door Standard.\n"
            return "- Domaine: cdn (GCP)\n- Backend Bucket + URL map.\n"

        if domain == "container_orchestration":
            if provider_lcl == "aws":
                return "- Domaine: container_orchestration (AWS)\n- ECS Fargate cluster minimal.\n"
            if provider_lcl == "azure":
                return "- Domaine: container_orchestration (Azure)\n- Container Apps env.\n"
            return "- Domaine: container_orchestration (GCP)\n- GKE minimal.\n"

        return f"- Domaine: {domain} — produire un minimum viable propre avec outputs utiles.\n"

    ALLOWED_INFRA_DOMAINS = {
        "cloud_network", "balancer_gateway", "dns_tls", "storage", "database",
        "observability", "identity_access", "queue_stream", "cdn", "container_orchestration"
    }

    # 8) Construire le prompt GPT
    prompt = None

    SAFE_NAMING_RULES = (
        "- N'utilise JAMAIS de tirets (-) dans les labels de ressources (le 2e identifiant après le type). "
        "Utilise uniquement minuscules, chiffres et underscores. Exemple: 'arnaudgif_s1_vpc', pas 'arnaudgif-s1-vpc'.\n"
        "- Les références doivent utiliser EXACTEMENT ces labels.\n"
        "- Ne redéfinis AUCUN attribut (ex: 'user_data' une seule fois).\n"
        "- Si 'user_data' est vide, omets complètement l'attribut.\n"
        "- Pour les outputs de listes d'instances, utilise: aws_instance.<name>[*].public_ip et aws_instance.<name>[*].id.\n"
    )
    # [P1] --- Règles supplémentaires pour configure (AWS) ---
    AWS_CONFIGURE_HARDENING = (
    "- AWS provider v5+: n'utilise jamais data \"aws_subnet_ids\". Utilise data \"aws_subnets\" (filter vpc-id).\n"
    "- Attribut 'name' pour aws_lb / aws_lb_target_group: uniquement [A-Za-z0-9-], pas d'underscore, longueur ≤ 32.\n"
    "- Les labels Terraform (identifiants après le type) restent en underscore, mais les attributs 'name' AWS doivent être au format hyphen-only.\n"
    "- Security Group de l'ALB: **adopt-or-create** : cherche d'abord avec `data \"aws_security_groups\"` en utilisant des **filters** "
    "`tag:Name = \"<name_prefix>-alb-sg\"` ET `vpc-id = data.aws_vpc.default.id`; sinon crée `aws_security_group` et utilise **locals** pour obtenir l'ID.\n"
    "- Dans resource aws_lb: `security_groups = [local.alb_sg_id]` et `subnets = data.aws_subnets.default.ids`.\n"
    "- Dans resource aws_lb_target_group: `vpc_id` = `data.aws_vpc.default.id`.\n"
)




    if intent_type == "create":
        extra_reqs = (
            "Section COMPUTE (create):\n"
            "- Génère UNIQUEMENT des ressources compute du provider (ex: aws_instance / azurerm_linux_virtual_machine / google_compute_instance).\n"
            "- Inclure type/size, count, IP publique, tags.\n"
            "- Pour AWS: utiliser AMI placeholder 'ami-xxxxxxxx' (remplacée côté backend).\n"
            "- **INTERDIT**: VPC/Subnets/IGW/Routes/ALB/DNS.\n"
            "- Si tu déclares un security group, référence le **VPC par défaut** via data sources:\n"
            '  data "aws_vpc" "default" { default = true }\n'
            '  data "aws_subnets" "default" { filter { name = "vpc-id" values = [data.aws_vpc.default.id] } }\n'
            "- Outputs obligatoires: IPs publiques, IDs des instances (syntaxe [*]).\n"
            + SAFE_NAMING_RULES
        )

        compute_details_map = {
            "aws": (
                f"- Ressource: aws_instance\n"
                f"- AMI: ami-xxxxxxxx\n"
                f"- instance_type: t2.micro\n"
                f"- count: {instance_count or 1}\n"
                f"- associate_public_ip_address = true\n"
                f"- Tags: Name = \"{name_prefix}_instance\"\n"
                f"- 'user_data' est OPTIONNEL: si tu fournis un heredoc, ne rajoute PAS un second 'user_data' vide.\n"
            ),
            "azure": (
                f"- Ressource: azurerm_linux_virtual_machine\n"
                f"- size: Standard_B1s\n"
                f"- count: {instance_count or 1}\n"
                f"- IP publique associée\n"
                f"- Tags: Name = \"{name_prefix}_vm\"\n"
            ),
            "gcp": (
                f"- Ressource: google_compute_instance\n"
                f"- machine_type: f1-micro\n"
                f"- count: {instance_count or 1}\n"
                f"- metadata/tags si besoin (utiliser '{name_prefix}_gce')\n"
            ),
        }
        compute_details = compute_details_map[provider_l]

        prompt = (
            base_requirements
            + cloud_header
            + extra_reqs
            + "\nDétails compute:\n"
            + compute_details
            + f"\nDemande utilisateur: {intent.prompt}\n"
            + " Retourne UNIQUEMENT du HCL brut, sans Markdown."
        )

    elif intent_type == "configure":
        zone_match = re.search(r"\b([a-z0-9-]+(?:\.[a-z0-9-]+)+)\b", intent.prompt.strip(), re.I)
        inferred_zone = zone_match.group(1) if zone_match else "domain.example"

        if bundle_domains:
            invalid = [d for d in bundle_domains if d not in ALLOWED_INFRA_DOMAINS]
            if invalid:
                raise HTTPException(
                    status_code=400,
                    detail=f"Domaines non supportés pour bundle: {invalid}. Autorisés: {sorted(ALLOWED_INFRA_DOMAINS)}",
                )

            details = [_domain_detail(provider_l, d, inferred_zone) for d in bundle_domains]

            integration_hint = ""
            if "balancer_gateway" in bundle_domains and "dns_tls" in bundle_domains and provider_l == "aws":
                integration_hint += "- Pour le DNS, créer un A ALIAS 'www' vers l'ALB.\n"

            #  PROMPT BUNDLE (ne pas utiliser single_domain ici)
            prompt = (
                base_requirements
                + cloud_header
                + "Section INFRA (configure - bundle):\n"
                + "- Génère les domaines listés dans UN SEUL fichier.\n"
                + "- Interdit: création d'instances/clefs SSH.\n"
                + "- Réutiliser le réseau existant via data; SI ABSENT pour ALB, créer un VPC minimal.\n"
                + "- Ajouter des outputs utiles (ARNs/hostnames/IDs).\n"
                + "- Ne crée PAS de Route53 record sauf si 'dns_tls' est inclus.\n"
                + SAFE_NAMING_RULES
                + AWS_CONFIGURE_HARDENING
                + "".join(details)
                + integration_hint
                + f"\nDemande utilisateur: {intent.prompt}\n"
                + " Retourne UNIQUEMENT du HCL brut, sans Markdown."
            )

        else:
            if not single_domain:
                raise HTTPException(status_code=400, detail="Aucun domaine infra fourni/détecté pour cette intention de configuration.")
            if single_domain not in ALLOWED_INFRA_DOMAINS:
                raise HTTPException(status_code=400, detail=f"Domaine infra non supporté par ce générateur Terraform: '{single_domain}'.")

            #  PROMPT SINGLE-DOMAIN
            if single_domain == "balancer_gateway":
                prompt = _make_balancer_gateway_prompt(name_prefix, label_prefix, region)
            else:
                prompt = (
                    base_requirements
                    + cloud_header
                    + "Section INFRA (configure - single domain):\n"
                    + "- Interdit: instances/clé SSH.\n"
                    + "- Réutiliser le réseau existant via data; SI ABSENT pour ALB, créer un VPC minimal.\n"
                    + "- Ne crée PAS de Route53 record sauf si domaine 'dns_tls'.\n"
                    + "- Ajouter des outputs utiles (ARNs/hostnames/IDs).\n"
                    + SAFE_NAMING_RULES
                    + AWS_CONFIGURE_HARDENING
                    + _domain_detail(provider_l, single_domain, inferred_zone)
                    + f"\nDemande utilisateur: {intent.prompt}\n"
                    + " Retourne UNIQUEMENT du HCL brut, sans Markdown."
                )

    else:
        raise HTTPException(status_code=400, detail=f"Intent Terraform non supporté : {intent_type}")

    # 9) Appel GPT
    try:
        gpt_response = await generate_instructions_from_gpt(prompt)
    except Exception as e:
        if hasattr(models.Intent, "generation_status"):
            intent.generation_status = "failed"
            intent.generation_error = f"gpt_error: {e}"
            intent.updated_at = datetime.utcnow() if hasattr(intent, "updated_at") else None
            db.commit()
        raise

    terraform_code = gpt_response.strip()
    if terraform_code.startswith("```"):
        terraform_code = (
            terraform_code.replace("```hcl", "")
            .replace("```terraform", "")
            .replace("```", "")
            .strip()
        )

    if not terraform_code or "resource" not in terraform_code:
        if hasattr(models.Intent, "generation_status"):
            intent.generation_status = "failed"
            intent.generation_error = "invalid_terraform_from_gpt"
            intent.updated_at = datetime.utcnow() if hasattr(intent, "updated_at") else None
            db.commit()
        raise HTTPException(status_code=500, detail="Réponse Terraform invalide:\n" + gpt_response)

    # 10) Détection OS (best effort)
    tf_code_lower = terraform_code.lower()
    ssh_user = "admin"
    base_name = "vm"
    os_family = "linux"
    distro = "generic"
    os_map = {
        "ubuntu": ("ubuntu", "ubuntu-server", "linux", "ubuntu"),
        "debian": ("debian", "debian-node", "linux", "debian"),
        "centos": ("centos", "centos-vm", "linux", "centos"),
        "rocky": ("rocky", "rocky-linux", "linux", "rocky"),
        "amazon-linux": ("ec2-user", "amazon-linux", "linux", "amazon-linux"),
        "amzn": ("ec2-user", "amazon-linux", "linux", "amazon-linux"),
        "rhel": ("ec2-user", "rhel-host", "linux", "rhel"),
        "redhat": ("ec2-user", "rhel-host", "linux", "redhat"),
        "windows": ("Administrator", "win-host", "windows", "windows"),
    }
    for os_key, (user_os, name_os, fam, dist) in os_map.items():
        if os_key in tf_code_lower:
            ssh_user, base_name, os_family, distro = user_os, name_os, fam, dist
            break

    # 11) Normalisation / nettoyage Terraform existant
    terraform_code, ssh_user = build_clean_terraform(terraform_code, decrypted_credentials)

    # 11bis) Patch AWS: data source déprécié + noms ALB/TG valides
    terraform_code = _aws_fix_deprecations_and_names(terraform_code, name_prefix)

    # 11bis+0) Hotfix: forcer le VPC par défaut si besoin
    terraform_code = _force_vpc_default_true(terraform_code)

    # 11bis+1) Hotfix: corriger d'éventuels data "aws_security_groups" mal formés
    terraform_code = _aws_fix_alb_sg_data_filters(terraform_code, name_prefix)

    # 11ter) Validation intent/type (avec contexte de domaine)
    _validate_tf_type(terraform_code, intent_type, single_domain, bundle_domains)

   
    # 12) Ajustements et validations AWS
    if provider_l == "aws":
        # Supprimer Route53 hors scope dns_tls
        terraform_code = _strip_route53_out_of_scope(terraform_code, intent_type, single_domain, bundle_domains)

        # Auto-réseau si ALB et pas de VPC détecté
        contains_balancer = (
            intent_type == "configure"
            and (
                (single_domain == "balancer_gateway")
                or (bundle_domains and "balancer_gateway" in bundle_domains)
            )
        )
        if contains_balancer:
            # 1) Réseau minimal SEULEMENT si aucun VPC/subnet n'est référencé
            terraform_code = _ensure_network_for_alb_if_missing(terraform_code, label_prefix, name_prefix, region)

            # 2) Mode "resource" (réseau créé) vs "data" (VPC par défaut)
            created_network = f'resource "aws_vpc" "{label_prefix}_vpc"' in terraform_code
            if created_network:
                terraform_code = _inject_or_replace_alb_requirements(terraform_code, label_prefix, name_prefix, region)
                # Harmoniser l’utilisation du SG UNIQUEMENT si on a créé le réseau (même VPC)
                terraform_code = _harmonize_sg_and_vpc(terraform_code, label_prefix)
            else:
                # S'assurer que les data sources existent en mode "data"
                if not re.search(r'\bdata\s+"aws_vpc"\s+"default"\s*{', terraform_code):
                    terraform_code += '\n\ndata "aws_vpc" "default" { default = true }\n'
                if not re.search(r'\bdata\s+"aws_subnets"\s+"default"\s*{', terraform_code):
                    terraform_code += (
                        '\n\ndata "aws_subnets" "default" {\n'
                        '  filter {\n'
                        '    name   = "vpc-id"\n'
                        '    values = [data.aws_vpc.default.id]\n'
                        '  }\n'
                        '}\n'
                    )
                terraform_code = _inject_or_replace_alb_requirements_using_data(terraform_code, label_prefix, name_prefix)

            # [ADOPT/CREATE - PATCH TG] : adopte le TG existant sinon crée un nom unique (suffixe sha1)
            terraform_code = _patch_tg_adopt_or_create(
                terraform_code,
                label_prefix,
                name_prefix,
                tg_info or {"exists": False}
            )

        # --- Fix générique "Missing resource instance key" pour SG avec count ---
        # Trouve tous les SG qui ont un 'count = ...' puis remplace .id -> [0].id partout
        sg_with_count = set(re.findall(
            r'resource\s+"aws_security_group"\s+"([^"]+)"\s*{[^}]*\bcount\s*=',
            terraform_code,
            flags=re.S
        ))
        for _sg_lbl in sg_with_count:
            terraform_code = re.sub(
                rf'\baws_security_group\.{re.escape(_sg_lbl)}\.id\b',
                rf'aws_security_group.{_sg_lbl}[0].id',
                terraform_code
            )

        # Validation finale AWS (toujours)
        _validate_tf_aws_sane(terraform_code)


    # ---------- Helpers idempotents pour patch CREATE ----------
    def _has_block(pattern: str) -> bool:
        return re.search(pattern, terraform_code, flags=re.DOTALL) is not None

    def _has_data_aws_vpc_default() -> bool:
        return _has_block(r'\bdata\s+"aws_vpc"\s+"default"\s*{')

    def _has_data_aws_subnets_default() -> bool:
        return _has_block(r'\bdata\s+"aws_subnets"\s+"default"\s*{')

    def _has_sg_ssh_access() -> bool:
        return _has_block(r'\bresource\s+"aws_security_group"\s+"ssh_access"\s*{')

    def _has_keypair_generated() -> bool:
        return _has_block(r'\bresource\s+"aws_key_pair"\s+"generated_key"\s*{')

    # 13) PATCH AWS (CREATE uniquement)
    if provider_l == "aws" and intent_type == "create":
        additions = []

        if not _has_data_aws_vpc_default():
            additions.append(
                '''
data "aws_vpc" "default" {
  default = true
}
'''.lstrip()
            )

        if not _has_data_aws_subnets_default():
            additions.append(
                '''
data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}
'''.lstrip()
            )

        if not _has_sg_ssh_access():
            additions.append(
                f'''
resource "aws_security_group" "ssh_access" {{
  name_prefix = "allow-ssh-{session_id}"
  description = "Allow SSH inbound traffic"
  vpc_id      = data.aws_vpc.default.id
  ingress {{
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }}
  egress {{
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }}
  tags = {{ Name = "{name_prefix}-ssh-sg" }}
}}
'''.lstrip()
            )

        if not _has_keypair_generated():
            unique_suffix = uuid.uuid4().hex[:8]
            additions.append(
                f'''
resource "aws_key_pair" "generated_key" {{
  key_name   = "generated-key-{session_id}-{unique_suffix}"
  public_key = "{public_key_str or ''}"
}}
'''.lstrip()
            )

        if additions:
            terraform_code = terraform_code.rstrip() + "\n\n" + "\n".join(additions)

        # retirer toute présence de user_data existant (multilignes) avant injection
        terraform_code = re.sub(
            r'user_data\s*=\s*<<-?EOF.*?EOF\s*',
            '',
            terraform_code,
            flags=re.DOTALL,
        )
        
        # Injecter SG + user_data + key_name dans chaque aws_instance (en évitant les doublons)
        # On traite chaque ressource aws_instance individuellement pour éviter les doublons
        def inject_instance_attributes(match):
            opening = match.group(1)  # resource "aws_instance" "<name>" {
            # Vérifier si vpc_security_group_ids existe déjà dans ce bloc (scan jusqu'au prochain "}")
            rest_of_text = terraform_code[match.end():]
            # Trouver la fin du bloc (première accolade fermante non imbriquée)
            depth = 1
            block_end = 0
            for i, char in enumerate(rest_of_text):
                if char == '{':
                    depth += 1
                elif char == '}':
                    depth -= 1
                    if depth == 0:
                        block_end = i
                        break
            block_content = rest_of_text[:block_end]
            
            # Vérifier la présence de vpc_security_group_ids dans ce bloc
            has_vpc_sg = re.search(r'\bvpc_security_group_ids\s*=', block_content)
            has_user_data = re.search(r'\buser_data\s*=', block_content)
            has_key_name = re.search(r'\bkey_name\s*=', block_content)
            
            injection = opening
            if not has_vpc_sg:
                injection += '\n  vpc_security_group_ids = [aws_security_group.ssh_access.id]'
            if not has_user_data:
                injection += '\n  user_data = <<EOF\n#!/bin/bash\napt-get update -y\napt-get install -y python3\nEOF'
            if not has_key_name:
                injection += '\n  key_name = aws_key_pair.generated_key.key_name'
            
            return injection
        
        terraform_code = re.sub(
            r'(resource\s+"aws_instance"\s+"[^"]+"\s*{)',
            inject_instance_attributes,
            terraform_code,
        )

        # Injection des outputs (AWS)
        terraform_code = _ensure_outputs_aws(terraform_code)

        # Remplacement défensif seulement en CREATE
        terraform_code = terraform_code.replace("aws_vpc.this.id", "data.aws_vpc.default.id")

    # 14) Sauvegarde (respect du target_path si fourni)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M")
    short_uuid = str(uuid.uuid4())[:6]

    if target_path:
        base = os.path.basename(target_path)
        filename = base if base.endswith(".tf") else f"{base}.tf"
    else:
        nature = "bundle" if (intent_type == "configure" and bundle_domains) else intent_type
        filename = f"tf_{safe_username}_s{session_id}_{nature}_{timestamp}_{short_uuid}.tf"

    tf_file = create_and_store_terraform_file(
        user_id=user.id,
        session_id=session_id,
        filename=filename,
        content=terraform_code,
        ssh_user=ssh_user,
        base_name=base_name,
    )

    # 15) Marquer l’intent comme généré si la colonne existe
    if hasattr(models.Intent, "generation_status"):
        intent.generation_status = "generated"
        if hasattr(models.Intent, "generated_at"):
            intent.generated_at = datetime.utcnow()
        if hasattr(models.Intent, "generation_error"):
            intent.generation_error = None
        db.commit()

    # 16) Réponse
    msg_tail = ""
    if intent_type == "create":
        msg_tail = f" pour {instance_count or 1} ressource(s) compute"
    elif intent_type == "configure":
        if bundle_domains:
            msg_tail = f" bundle: {', '.join(bundle_domains)}"
        else:
            msg_tail = f" domaine infra: {single_domain}"

    return {
        "status": "success",
        "engine": "terraform",
        "terraform_file_id": tf_file.id,
        "filename": tf_file.file_path,
        "ssh_private_key": encrypt(private_key_str) if private_key_str else None,
        "ssh_user": ssh_user,
        "base_name": base_name,
        "os_family": os_family,
        "distro": distro,
        "bundle_domains": bundle_domains or None,
        "message": f" Terraform ({intent_type}) généré sur {provider_name}{msg_tail}.",
    }
