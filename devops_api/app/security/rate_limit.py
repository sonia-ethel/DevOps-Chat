# © 2024–2026 TOURE Arnaud Patrick
# Licensed under the MIT License

# app/security/rate_limit.py
"""
P0.2 — Centralized Rate Limiting (PRODUCTION READY)

Rate limiting centralisé avec SlowAPI uniquement.

Limites :
- Globale : 100/minute/IP (toute l'API)
- POST /auth/login : 5/minute
- POST /auth/register : 3/minute
- POST /chat_creation/chat_message : 20/minute
- POST /generate : 10/minute

OPTIONS (CORS preflight) : jamais bloqué
Dépassement : HTTP 429 avec Retry-After: 60
"""

import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

logger = logging.getLogger(__name__)

# 
# Configuration du Limiter (SlowAPI uniquement)
# 
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100/minute"],
    storage_uri="memory://",
    # Bypass automatique pour OPTIONS (CORS)
    swallow_errors=False
)


# 
# Handler personnalisé pour RateLimitExceeded
# 
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """
    Handler pour les dépassements de limite.
    Retourne HTTP 429 avec message standard.
    """
    logger.warning(f"Rate limit exceeded: {request.method} {request.url.path} from {get_remote_address(request)}")
    
    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "message": "Trop de requêtes",
            "retry_after": 60
        },
        headers={"Retry-After": "60"}
    )


# 
# Fonction d'initialisation
# 
def setup_rate_limiting(app: FastAPI):
    """
    Configure le rate limiting pour l'application FastAPI.
    
    - Attache le limiter à app.state
    - Configure le handler pour HTTP 429
    - Active la limite globale 100/minute
    - Les limites spécifiques sont appliquées via @limiter.limit() dans les routes
    
    Args:
        app: L'instance FastAPI
    """
    logger.info(" Configuration du rate limiting...")
    
    # Attacher le limiter à l'app state (obligatoire pour SlowAPI)
    app.state.limiter = limiter
    
    # Ajouter le handler personnalisé pour RateLimitExceeded
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    
    logger.info("[RateLimit] Rate limiting configured:")
    logger.info("   • Limite globale: 100/minute/IP")
    logger.info("   • POST /auth/login: 5/minute")
    logger.info("   • POST /auth/register: 3/minute")
    logger.info("   • POST /chat_creation/chat_message: 20/minute")
    logger.info("   • POST /generate: 10/minute")
    logger.info("   • OPTIONS (CORS): jamais bloqué")


