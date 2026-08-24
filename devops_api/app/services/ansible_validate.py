import logging, yaml, re
from copy import deepcopy

logger = logging.getLogger(__name__)

REQUIRED_DEPENDENCIES = {
    # Mots-clés ou modules détectés -> dépendances à injecter (génériques)
    "docker_container": ["python3-pip", "docker"],
    "community.docker.docker_container": ["python3-pip", "docker"],
    "kubernetes.core.helm": ["helm"],
    "lynis": ["lynis"],
    "oscap": ["libopenscap8", "openscap-utils", "scap-security-guide"],
    "auditd": ["auditd", "libauparse0", "audispd-plugins"],
    "ufw": ["ufw"],
    "nginx": ["nginx"],
    "netstat": ["net-tools"],
    # NEW: ss -> iproute2 (pour ss -ltn)
    "ss": ["iproute2"],
}

# --- Ports helpers (NOUVEAU) --------------------------------------------------

PORT_FIELDS = ("published_ports", "ports")

# Regex pour parser les chaînes de published_ports/ports
# Ex: "80:8080", "127.0.0.1:80:8080", "80:8080/tcp"
_PORT_SIMPLE_RE = re.compile(r'^(?P<host>\d+):(?P<target>\d+)(?:/(?P<proto>tcp|udp))?$')
_PORT_WITH_IP_RE = re.compile(r'^(?P<ip>(?:\[[^\]]+\]|[^:]+)):(?P<host>\d+):(?P<target>\d+)(?:/(?P<proto>tcp|udp))?$')

def _parse_published_str(s: str) -> dict | None:
    m = _PORT_SIMPLE_RE.match(s)
    if m:
        d = m.groupdict()
        d["ip"] = None
        return d
    m = _PORT_WITH_IP_RE.match(s)
    if m:
        return m.groupdict()
    return None

# --- Helpers -----------------------------------------------------------------

IGNORED_TASK_KEYS = {
    "name","when","register","changed_when","failed_when","ignore_errors","vars","tags",
    "become","environment","delegate_to","loop","with_items","notify","args"
}

def extract_base_module(task: dict) -> str | None:
    """Retourne le nom du module de la tâche (ex: apt, dnf, win_shell, community.docker.docker_container, ...)"""
    if not isinstance(task, dict):
        return None
    for k in task.keys():
        if k in IGNORED_TASK_KEYS:
            continue
        if k.startswith("ansible.builtin."):
            return k.replace("ansible.builtin.", "")
        return k
    return None

def extract_ports(task: dict) -> list[int]:
    """
    Récupère les ports *hôte* à vérifier dans published_ports et ports (str ou dict).
    Gère: "80:8080", "127.0.0.1:80:8080", "80:8080/tcp", {"published":80,"target":8080}
    """
    ports: list[int] = []
    for _, value in task.items():
        if not isinstance(value, dict):
            continue
        for field in PORT_FIELDS:
            lst = value.get(field)
            if not isinstance(lst, list):
                continue
            for entry in lst:
                if isinstance(entry, str):
                    parsed = _parse_published_str(entry)
                    if parsed and parsed.get("host") and parsed["host"].isdigit():
                        ports.append(int(parsed["host"]))
                elif isinstance(entry, dict):
                    pub = entry.get("published") or entry.get("host_port") or entry.get("published_port")
                    if isinstance(pub, int):
                        ports.append(pub)
                    elif isinstance(pub, str) and pub.isdigit():
                        ports.append(int(pub))
                # Les entiers simples sont ambigus (souvent container_port) -> ignorés
    # Dédup + ordre stable
    seen = set()
    deduped = []
    for p in ports:
        if p not in seen:
            deduped.append(p)
            seen.add(p)
    return deduped

def _linux_check_cmd():
    # Utilise ss si dispo, sinon netstat, et ne renvoie **que** les ports (match exact)
    return ("(command -v ss >/dev/null 2>&1 && ss -H -ltn | awk '{print $4}' | "
            "sed -E 's/.*:([0-9]+)$/\\1/') || "
            "(command -v netstat >/dev/null 2>&1 && netstat -ltn | awk 'NR>2{print $4}' | "
            "sed -E 's/.*:([0-9]+)$/\\1/') || echo ''")

