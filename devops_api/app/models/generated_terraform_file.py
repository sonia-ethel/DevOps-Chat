# app/models/generated_terraform_file.py
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class GeneratedTerraformFile(Base):
    __tablename__ = "generated_terraform_files"

    id = Column(Integer, primary_key=True, index=True)
    file_path = Column(String, nullable=False)  # chemin vers le fichier .tf
    ssh_user = Column(String, nullable=True)
    base_name = Column(String, nullable=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")
    session = relationship("Session")
