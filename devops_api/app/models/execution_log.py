from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class ExecutionLog(Base):
    __tablename__ = "execution_logs"

    id = Column(Integer, primary_key=True, index=True)

    execution_id = Column(
        Integer,
        ForeignKey("executions.id", ondelete="CASCADE"),
        nullable=False
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    event = Column(String, nullable=False)  # ex: started, completed, failed
    message = Column(Text, nullable=True)   # OK toujours du texte (str ou JSON.stringify)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relations
    execution = relationship("Execution", back_populates="execution_logs")  #  nom cohérent
    user = relationship("User", back_populates="execution_logs", lazy="joined")
