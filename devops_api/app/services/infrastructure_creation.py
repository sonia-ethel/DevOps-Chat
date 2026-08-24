"""
Infrastructure Creation Service - P0.5

Crée les ressources AWS de base (VPC, subnets, instances EC2 avec SSM agent).
Utilisé par le chatbot pour créer l'infrastructure à la demande de l'utilisateur.
"""

import boto3
import logging
import json
from typing import Dict, Any, List, Optional
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class InfrastructureCreation:
    """Service pour créer l'infrastructure de base (VPC, subnets, instances)."""
    
    def __init__(self, region: str = "eu-north-1"):
        self.region = region
        self.ubuntu_amis = {
            "eu-north-1": {
                "22.04": "ami-00c5cec9e5dd94f06",  # Ubuntu 22.04 LTS HVM
                "20.04": "ami-0c7c85e8fe4651225",  # Ubuntu 20.04 LTS HVM
                "24.04": "ami-035f10d3f84f7c70b",  # Ubuntu 24.04 LTS HVM (if available)
            },
            "eu-west-1": {
                "22.04": "ami-0d2a4a5d69e46ea0b",
                "20.04": "ami-0f540e9444e9b0b41",
            }
        }
    
    def create_basic_infrastructure(
        self,
        aws_access_key_id: str,
        aws_secret_access_key: str,
        instance_count: int = 1,
        instance_type: str = "t3.micro",
        ubuntu_version: str = "22.04",
        vpc_name: str = "DAC-VPC",
        enable_ssm: bool = True
    ) -> Dict[str, Any]:
        """
        Crée l'infrastructure de base avec VPC, subnets, et instances EC2.
        
        Args:
            aws_access_key_id: AWS access key
            aws_secret_access_key: AWS secret key
            instance_count: Nombre d'instances à créer (1-5)
            instance_type: Type d'instance (t3.micro, t3.small, etc.)
            ubuntu_version: Version Ubuntu (20.04, 22.04, 24.04)
            vpc_name: Nom du VPC
            enable_ssm: Attacher le profil IAM pour SSM
        
        Returns:
            {
                "status": "created|error",
                "vpc": {"vpc_id": "vpc-xxx", "cidr": "10.0.0.0/16"},
                "subnets": [{"subnet_id": "subnet-xxx", ...}],
                "security_group": {"sg_id": "sg-xxx", ...},
                "instances": [{"instance_id": "i-xxx", "ip": "10.0.1.10", ...}],
                "iam_role": {"role_name": "DAC-SSM-Role", ...},
                "summary": "Human-readable summary",
                "errors": None or error_message
            }
        """
        try:
            # Validate inputs
            if not (1 <= instance_count <= 5):
                return self._error_response("instance_count doit être entre 1 et 5")
            
            if ubuntu_version not in self.ubuntu_amis.get(self.region, {}):
                available = list(self.ubuntu_amis.get(self.region, {}).keys())
                return self._error_response(
                    f"Ubuntu {ubuntu_version} non disponible. Versions: {available}"
                )
            
            ec2 = boto3.client(
                'ec2',
                region_name=self.region,
                aws_access_key_id=aws_access_key_id,
                aws_secret_access_key=aws_secret_access_key
            )
            
            iam = boto3.client(
                'iam',
                aws_access_key_id=aws_access_key_id,
                aws_secret_access_key=aws_secret_access_key
            )
            
            # Check for existing DAC infrastructure
            existing_vpcs = ec2.describe_vpcs(Filters=[
                {'Name': 'tag:dac_managed', 'Values': ['true']}
            ])
            
            if existing_vpcs['Vpcs']:
                # Réutiliser VPC existant
                vpc_id = existing_vpcs['Vpcs'][0]['VpcId']
                logger.info(f"Réutilisant VPC DAC existant: {vpc_id}")
                vpc = existing_vpcs['Vpcs'][0]
            else:
                # Créer nouveau VPC
                vpc = ec2.create_vpc(CidrBlock='10.0.0.0/16')['Vpc']
                vpc_id = vpc['VpcId']
                logger.info(f"VPC créé: {vpc_id}")
                
                # Tag VPC
                ec2.create_tags(Resources=[vpc_id], Tags=[
                    {'Key': 'Name', 'Value': vpc_name},
                    {'Key': 'dac_managed', 'Value': 'true'},
                    {'Key': 'dac_scope', 'Value': 'create_basic'},
                ])
                
                # Enable DNS
                ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsHostnames={'Value': True})
                ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsSupport={'Value': True})
            
            # Get or create subnets
            subnets_response = ec2.describe_subnets(Filters=[
                {'Name': 'vpc-id', 'Values': [vpc_id]}
            ])
            
            subnets = subnets_response['Subnets']
            
            if not subnets:
                # Créer subnets (2 dans différentes AZs)
                subnet1 = ec2.create_subnet(
                    VpcId=vpc_id,
                    CidrBlock='10.0.1.0/24',
                    AvailabilityZone=f'{self.region}a'
                )['Subnet']
                
                subnet2 = ec2.create_subnet(
                    VpcId=vpc_id,
                    CidrBlock='10.0.2.0/24',
                    AvailabilityZone=f'{self.region}b'
                )['Subnet']
                
                subnets = [subnet1, subnet2]
                logger.info(f"Subnets créés: {subnet1['SubnetId']}, {subnet2['SubnetId']}")
                
                # Tag subnets
                for subnet in subnets:
                    ec2.create_tags(Resources=[subnet['SubnetId']], Tags=[
                        {'Key': 'dac_managed', 'Value': 'true'}
                    ])
            
            # Get or create security group
            sg_response = ec2.describe_security_groups(Filters=[
                {'Name': 'vpc-id', 'Values': [vpc_id]},
                {'Name': 'tag:dac_managed', 'Values': ['true']}
            ])
            
            if sg_response['SecurityGroups']:
                sg = sg_response['SecurityGroups'][0]
            else:
                sg = ec2.create_security_group(
                    GroupName=f'dac-sg-basic-{vpc_id[-8:]}',
                    Description='DAC basic infrastructure security group',
                    VpcId=vpc_id
                )
                sg['GroupId'] = sg['id']
                
                # Allow SSH from anywhere (for demo)
                ec2.authorize_security_group_ingress(
                    GroupId=sg['GroupId'],
                    IpPermissions=[
                        {
                            'IpProtocol': 'tcp',
                            'FromPort': 22,
                            'ToPort': 22,
                            'IpRanges': [{'CidrIp': '0.0.0.0/0', 'Description': 'SSH'}]
                        },
                        {
                            'IpProtocol': 'tcp',
                            'FromPort': 443,
                            'ToPort': 443,
                            'IpRanges': [{'CidrIp': '0.0.0.0/0', 'Description': 'HTTPS'}]
                        }
                    ]
                )
                
                # Tag SG
                ec2.create_tags(Resources=[sg['GroupId']], Tags=[
                    {'Key': 'dac_managed', 'Value': 'true'}
                ])
                
                logger.info(f"Security Group créé: {sg['GroupId']}")
            
            # Create or get IAM role for SSM
            iam_role = None
            if enable_ssm:
                try:
                    iam_role = self._create_or_get_iam_role(iam)
                except Exception as e:
                    logger.warning(f"Couldn't create IAM role: {e}")
            
            # Get AMI
            ami_id = self.ubuntu_amis[self.region][ubuntu_version]
            
            # Launch instances
            instances = []
            instance_ids = []
            
            for i in range(instance_count):
                # Alternate between subnets
                subnet_id = subnets[i % len(subnets)]['SubnetId']
                
                # Prepare UserData for SSM agent installation
                user_data_script = self._get_user_data(ubuntu_version if enable_ssm else None)
                
                # Launch instance
                launch_response = ec2.run_instances(
                    ImageId=ami_id,
                    MinCount=1,
                    MaxCount=1,
                    InstanceType=instance_type,
                    SubnetId=subnet_id,
                    SecurityGroupIds=[sg['GroupId']],
                    IamInstanceProfile={'Name': iam_role['Role']['RoleName']} if iam_role else {},
                    UserData=user_data_script,
                    TagSpecifications=[
                        {
                            'ResourceType': 'instance',
                            'Tags': [
                                {'Key': 'Name', 'Value': f'dac-instance-{i+1}'},
                                {'Key': 'dac_managed', 'Value': 'true'},
                                {'Key': 'dac_scope', 'Value': 'create_basic'}
                            ]
                        }
                    ]
                )
                
                instance = launch_response['Instances'][0]
                instance_ids.append(instance['InstanceId'])
                instances.append({
                    'instance_id': instance['InstanceId'],
                    'state': instance['State']['Name'],
                    'subnet_id': subnet_id,
                    'private_ip': instance.get('PrivateIpAddress', 'N/A'),
                    'public_ip': instance.get('PublicIpAddress', 'Pending...'),
                })
                logger.info(f"Instance créée: {instance['InstanceId']}")
            
            # Build response
            return {
                "status": "created",
                "vpc": {
                    "vpc_id": vpc_id,
                    "cidr": vpc.get('CidrBlock', '10.0.0.0/16'),
                    "state": vpc.get('State', 'available')
                },
                "subnets": [
                    {
                        "subnet_id": s['SubnetId'],
                        "cidr": s['CidrBlock'],
                        "az": s['AvailabilityZone']
                    }
                    for s in subnets
                ],
                "security_group": {
                    "sg_id": sg['GroupId'],
                    "group_name": sg.get('GroupName', 'N/A'),
                    "vpc_id": sg['VpcId']
                },
                "instances": instances,
                "iam_role": {
                    "role_name": iam_role['Role']['RoleName'],
                    "arn": iam_role['Role']['Arn']
                } if iam_role else None,
                "summary": f" Infrastructure créée: 1 VPC ({vpc_id}), {len(subnets)} subnets, {len(instances)} instances",
                "errors": None
            }
        
        except Exception as e:
            logger.error(f"Infrastructure creation failed: {e}")
            return self._error_response(str(e))
    
    def _create_or_get_iam_role(self, iam):
        """Crée ou récupère le rôle IAM pour SSM."""
        role_name = "DAC-SSM-Role"
        
        try:
            # Essayer de récupérer le rôle existant
            role = iam.get_role(RoleName=role_name)
            logger.info(f"Rôle IAM existant: {role_name}")
            return role
        except ClientError as e:
            if e.response['Error']['Code'] != 'NoSuchEntity':
                raise
        
        # Créer le rôle
        assume_role_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {
                        "Service": "ec2.amazonaws.com"
                    },
                    "Action": "sts:AssumeRole"
                }
            ]
        }
        
        role = iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(assume_role_policy),
            Description="Role for DAC EC2 instances with SSM access"
        )
        
        # Attach SSM policy
        iam.attach_role_policy(
            RoleName=role_name,
            PolicyArn='arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore'
        )
        
        # Create instance profile
        try:
            iam.create_instance_profile(InstanceProfileName=role_name)
        except ClientError as e:
            if 'EntityAlreadyExists' not in str(e):
                raise
        
        # Add role to instance profile
        try:
            iam.add_role_to_instance_profile(
                InstanceProfileName=role_name,
                RoleName=role_name
            )
        except ClientError as e:
            if 'NoSuchEntity' not in str(e) and 'EntityAlreadyExists' not in str(e):
                raise
        
        logger.info(f"Rôle IAM créé: {role_name}")
        return iam.get_role(RoleName=role_name)
    
    def _get_user_data(self, ubuntu_version: Optional[str]) -> str:
        """Génère le script UserData pour installer l'agent SSM."""
        if not ubuntu_version:
            return ""
        
        # UserData script for Ubuntu with SSM agent
        script = """#!/bin/bash
apt-get update
apt-get install -y amazon-ssm-agent
systemctl enable amazon-ssm-agent
systemctl start amazon-ssm-agent
echo "DAC_OK" > /var/log/dac-init.log
"""
        return script
    
    def _error_response(self, error_msg: str) -> Dict[str, Any]:
        """Retourne une réponse d'erreur standardisée."""
        return {
            "status": "error",
            "vpc": None,
            "subnets": [],
            "security_group": None,
            "instances": [],
            "iam_role": None,
            "summary": f" {error_msg}",
            "errors": error_msg
        }


def create_basic_infrastructure(
    aws_access_key_id: str,
    aws_secret_access_key: str,
    instance_count: int = 1,
    instance_type: str = "t3.micro",
    ubuntu_version: str = "22.04",
    region: str = "eu-north-1"
) -> Dict[str, Any]:
    """Factory function pour créer l'infrastructure."""
    service = InfrastructureCreation(region=region)
    return service.create_basic_infrastructure(
        aws_access_key_id,
        aws_secret_access_key,
        instance_count=instance_count,
        instance_type=instance_type,
        ubuntu_version=ubuntu_version,
        enable_ssm=True
    )
