# © 2024–2026 TOURE Arnaud Patrick
# Licensed under the MIT License

"""
Config Catalog: Déterministe matching d'actions configure
Évite la magie, du scoring simple par keywords.
"""

import re
import unicodedata
from typing import Optional, List, Tuple, Dict, Any
from dataclasses import dataclass, asdict
from enum import Enum


class ConfigCategory(str, Enum):
    WEB = "web"
    SECURITY = "security"
    SYSTEM = "system"
    OBSERVABILITY = "observability"
    DATABASE = "database"
    CONTAINER = "container"


@dataclass
class ConfigAction:
    """Une action de configuration reconnaissable"""
    id: str
    label: str
    category: ConfigCategory
    keywords: List[str]  # Mots-clés déclencheurs (en minuscules)
    description: str
    params_schema: Optional[Dict[str, Any]] = None  # ex: {"port": int, ...}
    
    def to_dict(self):
        return {
            "id": self.id,
            "label": self.label,
            "category": self.category.value,
            "description": self.description,
            "keywords": self.keywords,
        }
    
    def is_installation(self) -> bool:
        """True si c'est une action d'installation (install_*, setup_*, configure package manager)"""
        return self.id.startswith("install_") or "docker" in self.id.lower()
    
    def execution_type(self) -> str:
        """Retourne le type d'exécution: 'installation', 'configuration', 'hardening'"""
        if self.id.startswith("install_"):
            return "installation"
        elif any(x in self.id for x in ["harden", "setup_ssl", "setup_ufw"]):
            return "hardening"
        else:
            return "configuration"


# Catalogue d'actions
CONFIG_ACTIONS = [
    # WEB
    ConfigAction(
        id="install_nginx",
        label="Installer Nginx",
        category=ConfigCategory.WEB,
        keywords=["nginx", "web server", "serveur web"],
        description="Installe et démarre Nginx",
        params_schema={"port": int},
    ),
    ConfigAction(
        id="install_apache",
        label="Installer Apache",
        category=ConfigCategory.WEB,
        keywords=["apache", "apache2", "httpd"],
        description="Installe et démarre Apache",
        params_schema={"port": int},
    ),
    ConfigAction(
        id="install_docker",
        label="Installer Docker",
        category=ConfigCategory.CONTAINER,
        keywords=["docker", "containerize", "container"],
        description="Installe Docker et Docker Compose",
    ),
    
    # SECURITY
    ConfigAction(
        id="setup_ufw",
        label="Configurer UFW",
        category=ConfigCategory.SECURITY,
        keywords=["ufw", "firewall", "pare-feu"],
        description="Configure UFW et ouvre les ports essentiels",
    ),
    ConfigAction(
        id="harden_ssh",
        label="Durcir SSH",
        category=ConfigCategory.SECURITY,
        keywords=["ssh hardening", "ssh security", "renforcer ssh", "durcir ssh"],
        description="Désactive password auth, change port, etc.",
    ),
    ConfigAction(
        id="setup_ssl",
        label="Configurer SSL/TLS",
        category=ConfigCategory.SECURITY,
        keywords=["ssl", "tls", "certificate", "https"],
        description="Installe Certbot, génère certificat Let's Encrypt",
    ),
    
    # SYSTEM
    ConfigAction(
        id="update_os",
        label="Mettre à jour OS",
        category=ConfigCategory.SYSTEM,
        keywords=["update", "upgrade", "mise à jour", "mettre à jour"],
        description="apt update && apt upgrade",
    ),
    ConfigAction(
        id="install_git",
        label="Installer Git",
        category=ConfigCategory.SYSTEM,
        keywords=["git", "version control"],
        description="Installe Git",
    ),
    ConfigAction(
        id="install_nodejs",
        label="Installer Node.js",
        category=ConfigCategory.SYSTEM,
        keywords=["nodejs", "node.js", "npm", "node"],
        description="Installe Node.js et npm",
    ),
    
    # OBSERVABILITY
    ConfigAction(
        id="install_prometheus",
        label="Installer Prometheus",
        category=ConfigCategory.OBSERVABILITY,
        keywords=["prometheus", "monitoring"],
        description="Installe Prometheus pour la métrique",
    ),
    ConfigAction(
        id="install_grafana",
        label="Installer Grafana",
        category=ConfigCategory.OBSERVABILITY,
        keywords=["grafana", "dashboard", "visualization"],
        description="Installe Grafana pour les dashboards",
    ),
]


