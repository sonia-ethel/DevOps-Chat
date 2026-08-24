# © 2024–2026 TOURE Arnaud Patrick
# Licensed under the MIT License

# app/services/gpt_service.py
import logging
import os
import json
import time
import random
import threading
from typing import Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

from openai import OpenAI, APIConnectionError, RateLimitError, BadRequestError
from app.env import load_app_env

logger = logging.getLogger(__name__)
load_app_env()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AI_PROVIDER = (os.getenv("DAC_AI_PROVIDER") or ("openai" if OPENAI_API_KEY else "mock")).lower()

# Client OpenAI (sync). En mode CodeCamp, le backend doit pouvoir demarrer sans cle IA.
client = OpenAI(api_key=OPENAI_API_KEY) if AI_PROVIDER == "openai" and OPENAI_API_KEY else None

# Modele configurable. DAC_AI_MODEL est le nom expose dans le rendu CodeCamp.
_DEFAULT_MODEL = os.getenv("DAC_AI_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"


def _mock_response(messages: list[dict], response_format: Optional[Dict[str, Any]] = None) -> str:
    if response_format:
        return json.dumps({
            "intent": "unknown",
            "runtime": "system",
            "details": "Mode IA mock actif: detection par fallback applicatif.",
        })

    system_message = next((m.get("content", "") for m in messages if m.get("role") == "system"), "")
    last_user = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")
    if "convertis des demandes" in system_message:
        raise RuntimeError("Mode IA mock actif: generation IA indisponible sans cle OpenAI.")

    if "Réponse (en français)" in last_user or "répond naturellement" in system_message:
        return (
            "Mode IA mock actif: aucune cle OpenAI n'est configuree. "
            "Je peux aider a lancer DAC, mais les reponses IA avancees necessitent DAC_AI_PROVIDER=openai."
        )

    return (
        "Mode IA mock actif: aucune cle OpenAI n'est configuree. "
        "Configure DAC_AI_PROVIDER=openai et OPENAI_API_KEY pour activer les reponses IA."
    )


# -----------------------
# Helpers
# -----------------------
def _strip_code_fences(s: str) -> str:
    """Supprime les fences Markdown éventuels (```hcl, ```yaml, ```terraform, ```yml, ```)."""
    if not s:
        return s
    s = s.strip()
    if s.startswith("```"):
        # Enlève les entêtes courants
        s = (
            s.replace("```hcl", "")
             .replace("```terraform", "")
             .replace("```yaml", "")
             .replace("```yml", "")
             .replace("```", "")
             .strip()
        )
    return s


def _chat_with_retry(messages: list[dict], model: Optional[str] = None,
                     temperature: float = 0.2,
                     response_format: Optional[Dict[str, Any]] = None,
                     max_retries: int = 4,
                     timeout_seconds: int = 10) -> str:
    """
    Appelle l'API Chat Completions avec repli exponentiel ET timeout.
    
    Args:
        timeout_seconds: Timeout global pour chaque tentative (défaut 10s)
    
    Retourne le .content (str).
    Si timeout ou erreur, fallback à une réponse minimale plutôt que de hang.
    """
    model = model or _DEFAULT_MODEL
    last_err = None

    if AI_PROVIDER != "openai" or client is None:
        return _mock_response(messages, response_format=response_format)
    
    def _make_openai_call():
        """Wrapper pour appel OpenAI (appelé via ThreadPoolExecutor)."""
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if response_format:
            kwargs["response_format"] = response_format
        
        completion = client.chat.completions.create(**kwargs)
        content = completion.choices[0].message.content or ""
        return content.strip()
    
    for attempt in range(1, max_retries + 1):
        try:
            # Exécute l'appel OpenAI dans un thread avec timeout
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_make_openai_call)
                content = future.result(timeout=timeout_seconds)
                return content
            
        except FuturesTimeoutError:
            last_err = f"OpenAI timeout ({timeout_seconds}s)"
            logger.warning(f" OpenAI timeout, retry {attempt}/{max_retries}")
            if attempt < max_retries:
                delay = min(2 ** attempt + random.random(), 10)
                time.sleep(delay)
            # Après le dernier timeout, on sort
            
        except (RateLimitError, APIConnectionError) as e:
            last_err = e
            # backoff exponentiel jitter
            delay = min(2 ** attempt + random.random(), 20)
            logger.warning(f"OpenAI transient error ({type(e).__name__}), retry {attempt}/{max_retries} in {delay:.1f}s")
            time.sleep(delay)
            
        except BadRequestError as e:
            # Prompt non valide / réponse trop longue / format impossible, on log et on remonte
            logger.error(f"OpenAI bad request: {e}")
            raise
            
        except Exception as e:
            last_err = e
            logger.error(f"OpenAI unexpected error: {e}", exc_info=True)
            break
    
    # Si on est ici, tous les retries ont échoué
    raise RuntimeError(f"Echec d'appel OpenAI après {max_retries} tentatives: {last_err}")


