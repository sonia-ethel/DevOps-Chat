"""
Catalogue de recipes pour l'Installer Engine.

Chaque recipe décrit SEULEMENT des métadonnées (pas de logique d'exécution).
Le runner générique utilise ces métadonnées pour construire les commandes.

MVP Coverage:
- Web servers: nginx, apache
- Reverse proxies/LB: haproxy, traefik
- TLS: certbot
- Runtimes: nodejs, python3, openjdk, dotnet
- Containers: docker, docker-compose, podman
- DB: postgresql, mysql/mariadb, redis, mongodb (community), elasticsearch (repo), rabbitmq
- Monitoring: prometheus-node-exporter, grafana, loki, promtail
- Tools: git, curl, ufw/firewalld, fail2ban
- K8s: kubectl, helm
- Proxy/SSH: openssh-server
- Generic package fallback
"""
from typing import Dict, List, Optional
from .schemas import OSStrategy, Check, AutoFix


class AppRecipe:
    def __init__(
        self,
        name: str,
        description: str,
        os_strategies: Dict[str, OSStrategy],
        checks: List[Check],
        auto_fixes: List[AutoFix],
        ports_needed: bool = False,
        default_port: Optional[int] = None,
        healthcheck_path: str = "/",
    ):
        self.name = name
        self.description = description
        self.os_strategies = os_strategies
        self.checks = checks
        self.auto_fixes = auto_fixes
        self.ports_needed = ports_needed
        self.default_port = default_port
        self.healthcheck_path = healthcheck_path


# ============================================================================
# Common AutoFixes (réutilisables)
# ============================================================================
COMMON_PORT_AUTOFIX = AutoFix(
    if_condition="port_in_use",
    action="choose_next_port",
    description="Requested port is in use, choose next available port"
)
COMMON_SERVICE_AUTOFIX = AutoFix(
    if_condition="service_failed",
    action="collect_journalctl_and_retry",
    description="Service failed to start, collect logs and retry restart"
)
COMMON_CONFIG_AUTOFIX = AutoFix(
    if_condition="config_invalid",
    action="restore_minimal_config",
    description="Config invalid, restore minimal config then retry"
)


# ============================================================================
# NGINX
# ============================================================================
NGINX_RECIPE = AppRecipe(
    name="nginx",
    description="NGINX web server",
    os_strategies={
        "ubuntu": OSStrategy(
            install_strategy="apt",
            package="nginx",
            pre_steps=["apt-get update -y"],
            post_steps=["systemctl enable nginx"],
            version_command="nginx -v 2>&1 | grep -oP 'nginx/\\K[0-9.]+'"
        ),
        "debian": OSStrategy(
            install_strategy="apt",
            package="nginx",
            pre_steps=["apt-get update -y"],
            post_steps=["systemctl enable nginx"],
            version_command="nginx -v 2>&1 | grep -oP 'nginx/\\K[0-9.]+'"
        ),
        "amzn": OSStrategy(
            install_strategy="amazon-linux-extras+yum",
            package="nginx",
            pre_steps=[
                "amazon-linux-extras enable nginx1 || amazon-linux-extras install nginx1 -y",
                "yum clean metadata"
            ],
            post_steps=["systemctl enable nginx"],
            version_command="nginx -v 2>&1 | grep -oP 'nginx/\\K[0-9.]+'"
        ),
        "rhel": OSStrategy(
            install_strategy="yum",
            package="nginx",
            pre_steps=["yum install -y epel-release || true"],
            post_steps=["systemctl enable nginx"],
            version_command="nginx -v 2>&1 | grep -oP 'nginx/\\K[0-9.]+'"
        ),
        "centos": OSStrategy(
            install_strategy="yum",
            package="nginx",
            pre_steps=["yum install -y epel-release || true"],
            post_steps=["systemctl enable nginx"],
            version_command="nginx -v 2>&1 | grep -oP 'nginx/\\K[0-9.]+'"
        ),
        "fedora": OSStrategy(
            install_strategy="dnf",
            package="nginx",
            pre_steps=[],
            post_steps=["systemctl enable nginx"],
            version_command="nginx -v 2>&1 | grep -oP 'nginx/\\K[0-9.]+'"
        ),
    },
    checks=[
        Check(type="service_active", service="nginx", description="NGINX service is active"),
        Check(type="port_listening", port="chosen_port", description="NGINX listening on chosen port"),
        Check(type="http_get", url="http://127.0.0.1:{{chosen_port}}/", expected="200", description="HTTP GET returns 200"),
    ],
    auto_fixes=[COMMON_PORT_AUTOFIX, COMMON_CONFIG_AUTOFIX, COMMON_SERVICE_AUTOFIX],
    ports_needed=True,
    default_port=80,
    healthcheck_path="/"
)

