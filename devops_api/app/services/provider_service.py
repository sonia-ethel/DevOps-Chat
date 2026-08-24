import logging
logger = logging.getLogger(__name__)

from sqlalchemy.orm import Session
from app import models
from app.utils.crypto import encrypt

def get_or_create_provider(
    user_id: int,
    provider_name: str,
    credentials: dict,
    session_id: int | None,
    db: Session
) -> models.Provider:
    """
     Crée un provider cloud ou récupère l'existant pour un utilisateur et une session.

    Ce service est utilisé pour :
    - Éviter les doublons de configuration pour un même utilisateur et provider.
    - Garantir qu'une combinaison (user_id, provider_name, session_id) est unique.
    - Chiffrer les credentials AVANT de les stocker dans la base.

     Le champ `encrypted_credentials` N'EST PAS utilisé dans la requête de filtre,
    car PostgreSQL ne peut pas comparer une string chiffrée à un champ JSON.

     Paramètres :
    - `user_id` : ID de l'utilisateur propriétaire du provider.
    - `provider_name` : Nom du provider cloud (ex: "aws", "azure", "gcp").
    - `credentials` : Dictionnaire des clés d’authentification du cloud provider.
    - `session_id` : ID de la session liée à ce provider.
    - `db` : Session SQLAlchemy pour les opérations en base.

     Retour :
    - L’instance du modèle `Provider` (existante ou nouvellement créée).
    """
    existing = db.query(models.Provider).filter_by(
        user_id=user_id,
        provider_name=provider_name,
        session_id=session_id
    ).first()

    # Si un provider existe déjà ET contient des credentials, on le retourne
    if existing and existing.encrypted_credentials:
        return existing

    # Sinon, on chiffre les nouveaux credentials
    encrypted = encrypt(credentials)

    # Si un provider existe mais n'a pas encore de credentials => on les met à jour
    if existing and not existing.encrypted_credentials:
        existing.encrypted_credentials = encrypted
        db.commit()
        db.refresh(existing)
        return existing

    #  Sinon on crée un nouveau provider complet
    new_provider = models.Provider(
        user_id=user_id,
        provider_name=provider_name,
        encrypted_credentials=encrypted,
        session_id=session_id
    )

    db.add(new_provider)
    db.commit()
    db.refresh(new_provider)
    return new_provider