def normalize_text(text: str) -> str:
    """Normalise le texte: minuscules, supprime accents, ponctuation"""
    # Minuscules
    text = text.lower()
    
    # Enlever accents
    text = ''.join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    )
    
    # Enlever ponctuation
    text = re.sub(r'[^\w\s]', ' ', text)
    
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


def match_config_action(
    text: str,
    confidence_threshold: float = 0.5,
) -> Tuple[Optional[str], List[str], float, Dict[str, Any]]:
    """
    Détecte l'action configure à partir du texte.
    
    Returns:
        (action_id, recognized_keywords, confidence, debug_info)
        - action_id: ID de l'action si trouvée, None sinon
        - recognized_keywords: Keywords qui ont matchés
        - confidence: Score de confiance (0-1)
        - debug_info: Dict avec détails du matching
    
    """
    normalized = normalize_text(text)
    words = normalized.split()
    
    debug = {
        "normalized_text": normalized,
        "words": words,
        "candidates": [],
    }
    
    # Scorer chaque action
    scores = []
    for action in CONFIG_ACTIONS:
        matched_keywords = []
        score = 0
        
        # Matcher keywords (exact et substring)
        for keyword in action.keywords:
            keyword_normalized = normalize_text(keyword)
            
            # Match exact d'un mot
            if keyword_normalized in words:
                matched_keywords.append(keyword)
                score += 1
            # Match substring dans le texte
            elif keyword_normalized in normalized:
                matched_keywords.append(keyword)
                score += 0.7
        
        if score > 0:
            confidence = min(1.0, score / len(action.keywords))
            scores.append({
                "action": action,
                "score": score,
                "confidence": confidence,
                "matched_keywords": matched_keywords,
            })
            debug["candidates"].append({
                "id": action.id,
                "score": score,
                "confidence": confidence,
            })
    
    # Pas de match
    if not scores:
        return None, [], 0.0, debug
    
    # Sort par score
    scores.sort(key=lambda x: x["score"], reverse=True)
    
    best = scores[0]
    
    # Ambiguïté: 2+ actions avec score similaire (dans 20%)
    top_score = best["score"]
    ambiguous_candidates = [
        s for s in scores
        if s["score"] >= top_score * 0.8
    ]
    
    if len(ambiguous_candidates) > 1:
        # Retourner le meilleur mais noter l'ambiguïté
        debug["ambiguous"] = [
            {"id": c["action"].id, "label": c["action"].label, "score": c["score"]}
            for c in ambiguous_candidates[1:]
        ]
    
    return (
        best["action"].id,
        best["matched_keywords"],
        best["confidence"],
        debug,
    )


def get_action_by_id(action_id: str) -> Optional[ConfigAction]:
    """Récupère une action par son ID"""
    for action in CONFIG_ACTIONS:
        if action.id == action_id:
            return action
    return None


def get_categories() -> Dict[str, List[ConfigAction]]:
    """Retourne les actions groupées par catégorie"""
    result = {cat.value: [] for cat in ConfigCategory}
    for action in CONFIG_ACTIONS:
        result[action.category.value].append(action)
    return result


def get_suggested_actions(limit: int = 6) -> List[ConfigAction]:
    """Retourne une liste de suggestions (pour la première question)"""
    # Une par catégorie, limit max
    suggested = []
    seen_cats = set()
    
    # Prioriser les actions populaires
    for action in CONFIG_ACTIONS:
        if len(suggested) >= limit:
            break
        if action.category.value not in seen_cats:
            suggested.append(action)
            seen_cats.add(action.category.value)
    
    # Si moins de limit, ajouter d'autres
    for action in CONFIG_ACTIONS:
        if len(suggested) >= limit:
            break
        if action not in suggested:
            suggested.append(action)
    
    return suggested[:limit]