def generate_port_tasks_linux(port: int) -> list[dict]:
    """
    Cherche le premier port libre parmi: p, p+100, p+200, p+300, p+400
    Définit set_fact 'port_<p>' avec la valeur choisie.
    """
    candidates = [port, port+100, port+200, port+300, port+400]
    cand_str = " ".join(str(x) for x in candidates)
    check = _linux_check_cmd()
    default = candidates[0]
    return [
        {
            "name": f"Choisir un port libre pour {port} (Linux)",
            "shell": (
                f"CANDS='{cand_str}'; CHOSEN=''; "
                f"for P in $CANDS; do OUT=$({check}); echo \"$OUT\" | grep -qx \"$P\" && continue; CHOSEN=$P; break; done; "
                f"echo ${{CHOSEN:-{default}}}"
            ),
            "register": f"port_{port}_probe_linux",
            "ignore_errors": True,
            "changed_when": False,
            "when": "ansible_os_family != 'Windows'"
        },
        {
            "name": f"Définir port alternatif (Linux) pour {port}",
            "set_fact": {
                f"port_{port}": f"{{{{ (port_{port}_probe_linux.stdout | default('{port}')) | int }}}}"
            },
            "when": "ansible_os_family != 'Windows'"
        },
        {
            "name": f"[Check] Port choisi pour {port}",
            "debug": {"msg": f"port_{port} = {{{{ port_{port} | default('UNDEF') }}}}"}
        }
    ]

def generate_port_tasks_windows(port: int) -> list[dict]:
    """
    Équivalent Windows (PowerShell): teste p, p+100, p+200, p+300, p+400
    """
    candidates = [port, port+100, port+200, port+300, port+400]
    ps_array = ",".join(str(x) for x in candidates)
    return [
        {
            "name": f"Choisir un port libre pour {port} (Windows)",
            "win_shell": (
                f"$ports=@({ps_array}); $chosen=$null; "
                f"foreach($p in $ports) {{ "
                f"  $inUse = (netstat -an | Select-String -Pattern \":$p\\s\").Length -gt 0; "
                f"  if(-not $inUse) {{ $chosen=$p; break }} "
                f"}} "
                f"if($chosen) {{ Write-Output $chosen }} else {{ Write-Output {port} }}"
            ),
            "register": f"port_{port}_probe_win",
            "ignore_errors": True,
            "changed_when": False,
            "when": "ansible_os_family == 'Windows'"
        },
        {
            "name": f"Définir port alternatif (Windows) pour {port}",
            "set_fact": {
                f"port_{port}": f"{{{{ (port_{port}_probe_win.stdout | default('{port}')) | int }}}}"
            },
            "when": "ansible_os_family == 'Windows'"
        }
    ]

def patch_ports(task: dict, ports: list[int]) -> dict:
    """
    Remplace les ports hôte détectés par {{ port_<host> }} dans published_ports et ports,
    en préservant IP/PROTO si présents.
    Gère les chaînes et les dicts {"published":..., "target":...}
    """
    task = deepcopy(task)
    for _, value in task.items():
        if not isinstance(value, dict):
            continue
        for field in PORT_FIELDS:
            lst = value.get(field)
            if not isinstance(lst, list):
                continue
            new_lst = []
            for entry in lst:
                # Chaînes "80:8080", "127.0.0.1:80:8080", "80:8080/tcp"
                if isinstance(entry, str):
                    parsed = _parse_published_str(entry)
                    if parsed and parsed.get("host") and parsed["host"].isdigit():
                        host = int(parsed["host"])
                        if host in ports:
                            host_j2 = f"{{{{ port_{host} }}}}"
                            ip = parsed.get("ip")
                            target = parsed.get("target")
                            proto = parsed.get("proto")
                            if ip:
                                patched = f"{ip}:{host_j2}:{target}"
                            else:
                                patched = f"{host_j2}:{target}"
                            if proto:
                                patched += f"/{proto}"
                            new_lst.append(patched)
                            continue
                    new_lst.append(entry)

                # Dict {"published": 80, "target": 8080, ...}
                elif isinstance(entry, dict):
                    e = deepcopy(entry)
                    pub_key = None
                    if "published" in e: pub_key = "published"
                    elif "host_port" in e: pub_key = "host_port"
                    elif "published_port" in e: pub_key = "published_port"
                    pub_val = e.get(pub_key)
                    if isinstance(pub_val, str) and pub_val.isdigit():
                        pub_val = int(pub_val)
                    if isinstance(pub_val, int) and pub_val in ports and pub_key:
                        e[pub_key] = f"{{{{ port_{pub_val} }}}}"
                    new_lst.append(e)

                else:
                    new_lst.append(entry)

            value[field] = new_lst
    return task

