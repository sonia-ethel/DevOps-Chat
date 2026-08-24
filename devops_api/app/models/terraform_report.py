# models/terraform_report.py

from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base

class TerraformReport(Base):
    __tablename__ = "terraform_reports"

    id = Column(Integer, primary_key=True, index=True)
    execution_id = Column(Integer, ForeignKey("executions.id"), nullable=False)
    plan_output = Column(Text, nullable=True)
    apply_output = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    execution = relationship("Execution", back_populates="terraform_report")
