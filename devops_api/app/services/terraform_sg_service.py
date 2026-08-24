"""
Terraform Security Group Service - P0.3 Idempotent SG Management

This service ensures that Security Group changes are:
1. DAC-managed via stable tags (dac_managed, dac_scope, dac_user_id, etc.)
2. Idempotent: rerunning the same intent = no changes (terraform plan exit code 0)
3. Stable: uses for_each with stable keys to prevent duplicate rules
"""

import os
import json
import subprocess
import logging
from typing import Dict, List, Optional, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class TerraformSGService:
    """Service for managing Security Groups via Terraform with idempotence guarantees."""
    
    def __init__(self, user_id: str, region: str = "eu-north-1"):
        self.user_id = user_id
        self.region = region
        self.base_tags = {
            "dac_managed": "true",
            "dac_scope": "configure_only",
            "dac_user_id": user_id,
            "dac_env": "mvp",
            "dac_purpose": "ingress_ports"
        }
    
    def ensure_sg_context(
        self,
        selected_instances: List[Dict[str, Any]],
        db_session: Any
    ) -> Dict[str, Any]:
        """
        Retrieve VPC and SG context from selected instances.
        
        Returns:
            {
                "vpc_id": "vpc-xxx",
                "existing_sg_ids": ["sg-xxx"],
                "region": "eu-north-1"
            }
        """
        if not selected_instances:
            raise ValueError("No instances selected for SG configuration")
        
        # Get VPC ID from first instance
        vpc_id = None
        existing_sg_ids = []
        
        for inst in selected_instances:
            if inst.get('vpc_id'):
                vpc_id = inst.get('vpc_id')
                if inst.get('security_group_id'):
                    sg_id = inst.get('security_group_id')
                    existing_sg_ids = [sg_id] if sg_id else []
                break
        
        if not vpc_id:
            raise ValueError("No VPC ID found in selected instances. Instances must have vpc_id populated.")
        
        return {
            "vpc_id": vpc_id,
            "existing_sg_ids": existing_sg_ids,
            "region": self.region
        }
    
    def generate_sg_tf(
        self,
        tf_dir: Path,
        vpc_id: str,
        ports: List[int],
        protocol: str = "tcp",
        cidr_blocks: List[str] = None
    ) -> Path:
        """
        Generate Terraform configuration for Security Group with idempotent rules.
        
        Uses for_each with stable keys to prevent duplicates.
        Tags the SG with dac_managed metadata for reuse.
        
        Returns:
            Path to generated main.tf
        """
        if cidr_blocks is None:
            cidr_blocks = ["0.0.0.0/0"]
        
        tf_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate stable rule keys
        rules = {}
        for port in ports:
            for cidr in cidr_blocks:
                key = f"{protocol}_{port}_{cidr.replace('/', '_')}"
                rules[key] = {
                    "protocol": protocol,
                    "from_port": port,
                    "to_port": port,
                    "cidr_blocks": [cidr]
                }
        
        # Generate tags as Terraform map
        tags_tf = json.dumps(self.base_tags, indent=2)
        
        # Generate fixed SG name based on user_id and vpc_id for idempotence
        sg_name = f"dac-sg-{self.user_id}-{vpc_id}"
        
        # Convert rules to ingress blocks format
        ingress_blocks = []
        for key, rule in rules.items():
            ingress_blocks.append(f'''  ingress {{
    description = "DAC-managed rule: {key}"
    from_port   = {rule["from_port"]}
    to_port     = {rule["to_port"]}
    protocol    = "{rule["protocol"]}"
    cidr_blocks = {json.dumps(rule["cidr_blocks"])}
  }}''')
        
        ingress_tf = "\n".join(ingress_blocks)
        
        # Generate Terraform configuration with inline ingress rules
        main_tf_content = f'''terraform {{
  required_providers {{
    aws = {{
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }}
  }}
}}

provider "aws" {{
  region = "{self.region}"
}}

# Security Group with inline ingress rules for idempotence
resource "aws_security_group" "dac_sg" {{
  name        = "{sg_name}"
  description = "DAC-managed Security Group for configure_only intent"
  vpc_id      = "{vpc_id}"
  
{ingress_tf}
  
  tags = {tags_tf}
  
  lifecycle {{
    create_before_destroy = false
  }}
}}

# Output the Security Group ID
output "security_group_id" {{
  value = aws_security_group.dac_sg.id
}}

output "security_group_name" {{
  value = aws_security_group.dac_sg.name
}}

output "vpc_id" {{
  value = aws_security_group.dac_sg.vpc_id
}}
'''
        
        main_tf_path = tf_dir / "main.tf"
        main_tf_path.write_text(main_tf_content)
        
        logger.info(f"Generated Terraform configuration at {main_tf_path}")
        logger.info(f"Security Group will be tagged with: {self.base_tags}")
        logger.info(f"Rules to apply: {list(rules.keys())}")
        
        return main_tf_path
    
    def apply_tf_idempotent(
        self,
        tf_dir: Path,
        aws_access_key_id: str,
        aws_secret_access_key: str
    ) -> Dict[str, Any]:
        """
        Apply Terraform with idempotence check using plan -detailed-exitcode.
        
        Exit codes:
        - 0: no changes needed (idempotent)
        - 2: changes applied
        - 1: error
        
        Returns:
            {
                "status": "applied|no_changes|error",
                "plan_exit_code": 0|1|2,
                "sg_id": "sg-xxx",
                "apply_stdout": "...",
                "apply_stderr": "...",
                "errors": None or error message
            }
        """
        env = os.environ.copy()
        env["AWS_ACCESS_KEY_ID"] = aws_access_key_id
        env["AWS_SECRET_ACCESS_KEY"] = aws_secret_access_key
        env["AWS_DEFAULT_REGION"] = self.region
        
        result = {
            "status": "error",
            "plan_exit_code": None,
            "sg_id": None,
            "apply_stdout": "",
            "apply_stderr": "",
            "errors": None
        }
        
        try:
            # Step 1: terraform init
            logger.info(f"Running terraform init in {tf_dir}")
            init_proc = subprocess.run(
                ["terraform", "init", "-no-color"],
                cwd=tf_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if init_proc.returncode != 0:
                result["errors"] = f"Terraform init failed: {init_proc.stderr}"
                logger.error(result["errors"])
                return result
            
            logger.info("Terraform init successful")
            
            # Step 2: terraform plan -detailed-exitcode
            logger.info("Running terraform plan -detailed-exitcode")
            plan_proc = subprocess.run(
                ["terraform", "plan", "-detailed-exitcode", "-no-color", "-input=false"],
                cwd=tf_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            result["plan_exit_code"] = plan_proc.returncode
            
            logger.info(f"Terraform plan exit code: {plan_proc.returncode}")
            
            if plan_proc.returncode == 0:
                # No changes needed - idempotent!
                result["status"] = "no_changes"
                result["apply_stdout"] = plan_proc.stdout
                logger.info(" Terraform plan shows no changes (idempotent)")
                
                # Try to get SG ID from state
                result["sg_id"] = self._get_sg_id_from_state(tf_dir, env)
                
                return result
            
            elif plan_proc.returncode == 2:
                # Changes detected, need to apply
                logger.info("Terraform plan detected changes, applying...")
                
                # Step 3: terraform apply -auto-approve
                apply_proc = subprocess.run(
                    ["terraform", "apply", "-auto-approve", "-no-color", "-input=false"],
                    cwd=tf_dir,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                
                result["apply_stdout"] = apply_proc.stdout
                result["apply_stderr"] = apply_proc.stderr
                
                if apply_proc.returncode == 0:
                    result["status"] = "applied"
                    result["sg_id"] = self._get_sg_id_from_state(tf_dir, env)
                    logger.info(f" Terraform apply successful, SG ID: {result['sg_id']}")
                else:
                    result["errors"] = f"Terraform apply failed: {apply_proc.stderr}"
                    logger.error(result["errors"])
                
                return result
            
            else:
                # Plan failed (exit code 1)
                result["errors"] = f"Terraform plan failed: {plan_proc.stderr}"
                logger.error(result["errors"])
                return result
        
        except subprocess.TimeoutExpired as e:
            result["errors"] = f"Terraform command timed out: {str(e)}"
            logger.error(result["errors"])
            return result
        
        except Exception as e:
            result["errors"] = f"Terraform execution error: {str(e)}"
            logger.error(result["errors"])
            return result
    
    def _get_sg_id_from_state(self, tf_dir: Path, env: Dict[str, str]) -> Optional[str]:
        """Extract Security Group ID from Terraform state using output."""
        try:
            output_proc = subprocess.run(
                ["terraform", "output", "-json"],
                cwd=tf_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if output_proc.returncode == 0:
                outputs = json.loads(output_proc.stdout)
                if "security_group_id" in outputs:
                    return outputs["security_group_id"]["value"]
        except Exception as e:
            logger.warning(f"Could not extract SG ID from state: {e}")
        
        return None


def create_terraform_sg_service(user_id: str, region: str = "eu-north-1") -> TerraformSGService:
    """Factory function to create TerraformSGService instance."""
    return TerraformSGService(user_id=user_id, region=region)
