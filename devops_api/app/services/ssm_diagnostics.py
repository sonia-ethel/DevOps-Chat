"""
SSM Diagnostics Service - Complete SSM health check

Provides detailed diagnostic for SSM readiness:
- Total instances (DB vs AWS)
- SSM Online vs Blocked
- Block reasons (IAM, agent, network, permissions)
"""
import logging
import boto3
from typing import Dict, List
from sqlalchemy.orm import Session as DbSession
from botocore.exceptions import ClientError

from app.models.instance import Instance

logger = logging.getLogger(__name__)


class SSMDiagnostics:
    """SSM diagnostic service."""
    
    def __init__(
        self,
        db: DbSession,
        region: str = "eu-north-1",
        aws_access_key: str = None,
        aws_secret_key: str = None
    ):
        """
        Initialize SSM diagnostics.
        
        Args:
            db: Database session
            region: AWS region
            aws_access_key: AWS Access Key
            aws_secret_key: AWS Secret Key
        """
        self.db = db
        self.region = region
        self.aws_access_key = aws_access_key
        self.aws_secret_key = aws_secret_key
        
        # Initialize AWS clients
        try:
            if aws_access_key and aws_secret_key:
                self.ec2_client = boto3.client(
                    'ec2',
                    region_name=region,
                    aws_access_key_id=aws_access_key,
                    aws_secret_access_key=aws_secret_key
                )
                self.ssm_client = boto3.client(
                    'ssm',
                    region_name=region,
                    aws_access_key_id=aws_access_key,
                    aws_secret_access_key=aws_secret_key
                )
            else:
                self.ec2_client = boto3.client('ec2', region_name=region)
                self.ssm_client = boto3.client('ssm', region_name=region)
        except Exception as e:
            logger.error("[SSM] Cannot initialize AWS clients: %s", e)
            self.ec2_client = None
            self.ssm_client = None
    
    def run_full_diagnostic(self) -> Dict:
        """
        Run complete SSM diagnostic.
        
        Returns:
            {
                "total_instances_db": int,
                "total_instances_aws": int,
                "total_ssm_managed_db": int,
                "total_ssm_online_aws": int,
                "online_instances": [...],
                "blocked_instances": [{"instance_id": "i-xxx", "block_reason": "NO_IAM_PROFILE"}],
                "permissions_check": {"status": "ok|failed", "error": "..."},
                "summary": "..."
            }
        """
        result = {
            "total_instances_db": 0,
            "total_instances_aws": 0,
            "total_ssm_managed_db": 0,
            "total_ssm_online_aws": 0,
            "online_instances": [],
            "blocked_instances": [],
            "permissions_check": {"status": "unknown"},
            "summary": "",
        }
        
        # 1. Count instances in DB
        total_db = self.db.query(Instance).count()
        ssm_managed_db = self.db.query(Instance).filter(Instance.ssm_managed == True).count()
        
        result["total_instances_db"] = total_db
        result["total_ssm_managed_db"] = ssm_managed_db
        
        # 2. Check AWS permissions (preflight)
        perm_check = self._check_ssm_permissions()
        result["permissions_check"] = perm_check
        
        if perm_check["status"] != "ok":
            result["summary"] = f"[Warning] SSM permissions check failed: {perm_check.get('error', 'Unknown')}"
            return result
        
        # 3. Query AWS EC2 instances
        aws_instances = self._fetch_aws_instances()
        result["total_instances_aws"] = len(aws_instances)
        
        # 4. Query SSM managed instances
        ssm_info = self._fetch_ssm_managed_instances()
        
        # 5. Classify instances
        online = []
        blocked = []
        
        for inst in aws_instances:
            instance_id = inst["instance_id"]
            ssm_status = ssm_info.get(instance_id)
            
            if ssm_status and ssm_status.get("ping_status") == "Online":
                # Online
                online.append({
                    "instance_id": instance_id,
                    "os_platform": ssm_status.get("platform_type", "unknown"),
                    "ping_status": "Online",
                    "agent_version": ssm_status.get("agent_version", "unknown"),
                })
            else:
                # Blocked - determine reason
                block_reason = self._determine_block_reason(inst, ssm_status)
                blocked.append({
                    "instance_id": instance_id,
                    "block_reason": block_reason,
                })
        
        result["total_ssm_online_aws"] = len(online)
        result["online_instances"] = online
        result["blocked_instances"] = blocked
        
        # 6. Summary
        result["summary"] = self._generate_summary(result)
        
        return result
    
    def _check_ssm_permissions(self) -> Dict:
        """
        Preflight check: verify SSM permissions.
        
        Returns:
            {"status": "ok|failed", "error": "..."}
        """
        if not self.ssm_client:
            return {"status": "failed", "error": "SSM client not initialized (missing credentials?)"}
        
        try:
            # Test call: DescribeInstanceInformation (minimal permissions)
            # MaxResults must be >= 5
            self.ssm_client.describe_instance_information(MaxResults=5)
            return {"status": "ok"}
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_msg = e.response.get('Error', {}).get('Message', str(e))
            
            if error_code == "AccessDeniedException":
                return {
                    "status": "failed",
                    "error": f"IAM permissions denied: {error_msg}",
                    "suggestion": "Grant ssm:DescribeInstanceInformation, ssm:SendCommand, ssm:GetCommandInvocation"
                }
            else:
                return {"status": "failed", "error": f"{error_code}: {error_msg}"}
        except Exception as e:
            return {"status": "failed", "error": str(e)}
    
    def _fetch_aws_instances(self) -> List[Dict]:
        """
        Fetch all EC2 instances from AWS.
        
        Returns:
            [{"instance_id": "i-xxx", "iam_profile": "...", "state": "running"}, ...]
        """
        if not self.ec2_client:
            return []
        
        instances = []
        try:
            paginator = self.ec2_client.get_paginator('describe_instances')
            for page in paginator.paginate():
                for reservation in page['Reservations']:
                    for inst in reservation['Instances']:
                        instances.append({
                            "instance_id": inst['InstanceId'],
                            "state": inst['State']['Name'],
                            "iam_profile": inst.get('IamInstanceProfile', {}).get('Arn'),
                        })
        except Exception as e:
            logger.error("[SSM] Cannot fetch EC2 instances: %s", e)
        
        return instances
    
    def _fetch_ssm_managed_instances(self) -> Dict[str, Dict]:
        """
        Fetch SSM managed instances.
        
        Returns:
            {
                "i-xxx": {"ping_status": "Online", "platform_type": "Linux", "agent_version": "3.x"},
                ...
            }
        """
        if not self.ssm_client:
            return {}
        
        ssm_info = {}
        try:
            paginator = self.ssm_client.get_paginator('describe_instance_information')
            for page in paginator.paginate():
                for info in page.get('InstanceInformationList', []):
                    instance_id = info.get('InstanceId')
                    ssm_info[instance_id] = {
                        "ping_status": info.get('PingStatus'),
                        "platform_type": info.get('PlatformType'),
                        "agent_version": info.get('AgentVersion'),
                    }
        except Exception as e:
            logger.error(" Cannot fetch SSM managed instances: %s", e)
        
        return ssm_info
    
    def _determine_block_reason(self, instance: Dict, ssm_status: Dict = None) -> str:
        """
        Determine why an instance is blocked.
        
        Args:
            instance: EC2 instance dict
            ssm_status: SSM status dict (if available)
        
        Returns:
            Block reason: NO_IAM_PROFILE, NO_SSM_AGENT, NO_NETWORK_PATH, UNKNOWN
        """
        # 1. Check IAM instance profile
        if not instance.get("iam_profile"):
            return "NO_IAM_PROFILE"
        
        # 2. Check if SSM agent is registered but not online
        if ssm_status:
            ping_status = ssm_status.get("ping_status")
            if ping_status in ["ConnectionLost", "Inactive"]:
                return "NO_NETWORK_PATH"  # Agent registered but can't reach SSM endpoints
            else:
                return "NO_SSM_AGENT"  # Registered but agent issue
        
        # 3. Not registered at all
        return "NO_SSM_AGENT"
    
    def _generate_summary(self, result: Dict) -> str:
        """Generate human-readable summary."""
        total_db = result["total_instances_db"]
        total_aws = result["total_instances_aws"]
        ssm_online = result["total_ssm_online_aws"]
        blocked_count = len(result["blocked_instances"])
        
        if ssm_online > 0:
            return f" SSM ready: {ssm_online}/{total_aws} instances online in AWS ({total_db} in DB)"
        elif blocked_count > 0:
            reasons = {}
            for b in result["blocked_instances"]:
                reason = b["block_reason"]
                reasons[reason] = reasons.get(reason, 0) + 1
            
            reason_summary = ", ".join([f"{count} {reason}" for reason, count in reasons.items()])
            return f" No SSM Online instances. Blocked: {reason_summary}"
        else:
            return f" No instances found in AWS (DB has {total_db})"


def run_ssm_diagnostic(
    db: DbSession,
    region: str = "eu-north-1",
    aws_access_key: str = None,
    aws_secret_key: str = None
) -> Dict:
    """
    Convenience function to run SSM diagnostic.
    
    Returns:
        Full diagnostic dict
    """
    diag = SSMDiagnostics(db, region, aws_access_key, aws_secret_key)
    return diag.run_full_diagnostic()
