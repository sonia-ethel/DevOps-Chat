from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app import models, database
from app.auth import get_current_user
from app.services.aws_credentials_service import get_user_aws_credentials

router = APIRouter()

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Modèle de requête
class ProviderCreateRequest(BaseModel):
    session_id: int
    provider_name: str
    credentials: dict

# Création du provider avec validation stricte
@router.post(
    "/providers/create",
    tags=["Providers"],
    summary="Créer un provider cloud avec vérification des credentials"
)
def create_provider(
    req: ProviderCreateRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    
    """
        ##  Création d’un provider (AWS, Azure ou GCP)

        Cette route permet d'enregistrer les credentials d'un provider cloud pour une session donnée.

        ###  Authentification requise : oui (JWT)

        ###  Paramètres (Body JSON) :
        ```json
        {
        "session_id": 1,
        "provider_name": "aws",
        "credentials": {
            "AWS_ACCESS_KEY_ID": "xxx",
            "AWS_SECRET_ACCESS_KEY": "yyy",
            "region": "eu-west-1"
        }
        }
        ```

        - `provider_name` : `"aws"`, `"azure"` ou `"gcp"` (obligatoire)
        - `credentials` : dictionnaire contenant les clés attendues selon le provider
        - `session_id` : ID de la session liée à ce provider

        ###  Réponse :
        ```json
        {
        "message": "Provider created successfully",
        "provider_id": 5
        }
        ```

        ###  Erreurs possibles :
        - 400 : provider non supporté
        - 400 : credentials incomplets pour le provider donné
        """
    provider_name = req.provider_name.lower()

    #  AWS - Check stored credentials first
    if provider_name == "aws":
        # Try to get stored AWS credentials for the user
        stored_credentials = get_user_aws_credentials(user.id, db)
        
        if stored_credentials:
            # Use stored credentials instead of manually provided ones
            req.credentials = stored_credentials
        else:
            # Validate manually provided credentials
            required_keys = ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "region"]
            missing = [key for key in required_keys if key not in req.credentials]

            if missing:
                raise HTTPException(
                    status_code=400,
                    detail=f"Clés manquantes dans les credentials AWS : {', '.join(missing)}. "
                           f"Vous pouvez configurer vos clés AWS dans les paramètres pour éviter de les saisir."
                )

    #  Azure
    elif provider_name == "azure":
        required_keys = [
            "client_id", "client_secret", "tenant_id", "subscription_id"
        ]
        missing = [key for key in required_keys if key not in req.credentials]

        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Clés manquantes dans les credentials Azure : {', '.join(missing)}"
            )

    #  GCP
    elif provider_name == "gcp":
        required_keys = [
            "type", "project_id", "private_key_id", "private_key", "client_email",
            "client_id", "auth_uri", "token_uri",
            "auth_provider_x509_cert_url", "client_x509_cert_url"
        ]
        missing = [key for key in required_keys if key not in req.credentials]

        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Clés manquantes dans les credentials GCP : {', '.join(missing)}"
            )

    else:
        raise HTTPException(
            status_code=400,
            detail=f"Provider non supporté : {req.provider_name}. Utilisez 'aws', 'azure' ou 'gcp'."
        )

    # Création du provider en base
    from app.services.provider_service import get_or_create_provider

    provider = get_or_create_provider(
        user_id=user.id,
        provider_name=req.provider_name,
        credentials=req.credentials,
        session_id=req.session_id,
        db=db
    )

    return {"message": "Provider created successfully", "provider_id": provider.id}


# Récupérer le provider pour une session donnée
@router.get(
    "/providers/for_session",
    tags=["Providers"],
    summary="Récupérer le provider lié à une session"
)
def get_provider_for_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    
    """
    ##  Vérifie si une session a un provider lié

    Permet de vérifier si un provider cloud est déjà lié à une session donnée.

    ###  Authentification requise : oui (JWT)

    ###  Paramètres (Query) :
    - `session_id` (int) : ID de la session

    ###  Réponse :
    Si trouvé :
    ```json
    {
      "status": "found",
      "provider_name": "aws",
      "created_at": "2025-07-21T15:26:00"
    }
    ```
    Sinon :
    ```json
    {
      "status": "not_found"
    }
    ```
    """
    provider = db.query(models.Provider).filter(
        models.Provider.user_id == user.id,
        models.Provider.session_id == session_id
    ).first()

    if provider:
        return {
            "status": "found",
            "provider_name": provider.provider_name,
            "created_at": provider.created_at
        }
    else:
        return {"status": "not_found"}

@router.get(
    "/providers/list",
    tags=["Providers"],
    summary="Lister tous les providers enregistrés par l’utilisateur"
)
def list_providers(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    """
    ##  Liste des providers d’un utilisateur

    Cette route retourne tous les providers enregistrés par l'utilisateur, triés par date de création décroissante.

    ###  Authentification requise : oui (JWT)

    ###  Réponse :
    ```json
    [
      {
        "id": 1,
        "provider_name": "aws",
        "session_id": 2,
        "created_at": "2025-07-21T15:30:00"
      },
      ...
    ]
    ```
    """
    
    providers = db.query(models.Provider).filter(
        models.Provider.user_id == user.id
    ).order_by(models.Provider.created_at.desc()).all()

    return [
        {
            "id": p.id,
            "provider_name": p.provider_name,
            "session_id": p.session_id,
            "created_at": p.created_at
        }
        for p in providers
    ]
