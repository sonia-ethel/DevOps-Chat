# app/routes/generate_audit.py

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from app import models, database
from app.auth import get_current_user
from app.services.gpt_service import generate_instructions_from_gpt
from app.services.ansible_service import validate_ansible_playbook
from app.services.intent_parser import parse_intent
from app.utils.file_utils import create_and_store_audit_file
from app.paths import AUDITS_DIR as BASE_AUDIT_DIR

import os
import re
import uuid

router = APIRouter()

SUPPORTED_TOOLS = {
    "lynis",
    "auditd",
    "windows-auditpol",
    "windows-defender",
    "windows-eventlog",
    "osquery",
}

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post(
    "/generate/audit",
    tags=["Génération"],
    summary="Générer un playbook d’audit à partir d’un intent"
)
async def generate_audit(
    intent_id: int = Body(..., description="ID de l'intention existante"),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    # 1) Charger l’intent (sécurisé à l'utilisateur)
    intent = (
        db.query(models.Intent)
        .filter(models.Intent.id == intent_id)
        .join(models.Session)
        .filter(models.Session.user_id == user.id)
        .first()
    )
    if not intent:
        raise HTTPException(status_code=404, detail="Intent introuvable ou non autorisé.")

    # 2) Déterminer l’outil d’audit : intent.audit_tool > parse_intent > erreur
    parsed = parse_intent(intent.prompt)
    audit_actions = [a for a in parsed.actions if a.type == "audit"]
    audit_tool = (intent.audit_tool or "").strip().lower() if intent.audit_tool else None
    if not audit_tool and audit_actions:
        # si ton parseur expose .tool/.tools on les lit; sinon on reste None
        action = audit_actions[0]
        audit_tool = getattr(action, "tool", None) or (action.tools[0] if getattr(action, "tools", None) else None)
        audit_tool = (audit_tool or "").strip().lower() or None

    if not audit_tool:
        raise HTTPException(status_code=400, detail=" Outil d’audit non défini (lynis, auditd, windows-auditpol, windows-defender, windows-eventlog, osquery).")

    if audit_tool not in SUPPORTED_TOOLS:
        raise HTTPException(status_code=400, detail=f"Outil d’audit invalide : {audit_tool}")

    # 3) Lire l’inventaire récent (pour guider le prompt)
    inv = (
        db.query(models.GeneratedInventoryFile)
        .filter_by(session_id=intent.session.id, user_id=user.id)
        .order_by(models.GeneratedInventoryFile.created_at.desc())
        .first()
    )

    inventory_hint = ""
    if inv and os.path.exists(inv.file_path):
        try:
            with open(inv.file_path, "r", encoding="utf-8") as f:
                inv_txt = f.read()
        except Exception:
            inv_txt = ""
        low = inv_txt.lower()
        has_windows = ("winrm" in low) or ("ansible_connection=winrm" in low) or bool(re.search(r"\bwindows\b", low))
        has_linux = ("ansible_connection=ssh" in low) or bool(re.search(r"\b(ubuntu|debian|rhel|redhat|centos|rocky|amzn|amazon linux|suse|sles)\b", low, re.I))
        detected = []
        if has_windows: detected.append("windows")
        if has_linux:   detected.append("linux")
        if detected:
            inventory_hint = " | OS détectés dans l'inventaire: " + ", ".join(detected)

    # 4) Prompt GPT selon l’outil
    if audit_tool == "lynis":
        prompt = (
    "Tu es un assistant DevOps **ultra-expert** en Ansible.\n"
    f"{inventory_hint}\n\n"
    " Mission : générer un **playbook YAML pur** (sans markdown, sans commentaires) pour exécuter un **audit de sécurité Lynis**.\n"
    "Le playbook doit être **idempotent**, **multi-distro Linux** et **ignorer Windows** proprement.\n\n"

    " Contraintes de sortie (OBLIGATOIRES) :\n"
    "- **YAML strict uniquement**, aucune explication, aucun balisage Markdown.\n"
    "- Un seul play :\n"
    "  - `- hosts: all`\n"
    "  - `gather_facts: true`\n"
    "  - `become: true` (Linux) ; aucune tâche Windows ne doit utiliser `become`.\n"
    "  - `tasks:` avec des `name:` **clairs et uniques**.\n"
    "- Utiliser les **FQCN** pour tous les modules (ex: `ansible.builtin.apt`, `ansible.builtin.dnf`, "
    "`ansible.builtin.yum`, `ansible.builtin.zypper`, `ansible.builtin.shell`, `ansible.builtin.copy`, `ansible.builtin.debug`).\n"
    "- **Une seule action/module par tâche** (si deux actions, créer deux tâches).\n"
    "- Ne jamais utiliser `sudo` en ligne de commande (laisser Ansible élever via `become`).\n\n"

    " Ciblage OS (via facts & host vars) :\n"
    "- **Linux** seulement : `when: ansible_system == 'Linux'` ou familles `Debian`/`RedHat`/`Suse`.\n"
    "- **Windows** : toutes les tâches doivent être **skippées** (`when:` inverse explicite) ; n’emploie **aucun** module Windows.\n\n"

    " Installation Lynis (selon distro) :\n"
    "- Debian/Ubuntu (`ansible_os_family == 'Debian'`) : installer paquet `lynis` via `ansible.builtin.apt` avec `update_cache: yes`.\n"
    "- RedHat/CentOS/Rocky (`ansible_os_family == 'RedHat'`) :\n"
    "  • Si nécessaire, installer `epel-release` via `ansible.builtin.dnf` (ou `ansible.builtin.yum`) **dans une tâche séparée**.\n"
    "  • Installer `lynis` via `ansible.builtin.dnf` (ou `ansible.builtin.yum`) — **une seule** des deux par tâche, conditionnée via `when:`.\n"
    "- Amazon Linux :\n"
    "  • AL2023 -> `ansible.builtin.dnf`, AL2 -> `ansible.builtin.yum` (conditionner sur `ansible_distribution_major_version`).\n"
    "- SLES/SUSE (`ansible_os_family == 'Suse'`) : installer `lynis` via `ansible.builtin.zypper` avec `update_cache: yes`/`refresh: yes`.\n\n"

    " Exécution de l’audit :\n"
    "- Lancer `lynis audit system` via `ansible.builtin.shell` **sur Linux uniquement**.\n"
    "- `register: lynis_result`, `ignore_errors: true`, `changed_when: false`.\n"
    "- Écrire `{{ lynis_result.stdout }}` dans `/tmp/lynis_output.log` avec `ansible.builtin.copy` (`content:`), mode `0644`.\n"
    "- Afficher **uniquement** les lignes contenant `Hardening index` via `ansible.builtin.debug` "
    "(ex: `msg: {{ lynis_result.stdout_lines | select('search', 'Hardening index') | list }}`).\n"
    "- Optionnel : afficher aussi les lignes contenant `[WARNING]` (même filtrage) dans une **tâche séparée**.\n\n"

    " Modèle minimal attendu (à adapter par distro et avec `when:` précis) :\n"
    "- hosts: all\n"
    "  gather_facts: true\n"
    "  become: true\n"
    "  tasks:\n"
    "    # Exemple Debian/Ubuntu\n"
    "    - name: Debian | Mettre à jour l'index APT\n"
    "      ansible.builtin.apt:\n"
    "        update_cache: true\n"
    "      when: ansible_os_family == 'Debian'\n"
    "    - name: Debian | Installer Lynis\n"
    "      ansible.builtin.apt:\n"
    "        name: lynis\n"
    "        state: present\n"
    "      when: ansible_os_family == 'Debian'\n"
    "    # Exemple RedHat (adapter dnf/yum selon disponibilité)\n"
    "    - name: RedHat | (Optionnel) Installer EPEL\n"
    "      ansible.builtin.dnf:\n"
    "        name: epel-release\n"
    "        state: present\n"
    "      when: ansible_os_family == 'RedHat'\n"
    "    - name: RedHat | Installer Lynis\n"
    "      ansible.builtin.dnf:\n"
    "        name: lynis\n"
    "        state: present\n"
    "      when: ansible_os_family == 'RedHat'\n"
    "    # Exemple SUSE\n"
    "    - name: Suse | Actualiser Zypper\n"
    "      ansible.builtin.zypper:\n"
    "        name: lynis\n"
    "        state: present\n"
    "        update_cache: true\n"
    "      when: ansible_os_family == 'Suse'\n"
    "    # Audit (Linux uniquement)\n"
    "    - name: Linux | Exécuter Lynis\n"
    "      ansible.builtin.shell: lynis audit system\n"
    "      register: lynis_result\n"
    "      changed_when: false\n"
    "      ignore_errors: true\n"
    "      when: ansible_system == 'Linux'\n"
    "    - name: Linux | Sauvegarder le rapport Lynis\n"
    "      ansible.builtin.copy:\n"
    "        dest: /tmp/lynis_output.log\n"
    "        content: \"{{ lynis_result.stdout | default('') }}\"\n"
    "        mode: '0644'\n"
    "      when: ansible_system == 'Linux'\n"
    "    - name: Linux | Afficher Hardening index\n"
    "      ansible.builtin.debug:\n"
    "        msg: \"{{ (lynis_result.stdout_lines | default([])) | select('search', 'Hardening index') | list }}\"\n"
    "      when: ansible_system == 'Linux'\n"
    "    - name: Linux | (Optionnel) Avertissements Lynis\n"
    "      ansible.builtin.debug:\n"
    "        msg: \"{{ (lynis_result.stdout_lines | default([])) | select('search', '\\\\[WARNING\\\\]') | list }}\"\n"
    "      when: ansible_system == 'Linux'\n\n"

    " Sortie attendue : **YAML pur uniquement**, sans texte ni ```.\n"
    "Génère maintenant le playbook d’audit Lynis conforme.\n"
)
    elif audit_tool == "auditd":
        # (contenu identique à ta version — abrégé ici pour la réponse)
        prompt = (
    "Tu es un assistant DevOps **ultra-expert** en Ansible.\n"
    f"{inventory_hint}\n\n"
    " Mission : générer un **playbook YAML pur** (sans markdown, sans commentaires) pour réaliser un **audit via auditd**.\n"
    "Le playbook doit être **idempotent**, **multi-distro Linux** et **ignorer Windows** proprement.\n\n"

    " Contraintes de sortie (OBLIGATOIRES) :\n"
    "- **YAML strict uniquement**, aucune explication, aucun balisage Markdown.\n"
    "- Un seul play :\n"
    "  - `- hosts: all`\n"
    "  - `gather_facts: true`\n"
    "  - `become: true` (Linux) ; aucune tâche Windows ne doit utiliser `become`.\n"
    "  - `tasks:` avec des `name:` **clairs et uniques**.\n"
    "- Utiliser les **FQCN** pour tous les modules (ex: `ansible.builtin.apt`, `ansible.builtin.dnf`, "
    "`ansible.builtin.yum`, `ansible.builtin.zypper`, `ansible.builtin.systemd`, "
    "`ansible.builtin.shell`, `ansible.builtin.copy`, `ansible.builtin.debug`).\n"
    "- **Une seule action/module par tâche** (si deux actions, créer deux tâches).\n"
    "- Ne jamais utiliser `sudo` en ligne de commande (laisser Ansible élever via `become`).\n\n"

    " Ciblage OS :\n"
    "- **Linux uniquement** (incluant Debian/Ubuntu, RedHat/CentOS/Rocky, Amazon Linux, Suse). "
    "Skipper toutes les tâches sur Windows via `when:` explicite (ex: `when: ansible_os_family != 'Windows'`).\n\n"

    " Installation & service (selon distro) :\n"
    "- Debian/Ubuntu (`ansible_os_family == 'Debian'`) :\n"
    "  • Mettre à jour l’index APT (`update_cache: true`) dans une tâche dédiée.\n"
    "  • Installer le paquet **auditd** via `ansible.builtin.apt`.\n"
    "- RedHat/CentOS/Rocky (`ansible_os_family == 'RedHat'`) : installer le paquet **audit** via `ansible.builtin.dnf` "
    "(ou `ansible.builtin.yum` si `dnf` non disponible — choisir une seule méthode par tâche avec `when:`).\n"
    "- Amazon Linux :\n"
    "  • AL2023 -> `ansible.builtin.dnf`\n"
    "  • AL2 -> `ansible.builtin.yum`\n"
    "  (conditionner sur `ansible_distribution_major_version`).\n"
    "- SLES/SUSE (`ansible_os_family == 'Suse'`) : installer le paquet **audit** via `ansible.builtin.zypper` "
    "(`update_cache: true`/`refresh: true`).\n"
    "- Activer et démarrer le service **auditd** via `ansible.builtin.systemd` (Linux uniquement).\n\n"

    " Audit & collecte :\n"
    "- Exécuter `auditctl -s` via `ansible.builtin.shell` (Linux uniquement) avec `register: auditctl_result`, "
    "`ignore_errors: true`, `changed_when: false`.\n"
    "- Exécuter `ausearch --start recent --limit 10` via `ansible.builtin.shell` avec `register: ausearch_result`, "
    "`ignore_errors: true`, `changed_when: false`.\n"
    "- Écrire dans `/tmp/auditd_output.log` le **résumé structuré** (état `auditctl -s` puis 10 derniers événements) "
    "via `ansible.builtin.copy` (`content:`), mode `'0644'`.\n"
    "- Afficher un **résumé** via `ansible.builtin.debug` (quelques lignes clés de `auditctl -s` et le nombre d’événements retournés).\n\n"

    " Modèle minimal attendu (à adapter par distro et avec `when:` précis) :\n"
    "- hosts: all\n"
    "  gather_facts: true\n"
    "  become: true\n"
    "  tasks:\n"
    "    # Debian/Ubuntu\n"
    "    - name: Debian | Mettre à jour l'index APT\n"
    "      ansible.builtin.apt:\n"
    "        update_cache: true\n"
    "      when: ansible_os_family == 'Debian'\n"
    "    - name: Debian | Installer auditd\n"
    "      ansible.builtin.apt:\n"
    "        name: auditd\n"
    "        state: present\n"
    "      when: ansible_os_family == 'Debian'\n"
    "\n"
    "    # RedHat family (choisir dnf ou yum via when)\n"
    "    - name: RedHat | Installer audit (dnf)\n"
    "      ansible.builtin.dnf:\n"
    "        name: audit\n"
    "        state: present\n"
    "      when: ansible_os_family == 'RedHat'\n"
    "\n"
    "    # Suse\n"
    "    - name: Suse | Installer audit\n"
    "      ansible.builtin.zypper:\n"
    "        name: audit\n"
    "        state: present\n"
    "        update_cache: true\n"
    "      when: ansible_os_family == 'Suse'\n"
    "\n"
    "    # Amazon Linux (exemple AL2023)\n"
    "    - name: Amazon Linux | Installer audit (dnf)\n"
    "      ansible.builtin.dnf:\n"
    "        name: audit\n"
    "        state: present\n"
    "      when: ansible_distribution == 'Amazon' and ansible_distribution_major_version is version('2023', '>=')\n"
    "\n"
    "    # Service auditd (Linux uniquement)\n"
    "    - name: Linux | Activer et démarrer auditd\n"
    "      ansible.builtin.systemd:\n"
    "        name: auditd\n"
    "        enabled: true\n"
    "        state: started\n"
    "      when: ansible_os_family != 'Windows'\n"
    "\n"
    "    # Auditctl & Ausearch (Linux uniquement)\n"
    "    - name: Linux | État auditctl\n"
    "      ansible.builtin.shell: timeout 30s auditctl -s\n"
    "      register: auditctl_result\n"
    "      changed_when: false\n"
    "      ignore_errors: true\n"
    "      when: ansible_os_family != 'Windows'\n"
    "    - name: Linux | Derniers événements ausearch\n"
    "      ansible.builtin.shell: timeout 30s ausearch --start recent --limit 10\n"
    "      register: ausearch_result\n"
    "      changed_when: false\n"
    "      ignore_errors: true\n"
    "      when: ansible_os_family != 'Windows'\n"
    "\n"
    "    - name: Linux | Sauvegarder le rapport auditd\n"
    "      ansible.builtin.copy:\n"
    "        dest: /tmp/auditd_output.log\n"
    "        mode: '0644'\n"
    "        content: |\n"
    "          === auditctl -s ===\n"
    "          {{ auditctl_result.stdout | default('') }}\n"
    "          \n"
    "          === ausearch recent (10) ===\n"
    "          {{ ausearch_result.stdout | default('') }}\n"
    "      when: ansible_os_family != 'Windows'\n"
    "\n"
    "    - name: Linux | Résumé auditd\n"
    "      ansible.builtin.debug:\n"
    "        msg:\n"
    "          - \"Etat: {{ (auditctl_result.stdout_lines | default([]))[:5] }}\"\n"
    "          - \"Evenements: {{ (ausearch_result.stdout_lines | default([])) | length }}\"\n"
    "      when: ansible_os_family != 'Windows'\n\n"

    " Sortie attendue : **YAML pur uniquement**, sans texte ni ```.\n"
    "Génère maintenant le playbook d’audit **auditd** conforme.\n"
)
    elif audit_tool == "windows-auditpol":
        prompt = (
    "Tu es un assistant DevOps **ultra-expert** en Ansible.\n"
    f"{inventory_hint}\n\n"
    " Mission : Générer un **playbook YAML pur** (sans markdown, sans commentaires) qui réalise un **audit Windows via auditpol**.\n"
    "Le playbook doit s’exécuter **uniquement sur Windows** et **skipper** proprement tout hôte non-Windows.\n\n"

    " Contraintes de sortie (OBLIGATOIRES) :\n"
    "- **YAML strict uniquement**, aucune explication, aucun balisage Markdown.\n"
    "- Un seul play :\n"
    "  - `- hosts: all`\n"
    "  - `gather_facts: true`\n"
    "  - **pas de `become`** (Windows n’utilise pas sudo)\n"
    "  - `tasks:` avec des `name:` **clairs et uniques**.\n"
    "- Utiliser les **FQCN** Windows : `ansible.windows.win_command`, `ansible.windows.win_shell`, "
    "`ansible.windows.win_file`, `ansible.windows.win_copy`, et `ansible.builtin.debug`.\n"
    "- **Une seule action/module par tâche** (si deux actions, créer deux tâches).\n"
    "- Toutes les tâches Windows doivent être protégées par `when: ansible_os_family == 'Windows' or ansible_system == 'Win32NT'`.\n"
    "- Aucune tâche Linux ne doit apparaître.\n\n"

    " Comportement attendu :\n"
    "- Créer/assurer le répertoire `C:\\\\Windows\\\\Temp` avec `ansible.windows.win_file` (state: directory).\n"
    "- Lister la politique d’audit : exécuter `auditpol /get /category:*` avec `ansible.windows.win_command`, "
    "`register: auditpol_get`, `changed_when: false`.\n"
    "- Sauvegarder la sortie dans `C:\\\\Windows\\\\Temp\\\\auditpol.txt` via `ansible.windows.win_copy` (`content:` depuis `auditpol_get.stdout`, `force: true`).\n"
    "- (Optionnel et idempotent) Activer quelques catégories clés si désactivées, par exemple : Logon/Logoff, Account Logon, Account Management.\n"
    "  • Lire l’état actuel (déjà obtenu) et **n’exécuter `auditpol /set ...` que si nécessaire** (utiliser un `when:` qui teste la présence de `No Auditing` dans les lignes correspondantes).\n"
    "  • Les commandes `set` peuvent utiliser `ansible.windows.win_command` avec `register:` et `changed_when: true` si une modification est appliquée.\n"
    "- Afficher un **résumé** concis via `ansible.builtin.debug` (par ex. lignes filtrées pour Logon/Logoff, Account Logon, Account Management, extraites de `auditpol_get.stdout`).\n\n"

    " Modèle minimal attendu (à adapter, sans commentaires) :\n"
    "- hosts: all\n"
    "  gather_facts: true\n"
    "  tasks:\n"
    "    - name: Windows | Ensure temp folder exists\n"
    "      ansible.windows.win_file:\n"
    "        path: C:\\\\Windows\\\\Temp\n"
    "        state: directory\n"
    "      when: ansible_os_family == 'Windows' or ansible_system == 'Win32NT'\n"
    "\n"
    "    - name: Windows | Get audit policy\n"
    "      ansible.windows.win_command: auditpol /get /category:*\n"
    "      register: auditpol_get\n"
    "      changed_when: false\n"
    "      when: ansible_os_family == 'Windows' or ansible_system == 'Win32NT'\n"
    "\n"
    "    - name: Windows | Save audit policy to file\n"
    "      ansible.windows.win_copy:\n"
    "        dest: C:\\\\Windows\\\\Temp\\\\auditpol.txt\n"
    "        content: \"{{ auditpol_get.stdout | default('') }}\"\n"
    "        force: true\n"
    "      when: ansible_os_family == 'Windows' or ansible_system == 'Win32NT'\n"
    "\n"
    "    - name: Windows | Enable Logon auditing if disabled\n"
    "      ansible.windows.win_command: auditpol /set /subcategory:\"Logon\" /success:enable /failure:enable\n"
    "      register: auditpol_set_logon\n"
    "      changed_when: true\n"
    "      when: (ansible_os_family == 'Windows' or ansible_system == 'Win32NT') and "
    "'Logon' in (auditpol_get.stdout | default('')) and ('No Auditing' in (auditpol_get.stdout | default('')))\n"
    "\n"
    "    - name: Windows | Summary\n"
    "      ansible.builtin.debug:\n"
    "        msg:\n"
    "          - \"Logon/Logoff: {{ (auditpol_get.stdout | regex_search('(?mi)^\\s*Logon/Logoff.*$', '\\\\0')) | default('n/a') }}\"\n"
    "          - \"Account Logon: {{ (auditpol_get.stdout | regex_search('(?mi)^\\s*Account Logon.*$', '\\\\0')) | default('n/a') }}\"\n"
    "          - \"Account Management: {{ (auditpol_get.stdout | regex_search('(?mi)^\\s*Account Management.*$', '\\\\0')) | default('n/a') }}\"\n"
    "      when: ansible_os_family == 'Windows' or ansible_system == 'Win32NT'\n\n"

    " Sortie attendue : **YAML pur uniquement**, sans texte ni ```.\n"
    "Génère maintenant le playbook d’audit **Windows auditpol** conforme.\n"
)
    elif audit_tool == "windows-defender":
        prompt = (
    "Tu es un assistant DevOps **ultra-expert** en Ansible.\n"
    f"{inventory_hint}\n\n"
    " Mission : Générer un **playbook YAML pur** (sans markdown, sans commentaires) pour **auditer Windows Defender**.\n"
    "Le playbook doit s’exécuter **uniquement sur Windows** et **skipper** proprement tout hôte non-Windows.\n\n"

    " Contraintes de sortie (OBLIGATOIRES) :\n"
    "- **YAML strict uniquement**, aucune explication, aucun balisage Markdown.\n"
    "- Un seul play :\n"
    "  - `- hosts: all`\n"
    "  - `gather_facts: true`\n"
    "  - **pas de `become`** (Windows n’utilise pas sudo)\n"
    "  - `tasks:` avec des `name:` **clairs et uniques**.\n"
    "- Utiliser les **FQCN** Windows : `ansible.windows.win_powershell`, `ansible.windows.win_command`, "
    "`ansible.windows.win_file`, `ansible.windows.win_copy`, et `ansible.builtin.debug`.\n"
    "- **Une seule action/module par tâche** (si deux actions, créer deux tâches).\n"
    "- Toutes les tâches doivent être protégées par `when: ansible_os_family == 'Windows' or ansible_system == 'Win32NT'`.\n"
    "- Aucune tâche Linux ne doit apparaître.\n\n"

    " Comportement attendu :\n"
    "- S’assurer que `C:\\\\Windows\\\\Temp` existe via `ansible.windows.win_file` (`state: directory`).\n"
    "- Récupérer l’état Defender avec PowerShell **en JSON** : `(Get-MpComputerStatus) | ConvertTo-Json -Depth 4` "
    "via `ansible.windows.win_powershell`, `register: mp_status_json`, `changed_when: false`.\n"
    "- Mettre à jour les signatures : `Update-MpSignature` via `ansible.windows.win_powershell`, `register: mp_update`, "
    "`failed_when: false` (tolérer absence/offload), `changed_when: true`.\n"
    "- Lancer un **QuickScan** : `Start-MpScan -ScanType QuickScan` via `ansible.windows.win_powershell`, "
    "`register: mp_scan`, `failed_when: false`, `changed_when: true`.\n"
    "- Construire un **résumé** (par ex. RealTimeProtectionEnabled, AntivirusSignatureVersion, "
    "AMServiceEnabled, NISEnabled) en parsant `mp_status_json.stdout` avec `from_json`.\n"
    "- Sauvegarder le rapport texte dans `C:\\\\Windows\\\\Temp\\\\defender_audit.txt` via `ansible.windows.win_copy` (`content:`), `force: true`.\n"
    "- Afficher un `debug` concis avec les champs clés (protection temps réel, version des signatures, résultat du scan si dispo).\n"
    "- Gérer proprement les environnements où Defender n’est pas présent (ex. serveurs protégés par un autre AV) : "
    "`failed_when: false`, messages clairs, et le play continue.\n\n"

    " Modèle minimal attendu (à adapter, sans commentaires) :\n"
    "- hosts: all\n"
    "  gather_facts: true\n"
    "  tasks:\n"
    "    - name: Windows | Ensure temp folder exists\n"
    "      ansible.windows.win_file:\n"
    "        path: C:\\\\Windows\\\\Temp\n"
    "        state: directory\n"
    "      when: ansible_os_family == 'Windows' or ansible_system == 'Win32NT'\n"
    "\n"
    "    - name: Windows | Get Defender status (JSON)\n"
    "      ansible.windows.win_powershell:\n"
    "        script: |\n"
    "          (Get-MpComputerStatus) | ConvertTo-Json -Depth 4\n"
    "      register: mp_status_json\n"
    "      changed_when: false\n"
    "      failed_when: false\n"
    "      when: ansible_os_family == 'Windows' or ansible_system == 'Win32NT'\n"
    "\n"
    "    - name: Windows | Update Defender signatures\n"
    "      ansible.windows.win_powershell:\n"
    "        script: |\n"
    "          Update-MpSignature\n"
    "      register: mp_update\n"
    "      failed_when: false\n"
    "      when: ansible_os_family == 'Windows' or ansible_system == 'Win32NT'\n"
    "\n"
    "    - name: Windows | Run QuickScan\n"
    "      ansible.windows.win_powershell:\n"
    "        script: |\n"
    "          Start-MpScan -ScanType QuickScan\n"
    "      register: mp_scan\n"
    "      failed_when: false\n"
    "      when: ansible_os_family == 'Windows' or ansible_system == 'Win32NT'\n"
    "\n"
    "    - name: Windows | Build Defender summary\n"
    "      ansible.builtin.set_fact:\n"
    "        mp_summary: \"{{ (mp_status_json.stdout | default('{}')) | from_json | default({}) }}\"\n"
    "      when: ansible_os_family == 'Windows' or ansible_system == 'Win32NT'\n"
    "\n"
    "    - name: Windows | Save Defender audit to file\n"
    "      ansible.windows.win_copy:\n"
    "        dest: C:\\\\Windows\\\\Temp\\\\defender_audit.txt\n"
    "        content: |\n"
    "          RealTimeProtectionEnabled={{ mp_summary.RealTimeProtectionEnabled | default('n/a') }}\n"
    "          AntivirusSignatureVersion={{ mp_summary.AntivirusSignatureVersion | default('n/a') }}\n"
    "          AMServiceEnabled={{ mp_summary.AMServiceEnabled | default('n/a') }}\n"
    "          NISEnabled={{ mp_summary.NISEnabled | default('n/a') }}\n"
    "      when: ansible_os_family == 'Windows' or ansible_system == 'Win32NT'\n"
    "\n"
    "    - name: Windows | Defender audit summary\n"
    "      ansible.builtin.debug:\n"
    "        msg:\n"
    "          - \"RealTimeProtectionEnabled={{ mp_summary.RealTimeProtectionEnabled | default('n/a') }}\"\n"
    "          - \"AntivirusSignatureVersion={{ mp_summary.AntivirusSignatureVersion | default('n/a') }}\"\n"
    "          - \"AMServiceEnabled={{ mp_summary.AMServiceEnabled | default('n/a') }}\"\n"
    "          - \"NISEnabled={{ mp_summary.NISEnabled | default('n/a') }}\"\n"
    "      when: ansible_os_family == 'Windows' or ansible_system == 'Win32NT'\n\n"

    " Sortie attendue : **YAML pur uniquement**, sans texte ni ```.\n"
    "Génère maintenant le playbook d’audit **Windows Defender** conforme.\n"
)
    elif audit_tool == "windows-eventlog":
        prompt = (
    "Tu es un assistant DevOps **ultra-expert** en Ansible.\n"
    f"{inventory_hint}\n\n"
    " Mission : Générer un **playbook YAML pur** (sans markdown, sans commentaires) pour **collecter les 200 derniers événements Windows**\n"
    "des journaux Security, System et Application et produire un petit résumé par niveaux (Error/Warning/Information).\n"
    "Le playbook doit s’exécuter **uniquement sur Windows** et **skipper** proprement tout hôte non-Windows.\n\n"

    " Contraintes de sortie (OBLIGATOIRES) :\n"
    "- **YAML strict uniquement**, aucune explication, aucun balisage Markdown.\n"
    "- Un seul play :\n"
    "  - `- hosts: all`\n"
    "  - `gather_facts: true`\n"
    "  - **pas de `become`** (Windows n’utilise pas sudo)\n"
    "  - `tasks:` avec des `name:` **clairs et uniques**.\n"
    "- Utiliser les **FQCN** Windows : `ansible.windows.win_powershell`, `ansible.windows.win_file`, `ansible.windows.win_command` (si vraiment nécessaire),\n"
    "  et `ansible.builtin.debug` / `ansible.builtin.set_fact`.\n"
    "- **Une seule action/module par tâche** (si deux actions, créer deux tâches).\n"
    "- Toutes les tâches doivent être protégées par `when: ansible_os_family == 'Windows' or ansible_system == 'Win32NT'`.\n"
    "- Aucune tâche Linux ne doit apparaître.\n\n"

    " Comportement attendu :\n"
    "- S’assurer que `C:\\\\Windows\\\\Temp` existe via `ansible.windows.win_file` (`state: directory`).\n"
    "- Exporter les **200 derniers événements** pour chaque journal (Security, System, Application) en **CSV UTF-8** via PowerShell :\n"
    "  `Get-WinEvent -LogName <Log> -MaxEvents 200 | Select TimeCreated,Id,LevelDisplayName,ProviderName,Message | Export-Csv -NoTypeInformation -Encoding UTF8 -Force -Path <dest>`.\n"
    "- Calculer des **compteurs par niveau** (Error/Warning/Information, etc.) pour chaque journal avec PowerShell, renvoyer en **JSON**, puis `from_json`.\n"
    "- Sauvegarder les CSV dans :\n"
    "  `C:\\\\Windows\\\\Temp\\\\eventlog_security.csv`, `C:\\\\Windows\\\\Temp\\\\eventlog_system.csv`, `C:\\\\Windows\\\\Temp\\\\eventlog_application.csv`.\n"
    "- Afficher un `debug` concis avec les compteurs clés par journal (au minimum Error et Warning).\n"
    "- Tolérer l’absence de certaines entrées (serveurs peu bavards) : `failed_when: false` là où pertinent, et `changed_when: false` pour les lectures.\n\n"

    " Modèle minimal attendu (à adapter, sans commentaires) :\n"
    "- hosts: all\n"
    "  gather_facts: true\n"
    "  tasks:\n"
    "    - name: Windows | Ensure temp folder exists\n"
    "      ansible.windows.win_file:\n"
    "        path: C:\\\\Windows\\\\Temp\n"
    "        state: directory\n"
    "      when: ansible_os_family == 'Windows' or ansible_system == 'Win32NT'\n"
    "\n"
    "    - name: Windows | Export last 200 Security events to CSV\n"
    "      ansible.windows.win_powershell:\n"
    "        script: |\n"
    "          Get-WinEvent -LogName Security -MaxEvents 200 |\n"
    "            Select TimeCreated, Id, LevelDisplayName, ProviderName, Message |\n"
    "            Export-Csv -NoTypeInformation -Encoding UTF8 -Force -Path 'C:\\\\Windows\\\\Temp\\\\eventlog_security.csv'\n"
    "      changed_when: false\n"
    "      failed_when: false\n"
    "      when: ansible_os_family == 'Windows' or ansible_system == 'Win32NT'\n"
    "\n"
    "    - name: Windows | Export last 200 System events to CSV\n"
    "      ansible.windows.win_powershell:\n"
    "        script: |\n"
    "          Get-WinEvent -LogName System -MaxEvents 200 |\n"
    "            Select TimeCreated, Id, LevelDisplayName, ProviderName, Message |\n"
    "            Export-Csv -NoTypeInformation -Encoding UTF8 -Force -Path 'C:\\\\Windows\\\\Temp\\\\eventlog_system.csv'\n"
    "      changed_when: false\n"
    "      failed_when: false\n"
    "      when: ansible_os_family == 'Windows' or ansible_system == 'Win32NT'\n"
    "\n"
    "    - name: Windows | Export last 200 Application events to CSV\n"
    "      ansible.windows.win_powershell:\n"
    "        script: |\n"
    "          Get-WinEvent -LogName Application -MaxEvents 200 |\n"
    "            Select TimeCreated, Id, LevelDisplayName, ProviderName, Message |\n"
    "            Export-Csv -NoTypeInformation -Encoding UTF8 -Force -Path 'C:\\\\Windows\\\\Temp\\\\eventlog_application.csv'\n"
    "      changed_when: false\n"
    "      failed_when: false\n"
    "      when: ansible_os_family == 'Windows' or ansible_system == 'Win32NT'\n"
    "\n"
    "    - name: Windows | Build per-log level counters (JSON)\n"
    "      ansible.windows.win_powershell:\n"
    "        script: |\n"
    "          $logs = @('Security','System','Application')\n"
    "          $result = @{}\n"
    "          foreach ($log in $logs) {\n"
    "            $counts = (Get-WinEvent -LogName $log -MaxEvents 200 |\n"
    "              Group-Object LevelDisplayName | ForEach-Object { @{ Name=$_.Name; Count=$_.Count } })\n"
    "            $result[$log] = $counts\n"
    "          }\n"
    "          ($result | ConvertTo-Json -Depth 6)\n"
    "      register: winlog_counts_json\n"
    "      changed_when: false\n"
    "      failed_when: false\n"
    "      when: ansible_os_family == 'Windows' or ansible_system == 'Win32NT'\n"
    "\n"
    "    - name: Windows | Parse counters JSON\n"
    "      ansible.builtin.set_fact:\n"
    "        winlog_counts: \"{{ (winlog_counts_json.stdout | default('{}')) | from_json | default({}) }}\"\n"
    "      when: ansible_os_family == 'Windows' or ansible_system == 'Win32NT'\n"
    "\n"
    "    - name: Windows | Event logs summary\n"
    "      ansible.builtin.debug:\n"
    "        msg:\n"
    "          - \"Security Error={{ (winlog_counts.Security | selectattr('Name','equalto','Error') | list | first).Count | default(0) }}\"\n"
    "          - \"Security Warning={{ (winlog_counts.Security | selectattr('Name','equalto','Warning') | list | first).Count | default(0) }}\"\n"
    "          - \"System Error={{ (winlog_counts.System | selectattr('Name','equalto','Error') | list | first).Count | default(0) }}\"\n"
    "          - \"System Warning={{ (winlog_counts.System | selectattr('Name','equalto','Warning') | list | first).Count | default(0) }}\"\n"
    "          - \"Application Error={{ (winlog_counts.Application | selectattr('Name','equalto','Error') | list | first).Count | default(0) }}\"\n"
    "          - \"Application Warning={{ (winlog_counts.Application | selectattr('Name','equalto','Warning') | list | first).Count | default(0) }}\"\n"
    "      when: ansible_os_family == 'Windows' or ansible_system == 'Win32NT'\n\n"

    " Sortie attendue : **YAML pur uniquement**, sans texte ni ```.\n"
    "Génère maintenant le playbook de **collecte d’événements Windows** conforme.\n"
) 
    elif audit_tool == "osquery":
        prompt = (
    "Tu es un assistant DevOps **ultra-expert** en Ansible.\n"
    f"{inventory_hint}\n\n"
    " Mission : Générer un **playbook YAML pur** (sans markdown, sans commentaires) pour **auditer avec osquery** sous Linux et Windows.\n"
    "Le playbook doit être **multi-OS**, idempotent, et séparé strictement par OS via `when:`.\n\n"

    " Règles par OS :\n"
    "- Windows (ansible_os_family == 'Windows' ou ansible_system == 'Win32NT') :\n"
    "  • Utiliser **exclusivement** des modules `ansible.windows.*` (ex: `ansible.windows.win_chocolatey`, `ansible.windows.win_package`, `ansible.windows.win_powershell`, `ansible.windows.win_file`).\n"
    "  • **Jamais** de `become`.\n"
    "  • Installer osquery via Chocolatey (`win_chocolatey`) si possible, sinon via `win_package` avec une URL MSI propre.\n"
    "  • Exécuter des requêtes osquery (`osqueryi`) pour users, listening_ports, processes, scheduled_tasks (équivalent crontab) et écrire un **JSON** unique dans `C:\\\\Windows\\\\Temp\\\\osquery_audit.json`.\n"
    "- Linux (Debian/Ubuntu, RedHat/CentOS/Rocky, Suse) :\n"
    "  • `become: true` **uniquement** sur les tâches Linux (pas au niveau du play).\n"
    "  • Installer osquery via le gestionnaire natif : `apt` (Debian), `dnf` (RedHat/AL2023), `yum` (AL2/anciennes RedHat) ou `zypper` (Suse). **Une seule** méthode par tâche.\n"
    "  • Si osquery n’est pas dans les dépôts, utiliser un **fallback** binaire officiel propre (téléchargement + placement sous `/usr/local/bin`), dans **des tâches distinctes**.\n"
    "  • Exécuter des requêtes `osqueryi --json` (users, listening_ports, processes, crontab) et écrire un **JSON** unique dans `/tmp/osquery_audit.json`.\n\n"

    " Contraintes générales :\n"
    "- **YAML strict uniquement** : un seul play `- hosts: all`, `gather_facts: true`, pas de `become` global.\n"
    "- **Une action/module par tâche**. Si deux actions sont nécessaires, créer deux tâches avec des `name:` uniques.\n"
    "- Toutes les exécutions shell/powershell doivent avoir **timeouts** et être non-bloquantes (`changed_when: false`, `failed_when: false` pour la collecte).\n"
    "- Toujours créer les répertoires de sortie (`/tmp` est présent sur Linux, mais vérifier/assurer `C:\\\\Windows\\\\Temp` côté Windows).\n"
    "- Séparer **strictement** Windows et Linux avec des `when:` explicites. **Aucune tâche mixte**.\n"
    "- Après exécution, produire un **résumé** (`ansible.builtin.debug`) : compteur d’utilisateurs locaux et nombre de ports à l’écoute.\n\n"

    " Modèle minimal attendu (à adapter, sans commentaires) :\n"
    "- hosts: all\n"
    "  gather_facts: true\n"
    "  tasks:\n"
    "    - name: Windows | Ensure temp folder exists\n"
    "      ansible.windows.win_file:\n"
    "        path: C:\\\\Windows\\\\Temp\n"
    "        state: directory\n"
    "      when: ansible_os_family == 'Windows' or ansible_system == 'Win32NT'\n"
    "\n"
    "    - name: Windows | Install osquery via Chocolatey\n"
    "      ansible.windows.win_chocolatey:\n"
    "        name: osquery\n"
    "        state: present\n"
    "      register: win_osq_choco\n"
    "      failed_when: false\n"
    "      when: ansible_os_family == 'Windows' or ansible_system == 'Win32NT'\n"
    "\n"
    "    - name: Windows | Ensure osquery via MSI if Chocolatey failed\n"
    "      ansible.windows.win_package:\n"
    "        path: https://download.osquery.io/windows/osquery.msi\n"
    "        state: present\n"
    "      when: (ansible_os_family == 'Windows' or ansible_system == 'Win32NT') and (win_osq_choco is failed)\n"
    "\n"
    "    - name: Windows | Run osquery and write JSON\n"
    "      ansible.windows.win_powershell:\n"
    "        script: |\n"
    "          $out = @{}\n"
    "          $out.users = (osqueryi --json \"SELECT username, uid, gid, directory, shell FROM users\") | ConvertFrom-Json\n"
    "          $out.listening = (osqueryi --json \"SELECT pid, address, port, protocol FROM listening_ports\") | ConvertFrom-Json\n"
    "          $out.processes = (osqueryi --json \"SELECT pid, name, path, cpu_time FROM processes LIMIT 200\") | ConvertFrom-Json\n"
    "          $out.scheduled = (osqueryi --json \"SELECT * FROM scheduled_tasks LIMIT 200\") | ConvertFrom-Json\n"
    "          ($out | ConvertTo-Json -Depth 6) | Out-File -Encoding utf8 'C:\\\\Windows\\\\Temp\\\\osquery_audit.json'\n"
    "      changed_when: false\n"
    "      failed_when: false\n"
    "      when: ansible_os_family == 'Windows' or ansible_system == 'Win32NT'\n"
    "\n"
    "    - name: Linux | Ensure osquery present (Debian)\n"
    "      ansible.builtin.apt:\n"
    "        name: osquery\n"
    "        state: present\n"
    "        update_cache: true\n"
    "      become: true\n"
    "      when: ansible_os_family == 'Debian'\n"
    "\n"
    "    - name: Linux | Ensure osquery present (RedHat dnf)\n"
    "      ansible.builtin.dnf:\n"
    "        name: osquery\n"
    "        state: present\n"
    "      become: true\n"
    "      when: ansible_os_family == 'RedHat' and (ansible_pkg_mgr == 'dnf')\n"
    "\n"
    "    - name: Linux | Ensure osquery present (RedHat yum)\n"
    "      ansible.builtin.yum:\n"
    "        name: osquery\n"
    "        state: present\n"
    "      become: true\n"
    "      when: ansible_os_family == 'RedHat' and (ansible_pkg_mgr == 'yum')\n"
    "\n"
    "    - name: Linux | Ensure osquery present (Suse)\n"
    "      community.general.zypper:\n"
    "        name: osquery\n"
    "        state: present\n"
    "      become: true\n"
    "      when: ansible_os_family == 'Suse'\n"
    "\n"
    "    - name: Linux | Run osquery and write JSON\n"
    "      ansible.builtin.shell: >-\n"
    "        timeout 30s bash -lc\n"
    "        \"jqbin=$(command -v jq || echo jq);\n"
    "        users=$(osqueryi --json 'SELECT username, uid, gid, directory, shell FROM users');\n"
    "        listening=$(osqueryi --json 'SELECT pid, address, port, protocol FROM listening_ports');\n"
    "        processes=$(osqueryi --json 'SELECT pid, name, path, cpu_time FROM processes LIMIT 200');\n"
    "        crontab=$(osqueryi --json 'SELECT * FROM crontab');\n"
    "        python3 - <<'PY'\n"
    "        import json,sys\n"
    "        out={\n"
    "          'users': json.loads(sys.argv[1] or '[]'),\n"
    "          'listening': json.loads(sys.argv[2] or '[]'),\n"
    "          'processes': json.loads(sys.argv[3] or '[]'),\n"
    "          'crontab': json.loads(sys.argv[4] or '[]')}\n"
    "        open('/tmp/osquery_audit.json','w').write(json.dumps(out))\n"
    "        PY\n"
    "        \"$users\" \"$listening\" \"$processes\" \"$crontab\"\"\n"
    "      args:\n"
    "        executable: /bin/bash\n"
    "      changed_when: false\n"
    "      failed_when: false\n"
    "      when: ansible_system == 'Linux'\n"
    "\n"
    "    - name: Summaries | Build facts from JSON (Windows)\n"
    "      ansible.windows.win_powershell:\n"
    "        script: |\n"
    "          $j = Get-Content 'C:\\\\Windows\\\\Temp\\\\osquery_audit.json' -Raw | ConvertFrom-Json\n"
    "          @{ users_count = ($j.users | Measure-Object).Count; listening_count = ($j.listening | Measure-Object).Count } | ConvertTo-Json\n"
    "      register: win_summary_json\n"
    "      changed_when: false\n"
    "      failed_when: false\n"
    "      when: ansible_os_family == 'Windows' or ansible_system == 'Win32NT'\n"
    "\n"
    "    - name: Summaries | Build facts from JSON (Linux)\n"
    "      ansible.builtin.shell: >-\n"
    "        timeout 10s python3 - <<'PY'\n"
    "        import json\n"
    "        j=json.load(open('/tmp/osquery_audit.json'))\n"
    "        print(json.dumps({'users_count': len(j.get('users',[])), 'listening_count': len(j.get('listening',[]))}))\n"
    "        PY\n"
    "      register: lin_summary_json\n"
    "      changed_when: false\n"
    "      failed_when: false\n"
    "      when: ansible_system == 'Linux'\n"
    "\n"
    "    - name: Summaries | Set facts (Windows)\n"
    "      ansible.builtin.set_fact:\n"
    "        osq_summary: \"{{ (win_summary_json.stdout | default('{}')) | from_json | default({}) }}\"\n"
    "      when: ansible_os_family == 'Windows' or ansible_system == 'Win32NT'\n"
    "\n"
    "    - name: Summaries | Set facts (Linux)\n"
    "      ansible.builtin.set_fact:\n"
    "        osq_summary: \"{{ (lin_summary_json.stdout | default('{}')) | from_json | default({}) }}\"\n"
    "      when: ansible_system == 'Linux'\n"
    "\n"
    "    - name: Summaries | Debug\n"
    "      ansible.builtin.debug:\n"
    "        msg:\n"
    "          - \"users_count={{ osq_summary.users_count | default(0) }}\"\n"
    "          - \"listening_count={{ osq_summary.listening_count | default(0) }}\"\n"
    "\n"
    " Sortie attendue : **YAML pur uniquement**, sans texte ni ```.\n"
    "Génère maintenant le playbook **osquery multi-OS** conforme.\n"
)

    # 5) Génération GPT
    gpt_response = await generate_instructions_from_gpt(prompt)
    ansible_code = gpt_response.strip()
    if ansible_code.startswith("```"):
        ansible_code = ansible_code.replace("```yaml", "").replace("```yml", "").replace("```", "").strip()
    if not ansible_code or "hosts:" not in ansible_code:
        raise HTTPException(status_code=500, detail="Réponse Ansible invalide:\n" + gpt_response)

    # 6) Validation/patch
    patched = validate_ansible_playbook(ansible_code)
    final_code = patched or ansible_code

    # 7) Sauvegarde via utilitaire centralisé
    os.makedirs(BASE_AUDIT_DIR, exist_ok=True)
    filename = f"audit_{audit_tool}_{uuid.uuid4().hex}.yml"
    audit_rec = create_and_store_audit_file(
        user_id=user.id,
        session_id=intent.session.id,
        filename=filename,
        content=final_code
    )

    return {
        "status": "success",
        "engine": "audit",
        "file_id": audit_rec.id,
        "filename": filename,
        "tools": [audit_tool],
        "message": f" Fichier d’audit généré pour l’outil **{audit_tool}**. Exécute-le via `/executions/create`."
    }