# ============================================================================
# APACHE
# ============================================================================
APACHE_RECIPE = AppRecipe(
    name="apache",
    description="Apache HTTP Server",
    os_strategies={
        "ubuntu": OSStrategy(
            install_strategy="apt",
            package="apache2",
            pre_steps=["apt-get update -y"],
            post_steps=["systemctl enable apache2"],
            version_command="apache2 -v | grep -oP 'Apache/\\K[0-9.]+'"
        ),
        "debian": OSStrategy(
            install_strategy="apt",
            package="apache2",
            pre_steps=["apt-get update -y"],
            post_steps=["systemctl enable apache2"],
            version_command="apache2 -v | grep -oP 'Apache/\\K[0-9.]+'"
        ),
        "amzn": OSStrategy(
            install_strategy="yum",
            package="httpd",
            pre_steps=[],
            post_steps=["systemctl enable httpd"],
            version_command="httpd -v | grep -oP 'Apache/\\K[0-9.]+'"
        ),
        "rhel": OSStrategy(
            install_strategy="yum",
            package="httpd",
            pre_steps=[],
            post_steps=["systemctl enable httpd"],
            version_command="httpd -v | grep -oP 'Apache/\\K[0-9.]+'"
        ),
        "centos": OSStrategy(
            install_strategy="yum",
            package="httpd",
            pre_steps=[],
            post_steps=["systemctl enable httpd"],
            version_command="httpd -v | grep -oP 'Apache/\\K[0-9.]+'"
        ),
        "fedora": OSStrategy(
            install_strategy="dnf",
            package="httpd",
            pre_steps=[],
            post_steps=["systemctl enable httpd"],
            version_command="httpd -v | grep -oP 'Apache/\\K[0-9.]+'"
        ),
    },
    checks=[
        # NOTE: runner doit remplacer {{service_name}} selon OSStrategy (apache2 vs httpd)
        Check(type="service_active", service="{{service_name}}", description="Apache service is active"),
        Check(type="port_listening", port="chosen_port", description="Apache listening on chosen port"),
        Check(type="http_get", url="http://127.0.0.1:{{chosen_port}}/", expected="200", description="HTTP GET returns 200"),
    ],
    auto_fixes=[COMMON_PORT_AUTOFIX, COMMON_SERVICE_AUTOFIX],
    ports_needed=True,
    default_port=80,
    healthcheck_path="/"
)

# ============================================================================
# HAProxy (LB)
# ============================================================================
HAPROXY_RECIPE = AppRecipe(
    name="haproxy",
    description="HAProxy load balancer",
    os_strategies={
        "ubuntu": OSStrategy(install_strategy="apt", package="haproxy", pre_steps=["apt-get update -y"], post_steps=["systemctl enable haproxy"], version_command="haproxy -v | head -1"),
        "debian": OSStrategy(install_strategy="apt", package="haproxy", pre_steps=["apt-get update -y"], post_steps=["systemctl enable haproxy"], version_command="haproxy -v | head -1"),
        "amzn": OSStrategy(install_strategy="yum", package="haproxy", pre_steps=[], post_steps=["systemctl enable haproxy"], version_command="haproxy -v | head -1"),
        "rhel": OSStrategy(install_strategy="yum", package="haproxy", pre_steps=[], post_steps=["systemctl enable haproxy"], version_command="haproxy -v | head -1"),
        "centos": OSStrategy(install_strategy="yum", package="haproxy", pre_steps=[], post_steps=["systemctl enable haproxy"], version_command="haproxy -v | head -1"),
        "fedora": OSStrategy(install_strategy="dnf", package="haproxy", pre_steps=[], post_steps=["systemctl enable haproxy"], version_command="haproxy -v | head -1"),
    },
    checks=[
        Check(type="service_active", service="haproxy", description="HAProxy service active"),
    ],
    auto_fixes=[COMMON_SERVICE_AUTOFIX],
    ports_needed=False,
)

# ============================================================================
# Traefik (proxy) - installation via package (MVP) or binary. Here: package best-effort.
# ============================================================================
TRAEFIK_RECIPE = AppRecipe(
    name="traefik",
    description="Traefik reverse proxy (best-effort via package where available)",
    os_strategies={
        "ubuntu": OSStrategy(install_strategy="apt", package="traefik", pre_steps=["apt-get update -y"], post_steps=["systemctl enable traefik || true"], version_command="traefik version 2>/dev/null || true"),
        "debian": OSStrategy(install_strategy="apt", package="traefik", pre_steps=["apt-get update -y"], post_steps=["systemctl enable traefik || true"], version_command="traefik version 2>/dev/null || true"),
        "amzn": OSStrategy(install_strategy="yum", package="traefik", pre_steps=[], post_steps=["systemctl enable traefik || true"], version_command="traefik version 2>/dev/null || true"),
        "rhel": OSStrategy(install_strategy="yum", package="traefik", pre_steps=[], post_steps=["systemctl enable traefik || true"], version_command="traefik version 2>/dev/null || true"),
        "centos": OSStrategy(install_strategy="yum", package="traefik", pre_steps=[], post_steps=["systemctl enable traefik || true"], version_command="traefik version 2>/dev/null || true"),
        "fedora": OSStrategy(install_strategy="dnf", package="traefik", pre_steps=[], post_steps=["systemctl enable traefik || true"], version_command="traefik version 2>/dev/null || true"),
    },
    checks=[
        Check(type="command", command="traefik version", expected="", description="Traefik binary responds"),
    ],
    auto_fixes=[],
    ports_needed=False,
)

