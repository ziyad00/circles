from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional, List
from typing import Optional


class Settings(BaseSettings):
    # App settings
    debug: bool = False
    app_name: str = "Circles"
    cors_allowed_origins: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # Database settings
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:password@127.0.0.1:5432/circles",
        env="DATABASE_URL",
    )
    # OTP settings
    otp_secret_key: str = Field(
        default="your-secret-key-change-in-production", env="OTP_SECRET_KEY"
    )
    otp_expiry_minutes: int = Field(default=10, env="OTP_EXPIRY_MINUTES")
    otp_requests_per_minute: int = 5
    otp_requests_burst: int = 10

    # JWT settings (for future use)
    jwt_secret_key: str = Field(
        default="your-jwt-secret-key-change-in-production", env="JWT_SECRET_KEY"
    )
    jwt_algorithm: str = Field(default="HS256", env="JWT_ALGORITHM")
    jwt_expiry_minutes: int = Field(default=30, env="JWT_EXPIRY_MINUTES")

    class Config:
        env_file = ".env"
        env_prefix = "APP_"
        case_sensitive = False


settings = Settings()