def extract_tools_from_task(task: dict) -> set[str]:
    tools = set()
    # modules explicites
    for key in task:
        if key in REQUIRED_DEPENDENCIES:
            tools.add(key)
        if key.startswith("community.docker") or key.startswith("kubernetes.core"):
            tools.add("docker")
    # commandes
    for k in ["shell", "command", "cmd", "win_shell", "win_command"]:
        if k in task:
            content = task[k]
            texts = [content] if isinstance(content, str) else content if isinstance(content, list) else []
            for part in texts:
                matches = re.findall(r"\b([a-z0-9_\-]+)(?=\s|$)", part)
                tools.update(matches)
    return tools

def deps_tasks_for_tool(tool: str) -> list[dict]:
    """Génère des tâches d'install adaptées par famille d'OS (skip Windows)"""
    pkgs = REQUIRED_DEPENDENCIES.get(tool, [])
    tasks = []
    if not pkgs:
        return tasks

    # Debian/Ubuntu
    tasks.append({
        "name": f"Installer dépendances ({tool}) [Debian/Ubuntu]",
        "apt": {"name": pkgs if len(pkgs) > 1 else pkgs[0], "state": "present", "update_cache": True},
        "when": "ansible_os_family == 'Debian'"
    })
    # RedHat family
    tasks.append({
        "name": f"Installer dépendances ({tool}) [RedHat]",
        "dnf": {"name": pkgs if len(pkgs) > 1 else pkgs[0], "state": "present"},
        "when": "ansible_os_family == 'RedHat'"
    })
    # Suse
    tasks.append({
        "name": f"Installer dépendances ({tool}) [Suse]",
        "zypper": {"name": pkgs if len(pkgs) > 1 else pkgs[0], "state": "present"},
        "when": "ansible_os_family == 'Suse'"
    })
    # Jamais sur Windows
    return tasks

def _task_defines_port_var(task: dict, p: int) -> bool:
    # set_fact: port_<p>
    if isinstance(task, dict) and "set_fact" in task and isinstance(task["set_fact"], dict):
        if f"port_{p}" in task["set_fact"]:
            return True
    # registres/nom standardisés
    reg = task.get("register", "")
    if reg in (f"port_{p}_probe_linux", f"port_{p}_probe_win"):
        return True
    name = (task.get("name") or "").lower()
    if f"port libre pour {p}" in name or f"port alternatif" in name:
        return True
    # tag optionnel
    tags = task.get("tags", [])
    if isinstance(tags, list) and f"port-guard-{p}" in tags:
        return True
    return False

def _has_port_guard(tasks: list[dict], p: int) -> bool:
    for t in tasks:
        if _task_defines_port_var(t, p):
            return True
    return False


# --- Fixers ------------------------------------------------------------------

def fix_common_issues(task: dict) -> dict | list[dict]:
    task = deepcopy(task)
    injected = []

    # Dépendances implicites
    tools = extract_tools_from_task(task)
    for t in tools:
        if t in REQUIRED_DEPENDENCIES or t in {"docker","helm","lynis","auditd","nginx","ufw","oscap","libopenscap8","openscap-utils","scap-security-guide","python3-pip"}:
            injected.extend(deps_tasks_for_tool(t))

    # Cas spécial: redémarrage nginx
    if task.get("name","").lower().startswith("redémarrer") and "nginx" in str(task).lower():
        injected += [
            {"name": "Forcer systemd daemon-reload", "systemd": {"daemon_reload": True}, "when": "ansible_os_family != 'Windows'"},
            {"name": "Activer NGINX au démarrage", "systemd": {"name": "nginx", "enabled": True}, "when": "ansible_os_family != 'Windows'"},
            task,
            {
                "name": "Vérifier statut NGINX (Linux)",
                "shell": "systemctl status nginx || journalctl -xeu nginx",
                "register": "nginx_status",
                "ignore_errors": True,
                "changed_when": False,
                "when": "ansible_os_family != 'Windows'"
            }
        ]
        return injected

    # Docker: afficher logs après création du conteneur
    for key in ["docker_container", "community.docker.docker_container"]:
        if key in task and isinstance(task[key], dict):
            cname = task[key].get("name")
            if cname:
                injected.append(task)
                injected.append({
                    "name": f"Logs du conteneur {cname}",
                    "shell": f"docker logs {cname}",
                    "register": f"{cname}_logs",
                    "ignore_errors": True,
                    "changed_when": False,
                    "when": "ansible_os_family != 'Windows'"
                })
                return injected

    if injected:
        injected.append(task)
        return injected

    return task

