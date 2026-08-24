"""
Service pour synchroniser les instances AWS réelles vers la base de données.
"""
import logging
import boto3
from typing import List, Dict
from datetime import datetime, timezone
from sqlalchemy.orm import Session as DbSession
from app.models.instance import Instance
from app.models.session import Session as SessionModel
from app.utils.crypto import encrypt

logger = logging.getLogger(__name__)


def sync_aws_instances_to_db(
    db: DbSession,
    session_id: int,
    aws_access_key: str,
    aws_secret_key: str,
    region: str = "eu-north-1"
) -> List[Dict]:
    """
    Synchronise les instances EC2 AWS vers la base de données avec upsert intelligent.
    
    Logique :
    - Compare chaque instance AWS avec la DB (par instance_id global, pas par session)
    - Si existe : update UNIQUEMENT les champs qui ont changé (public_ip, status, ssm_managed, etc.)
    - Si n'existe pas : crée une nouvelle entrée
    - Supprime les instances qui n'existent plus en AWS
    
    Args:
        db: Session SQLAlchemy
        session_id: ID de la session à associer
        aws_access_key: AWS Access Key
        aws_secret_key: AWS Secret Key
        region: Région AWS
        
    Returns:
        Liste des instances importées/mises à jour
    """
    logger.info(" [AWS Sync] Début synchronisation instances AWS région=%s", region)
    
    # Clients EC2 / SSM
    ec2 = boto3.client(
        'ec2',
        region_name=region,
        aws_access_key_id=aws_access_key,
        aws_secret_access_key=aws_secret_key
    )
    ssm_info: Dict[str, Dict] = {}
    try:
        ssm = boto3.client(
            'ssm',
            region_name=region,
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
        )
        paginator = ssm.get_paginator('describe_instance_information')
        for page in paginator.paginate():
            for info in page.get('InstanceInformationList', []):
                iid = info.get('InstanceId')
                if not iid:
                    continue
                ssm_info[iid] = {
                    "ping_status": info.get("PingStatus"),
                    "platform_type": info.get("PlatformType"),
                    "agent_version": info.get("AgentVersion"),
                }
    except Exception as e:
        logger.warning(" [AWS Sync] Impossible de récupérer le statut SSM: %s", e)
    
    # Récupérer toutes les instances (running + stopped)
    response = ec2.describe_instances(
        Filters=[
            {'Name': 'instance-state-name', 'Values': ['running', 'stopped']}
        ]
    )
    
    imported = []
    updated = []
    session = db.query(SessionModel).filter_by(id=session_id).first()
    if not session:
        raise ValueError(f"Session {session_id} introuvable")
    
    aws_ids = set()

    for reservation in response['Reservations']:
        for instance in reservation['Instances']:
            instance_id = instance['InstanceId']
            aws_ids.add(instance_id)
            public_ip = instance.get('PublicIpAddress')
            private_ip = instance.get('PrivateIpAddress')
            state = instance['State']['Name']
            
            # Capturer les infos VPC/SG
            vpc_id = instance.get('VpcId')
            subnet_id = instance.get('SubnetId')
            
            if not subnet_id and instance.get('NetworkInterfaces'):
                subnet_id = instance['NetworkInterfaces'][0].get('SubnetId')
                if not vpc_id:
                    vpc_id = instance['NetworkInterfaces'][0].get('VpcId')
            
            sg_ids = []
            if instance.get('SecurityGroups'):
                sg_ids = [sg['GroupId'] for sg in instance['SecurityGroups']]
            elif instance.get('NetworkInterfaces'):
                for ni in instance['NetworkInterfaces']:
                    for sg in ni.get('Groups', []):
                        if sg['GroupId'] not in sg_ids:
                            sg_ids.append(sg['GroupId'])
            
            sg_id = sg_ids[0] if sg_ids else None
            
            # Les instances sans IP ne sont pas acceptées
            if not public_ip and not private_ip:
                logger.warning("⏭ Instance %s ignorée (ni IP publique ni privée)", instance_id)
                continue
            
            # Récupérer le nom depuis les tags
            name = None
            for tag in instance.get('Tags', []):
                if tag['Key'] == 'Name':
                    name = tag['Value']
                    break
            if not name:
                name = f"aws-{instance_id}"
            
            # Vérifier si existe déjà (unicité globale par instance_id)
            existing = db.query(Instance).filter_by(instance_id=instance_id).first()
            ssm_status = ssm_info.get(instance_id)
            is_ssm_managed = bool(ssm_status)
            
            if existing:
                #  UPSERT : Comparer et updater UNIQUEMENT si différences
                changed = False
                
                # Comparer public_ip
                existing_public_ip = encrypt(public_ip) if public_ip else None
                if existing_public_ip and existing.public_ip != existing_public_ip:
                    existing.public_ip = existing_public_ip
                    changed = True
                
                # Comparer status
                if existing.status != state:
                    existing.status = state
                    changed = True
                
                # Comparer private_ip
                if private_ip:
                    existing_private_ip = encrypt(private_ip)
                    if existing.private_ip != existing_private_ip:
                        existing.private_ip = existing_private_ip
                        changed = True
                
                # Comparer VPC/SG/subnet
                if existing.vpc_id != vpc_id:
                    existing.vpc_id = vpc_id
                    changed = True
                if existing.subnet_id != subnet_id:
                    existing.subnet_id = subnet_id
                    changed = True
                if existing.security_group_id != sg_id:
                    existing.security_group_id = sg_id
                    changed = True
                
                # Comparer SSM status
                connection_method = "ssm" if is_ssm_managed else "ssh"
                if existing.connection_method != connection_method:
                    existing.connection_method = connection_method
                    changed = True
                if existing.ssm_managed != is_ssm_managed:
                    existing.ssm_managed = is_ssm_managed
                    changed = True
                
                # Mettre à jour session_id et timestamp (toujours)
                existing.session_id = session_id
                existing.last_synced_at = datetime.now(timezone.utc)
                
                if changed:
                    logger.info(" [AWS Sync] Mise à jour instance: %s (changements détectés)", instance_id)
                    updated.append(instance_id)
                else:
                    logger.info(" [AWS Sync] Instance %s inchangée, skip", instance_id)
            else:
                #  INSERT : Créer nouvelle instance
                logger.info(" [AWS Sync] Nouvelle instance: %s", instance_id)
                
                # Déterminer le SSH user basé sur l'AMI
                ssh_user = "ec2-user"
                if instance.get('Platform') == 'windows':
                    ssh_user = "Administrator"
                else:
                    try:
                        image_response = ec2.describe_images(ImageIds=[instance['ImageId']])
                        if image_response['Images']:
                            image_name = image_response['Images'][0].get('Name', '').lower()
                            if 'ubuntu' in image_name:
                                ssh_user = "ubuntu"
                            elif 'debian' in image_name:
                                ssh_user = "admin"
                            elif 'amzn' in image_name or 'amazon' in image_name:
                                ssh_user = "ec2-user"
                    except Exception as e:
                        logger.warning("Impossible de détecter l'AMI pour %s: %s", instance_id, e)
                
                new_instance = Instance(
                    instance_id=instance_id,
                    session_id=session_id,
                    provider="aws",
                    public_ip=encrypt(public_ip),
                    private_ip=encrypt(private_ip) if private_ip else None,
                    ssh_user=ssh_user,
                    ssh_private_key=encrypt(""),
                    name=name,
                    status=state,
                    os_family="linux" if instance.get('Platform') != 'windows' else "windows",
                    distro="unknown",
                    ssm_managed=is_ssm_managed,
                    connection_method="ssm" if is_ssm_managed else "ssh",
                    vpc_id=vpc_id,
                    subnet_id=subnet_id,
                    security_group_id=sg_id,
                    last_synced_at=datetime.now(timezone.utc)
                )
                db.add(new_instance)
                imported.append(instance_id)
            
            imported.append({
                "instance_id": instance_id,
                "name": name,
                "public_ip": public_ip,
                "status": state
            })
    
    db.commit()
    logger.info(" [AWS Sync] Synchronisation complète: %d nouvelles, %d mises à jour", 
                len(imported), len(updated))

    #  Suppression des instances obsolètes (présentes en DB mais absentes d'AWS)
    try:
        # Déterminer l'utilisateur via la session
        owner_session = session
        user_id = owner_session.user_id if owner_session else None

        if user_id is not None:
            stale_rows = (
                db.query(Instance)
                .join(SessionModel, Instance.session_id == SessionModel.id)
                .filter(SessionModel.user_id == user_id)
                .filter(Instance.provider == "aws")
                .all()
            )

            deleted = 0
            for row in stale_rows:
                if row.instance_id not in aws_ids:
                    logger.info(" [AWS Sync] Suppression instance obsolète: %s", row.instance_id)
                    db.delete(row)
                    deleted += 1
            if deleted:
                db.commit()
                logger.info(" [AWS Sync] %d instance(s) supprimée(s) car absentes d'AWS", deleted)
    except Exception as e:
        logger.warning(" [AWS Sync] Échec suppression obsolètes: %s", e)
    
    # Vérification post-sync : instances avec VPC/subnet
    instances_with_vpc = db.query(Instance).filter(
        Instance.vpc_id.isnot(None),
        Instance.subnet_id.isnot(None)
    ).all()
    
    logger.info(" [AWS Sync] Vérification VPC: %d/%d instances avec vpc_id+subnet_id", 
                len(instances_with_vpc), db.query(Instance).count())
    
    if instances_with_vpc:
        sample = instances_with_vpc[0]
        logger.info(" [AWS Sync] Sample: %s | VPC=%s | Subnet=%s | SG=%s",
                   sample.name, sample.vpc_id, sample.subnet_id, sample.security_group_id)
    
    return imported
