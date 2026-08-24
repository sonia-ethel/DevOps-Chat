# app/services/intent_parser.py
from __future__ import annotations
import re, unicodedata
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from difflib import get_close_matches

# --------- Comportement ----------
# Si True, on fusionne plusieurs domaines infra trouvés dans un même segment
# en UNE action configure (domains=[...]) plutôt que 1 action par domaine.
MERGE_INFRA_DOMAINS = True

# ---------- Data models ----------
@dataclass
class VMRequest:
    os: str
    count: int = 1
    size: Optional[str] = None
    region: Optional[str] = None

@dataclass
class Action:
    type: str  # "create" | "configure" | "audit" | "kubernetes"
    provider: Optional[str] = None
    vms: List[VMRequest] = field(default_factory=list)
    domains: List[str] = field(default_factory=list)   # ex: ["dns_tls","system_service"]
    mode: Optional[str] = None                         # "infra" | "system" | "mixed"
    raw: str = ""                                      # sous-prompt exact extrait

@dataclass
class ParsedIntent:
    actions: List[Action] = field(default_factory=list)
    raw: str = ""   # prompt complet

# ---------- Normalization helpers ----------
WORDS_TO_NUM = {
    "zero":0,"un":1,"une":1,"deux":2,"trois":3,"quatre":4,"cinq":5,"six":6,"sept":7,"huit":8,"neuf":9,"dix":10,
    "one":1,"two":2,"three":3,"four":4,"five":5,"six_en":6,"seven":7,"eight":8,"nine":9,"ten":10
}
OS_CANON = ["ubuntu","debian","centos","rocky","almalinux","amazonlinux","windows"]
OS_SYNONYMS = {
    "ubuntu":["ubutu","ubutun","ubunutu","ubunt","ubnt","u20","u22","ubuntu20","ubuntu22","ubuntu 20","ubuntu 22"],
    "debian":["debiane","deb","debians"],
    "centos":["cent0s","cent os","centos7","centos8"],
    "rocky":["rockylinux","rhel8","rhel9"],
    "almalinux":["alma","alma linux","almalnx","alma8","alma9"],
    "amazonlinux":["amzn","amazon linux","al2","al2023","amazonlinux2","amazon linux 2"],
    "windows":["win","win2019","win2022","windows server","windowsserver","ws2019","ws2022"]
}
PROVIDERS = ["aws","azure","gcp"]

