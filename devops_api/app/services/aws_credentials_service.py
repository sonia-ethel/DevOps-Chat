# © 2024–2026 TOURE Arnaud Patrick
# Licensed under the MIT License

# app/services/aws_credentials_service.py

import logging
from sqlalchemy.orm import Session
from app import models
from app.utils.crypto import decrypt_aws_secret
from typing import Optional, Dict
from botocore.exceptions import BotoCoreError, ClientError
import boto3

logger = logging.getLogger(__name__)


def validate_aws_credentials(credentials: Dict[str, str]) -> tuple[bool, Dict[str, str]]:
    """
    Valide réellement les credentials AWS via STS GetCallerIdentity.
    Utilisé par la branche codecamp pour éviter de lancer Terraform avec
    une clé expirée ou incorrecte.
    """
    access_key = credentials.get("access_key_id") or credentials.get("AWS_ACCESS_KEY_ID")
    secret_key = credentials.get("secret_access_key") or credentials.get("AWS_SECRET_ACCESS_KEY")
    region = credentials.get("region") or "eu-west-1"

    if not access_key or not secret_key:
        return False, {
            "message": "Credentials AWS incomplets. Renseigne Access Key ID et Secret Access Key.",
            "region": region,
        }

    try:
        sts = boto3.client(
            "sts",
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
        identity = sts.get_caller_identity()
        return True, {
            "message": "Credentials AWS valides.",
            "account_id": identity.get("Account", ""),
            "arn": identity.get("Arn", ""),
            "region": region,
        }
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "AWSClientError")
        return False, {
            "message": (
                f"Credentials AWS invalides ou expirés ({code}). "
                "Retourne dans l'onboarding AWS et remplace la clé avant de relancer."
            ),
            "error_code": code,
            "region": region,
        }
    except BotoCoreError as exc:
        return False, {
            "message": f"Impossible de valider les credentials AWS: {str(exc)[:160]}",
            "region": region,
        }


def get_user_aws_credentials(user_id: int, db: Session) -> Optional[Dict[str, str]]:
    """
    Récupère et déchiffre les credentials AWS d'un utilisateur.
    
    Args:
        user_id: ID de l'utilisateur
        db: Session de base de données
        
    Returns:
        Dict avec les credentials AWS déchiffrés ou None si pas trouvés
        Format: {
            "AWS_ACCESS_KEY_ID": "AKIA...",
            "AWS_SECRET_ACCESS_KEY": "xxx...",
            "region": "us-east-1",
            "provider": "aws"
        }
    """
    try:
        credentials = db.query(models.UserAWSCredentials).filter(
            models.UserAWSCredentials.user_id == user_id
        ).first()
        
        if not credentials:
            logger.info(f"No UserAWSCredentials found for user {user_id}, checking Provider...")
            # Fallback: chercher dans Provider
            from app.utils.crypto import decrypt
            import json
            provider = db.query(models.Provider).filter(
                models.Provider.user_id == user_id
            ).order_by(models.Provider.created_at.desc()).first()
            
            if not provider:
                logger.info(f"No Provider found for user {user_id}")
                return None
            
            # Decrypt provider credentials
            creds_json = decrypt(provider.encrypted_credentials)
            creds = json.loads(creds_json)
            
            return {
                "AWS_ACCESS_KEY_ID": creds.get("AWS_ACCESS_KEY_ID"),
                "AWS_SECRET_ACCESS_KEY": creds.get("AWS_SECRET_ACCESS_KEY"),
                "region": creds.get("region", "us-east-1"),
                "provider": "aws"
            }
            
        # Déchiffrer la clé secrète
        decrypted_secret = decrypt_aws_secret(credentials.secret_access_key_encrypted)
        
        # Retourner au format attendu par les services existants
        return {
            "AWS_ACCESS_KEY_ID": credentials.access_key_id,
            "AWS_SECRET_ACCESS_KEY": decrypted_secret,
            "region": credentials.region,
            "provider": "aws"
        }
        
    except Exception as e:
        logger.error(f"Error retrieving AWS credentials for user {user_id}: {str(e)}")
        return None


def has_user_aws_credentials(user_id: int, db: Session) -> bool:
    """
    Vérifie si un utilisateur a des credentials AWS configurés.
    
    Args:
        user_id: ID de l'utilisateur
        db: Session de base de données
        
    Returns:
        True si l'utilisateur a des credentials AWS, False sinon
    """
    try:
        credentials = db.query(models.UserAWSCredentials).filter(
            models.UserAWSCredentials.user_id == user_id
        ).first()
        
        return credentials is not None
        
    except Exception as e:
        logger.error(f"Error checking AWS credentials for user {user_id}: {str(e)}")
        return False


def get_aws_credentials_for_session(session_id: int, db: Session) -> Optional[Dict[str, str]]:
    """
    Récupère les credentials AWS pour une session donnée via l'utilisateur propriétaire.
    
    Args:
        session_id: ID de la session
        db: Session de base de données
        
    Returns:
        Dict avec les credentials AWS ou None si pas trouvés
    """
    try:
        session = db.query(models.Session).filter(models.Session.id == session_id).first()
        
        if not session:
            logger.error(f"Session {session_id} not found")
            return None
            
        return get_user_aws_credentials(session.user_id, db)
        
    except Exception as e:
        logger.error(f"Error retrieving AWS credentials for session {session_id}: {str(e)}")
        return None
