# © 2024–2026 TOURE Arnaud Patrick
# Licensed under the MIT License

# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
import logging
import threading

from app.env import load_app_env
from app.settings import settings
from app.database import engine
from app.paths import ensure_dirs            # OK crée /data/generated_files + sous-dossiers
from app.maintenance import janitor_loop     # OK ménage périodique (rotation + purge)
from app.services.scheduler import init_scheduler, shutdown_scheduler  # OK P0.1 auto-sync
from app.security.rate_limit import setup_rate_limiting  # OK P0.2 rate limiting centralisé

# 
# Env & logs
# 
load_app_env()

# Configure logging avec fichier centralisé dans generated_files
from pathlib import Path
from datetime import datetime, timezone

log_dir = Path(os.path.join(os.path.dirname(__file__), "../generated_files/api_logs"))
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / f"api_{datetime.now().strftime('%Y%m%d')}.log"

# Configuration logging avec fichier + console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s:%(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
logger.info(f" Logging vers: {log_file}")
logger.info(f"BACKEND_BASE_URL = {settings.BACKEND_BASE_URL}")
logger.info(f"DATABASE URL = {engine.url}")

# 
# Imports des routes
# 
from app.routes.generate_routes import router as generate_router
from app.routes.auth_routes import router as auth_router
from app.routes.resource_routes import router as resource_router
from app.routes.executions_routes import router as executions_router
from app.routes.sessions_routes import router as sessions_router
from app.routes.providers_routes import router as providers_router
from app.routes.chat_creation_routes import router as chat_creation_router
from app.routes.chat_metadata_routes import router as chat_metadata_router
from app.routes.async_tasks_routes import router as async_tasks_router
from app.routes import inventories_routes
from app.routes import configure_routes
from app.routes import intents_routes
from app.routes import dashboard_routes
from app.routes.user_credentials_routes import router as user_credentials_router
from app.routes import diagnostics_routes
from app.swagger_doc import custom_openapi
from app.routes import generate_terraform
from app.routes import generate_ansible
from app.routes import generate_audit
from app.routes import terraform_routes
from app.routes import chat_resume_routes


# 
# App FastAPI
# 
app = FastAPI(
    title="DevOps-as-a-Chat API",
    description="API permettant de générer, configurer et auditer une infrastructure cloud de manière automatique.",
    version="2.0.0",
)

# Dev CORS fallback (ensures headers on error responses and exceptions)
@app.middleware("http")
async def add_dev_cors_headers(request, call_next):
    from fastapi.responses import JSONResponse
    
    origin = request.headers.get("origin")
    
    try:
        response = await call_next(request)
    except Exception as e:
        # En cas d'exception, créer une réponse d'erreur avec CORS
        logger.error(f"Exception non gérée: {e}", exc_info=True)
        response = JSONResponse(
            status_code=500,
            content={"detail": f"Erreur interne: {str(e)}"}
        )
    
    # Ajouter les headers CORS pour localhost
    if origin in {"http://localhost:5173", "http://127.0.0.1:5173"}:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "*"
        response.headers["Vary"] = "Origin"
    
    return response

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://devops-backend-uzw2.onrender.com",
        "https://devops-frontend-vc18.onrender.com",
    ],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

#  Auth
app.include_router(auth_router, prefix="/auth")

#  Génération & ressources
app.include_router(generate_terraform.router)
app.include_router(generate_ansible.router)
app.include_router(generate_audit.router)

app.include_router(generate_router)
app.include_router(resource_router, prefix="/resources")

#  Exécutions & Sessions
app.include_router(executions_router)
app.include_router(sessions_router)
app.include_router(providers_router)

#  Chat
app.include_router(chat_creation_router, prefix="/chat_creation")
app.include_router(chat_metadata_router, prefix="/chats")
app.include_router(chat_resume_routes.router)

#  Async Tasks (Polling system)
app.include_router(async_tasks_router, prefix="/async")

#  Inventaires /  Config /  Intentions /  Dashboard
app.include_router(inventories_routes.router)
app.include_router(configure_routes.router)
app.include_router(intents_routes.router)
app.include_router(dashboard_routes.router)

#  Terraform operations (P0.3 SG idempotent)
app.include_router(terraform_routes.router)

#  Diagnostics
app.include_router(diagnostics_routes.router, prefix="/diagnostics")


#  User credentials
app.include_router(user_credentials_router, prefix="/user")

# Swagger custom
app.openapi = lambda: custom_openapi(app)

# 
# P0.2 — Rate Limiting (PROD READY)
# 
setup_rate_limiting(app)

# 
# Startup
# 
@app.on_event("startup")
async def startup_event():
    # 1) crée les dossiers nécessaires (tolère PermissionError et log)
    ensure_dirs()

    # 2) lance le janitor en continu (rotation + purge) toutes les X minutes
    threading.Thread(
        target=janitor_loop, kwargs={"blocking": True}, daemon=True
    ).start()
    
    # 3) initialiser scheduler auto-sync (P0.1)
    init_scheduler()

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on API shutdown."""
    shutdown_scheduler()

# 
# P0.1 — Healthcheck & Readiness (PROD READY)
# 
@app.get("/health")
async def health_check():
    """
    Liveness probe pour Kubernetes / Docker.
    Vérifie uniquement que le process FastAPI est vivant.
    Retourne toujours 200 OK.
    """
    from datetime import datetime, timezone
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/ready")
async def readiness_check():
    """
    Readiness probe pour Kubernetes / Load Balancer.
    Vérifie que l'API peut réellement fonctionner (teste la connexion DB).
    Retourne 200 OK si la DB répond, 503 si la DB est KO.
    """
    from fastapi import status
    from fastapi.responses import JSONResponse
    from sqlalchemy import text
    from datetime import datetime, timezone
    
    try:
        # Test simple de connexion DB avec SELECT 1
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        
        return {
            "status": "ready",
            "database": "connected",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "not_ready",
                "database": "disconnected",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )

# Root
@app.get("/")
async def read_root():
    return {"message": "Bienvenue sur l'API DevOps Automation"}