# ---------- Domain patterns (élargis avec synonymes EN/FR) ----------
DOMAIN_PATTERNS = {
    # Réseau & sécurité
    "cloud_network": r"\b("
        r"vpc|subnet|subnets|subnetwork|subnetworks|igw|internet gateway|nat\s?gateway|natgw|"
        r"eip|elastic ip|static ip|public static ip|allocate-address|associate-address|"
        r"route\s?table|route\s?tables|rtb|nacl|network access control list|cidr|peering|vpc peering|transit gateway|tgw|"
        r"vpc endpoint|interface endpoint|gateway endpoint|endpoint service|"
        r"security group|security groups|sgs?|ingress|egress|"
        r"eni|elastic network interface|placement group|"
        # déclencheurs “naturels” (non-tech)
        r"ouvre l'?acc[eè]s|ouvre|open|autorise|allow|expose|exposer|"
        r"port[s]?\s*\d+|port 80|port 22|acc[eè]s web|web access|ssh access|http 80|ssh 22"
    r")\b",

    # Load balancers & API Gateway ( sans 'http'/'https' pour éviter faux positifs)
    "balancer_gateway": r"\b("
        r"alb|nlb|elb|gwlb|gateway load balancer|"
        r"listener|listeners|target\s?group|target\s?groups|tg|health\s?check|stickiness|"
        r"ssl policy|"
        r"api gateway|application load balancer|network load balancer|classic load balancer|load\s*balanc(e|er)"
    r")\b",

    # DNS & TLS/ACM
    "dns_tls": r"\b("
        r"route ?53|route53|hosted zone|record set|dns|zone|record|"
        r"a record|aaaa|cname|txt|mx|srv|"
        r"acm|certificate manager|certificat|certificate|certbot|"
        r"https|tls|ssl|let'?s encrypt|letsencrypt"
    r")\b",

    # Compute (EC2/ASG/Launch Templates/AMI/Spot/EBS/Snapshots/KeyPair/UserData)
    "compute": r"\b("
        r"ec2|instance|instances|asg|auto\s?scaling|launch template|launch configuration|instance profile|"
        r"ami|image|golden image|"
        r"spot\s?(fleet|request|instance)|on-?demand|capacity reservation|dedicated (host|instance)|"
        r"ebs|volume|volumes|snapshot|snapshots|"
        r"key\s?pair|keypair|ssh key|public key|\.pem|user\s?data"
    r")\b",

    # Conteneurs / Orchestration
    "container_orchestration": r"\b("
        r"ecs|fargate|task definition|task|service|cluster|"
        r"eks|node\s?group|managed node group|kubernetes|k8s"
    r")\b",

    # Stockage
    "storage": r"\b("
        r"s3|bucket|bucket policy|oac bucket|versioning|lifecycle|encryption|sse-?s3|kms|"
        r"efs|mount target|nfs|"
        r"ebs|volume|snapshot"
    r")\b",

    # Bases de données & cache
    "database": r"\b("
        r"rds|aurora|postgres|postgresql|mysql|mariadb|parameter group|subnet group|"
        r"elasticache|redis|memcached"
    r")\b",

    # Observabilité
    "observability": r"\b("
        r"cloudwatch|log group|logs|metric|alarm|dashboard|insights|x-?ray"
    r")\b",

    # Identité & accès (et KMS)
    "identity_access": r"\b("
        r"iam|role|policy|user|group|assume role|permission|instance profile|"
        r"kms|customer managed key|key policy"
    r")\b",

    # Queue & streaming
    "queue_stream": r"\b("
        r"sqs|sns|kinesis|msk|kafka|eventbridge|event bridge|event bus"
    r")\b",

    # CDN & edge
    "cdn": r"\b("
        r"cloudfront|distribution|origin|behavior|cache|oac|origin access control|"
        r"waf|shield"
    r")\b",

    # Système (VM)
    "system_firewall": r"\b(ufw|iptables|firewalld|pare-?feu)\b",
    "system_service": r"\b(nginx|apache|httpd|apache2|iis|docker|node\b|pm2|gunicorn|systemd|certbot|app|web\s?server|site web)\b",
}

INFRA_DOMAINS = {
    "cloud_network","balancer_gateway","dns_tls","compute","container_orchestration",
    "storage","database","observability","identity_access","queue_stream","cdn"
}
SYSTEM_DOMAINS = {"system_firewall","system_service"}

# ---------- Utilitaires ----------
def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")

def normalize(text: str) -> str:
    t = _strip_accents(text or "")
    t = t.lower().strip()
    # nombres en lettres -> chiffres
    def repl_wordnum(m):
        w = m.group(0)
        return str(WORDS_TO_NUM.get(w, w))
    t = re.sub(r"\b(" + "|".join(map(re.escape, WORDS_TO_NUM.keys())) + r")\b", repl_wordnum, t)
    # formats “x2”, “*3”
    t = re.sub(r"\bx\s*(\d+)\b", r"\1", t)
    t = re.sub(r"\*(\d+)\b", r"\1", t)
    # normalisation espaces +
    t = re.sub(r"\s*\+\s*", " + ", t)
    t = re.sub(r"\s+", " ", t)
    return t

def canon_os(token: str) -> Optional[str]:
    token = token.lower().strip()
    if token in OS_CANON:
        return token
    for base, syns in OS_SYNONYMS.items():
        if token in syns or get_close_matches(token, [base]+syns, n=1, cutoff=0.8):
            return base
    return None

# ---------- Parsing VMs ----------
VM_RE = re.compile(r"\b(?:(\d+)\s+)?(ubuntu|debian|centos|rocky|almalinux|amazon ?linux|windows|ubutu|ubutun|ubunutu|alma|amzn|al2|al2023|ubuntu20|ubuntu22|amazonlinux2)\b", re.I)

