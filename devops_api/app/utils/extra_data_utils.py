# © 2024–2026 TOURE Arnaud Patrick
# Licensed under the MIT License

# app/utils/extra_data_utils.py
"""Utilities for handling Execution.extra_data consistently."""

import json
import logging
from typing import Any, Dict
from app import models

logger = logging.getLogger(__name__)


def get_extra(execution: models.Execution) -> Dict[str, Any]:
    """
    Safely extract extra_data from Execution as dict.
    
    Handles:
    - None values
    - Already-parsed dicts
    - Legacy string-encoded JSON
    
    Args:
        execution: Execution model instance
    
    Returns:
        Dictionary (never None, empty dict if invalid)
    """
    if execution.extra_data is None:
        return {}
    
    if isinstance(execution.extra_data, dict):
        return execution.extra_data
    
    # Fallback: legacy rows stored as string JSON
    if isinstance(execution.extra_data, str):
        try:
            return json.loads(execution.extra_data)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse extra_data JSON for execution {execution.id}: {e}")
            return {}
    
    logger.warning(f"Unexpected extra_data type for execution {execution.id}: {type(execution.extra_data)}")
    return {}


def set_extra(execution: models.Execution, data: Dict[str, Any]) -> None:
    """
    Safely set extra_data on Execution as dict.
    
    Always stores as dict (SQLAlchemy JSON will handle serialization).
    
    Args:
        execution: Execution model instance
        data: Dictionary to store
    """
    if not isinstance(data, dict):
        logger.error(f"set_extra called with non-dict: {type(data)}")
        execution.extra_data = {}
    else:
        execution.extra_data = data
