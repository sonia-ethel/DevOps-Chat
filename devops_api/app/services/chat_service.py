# © 2024–2026 TOURE Arnaud Patrick
# Licensed under the MIT License

import logging
import re

from app.paths import LOGS_DIR
logger = logging.getLogger(__name__)

import os
import json
import logging
from app.services.gpt_service import (
    generate_instructions_from_gpt,
    generate_free_chat_completion
)

#  Répertoire des logs
BASE_LOG_DIR = LOGS_DIR
os.makedirs(BASE_LOG_DIR, exist_ok=True)
LOG_FILE_PATH = os.path.join(BASE_LOG_DIR, "chat_service.log")

#  Création du logger
logger = logging.getLogger("chat_service")
logger.setLevel(logging.INFO)

#  Évite les handlers en double
if not logger.hasHandlers():
    handler = logging.FileHandler(LOG_FILE_PATH)
    formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

#  Safe JSON loader for GPT responses
def safe_json_loads(text: str) -> dict:
    """
    Safely parse JSON from GPT responses.
    Handles markdown formatting, json prefix, and other common issues.
    """
    try:
        cleaned = text.strip()
        # Remove markdown code blocks
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        # Remove "json" prefix if present
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
        # Extract JSON object {...}
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("no_json_object_found")
        return json.loads(cleaned[start:end+1])
    except Exception as e:
        logger.error(f"Failed to parse JSON: {e}, text was: {text[:200]}")
        raise ValueError(f"JSON parsing failed: {e}")

#  Import du nouveau détecteur minimal Ubuntu
from app.services.intent_detector import detect_ubuntu_creation_intent, detect_service_configuration_intent

