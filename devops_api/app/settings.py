# app/settings.py
import os
from app.env import load_app_env

load_app_env()

class Settings:
    BACKEND_BASE_URL: str = os.getenv("BACKEND_BASE_URL", "https://devops-backend-uzw2.onrender.com")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "").strip()
    DAC_AI_PROVIDER: str = os.getenv("DAC_AI_PROVIDER", "mock").strip().lower()
    SECRET_KEY: str = os.getenv("SECRET_KEY", "").strip()
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    DATABASE_URL: str = os.getenv("DATABASE_URL", "").strip()
    FERNET_KEY: str = os.getenv("FERNET_KEY", "").strip()
    FERNET_SECRET: str = FERNET_KEY or os.getenv("FERNET_SECRET", "").strip()

    def validate(self):
        missing = [attr for attr in [
            "SECRET_KEY",
            "DATABASE_URL",
        ] if not getattr(self, attr)]
        if not (self.FERNET_KEY or self.FERNET_SECRET):
            missing.append("FERNET_KEY")
        if self.DAC_AI_PROVIDER == "openai" and not self.OPENAI_API_KEY:
            missing.append("OPENAI_API_KEY")
        if missing:
            raise RuntimeError(f"Variables d'environnement manquantes: {', '.join(missing)}")

settings = Settings()
