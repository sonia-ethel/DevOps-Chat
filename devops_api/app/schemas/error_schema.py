# © 2024–2026 TOURE Arnaud Patrick
# Licensed under the MIT License

"""
Structured Error Response - Erreurs actionnables et debuggables
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class ErrorResponse:
    """Erreur structurée, claire et actionnelle"""
    error_code: str  # ACTION_NOT_FOUND, ACTION_AMBIGUOUS, NO_TARGETS, SSM_UNAVAILABLE, ANSIBLE_FAILED, etc.
    error_message: str  # Message clair pour l'utilisateur
    details: Optional[Dict[str, Any]] = None  # Détails techniques optionnels
    user_action: Optional[str] = None  # Ce que l'utilisateur peut faire
    
    def to_dict(self):
        return {
            "error_code": self.error_code,
            "error_message": self.error_message,
            "details": self.details or {},
            "user_action": self.user_action,
        }


# Codes d'erreur standardisés
ERROR_CODES = {
    "ACTION_NOT_FOUND": "L'action n'a pas été reconnue.",
    "ACTION_AMBIGUOUS": "Plusieurs actions correspondent. Précise laquelle.",
    "NO_TARGETS": "Aucune cible (instance) sélectionnée.",
    "NO_INSTANCES_AVAILABLE": "Aucune instance AWS disponible.",
    "SSM_UNAVAILABLE": "SSM n'est pas disponible sur les instances.",
    "SSM_FAILED": "Échec de la communication SSM avec les instances.",
    "ANSIBLE_FAILED": "L'exécution Ansible a échoué.",
    "CREDENTIALS_MISSING": "Les credentials AWS manquent.",
    "SYNTAX_ERROR": "La commande n'a pas la bonne syntaxe.",
    "UNKNOWN_ERROR": "Une erreur inattendue s'est produite.",
}


def make_error(
    error_code: str,
    user_action: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> ErrorResponse:
    """Factory pour créer une ErrorResponse avec le bon message"""
    message = ERROR_CODES.get(error_code, ERROR_CODES["UNKNOWN_ERROR"])
    return ErrorResponse(
        error_code=error_code,
        error_message=message,
        details=details,
        user_action=user_action,
    )