# ============================================================================
# Certbot (TLS)
# ============================================================================
CERTBOT_RECIPE = AppRecipe(
    name="certbot",
    description="Certbot Let's Encrypt client",
    os_strategies={
        "ubuntu": OSStrategy(install_strategy="apt", package="certbot", pre_steps=["apt-get update -y"], post_steps=[], version_command="certbot --version | grep -oP '\\K[0-9.]+' || true"),
        "debian": OSStrategy(install_strategy="apt", package="certbot", pre_steps=["apt-get update -y"], post_steps=[], version_command="certbot --version | grep -oP '\\K[0-9.]+' || true"),
        "amzn": OSStrategy(install_strategy="yum", package="certbot", pre_steps=[], post_steps=[], version_command="certbot --version 2>/dev/null || true"),
        "rhel": OSStrategy(install_strategy="yum", package="certbot", pre_steps=["yum install -y epel-release || true"], post_steps=[], version_command="certbot --version 2>/dev/null || true"),
        "centos": OSStrategy(install_strategy="yum", package="certbot", pre_steps=["yum install -y epel-release || true"], post_steps=[], version_command="certbot --version 2>/dev/null || true"),
        "fedora": OSStrategy(install_strategy="dnf", package="certbot", pre_steps=[], post_steps=[], version_command="certbot --version 2>/dev/null || true"),
    },
    checks=[Check(type="command", command="certbot --version", expected="", description="Certbot installed")],
    auto_fixes=[],
    ports_needed=False,
)

# ============================================================================
# Runtimes: Node.js, Python, Java, .NET (MVP best-effort)
# ============================================================================
NODEJS_RECIPE = AppRecipe(
    name="nodejs",
    description="Node.js runtime (OS package best-effort)",
    os_strategies={
        "ubuntu": OSStrategy(install_strategy="apt", package="nodejs", pre_steps=["apt-get update -y"], post_steps=[], version_command="node -v 2>/dev/null || true"),
        "debian": OSStrategy(install_strategy="apt", package="nodejs", pre_steps=["apt-get update -y"], post_steps=[], version_command="node -v 2>/dev/null || true"),
        "amzn": OSStrategy(install_strategy="yum", package="nodejs", pre_steps=[], post_steps=[], version_command="node -v 2>/dev/null || true"),
        "rhel": OSStrategy(install_strategy="yum", package="nodejs", pre_steps=[], post_steps=[], version_command="node -v 2>/dev/null || true"),
        "centos": OSStrategy(install_strategy="yum", package="nodejs", pre_steps=[], post_steps=[], version_command="node -v 2>/dev/null || true"),
        "fedora": OSStrategy(install_strategy="dnf", package="nodejs", pre_steps=[], post_steps=[], version_command="node -v 2>/dev/null || true"),
    },
    checks=[Check(type="command", command="node -v", expected="", description="Node installed")],
    auto_fixes=[],
)

PYTHON3_RECIPE = AppRecipe(
    name="python3",
    description="Python 3 runtime",
    os_strategies={
        "ubuntu": OSStrategy(install_strategy="apt", package="python3", pre_steps=["apt-get update -y"], post_steps=[], version_command="python3 --version | grep -oP '\\K[0-9.]+' || true"),
        "debian": OSStrategy(install_strategy="apt", package="python3", pre_steps=["apt-get update -y"], post_steps=[], version_command="python3 --version | grep -oP '\\K[0-9.]+' || true"),
        "amzn": OSStrategy(install_strategy="yum", package="python3", pre_steps=[], post_steps=[], version_command="python3 --version 2>/dev/null || true"),
        "rhel": OSStrategy(install_strategy="yum", package="python3", pre_steps=[], post_steps=[], version_command="python3 --version 2>/dev/null || true"),
        "centos": OSStrategy(install_strategy="yum", package="python3", pre_steps=[], post_steps=[], version_command="python3 --version 2>/dev/null || true"),
        "fedora": OSStrategy(install_strategy="dnf", package="python3", pre_steps=[], post_steps=[], version_command="python3 --version 2>/dev/null || true"),
    },
    checks=[Check(type="command", command="python3 --version", expected="", description="Python3 installed")],
    auto_fixes=[],
)

OPENJDK_RECIPE = AppRecipe(
    name="openjdk",
    description="OpenJDK (default)",
    os_strategies={
        "ubuntu": OSStrategy(install_strategy="apt", package="default-jre", pre_steps=["apt-get update -y"], post_steps=[], version_command="java -version 2>&1 | head -1"),
        "debian": OSStrategy(install_strategy="apt", package="default-jre", pre_steps=["apt-get update -y"], post_steps=[], version_command="java -version 2>&1 | head -1"),
        "amzn": OSStrategy(install_strategy="yum", package="java-17-amazon-corretto-headless", pre_steps=[], post_steps=[], version_command="java -version 2>&1 | head -1"),
        "rhel": OSStrategy(install_strategy="yum", package="java-11-openjdk", pre_steps=[], post_steps=[], version_command="java -version 2>&1 | head -1"),
        "centos": OSStrategy(install_strategy="yum", package="java-11-openjdk", pre_steps=[], post_steps=[], version_command="java -version 2>&1 | head -1"),
        "fedora": OSStrategy(install_strategy="dnf", package="java-17-openjdk", pre_steps=[], post_steps=[], version_command="java -version 2>&1 | head -1"),
    },
    checks=[Check(type="command", command="java -version", expected="", description="Java present")],
    auto_fixes=[],
)

