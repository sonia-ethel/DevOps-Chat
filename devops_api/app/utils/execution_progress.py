# © 2024–2026 TOURE Arnaud Patrick
# Licensed under the MIT License

# app/utils/execution_progress.py
# Utility for updating execution progress in database

import json
import logging
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from app import models
from app.utils.extra_data_utils import get_extra, set_extra

logger = logging.getLogger(__name__)


def update_execution_progress(
    db: Session,
    execution_id: int,
    progress: int,
    message: Optional[str] = None,
    phase: Optional[str] = None,
) -> bool:
    """
    Update execution progress in database (stored in extra_data JSON).
    
    Args:
        db: Database session
        execution_id: ID of the execution to update
        progress: Progress percentage (0-100, will be clamped)
        message: Optional progress message
        phase: Optional phase name (e.g., "preparing", "running", "finalizing")
    
    Returns:
        True if successful, False if execution not found
    
    Example:
        update_execution_progress(db, 123, 50, "Running instance checks...")
    """
    # Clamp progress to 0-100
    progress = max(0, min(100, int(progress)))

    try:
        execution = db.query(models.Execution).filter_by(id=execution_id).first()
        if not execution:
            logger.warning("[PROGRESS] Execution not found: id=%d", execution_id)
            return False

        # Parse or initialize extra_data
        extra = get_extra(execution)

        # Update progress fields
        extra["progress"] = progress
        if message is not None:
            extra["progress_message"] = message
        if phase is not None:
            extra["progress_phase"] = phase

        # Write back to database
        set_extra(execution, extra)
        execution.updated_at = datetime.utcnow()
        db.commit()

        logger.debug(
            "[PROGRESS] Updated: id=%d progress=%d message=%s phase=%s",
            execution_id,
            progress,
            message,
            phase,
        )
        return True

    except Exception as e:
        logger.error("[PROGRESS] Error updating execution: %s", str(e))
        db.rollback()
        return False
