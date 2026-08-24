# app/models/generated_kubernetes_manifest.py
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class GeneratedKubernetesManifest(Base):
    __tablename__ = "generated_kubernetes_manifests"

    id = Column(Integer, primary_key=True, index=True)
    file_path = Column(String, nullable=False)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")
    session = relationship("Session")
