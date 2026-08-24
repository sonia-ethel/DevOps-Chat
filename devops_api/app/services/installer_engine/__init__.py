"""
DAC Installer Engine - Système d'installation générique multi-app.

Package complet pour gérer l'installation de 35+ applications
sur n'importe quelle distribution Linux via SSM.

Architecture:
    Request -> Engine (Plan) -> Runner (Execute) -> Result

Components:
    - schemas.py: Schémas Pydantic standard (Request/Plan/Result)
    - app_recipes.py: Catalogue de 35+ recipes (nginx, apache, docker, redis, postgres, etc.)
    - installer_engine.py: Phase A - Analyse et planification
    - installer_runner.py: Phase B - Génération de scripts bash et exécution

Usage:
    from installer_engine import InstallerEngine, InstallerRunner
    from installer_engine import create_installation_request_from_text
    
    # Créer une requête
    request = create_installation_request_from_text(
        "installe nginx sur port 8080",
        instances=["i-1234567890abcdef0"]
    )
    
    # Planifier
    engine = InstallerEngine()
    plan = engine.create_plan(request)
    
    # Exécuter
    runner = InstallerRunner()
    script = runner.generate_runner_script(plan)
    # Envoyer le script via SSM...

Supported Apps (35+):
    - Web: nginx, apache, haproxy, traefik, certbot
    - Runtimes: nodejs, python3, openjdk, dotnet
    - Containers: docker, docker-compose, podman
    - Databases: postgresql, mariadb, redis, mongodb, rabbitmq
    - Monitoring: node-exporter, grafana
    - Security: fail2ban
    - K8s: kubectl, helm
    - Generic fallback pour tout package OS
"""

# Core classes
from .installer_engine import InstallerEngine, create_installation_request_from_text
from .installer_runner import InstallerRunner

# Schemas
from .schemas import (
    InstallationRequest,
    InstallationPlan,
    InstallationResult,
    InstanceResult,
    InstallationSummary,
    OSInfo,
    AppSpec,
    AppConfig,
    Check,
    AutoFix,
    OSStrategy,
)

# Recipes
from .app_recipes import (
    get_recipe,
    list_recipes,
    RECIPE_REGISTRY,
    AppRecipe,
    # Common recipes
    NGINX_RECIPE,
    APACHE_RECIPE,
    DOCKER_RECIPE,
    REDIS_RECIPE,
    POSTGRES_RECIPE,
)

__all__ = [
    # Engine & Runner
    "InstallerEngine",
    "InstallerRunner",
    "create_installation_request_from_text",
    
    # Schemas
    "InstallationRequest",
    "InstallationPlan",
    "InstallationResult",
    "InstanceResult",
    "InstallationSummary",
    "OSInfo",
    "AppSpec",
    "AppConfig",
    "Check",
    "AutoFix",
    "OSStrategy",
    
    # Recipes
    "get_recipe",
    "list_recipes",
    "RECIPE_REGISTRY",
    "AppRecipe",
    "NGINX_RECIPE",
    "APACHE_RECIPE",
    "DOCKER_RECIPE",
    "REDIS_RECIPE",
    "POSTGRES_RECIPE",
]

__version__ = "1.0.0"
