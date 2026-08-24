# © 2024–2026 TOURE Arnaud Patrick
# Licensed under the MIT License

# app/services/idempotency_service.py
"""
P0.5 — Idempotence (PRODUCTION READY)

Service centralisé de gestion de l'idempotence pour prévenir les doubles exécutions.

Garanties :
- Même requête = même résultat
- Zéro double exécution réelle
- Best-effort (ne casse jamais la route)

Scopes supportés :
  - generate: Terraform, Ansible, Kubernetes, Audit generation
  - execution.create: Création d'une exécution
  - execution.execute: Lancement d'une exécution

Status :
  - started: Clé créée, traitement en cours
  - completed: Traitement terminé avec succès
  - failed: Traitement échoué
"""

import logging
import json
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)

# 
# Modèle de retour (quand clé déjà complétée)
# 

class IdempotencyResult:
    """Résultat du check idempotency"""
    
    def __init__(
        self,
        is_duplicate: bool,
        is_in_progress: bool,
        resource_id: Optional[int] = None,
        cached_response: Optional[Dict[str, Any]] = None
    ):
        self.is_duplicate = is_duplicate  # Clé déjà complétée
        self.is_in_progress = is_in_progress  # Clé déjà en cours
        self.resource_id = resource_id  # ID de la ressource créée
        self.cached_response = cached_response  # Réponse mise en cache


# 
# Fonctions principales d'idempotence
# 

def check_or_create_idempotency_key(
    db: Session,
    user_id: int,
    idempotency_key: str,
    scope: str,  # "generate" | "execution.create" | "execution.execute"
) -> IdempotencyResult:
    """
    Vérifie ou crée une clé d'idempotence.
    
    Comportement :
    - Si clé existe et status=completed -> retourner is_duplicate=True
    - Si clé existe et status=started -> retourner is_in_progress=True
    - Si clé n'existe pas -> créer avec status=started, retourner is_duplicate=False
    
    Args:
        db: SQLAlchemy Session
        user_id: ID de l'utilisateur
        idempotency_key: Clé unique fournie par le client
        scope: Type d'opération (generate, execution.create, execution.execute)
    
    Returns:
        IdempotencyResult avec statuts
    
    Raises:
        HTTP 409 si déjà en cours
    """
    
    try:
        # Chercher la clé existante
        result = db.execute(
            text("""
                SELECT id, status, response_body FROM idempotency_keys
                WHERE user_id = :user_id AND key = :key AND route = :scope
                ORDER BY created_at DESC LIMIT 1
            """),
            {"user_id": user_id, "key": idempotency_key, "scope": scope}
        )
        
        existing = result.fetchone()
        
        if existing:
            key_id, status_val, response_body = existing
            
            #  Déjà complétée -> retourner le résultat mis en cache
            if status_val == "completed":
                logger.info(f" Idempotency duplicate: {scope} key={idempotency_key} (user={user_id})")
                
                # Parser la ressource_id depuis response_body si présent
                resource_id = None
                try:
                    if response_body:
                        resp = json.loads(response_body)
                        resource_id = resp.get("id") or resp.get("execution_id")
                except:
                    pass
                
                return IdempotencyResult(
                    is_duplicate=True,
                    is_in_progress=False,
                    resource_id=resource_id,
                    cached_response=json.loads(response_body) if response_body else None
                )
            
            #  Déjà en cours -> rejeter (HTTP 409)
            elif status_val == "started":
                logger.warning(f" Idempotency in progress: {scope} key={idempotency_key} (user={user_id})")
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Cette opération est déjà en cours. Veuillez attendre ou utiliser une nouvelle clé d'idempotence."
                )
            
            #  Échouée -> créer une nouvelle entrée
            elif status_val == "failed":
                logger.info(f" Idempotency retrying failed: {scope} key={idempotency_key} (user={user_id})")
                # Continuer et créer une nouvelle clé
        
        #  Créer une nouvelle clé avec status=started
        db.execute(
            text("""
                INSERT INTO idempotency_keys (user_id, key, route, status, created_at, updated_at)
                VALUES (:user_id, :key, :route, 'started', NOW(), NOW())
                ON CONFLICT (user_id, key, route) DO UPDATE
                SET status = 'started', updated_at = NOW()
                WHERE idempotency_keys.status = 'failed'
            """),
            {"user_id": user_id, "key": idempotency_key, "route": scope}
        )
        db.commit()
        
        logger.info(f" Idempotency key created: {scope} key={idempotency_key} (user={user_id})")
        
        return IdempotencyResult(
            is_duplicate=False,
            is_in_progress=False,
            resource_id=None
        )
        
    except HTTPException:
        raise  # Re-lever les exceptions HTTP
    except Exception as e:
        logger.error(f" Idempotency check failed: {str(e)}")
        try:
            db.rollback()
        except Exception:
            pass
        # BEST-EFFORT : ne pas casser la route
        return IdempotencyResult(
            is_duplicate=False,
            is_in_progress=False,
            resource_id=None
        )


