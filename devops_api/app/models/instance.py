from sqlalchemy import Column, Integer, String, Text, ForeignKey, Boolean, Enum, DateTime
from sqlalchemy.orm import relationship
from app.database import Base
from datetime import datetime
import enum


class ConnectionMethod(str, enum.Enum):
    """Méthode de connexion pour configurer une instance"""
    SSH = "ssh"
    SSM = "ssm"


class Instance(Base):
    __tablename__ = "instances"

    id = Column(Integer, primary_key=True, index=True)

    # Identité cloud
    instance_id = Column(String, unique=True, index=True)   # ex: i-xxxxxxxx
    provider = Column(String)                                # ex: aws
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)

    # Réseau / accès
    public_ip = Column(String, nullable=False)               # (peut être chiffré en DB selon ton utilitaire)
    private_ip = Column(String, nullable=True)
    ssh_user = Column(String, nullable=False)
    ssh_private_key = Column(Text, nullable=False)

    # Métadonnées
    name = Column(String)                                    # ex: "web-server-1"

    # Nouvelles infos (corrige l'erreur)
    status = Column(String, nullable=True)                   # ex: "running", "stopped", etc.

    # Infos système détectées
    os_family = Column(String, nullable=True)                # "linux" | "windows"
    distro = Column(String, nullable=True)                   # "ubuntu", "debian", ...
    hostname = Column(String, nullable=True)

    #  ÉTAPE 1 — Configuration only
    connection_method = Column(String, default="ssh", nullable=False)  # "ssh" ou "ssm"
    ssm_managed = Column(Boolean, default=False)             # true si SSM peut être utilisé

    #  ÉTAPE 3 — Security Group management
    security_group_id = Column(String, nullable=True)        # ex: sg-xxxxxxxx
    subnet_id = Column(String, nullable=True)                # ex: subnet-xxxxxxxx
    vpc_id = Column(String, nullable=True)                   # ex: vpc-xxxxxxxx

    #  ÉTAPE P0.1 — Auto-sync tracking
    last_synced_at = Column(DateTime, default=datetime.utcnow, nullable=True)  # Timestamp dernier sync

    session = relationship("Session", back_populates="instances")
