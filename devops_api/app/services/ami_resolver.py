"""
AMI Resolver Service - Multi-OS SSM-ready AMI selection

Resolves AMI IDs for Ubuntu, Debian, Amazon Linux 2, Windows Server
Ensures SSM agent presence or generates user_data to install it
"""
import logging
import boto3
from typing import Dict, Optional, Tuple
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class AMIResolver:
    """Resolves SSM-ready AMIs for multiple OS families."""
    
    # SSM Parameter Store paths (AWS-managed, always up-to-date)
    SSM_PARAMS = {
        "amazonlinux2": "/aws/service/ami-amazon-linux-latest/amzn2-ami-hvm-x86_64-gp2",
        "ubuntu_22_04": "/aws/service/canonical/ubuntu/server/22.04/stable/current/amd64/hvm/ebs-gp2/ami-id",
        "ubuntu_20_04": "/aws/service/canonical/ubuntu/server/20.04/stable/current/amd64/hvm/ebs-gp2/ami-id",
        "debian_12": "/aws/service/debian/release/12/latest/amd64",
        "windows_2022": "/aws/service/ami-windows-latest/Windows_Server-2022-English-Full-Base",
        "windows_2019": "/aws/service/ami-windows-latest/Windows_Server-2019-English-Full-Base",
    }
    
    # Fallback manual mapping (if SSM Parameter Store fails)
    FALLBACK_AMIS = {
        "eu-north-1": {
            "amazonlinux2": "ami-0989fb15ce71ba39e",
            "ubuntu_22_04": "ami-0d441b94e52b27d9e",
            "debian_12": "ami-0705384442bec7627",
            "windows_2022": "ami-0c6c29c5c29c2a3f9",
        },
        "eu-west-1": {
            "amazonlinux2": "ami-0d71ea30463e0ff8d",
            "ubuntu_22_04": "ami-0694d931cee176e7d",
            "debian_12": "ami-0d1bf5b68307103c2",
            "windows_2022": "ami-0c0933ae5caf0c3f7",
        },
    }
    
    def __init__(self, region: str = "eu-north-1", aws_access_key: str = None, aws_secret_key: str = None):
        """
        Initialize AMI resolver.
        
        Args:
            region: AWS region
            aws_access_key: AWS Access Key (optional, uses env/instance profile if None)
            aws_secret_key: AWS Secret Key (optional)
        """
        self.region = region
        try:
            if aws_access_key and aws_secret_key:
                self.ssm_client = boto3.client(
                    'ssm',
                    region_name=region,
                    aws_access_key_id=aws_access_key,
                    aws_secret_access_key=aws_secret_key
                )
            else:
                self.ssm_client = boto3.client('ssm', region_name=region)
        except Exception as e:
            logger.warning(" Cannot create SSM client for AMI resolver: %s", e)
            self.ssm_client = None
    
    def resolve_ami(self, os_family: str, distro: str = None, version: str = None) -> Tuple[str, Dict]:
        """
        Resolve AMI ID for given OS.
        
        Args:
            os_family: 'linux' or 'windows'
            distro: 'amazonlinux2', 'ubuntu', 'debian', 'windows'
            version: '22.04', '12', '2022', '2019', etc.
        
        Returns:
            (ami_id, metadata_dict)
            metadata includes: os_family, distro, version, ssm_agent_preinstalled, user_data_required
        """
        # Normalize inputs
        os_family = (os_family or "linux").lower()
        distro = (distro or "amazonlinux2").lower()
        version = (version or "").strip()
        
        # Build key
        if os_family == "windows":
            if distro == "windows" and version in ["2022", "2019"]:
                key = f"windows_{version}"
            else:
                key = "windows_2022"  # Default
        elif distro == "ubuntu":
            if version in ["22.04", "20.04"]:
                key = f"ubuntu_{version.replace('.', '_')}"
            else:
                key = "ubuntu_22_04"  # Default
        elif distro == "debian":
            key = "debian_12"
        else:
            key = "amazonlinux2"
        
        logger.info(" Resolving AMI: os_family=%s, distro=%s, version=%s -> key=%s",
                    os_family, distro, version, key)
        
        # Try SSM Parameter Store (official AWS-managed)
        ami_id = self._resolve_via_ssm_parameter(key)
        
        # Fallback to manual mapping
        if not ami_id:
            ami_id = self._resolve_via_fallback(key)
        
        if not ami_id:
            raise ValueError(f"Cannot resolve AMI for {os_family}/{distro}/{version} in {self.region}")
        
        # Metadata
        metadata = {
            "os_family": os_family,
            "distro": distro,
            "version": version,
            "ami_id": ami_id,
            "region": self.region,
            "ssm_agent_preinstalled": self._has_ssm_agent_preinstalled(key),
            "user_data_required": not self._has_ssm_agent_preinstalled(key),
        }
        
        logger.info(" AMI resolved: %s -> %s (SSM agent: %s)",
                    key, ami_id, "preinstalled" if metadata["ssm_agent_preinstalled"] else "needs install")
        
        return ami_id, metadata
    
    def _resolve_via_ssm_parameter(self, key: str) -> Optional[str]:
        """Resolve AMI via SSM Parameter Store (AWS-managed)."""
        if not self.ssm_client:
            return None
        
        param_path = self.SSM_PARAMS.get(key)
        if not param_path:
            return None
        
        try:
            response = self.ssm_client.get_parameter(Name=param_path)
            ami_id = response['Parameter']['Value']
            logger.info(" AMI from SSM Parameter Store: %s -> %s", param_path, ami_id)
            return ami_id
        except ClientError as e:
            logger.warning(" SSM Parameter Store failed for %s: %s", param_path, e)
            return None
        except Exception as e:
            logger.warning(" Unexpected error fetching SSM parameter %s: %s", param_path, e)
            return None
    
    def _resolve_via_fallback(self, key: str) -> Optional[str]:
        """Fallback to manual mapping."""
        region_map = self.FALLBACK_AMIS.get(self.region, {})
        ami_id = region_map.get(key)
        if ami_id:
            logger.info(" AMI from fallback mapping: %s -> %s", key, ami_id)
        return ami_id
    
    def _has_ssm_agent_preinstalled(self, key: str) -> bool:
        """Check if AMI has SSM agent preinstalled."""
        # Amazon Linux 2 and Windows Server AMIs have SSM agent by default
        if key.startswith("amazonlinux") or key.startswith("windows"):
            return True
        # Ubuntu 22.04+ official AMIs often have SSM agent
        if key == "ubuntu_22_04":
            return True  # Recent Ubuntu AMIs include SSM agent
        # Debian and older Ubuntu need manual install
        return False
    
    def generate_user_data(self, os_family: str, distro: str) -> str:
        """
        Generate user_data script to install SSM agent if needed.
        
        Args:
            os_family: 'linux' or 'windows'
            distro: OS distribution
        
        Returns:
            user_data script (bash or PowerShell)
        """
        os_family = os_family.lower()
        distro = distro.lower()
        
        if os_family == "windows":
            return self._generate_windows_user_data()
        elif distro in ["ubuntu", "debian"]:
            return self._generate_debian_ubuntu_user_data(distro)
        else:
            # Amazon Linux 2 or other (SSM preinstalled, minimal user_data)
            return self._generate_amazonlinux_user_data()
    
    def _generate_amazonlinux_user_data(self) -> str:
        """Amazon Linux 2 user_data (SSM agent already present)."""
        return """#!/bin/bash
# Amazon Linux 2 - SSM agent preinstalled
# Ensure service is running
systemctl enable amazon-ssm-agent
systemctl start amazon-ssm-agent
"""
    
    def _generate_debian_ubuntu_user_data(self, distro: str) -> str:
        """Ubuntu/Debian user_data to install SSM agent."""
        return f"""#!/bin/bash
# {distro.capitalize()} - Install SSM agent
set -e

# Update package lists
apt-get update -y

# Install SSM agent
cd /tmp
wget https://s3.amazonaws.com/ec2-downloads-windows/SSMAgent/latest/debian_amd64/amazon-ssm-agent.deb
dpkg -i amazon-ssm-agent.deb || apt-get install -f -y

# Enable and start service
systemctl enable amazon-ssm-agent
systemctl start amazon-ssm-agent

# Verify
systemctl status amazon-ssm-agent --no-pager || true
"""
    
    def _generate_windows_user_data(self) -> str:
        """Windows user_data to ensure SSM agent is running."""
        return """<powershell>
# Windows Server - Ensure SSM agent is running
# Most Windows Server AMIs have SSM agent preinstalled

# Check if service exists
$service = Get-Service -Name AmazonSSMAgent -ErrorAction SilentlyContinue

if ($service) {
    Write-Host "SSM Agent found, ensuring it's running..."
    Set-Service -Name AmazonSSMAgent -StartupType Automatic
    Start-Service -Name AmazonSSMAgent -ErrorAction SilentlyContinue
    Get-Service -Name AmazonSSMAgent
} else {
    Write-Host "SSM Agent not found, installing..."
    # Download and install SSM agent
    $url = "https://s3.amazonaws.com/ec2-downloads-windows/SSMAgent/latest/windows_amd64/AmazonSSMAgentSetup.exe"
    $output = "$env:TEMP\\AmazonSSMAgentSetup.exe"
    Invoke-WebRequest -Uri $url -OutFile $output
    Start-Process -FilePath $output -ArgumentList "/S" -Wait
    Start-Service -Name AmazonSSMAgent
}
</powershell>
"""


def resolve_ami_for_create(
    os_family: str = "linux",
    distro: str = "amazonlinux2",
    version: str = None,
    region: str = "eu-north-1",
    aws_access_key: str = None,
    aws_secret_key: str = None
) -> Dict:
    """
    Convenience function to resolve AMI + generate user_data.
    
    Returns:
        {
            "ami_id": "ami-xxx",
            "user_data": "#!/bin/bash...",
            "metadata": {...}
        }
    """
    resolver = AMIResolver(region, aws_access_key, aws_secret_key)
    ami_id, metadata = resolver.resolve_ami(os_family, distro, version)
    
    user_data = ""
    if metadata["user_data_required"]:
        user_data = resolver.generate_user_data(os_family, distro)
    
    return {
        "ami_id": ami_id,
        "user_data": user_data,
        "metadata": metadata,
    }