#  Détection complète d'intention avec extraction contextuelle
async def detect_intent_and_action(request_text: str) -> dict:
    """
    Analyse le prompt utilisateur pour détecter l'intention DevOps ET extraire tous les paramètres disponibles.
     PRIORITÉ V0: Détection ultra-fiable pour Ubuntu sur AWS
    Si GPT échoue ou timeout, utilise une logique de fallback.
    """
    
    #  PRIORITÉ V0: Détection spécialisée Ubuntu avant tout le reste
    logger.info(f" Testing Ubuntu detection for: '{request_text}'")
    
    try:
        ubuntu_intent = detect_ubuntu_creation_intent(request_text)
        logger.info(f" Ubuntu detection result: {ubuntu_intent}")
        
        if ubuntu_intent["action"] == "create_ubuntu":
            logger.info(f" V0 Fast Track - Ubuntu détecté: {ubuntu_intent}")
            return {
                "action": "create",  # Mapped vers le système existant
                "description": ubuntu_intent["description"],
                "extracted_params": ubuntu_intent["extracted_params"], 
                "missing_params": [],
                "ubuntu_detected": True,  # Flag pour traitement spécial
                "confidence_score": ubuntu_intent.get("confidence_score", 0.8)
            }
    except Exception as e:
        logger.error(f" Erreur détection Ubuntu: {e}")
    
    #  Détection spécialisée des configurations de service
    logger.info(f" Testing service configuration detection for: '{request_text}'")
    
    try:
        service_intent = detect_service_configuration_intent(request_text)
        logger.info(f" Service detection result: {service_intent}")
        
        if service_intent["action"] == "configure" and service_intent["service_detected"]:
            logger.info(f" Service Fast Track - Configuration détectée: {service_intent}")
            return {
                "action": "configure",
                "description": service_intent["description"],
                "extracted_params": service_intent["extracted_params"],
                "missing_params": ["instance_selection"],  # Force la sélection d'instance
                "service_detected": True,
                "service_name": service_intent["service"],
                "confidence_score": 0.9 if service_intent["confidence"] == "high" else 0.7
            }
    except Exception as e:
        logger.error(f" Erreur détection service: {e}")
        # Continue avec GPT fallback
    
    #  Si pas Ubuntu, continuer avec la détection GPT normale
    #  IMPORTANT: GPT call has timeout of 10s; if it fails, we use fallback
    prompt = (
        "Tu es un assistant DevOps intelligent.\n"
        "Ta mission est d'analyser une demande utilisateur et d'extraire TOUTES les informations disponibles.\n\n"
        "Tu dois répondre UNIQUEMENT avec un JSON structuré comme :\n"
        "{\n"
        "  \"action\": \"create | configure | audit | kubernetes\",\n"
        "  \"description\": \"Phrase courte qui résume ce que l'utilisateur veut faire\",\n"
        "  \"extracted_params\": {\n"
        "    \"provider\": \"aws|azure|gcp\" (si mentionné),\n"
        "    \"os\": \"ubuntu|centos|debian|windows\" (si mentionné),\n"
        "    \"instance_type\": \"t3.micro|t2.small|etc\" (si mentionné),\n"
        "    \"region\": \"eu-west-1|us-east-1|etc\" (si mentionné),\n"
        "    \"services\": [\"nginx\", \"docker\", \"mysql\"] (si mentionné),\n"
        "    \"audit_tool\": \"lynis|auditd\" (si mentionné)\n"
        "  },\n"
        "  \"missing_params\": [\"liste des paramètres manquants essentiels\"]\n"
        "}\n\n"
        "IMPORTANT: Extrais TOUS les paramètres mentionnés explicitement.\n"
        "Exemples:\n"
        "- \"Je veux une instance ubuntu aws\" -> provider: \"aws\", os: \"ubuntu\"\n"
        "- \"Crée une VM t3.micro en eu-west-1\" -> instance_type: \"t3.micro\", region: \"eu-west-1\"\n"
        "- \"Installe nginx et docker\" -> services: [\"nginx\", \"docker\"]\n\n"
        f"Texte de l'utilisateur : {request_text}"
    )

    try:
        # Call GPT with timeout protection (10s)
        gpt_response = await generate_instructions_from_gpt(prompt)
        gpt_response_limited = gpt_response.strip()[:2000]

        logger.info("Request: %s", request_text)
        logger.info("GPT Response: %s", gpt_response_limited)

        # Use safe JSON loader to handle markdown, json prefix, etc.
        try:
            parsed = safe_json_loads(gpt_response)
        except Exception as e:
            logger.error(f" GPT JSON parsing failed: {e}, using fallback")
            raise ValueError(f"GPT intent parsing failed: {e}")

        if "action" not in parsed or "description" not in parsed:
            raise ValueError("Champs manquants")

        parsed_normalized = {
            "action": parsed["action"].lower().strip(),
            "description": parsed["description"].strip(),
            "extracted_params": parsed.get("extracted_params", {}),
            "missing_params": parsed.get("missing_params", [])
        }

        # Normalize extracted params
        if not isinstance(parsed_normalized["extracted_params"], dict):
            parsed_normalized["extracted_params"] = {}
        if not isinstance(parsed_normalized["missing_params"], list):
            parsed_normalized["missing_params"] = []

        #  Protection contre le cas "unknown"
        if parsed_normalized["action"] not in ["create", "configure", "audit", "kubernetes"]:
            parsed_normalized["action"] = "none"

        logger.info(" Intent détecté: %s", json.dumps(parsed_normalized, ensure_ascii=False))
        return parsed_normalized

    except Exception as e:
        #  GPT failed (timeout, parsing error, etc) - use FAST FALLBACK
        logger.warning(f" GPT Failed ({type(e).__name__}), using fast fallback: {str(e)[:100]}")
        
        # Fast heuristic detection - NO async calls, NO timeouts
        text_lower = request_text.lower()
        
        # Detect intent from keywords
        if any(word in text_lower for word in ["créer", "crée", "create", "déployer", "deploy", "lancer", "instance", "vm", "machine"]):
            action = "create"
            description = "Créer une instance cloud"
        elif any(word in text_lower for word in ["installer", "install", "configurer", "configure", "setup", "nginx", "docker", "mysql", "apache", "httpd"]):
            action = "configure"
            description = "Configurer un service ou une application"
        elif any(word in text_lower for word in ["audit", "audit de sécurité", "lynis", "scan", "security", "scanner"]):
            action = "audit"
            description = "Faire un audit de sécurité"
        elif any(word in text_lower for word in ["kubernetes", "k8s", "helm", "deploy cluster"]):
            action = "kubernetes"
            description = "Gérer Kubernetes"
        else:
            action = "none"
            description = "Intention non claire détectée (fallback GPT timeout)"
        
        # Fast param extraction
        extracted_params = {}
        if "aws" in text_lower:
            extracted_params["provider"] = "aws"
        elif "azure" in text_lower:
            extracted_params["provider"] = "azure"
        elif "gcp" in text_lower or "google" in text_lower:
            extracted_params["provider"] = "gcp"
        
        if "ubuntu" in text_lower:
            extracted_params["os"] = "ubuntu"
        elif "centos" in text_lower:
            extracted_params["os"] = "centos"
        elif "debian" in text_lower:
            extracted_params["os"] = "debian"
        
        logger.info(f" Fast Fallback: action={action}, params={extracted_params}")
        
        return {
            "action": action,
            "description": description,
            "extracted_params": extracted_params,
            "missing_params": [],
            "fallback": True  # Flag indicating we used fallback
        }