def mark_idempotency_completed(
    db: Session,
    user_id: int,
    idempotency_key: str,
    scope: str,
    resource_id: Optional[int] = None,
    response_body: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Marquer une clé d'idempotence comme complétée.
    
    À appeler UNIQUEMENT à la fin d'un succès.
    
    Args:
        db: SQLAlchemy Session
        user_id: ID de l'utilisateur
        idempotency_key: Clé unique
        scope: Type d'opération
        resource_id: ID de la ressource créée (optionnel)
        response_body: Réponse à mettre en cache (optionnel)
    """
    
    try:
        response_json = json.dumps(response_body) if response_body else None
        
        db.execute(
            text("""
                UPDATE idempotency_keys
                SET status = 'completed', 
                    response_body = :response_body,
                    response_code = 200,
                    updated_at = NOW()
                WHERE user_id = :user_id AND key = :key AND route = :scope
            """),
            {
                "user_id": user_id,
                "key": idempotency_key,
                "scope": scope,
                "response_body": response_json
            }
        )
        db.commit()
        
        logger.info(f" Idempotency completed: {scope} key={idempotency_key} resource_id={resource_id}")
        
    except Exception as e:
        logger.warning(f" Idempotency mark_completed failed: {str(e)}")
        try:
            db.rollback()
        except:
            pass
        # BEST-EFFORT : ne pas casser la route


def mark_idempotency_failed(
    db: Session,
    user_id: int,
    idempotency_key: str,
    scope: str,
    error_message: Optional[str] = None,
) -> None:
    """
    Marquer une clé d'idempotence comme échouée.
    
    À appeler en cas d'exception métier.
    
    Args:
        db: SQLAlchemy Session
        user_id: ID de l'utilisateur
        idempotency_key: Clé unique
        scope: Type d'opération
        error_message: Message d'erreur (optionnel)
    """
    
    try:
        error_json = json.dumps({"error": error_message}) if error_message else None
        
        db.execute(
            text("""
                UPDATE idempotency_keys
                SET status = 'failed',
                    response_body = :response_body,
                    response_code = 500,
                    updated_at = NOW()
                WHERE user_id = :user_id AND key = :key AND route = :scope
            """),
            {
                "user_id": user_id,
                "key": idempotency_key,
                "scope": scope,
                "response_body": error_json
            }
        )
        db.commit()
        
        logger.info(f" Idempotency failed: {scope} key={idempotency_key} error={error_message}")
        
    except Exception as e:
        logger.warning(f" Idempotency mark_failed failed: {str(e)}")
        try:
            db.rollback()
        except:
            pass
        # BEST-EFFORT : ne pas casser la route


def extract_idempotency_key(request_headers: Dict[str, str]) -> Optional[str]:
    """
    Extraire la clé d'idempotence depuis les headers HTTP.
    
    Cherche le header "Idempotency-Key" (case-insensitive).
    
    Args:
        request_headers: Headers HTTP
    
    Returns:
        Clé d'idempotence ou None
    """
    
    for key, value in request_headers.items():
        if key.lower() == "idempotency-key":
            return value.strip()
    
    return None
