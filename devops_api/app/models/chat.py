# app/models/chat.py

from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Chat(Base):
    __tablename__ = "chats"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"))
    name = Column(String, default="Chat sans nom", nullable=False)
    chat_mode = Column("mode", String, nullable=False, default="free")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relation avec la session
    session = relationship("Session", back_populates="chats")

    # Relation avec les messages
    messages = relationship("Message", back_populates="chat", cascade="all, delete-orphan")