#  Réponse libre avec GPT
async def generate_free_chat_response(request_text: str = None, user_message: str = None, context: str = None) -> str:
    """
    Utilise GPT pour répondre librement à une question ou un échange conversationnel.
    Paramètres compatibles: request_text (legacy) ou user_message + context (nouveau)
    """
    # Support des deux signatures pour rétrocompatibilité
    question = user_message or request_text or "Question vide"
    
    # Construction du prompt avec contexte optionnel
    prompt_parts = [
        "Tu es un assistant DevOps expérimenté et sympathique.",
        "IMPORTANT : Réponds TOUJOURS en français, peu importe la langue de la question.",
        "Réponds clairement et de façon concise à la question suivante.",
        "Si la question concerne DevOps, donne une réponse technique.",
        "Si la question est générale, réponds poliment.\n"
    ]
    
    if context:
        prompt_parts.append(f"Contexte de la session : {context}\n")
    
    prompt_parts.append(f"Question utilisateur : {question}\n\nRéponse (en français) :")
    
    prompt = "\n".join(prompt_parts)

    response = await generate_free_chat_completion(prompt)
    response_limited = response.strip()[:1500]

    logger.info("Free chat request: %s", question)
    logger.info("Free chat response: %s", response_limited)

    return response_limited

#  Extraction de paramètres basée sur des mots-clés (fallback)
def extract_params_from_text(request_text: str) -> dict:
    """
    Extraction manuelle de paramètres à partir du texte utilisateur (fallback).
    """
    text = request_text.lower()
    params = {}
    
    # Provider detection
    if any(kw in text for kw in ["aws", "amazon"]):
        params["provider"] = "aws"
    elif any(kw in text for kw in ["azure", "microsoft"]):
        params["provider"] = "azure"
    elif any(kw in text for kw in ["gcp", "google"]):
        params["provider"] = "gcp"
    
    # OS detection
    if "ubuntu" in text:
        params["os"] = "ubuntu"
    elif "centos" in text:
        params["os"] = "centos"
    elif "debian" in text:
        params["os"] = "debian"
    elif "windows" in text:
        params["os"] = "windows"
    
    # Instance type detection
    import re
    instance_match = re.search(r't[0-9]+\.[a-z]+', text)
    if instance_match:
        params["instance_type"] = instance_match.group()
    
    # Region detection
    region_match = re.search(r'(eu|us|ap)-[a-z]+-[0-9]+', text)
    if region_match:
        params["region"] = region_match.group()
    
    # Services detection
    services = []
    service_keywords = ["nginx", "apache", "docker", "mysql", "postgresql", "redis", "mongodb"]
    for service in service_keywords:
        if service in text:
            services.append(service)
    if services:
        params["services"] = services
    
    # Audit tool detection
    if "lynis" in text:
        params["audit_tool"] = "lynis"
    elif "auditd" in text:
        params["audit_tool"] = "auditd"
    
    return params

#  Détection rapide fallback par mots-clés
def detect_intent_type(request_text: str) -> str:
    """
    Détection rapide et manuelle d’intention basée sur des mots-clés.
    """
    text = request_text.lower()

    if any(kw in text for kw in [
        "créer", "creer", "création", "déployer", "deploie", "lancer", "déploie",
        "vm", "instance", "serveur", "machine", "ubuntu", "aws", "vps",
        "nouvelle", "nouveau"  # Ajout pour couvrir plus de cas
    ]):
        return "create"

    elif any(kw in text for kw in [
        "configurer", "installer", "setup", "mettre à jour", "activer",
        "nginx", "mysql", "apache", "docker", "ufw", "ssh", "firewall"
    ]):
        return "configure"

    elif any(kw in text for kw in [
        "auditer", "vérifier", "scanner", "audit", "sécurité", "securite", 
        "hardening", "vulnérabilités", "vulnerabilites", "scan de sécurité"
    ]):
        return "audit"

    elif any(kw in text for kw in [
        "monitoring", "métriques", "metriques", "dashboard", "surveiller",
        "cpu", "mémoire", "memoire", "disque", "performances", "stats",
        "charge", "load", "uptime", "monitoring"
    ]):
        return "monitoring"

    elif any(kw in text for kw in [
        "kubernetes", "k8s", "pod", "cluster", "deployment", "namespace", "helm"
    ]):
        return "kubernetes"

    else:
        return "unknown"
