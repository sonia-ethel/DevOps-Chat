# app/utils/crypto.py

from cryptography.fernet import Fernet
import os
import json
from app.env import load_app_env

load_app_env()

FERNET_KEY = os.getenv("FERNET_KEY") or os.getenv("FERNET_SECRET")

if not FERNET_KEY:
    raise RuntimeError("ERR FERNET_KEY non défini dans l'environnement.")

#  Création de l'objet Fernet
fernet = Fernet(FERNET_KEY)

def encrypt(data: str | dict) -> str:
    """
    Chiffre une chaîne ou un dictionnaire Python.
    """
    if isinstance(data, dict):
        data = json.dumps(data)  #  Convertir en JSON string
    return fernet.encrypt(data.encode()).decode()

def decrypt(token: str) -> str:
    """
    Déchiffre un token et retourne une chaîne JSON (à parser si besoin).
    """
    return fernet.decrypt(token.encode()).decode()


#  Fonctions spécialisées pour les credentials AWS
def encrypt_aws_secret(secret_key: str) -> str:
    """
    Chiffre une clé secrète AWS.
    """
    return encrypt(secret_key)


def decrypt_aws_secret(encrypted_secret: str) -> str:
    """
    Déchiffre une clé secrète AWS.
    """
    return decrypt(encrypted_secret)


def encrypt_aws_credentials(credentials: dict) -> dict:
    """
    Chiffre les credentials AWS (garde access_key_id en clair, chiffre secret_access_key).
    
    Args:
        credentials: {"access_key_id": "AKIA...", "secret_access_key": "xxx", "region": "us-east-1"}
        
    Returns:
        {"access_key_id": "AKIA...", "secret_access_key_encrypted": "gAA...", "region": "us-east-1"}
    """
    result = credentials.copy()
    if 'secret_access_key' in result:
        result['secret_access_key_encrypted'] = encrypt_aws_secret(result.pop('secret_access_key'))
    return result


def decrypt_aws_credentials(encrypted_credentials: dict) -> dict:
    """
    Déchiffre les credentials AWS.
    
    Args:
        encrypted_credentials: {"access_key_id": "AKIA...", "secret_access_key_encrypted": "gAA...", "region": "us-east-1"}
        
    Returns:
        {"access_key_id": "AKIA...", "secret_access_key": "xxx", "region": "us-east-1"}
    """
    result = encrypted_credentials.copy()
    if 'secret_access_key_encrypted' in result:
        result['secret_access_key'] = decrypt_aws_secret(result.pop('secret_access_key_encrypted'))
    return result
