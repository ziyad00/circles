from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # App settings
    debug: bool = False
    app_name: str = "Circles"

    # Database settings
    database_url: str = "postgresql+asyncpg://postgres:password@127.0.0.1:5432/circles"
    # OTP settings
    otp_secret_key: str = "your-secret-key-change-in-production"
    otp_expiry_minutes: int = 10

    # JWT settings (for future use)
    jwt_secret_key: str = "your-jwt-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 30

    class Config:
        env_file = ".env"
        env_prefix = "APP_"
        case_sensitive = False


settings = Settings()