def extract_vms(t: str) -> List[VMRequest]:
    vms: List[VMRequest] = []
    for m in VM_RE.finditer(t):
        cnt = int(m.group(1) or 1)
        raw = m.group(2).replace(" ", "")
        os_c = canon_os(raw) or raw.lower()
        if os_c == "amazonlinux" or raw.lower() in {"amazonlinux","amazon linux","amzn","al2","al2023","amazonlinux2","amazon linux 2"}:
            os_c = "amazonlinux"
        vms.append(VMRequest(os=os_c, count=cnt))
    # fusion par OS
    agg = {}
    for vm in vms:
        agg[vm.os] = agg.get(vm.os, 0) + vm.count
    return [VMRequest(os=k, count=v) for k, v in agg.items()]

# ---------- Providers ----------
def detect_provider(t: str) -> Optional[str]:
    if re.search(r"\b(aws|amazon( ec2)?|route ?53|cloudfront|rds|eks|ec2|alb|cloudwatch|iam|s3|lambda)\b", t):
        return "aws"
    if re.search(r"\b(azure|microsoft azure|azurerm|application gateway|appgw|vnet|vmss|cosmosdb|aks)\b", t):
        return "azure"
    if re.search(r"\b(gcp|google cloud|gce|gke|cloud dns|pub/sub|bigquery)\b", t):
        return "gcp"
    for p in PROVIDERS:
        if re.search(rf"\b{p}\b", t):
            return p
    return None

# ---------- Heuristiques d'intentions “naturelles” ----------
def _has_ports_open_request(t: str) -> bool:
    t = t.lower()
    return bool(
        re.search(r"(ouvre|open|autorise|allow|expose|exposer)", t)
        and re.search(r"(port[s]?\s*\d+|port 80|port 22|http 80|ssh 22|acc[eè]s web|web access|ssh access)", t)
    )

def _wants_public_url(t: str) -> bool:
    t = t.lower()
    return bool(re.search(r"\b(url|lien|navigateur|browser|accessible|public|exposer|expose|domain|domaine)\b", t))

def _wants_dns_tls(t: str) -> bool:
    t = t.lower()
    return bool(re.search(r"\b(https|tls|ssl|certificat|certificate|acm|let'?s encrypt|letsencrypt|route ?53|dns|cname|a record|enregistrer un domaine)\b", t))

def _strong_lb_signals(t: str) -> bool:
    # indices FORTS d'infra LB (création/attachement/ressources LB)
    return bool(re.search(
        r"(listener|target\s?group|health\s?check|register|deregister|attachment|"
        r"aws_lb\b|aws_lb_listener\b|aws_lb_target_group\b|aws_lb_target_group_attachment\b)",
        t, re.IGNORECASE
    ))

def _augment_ports_to_cloud_network(text: str, hits: List[str]) -> List[str]:
    # Si ports/accès web/ssh mentionnés, forcer cloud_network
    if _has_ports_open_request(text) and "cloud_network" not in hits:
        hits = hits + ["cloud_network"]
    return hits

def _augment_outcomes(text: str, hits: List[str], vms_count: int) -> List[str]:
    """
    - URL publique -> cloud_network
    - HTTPS/Cert/DNS -> dns_tls
    - multi-VM OU sémantique "load balancer/une URL pour plusieurs" (+ signaux forts) -> balancer_gateway
    """
    t = text.lower()

    # HTTPS/DNS -> dns_tls
    if _wants_dns_tls(t) and "dns_tls" not in hits:
        hits = hits + ["dns_tls"]

    # URL publique -> au minimum SG
    if _wants_public_url(t) and "cloud_network" not in hits:
        hits = hits + ["cloud_network"]

    # ALB quand pertinent :
    wants_lb_words = bool(re.search(r"\b(load[\s-]?balanc(e|er)|repartition|repartir|haute disponibilite|ha|scal(e|ing)|balanceur)\b", t))
    strong = _strong_lb_signals(t)
    if (vms_count > 1 or wants_lb_words) and (strong or wants_lb_words):
        if "balancer_gateway" not in hits:
            hits = hits + ["balancer_gateway"]

    return hits

