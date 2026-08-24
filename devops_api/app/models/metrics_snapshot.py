"""
Modèle pour stocker les snapshots de métriques de monitoring
"""
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class MetricsSnapshot(Base):
    """Snapshot de métriques collectées pour un ensemble d'instances"""
    __tablename__ = "metrics_snapshots"
    
    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(String(100), nullable=False, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Résumé global
    instances_total = Column(Integer, nullable=False)
    instances_ok = Column(Integer, default=0)
    instances_failed = Column(Integer, default=0)
    
    # Moyennes globales
    avg_cpu_percent = Column(Float, nullable=True)
    avg_mem_used_percent = Column(Float, nullable=True)
    avg_disk_used_percent = Column(Float, nullable=True)
    
    # Statut
    status = Column(String(20), nullable=False)  # success, partial, failed
    
    # Données complètes (JSON)
    full_data = Column(Text, nullable=True)  # JSON complet du snapshot
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relations
    session = relationship("Session", foreign_keys=[session_id])
    user = relationship("User", foreign_keys=[user_id])
    
    def __repr__(self):
        return f"<MetricsSnapshot(id={self.id}, task_id={self.task_id}, instances={self.instances_total}, status={self.status})>"
