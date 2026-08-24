# app/services/intent_detector.py

import re
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class SimpleIntentDetector:
    """
    Détecteur d'intentions minimal et fiable basé sur des patterns regex.
    Commencer par l'intention la plus fréquente : créer instance Ubuntu.
    """
    
    # Patterns pour détecter la création d'instances Ubuntu
    UBUNTU_CREATION_PATTERNS = [
        # Formes avec verbes de création + ubuntu
        r'(?:créer?|creer|créé|faire|lance[rz]?|déploy|provision)\s+.*ubuntu',
        r'(?:créer?|creer|créé|faire|lance[rz]?|déploy|provision)\s+.*(?:instance|vm|machine|serveur)\s+.*ubuntu',
        
        # Formes avec déterminant + instance/vm + ubuntu
        r'(?:une?|des?)\s+(?:instance|vm|machine|serveur)\s+.*ubuntu',
        r'(?:une?|des?)\s+(?:nouvelle?|nouveau)\s+.*ubuntu',
        
        # Ubuntu en premier avec spécifications
        r'ubuntu\s+(?:instance|vm|machine|serveur)',
        r'ubuntu\s+t[0-9]+\.[a-z]+',  # Ubuntu + type d'instance
        
        # Formes directes
        r'(?:instance|vm|machine|serveur)\s+ubuntu',
        r'(?:nouvelle?|nouveau)\s+ubuntu',
        
        # Avec des mots clés de déploiement
        r'(?:veux|voudrai[st]?|souhaite|besoin)\s+.*ubuntu',
    ]
    
    # Patterns pour extraire les providers
    PROVIDER_PATTERNS = {
        'aws': [r'\baws\b', r'\bamazon\b'],
        'azure': [r'\bazure\b', r'\bmicrosoft\b'],
        'gcp': [r'\bgcp\b', r'\bgoogle\b', r'\bcloud\b.*google']
    }
    
    # Patterns pour types d'instances AWS
    INSTANCE_TYPE_PATTERN = r'\bt[0-9]+\.[a-z]+\b'
    
    # Patterns pour régions AWS
    REGION_PATTERN = r'\b(?:eu|us|ap|ca|sa)-[a-z]+-[0-9]+\b'

    def detect_ubuntu_creation(self, text: str) -> bool:
        """
        Détecte l'intention de créer une instance Ubuntu.
        
        Args:
            text: Le texte utilisateur à analyser
            
        Returns:
            bool: True si l'intention Ubuntu est détectée
        """
        if not text or not text.strip():
            return False
            
        # Normalisation du texte
        text_clean = text.lower().strip()
        
        # Vérification de la présence d'Ubuntu
        if 'ubuntu' not in text_clean:
            return False
        
        # Test des patterns de création Ubuntu
        for pattern in self.UBUNTU_CREATION_PATTERNS:
            if re.search(pattern, text_clean, re.IGNORECASE):
                logger.info(f" Ubuntu creation detected with pattern: {pattern}")
                return True
        
        # Pattern fallback : si ubuntu + mots-clés de création dans la même phrase
        # Exclusions pour éviter les faux positifs
        exclusion_words = ['comment', 'installer', 'pourquoi', 'est', 'bon', 'préfère']
        if any(word in text_clean for word in exclusion_words):
            return False
            
        creation_words = [
            'créer', 'creer', 'création', 'faire', 'lancer', 'déployer', 
            'provision', 'instance', 'vm', 'machine', 'serveur'
        ]
        
        if any(word in text_clean for word in creation_words):
            logger.info(" Ubuntu creation detected via fallback (ubuntu + creation keywords)")
            return True
            
        return False
    
    def extract_ubuntu_params(self, text: str) -> Dict:
        """
        Extrait les paramètres spécifiques à la création d'instance Ubuntu.
        
        Args:
            text: Le texte utilisateur à analyser
            
        Returns:
            Dict: Paramètres extraits (provider, instance_type, region, etc.)
        """
        params = {
            "os": "ubuntu",  # Fixe pour cette intention
            "action": "create_ubuntu"
        }
        
        text_clean = text.lower().strip()
        
        # Extraction du provider
        for provider, patterns in self.PROVIDER_PATTERNS.items():
            if any(re.search(pattern, text_clean) for pattern in patterns):
                params["provider"] = provider
                logger.info(f" Provider détecté: {provider}")
                break
        
        # Extraction du type d'instance
        instance_match = re.search(self.INSTANCE_TYPE_PATTERN, text_clean)
        if instance_match:
            params["instance_type"] = instance_match.group()
            logger.info(f" Instance type détecté: {params['instance_type']}")
        
        # Extraction de la région
        region_match = re.search(self.REGION_PATTERN, text_clean)
        if region_match:
            params["region"] = region_match.group()
            logger.info(f" Région détectée: {params['region']}")
        
        # Extraction de tags/noms si présents
        name_patterns = [
            r'nom[mé]?\s*[:\s]\s*([a-zA-Z0-9\-_]+)',
            r'appel[lé]?\s*[:\s]\s*([a-zA-Z0-9\-_]+)',
            r'tag\s*[:\s]\s*([a-zA-Z0-9\-_]+)'
        ]
        
        for pattern in name_patterns:
            name_match = re.search(pattern, text_clean)
            if name_match:
                params["name"] = name_match.group(1)
                logger.info(f" Nom détecté: {params['name']}")
                break
        
        return params

    def detect_service_configuration(self, text: str) -> Dict:
        """
        Détecte l'intention de configurer/installer un service (nginx, docker, etc.)
        """
        text_clean = text.lower().strip()
        
        # Services supportés avec leurs patterns
        SERVICES = {
            'nginx': ['nginx', 'web server', 'reverse proxy'],
            'docker': ['docker', 'container', 'conteneur'],
            'mysql': ['mysql', 'mariadb', 'database'],
            'apache': ['apache', 'httpd'],
            'ssh': ['ssh', 'openssh'],
            'ufw': ['ufw', 'firewall'],
            'fail2ban': ['fail2ban'],
        }
        
        # Verbes de configuration
        CONFIG_VERBS = [
            'configurer', 'installer', 'setup', 'mettre en place',
            'activer', 'déployer', 'install', 'config', 'configure'
        ]
        
        detected_service = None
        detected_verb = None
        
        # Détecter le service
        for service, patterns in SERVICES.items():
            if any(pattern in text_clean for pattern in patterns):
                detected_service = service
                break
        
        # Détecter le verbe d'action
        for verb in CONFIG_VERBS:
            if verb in text_clean:
                detected_verb = verb
                break
        
        if detected_service:
            return {
                "action": "configure_service",
                "service": detected_service,
                "verb": detected_verb or "configurer",
                "confidence": "high" if detected_verb else "medium"
            }
        
        return {"action": "unknown"}
    
    def get_confidence_score(self, text: str) -> float:
        """
        Calcule un score de confiance pour la détection Ubuntu.
        
        Args:
            text: Le texte à analyser
            
        Returns:
            float: Score entre 0.0 et 1.0
        """
        if not self.detect_ubuntu_creation(text):
            return 0.0
        
        text_clean = text.lower().strip()
        score = 0.5  # Base score si détection positive
        
        # Bonus pour mots-clés explicites
        explicit_keywords = ['créer', 'nouvelle', 'instance', 'vm', 'déployer']
        for keyword in explicit_keywords:
            if keyword in text_clean:
                score += 0.1
        
        # Bonus pour provider spécifié
        if any(any(re.search(pattern, text_clean) for pattern in patterns) 
               for patterns in self.PROVIDER_PATTERNS.values()):
            score += 0.2
        
        # Bonus pour spécifications techniques
        if re.search(self.INSTANCE_TYPE_PATTERN, text_clean):
            score += 0.1
        
        if re.search(self.REGION_PATTERN, text_clean):
            score += 0.1
        
        return min(score, 1.0)


