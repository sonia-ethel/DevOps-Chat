"""
Installer Runner - Runner SSM générique.

Phase B: Exécution
Exécute un InstallationPlan sur des instances via SSM.
Supporte 35+ applications avec détection OS, port fallback, et checks.
"""
import logging
import json
from typing import List, Dict, Optional
from datetime import datetime, timezone
from .schemas import InstallationPlan, InstallationResult, InstanceResult, InstallationSummary, OSInfo, Fallback, CheckResult, Artifact

logger = logging.getLogger(__name__)


def extract_dac_result_json(stdout: str) -> dict | None:
    """
    Extrait le JSON final du stdout en cherchant la ligne marquée DAC_RESULT_JSON:.
    
    Convention: La dernière ligne commençant par 'DAC_RESULT_JSON:' contient le JSON valide.
    
    Args:
        stdout: Sortie complète du script bash
        
    Returns:
        dict: Dictionnaire parsé du JSON, ou None si non trouvé/invalide
    """
    if not stdout:
        return None
    
    lines = stdout.strip().split('\n')
    
    # Chercher la dernière ligne qui commence par DAC_RESULT_JSON:
    for line in reversed(lines):
        line = line.strip()
        if line.startswith('DAC_RESULT_JSON:'):
            # Extraire la partie après le marqueur
            json_str = line[len('DAC_RESULT_JSON:'):].strip()
            try:
                return json.loads(json_str)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse DAC_RESULT_JSON: {e}")
                return None
    
    # Si DAC_RESULT_JSON: non trouvé, chercher un JSON brut (fallback legacy)
    for line in reversed(lines):
        line = line.strip()
        if line.startswith('{'):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    
    return None


