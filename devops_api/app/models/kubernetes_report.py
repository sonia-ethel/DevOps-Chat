# models/kubernetes_report.py

from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class KubernetesReport(Base):
    __tablename__ = "kubernetes_reports"

    id = Column(Integer, primary_key=True, index=True)
    execution_id = Column(Integer, ForeignKey("executions.id"), nullable=False)
    manifest_path = Column(String, nullable=False)
    stdout = Column(Text, nullable=True)
    stderr = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    execution = relationship("Execution", back_populates="kubernetes_report")