# ---------- Domains & modes ----------
def detect_domains_and_mode(t: str) -> Tuple[List[str], Optional[str]]:
    # Désambig: "target group" + (alb|load balancer) -> c'est du LB, pas de l'IAM
    block_identity_access = bool(
        re.search(r"\btarget\s+group\b", t, re.I)
        and re.search(r"\b(alb|load\s*balancer)\b", t, re.I)
    )

    hits = [d for d, pat in DOMAIN_PATTERNS.items() if re.search(pat, t)]
    if block_identity_access and "identity_access" in hits:
        hits = [d for d in hits if d != "identity_access"]

    # Renforce cloud_network si ports/accès web
    hits = _augment_ports_to_cloud_network(t, hits)

    # Outcomes (url publique, https/dns, multi-VM -> ALB)
    vms_in_text = extract_vms(t) or []
    vms_count = sum(vm.count for vm in vms_in_text) if vms_in_text else 0
    hits = _augment_outcomes(t, hits, vms_count)

    # Mode après augmentations
    has_infra = any(d in INFRA_DOMAINS for d in hits)
    has_system = any(d in SYSTEM_DOMAINS for d in hits)
    if has_infra and has_system:
        mode = "mixed"
    elif has_infra:
        mode = "infra"
    elif has_system:
        mode = "system"
    else:
        mode = None

    return hits, mode

# ---------- Actions ----------
def detect_actions(t: str) -> List[str]:
    acts = set()
    if re.search(r"\b(create|creer|cré(?:er|ation)|provision|deploy|deploie|launch|spin up|build|make|spawn|lancer)\b", t):
        acts.add("create")
    if re.search(r"\b(configure|configurer|setup|set up|hardening|expose|exposer|ouvrir|ajoute|add|installe|install|enable|attach|associate|allocate|route|dns|certificat|certbot)\b", t):
        acts.add("configure")
    if re.search(r"\b(audit|verifie|verify|scan|check|analyse|inspect)\b", t):
        acts.add("audit")
    if re.search(r"\b(k8s|kubernetes|eks|gke|aks)\b", t):
        acts.add("kubernetes")
    return sorted(acts)

# ---------- Split helpers ----------
CREATE_VERBS = r"(?:cr[ée]er?|creer|create|provision|d[ée]ployer|deploy|launch|spawn|build|spin up|lancer)"
CONFIG_VERBS = r"(?:configurer|configure|setup|set up|hardening|expose|exposer|ouvrir|ajoute|add|installe|install|enable|attach|associate|allocate|dns|route|certificat|certbot|https|tls|ssl)"
CONNECTORS = r"(?:\bet\b|\band\b|\bavec\b|/|,|\+|\bvia\b|\bsur\b|\bpour\b)"
VM_TOKEN = r"(?:(\d+)\s+)?(ubuntu|debian|centos|rocky|almalinux|amazon ?linux|windows|ubutu|ubutun|ubunutu|alma|amzn|al2|al2023|ubuntu20|ubuntu22|amazonlinux2)"
VM_SEQ = rf"{VM_TOKEN}(?:\s*(?:,|\bet\b|\band\b|\+)\s*{VM_TOKEN})*"