class InstallerRunner:
    """
    Runner générique pour exécuter des installations via SSM.
    
    Génère un script bash universel qui:
    1. Détecte l'OS
    2. Applique la stratégie appropriée
    3. Gère les ports (détection conflit + fallback)
    4. Installe et configure
    5. Valide avec checks
    6. Applique auto-fixes si nécessaire
    7. Retourne un JSON standard
    """
    
    def __init__(self):
        self.logger = logger
    
    def generate_runner_script(self, plan: InstallationPlan) -> str:
        """
        Génère le script bash universel pour l'installation.
        
        Ce script est envoyé tel quel via SSM et:
        - Détecte l'OS automatiquement
        - Choisit la bonne stratégie
        - Gère les ports intelligemment
        - Exécute l'installation
        - Valide et retourne JSON
        """
        app_name = plan.app.name
        requested_port = plan.app.config.requested_port
        port_candidates = plan.app.config.port_candidates
        
        # Template du script bash
        script = f"""#!/bin/bash
set -e

# ============================================================================
# DAC Installer Runner - Script universel
# App: {app_name}
# Generated: {datetime.now(timezone.utc).isoformat()}
# ============================================================================

# Variables globales
APP_NAME="{app_name}"
REQUESTED_PORT={requested_port or 'null'}
PORT_CANDIDATES=({' '.join(map(str, port_candidates))})
CHOSEN_PORT=$REQUESTED_PORT
INSTALL_STATUS="pending"
INSTALL_VERSION="unknown"
SERVICE_NAME=""
ACTIONS_TAKEN=()

# Associative array pour les checks (bash 4+)
declare -A CHECKS_PASSED

# Fonction: Ajouter une action
add_action() {{
    ACTIONS_TAKEN+=("$1")
}}

# Fonction: Log check
log_check() {{
    local check_name="$1"
    local passed="$2"
    CHECKS_PASSED["$check_name"]="$passed"
}}

# ============================================================================
# STEP 1: Détection OS
# ============================================================================
add_action "detect_os"

if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS_ID=${{ID}}
    OS_VERSION=${{VERSION_ID:-unknown}}
    OS_PRETTY_NAME=${{PRETTY_NAME:-unknown}}
else
    echo "ERROR: Cannot detect OS"
    exit 1
fi

echo " OS détecté: $OS_ID $OS_VERSION ($OS_PRETTY_NAME)"

# ============================================================================
# STEP 2: Sélection stratégie OS
# ============================================================================
add_action "select_strategy"

PACKAGE=""
INSTALL_STRATEGY=""

"""
        
        # Générer les branches pour chaque OS
        first_os = True
        for os_id, strategy in plan.os_matrix.items():
            if_clause = "if" if first_os else "elif"
            first_os = False
            
            script += f"""
{if_clause} [ "$OS_ID" = "{os_id}" ]; then
    echo " Stratégie: {strategy.install_strategy}"
    INSTALL_STRATEGY="{strategy.install_strategy}"
    PACKAGE="{strategy.package}"
    SERVICE_NAME="{strategy.package}"  # Default: package name = service name
    
    # Pre-steps
"""
            for step in strategy.pre_steps:
                script += f'    {step}\n'
            
            script += f"""
    # Installation
    add_action "install_package"
    case "$INSTALL_STRATEGY" in
        apt)
            export DEBIAN_FRONTEND=noninteractive
            apt-get install -y $PACKAGE 2>&1 || echo "Install failed but continuing..."
            ;;
        yum)
            yum install -y $PACKAGE 2>&1 || echo "Install failed but continuing..."
            ;;
        amazon-linux-extras+yum)
            # Pre-steps should have enabled extras
            yum install -y $PACKAGE 2>&1 || echo "Install failed but continuing..."
            ;;
        dnf)
            dnf install -y $PACKAGE 2>&1 || echo "Install failed but continuing..."
            ;;
        *)
            echo "ERROR: Unknown install strategy: $INSTALL_STRATEGY"
            exit 1
            ;;
    esac
    
    # Post-steps
"""
            for step in strategy.post_steps:
                script += f'    {step}\n'
            
            if strategy.version_command:
                script += f"""
    # Detect version
    INSTALL_VERSION=$({strategy.version_command} || echo "unknown")
"""
        
        # Fermer le if/elif
        script += """
else
    echo "  OS non supporté: $OS_ID"
    echo "Fallback: tentative d'installation best-effort..."
    
    # Generic fallback (try apt first, then yum)
    if command -v apt-get &>/dev/null; then
        export DEBIAN_FRONTEND=noninteractive
        apt-get update -y && apt-get install -y "$APP_NAME" 2>&1 || true
    elif command -v yum &>/dev/null; then
        yum install -y "$APP_NAME" 2>&1 || true
    elif command -v dnf &>/dev/null; then
        dnf install -y "$APP_NAME" 2>&1 || true
    fi
    PACKAGE="$APP_NAME"
    SERVICE_NAME="$APP_NAME"
fi

"""
        
        # Gestion des ports si nécessaire
        if plan.ports_needed:
            script += f"""

# ============================================================================
# STEP 3: Port Management
# ============================================================================
add_action "port_check"

if [ "$REQUESTED_PORT" != "null" ]; then
    # Vérifier si le port est libre
    if command -v ss &>/dev/null && ss -lntp 2>/dev/null | grep -q ":$REQUESTED_PORT "; then
        echo "  Port $REQUESTED_PORT déjà utilisé, fallback..."
        add_action "port_fallback"
        
        # Chercher un port libre
        for port in ${{PORT_CANDIDATES[@]}}; do
            if ! ss -lntp 2>/dev/null | grep -q ":$port "; then
                CHOSEN_PORT=$port
                echo " Port libre trouvé: $CHOSEN_PORT"
                break
            fi
        done
    else
        echo " Port $REQUESTED_PORT est libre"
    fi
fi

# ============================================================================
# STEP 4: Configuration app-specific
# ============================================================================
add_action "configure"

"""
            
            # Configuration spécifique par type d'app
            if app_name.lower() == "nginx":
                script += """
# NGINX: Config minimale
if [ "$CHOSEN_PORT" != "null" ]; then
    mkdir -p /etc/nginx/conf.d
    cat > /etc/nginx/conf.d/dac-install.conf <<'EOFNGINX'
server {
    listen $CHOSEN_PORT default_server;
    listen [::]:$CHOSEN_PORT default_server;
    root /usr/share/nginx/html;
    index index.html;
    
    location / {
        try_files \\$uri \\$uri/ =404;
    }
}
EOFNGINX
    # Inject port into config
    sed -i "s/\\$CHOSEN_PORT/$CHOSEN_PORT/g" /etc/nginx/conf.d/dac-install.conf
    
    # Désactiver default si conflit
    rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true
    mv /etc/nginx/conf.d/default.conf /etc/nginx/conf.d/default.conf.bak 2>/dev/null || true
    
    SERVICE_NAME="nginx"
fi
"""
            elif app_name.lower() in ["apache", "apache2", "httpd"]:
                script += """
# Apache: Config minimale
if [ "$CHOSEN_PORT" != "null" ]; then
    # Déterminer le nom du service selon l'OS
    if [ "$OS_ID" = "ubuntu" ] || [ "$OS_ID" = "debian" ]; then
        sed -i "s/Listen 80/Listen $CHOSEN_PORT/" /etc/apache2/ports.conf 2>/dev/null || true
        SERVICE_NAME="apache2"
    else
        sed -i "s/Listen 80/Listen $CHOSEN_PORT/" /etc/httpd/conf/httpd.conf 2>/dev/null || true
        SERVICE_NAME="httpd"
    fi
fi
"""
            elif app_name.lower() in ["redis"]:
                script += """
# Redis: Detect service name
if [ "$OS_ID" = "ubuntu" ] || [ "$OS_ID" = "debian" ]; then
    SERVICE_NAME="redis-server"
else
    SERVICE_NAME="redis"
fi

if [ "$CHOSEN_PORT" != "null" ] && [ "$CHOSEN_PORT" != "6379" ]; then
    # Change port if needed (simplified, may need more logic for production)
    if [ -f /etc/redis/redis.conf ]; then
        sed -i "s/^port 6379/port $CHOSEN_PORT/" /etc/redis/redis.conf
    elif [ -f /etc/redis.conf ]; then
        sed -i "s/^port 6379/port $CHOSEN_PORT/" /etc/redis.conf
    fi
fi
"""
            elif app_name.lower() in ["postgresql", "postgres"]:
                script += """
# PostgreSQL: Detect service name
SERVICE_NAME="postgresql"

# Port config for postgres requires more complex setup, skip for MVP
"""
            elif app_name.lower() in ["mariadb", "mysql"]:
                script += """
# MariaDB: Service name
SERVICE_NAME="mariadb"
"""
            elif app_name.lower() == "docker":
                script += """
# Docker: Service name
SERVICE_NAME="docker"
"""
        
        script += """

# ============================================================================
# STEP 5: Restart/Start service
# ============================================================================
add_action "restart_service"

if [ -n "$SERVICE_NAME" ] && systemctl list-unit-files | grep -q "$SERVICE_NAME.service"; then
    echo " Redémarrage du service: $SERVICE_NAME"
    systemctl restart $SERVICE_NAME 2>&1 || {{
        echo " Service $SERVICE_NAME failed to start"
        echo " Collecting logs..."
        journalctl -u $SERVICE_NAME -n 50 2>&1 || true
        # Don't exit, continue to checks
    }}
else
    echo "  Aucun service systemd détecté pour: $SERVICE_NAME"
fi

# ============================================================================
# STEP 6: Validation Checks
# ============================================================================
add_action "validate"

"""
        
        # Générer les checks
        for check in plan.checks:
            if check.type == "service_active":
                service = check.service or "$SERVICE_NAME"
                # Handle template variables - remplacer le placeholder
                if "{{service_name}}" in service:
                    service = "$SERVICE_NAME"
                
                script += f"""
# Check: service_active ({check.description})
if [ -n "$SERVICE_NAME" ]; then
    if systemctl is-active --quiet {service} 2>/dev/null; then
        log_check "service_active" "true"
        echo "OK Service {service} is active"
    else
        log_check "service_active" "false"
        echo "ERR Service {service} is NOT active"
    fi
else
    log_check "service_active" "skipped"
    echo "⏭  Service check skipped (no systemd service)"
fi
"""
            elif check.type == "port_listening":
                script += """
# Check: port_listening
if [ "$CHOSEN_PORT" != "null" ]; then
    if command -v ss &>/dev/null && ss -lntp 2>/dev/null | grep -q ":$CHOSEN_PORT "; then
        log_check "port_listening" "true"
        echo " Port $CHOSEN_PORT is listening"
    else
        log_check "port_listening" "false"
        echo " Port $CHOSEN_PORT is NOT listening"
    fi
else
    log_check "port_listening" "skipped"
fi
"""
            elif check.type == "http_get":
                script += """
# Check: http_get
if [ "$CHOSEN_PORT" != "null" ] && command -v curl &>/dev/null; then
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:$CHOSEN_PORT/ 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "301" ] || [ "$HTTP_CODE" = "302" ]; then
        log_check "http_ok" "true"
        echo " HTTP GET returns $HTTP_CODE"
    else
        log_check "http_ok" "false"
        echo " HTTP GET returned $HTTP_CODE (expected 200)"
    fi
else
    log_check "http_ok" "skipped"
fi
"""
            elif check.type == "command":
                cmd = check.command or "true"
                script += f"""
# Check: command ({check.description})
if {cmd} &>/dev/null; then
    log_check "command_ok" "true"
    echo " Command check passed: {cmd}"
else
    log_check "command_ok" "false"
    echo " Command check failed: {cmd}"
fi
"""
        
        # Retour JSON final - Robust et univoque
        script += """

# ============================================================================
# STEP 7: Construction du JSON final avec marqueur DAC_RESULT_JSON
# ============================================================================
add_action "generate_report"

# Déterminer le statut global basé sur les checks
DAC_ERROR=""
DAC_SERVICE_ACTIVE="${CHECKS_PASSED[service_active]:-false}"
DAC_PORT_LISTENING="${CHECKS_PASSED[port_listening]:-false}"
DAC_HTTP_OK="${CHECKS_PASSED[http_ok]:-false}"
DAC_INSTALLED_VERSION="$INSTALL_VERSION"
DAC_CHOSEN_PORT="$CHOSEN_PORT"
DAC_SERVICE_NAME="$SERVICE_NAME"

# Déterminer le status
if [ "$DAC_SERVICE_ACTIVE" = "true" ]; then
    DAC_STATUS="success"
else
    DAC_STATUS="failed"
    if [ -z "$SERVICE_NAME" ]; then
        DAC_ERROR="No service name detected"
    elif ! systemctl is-active --quiet $SERVICE_NAME 2>/dev/null; then
        DAC_ERROR="Service not active: $SERVICE_NAME"
    else
        DAC_ERROR="Installation checks failed"
    fi
fi

# Générer le JSON final avec marqueur unique
# Le marqueur DAC_RESULT_JSON: permet une extraction robuste
cat <<'EOJSON'
DAC_RESULT_JSON: {"status": "$DAC_STATUS", "os": {"id": "$OS_ID", "version": "$OS_VERSION", "pretty_name": "$OS_PRETTY_NAME"}, "app": "$APP_NAME", "service_name": "$DAC_SERVICE_NAME", "installed_version": "$DAC_INSTALLED_VERSION", "requested_port": $REQUESTED_PORT, "chosen_port": $DAC_CHOSEN_PORT, "checks": {"service_active": $DAC_SERVICE_ACTIVE, "port_listening": $DAC_PORT_LISTENING, "http_ok": $DAC_HTTP_OK}, "error": "$DAC_ERROR", "actions_taken": [$(IFS=','; echo "${ACTIONS_TAKEN[*]})")]}
EOJSON

echo " Installation completed"
exit 0
"""
        
        return script
    
    def parse_runner_output(
        self,
        stdout: str,
        stderr: str,
        instance_id: str,
        duration: float
    ) -> InstanceResult:
        """
        Parse la sortie du runner pour créer un InstanceResult.
        
        Utilise extract_dac_result_json() pour extraire le JSON avec marqueur DAC_RESULT_JSON:.
        """
        try:
            # Extraire le JSON du marqueur DAC_RESULT_JSON:
            data = extract_dac_result_json(stdout)
            
            if not data:
                # JSON non trouvé ou invalide
                return InstanceResult(
                    instance_id=instance_id,
                    status="failed",
                    stdout=stdout,
                    stderr=stderr,
                    duration_seconds=duration,
                    error="No valid DAC_RESULT_JSON found in stdout"
                )
            
            # Extraire les infos du JSON
            os_info = OSInfo(
                id=data.get("os", {}).get("id", "unknown"),
                version=data.get("os", {}).get("version", "unknown"),
                pretty_name=data.get("os", {}).get("pretty_name", "unknown")
            )
            
            # Récupérer les actions
            actions_raw = data.get("actions_taken", [])
            if isinstance(actions_raw, str):
                actions = [a.strip() for a in actions_raw.split(',') if a.strip()]
            elif isinstance(actions_raw, list):
                actions = [str(a).strip() for a in actions_raw if a]
            else:
                actions = []
            
            # Extraire et normaliser les checks
            checks = data.get("checks", {})
            checks_dict = {}
            for key, value in checks.items():
                if isinstance(value, bool):
                    checks_dict[key] = value
                elif isinstance(value, str):
                    checks_dict[key] = value.lower() == "true"
                else:
                    checks_dict[key] = bool(value)
            
            # Déterminer le status
            # 1. Si error est présent et non vide -> "failed"
            error_msg = data.get("error", "").strip()
            if error_msg:
                status = "failed"
            # 2. Sinon, vérifier si tous les checks ont passé
            elif checks_dict:
                all_passed = all(checks_dict.values())
                status = "success" if all_passed else "failed"
                
                # Log des checks échoués
                if not all_passed:
                    failed_checks = [k for k, v in checks_dict.items() if not v]
                    self.logger.warning(
                        f"[{instance_id}] Checks failed: {', '.join(failed_checks)}"
                    )
            # 3. Sinon, utiliser le status du JSON
            else:
                status = data.get("status", "partial")
            
            # Construire le résultat
            return InstanceResult(
                instance_id=instance_id,
                status=status,
                os=os_info,
                actions_taken=actions,
                checks=checks_dict,
                stdout=stdout,
                stderr=stderr,
                duration_seconds=duration,
                error=error_msg if error_msg else None
            )
            
        except Exception as e:
            self.logger.error(f"[{instance_id}] Failed to parse runner output: {e}", exc_info=True)
            return InstanceResult(
                instance_id=instance_id,
                status="failed",
                stdout=stdout,
                stderr=stderr,
                duration_seconds=duration,
                error=f"Parser error: {str(e)}"
            )

    """
    Runner générique pour exécuter des installations via SSM.
    
    Génère un script bash universel qui:
    1. Détecte l'OS
    2. Applique la stratégie appropriée
    3. Gère les ports (détection conflit + fallback)
    4. Installe et configure
    5. Valide avec checks
    6. Applique auto-fixes si nécessaire
    7. Retourne un JSON standard
    """
    
    def __init__(self):
        self.logger = logger
    
    def generate_runner_script(self, plan: InstallationPlan) -> str:
        """
        Génère le script bash universel pour l'installation.
        
        Ce script est envoyé tel quel via SSM et:
        - Détecte l'OS automatiquement
        - Choisit la bonne stratégie
        - Gère les ports intelligemment
        - Exécute l'installation
        - Valide et retourne JSON
        """
        app_name = plan.app.name
        requested_port = plan.app.config.requested_port
        port_candidates = plan.app.config.port_candidates
        
        # Template du script bash
        script = f"""#!/bin/bash
set -e

# ============================================================================
# DAC Installer Runner - Script universel
# App: {app_name}
# Generated: {datetime.now(timezone.utc).isoformat()}
# ============================================================================

# Variables
APP_NAME="{app_name}"
REQUESTED_PORT={requested_port or 'null'}
PORT_CANDIDATES=({' '.join(map(str, port_candidates))})
CHOSEN_PORT=$REQUESTED_PORT
INSTALL_STATUS="pending"
INSTALL_VERSION="unknown"
ACTIONS_TAKEN=()
CHECKS_PASSED={{}}
STDOUT_LOG=""
STDERR_LOG=""

# Fonction: Ajouter une action
add_action() {{
    ACTIONS_TAKEN+=("$1")
}}

# Fonction: Log check
log_check() {{
    local check_name="$1"
    local passed="$2"
    CHECKS_PASSED["$check_name"]="$passed"
}}

# ============================================================================
# STEP 1: Détection OS
# ============================================================================
add_action "detect_os"

if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS_ID=${{ID}}
    OS_VERSION=${{VERSION_ID:-unknown}}
    OS_PRETTY_NAME=${{PRETTY_NAME:-unknown}}
else
    echo "ERROR: Cannot detect OS"
    exit 1
fi

echo " OS détecté: $OS_ID $OS_VERSION ($OS_PRETTY_NAME)"

# ============================================================================
# STEP 2: Sélection stratégie
# ============================================================================
add_action "select_strategy"

"""
        
        # Générer les branches pour chaque OS
        for os_id, strategy in plan.os_matrix.items():
            script += f"""
if [ "$OS_ID" = "{os_id}" ]; then
    INSTALL_STRATEGY="{strategy.install_strategy}"
    PACKAGE="{strategy.package}"
    
    # Pre-steps
"""
            for step in strategy.pre_steps:
                script += f'    {step}\n'
            
            script += f"""
    # Installation
    add_action "install_package"
    case "$INSTALL_STRATEGY" in
        apt)
            export DEBIAN_FRONTEND=noninteractive
            apt-get install -y $PACKAGE
            ;;
        yum)
            yum install -y $PACKAGE
            ;;
        amazon-linux-extras+yum)
            # Pre-steps handle extras enable
            yum install -y $PACKAGE
            ;;
        dnf)
            dnf install -y $PACKAGE
            ;;
        *)
            echo "ERROR: Unknown install strategy: $INSTALL_STRATEGY"
            exit 1
            ;;
    esac
    
    # Post-steps
"""
            for step in strategy.post_steps:
                script += f'    {step}\n'
            
            if strategy.version_command:
                script += f"""
    # Detect version
    INSTALL_VERSION=$({strategy.version_command} || echo "unknown")
"""
            
            script += "fi\n"
        
        # Gestion des ports si nécessaire
        if plan.ports_needed:
            script += f"""

# ============================================================================
# STEP 3: Port Management
# ============================================================================
add_action "port_check"

if [ "$REQUESTED_PORT" != "null" ]; then
    # Vérifier si le port est libre
    if ss -lntp | grep -q ":$REQUESTED_PORT "; then
        echo "  Port $REQUESTED_PORT déjà utilisé, fallback..."
        add_action "port_fallback"
        
        # Chercher un port libre
        for port in ${{PORT_CANDIDATES[@]}}; do
            if ! ss -lntp | grep -q ":$port "; then
                CHOSEN_PORT=$port
                echo " Port libre trouvé: $CHOSEN_PORT"
                break
            fi
        done
    else
        echo " Port $REQUESTED_PORT est libre"
    fi
fi

# ============================================================================
# STEP 4: Configuration minimale
# ============================================================================
add_action "configure_minimal"

"""
        
        # Configuration spécifique par app
        if app_name == "nginx":
            script += """
# NGINX: Config minimale
if [ "$CHOSEN_PORT" != "null" ]; then
    cat > /etc/nginx/conf.d/dac-install.conf <<EOF
server {
    listen $CHOSEN_PORT default_server;
    listen [::]:$CHOSEN_PORT default_server;
    root /usr/share/nginx/html;
    index index.html;
    
    location / {
        try_files \\$uri \\$uri/ =404;
    }
}
EOF
    
    # Désactiver default si conflit
    if [ -f /etc/nginx/sites-enabled/default ]; then
        rm -f /etc/nginx/sites-enabled/default || true
    fi
    if [ -f /etc/nginx/conf.d/default.conf ]; then
        mv /etc/nginx/conf.d/default.conf /etc/nginx/conf.d/default.conf.bak || true
    fi
fi
"""
        elif app_name in ["apache", "httpd"]:
            script += """
# Apache: Config minimale
if [ "$CHOSEN_PORT" != "null" ]; then
    # Ubuntu/Debian: apache2
    if [ "$OS_ID" = "ubuntu" ] || [ "$OS_ID" = "debian" ]; then
        sed -i "s/Listen 80/Listen $CHOSEN_PORT/" /etc/apache2/ports.conf || true
        APACHE_SERVICE="apache2"
    else
        # RHEL/CentOS: httpd
        sed -i "s/Listen 80/Listen $CHOSEN_PORT/" /etc/httpd/conf/httpd.conf || true
        APACHE_SERVICE="httpd"
    fi
fi
"""
        
        script += """

# ============================================================================
# STEP 5: Restart service
# ============================================================================
add_action "restart_service"

"""
        
        # Restart service (spécifique par app)
        if app_name == "nginx":
            script += """
systemctl restart nginx || {
    echo " NGINX failed to start, collecting logs..."
    journalctl -u nginx -n 50 || true
    exit 1
}
"""
        elif app_name in ["apache", "httpd"]:
            script += """
systemctl restart $APACHE_SERVICE || {
    echo " Apache failed to start, collecting logs..."
    journalctl -u $APACHE_SERVICE -n 50 || true
    exit 1
}
"""
        elif app_name == "docker":
            script += """
systemctl restart docker || {
    echo " Docker failed to start, collecting logs..."
    journalctl -u docker -n 50 || true
    exit 1
}
"""
        
        # Checks
        script += """

# ============================================================================
# STEP 6: Validation Checks
# ============================================================================
add_action "validate"

"""
        
        for check in plan.checks:
            if check.type == "service_active":
                service = check.service
                if "{{" in service:  # Template variable
                    service = "$APACHE_SERVICE" if "apache" in service else check.service
                script += f"""
# Check: service_active
if systemctl is-active --quiet {service}; then
    log_check "service_active" "true"
    echo " Service {service} is active"
else
    log_check "service_active" "false"
    echo " Service {service} is NOT active"
fi
"""
            elif check.type == "port_listening":
                script += """
# Check: port_listening
if [ "$CHOSEN_PORT" != "null" ]; then
    if ss -lntp | grep -q ":$CHOSEN_PORT "; then
        log_check "port_listening" "true"
        echo " Port $CHOSEN_PORT is listening"
    else
        log_check "port_listening" "false"
        echo " Port $CHOSEN_PORT is NOT listening"
    fi
fi
"""
            elif check.type == "http_get":
                script += """
# Check: http_get
if [ "$CHOSEN_PORT" != "null" ]; then
    if curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:$CHOSEN_PORT/ | grep -q "200"; then
        log_check "http_ok" "true"
        echo " HTTP GET returns 200"
    else
        log_check "http_ok" "false"
        echo " HTTP GET did not return 200"
    fi
fi
"""
        
        # Retour JSON final
        script += """

# ============================================================================
# STEP 7: Retour JSON standard
# ============================================================================
add_action "generate_report"

# Construire le JSON de sortie
cat <<EOJSON
{
  "status": "success",
  "os": {
    "id": "$OS_ID",
    "version": "$OS_VERSION",
    "pretty_name": "$OS_PRETTY_NAME"
  },
  "app": "$APP_NAME",
  "requested_port": $REQUESTED_PORT,
  "chosen_port": $CHOSEN_PORT,
  "installed_version": "$INSTALL_VERSION",
  "actions_taken": ["$(IFS=','; echo "${ACTIONS_TAKEN[*]}")"],
  "checks": {
    "service_active": "${CHECKS_PASSED[service_active]:-false}",
    "port_listening": "${CHECKS_PASSED[port_listening]:-false}",
    "http_ok": "${CHECKS_PASSED[http_ok]:-false}"
  }
}
EOJSON

echo " Installation completed successfully"
exit 0
"""
        
        return script
    
    def parse_runner_output(
        self,
        stdout: str,
        stderr: str,
        instance_id: str,
        duration: float
    ) -> InstanceResult:
        """
        Parse la sortie du runner pour créer un InstanceResult.
        
        Le runner génère un JSON en fin de stdout.
        """
        try:
            # Extraire le JSON de la fin du stdout
            lines = stdout.strip().split('\n')
            json_lines = []
            in_json = False
            
            for line in lines:
                if line.strip().startswith('{'):
                    in_json = True
                if in_json:
                    json_lines.append(line)
            
            if json_lines:
                json_str = '\n'.join(json_lines)
                data = json.loads(json_str)
                
                # Construire InstanceResult à partir du JSON
                os_info = OSInfo(
                    id=data.get("os", {}).get("id", "unknown"),
                    version=data.get("os", {}).get("version", "unknown"),
                    pretty_name=data.get("os", {}).get("pretty_name", "unknown")
                )
                
                actions = data.get("actions_taken", [])[0].split(',') if data.get("actions_taken") else []
                
                checks = data.get("checks", {})
                checks_dict = {
                    "service_active": checks.get("service_active") == "true",
                    "port_listening": checks.get("port_listening") == "true",
                    "http_ok": checks.get("http_ok") == "true"
                }
                
                # Déterminer le status basé sur les checks
                # Si au moins un check critique échoue, status = failed
                all_passed = all(checks_dict.values())
                status = "success" if all_passed else "failed"
                
                # Log des checks échoués pour debugging
                if not all_passed:
                    failed_checks = [k for k, v in checks_dict.items() if not v]
                    self.logger.warning(
                        f"[{instance_id}] Installation checks failed: {', '.join(failed_checks)}"
                    )
                
                return InstanceResult(
                    instance_id=instance_id,
                    status=status,
                    os=os_info,
                    actions_taken=actions,
                    checks=checks_dict,
                    stdout=stdout,
                    stderr=stderr,
                    duration_seconds=duration
                )
            else:
                # Pas de JSON trouvé, échec
                return InstanceResult(
                    instance_id=instance_id,
                    status="failed",
                    stdout=stdout,
                    stderr=stderr,
                    duration_seconds=duration,
                    error="No JSON output found in stdout"
                )
        except Exception as e:
            self.logger.error(f"Failed to parse runner output: {e}")
            return InstanceResult(
                instance_id=instance_id,
                status="failed",
                stdout=stdout,
                stderr=stderr,
                duration_seconds=duration,
                error=str(e)
            )
