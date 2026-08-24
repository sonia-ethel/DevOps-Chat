from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class UserAWSCredentials(Base):
    __tablename__ = "user_aws_credentials"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    access_key_id = Column(String, nullable=False)
    secret_access_key_encrypted = Column(String, nullable=False)  # Encrypted with Fernet
    region = Column(String, nullable=False, default="us-east-1")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relations
    user = relationship("User", back_populates="aws_credentials")