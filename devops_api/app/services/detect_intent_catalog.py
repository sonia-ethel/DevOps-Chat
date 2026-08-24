# © 2024–2026 TOURE Arnaud Patrick
# Licensed under the MIT License

"""
Enhanced Intent Detection - intègre le catalogue configure
"""

import logging
import re
from typing import Optional
from app.schemas.intent_schema import DetectedIntent
from app.services.config_catalog import match_config_action, get_action_by_id

logger = logging.getLogger(__name__)


def detect_intent_with_catalog(text: str, last_action_id: Optional[str] = None) -> DetectedIntent:
    """
    Détecte l'intent (create/configure/audit/monitoring/free_chat) + action si applicable.
    
    Args:
        text: Message utilisateur
        last_action_id: ID de l'action précédente (pour contexte)
    
    Returns:
        DetectedIntent avec tous les détails
    """
    text_lower = text.lower().strip()
    
    # Détection intent primaire
    create_keywords = [
        "créer", "crée", "creer", "créé",
        "create", "creation", "création",
        "provisionner", "provision",
        "déployer", "deployer", "déploie", "deploie",
        "lancer"
    ]

    if any(kw in text_lower for kw in create_keywords):
        return DetectedIntent(
            intent_type="create",
            confidence=0.9,
            recognized_keywords=["create"],
        )
    
    if any(kw in text_lower for kw in ["audit", "vérif", "check", "status", "statut"]):
        return DetectedIntent(
            intent_type="audit",
            confidence=0.9,
            recognized_keywords=["audit"],
        )
    
    if any(kw in text_lower for kw in ["monitoring", "monitor", "observe", "metrics", "métriques"]):
        return DetectedIntent(
            intent_type="monitoring",
            confidence=0.9,
            recognized_keywords=["monitoring"],
        )
    
    # CONFIGURE: possiblement le cas le plus complexe
    if any(kw in text_lower for kw in ["configure", "configurer", "setup", "installer", "install"]):
        # Essayer de matcher une action spécifique
        action_id, keywords, confidence, debug = match_config_action(text)
        
        intent = DetectedIntent(
            intent_type="configure",
            action_id=action_id,
            confidence=confidence if action_id else 0.5,  # Action non trouvée = confiance faible
            recognized_keywords=["configure"] + keywords,
            debug=debug,
        )
        
        # Si ambiguous, ajouter les candidates
        if debug.get("ambiguous"):
            intent.action_candidates = debug["ambiguous"]
        
        return intent
    
    # Par défaut: free_chat
    return DetectedIntent(
        intent_type="free_chat",
        confidence=0.0,
        recognized_keywords=[],
    )
