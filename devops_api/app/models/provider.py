from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, JSON, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class Provider(Base):
    __tablename__ = "providers"
    __table_args__ = (
        UniqueConstraint("user_id", "provider_name", "session_id", name="uq_provider_user_type_session"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=True)
    provider_name = Column(String, nullable=False)
    encrypted_credentials = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="providers")
    session = relationship("Session")
