# app/models/plan.py
"""
Plan execution model - represents a structured sequence of operations.
Bridges natural language to deterministic infrastructure deployment.
"""
from sqlalchemy import Column, Integer, String, JSON, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from app.database import Base


class PlanPhase(enum.Enum):
    """Ordered execution phases for infrastructure deployment."""
    TERRAFORM_CREATE = "terraform.create"      # 1. Provision AWS infrastructure
    INVENTORY_GENERATE = "inventory.generate"  # 2. Generate Ansible inventory from outputs
    ANSIBLE_CONFIGURE = "ansible.configure"    # 3. Configure OS/applications
    VERIFY = "verify"                          # 4. Test/verify deployment
    AUDIT = "audit"                            # 5. Security audit


class InfraRequirement:
    """
    Represents a single infrastructure requirement.
    Example: {"type": "ec2", "count": 2, "os": "ubuntu", "sg": [22, 80]}
    """
    pass  # Will be JSON in database


class ConfigRequirement:
    """
    Represents a single configuration requirement (system or application).
    Example: {"type": "nginx", "state": "present", "port": 80}
    """
    pass  # Will be JSON in database


class Plan(Base):
    """
    A Plan is a structured sequence of operations derived from user intent.
    
    Flow:
    1. User prompt -> parse_intent (quick detection)
    2. Intent -> generate_plan (structured analysis)
    3. Plan -> execution phases (Terraform -> Inventory -> Ansible -> Verify)
    """
    __tablename__ = "plans"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Raw input
    raw_prompt = Column(String(5000), nullable=False)

    # Parsed requirements (JSON)
    # infra_requirements: [{"type": "ec2", "count": 2, "os": "ubuntu", "sg": [22, 80], "tags": {...}}]
    infra_requirements = Column(JSON, nullable=True, default=list)

    # config_requirements: [{"type": "nginx", "state": "present"}, {"type": "user", "name": "deployer"}]
    config_requirements = Column(JSON, nullable=True, default=list)

    # verification: [{"type": "http", "port": 80, "path": "/"}]
    verification_requirements = Column(JSON, nullable=True, default=list)

    # audit_requirements: [{"type": "lynis", "scope": "system"}]
    audit_requirements = Column(JSON, nullable=True, default=list)

    # kubernetes_requirements: [{"type": "eks_cluster", "nodes": 3}]
    kubernetes_requirements = Column(JSON, nullable=True, default=list)

    # Execution status
    status = Column(String(50), default="pending")  # pending, executing, completed, failed
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    session = relationship("Session", back_populates="plans")
    user = relationship("User")

    def __repr__(self):
        return f"<Plan(id={self.id}, session_id={self.session_id}, status={self.status})>"


class PlanExecution(Base):
    """
    Tracks execution of a single plan phase.
    
    Example:
    - Phase: terraform.create
    - Status: completed
    - Output: Terraform state, instance IDs, security group IDs
    """
    __tablename__ = "plan_executions"

    id = Column(Integer, primary_key=True)
    plan_id = Column(Integer, ForeignKey("plans.id"), nullable=False)
    
    phase = Column(String(50), nullable=False)  # "terraform.create", "ansible.configure", etc.
    sequence = Column(Integer, nullable=False)  # Order: 1, 2, 3, 4 (terraform, inventory, ansible, verify)
    
    status = Column(String(50), default="pending")  # pending, running, completed, failed
    
    # Generated code/config for this phase
    code = Column(String(50000), nullable=True)  # Terraform/Ansible code
    
    # Execution output
    output = Column(String(50000), nullable=True)  # stdout/stderr from execution
    errors = Column(String(5000), nullable=True)   # Error details if failed
    
    # Results (stored JSON for phase outputs)
    # terraform: {"instances": [{"id": "i-xxx", "ip": "10.0.0.1"}], "sg_id": "sg-xxx"}
    # ansible: {"changed": 5, "failed": 0}
    # verify: {"http_80": true, "ssh_22": true}
    results = Column(JSON, nullable=True)
    
    execution_started = Column(DateTime, nullable=True)
    execution_ended = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    plan = relationship("Plan")

    def __repr__(self):
        return f"<PlanExecution(phase={self.phase}, status={self.status})>"
