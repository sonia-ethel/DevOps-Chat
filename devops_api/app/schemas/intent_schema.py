# © 2024–2026 TOURE Arnaud Patrick
# Licensed under the MIT License

"""
Intent Detection - Nouvelle structure unifiée
Retourne des détails complets, pas seulement le type d'intent.
"""

from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any


@dataclass
class DetectedIntent:
    """Résultat unifié de détection d'intent"""
    intent_type: str  # "create", "configure", "audit", "monitoring", "free_chat"
    
    action_id: Optional[str] = None  # Pour configure: "install_nginx", etc.
    action_candidates: Optional[List[Dict[str, Any]]] = None  # Si ambigu
    
    confidence: float = 0.0  # 0-1
    recognized_keywords: List[str] = None  # Keywords détectés
    
    params: Optional[Dict[str, Any]] = None  # Paramètres détectés (ex: port)
    debug: Optional[Dict[str, Any]] = None  # Info debug
    
    def __post_init__(self):
        if self.recognized_keywords is None:
            self.recognized_keywords = []
        if self.params is None:
            self.params = {}
    
    def to_dict(self):
        return asdict(self)
    
    def is_ambiguous(self) -> bool:
        """True si plusieurs candidates possibles"""
        return bool(self.action_candidates and len(self.action_candidates) > 1)
    
    def is_complete(self) -> bool:
        """True si intent complet et prêt à exécuter"""
        if self.intent_type == "configure":
            return bool(self.action_id)  # Besoin d'une action pour configure
        elif self.intent_type in ["create", "audit", "monitoring"]:
            return True  # Ont besoin de sélection VM, pas de détails supplémentaires
        return True
