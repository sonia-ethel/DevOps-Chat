# © 2024–2026 TOURE Arnaud Patrick
# Licensed under the MIT License

# app/security/audit_logger.py
"""
P0.3 — Centralized Audit Logging (PRODUCTION READY)

Service d'audit logging centralisé, best-effort.
Jamais casser une route, même si l'audit log échoue.

Actions normalisées :
- auth.login, auth.register
- credentials.aws.create, credentials.aws.read, credentials.aws.update, credentials.aws.delete
- chat.message, chat.start, chat.delete, session.create, session.delete
- generate.terraform, generate.ansible, generate.audit, generate.kubernetes
- execution.create, execution.execute.start, execution.execute.end, execution.status.read
- resource.create, resource.delete, resource.sync
"""

import logging
import json
from typing import Optional, Any, Dict
from datetime import datetime
from fastapi import Request
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.database import SessionLocal

logger = logging.getLogger(__name__)

# 
# Fonction centralisée d'audit logging (BEST-EFFORT)
# 

def audit_log(
    request: Optional[Request],
    db: Session,  # WARN Paramètre ignoré, on crée une session indépendante
    action: str,
    resource_type: str,
    status: str,  # "success" | "fail"
    user_id: Optional[int] = None,
    resource_id: Optional[str] = None,
    session_id: Optional[int] = None,
    execution_id: Optional[int] = None,
    details: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> None:
    """
    Enregistrer un événement d'audit dans la DB.
    
    Cette fonction est BEST-EFFORT : si elle échoue, elle loggue un warning
    et continue (ne casse JAMAIS la route appelante).
    
    WARN Crée une SESSION DB INDÉPENDANTE pour éviter les rollbacks de la route principale.
    
    Args:
        request: FastAPI Request (pour IP, User-Agent)
        db: SQLAlchemy Session (IGNORÉ - on crée une session indépendante)
        action: action normalisée (ex: "auth.login")
        resource_type: type de ressource (ex: "user", "credentials")
        status: "success" ou "fail"
        user_id: ID utilisateur (nullable)
        resource_id: ID ressource (nullable)
        session_id: ID session (nullable)
        execution_id: ID exécution (nullable)
        details: JSON dict (sans secrets)
        error: message d'erreur court (max 500 chars)
    """
    # OK SESSION INDÉPENDANTE pour éviter les rollbacks FastAPI
    audit_db = SessionLocal()
    
    try:
        logger.info(f" audit_log START: {action} ({status})")
        
        # Récupérer IP address
        ip_address = "unknown"
        if request and request.client:
            ip_address = request.client.host
        
        # Récupérer User-Agent
        user_agent = "unknown"
        if request:
            user_agent = request.headers.get("user-agent", "unknown")[:200]
        
        # Tronquer error message
        if error:
            error = str(error)[:500]
        
        # Normaliser details (pas None, pas de secrets)
        if details is None:
            details = {}
        details_json = json.dumps(details, default=str)[:2000]  # Max 2000 chars
        
        # Créer l'enregistrement audit_log
        # On utilise une requête SQL brute pour éviter les dépendances circulaires
        query = """
        INSERT INTO audit_logs (
            user_id, ip_address, user_agent, action, resource_type, 
            resource_id, status, error_message, details, session_id, 
            execution_id, created_at
        ) VALUES (
            :user_id, :ip_address, :user_agent, :action, :resource_type,
            :resource_id, :status, :error_message, :details, :session_id,
            :execution_id, :created_at
        )
        """
        
        audit_db.execute(
            text(query),
            {
                "user_id": user_id,
                "ip_address": ip_address,
                "user_agent": user_agent,
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "status": status,
                "error_message": error,
                "details": details_json,
                "session_id": session_id,
                "execution_id": execution_id,
                "created_at": datetime.utcnow(),
            }
        )
        audit_db.commit()
        logger.info(f" audit_log COMMITTED: {action}")
        
        logger.debug(f"OK Audit log: {action} ({resource_type}) by user {user_id} - {status}")
        
    except Exception as e:
        # BEST-EFFORT : never crash
        logger.error(f"ERR audit_log FAILED ({action}): {type(e).__name__}: {str(e)}")
        try:
            audit_db.rollback()
        except:
            pass
    finally:
        # OK Toujours fermer la session indépendante
        try:
            audit_db.close()
            logger.info(f" audit_log CLOSED: {action}")
        except:
            pass
