from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app import models, database
from app.auth import get_current_user
from app.utils.crypto import decrypt
from app.services.resource_service import delete_resource, list_resources
from app.services.aws_sync_service import sync_aws_instances_to_db
import json
from azure.identity import ClientSecretCredential
from azure.mgmt.compute import ComputeManagementClient


router = APIRouter()

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get(
    "/list_resources",
    tags=["Resources"],
    summary="Lister les ressources (instances) créées par session"
)
def list_instances(
    session_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    """
    ##  Lister les instances d’un utilisateur
    Permet d’afficher toutes les instances créées par l’utilisateur connecté.
     Authentification requise : oui (JWT)
    """
    session = db.query(models.Session).filter(
        models.Session.id == session_id,
        models.Session.user_id == user.id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session non trouvée.")

    instances = db.query(models.Instance).join(models.Session).filter(
        models.Session.user_id == user.id
    ).all()

    response = []
    for inst in instances:
        response.append({
            "instance_id": inst.instance_id,
            "public_ip": decrypt(inst.public_ip),
            "private_ip": decrypt(inst.private_ip) if inst.private_ip else None,
            "ssh_user": inst.ssh_user,
            "provider": inst.provider
        })

    return {"resources": response}


@router.get(
    "/list_all_resources",
    tags=["Resources"],
    summary="Lister TOUTES les ressources (base locale + cloud AWS)"
)
def list_all_resources(
    session_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    """
    ##  Lister toutes les ressources (hybride)
    
    Liste les instances de la base locale ET découvre toutes les ressources AWS réelles.
    Fournit une vue complète des ressources cloud.
    
     Authentification requise : oui (JWT)
    
    ###  Réponse enrichie :
    ```json
    {
      "database_resources": [...],
      "cloud_resources": [...],
      "summary": {
        "total_db": 2,
        "total_cloud": 5,
        "total_unique": 6
      }
    }
    ```
    """
    session = db.query(models.Session).filter(
        models.Session.id == session_id,
        models.Session.user_id == user.id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session non trouvée.")

    # 1. Ressources de la base de données (comme avant)
    instances = db.query(models.Instance).join(models.Session).filter(
        models.Session.user_id == user.id
    ).all()

    database_resources = []
    for inst in instances:
        database_resources.append({
            "instance_id": inst.instance_id,
            "public_ip": decrypt(inst.public_ip),
            "private_ip": decrypt(inst.private_ip) if inst.private_ip else None,
            "ssh_user": inst.ssh_user,
            "provider": inst.provider,
            "source": "database"
        })

    # 2. Découverte des ressources cloud (AWS)
    cloud_resources = []
    try:
        # Récupérer les credentials AWS de l'utilisateur
        provider = db.query(models.Provider).filter(
            models.Provider.user_id == user.id,
            models.Provider.provider_name == "aws"
        ).first()
        
        if provider:
            # Decrypt credentials
            decrypted = decrypt(provider.encrypted_credentials)
            credentials = json.loads(decrypted)
            
            # Appel de la fonction existante list_resources
            aws_instances = list_resources(credentials, db, user.id)
            
            for aws_inst in aws_instances:
                cloud_resources.append({
                    "instance_id": aws_inst.get("InstanceId"),
                    "state": aws_inst.get("State"),
                    "public_ip": aws_inst.get("PublicIp"),
                    "private_ip": aws_inst.get("PrivateIp"),
                    "launch_time": aws_inst.get("LaunchTime"),
                    "provider": "aws",
                    "source": "cloud_api"
                })
    except Exception as e:
        # Si l'API AWS échoue, on continue avec les données de la base
        print(f" Erreur lors de la découverte AWS: {e}")

    # 3. Calcul du résumé
    db_ids = {r["instance_id"] for r in database_resources}
    cloud_ids = {r["instance_id"] for r in cloud_resources if r["instance_id"]}
    total_unique = len(db_ids.union(cloud_ids))

    return {
        "database_resources": database_resources,
        "cloud_resources": cloud_resources,
        "summary": {
            "total_db": len(database_resources),
            "total_cloud": len(cloud_resources),
            "total_unique": total_unique,
            "aws_discovery_success": len(cloud_resources) > 0
        }
    }


@router.post(
    "/delete_resource",
    tags=["Resources"],
    summary="Supprimer une ou plusieurs instances du cloud et de la base"
)
async def delete_instance(
    session_id: int,
    instance_id: str = Query(..., description="Un ou plusieurs IDs séparés par des virgules, ex: i-123,i-456"),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    """
    ##  Supprimer une ou plusieurs instances du cloud et de la base

    Supprime une ou plusieurs ressources cloud (AWS, Azure, GCP…) **et** leurs entrées en base.

     Authentification requise : oui (JWT)

    ###  Paramètres :
    - `session_id` : ID de la session
    - `instance_id` : ID unique ou plusieurs séparés par des virgules (ex: `i-123,i-456`)

    ###  Réponse :
    ```json
    {
      "deleted": ["i-123", "i-456"]
    }
    ```
    """
    session = db.query(models.Session).filter(
        models.Session.id == session_id,
        models.Session.user_id == user.id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session non trouvée.")

    instance_ids = [id.strip() for id in instance_id.split(",") if id.strip()]
    deleted = []

    for inst_id in instance_ids:
        db_instance = db.query(models.Instance).join(models.Session).filter(
            models.Instance.instance_id == inst_id,
            models.Session.user_id == user.id
        ).first()
        if not db_instance:
            print(f" Instance {inst_id} non trouvée.")
            continue

        provider = db.query(models.Provider).filter(
            models.Provider.user_id == user.id,
            models.Provider.provider_name == db_instance.provider
        ).first()
        if not provider:
            print(f" Provider non trouvé pour l'instance {inst_id}.")
            continue

        decrypted = decrypt(provider.encrypted_credentials)
        credentials = json.loads(decrypted)

        try:
            delete_resource(credentials, inst_id, db, user.id)
            db.delete(db_instance)
            db.commit()
            print(f" Instance {inst_id} supprimée.")
            deleted.append(inst_id)
        except Exception as e:
            print(f" Erreur suppression {inst_id} : {e}")

    if not deleted:
        raise HTTPException(status_code=404, detail="Aucune instance n’a pu être supprimée.")

    return {"deleted": deleted}


@router.post(
    "/delete_resource_direct",
    tags=["Resources"],  
    summary="Supprimer directement une instance AWS (même si non trackée en DB)"
)
async def delete_instance_direct(
    session_id: int,
    instance_id: str = Query(..., description="ID de l'instance AWS à supprimer"),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    """
    ##  Suppression directe d'instance AWS
    
    Supprime une instance AWS directement via l'API, même si elle n'est pas trackée en base locale.
    Utilise les credentials AWS de l'utilisateur pour effectuer la suppression.
    
     Authentification requise : oui (JWT)
    
    ###  Paramètres :
    - `session_id` : ID de la session (pour récupérer les credentials)
    - `instance_id` : ID de l'instance AWS (ex: i-1234567890abcdef0)
    
    ###  Réponse :
    ```json
    {
      "deleted": ["i-1234567890abcdef0"],
      "source": "direct_aws_api"
    }
    ```
    """
    session = db.query(models.Session).filter(
        models.Session.id == session_id,
        models.Session.user_id == user.id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session non trouvée.")
    
    # Récupérer le provider AWS de l'utilisateur
    provider = db.query(models.Provider).filter(
        models.Provider.user_id == user.id,
        models.Provider.provider_name == "aws"
    ).first()
    
    if not provider:
        raise HTTPException(status_code=404, detail="Aucun provider AWS configuré pour cet utilisateur.")
    
    try:
        # Déchiffrer les credentials AWS
        decrypted = decrypt(provider.encrypted_credentials)
        credentials = json.loads(decrypted)
        credentials["provider"] = "aws"  # Ensure provider is set
        
        # Appel direct à l'API AWS pour supprimer
        result = delete_resource(credentials, instance_id, db, user.id)
        
        # Si l'instance existe aussi en DB locale, la supprimer
        db_instance = db.query(models.Instance).join(models.Session).filter(
            models.Instance.instance_id == instance_id,
            models.Session.user_id == user.id
        ).first()
        
        if db_instance:
            db.delete(db_instance) 
            db.commit()
            print(f" Instance {instance_id} aussi supprimée de la DB locale")
        
        return {
            "deleted": [instance_id], 
            "source": "direct_aws_api",
            "details": result
        }
        
    except Exception as e:
        error_msg = str(e)
        
        #  Gestion spécifique des erreurs AWS
        if "InvalidInstanceID.NotFound" in error_msg:
            # L'instance n'existe plus sur AWS, nettoyage de la DB locale
            db_instance = db.query(models.Instance).join(models.Session).filter(
                models.Instance.instance_id == instance_id,
                models.Session.user_id == user.id
            ).first()
            
            if db_instance:
                db.delete(db_instance)
                db.commit()
                print(f" Instance {instance_id} supprimée de la DB locale (inexistante sur AWS)")
            
            return {
                "deleted": [instance_id],
                "source": "cleanup_db_only", 
                "details": f"Instance {instance_id} n'existait plus sur AWS, nettoyée de la DB locale"
            }
        
        # Autres erreurs
        full_error_msg = f"Erreur lors de la suppression directe : {error_msg}"
        print(f" {full_error_msg}")
        raise HTTPException(status_code=500, detail=full_error_msg)


@router.post(
    "/cleanup_obsolete_instances",
    tags=["Resources"],
    summary="Nettoyer les instances obsolètes (DB locale vs AWS réel)"
)
async def cleanup_obsolete_instances(
    session_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    """
    ##  Nettoyage des instances obsolètes
    
    Compare les instances en DB locale avec l'état réel AWS et supprime 
    les entrées DB pour les instances qui n'existent plus sur AWS.
    
     Authentification requise : oui (JWT)
    """
    session = db.query(models.Session).filter(
        models.Session.id == session_id,
        models.Session.user_id == user.id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session non trouvée.")
    
    # Récupérer le provider AWS
    provider = db.query(models.Provider).filter(
        models.Provider.user_id == user.id,
        models.Provider.provider_name == "aws"
    ).first()
    
    if not provider:
        raise HTTPException(status_code=404, detail="Aucun provider AWS configuré.")
    
    try:
        # 1. Récupérer les instances réelles AWS
        decrypted = decrypt(provider.encrypted_credentials)
        credentials = json.loads(decrypted)
        aws_instances = list_resources(credentials, db, user.id)
        aws_instance_ids = {inst["InstanceId"] for inst in aws_instances}
        
        # 2. Récupérer les instances de la DB locale
        db_instances = db.query(models.Instance).join(models.Session).filter(
            models.Session.user_id == user.id
        ).all()
        
        # 3. Identifier les instances obsolètes (en DB mais pas sur AWS)
        obsolete_instances = []
        for db_inst in db_instances:
            if db_inst.instance_id not in aws_instance_ids:
                obsolete_instances.append(db_inst)
        
        # 4. Nettoyer les instances obsolètes
        cleaned_ids = []
        for obsolete_inst in obsolete_instances:
            cleaned_ids.append(obsolete_inst.instance_id)
            db.delete(obsolete_inst)
        
        db.commit()
        
        return {
            "cleaned_count": len(cleaned_ids),
            "cleaned_instances": cleaned_ids,
            "aws_instances_found": len(aws_instances),
            "db_instances_before": len(db_instances)
        }
        
    except Exception as e:
        error_msg = f"Erreur lors du nettoyage : {str(e)}"
        print(f" {error_msg}")
        raise HTTPException(status_code=500, detail=error_msg)


@router.post(
    "/sync_aws_instances",
    tags=["Resources"],
    summary="Importer les instances AWS existantes vers la DB"
)
async def sync_aws_instances(
    session_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    """
    ##  Synchroniser les instances AWS vers la base de données
    
    Découvre toutes les instances EC2 running/stopped dans AWS et les importe en DB.
    Utile pour le mode "configure-only" quand les instances ont été créées hors système.
    
     Authentification requise : oui (JWT)
    
    ### Prérequis :
    - L'utilisateur doit avoir des credentials AWS configurés
    - La session doit exister
    
    ### Retour :
    ```json
    {
        "imported": [
            {"instance_id": "i-xxx", "name": "...", "public_ip": "...", "status": "running"}
        ],
        "count": 3
    }
    ```
    """
    # Vérifier que la session existe et appartient à l'utilisateur
    session = db.query(models.Session).filter(
        models.Session.id == session_id,
        models.Session.user_id == user.id
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session non trouvée")
    
    # Récupérer les credentials AWS de l'utilisateur
    creds = db.query(models.UserAWSCredentials).filter_by(user_id=user.id).first()
    
    if not creds:
        raise HTTPException(
            status_code=400,
            detail="Credentials AWS non configurés. Configurez-les d'abord via /user/aws-credentials"
        )
    
    try:
        from app.utils.crypto import decrypt_aws_secret
        # access_key_id n'est PAS chiffré, seulement le secret
        aws_key = creds.access_key_id
        aws_secret = decrypt_aws_secret(creds.secret_access_key_encrypted)
        region = creds.region or "eu-north-1"
        
        imported = sync_aws_instances_to_db(
            db=db,
            session_id=session_id,
            aws_access_key=aws_key,
            aws_secret_key=aws_secret,
            region=region
        )
        
        return {
            "message": f" {len(imported)} instances synchronisées",
            "imported": imported,
            "count": len(imported)
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la synchronisation AWS: {str(e)}"
        )
