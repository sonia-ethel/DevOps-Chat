import logging
logger = logging.getLogger(__name__)

import boto3
from botocore.exceptions import ClientError
from app.models.resource_action_log import ResourceActionLog
from azure.identity import ClientSecretCredential
from azure.mgmt.compute import ComputeManagementClient
from google.oauth2 import service_account
from googleapiclient.discovery import build


def list_resources(provider_credentials: dict, db, user_id: int) -> list:
    provider = provider_credentials.get("provider", "aws").lower()
    instances_info = []
    status = "success"
    details = ""

    try:
        if provider == "aws":
            logger.info(" [AWS] Initialisation de la session EC2")
            ec2 = boto3.client(
                "ec2",
                aws_access_key_id=provider_credentials["AWS_ACCESS_KEY_ID"],
                aws_secret_access_key=provider_credentials["AWS_SECRET_ACCESS_KEY"],
                region_name=provider_credentials.get("region", "eu-west-1")
            )
            #  Filtrer seulement les instances actives (exclure terminated, shutting-down)
            response = ec2.describe_instances(
                Filters=[
                    {
                        'Name': 'instance-state-name',
                        'Values': ['pending', 'running', 'stopping', 'stopped']
                    }
                ]
            )
            for reservation in response["Reservations"]:
                for instance in reservation["Instances"]:
                    state = instance["State"]["Name"]
                    
                    # Double vérification: ne pas inclure les instances terminated
                    if state in ['terminated', 'shutting-down', 'terminating']:
                        continue
                        
                    instances_info.append({
                        "InstanceId": instance["InstanceId"],
                        "State": state,
                        "PublicIp": instance.get("PublicIpAddress"),
                        "PrivateIp": instance.get("PrivateIpAddress"),
                        "LaunchTime": str(instance["LaunchTime"])
                    })
            details = f"{len(instances_info)} instance(s) AWS listée(s)."

        elif provider == "azure":
            logger.info(" [Azure] Initialisation de la session ComputeManagementClient")
            credentials = ClientSecretCredential(
                tenant_id=provider_credentials["tenant_id"],
                client_id=provider_credentials["client_id"],
                client_secret=provider_credentials["client_secret"]
            )
            compute_client = ComputeManagementClient(
                credentials,
                provider_credentials["subscription_id"]
            )
            for vm in compute_client.virtual_machines.list_all():
                instances_info.append({
                    "InstanceId": vm.id,
                    "Name": vm.name,
                    "Location": vm.location,
                    "Type": vm.type
                })
            details = f"{len(instances_info)} VM(s) Azure listée(s)."

        elif provider == "gcp":
            logger.info(" [GCP] Initialisation de la session GCP Compute")
            credentials = service_account.Credentials.from_service_account_info(
                provider_credentials["service_account"]
            )
            service = build("compute", "v1", credentials=credentials)
            project = provider_credentials["project_id"]
            zones = provider_credentials.get("zones", ["europe-west1-b"])

            for zone in zones:
                result = service.instances().list(project=project, zone=zone).execute()
                for instance in result.get("items", []):
                    instances_info.append({
                        "InstanceId": instance["id"],
                        "Name": instance["name"],
                        "Status": instance["status"],
                        "Zone": zone
                    })
            details = f"{len(instances_info)} instance(s) GCP listée(s)."

        else:
            raise Exception("Provider non supporté : " + provider)

        logger.info(f" [{provider.upper()}] {details}")

    except Exception as e:
        status = "failure"
        details = str(e)
        logger.info(f" [{provider.upper()}] list_resources failed: {details}")
        raise

    finally:
        log = ResourceActionLog(
            user_id=user_id,
            action="list",
            resource_id=None,
            status=status,
            details=details
        )
        db.add(log)
        db.commit()
        logger.info(" [LOG] Log enregistré.")

    return instances_info


def delete_resource(provider_credentials: dict, instance_id: str, db, user_id: int) -> str:
    provider = provider_credentials.get("provider", "aws").lower()
    status = "success"
    details = ""

    try:
        if provider == "aws":
            logger.info(f" [AWS] Suppression de l'instance {instance_id}")
            ec2 = boto3.client(
                "ec2",
                aws_access_key_id=provider_credentials["AWS_ACCESS_KEY_ID"],
                aws_secret_access_key=provider_credentials["AWS_SECRET_ACCESS_KEY"],
                region_name=provider_credentials.get("region", "eu-west-1")
            )
            ec2.terminate_instances(InstanceIds=[instance_id])
            details = f"Instance {instance_id} AWS en cours de suppression."

        elif provider == "azure":
            logger.info(f" [Azure] Suppression de la VM {instance_id}")
            credentials = ClientSecretCredential(
                tenant_id=provider_credentials["tenant_id"],
                client_id=provider_credentials["client_id"],
                client_secret=provider_credentials["client_secret"]
            )
            compute_client = ComputeManagementClient(
                credentials,
                provider_credentials["subscription_id"]
            )
            resource_group = provider_credentials["resource_group"]
            async_delete = compute_client.virtual_machines.begin_delete(resource_group, instance_id)
            async_delete.wait()
            details = f"VM {instance_id} Azure supprimée."

        elif provider == "gcp":
            logger.info(f" [GCP] Suppression de l'instance {instance_id}")
            credentials = service_account.Credentials.from_service_account_info(
                provider_credentials["service_account"]
            )
            service = build("compute", "v1", credentials=credentials)
            project = provider_credentials["project_id"]
            zone = provider_credentials["zone"]  # obligatoire ici
            service.instances().delete(project=project, zone=zone, instance=instance_id).execute()
            details = f"Instance {instance_id} GCP supprimée."

        else:
            raise Exception("Provider non supporté : " + provider)

        logger.info(f" [{provider.upper()}] {details}")
        return details

    except Exception as e:
        status = "failure"
        details = str(e)
        logger.info(f" [{provider.upper()}] delete_resource failed: {details}")
        raise

    finally:
        log = ResourceActionLog(
            user_id=user_id,
            action="delete",
            resource_id=instance_id,
            status=status,
            details=details
        )
        db.add(log)
        db.commit()
logger.info(" [LOG] Log enregistré.")