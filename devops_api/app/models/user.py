from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
from sqlalchemy import Boolean
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_admin = Column(Boolean, default=False)

    # Relations
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")
    providers = relationship("Provider", back_populates="user", cascade="all, delete-orphan")
    deployments = relationship("Deployment", back_populates="user", cascade="all, delete-orphan")
    executions = relationship("Execution", back_populates="user", cascade="all, delete-orphan")
    

    execution_logs = relationship("ExecutionLog", back_populates="user")
    inventory_files = relationship("GeneratedInventoryFile", back_populates="user")
    aws_credentials = relationship("UserAWSCredentials", back_populates="user", uselist=False, cascade="all, delete-orphan")
    
    # Monitoring & Audit snapshots
    metrics_snapshots = relationship("MetricsSnapshot", back_populates="user")
    audit_snapshots = relationship("AuditSnapshot", back_populates="user")
