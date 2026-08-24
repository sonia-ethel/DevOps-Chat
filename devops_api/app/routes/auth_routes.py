# app/auth_routes.py

import logging

from fastapi import APIRouter, Depends, HTTPException, status, Request
from passlib.exc import UnknownHashError
from app.schemas import schemas 
from sqlalchemy.orm import Session
from app import models, auth, database
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from app.security.rate_limit import limiter
from app.security.audit_logger import audit_log

logger = logging.getLogger(__name__)
router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

# Dependency pour la DB
def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Register
@router.post(
    "/register",
    response_model=schemas.UserResponse,
    tags=["Authentication"],
    summary="Créer un nouveau compte utilisateur"
)
@limiter.limit("3/minute")
def register(user: schemas.UserCreate, request: Request, db: Session = Depends(get_db)):

    """
        ##  Inscription d’un nouvel utilisateur

        Permet à un utilisateur de s’enregistrer avec une adresse e-mail et un mot de passe.

        -  Le mot de passe est automatiquement haché avant d’être stocké.
        -  L’email doit être unique.

        ### Paramètres requis (via JSON Body) :
        - **email** : adresse email de l'utilisateur
        - **password** : mot de passe en clair (sera haché côté backend)

        ### Réponses :
        -  200 : Utilisateur créé avec succès (retourne `id` et `email`)
        -  400 : Email déjà enregistré
        """

    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email déjà enregistré")
    
    # Créer l'utilisateur
    hashed_password = auth.get_password_hash(user.password)
    new_user = models.User(email=user.email, password_hash=hashed_password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return new_user

# Login
@router.post(
    "/login",
    tags=["Authentication"],
    summary="Se connecter et obtenir un token JWT"
)
@limiter.limit("5/minute")
def login(form_data: OAuth2PasswordRequestForm = Depends(), request: Request = None, db: Session = Depends(get_db)):

    """
        ##  Connexion utilisateur (Login)

        Permet à un utilisateur de se connecter avec son email et son mot de passe.
        Retourne un token JWT à utiliser pour accéder aux routes sécurisées.

        ### Paramètres requis (via `application/x-www-form-urlencoded`) :
        - **username** : email de l’utilisateur (champ `username` attendu par `OAuth2PasswordRequestForm`)
        - **password** : mot de passe en clair

        ### Réponses :
        -  200 : Token JWT généré avec succès
        -  401 : Identifiants invalides (email ou mot de passe incorrect)

        ### Exemple de réponse :
        ```json
        {
        "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
        "token_type": "bearer"
        }
        ```
        """

    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    password_valid = False
    if user:
        try:
            password_valid = auth.verify_password(
                form_data.password,
                user.password_hash
            )
        except UnknownHashError:
            logger.warning(
                f"Hash invalide détecté pour l'utilisateur {user.email}"
            )
            password_valid = False

    if not user or not password_valid:
        # Audit log: login fail
        audit_log(
            request=request,
            db=db,
            action="auth.login",
            resource_type="user",
            status="fail",
            user_id=None,
            details={"email": form_data.username, "reason": "invalid_credentials"},
            error="Invalid credentials"
        )
        raise HTTPException(status_code=401, detail="Email ou mot de passe invalide")
    
    # Audit log: login success
    audit_log(
        request=request,
        db=db,
        action="auth.login",
        resource_type="user",
        status="success",
        user_id=user.id,
        details={"email": user.email}
    )
    
    access_token = auth.create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}

# Get current user info
@router.get(
    "/me",
    response_model=schemas.UserResponse,
    tags=["Authentication"],
    summary="Obtenir les informations de l'utilisateur connecté"
)
def get_current_user_info(current_user: models.User = Depends(auth.get_current_user)):
    """
    ##  Informations utilisateur connecté
    
    Retourne les informations de l'utilisateur actuellement connecté.
    Nécessite un token JWT valide.
    
    ### Réponses :
    -  200 : Informations utilisateur récupérées avec succès
    -  401 : Token JWT invalide ou manquant
    """
    return current_user
