"""
Installer Engine - Moteur d'installation générique pour DAC.

Phase A: Analyse -> Planification
Transforme une InstallationRequest en InstallationPlan exécutable.
"""
import logging
from typing import Optional
from .schemas import InstallationRequest, InstallationPlan, AppSpec
from .app_recipes import get_recipe, list_recipes, RECIPE_REGISTRY

logger = logging.getLogger(__name__)


class InstallerEngine:
    """
    Moteur d'installation générique.
    
    Responsabilités:
    - Analyser la requête d'installation
    - Charger la recipe appropriée (35+ apps supportées)
    - Générer un plan d'installation multi-OS
    - Définir les checks et auto-fixes
    """
    
    def __init__(self):
        self.logger = logger
    
    def create_plan(self, request: InstallationRequest) -> Optional[InstallationPlan]:
        """
        Crée un plan d'installation à partir d'une requête.
        
        Args:
            request: La requête d'installation
            
        Returns:
            Un plan d'installation ou None si l'app n'est pas supportée
        """
        app_name = request.app.name.lower()
        self.logger.info(f" Création du plan pour: {app_name}")
        
        # Charger la recipe
        recipe = get_recipe(app_name)
        if not recipe:
            # Fallback to generic package installer
            self.logger.warning(f"  Aucune recipe spécifique pour '{app_name}', utilisation du generic fallback")
            recipe = RECIPE_REGISTRY.get("_generic")
            if not recipe:
                self.logger.error(f" Aucune recipe trouvée pour: {app_name}")
                return None
        
        self.logger.info(f" Recipe '{recipe.name}' chargée: {recipe.description}")
        
        # Enrichir la config avec les defaults de la recipe si nécessaire
        if recipe.ports_needed and not request.app.config.requested_port:
            if recipe.default_port:
                request.app.config.requested_port = recipe.default_port
                self.logger.info(f" Port par défaut: {recipe.default_port}")
        
        # Créer le plan
        plan = InstallationPlan(
            app=request.app,
            os_matrix=recipe.os_strategies,
            checks=recipe.checks,
            auto_fixes=recipe.auto_fixes,
            ports_needed=recipe.ports_needed
        )
        
        self.logger.info(f" Plan créé avec {len(plan.os_matrix)} stratégies OS")
        self.logger.info(f"   Checks: {len(plan.checks)}, Auto-fixes: {len(plan.auto_fixes)}")
        
        return plan
    
    def validate_request(self, request: InstallationRequest) -> tuple[bool, str]:
        """
        Valide une requête d'installation.
        
        Returns:
            (valid, error_message)
        """
        # Vérifier que l'app est supportée
        recipe = get_recipe(request.app.name)
        if not recipe and "_generic" not in RECIPE_REGISTRY:
            supported = ", ".join(list_recipes()[:10]) + "..."  # Show first 10
            return False, f"App '{request.app.name}' non supportée. Apps disponibles: {supported}"
        
        # Vérifier les instances
        if not request.instances:
            return False, "Aucune instance spécifiée"
        
        # Vérifier les ports si nécessaire
        if recipe and recipe.ports_needed:
            if not request.app.config.requested_port and not recipe.default_port:
                return False, f"Port requis pour {request.app.name} mais non spécifié"
        
        return True, ""


# ============================================================================
# Helper functions
# ============================================================================

def create_installation_request_from_text(
    text: str,
    instances: list,
    default_app: str = "nginx"
) -> InstallationRequest:
    """
    Crée une InstallationRequest à partir d'un texte utilisateur.
    
    Exemples:
    - "installe nginx"
    - "installe apache sur le port 8080"
    - "installe docker"
    - "installe postgresql"
    - "installe redis sur port 6380"
    - "installe grafana"
    
    Args:
        text: Le texte de l'utilisateur
        instances: Les IDs d'instances
        default_app: App par défaut si non détectée
        
    Returns:
        Une InstallationRequest
    """
    text_lower = text.lower()
    
    # Détecter l'app (cherche dans toutes les recipes disponibles)
    app_name = default_app
    available_apps = list_recipes()
    
    for app in available_apps:
        if app in text_lower:
            app_name = app
            break
    
    # Si pas trouvé dans les recipes, extraire le mot après "installe"
    if app_name == default_app and "install" in text_lower:
        import re
        install_match = re.search(r'install[e]?\s+([a-z0-9-]+)', text_lower)
        if install_match:
            potential_app = install_match.group(1)
            # Vérifier si c'est dans le registry ou utiliser tel quel (generic)
            app_name = potential_app
    
    # Détecter le port
    import re
    port_match = re.search(r'port\s+(\d+)', text_lower)
    requested_port = int(port_match.group(1)) if port_match else None
    
    # Détecter la version
    version_match = re.search(r'version\s+([0-9.]+)', text_lower)
    requested_version = version_match.group(1) if version_match else None
    
    # Construire la requête
    from .schemas import AppSpec, AppConfig, InstallationRequest
    
    app_spec = AppSpec(
        name=app_name,
        requested_version=requested_version,
        config=AppConfig(requested_port=requested_port) if requested_port else AppConfig()
    )
    
    request = InstallationRequest(
        app=app_spec,
        instances=instances
    )
    
    return request
