from __future__ import annotations

from typing import Any
from datetime import datetime, timezone

SENSITIVE_KEYS = {
    "access_key_id",
    "aws_access_key_id",
    "secret_access_key",
    "aws_secret_access_key",
    "session_token",
    "token",
    "password",
    "private_key",
    "authorization",
}

REDACTED = "***REDACTED***"


def _is_sensitive_key(key: str) -> bool:
    return key.strip().lower() in SENSITIVE_KEYS


def ensure_timezone_aware(dt: datetime | None) -> datetime | None:
    """
    Convert naive datetime to timezone-aware (UTC).
    
    This ensures ISO8601 serialization includes timezone info like +00:00 or Z.
    PostgreSQL DateTime(timezone=True) stores UTC but may return naive datetime objects.
    
    Args:
        dt: A datetime object (may be naive or aware)
    
    Returns:
        A timezone-aware datetime in UTC, or None if input is None
    """
    if dt is None:
        return None
    
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            # Naive datetime - assume UTC
            return dt.replace(tzinfo=timezone.utc)
        else:
            # Already aware
            return dt
    
    return dt


def redact_secrets(obj: Any) -> Any:
    """Recursively redact sensitive fields from dicts/lists/objects."""
    if obj is None:
        return obj

    if isinstance(obj, dict):
        redacted: dict[str, Any] = {}
        for k, v in obj.items():
            if _is_sensitive_key(str(k)):
                redacted[k] = REDACTED
            else:
                redacted[k] = redact_secrets(v)
        return redacted

    if isinstance(obj, (list, tuple, set)):
        return [redact_secrets(v) for v in obj]

    if hasattr(obj, "model_dump") and callable(getattr(obj, "model_dump")):
        return redact_secrets(obj.model_dump())

    if hasattr(obj, "dict") and callable(getattr(obj, "dict")):
        return redact_secrets(obj.dict())

    return obj
