"""
VPC Diagnostics Service - P0.4

Diagnostique l'état du VPC et des subnets pour une région donnée.
Utilisé par le chatbot pour vérifier la disponibilité de l'infrastructure.
"""

import boto3
import logging
from typing import Dict, Any, List, Optional
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class VPCDiagnostics:
    """Service pour diagnostiquer l'état du VPC et subnets."""
    
    def __init__(self, region: str = "eu-north-1"):
        self.region = region
    
    def run_diagnostics(
        self,
        aws_access_key_id: str,
        aws_secret_access_key: str
    ) -> Dict[str, Any]:
        """
        Diagnostique complet VPC/Subnets.
        
        Returns:
            {
                "status": "ok|warning|error",
                "vpcs": [
                    {
                        "vpc_id": "vpc-xxx",
                        "cidr": "10.0.0.0/16",
                        "dac_managed": True/False,
                        "subnets": [
                            {
                                "subnet_id": "subnet-xxx",
                                "cidr": "10.0.1.0/24",
                                "available_ips": 251,
                                "az": "eu-north-1a"
                            }
                        ]
                    }
                ],
                "default_vpc": {"vpc_id": "vpc-xxx", ...},
                "summary": "Human-readable summary",
                "warnings": ["warning 1", "warning 2"],
                "errors": None or error_message
            }
        """
        try:
            ec2 = boto3.client(
                'ec2',
                region_name=self.region,
                aws_access_key_id=aws_access_key_id,
                aws_secret_access_key=aws_secret_access_key
            )
            
            # Check VPC permissions
            try:
                ec2.describe_vpcs(MaxResults=5)
            except ClientError as e:
                if 'UnauthorizedOperation' in str(e) or 'Unauthorized' in str(e):
                    return {
                        "status": "error",
                        "vpcs": [],
                        "default_vpc": None,
                        "summary": "[Error] Permissions insuffisantes pour accéder aux VPCs",
                        "warnings": [],
                        "errors": "UnauthorizedOperation: Permissions insuffisantes"
                    }
                raise
            
            # Get all VPCs
            vpcs_response = ec2.describe_vpcs()
            vpcs = vpcs_response.get('Vpcs', [])
            
            if not vpcs:
                return {
                    "status": "error",
                    "vpcs": [],
                    "default_vpc": None,
                    "summary": "[Error] Aucun VPC trouvé dans cette région",
                    "warnings": [],
                    "errors": "No VPCs found in region"
                }
            
            # Get subnets
            subnets_response = ec2.describe_subnets()
            subnets_by_vpc = {}
            for subnet in subnets_response.get('Subnets', []):
                vpc_id = subnet['VpcId']
                if vpc_id not in subnets_by_vpc:
                    subnets_by_vpc[vpc_id] = []
                subnets_by_vpc[vpc_id].append(subnet)
            
            # Build VPC details
            vpc_details = []
            default_vpc = None
            dac_managed_vpc = None
            
            for vpc in vpcs:
                vpc_id = vpc['VpcId']
                is_default = vpc.get('IsDefault', False)
                
                # Check for DAC tags
                tags = {tag['Key']: tag['Value'] for tag in vpc.get('Tags', [])}
                is_dac = tags.get('dac_managed') == 'true'
                
                subnet_list = []
                for subnet in subnets_by_vpc.get(vpc_id, []):
                    # Calculate available IPs
                    cidr_block = subnet['CidrBlock']
                    # Simple calculation: /24 = 256 - 5 reserved AWS = 251
                    # /25 = 128 - 5 = 123, etc.
                    available_ips = self._calculate_available_ips(cidr_block)
                    
                    subnet_list.append({
                        "subnet_id": subnet['SubnetId'],
                        "cidr": cidr_block,
                        "available_ips": available_ips,
                        "az": subnet['AvailabilityZone'],
                        "state": subnet['State']
                    })
                
                vpc_info = {
                    "vpc_id": vpc_id,
                    "cidr": vpc['CidrBlock'],
                    "dac_managed": is_dac,
                    "is_default": is_default,
                    "state": vpc['State'],
                    "subnets": subnet_list,
                    "total_subnets": len(subnet_list)
                }
                
                vpc_details.append(vpc_info)
                
                if is_default:
                    default_vpc = vpc_info
                if is_dac:
                    dac_managed_vpc = vpc_info
            
            # Determine overall status
            status = "ok"
            warnings = []
            
            # Check for DAC-managed VPC
            if not dac_managed_vpc:
                warnings.append("[Warning] Aucun VPC tagué dac_managed=true trouvé")
            
            # Check if default VPC has subnets
            if default_vpc and default_vpc['total_subnets'] == 0:
                warnings.append("[Warning] Le VPC par défaut n'a pas de subnets")
                status = "warning"
            
            # Check for available IPs
            for vpc in vpc_details:
                for subnet in vpc['subnets']:
                    if subnet['available_ips'] < 10:
                        warnings.append(f"[Warning] Subnet {subnet['subnet_id']} a peu d'IPs disponibles ({subnet['available_ips']})")
                        status = "warning"
            
            # Build summary
            if dac_managed_vpc:
                summary = f"[Success] VPC DAC-managed: {dac_managed_vpc['vpc_id']} ({dac_managed_vpc['total_subnets']} subnets)"
            elif default_vpc:
                summary = f"[Success] VPC par défaut: {default_vpc['vpc_id']} ({default_vpc['total_subnets']} subnets)"
            else:
                summary = f"[Warning] {len(vpc_details)} VPC(s) disponibles, mais aucun optimisé pour DAC"
            
            if warnings:
                status = "warning"
            
            return {
                "status": status,
                "vpcs": vpc_details,
                "default_vpc": default_vpc,
                "dac_managed_vpc": dac_managed_vpc,
                "summary": summary,
                "warnings": warnings,
                "errors": None
            }
        
        except Exception as e:
            logger.error(f"VPC diagnostics failed: {e}")
            return {
                "status": "error",
                "vpcs": [],
                "default_vpc": None,
                "summary": f"[Error] Erreur lors du diagnostic: {str(e)[:100]}",
                "warnings": [],
                "errors": str(e)
            }
    
    def _calculate_available_ips(self, cidr_block: str) -> int:
        """
        Calcule approximativement le nombre d'IPs disponibles.
        AWS réserve les 5 premières IPs: .0, .1, .2, .3, .255
        """
        try:
            mask = int(cidr_block.split('/')[1])
            total_ips = 2 ** (32 - mask)
            return max(0, total_ips - 5)  # 5 réservées par AWS
        except:
            return 0


def run_vpc_diagnostics(
    aws_access_key_id: str,
    aws_secret_access_key: str,
    region: str = "eu-north-1"
) -> Dict[str, Any]:
    """Factory function pour lancer les diagnostics VPC."""
    service = VPCDiagnostics(region=region)
    return service.run_diagnostics(aws_access_key_id, aws_secret_access_key)
