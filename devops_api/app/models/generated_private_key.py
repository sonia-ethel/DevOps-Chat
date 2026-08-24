# app/models/generated_private_key.py
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class GeneratedPrivateKey(Base):
    __tablename__ = "generated_private_keys"

    id = Column(Integer, primary_key=True, index=True)
    file_path = Column(String, nullable=False)
    content = Column(String, nullable=False)  #  clé privée chiffrée (ex: fernet)
    fingerprint = Column(String, nullable=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")
    session = relationship("Session")
