# © 2024–2026 TOURE Arnaud Patrick
# Licensed under the MIT License

# app/models/session.py

from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
from sqlalchemy.orm import backref

class Session(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    state = Column(String, nullable=False)
    mode = Column(String, default="free", nullable=False)  # "free" ou "dac"
    request_text = Column(Text)
    action = Column(String)
    description = Column(Text)
    provider = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    session_temp_data = Column(String, nullable=True)

    # OK Relation hiérarchique entre sessions
    parent_session_id = Column(Integer, ForeignKey("sessions.id"), nullable=True)
    parent_session = relationship("Session", remote_side=[id], backref=backref("child_sessions", cascade="all, delete"))

    # Relations existantes
    user = relationship("User", back_populates="sessions")
    instances = relationship("Instance", back_populates="session", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan")
    chats = relationship("Chat", back_populates="session", cascade="all, delete-orphan")
    executions = relationship("Execution", back_populates="session", cascade="all, delete-orphan")
    intents = relationship("Intent", back_populates="session", cascade="all, delete-orphan")
    inventory_files = relationship("GeneratedInventoryFile", back_populates="session")
    plans = relationship("Plan", back_populates="session", cascade="all, delete-orphan")
    
    # Monitoring & Audit snapshots
    metrics_snapshots = relationship("MetricsSnapshot", back_populates="session")
    audit_snapshots = relationship("AuditSnapshot", back_populates="session")