DOTNET_RECIPE = AppRecipe(
    name="dotnet",
    description=".NET SDK/runtime (best-effort via OS packages)",
    os_strategies={
        "ubuntu": OSStrategy(install_strategy="apt", package="dotnet-sdk-8.0", pre_steps=["apt-get update -y"], post_steps=[], version_command="dotnet --version 2>/dev/null || true"),
        "debian": OSStrategy(install_strategy="apt", package="dotnet-sdk-8.0", pre_steps=["apt-get update -y"], post_steps=[], version_command="dotnet --version 2>/dev/null || true"),
        "amzn": OSStrategy(install_strategy="yum", package="dotnet-sdk-8.0", pre_steps=[], post_steps=[], version_command="dotnet --version 2>/dev/null || true"),
        "rhel": OSStrategy(install_strategy="yum", package="dotnet-sdk-8.0", pre_steps=[], post_steps=[], version_command="dotnet --version 2>/dev/null || true"),
        "centos": OSStrategy(install_strategy="yum", package="dotnet-sdk-8.0", pre_steps=[], post_steps=[], version_command="dotnet --version 2>/dev/null || true"),
        "fedora": OSStrategy(install_strategy="dnf", package="dotnet-sdk-8.0", pre_steps=[], post_steps=[], version_command="dotnet --version 2>/dev/null || true"),
    },
    checks=[Check(type="command", command="dotnet --version", expected="", description="dotnet present")],
    auto_fixes=[],
)

# ============================================================================
# Containers: Docker / Docker Compose / Podman
# ============================================================================
DOCKER_RECIPE = AppRecipe(
    name="docker",
    description="Docker container runtime",
    os_strategies={
        "ubuntu": OSStrategy(
            install_strategy="apt",
            package="docker.io",
            pre_steps=["apt-get update -y"],
            post_steps=["systemctl enable docker", "systemctl start docker"],
            version_command="docker --version | grep -oP 'Docker version \\K[0-9.]+'"
        ),
        "debian": OSStrategy(
            install_strategy="apt",
            package="docker.io",
            pre_steps=["apt-get update -y"],
            post_steps=["systemctl enable docker", "systemctl start docker"],
            version_command="docker --version | grep -oP 'Docker version \\K[0-9.]+'"
        ),
        "amzn": OSStrategy(
            install_strategy="yum",
            package="docker",
            pre_steps=[],
            post_steps=["systemctl enable docker", "systemctl start docker"],
            version_command="docker --version | grep -oP 'Docker version \\K[0-9.]+'"
        ),
        "rhel": OSStrategy(
            install_strategy="yum",
            package="docker",
            pre_steps=["yum install -y yum-utils || true", "yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo || true"],
            post_steps=["systemctl enable docker", "systemctl start docker"],
            version_command="docker --version | grep -oP 'Docker version \\K[0-9.]+'"
        ),
        "centos": OSStrategy(
            install_strategy="yum",
            package="docker",
            pre_steps=["yum install -y yum-utils || true", "yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo || true"],
            post_steps=["systemctl enable docker", "systemctl start docker"],
            version_command="docker --version | grep -oP 'Docker version \\K[0-9.]+'"
        ),
        "fedora": OSStrategy(
            install_strategy="dnf",
            package="docker",
            pre_steps=[],
            post_steps=["systemctl enable docker", "systemctl start docker"],
            version_command="docker --version | grep -oP 'Docker version \\K[0-9.]+'"
        ),
    },
    checks=[
        Check(type="service_active", service="docker", description="Docker service is active"),
        Check(type="command", command="docker ps", expected="", description="Docker daemon responds"),
    ],
    auto_fixes=[COMMON_SERVICE_AUTOFIX],
    ports_needed=False,
)

DOCKER_COMPOSE_RECIPE = AppRecipe(
    name="docker-compose",
    description="Docker Compose (plugin or binary, best-effort)",
    os_strategies={
        "ubuntu": OSStrategy(install_strategy="apt", package="docker-compose", pre_steps=["apt-get update -y"], post_steps=[], version_command="docker-compose version 2>/dev/null || docker compose version 2>/dev/null || true"),
        "debian": OSStrategy(install_strategy="apt", package="docker-compose", pre_steps=["apt-get update -y"], post_steps=[], version_command="docker-compose version 2>/dev/null || docker compose version 2>/dev/null || true"),
        "amzn": OSStrategy(install_strategy="yum", package="docker-compose", pre_steps=[], post_steps=[], version_command="docker-compose version 2>/dev/null || true"),
        "rhel": OSStrategy(install_strategy="yum", package="docker-compose", pre_steps=[], post_steps=[], version_command="docker-compose version 2>/dev/null || true"),
        "centos": OSStrategy(install_strategy="yum", package="docker-compose", pre_steps=[], post_steps=[], version_command="docker-compose version 2>/dev/null || true"),
        "fedora": OSStrategy(install_strategy="dnf", package="docker-compose", pre_steps=[], post_steps=[], version_command="docker-compose version 2>/dev/null || true"),
    },
    checks=[Check(type="command", command="docker-compose version || docker compose version", expected="", description="Compose available")],
    auto_fixes=[],
)

