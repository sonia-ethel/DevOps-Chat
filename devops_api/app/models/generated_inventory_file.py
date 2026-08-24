from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class GeneratedInventoryFile(Base):
    __tablename__ = "generated_inventory_files"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=True)
    intent_id = Column(Integer, ForeignKey("intents.id"), nullable=True)

    filename = Column(String, nullable=False)  #  requis pour compatibilité
    file_path = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # --- Relations explicites ---
    user = relationship("User", back_populates="inventory_files")
    session = relationship("Session", back_populates="inventory_files")

    # On précise bien quel FK utiliser pour lever l’ambiguïté
    intent = relationship(
        "Intent",
        back_populates="inventory_files",
        foreign_keys=[intent_id],
    )
