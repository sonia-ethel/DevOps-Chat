"""
AuditSnapshot model for storing audit results snapshots
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class AuditSnapshot(Base):
    """Store snapshots of audit results for historical tracking"""
    __tablename__ = "audit_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    
    # Summary statistics
    instances_total = Column(Integer, nullable=False, default=0)
    instances_ok = Column(Integer, nullable=False, default=0)
    instances_failed = Column(Integer, nullable=False, default=0)
    
    # Finding counts by severity
    critical_count = Column(Integer, nullable=False, default=0)
    high_count = Column(Integer, nullable=False, default=0)
    medium_count = Column(Integer, nullable=False, default=0)
    low_count = Column(Integer, nullable=False, default=0)
    info_count = Column(Integer, nullable=False, default=0)
    
    # Execution status
    status = Column(String(50), nullable=False)  # success, partial, failed
    
    # Full audit data as JSON string
    full_data = Column(Text, nullable=False)
    
    # Relationships
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    user = relationship("User", back_populates="audit_snapshots")
    
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=True)
    session = relationship("Session", back_populates="audit_snapshots")
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    def __repr__(self):
        return f"<AuditSnapshot(id={self.id}, instances={self.instances_total}, status={self.status})>"