def fix_invalid_packages(task: dict) -> dict:
    corrections = {
        "openscap-scanner": "libopenscap8",
        "openscap-utils": "libopenscap8",
        "openscap": "libopenscap8",
        "oscap": "libopenscap8",
        "python-pip": "python3-pip",
        "pip": "python3-pip",
        "audit": "auditd",
        "auditctl": "auditd",
        "audispd": "auditd",
        "docker-py": "docker",
        "docker.io": "docker",
        "scap": "scap-security-guide"
    }
    task = deepcopy(task)
    for k in ["apt","yum","dnf","zypper","package"]:
        if k in task:
            name = task[k].get("name")
            if isinstance(name, str) and name in corrections:
                task[k]["name"] = corrections[name]
            elif isinstance(name, list):
                task[k]["name"] = [corrections.get(pkg, pkg) for pkg in name]
    return task

# --- Validator ---------------------------------------------------------------

TASK_LEVEL_KEYS = {
    "name","when","register","changed_when","failed_when","ignore_errors","vars","tags",
    "become","environment","delegate_to","loop","with_items","notify","args"
}

SHELL_META_CHARS_RE = re.compile(r"[|&;><`$()]", re.ASCII)

def _module_key_and_val(task: dict) -> tuple[str|None, object]:
    """Retourne (module_key, module_val) en ignorant les clés de niveau tâche."""
    if not isinstance(task, dict):
        return None, None
    for k, v in task.items():
        if k in TASK_LEVEL_KEYS:
            continue
        return k, v
    return None, None

def _lift_task_level_keys(task: dict) -> dict:
    """
    Si le dict du module contient par erreur des clés de niveau tâche (register, ignore_errors, when, become...),
    on les remonte au niveau de la tâche.
    """
    t = deepcopy(task)
    mkey, mval = _module_key_and_val(t)
    if mkey and isinstance(mval, dict):
        to_delete = []
        for k in list(mval.keys()):
            if k in TASK_LEVEL_KEYS:
                # remonte la valeur, ne pas écraser si déjà présent au niveau tâche
                t.setdefault(k, mval[k])
                to_delete.append(k)
        for k in to_delete:
            del t[mkey][k]
    return t

# --- Pré-nettoyage YAML pour lignes shell/command ----------------------------

_SHELL_LINE_RE = re.compile(
    r'^(?P<indent>\s*)(?P<fullkey>(?:ansible\.(?:builtin|legacy)\.)?(?:shell|command)):\s*(?P<value>.+)$',
    re.MULTILINE
)

def _canonicalize_shell_like_lines(cleaned: str) -> str:
    """
    Convertit les lignes de type:
      '<indent>shell: <commande...>'
    en bloc littéral YAML:
      '<indent>shell: |\\n<indent>  <commande...>'
    Sauf si la valeur commence déjà par |, >, {, [ (déjà un bloc/dict/liste).
    Cela évite les erreurs YAML quand il y a des guillemets imbriqués.
    """
    def repl(m: re.Match) -> str:
        indent = m.group("indent")
        fullkey = m.group("fullkey")
        value = m.group("value").rstrip()
        v0 = value.lstrip()
        if v0.startswith(('|', '>', '{', '[')):
            return m.group(0)
        return f"{indent}{fullkey}: |\n{indent}  {value}"
    return _SHELL_LINE_RE.sub(repl, cleaned)

# -----------------------------------------------------------------------------

