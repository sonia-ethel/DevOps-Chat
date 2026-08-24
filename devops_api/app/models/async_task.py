# app/models/async_task.py

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Float
from sqlalchemy.orm import relationship
from app.database import Base
from datetime import datetime


class AsyncTask(Base):
    __tablename__ = "async_tasks"

    id = Column(Integer, primary_key=True, index=True)
    
    # Task identification
    task_id = Column(String, unique=True, index=True, nullable=False)  # UUID pour identification
    task_type = Column(String, nullable=False)  # "terraform", "ansible", "kubernetes", "audit"
    
    # Status tracking
    status = Column(String, default="pending")  # pending, running, completed, failed, cancelled
    progress_percentage = Column(Float, default=0.0)  # 0.0 to 100.0
    current_step = Column(String, nullable=True)  # "Initializing...", "Running terraform apply...", etc.
    
    # Relationships
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    execution_id = Column(Integer, ForeignKey("executions.id"), nullable=True)  # Lié à l'execution une fois créée
    
    # Task data
    task_data = Column(Text, nullable=True)  # JSON avec paramètres de la tâche
    result_data = Column(Text, nullable=True)  # JSON avec résultats finaux
    error_message = Column(Text, nullable=True)  # Message d'erreur si échec
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Progress logs
    progress_logs = relationship("AsyncTaskLog", back_populates="task", cascade="all, delete-orphan")
    
    # Relationships
    user = relationship("User")
    session = relationship("Session")
    execution = relationship("Execution", uselist=False)


class AsyncTaskLog(Base):
    __tablename__ = "async_task_logs"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("async_tasks.id", ondelete="CASCADE"), nullable=False)
    
    # Log entry
    timestamp = Column(DateTime, default=datetime.utcnow)
    level = Column(String, default="info")  # "info", "warning", "error", "success"
    message = Column(Text, nullable=False)
    step_name = Column(String, nullable=True)  # "terraform_init", "terraform_apply", etc.
    
    # Progress data
    progress_percentage = Column(Float, nullable=True)  # Progress à ce moment
    
    # Relationship
    task = relationship("AsyncTask", back_populates="progress_logs")