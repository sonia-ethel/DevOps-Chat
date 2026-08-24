# © 2024–2026 TOURE Arnaud Patrick
# Licensed under the MIT License

# app/auth.py

from passlib.context import CryptContext
from passlib.exc import InvalidHashError, UnknownHashError
from jose import JWTError, jwt
from datetime import datetime, timedelta
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.env import load_app_env
from app import database, models
import os

# Charger les variables d'environnement
load_app_env()

# Récupérer les variables de configuration
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES"))

# Initialiser le contexte de hashage
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 schema
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


# Hashage du mot de passe
def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

# Vérification du mot de passe
def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not hashed_password or not isinstance(hashed_password, str):
        raise UnknownHashError("Hash invalide ou manquant")

    try:
        return pwd_context.verify(plain_password, hashed_password)
    except UnknownHashError:
        raise
    except (InvalidHashError, ValueError, TypeError) as exc:
        raise UnknownHashError(str(exc)) from exc

# Création d'un token JWT
def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# Dependency de récupération de la session DB
def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Récupération de l'utilisateur courant via le token JWT
# Accepte désormais `sub` en email OU en id pour couvrir dev-auth et auth classiques.
def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> models.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Impossible de valider les identifiants",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        subject = payload.get("sub")
        if subject is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = None
    #  Try by numeric id first when sub is an id
    try:
        if isinstance(subject, (int, float)) or (isinstance(subject, str) and subject.isdigit()):
            user_id = int(subject)
            user = db.query(models.User).filter(models.User.id == user_id).first()
    except Exception:
        # Fallback handled below
        user = None

    #  Fallback to email lookup
    if user is None and isinstance(subject, str):
        user = db.query(models.User).filter(models.User.email == subject).first()

    if user is None:
        raise credentials_exception
    return user