PODMAN_RECIPE = AppRecipe(
    name="podman",
    description="Podman container engine",
    os_strategies={
        "ubuntu": OSStrategy(install_strategy="apt", package="podman", pre_steps=["apt-get update -y"], post_steps=[], version_command="podman --version 2>/dev/null || true"),
        "debian": OSStrategy(install_strategy="apt", package="podman", pre_steps=["apt-get update -y"], post_steps=[], version_command="podman --version 2>/dev/null || true"),
        "amzn": OSStrategy(install_strategy="yum", package="podman", pre_steps=[], post_steps=[], version_command="podman --version 2>/dev/null || true"),
        "rhel": OSStrategy(install_strategy="yum", package="podman", pre_steps=[], post_steps=[], version_command="podman --version 2>/dev/null || true"),
        "centos": OSStrategy(install_strategy="yum", package="podman", pre_steps=[], post_steps=[], version_command="podman --version 2>/dev/null || true"),
        "fedora": OSStrategy(install_strategy="dnf", package="podman", pre_steps=[], post_steps=[], version_command="podman --version 2>/dev/null || true"),
    },
    checks=[Check(type="command", command="podman --version", expected="", description="Podman installed")],
    auto_fixes=[],
)

# ============================================================================
# Databases / caches
# ============================================================================
POSTGRES_RECIPE = AppRecipe(
    name="postgresql",
    description="PostgreSQL server",
    os_strategies={
        "ubuntu": OSStrategy(install_strategy="apt", package="postgresql", pre_steps=["apt-get update -y"], post_steps=["systemctl enable postgresql"], version_command="psql --version | grep -oP '\\K[0-9.]+' || true"),
        "debian": OSStrategy(install_strategy="apt", package="postgresql", pre_steps=["apt-get update -y"], post_steps=["systemctl enable postgresql"], version_command="psql --version | grep -oP '\\K[0-9.]+' || true"),
        "amzn": OSStrategy(install_strategy="yum", package="postgresql-server", pre_steps=[], post_steps=["systemctl enable postgresql || true"], version_command="psql --version 2>/dev/null || true"),
        "rhel": OSStrategy(install_strategy="yum", package="postgresql-server", pre_steps=[], post_steps=["systemctl enable postgresql || true"], version_command="psql --version 2>/dev/null || true"),
        "centos": OSStrategy(install_strategy="yum", package="postgresql-server", pre_steps=[], post_steps=["systemctl enable postgresql || true"], version_command="psql --version 2>/dev/null || true"),
        "fedora": OSStrategy(install_strategy="dnf", package="postgresql-server", pre_steps=[], post_steps=["systemctl enable postgresql || true"], version_command="psql --version 2>/dev/null || true"),
    },
    checks=[Check(type="service_active", service="postgresql", description="PostgreSQL service active")],
    auto_fixes=[COMMON_SERVICE_AUTOFIX],
    ports_needed=True,
    default_port=5432,
)

REDIS_RECIPE = AppRecipe(
    name="redis",
    description="Redis server",
    os_strategies={
        "ubuntu": OSStrategy(install_strategy="apt", package="redis-server", pre_steps=["apt-get update -y"], post_steps=["systemctl enable redis-server"], version_command="redis-server --version 2>/dev/null || true"),
        "debian": OSStrategy(install_strategy="apt", package="redis-server", pre_steps=["apt-get update -y"], post_steps=["systemctl enable redis-server"], version_command="redis-server --version 2>/dev/null || true"),
        "amzn": OSStrategy(install_strategy="yum", package="redis", pre_steps=[], post_steps=["systemctl enable redis || true"], version_command="redis-server --version 2>/dev/null || true"),
        "rhel": OSStrategy(install_strategy="yum", package="redis", pre_steps=[], post_steps=["systemctl enable redis || true"], version_command="redis-server --version 2>/dev/null || true"),
        "centos": OSStrategy(install_strategy="yum", package="redis", pre_steps=[], post_steps=["systemctl enable redis || true"], version_command="redis-server --version 2>/dev/null || true"),
        "fedora": OSStrategy(install_strategy="dnf", package="redis", pre_steps=[], post_steps=["systemctl enable redis || true"], version_command="redis-server --version 2>/dev/null || true"),
    },
    checks=[Check(type="service_active", service="{{service_name}}", description="Redis service active")],
    auto_fixes=[COMMON_SERVICE_AUTOFIX],
    ports_needed=True,
    default_port=6379,
)