def validate_ansible_playbook(playbook_content: str) -> str:
    cleaned = (playbook_content or "").strip()

    # Nettoyage fences ``` éventuels
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(yaml|yml)?", "", cleaned, flags=re.I).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()

    # Canonicaliser toutes les lignes shell/command en bloc littéral pour éviter les guillemets imbriqués
    cleaned = _canonicalize_shell_like_lines(cleaned)

    try:
        data = yaml.safe_load(cleaned)
    except yaml.YAMLError as e:
        raise ValueError(f"YAML invalide : {e}")

    if not isinstance(data, list) or not data:
        raise ValueError("Le playbook doit être une liste de plays débutant par '- hosts: ...'.")

    root = data[0]
    if not isinstance(root, dict):
        raise ValueError("Le premier bloc doit être un dictionnaire (play).")

    # Assurer gather_facts & become
    root.setdefault("gather_facts", True)
    root.setdefault("become", True)

    tasks_key = "tasks" if "tasks" in root else "pre_tasks" if "pre_tasks" in root else None
    if not tasks_key:
        raise ValueError("Aucun bloc 'tasks' trouvé.")
    orig_tasks = list(root[tasks_key] or [])
    new_tasks: list[dict] = []

    # Indexation sûre : pré-calcul des noms existants et des gardes ports déjà présents
    existing_names = {t.get("name","") for t in orig_tasks if isinstance(t, dict)}
    guarded_ports: set[int] = set()
    for t in orig_tasks:
        if not isinstance(t, dict):
            continue
        # détecter tous les ports déjà "gardés"
        for p in range(1, 65536):
            # (optimisation légère: on n'itère pas tout, on détecte via motifs)
            # On scanne quelques patterns connus plutôt qu'une boucle complète
            if _task_defines_port_var(t, p):
                guarded_ports.add(p)
        # alternative plus réaliste: inspecter par motifs communs
        m = re.findall(r"port_(\d+)", str(t))
        for x in m:
            try:
                px = int(x)
                if _task_defines_port_var(t, px):
                    guarded_ports.add(px)
            except Exception:
                pass

    def _append_with_normalization(task_obj: dict):
        """Normalise et ajoute une tâche à new_tasks (lift, fix pkgs, timeout, deps, windows become...)."""
        if not isinstance(task_obj, dict):
            return
        task = _lift_task_level_keys(task_obj)
        task = fix_invalid_packages(task)

        # Normalisation command -> shell si méta-caractères
        mkey, mval = _module_key_and_val(task)
        if mkey in ("command", "ansible.builtin.command", "ansible.legacy.command"):
            if isinstance(mval, dict):
                cmd = mval.get("cmd") or mval.get("_raw_params")
            else:
                cmd = mval
            if isinstance(cmd, str) and SHELL_META_CHARS_RE.search(cmd):
                new_key = "ansible.builtin.shell" if (mkey or "").startswith("ansible.builtin") else "shell"
                task[new_key] = cmd
                if mkey in task:
                    del task[mkey]
                mkey, mval = new_key, cmd

        # Timeout 30s sur shell Linux (pas sur win_shell)
        mkey, mval = _module_key_and_val(task)
        if mkey in ("shell", "ansible.builtin.shell") and isinstance(mval, str):
            if not mval.lstrip().startswith("timeout "):
                task[mkey] = f"timeout 30s {mval}"

        # Debug auto après ignore_errors + ensure register
        if any(k in task for k in ("shell","command","win_shell","win_command")) and task.get("ignore_errors"):
            if "register" not in task:
                task["register"] = "task_result"
            reg = task.get("register", "task_result")
            new_tasks.append(task)
            new_tasks.append({
                "name": f"Afficher debug après échec potentiel [{task.get('name','cmd')}]",
                "debug": {"msg": f"{{{{ {reg}.stderr | default({reg}.stdout | default('aucune sortie')) }}}}"}
            })
            return  # déjà ajouté les deux

        # Dépendances explicites par mot-clé/module
        full_str = str(task)
        module_key = extract_base_module(task)
        for keyword, _ in REQUIRED_DEPENDENCIES.items():
            if keyword in full_str or keyword == module_key:
                dep_tasks = deps_tasks_for_tool(keyword)
                for dep in dep_tasks:
                    if dep["name"] not in existing_names:
                        new_tasks.append(dep)
                        existing_names.add(dep["name"])

        # Garde-fou Windows: désactiver become si module Windows utilisé
        module_key = extract_base_module(task)
        if module_key and (module_key.startswith("win_") or module_key.startswith("ansible.windows.") or module_key.startswith("chocolatey.")):
            task.setdefault("become", False)

        new_tasks.append(task)

    for task in orig_tasks:
        if not isinstance(task, dict):
            # On passe tel quel (ligne vide ou commentaire déjà parsé)
            new_tasks.append(task)
            continue

        # 0) Lift dès le départ
        task = _lift_task_level_keys(task)

        # 1) Corriger paquets invalides
        task = fix_invalid_packages(task)

        # 2) Ports dynamiques (Linux + Windows) — support published_ports & ports
        ports = extract_ports(task)
        if ports:
            # Injecter gardes uniquement pour les ports non déjà couverts
            to_guard = [p for p in ports if p not in guarded_ports]
            for p in to_guard:
                # Linux + Windows
                for t_ins in generate_port_tasks_linux(p) + generate_port_tasks_windows(p):
                    _append_with_normalization(t_ins)
                guarded_ports.add(p)
            # Patch la tâche pour utiliser {{ port_<p> }}
            task = patch_ports(task, ports)

        # 3) Fix récurrents (dépendances implicites, logs docker, nginx, etc.)
        fixed = fix_common_issues(task)
        if isinstance(fixed, list):
            for t_new in fixed:
                _append_with_normalization(t_new)
            continue
        else:
            task = fixed  # déjà normalisé pkgs etc. dans _append_with_normalization

        # 4..7) Normalisations/déps/windows via helper
        _append_with_normalization(task)

    # Écrire la nouvelle liste de tâches
    root[tasks_key] = new_tasks

    return yaml.dump(data, allow_unicode=True, sort_keys=False)
