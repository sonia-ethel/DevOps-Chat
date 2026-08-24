# © 2024–2026 TOURE Arnaud Patrick
# Licensed under the MIT License

# app/models/execution.py
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class Execution(Base):
    __tablename__ = "executions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=True)

    task_type = Column(String, nullable=False)      # terraform | ansible | audit | kubernetes
    status = Column(String, default="pending")      # pending | running | completed | failed
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    extra_data = Column(JSON, nullable=True)
    tags = Column(JSON, nullable=True)              # liste de tags ["ssm", "bootstrap", "windows", ...]
    target_file = Column(Integer, nullable=True)

    # WARN FK vers intents (l’exécution est déclenchée par un intent)
    intent_id = Column(Integer, ForeignKey("intents.id"), nullable=True)

    # WARN FK vers generated_inventory_files (inventaire utilisé par ansible/audit)
    inventory_id = Column(Integer, ForeignKey("generated_inventory_files.id"), nullable=True)

    #  Relations 

    session = relationship("Session", back_populates="executions")
    user = relationship("User", back_populates="executions")

    #  Rendre le lien vers Intent non ambigu (il existe AUSSI intents.execution_id -> executions.id)
    intent = relationship(
        "Intent",
        back_populates="executions",
        foreign_keys=[intent_id],
    )

    #  Idem pour l’inventaire (évite l’ambiguïté avec intents.intent_id -> generated_inventory_files.id)
    inventory = relationship(
        "GeneratedInventoryFile",
        foreign_keys=[inventory_id],
    )

    # Rapports
    ansible_report = relationship("AnsibleReport", uselist=False, back_populates="execution")
    terraform_report = relationship("TerraformReport", uselist=False, back_populates="execution")
    kubernetes_report = relationship("KubernetesReport", uselist=False, back_populates="execution")
    audit_reports = relationship("AuditReport", back_populates="execution")

    # Logs
    execution_logs = relationship(
        "ExecutionLog",
        back_populates="execution",
        cascade="all, delete-orphan",
    )
