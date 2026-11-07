from typing import List
from sqlalchemy.engine import URL, make_url
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
    ENVIRONMENT: str = "production"
    DEBUG: bool = False
    SQL_ECHO: bool = False
    API_V1_STR: str = "/api/v1"

    # Security
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours default
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14
    ALGORITHM: str = "HS256"
    JWT_ISSUER: str = "encheres-drafts-api"
    JWT_AUDIENCE: str = "encheres-drafts-client"

    # CORS & Proxy
    BACKEND_CORS_ORIGINS: List[str] = []
    TRUSTED_PROXY_HOSTS: List[str] = ["127.0.0.1", "::1"]

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
            url = make_url(self.DATABASE_URL)
            if url.drivername == "postgresql":
                url = url.set(drivername="postgresql+asyncpg")
            return url.render_as_string(hide_password=False)
        return URL.create(
            "postgresql+asyncpg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_SERVER,
            port=self.POSTGRES_PORT,
            database=self.POSTGRES_DB,
        ).render_as_string(hide_password=False)

    # Redis Cache & Real-time
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str | None = None
    REDIS_SSL: bool = False

    @property
    def REDIS_URL(self) -> str:
        return URL.create(
            "rediss" if self.REDIS_SSL else "redis",
            username="" if self.REDIS_PASSWORD else None,
            password=self.REDIS_PASSWORD,
            host=self.REDIS_HOST,
            port=self.REDIS_PORT,
            database=str(self.REDIS_DB),
        ).render_as_string(hide_password=False)

    # Google Gemini AI API
    GEMINI_API_KEY: str
    GEMINI_MODEL: str = "gemini-1.5-flash"

    # Game Economy & Draft Rules
    INITIAL_FREE_TOKENS: int = 3
    AI_DECK_CREATION_TOKEN_COST: int = 1
    AI_DAILY_GLOBAL_GENERATION_CAP: int = 200
    AI_GENERATE_RATE_LIMIT_PER_MIN: int = 3
    MAX_ACTIVE_GAMES_PER_HOST: int = 3
    DEFAULT_STARTING_BUDGET: int = 1000
    DEFAULT_BID_TIMER_SECONDS: int = 15
    MAX_ROUNDS_PER_GAME: int = 10

    # Achats & publicités récompensées
    # Tant qu'aucun identifiant fournisseur n'est configuré, les crédits IAP / pub sont refusés (501 fail-closed),
    # sauf si ALLOW_UNVERIFIED_PURCHASES=True en développement uniquement.
    ALLOW_UNVERIFIED_PURCHASES: bool = False
    REWARDED_AD_DAILY_CAP: int = 5
    APPLE_IAP_VERIFY_URL: str = "https://api.storekit.itunes.apple.com"
    APPLE_IAP_BEARER_TOKEN: str = ""
    APPLE_IAP_PRIVATE_KEY: str = ""
    APPLE_IAP_KEY_ID: str = ""
    APPLE_IAP_ISSUER_ID: str = ""
    APPLE_BUNDLE_ID: str = ""
    APPLE_APP_ID: str = ""
    APPLE_ENVIRONMENT: str = "Production"
    APPLE_ROOT_CERTIFICATES_B64: str = ""
    GOOGLE_PLAY_PACKAGE_NAME: str = ""
    GOOGLE_PLAY_ACCESS_TOKEN: str = ""
    GOOGLE_PLAY_SERVICE_ACCOUNT_JSON: str = ""
    ADMOB_REWARD_ITEM: str = "token"
    ADMOB_REWARD_AMOUNT: int = 1
    ADMOB_ALLOWED_AD_UNIT: str = ""

    # Limitation de débit (requêtes / fenêtre) sur les routes d'authentification
    AUTH_RATE_LIMIT_ATTEMPTS: int = 10
    AUTH_RATE_LIMIT_WINDOW_SECONDS: int = 60

    @property
    def IS_DEVELOPMENT(self) -> bool:
        return self.ENVIRONMENT.strip().lower() in ("development", "test")

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
        if self.DEBUG:
            raise ValueError("DEBUG doit rester False hors développement")
        return self


settings = Settings()