# Instance globale pour utilisation dans l'application
ubuntu_detector = SimpleIntentDetector()


def detect_service_configuration_intent(text: str) -> Dict:
    """
    Fonction utilitaire pour détecter l'intention de configuration de service.
    """
    detector = ubuntu_detector
    
    service_result = detector.detect_service_configuration(text)
    
    if service_result["action"] == "configure_service":
        return {
            "action": "configure",  # Mapped vers le système existant
            "service_detected": True,
            "service": service_result["service"],
            "verb": service_result["verb"],
            "confidence": service_result["confidence"],
            "description": f"Configuration de {service_result['service']} détectée",
            "extracted_params": {
                "service": service_result["service"],
                "action_type": "install_configure"
            }
        }
    
    return {
        "action": "unknown",
        "service_detected": False,
        "description": "Aucune configuration de service détectée"
    }


def detect_ubuntu_creation_intent(text: str) -> Dict:
    """
    Fonction utilitaire pour détecter l'intention de création Ubuntu.
    
    Args:
        text: Le texte utilisateur
        
    Returns:
        Dict: Résultat de la détection avec action, confiance et paramètres
    """
    detector = ubuntu_detector
    
    if detector.detect_ubuntu_creation(text):
        extracted_params = detector.extract_ubuntu_params(text)
        confidence = detector.get_confidence_score(text)
        
        return {
            "action": "create_ubuntu",
            "confidence": "high" if confidence > 0.7 else "medium",
            "confidence_score": confidence,
            "extracted_params": extracted_params,
            "description": f"Création d'une instance Ubuntu (confiance: {confidence:.2f})"
        }
    
    return {
        "action": "unknown", 
        "confidence": "none",
        "confidence_score": 0.0,
        "extracted_params": {},
        "description": "Aucune intention Ubuntu détectée"
    }