# -----------------------
# Public API
# -----------------------
async def generate_instructions_from_gpt(prompt: str) -> str:
    """
    Envoie une requête au modèle (par défaut gpt-4o) pour générer du code/texte structuré.
     Cette fonction NE rajoute PAS de guidage sur le format (HCL/YAML) — c'est au caller de le préciser.
    On nettoie simplement les code fences éventuels.
    """
    messages = [
        {
            "role": "system",
            "content": (
                "Tu es un assistant DevOps. Tu convertis des demandes en langage naturel "
                "en instructions **strictement conformes** aux contraintes précisées dans le prompt utilisateur. "
                "N'ajoute jamais d'explications si le prompt exige un format strict (ex: HCL/YAML pur). "
                "Réponds en français."
            ),
        },
        {"role": "user", "content": prompt},
    ]

    content = _chat_with_retry(messages, model=_DEFAULT_MODEL, temperature=0.2)
    return _strip_code_fences(content)


async def analyze_intent(request_text: str) -> dict:
    """
    Détecte l'intention ET le runtime (system|docker) au format JSON strict.
    Utilise response_format=json_object pour fiabiliser le parsing.
    Fallback : retourne un JSON minimal 'unknown' si parsing impossible.
    """
    schema_hint = (
        "Tu dois retourner un JSON STRICT au format :\n"
        "{\n"
        '  "intent": "create|configure|audit|kubernetes|unknown",\n'
        '  "runtime": "system|docker",\n'
        '  "details": "<résumé court>"\n'
        "}\n\n"
        "Règles runtime :\n"
        "- system : installation/config sur l'OS (apt/dnf, systemctl, firewall, ssh...)\n"
        "- docker : si la demande mentionne docker/conteneur/compose/image\n"
        "Si ambigu : intent=unknown, runtime=system.\n"
    )

    messages = [
        {"role": "system", "content": "Tu es un assistant DevOps expert en analyse d'intention. Réponds en JSON strict."},
        {
            "role": "user",
            "content": f"{schema_hint}\nTexte de l'utilisateur : {request_text}",
        },
    ]

    try:
        content = _chat_with_retry(
            messages,
            model=_DEFAULT_MODEL,
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        result = json.loads(content)
    except Exception as e:
        logger.warning(f"analyze_intent: JSON parsing failed, using fallback. err={e}")
        result = {
            "intent": "unknown",
            "runtime": "system",
            "details": "Erreur de parsing JSON",
        }

    # Validation minimale & normalisation
    intent = (result.get("intent") or "unknown").lower()
    runtime = (result.get("runtime") or "system").lower()
    details = result.get("details") or ""

    if intent not in {"create", "configure", "audit", "kubernetes", "unknown"}:
        intent = "unknown"
    if runtime not in {"system", "docker"}:
        runtime = "system"

    return {"intent": intent, "runtime": runtime, "details": details}


def fallback_intent(request_text: str) -> dict:
    """
    Fallback manuel si analyze_intent échoue gravement côté API.
    Retourne intent + runtime + details.
    """
    text = (request_text or "").lower()

    intent_keywords = {
        "create": ["créer", "creer", "déployer", "lancer", "provisionner", "déploie", "instance", "vm", "serveur", "provider", "aws", "azure", "gcp"],
        "configure": ["configurer", "installer", "setup", "modifier", "activer", "mettre à jour", "package", "apt", "service", "nginx", "docker", "firewall", "ufw", "ssh", "ports", "port", "ouvrir", "fermer"],
        "audit": ["auditer", "vérifier", "scanner", "analyse", "sécurité", "check", "audit", "compliance", "lynis", "auditd", "fail2ban", "clamav"],
        "kubernetes": ["kubernetes", "k8s", "pod", "cluster", "manifeste", "deployment", "namespace", "ingress", "service", "yaml", "helm"],
    }

    # Détection runtime
    runtime = "system"
    if any(kw in text for kw in ["docker", "container", "compose", "image"]):
        runtime = "docker"

    scores = []
    for intent, keywords in intent_keywords.items():
        for kw in keywords:
            idx = text.find(kw)
            if idx != -1:
                scores.append((idx, intent))
                break  # premier match pour cette famille

    if scores:
        scores.sort()
        intent = scores[0][1]
    else:
        intent = "unknown"

    return {
        "intent": intent,
        "runtime": runtime,
        "details": f"Intent détecté en fallback : {intent} avec runtime {runtime}",
    }


async def generate_free_chat_completion(prompt: str) -> str:
    """
    Génère une réponse libre, en français.
    """
    messages = [
        {
            "role": "system",
            "content": (
                "Tu es un assistant DevOps qui répond naturellement et clairement aux questions. "
                "IMPORTANT: Réponds TOUJOURS en français."
            ),
        },
        {"role": "user", "content": prompt},
    ]

    content = _chat_with_retry(messages, model=_DEFAULT_MODEL, temperature=0.5)
    return content.strip()