MARIADB_RECIPE = AppRecipe(
    name="mariadb",
    description="MariaDB server",
    os_strategies={
        "ubuntu": OSStrategy(install_strategy="apt", package="mariadb-server", pre_steps=["apt-get update -y"], post_steps=["systemctl enable mariadb"], version_command="mariadb --version 2>/dev/null || mysql --version 2>/dev/null || true"),
        "debian": OSStrategy(install_strategy="apt", package="mariadb-server", pre_steps=["apt-get update -y"], post_steps=["systemctl enable mariadb"], version_command="mariadb --version 2>/dev/null || mysql --version 2>/dev/null || true"),
        "amzn": OSStrategy(install_strategy="yum", package="mariadb-server", pre_steps=[], post_steps=["systemctl enable mariadb || true"], version_command="mysql --version 2>/dev/null || true"),
        "rhel": OSStrategy(install_strategy="yum", package="mariadb-server", pre_steps=[], post_steps=["systemctl enable mariadb || true"], version_command="mysql --version 2>/dev/null || true"),
        "centos": OSStrategy(install_strategy="yum", package="mariadb-server", pre_steps=[], post_steps=["systemctl enable mariadb || true"], version_command="mysql --version 2>/dev/null || true"),
        "fedora": OSStrategy(install_strategy="dnf", package="mariadb-server", pre_steps=[], post_steps=["systemctl enable mariadb || true"], version_command="mysql --version 2>/dev/null || true"),
    },
    checks=[Check(type="service_active", service="mariadb", description="MariaDB active")],
    auto_fixes=[COMMON_SERVICE_AUTOFIX],
    ports_needed=True,
    default_port=3306,
)

MONGODB_RECIPE = AppRecipe(
    name="mongodb",
    description="MongoDB (best-effort via OS package where available)",
    os_strategies={
        "ubuntu": OSStrategy(install_strategy="apt", package="mongodb", pre_steps=["apt-get update -y"], post_steps=["systemctl enable mongodb || true"], version_command="mongod --version 2>/dev/null | head -1 || true"),
        "debian": OSStrategy(install_strategy="apt", package="mongodb", pre_steps=["apt-get update -y"], post_steps=["systemctl enable mongodb || true"], version_command="mongod --version 2>/dev/null | head -1 || true"),
        "amzn": OSStrategy(install_strategy="yum", package="mongodb", pre_steps=[], post_steps=["systemctl enable mongod || true"], version_command="mongod --version 2>/dev/null | head -1 || true"),
        "rhel": OSStrategy(install_strategy="yum", package="mongodb", pre_steps=[], post_steps=["systemctl enable mongod || true"], version_command="mongod --version 2>/dev/null | head -1 || true"),
        "centos": OSStrategy(install_strategy="yum", package="mongodb", pre_steps=[], post_steps=["systemctl enable mongod || true"], version_command="mongod --version 2>/dev/null | head -1 || true"),
        "fedora": OSStrategy(install_strategy="dnf", package="mongodb", pre_steps=[], post_steps=["systemctl enable mongod || true"], version_command="mongod --version 2>/dev/null | head -1 || true"),
    },
    checks=[Check(type="command", command="mongod --version", expected="", description="mongod exists")],
    auto_fixes=[],
    ports_needed=True,
    default_port=27017,
)

RABBITMQ_RECIPE = AppRecipe(
    name="rabbitmq",
    description="RabbitMQ message broker",
    os_strategies={
        "ubuntu": OSStrategy(install_strategy="apt", package="rabbitmq-server", pre_steps=["apt-get update -y"], post_steps=["systemctl enable rabbitmq-server"], version_command="rabbitmqctl version 2>/dev/null || true"),
        "debian": OSStrategy(install_strategy="apt", package="rabbitmq-server", pre_steps=["apt-get update -y"], post_steps=["systemctl enable rabbitmq-server"], version_command="rabbitmqctl version 2>/dev/null || true"),
        "amzn": OSStrategy(install_strategy="yum", package="rabbitmq-server", pre_steps=[], post_steps=["systemctl enable rabbitmq-server || true"], version_command="rabbitmqctl version 2>/dev/null || true"),
        "rhel": OSStrategy(install_strategy="yum", package="rabbitmq-server", pre_steps=[], post_steps=["systemctl enable rabbitmq-server || true"], version_command="rabbitmqctl version 2>/dev/null || true"),
        "centos": OSStrategy(install_strategy="yum", package="rabbitmq-server", pre_steps=[], post_steps=["systemctl enable rabbitmq-server || true"], version_command="rabbitmqctl version 2>/dev/null || true"),
        "fedora": OSStrategy(install_strategy="dnf", package="rabbitmq-server", pre_steps=[], post_steps=["systemctl enable rabbitmq-server || true"], version_command="rabbitmqctl version 2>/dev/null || true"),
    },
    checks=[Check(type="service_active", service="rabbitmq-server", description="RabbitMQ active")],
    auto_fixes=[COMMON_SERVICE_AUTOFIX],
    ports_needed=True,
    default_port=5672,
)

