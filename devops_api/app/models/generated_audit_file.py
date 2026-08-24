# app/models/generated_audit_file.py
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base

class GeneratedAuditFile(Base):
    __tablename__ = "generated_audit_files"

    id = Column(Integer, primary_key=True, index=True)
    file_path = Column(String, nullable=False)
    tool = Column(String, nullable=True)  # ex: lynis, oscap

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User")
    session = relationship("Session")
