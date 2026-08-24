import logging
logger = logging.getLogger(__name__)

import json
from sqlalchemy.orm import Session
from app import models
from datetime import datetime
from typing import Union


def log_execution_event(
    db: Session,
    execution_id: int,
    user_id: int,
    event: str,
    message: Union[str, dict],
    log_content: Union[str, dict] = ""
):
    """
    Crée une entrée dans execution_logs.
    Convertit automatiquement les dicts en JSON pour éviter les erreurs SQL.
    """

    # Sécuriser : convertir tous les dicts en chaîne pour message
    if isinstance(message, dict):
        try:
            message = json.dumps(message, indent=2, ensure_ascii=False)
        except Exception as e:
            message = f"[ERREUR de serialization JSON message] {str(e)}"

    # log_content uniquement pour affichage console
    if isinstance(log_content, dict):
        try:
            log_content = json.dumps(log_content, indent=2, ensure_ascii=False)
        except Exception as e:
            log_content = f"[ERREUR de serialization JSON log_content] {str(e)}"

    logger.info(f" [LOGGER] Log : execution_id={execution_id}, event={event}")
    logger.info(f" [MESSAGE] {message[:100]}{'...' if len(message) > 100 else ''}")
    logger.info(f" [LOG_CONTENT] {log_content[:100]}{'...' if len(log_content) > 100 else ''}")

    log = models.ExecutionLog(
        execution_id=execution_id,
        user_id=user_id,
        event=event,
        message=message,
        created_at=datetime.utcnow()
    )

    db.add(log)
    db.commit()
    logger.info(" [LOGGER] Log enregistré.")