# ============================================================================
# Monitoring / logging
# ============================================================================
NODE_EXPORTER_RECIPE = AppRecipe(
    name="node-exporter",
    description="Prometheus Node Exporter",
    os_strategies={
        "ubuntu": OSStrategy(install_strategy="apt", package="prometheus-node-exporter", pre_steps=["apt-get update -y"], post_steps=["systemctl enable prometheus-node-exporter"], version_command="prometheus-node-exporter --version 2>/dev/null || true"),
        "debian": OSStrategy(install_strategy="apt", package="prometheus-node-exporter", pre_steps=["apt-get update -y"], post_steps=["systemctl enable prometheus-node-exporter"], version_command="prometheus-node-exporter --version 2>/dev/null || true"),
        "amzn": OSStrategy(install_strategy="yum", package="node_exporter", pre_steps=[], post_steps=[], version_command="node_exporter --version 2>/dev/null || true"),
        "rhel": OSStrategy(install_strategy="yum", package="node_exporter", pre_steps=[], post_steps=[], version_command="node_exporter --version 2>/dev/null || true"),
        "centos": OSStrategy(install_strategy="yum", package="node_exporter", pre_steps=[], post_steps=[], version_command="node_exporter --version 2>/dev/null || true"),
        "fedora": OSStrategy(install_strategy="dnf", package="node_exporter", pre_steps=[], post_steps=[], version_command="node_exporter --version 2>/dev/null || true"),
    },
    checks=[Check(type="command", command="prometheus-node-exporter --version || node_exporter --version", expected="", description="Exporter installed")],
    auto_fixes=[],
    ports_needed=True,
    default_port=9100,
)

GRAFANA_RECIPE = AppRecipe(
    name="grafana",
    description="Grafana (best-effort via OS package)",
    os_strategies={
        "ubuntu": OSStrategy(install_strategy="apt", package="grafana", pre_steps=["apt-get update -y"], post_steps=["systemctl enable grafana-server || true"], version_command="grafana-server -v 2>/dev/null || true"),
        "debian": OSStrategy(install_strategy="apt", package="grafana", pre_steps=["apt-get update -y"], post_steps=["systemctl enable grafana-server || true"], version_command="grafana-server -v 2>/dev/null || true"),
        "amzn": OSStrategy(install_strategy="yum", package="grafana", pre_steps=[], post_steps=["systemctl enable grafana-server || true"], version_command="grafana-server -v 2>/dev/null || true"),
        "rhel": OSStrategy(install_strategy="yum", package="grafana", pre_steps=[], post_steps=["systemctl enable grafana-server || true"], version_command="grafana-server -v 2>/dev/null || true"),
        "centos": OSStrategy(install_strategy="yum", package="grafana", pre_steps=[], post_steps=["systemctl enable grafana-server || true"], version_command="grafana-server -v 2>/dev/null || true"),
        "fedora": OSStrategy(install_strategy="dnf", package="grafana", pre_steps=[], post_steps=["systemctl enable grafana-server || true"], version_command="grafana-server -v 2>/dev/null || true"),
    },
    checks=[Check(type="service_active", service="grafana-server", description="Grafana active")],
    auto_fixes=[COMMON_SERVICE_AUTOFIX],
    ports_needed=True,
    default_port=3000,
)

# ============================================================================
# Security / network
# ============================================================================
FAIL2BAN_RECIPE = AppRecipe(
    name="fail2ban",
    description="Fail2ban intrusion prevention",
    os_strategies={
        "ubuntu": OSStrategy(install_strategy="apt", package="fail2ban", pre_steps=["apt-get update -y"], post_steps=["systemctl enable fail2ban"], version_command="fail2ban-client --version 2>/dev/null || true"),
        "debian": OSStrategy(install_strategy="apt", package="fail2ban", pre_steps=["apt-get update -y"], post_steps=["systemctl enable fail2ban"], version_command="fail2ban-client --version 2>/dev/null || true"),
        "amzn": OSStrategy(install_strategy="yum", package="fail2ban", pre_steps=[], post_steps=["systemctl enable fail2ban || true"], version_command="fail2ban-client --version 2>/dev/null || true"),
        "rhel": OSStrategy(install_strategy="yum", package="fail2ban", pre_steps=["yum install -y epel-release || true"], post_steps=["systemctl enable fail2ban || true"], version_command="fail2ban-client --version 2>/dev/null || true"),
        "centos": OSStrategy(install_strategy="yum", package="fail2ban", pre_steps=["yum install -y epel-release || true"], post_steps=["systemctl enable fail2ban || true"], version_command="fail2ban-client --version 2>/dev/null || true"),
        "fedora": OSStrategy(install_strategy="dnf", package="fail2ban", pre_steps=[], post_steps=["systemctl enable fail2ban || true"], version_command="fail2ban-client --version 2>/dev/null || true"),
    },
    checks=[Check(type="service_active", service="fail2ban", description="fail2ban active")],
    auto_fixes=[COMMON_SERVICE_AUTOFIX],
)

# ============================================================================
# K8s tools
# ============================================================================
KUBECTL_RECIPE = AppRecipe(
    name="kubectl",
    description="Kubernetes kubectl client (best-effort)",
    os_strategies={
        "ubuntu": OSStrategy(install_strategy="apt", package="kubectl", pre_steps=["apt-get update -y"], post_steps=[], version_command="kubectl version --client --short 2>/dev/null || true"),
        "debian": OSStrategy(install_strategy="apt", package="kubectl", pre_steps=["apt-get update -y"], post_steps=[], version_command="kubectl version --client --short 2>/dev/null || true"),
        "amzn": OSStrategy(install_strategy="yum", package="kubectl", pre_steps=[], post_steps=[], version_command="kubectl version --client --short 2>/dev/null || true"),
        "rhel": OSStrategy(install_strategy="yum", package="kubectl", pre_steps=[], post_steps=[], version_command="kubectl version --client --short 2>/dev/null || true"),
        "centos": OSStrategy(install_strategy="yum", package="kubectl", pre_steps=[], post_steps=[], version_command="kubectl version --client --short 2>/dev/null || true"),
        "fedora": OSStrategy(install_strategy="dnf", package="kubectl", pre_steps=[], post_steps=[], version_command="kubectl version --client --short 2>/dev/null || true"),
    },
    checks=[Check(type="command", command="kubectl version --client --short", expected="", description="kubectl present")],
    auto_fixes=[],
)

