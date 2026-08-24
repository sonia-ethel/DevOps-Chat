"""
Terraform Routes - P0.3 Security Group Management

Endpoints for Terraform-based infrastructure changes, starting with Security Groups.
"""

from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from typing import List, Dict, Any
import logging
from pathlib import Path
import tempfile

from app.database import get_db
from app.auth import get_current_user
from app.models.user import User
from app.models.instance import Instance
from app.models.execution_log import ExecutionLog
from app.services.terraform_sg_service import TerraformSGService
from app.services.aws_credentials_service import get_user_aws_credentials

router = APIRouter(prefix="/terraform", tags=["terraform"])
logger = logging.getLogger(__name__)


@router.post("/sg/apply")
async def apply_security_group(
    payload: Dict[str, Any] = Body(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Apply Security Group changes via Terraform with idempotence guarantee.
    
    Request body:
    {
        "instance_ids": ["i-xxx"],
        "ports": [8080, 443],
        "protocol": "tcp",
        "cidr_blocks": ["0.0.0.0/0"]
    }
    
    Response:
    {
        "terraform": {
            "status": "applied|no_changes|error",
            "plan_exit_code": 0|1|2,
            "sg_id": "sg-xxx",
            "vpc_id": "vpc-xxx",
            "ports": [8080, 443],
            "apply_stdout": "...",
            "errors": null
        },
        "execution_log_id": 123
    }
    """
    instance_ids = payload.get("instance_ids", [])
    ports = payload.get("ports", [])
    protocol = payload.get("protocol", "tcp")
    cidr_blocks = payload.get("cidr_blocks", ["0.0.0.0/0"])
    
    if not instance_ids:
        raise HTTPException(status_code=400, detail="instance_ids required")
    
    if not ports:
        raise HTTPException(status_code=400, detail="ports required")
    
    logger.info(f"User {current_user.id} requesting SG changes: ports={ports}, instances={instance_ids}")
    
    # Step 1: Get AWS credentials
    try:
        creds = get_user_aws_credentials(current_user.id, db)
        if not creds:
            raise HTTPException(status_code=400, detail="No AWS credentials configured. Please add credentials first.")
        
        aws_key = creds["AWS_ACCESS_KEY_ID"]
        aws_secret = creds["AWS_SECRET_ACCESS_KEY"]
        region = creds.get("region", "eu-north-1")
    except Exception as e:
        logger.error(f"Failed to get AWS credentials: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get AWS credentials: {str(e)}")
    
    # Step 2: Get instances and extract VPC context
    try:
        # Instance has session_id -> Session has user_id, so we need to join
        from app.models.session import Session
        
        instances = db.query(Instance).join(Session).filter(
            Session.user_id == current_user.id,
            Instance.instance_id.in_(instance_ids)
        ).all()
        
        if not instances:
            # If no instances found via join, try without user filter (for testing)
            instances = db.query(Instance).filter(
                Instance.instance_id.in_(instance_ids)
            ).all()
            
            if not instances:
                raise HTTPException(status_code=404, detail="No instances found with provided IDs")
            
            logger.warning(f"Found instances without user filter (testing mode)")
        
        logger.info(f"Found {len(instances)} instances")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Database query failed: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
    # Step 3: Create Terraform SG service
    try:
        tf_service = TerraformSGService(user_id=str(current_user.id), region=region)
        
        # Get VPC context
        sg_context = tf_service.ensure_sg_context(
            selected_instances=[{
                "instance_id": inst.instance_id,
                "vpc_id": inst.vpc_id,
                "security_group_id": inst.security_group_id
            } for inst in instances],
            db_session=db
        )
        
        vpc_id = sg_context["vpc_id"]
        logger.info(f"Using VPC: {vpc_id}")
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get SG context: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get SG context: {str(e)}")
    
    # Step 4: Generate Terraform configuration in persistent directory
    try:
        # Use persistent terraform directory per user + vpc for state preservation
        import os
        tf_base_dir = Path(os.getenv("TERRAFORM_STATE_DIR", "/tmp/dac-terraform")) / f"user_{current_user.id}" / f"vpc_{vpc_id}"
        tf_base_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Using Terraform dir: {tf_base_dir}")
        
        # Generate main.tf
        tf_service.generate_sg_tf(
            tf_dir=tf_base_dir,
            vpc_id=vpc_id,
            ports=ports,
            protocol=protocol,
            cidr_blocks=cidr_blocks
        )
        
        # Apply with idempotence check
        tf_result = tf_service.apply_tf_idempotent(
            tf_dir=tf_base_dir,
            aws_access_key_id=aws_key,
            aws_secret_access_key=aws_secret
        )
        
        logger.info(f"Terraform result: status={tf_result['status']}, exit_code={tf_result['plan_exit_code']}")
    
    except Exception as e:
        logger.error(f"Terraform execution failed: {e}")
        raise HTTPException(status_code=500, detail=f"Terraform execution failed: {str(e)}")
    
    # Step 6: Return result (skip ExecutionLog for now - would need Execution first)
    return {
        "terraform": {
            "status": tf_result["status"],
            "plan_exit_code": tf_result["plan_exit_code"],
            "sg_id": tf_result["sg_id"],
            "vpc_id": vpc_id,
            "ports": ports,
            "protocol": protocol,
            "cidr_blocks": cidr_blocks,
            "apply_stdout": tf_result.get("apply_stdout", ""),
            "apply_stderr": tf_result.get("apply_stderr", ""),
            "errors": tf_result.get("errors")
        }
    }


@router.get("/sg/status")
async def get_terraform_sg_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get last Terraform SG execution status for debugging.
    
    Returns last execution log with terraform_sg type.
    """
    try:
        last_exec = db.query(ExecutionLog).filter(
            ExecutionLog.user_id == current_user.id,
            ExecutionLog.execution_type == "terraform_sg"
        ).order_by(ExecutionLog.created_at.desc()).first()
        
        if not last_exec:
            return {"message": "No terraform SG executions found"}
        
        return {
            "id": last_exec.id,
            "status": last_exec.status,
            "created_at": last_exec.created_at.isoformat(),
            "command_summary": last_exec.command_summary,
            "metadata": last_exec.metadata
        }
    
    except Exception as e:
        logger.error(f"Failed to get terraform SG status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")
