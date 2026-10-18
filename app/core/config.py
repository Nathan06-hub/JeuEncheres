from typing import List
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Fragments interdits dans une SECRET_KEY hors développement (valeurs par défaut / placeholders).
_WEAK_SECRET_MARKERS = ("change_this", "change_me", "changeme", "insecure", "default", "secret_key", "your-")
_MIN_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    PROJECT_NAME: str = "Enchères & Drafts IA API"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_V1_STR: str = "/api/v1"

    # Security
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    ALGORITHM: str = "HS256"

    # CORS
    BACKEND_CORS_ORIGINS: List[str] = ["*"]

    # PostgreSQL Database
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str = "encheres_db"
    DATABASE_URL: str | None = None

    @property
    def ASYNC_DATABASE_URI(self) -> str:
        if self.DATABASE_URL:
            if self.DATABASE_URL.startswith("postgresql://"):
                return self.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
            return self.DATABASE_URL
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # Redis Cache & Real-time
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str | None = None

    @property
    def REDIS_URL(self) -> str:
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # Google Gemini AI API
    GEMINI_API_KEY: str
    GEMINI_MODEL: str = "gemini-1.5-flash"

    # Game Economy & Draft Rules
    INITIAL_FREE_TOKENS: int = 3
    AI_DECK_CREATION_TOKEN_COST: int = 1
    DEFAULT_STARTING_BUDGET: int = 1000
    DEFAULT_BID_TIMER_SECONDS: int = 15
    MAX_ROUNDS_PER_GAME: int = 10

    # Achats & publicités récompensées
    # Tant qu'aucun vérificateur de reçu réel n'est branché, les crédits IAP / pub sont refusés,
    # sauf si ce drapeau est explicitement activé (développement uniquement).
    ALLOW_UNVERIFIED_PURCHASES: bool = False
    REWARDED_AD_DAILY_CAP: int = 5

    # Limitation de débit (requêtes / fenêtre) sur les routes d'authentification
    AUTH_RATE_LIMIT_ATTEMPTS: int = 10
    AUTH_RATE_LIMIT_WINDOW_SECONDS: int = 60

    @property
    def IS_DEVELOPMENT(self) -> bool:
        return self.ENVIRONMENT.strip().lower() == "development"

    @model_validator(mode="after")
    def _forbid_weak_secret_outside_development(self) -> "Settings":
        """Refuse de démarrer hors `development` avec une SECRET_KEY par défaut ou trop faible."""
        if self.IS_DEVELOPMENT:
            return self

        key = self.SECRET_KEY or ""
        lowered = key.lower()
        if len(key) < _MIN_SECRET_LENGTH:
            raise ValueError(
                f"SECRET_KEY trop courte ({len(key)} < {_MIN_SECRET_LENGTH} caractères) "
                f"pour ENVIRONMENT='{self.ENVIRONMENT}'"
            )
        if any(marker in lowered for marker in _WEAK_SECRET_MARKERS):
            raise ValueError(
                f"SECRET_KEY par défaut/placeholder interdite pour ENVIRONMENT='{self.ENVIRONMENT}'. "
                "Générez-en une avec : python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
        if "*" in self.BACKEND_CORS_ORIGINS:
            raise ValueError("BACKEND_CORS_ORIGINS ne peut pas contenir '*' hors développement")
        if self.ALLOW_UNVERIFIED_PURCHASES:
            raise ValueError("ALLOW_UNVERIFIED_PURCHASES doit rester False hors développement")
        return self


settings = Settings()