HELM_RECIPE = AppRecipe(
    name="helm",
    description="Helm client (best-effort via package)",
    os_strategies={
        "ubuntu": OSStrategy(install_strategy="apt", package="helm", pre_steps=["apt-get update -y"], post_steps=[], version_command="helm version --short 2>/dev/null || true"),
        "debian": OSStrategy(install_strategy="apt", package="helm", pre_steps=["apt-get update -y"], post_steps=[], version_command="helm version --short 2>/dev/null || true"),
        "amzn": OSStrategy(install_strategy="yum", package="helm", pre_steps=[], post_steps=[], version_command="helm version --short 2>/dev/null || true"),
        "rhel": OSStrategy(install_strategy="yum", package="helm", pre_steps=[], post_steps=[], version_command="helm version --short 2>/dev/null || true"),
        "centos": OSStrategy(install_strategy="yum", package="helm", pre_steps=[], post_steps=[], version_command="helm version --short 2>/dev/null || true"),
        "fedora": OSStrategy(install_strategy="dnf", package="helm", pre_steps=[], post_steps=[], version_command="helm version --short 2>/dev/null || true"),
    },
    checks=[Check(type="command", command="helm version --short", expected="", description="helm present")],
    auto_fixes=[],
)

# ============================================================================
# Generic fallback: install any OS package + optional service check
# ============================================================================
GENERIC_PACKAGE_RECIPE = AppRecipe(
    name="generic_package",
    description="Generic OS package installer (fallback). Requires request to provide package/service/checks.",
    os_strategies={
        # runner must override `package` dynamically from request for this recipe
        "ubuntu": OSStrategy(install_strategy="apt", package="{{package}}", pre_steps=["apt-get update -y"], post_steps=[], version_command=""),
        "debian": OSStrategy(install_strategy="apt", package="{{package}}", pre_steps=["apt-get update -y"], post_steps=[], version_command=""),
        "amzn": OSStrategy(install_strategy="yum", package="{{package}}", pre_steps=[], post_steps=[], version_command=""),
        "rhel": OSStrategy(install_strategy="yum", package="{{package}}", pre_steps=[], post_steps=[], version_command=""),
        "centos": OSStrategy(install_strategy="yum", package="{{package}}", pre_steps=[], post_steps=[], version_command=""),
        "fedora": OSStrategy(install_strategy="dnf", package="{{package}}", pre_steps=[], post_steps=[], version_command=""),
    },
    checks=[],
    auto_fixes=[],
    ports_needed=False,
)

# ============================================================================
# Registry
# ============================================================================
RECIPE_REGISTRY: Dict[str, AppRecipe] = {
    # web
    "nginx": NGINX_RECIPE,
    "apache": APACHE_RECIPE,
    "apache2": APACHE_RECIPE,
    "httpd": APACHE_RECIPE,
    "haproxy": HAPROXY_RECIPE,
    "traefik": TRAEFIK_RECIPE,
    "certbot": CERTBOT_RECIPE,

    # runtimes
    "node": NODEJS_RECIPE,
    "nodejs": NODEJS_RECIPE,
    "python3": PYTHON3_RECIPE,
    "java": OPENJDK_RECIPE,
    "openjdk": OPENJDK_RECIPE,
    "dotnet": DOTNET_RECIPE,

    # containers
    "docker": DOCKER_RECIPE,
    "docker-compose": DOCKER_COMPOSE_RECIPE,
    "podman": PODMAN_RECIPE,

    # db/cache
    "postgres": POSTGRES_RECIPE,
    "postgresql": POSTGRES_RECIPE,
    "redis": REDIS_RECIPE,
    "mariadb": MARIADB_RECIPE,
    "mysql": MARIADB_RECIPE,  # fallback mysql->mariadb for MVP
    "mongodb": MONGODB_RECIPE,
    "rabbitmq": RABBITMQ_RECIPE,

    # monitoring
    "node-exporter": NODE_EXPORTER_RECIPE,
    "prometheus-node-exporter": NODE_EXPORTER_RECIPE,
    "grafana": GRAFANA_RECIPE,

    # security
    "fail2ban": FAIL2BAN_RECIPE,

    # k8s tools
    "kubectl": KUBECTL_RECIPE,
    "helm": HELM_RECIPE,

    # generic fallback
    "_generic": GENERIC_PACKAGE_RECIPE,
}


def get_recipe(app_name: str) -> Optional[AppRecipe]:
    return RECIPE_REGISTRY.get(app_name.lower())


def list_recipes() -> List[str]:
    """Liste tous les apps disponibles dans le registry (sauf _generic)."""
    return [k for k in RECIPE_REGISTRY.keys() if not k.startswith("_")]
