# © 2024–2026 TOURE Arnaud Patrick
# Licensed under the MIT License

# app/models/intent.py

import enum
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Index
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class GenerationStatus(str, enum.Enum):
    pending = "pending"         # jamais généré
    generating = "generating"   # en cours
    generated = "generated"     # généré OK
    failed = "failed"           # erreur génération


class Intent(Base):
    __tablename__ = "intents"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    intent_type = Column(String, nullable=False)  # ex: configure, create, audit, kubernetes
    prompt = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    audit_tool = Column(String, nullable=True)

    # Champ existant
    runtime = Column(String, nullable=True, default="system")  # valeurs possibles: system, docker, k8s

    # Champs routeur d’actions (existants)
    configure_domain = Column(String, nullable=True)  # ex: "dns_tls", "compute", "system_service"
    configure_mode = Column(String, nullable=True)    # "infra" | "system" | "mixed"

    #  Suivi de génération (idempotence + batch)
    generation_status = Column(
        SAEnum(GenerationStatus), nullable=False, default=GenerationStatus.pending, index=True
    )
    generated_at = Column(DateTime(timezone=True), nullable=True)
    generation_error = Column(Text, nullable=True)

    #  Lien (optionnel) vers l’exécution principale déclenchée par cette génération
    # WARN Ambiguïté avec Execution.intent_id -> on déclare une relation dédiée et on
    # précise les foreign_keys des deux côtés.
    execution_id = Column(Integer, ForeignKey("executions.id"), nullable=True)
    executed_at = Column(DateTime(timezone=True), nullable=True)

    # (optionnel) identifiant de lot si génération par batch de session
    generation_batch_id = Column(String, nullable=True)

    __table_args__ = (
        Index("ix_intents_type_domain_mode", "intent_type", "configure_domain", "configure_mode"),
        Index("ix_intents_session_status", "session_id", "generation_status"),
        Index("ix_intents_type", "intent_type"),
    )

    # --- Relations ---
    session = relationship("Session", back_populates="intents")

    # Liée au FK Execution.intent_id (plusieurs exécutions peuvent référencer un intent)
    executions = relationship(
        "Execution",
        back_populates="intent",
        foreign_keys="Execution.intent_id",
    )

    # Liée au FK local Intent.execution_id (exécution principale unique)
    primary_execution = relationship(
        "Execution",
        foreign_keys=[execution_id],
        uselist=False,
        post_update=True,  # aide à résoudre les cycles lors des updates
    )

    # Fichiers d’inventaire générés pour cet intent
    inventory_files = relationship("GeneratedInventoryFile", back_populates="intent")
