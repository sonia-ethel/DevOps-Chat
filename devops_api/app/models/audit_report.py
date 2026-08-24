# app/models/audit_report.py

from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base

class AuditReport(Base):
    __tablename__ = "audit_reports"

    id = Column(Integer, primary_key=True, index=True)
    execution_id = Column(Integer, ForeignKey("executions.id"), nullable=False)
    tool = Column(String, nullable=False)            # ex: scap, lynis, auditd

    report_path = Column(String, nullable=True)      # fichier .txt, .log, .xml...
    stdout = Column(Text, nullable=True)
    stderr = Column(Text, nullable=True)

    score = Column(Integer, nullable=True)           # Hardening index (Lynis)
    level = Column(String, nullable=True)            # Niveau de sévérité (optionnel)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    execution = relationship("Execution", back_populates="audit_reports")
