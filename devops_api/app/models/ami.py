# app/models/ami.py

from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from app.database import Base

class Ami(Base):
    __tablename__ = "amis"

    id = Column(Integer, primary_key=True, index=True)
    distribution = Column(String, nullable=False)   # ex: debian / ubuntu / windows
    description = Column(String, nullable=True)     # ex: Debian 11 Buster
    ami_id = Column(String, nullable=False)         # l'AMI officiel: ami-xxxxxx
    region = Column(String, nullable=False)         # ex: eu-west-1
    created_at = Column(DateTime(timezone=True), server_default=func.now())
