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
        default="postgresql+asyncpg://postgres:password@postgres:5432/circles",
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

    # Storage settings
    storage_backend: str = Field(
        default="local", env="STORAGE_BACKEND")  # "local" or "s3"
    s3_bucket: Optional[str] = Field(default=None, env="S3_BUCKET")
    s3_region: Optional[str] = Field(default=None, env="S3_REGION")
    s3_endpoint_url: Optional[str] = Field(default=None, env="S3_ENDPOINT_URL")
    s3_access_key_id: Optional[str] = Field(
        default=None, env="S3_ACCESS_KEY_ID")
    s3_secret_access_key: Optional[str] = Field(
        default=None, env="S3_SECRET_ACCESS_KEY")
    s3_public_base_url: Optional[str] = Field(
        default=None, env="S3_PUBLIC_BASE_URL")
    s3_use_path_style: bool = Field(default=False, env="S3_USE_PATH_STYLE")

    # Metrics
    metrics_token: Optional[str] = Field(default=None, env="METRICS_TOKEN")

    # Geo
    use_postgis: bool = Field(default=True, env="USE_POSTGIS")
    # Check-in proximity enforcement
    checkin_enforce_proximity: bool = Field(
        default=True, env="CHECKIN_ENFORCE_PROXIMITY")
    # Max allowed distance in meters between user and place to allow check-in
    checkin_max_distance_meters: int = Field(
        default=500, env="CHECKIN_MAX_DISTANCE_METERS")

    # Place Data API Keys
    google_places_api_key: Optional[str] = Field(
        default=None, env="GOOGLE_PLACES_API_KEY"
    )
    foursquare_api_key: Optional[str] = Field(
        default="demo_key_for_testing", env="FOURSQUARE_API_KEY"
    )
    use_openstreetmap: bool = Field(
        default=True, env="USE_OPENSTREETMAP"
    )

    class Config:
        env_file = ".env"
        env_prefix = "APP_"
        case_sensitive = False


settings = Settings()
