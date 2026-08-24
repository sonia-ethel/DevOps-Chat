# app/models/generated_playbook.py
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class GeneratedPlaybook(Base):
    __tablename__ = "generated_playbooks"

    id = Column(Integer, primary_key=True, index=True)
    file_path = Column(String, nullable=False)
    ssh_user = Column(String, nullable=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    tools = Column(String, nullable=True)

    user = relationship("User")
    session = relationship("Session")
