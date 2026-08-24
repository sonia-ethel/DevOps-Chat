# app/routes/user_credentials_routes.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.schemas import schemas
from app import models, auth
from app.database import get_db
from app.utils.crypto import encrypt_aws_secret, decrypt_aws_secret
from app.services.aws_credentials_service import validate_aws_credentials
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


def get_aws_credentials_for_user(user_id: int, db: Session) -> models.UserAWSCredentials:
    """
    Helper function to get AWS credentials for a specific user.
    Used by diagnostics and services that need AWS creds outside FastAPI dependency injection.
    """
    credentials = db.query(models.UserAWSCredentials).filter(
        models.UserAWSCredentials.user_id == user_id
    ).first()
    return credentials


@router.post(
    "/aws-credentials",
    response_model=schemas.AWSCredentialsResponse,
    tags=["User Credentials"],
    summary="Save or update AWS credentials"
)
def save_aws_credentials(
    credentials: schemas.AWSCredentialsCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """
    ##  Save or update AWS credentials for the authenticated user
    
    Securely stores AWS credentials with encryption for sensitive data.
    The secret access key is encrypted before storage.
    
    ### Parameters:
    - **access_key_id**: AWS Access Key ID (AKIA...)
    - **secret_access_key**: AWS Secret Access Key (will be encrypted)
    - **region**: AWS region (default: us-east-1)
    
    ### Security:
    - Secret access key is encrypted using Fernet encryption
    - Only the authenticated user can access their credentials
    - Credentials are tied to the user's account
    
    ### Responses:
    -  200: Credentials saved successfully
    -  500: Encryption or database error
    """
    try:
        valid, validation = validate_aws_credentials({
            "access_key_id": credentials.access_key_id,
            "secret_access_key": credentials.secret_access_key,
            "region": credentials.region,
        })
        if not valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=validation.get("message", "Credentials AWS invalides."),
            )

        # Check if user already has AWS credentials
        existing_creds = db.query(models.UserAWSCredentials).filter(
            models.UserAWSCredentials.user_id == current_user.id
        ).first()
        
        # Encrypt the secret access key
        encrypted_secret = encrypt_aws_secret(credentials.secret_access_key)
        
        if existing_creds:
            # Update existing credentials
            existing_creds.access_key_id = credentials.access_key_id
            existing_creds.secret_access_key_encrypted = encrypted_secret
            existing_creds.region = credentials.region
            
            db.commit()
            db.refresh(existing_creds)
            # Log masked key (don't log secrets)
            masked = (credentials.access_key_id[:6] + "****") if credentials.access_key_id else "(none)"
            logger.info(
                "Updated AWS credentials for user_id=%s region=%s access_key=%s",
                current_user.id,
                existing_creds.region,
                masked,
            )
            return {
                "configured": True,
                "validated": True,
                "region": existing_creds.region,
                "account_id": validation.get("account_id"),
                "message": validation.get("message"),
            }
        else:
            # Create new credentials
            new_creds = models.UserAWSCredentials(
                user_id=current_user.id,
                access_key_id=credentials.access_key_id,
                secret_access_key_encrypted=encrypted_secret,
                region=credentials.region
            )
            
            db.add(new_creds)
            db.commit()
            db.refresh(new_creds)

            masked = (credentials.access_key_id[:6] + "****") if credentials.access_key_id else "(none)"
            logger.info(
                "Created AWS credentials for user_id=%s region=%s access_key=%s",
                current_user.id,
                new_creds.region,
                masked,
            )
            return {
                "configured": True,
                "validated": True,
                "region": new_creds.region,
                "account_id": validation.get("account_id"),
                "message": validation.get("message"),
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving AWS credentials for user {current_user.id}: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save AWS credentials"
        )


@router.get(
    "/aws-credentials",
    tags=["User Credentials"],
    summary="Get AWS credentials status"
)
def get_aws_credentials(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """
    ##  Get AWS credentials for the authenticated user
    
    Returns the stored AWS credentials (excluding the secret access key).
    Returns configured=false if no credentials exist instead of 404.
    
    ### Security:
    - Only returns non-sensitive information
    - Secret access key is never returned in API responses
    - Only the authenticated user can access their credentials
    
    ### Responses:
    -  200: Always returns success with configured status
    """
    credentials = db.query(models.UserAWSCredentials).filter(
        models.UserAWSCredentials.user_id == current_user.id
    ).first()
    
    if not credentials:
        logger.info("No AWS credentials found for user_id=%s", current_user.id)
        return {
            "configured": False,
            "validated": False,
            "region": None,
        }

    logger.info("Retrieved AWS credentials for user_id=%s region=%s", current_user.id, credentials.region)
    secret_key = decrypt_aws_secret(credentials.secret_access_key_encrypted)
    valid, validation = validate_aws_credentials({
        "access_key_id": credentials.access_key_id,
        "secret_access_key": secret_key,
        "region": credentials.region,
    })
    return {
        "configured": True,
        "validated": valid,
        "region": credentials.region,
        "account_id": validation.get("account_id"),
        "message": validation.get("message"),
    }


@router.delete(
    "/aws-credentials",
    tags=["User Credentials"],
    summary="Delete AWS credentials"
)
def delete_aws_credentials(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """
    ##  Delete AWS credentials for the authenticated user
    
    Permanently removes the stored AWS credentials from the database.
    This action cannot be undone.
    
    ### Security:
    - Only the authenticated user can delete their credentials
    - Secure deletion from database
    
    ### Responses:
    -  200: Credentials deleted successfully
    -  404: No credentials found for user
    """
    credentials = db.query(models.UserAWSCredentials).filter(
        models.UserAWSCredentials.user_id == current_user.id
    ).first()
    
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No AWS credentials found for this user"
        )
    
    try:
        db.delete(credentials)
        db.commit()
        
        logger.info(f"Deleted AWS credentials for user {current_user.id}")
        return {"message": "AWS credentials deleted successfully"}
        
    except Exception as e:
        logger.error(f"Error deleting AWS credentials for user {current_user.id}: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete AWS credentials"
        )