def split_create_config(seg: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Agrège toutes les séquences de VMs dans CREATE.
    Ne bascule vers CONFIGURE que si le reste n'est plus une séquence VM
    et contient des indices de config/infra.
    """
    s = seg.strip()
    if not s:
        return None, None

    pat = re.compile(
        rf"^(?P<prefix>.*?{CREATE_VERBS}\s+)?(?P<vmblock>{VM_SEQ})\s*(?P<rest>.*)$",
        re.IGNORECASE
    )
    m = pat.match(s)
    if not m:
        if re.search(CONFIG_VERBS, s, re.IGNORECASE):
            return None, s
        return None, None

    prefix = (m.group("prefix") or "").strip()
    vmblock = (m.group("vmblock") or "").strip()
    rest = (m.group("rest") or "").strip()

    raw_create = " ".join(x for x in [prefix, vmblock] if x).strip()

    while rest:
        m2 = re.match(rf"^(?:{CONNECTORS}\s*)?(?P<vmnext>{VM_SEQ})\s*(?P<rest>.*)$", rest, re.IGNORECASE)
        if not m2:
            break
        vmnext = (m2.group("vmnext") or "").strip()
        rest = (m2.group("rest") or "").strip()
        raw_create = f"{raw_create} et {vmnext}".strip()

    if not rest:
        return raw_create or None, None

    looks_infra = re.search(
        r"(alb|nlb|elb|route ?53|dns|acm|tls|https|listener|target group|vpc|subnet|iam|s3|rds|asg|health ?check|certificate|certbot)",
        rest, re.IGNORECASE
    )
    looks_config = re.search(CONFIG_VERBS, rest, re.IGNORECASE)

    if looks_infra or looks_config:
        rest = re.sub(rf"^(?:{CONNECTORS}\s*)+", "", rest, flags=re.IGNORECASE).strip(" ,;./+")
        return raw_create or None, (rest or None)

    return raw_create or None, None

# ---------- Heuristique: vrai travail LB vs simple mention d'ALB ----------
def _looks_strict_lb_infra(text: str) -> bool:
    """
    Retourne True si 'text' contient des indices FORTS d'infra ALB/NLB
    (création/attachement/ressources LB), pas juste une mention contextuelle d'ALB.
    """
    return bool(re.search(
        r"(listener|target\s?group|health\s?check|register|deregister|attachment|"
        r"aws_lb\b|aws_lb_listener\b|aws_lb_target_group\b|aws_lb_target_group_attachment\b)",
        text, re.IGNORECASE
    ))

# ---------- Main parser ----------
def parse_intent(text: str) -> ParsedIntent:
    raw = text or ""
    actions: List[Action] = []

    # 1) découpe en sous-phrases grossières
    rough_segments = [seg.strip() for seg in re.split(r"[;,.]+", raw) if seg.strip()]

    for seg in rough_segments:
        seg_added = False  # évite le fallback si on a déjà ajouté des actions
        # 2) split create vs configure
        raw_create, raw_config = split_create_config(seg)

        # 3) CREATE
        if raw_create:
            t_create = normalize(raw_create)
            provider_c = detect_provider(t_create) or detect_provider(normalize(seg))
            vms = extract_vms(t_create)
            if vms or re.search(rf"\b{CREATE_VERBS}\b", raw_create, re.IGNORECASE):
                actions.append(Action(
                    type="create",
                    provider=provider_c,
                    vms=vms,
                    raw=raw_create.strip()
                ))
                seg_added = True
                
                #  PROTECTION: Si raw_config est vide ou ne contient QUE du compute/infra
                # sans verbes explicites de configuration, ignorer raw_config
                if raw_config and not re.search(CONFIG_VERBS, raw_config, re.IGNORECASE):
                    # raw_config ne contient pas de verbes de config (configure, install, etc.)
                    # C'est probablement juste "ec2 t3" après "créer ubuntu"
                    # -> on le supprime pour ne pas créer une action configure dupliquée
                    raw_config = None

        # 4) CONFIGURE
        if raw_config:
            t_conf = normalize(raw_config)
            provider_k = detect_provider(t_conf) or detect_provider(normalize(seg))
            domains, _mode_detected = detect_domains_and_mode(t_conf)

            # Si aucun domaine détecté mais des mots systèmes, force system_service
            if not domains and re.search(DOMAIN_PATTERNS["system_service"], t_conf):
                domains, _mode_detected = ["system_service"], "system"

            if domains:
                infra_domains = [d for d in domains if d in INFRA_DOMAINS]
                system_domains = [d for d in domains if d in SYSTEM_DOMAINS]

                # Filtre anti-bruit: si on a du système ET seulement 'balancer_gateway' en infra,
                # mais sans indices forts d'infra LB -> on retire 'balancer_gateway'
                if ("balancer_gateway" in infra_domains and system_domains
                        and not _looks_strict_lb_infra(t_conf)):
                    infra_domains = [d for d in infra_domains if d != "balancer_gateway"]

                # 4a) action(s) INFRA
                if infra_domains:
                    if MERGE_INFRA_DOMAINS:
                        actions.append(Action(
                            type="configure",
                            provider=provider_k,
                            domains=list(dict.fromkeys(infra_domains)),
                            mode="infra",
                            raw=raw_config.strip()
                        ))
                    else:
                        for d in dict.fromkeys(infra_domains):
                            actions.append(Action(
                                type="configure",
                                provider=provider_k,
                                domains=[d],
                                mode="infra",
                                raw=raw_config.strip()
                            ))
                    seg_added = True

                # 4b) action SYSTEM (séparée)
                if system_domains:
                    actions.append(Action(
                        type="configure",
                        provider=provider_k,
                        domains=list(dict.fromkeys(system_domains)),
                        mode="system",
                        raw=raw_config.strip()
                    ))
                    seg_added = True
            else:
                # Aucun domaine trouvé : heuristique infra courante
                if re.search(r"(alb|dns|certbot|acm|route53|tls|https|vpc|subnet|iam|s3|rds|asg|target group|listener)", t_conf):
                    d2, _m2 = detect_domains_and_mode(t_conf)
                    if d2:
                        infra_domains = [d for d in d2 if d in INFRA_DOMAINS]
                        system_domains = [d for d in d2 if d in SYSTEM_DOMAINS]

                        # Même filtre anti-bruit pour ALB
                        if ("balancer_gateway" in infra_domains and system_domains
                                and not _looks_strict_lb_infra(t_conf)):
                            infra_domains = [d for d in infra_domains if d != "balancer_gateway"]

                        if infra_domains:
                            actions.append(Action(
                                type="configure",
                                provider=provider_k,
                                domains=list(dict.fromkeys(infra_domains)),
                                mode="infra",
                                raw=raw_config.strip()
                            ))
                            seg_added = True
                        if system_domains:
                            actions.append(Action(
                                type="configure",
                                provider=provider_k,
                                domains=list(dict.fromkeys(system_domains)),
                                mode="system",
                                raw=raw_config.strip()
                            ))
                            seg_added = True

        # 5) Fallback UNIQUEMENT si rien n'a été ajouté pour ce segment
        if not seg_added and not raw_create and not raw_config:
            t_all = normalize(seg)
            provider_a = detect_provider(t_all)
            vms_all = extract_vms(t_all)
            acts = detect_actions(t_all)

            #  PRIORITY: Si on détecte des VMs, c'est du CREATE -> ignorer CONFIGURE
            if vms_all or ("create" in acts):
                actions.append(Action(type="create", provider=provider_a, vms=vms_all, raw=seg))
                seg_added = True
                #  NE PAS ajouter d'action configure pour ce segment

            # Configure SEULEMENT si pas de VMs et pas d'action create détectée
            if not seg_added:
                d_all, _m_all = detect_domains_and_mode(t_all)
                if d_all or ("configure" in acts):
                    if not d_all and re.search(DOMAIN_PATTERNS["system_service"], t_all):
                        d_all, _m_all = ["system_service"], "system"
                    if d_all:
                        infra_domains = [d for d in d_all if d in INFRA_DOMAINS]
                        system_domains = [d for d in d_all if d in SYSTEM_DOMAINS]

                        # Filtre anti-bruit pour ALB aussi en fallback
                        if ("balancer_gateway" in infra_domains and system_domains
                                and not _looks_strict_lb_infra(t_all)):
                            infra_domains = [d for d in infra_domains if d != "balancer_gateway"]

                        if infra_domains:
                            actions.append(Action(
                                type="configure",
                                provider=provider_a,
                                domains=list(dict.fromkeys(infra_domains)),
                                mode="infra",
                                raw=seg
                            ))
                            seg_added = True
                        if system_domains:
                            actions.append(Action(
                                type="configure",
                                provider=provider_a,
                                domains=list(dict.fromkeys(system_domains)),
                                mode="system",
                                raw=seg
                            ))
                            seg_added = True

            if ("audit" in acts):
                actions.append(Action(type="audit", provider=provider_a, raw=seg))
            if ("kubernetes" in acts):
                actions.append(Action(type="kubernetes", provider=provider_a, raw=seg))

    return _dedupe_actions(ParsedIntent(actions=actions, raw=raw))

# --------- Déduplication finale (sécurité) ----------
def _normalize_prompt_dedupe(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())

def _dedupe_actions(parsed: ParsedIntent) -> ParsedIntent:
    seen = set()
    uniq: List[Action] = []
    for a in parsed.actions:
        key = (
            a.type,
            (a.provider or "").lower(),
            (a.mode or "").lower(),
            tuple(a.domains or []),  # ordre conservé
            _normalize_prompt_dedupe(a.raw),
        )
        if key in seen:
            continue
        seen.add(key)
        uniq.append(a)
    parsed.actions = uniq
    return parsed
