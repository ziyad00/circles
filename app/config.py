from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional, List
from typing import Optional


class Settings(BaseSettings):
    # App settings
    debug: bool = Field(default=False, env="APP_DEBUG")
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
        env="APP_DATABASE_URL",  # Use APP_DATABASE_URL for AWS deployment
    )
    # OTP settings
    otp_secret_key: str = Field(
        default="your-secret-key-change-in-production", env="OTP_SECRET_KEY"
    )
    otp_expiry_minutes: int = Field(default=10, env="OTP_EXPIRY_MINUTES")
    # OTP rate limiting (configurable; disabled by default)
    otp_rate_limit_enabled: bool = Field(
        default=False, env="OTP_RATE_LIMIT_ENABLED")
    otp_requests_per_minute: int = Field(
        default=5, env="OTP_REQUESTS_PER_MINUTE")
    otp_requests_burst: int = Field(default=10, env="OTP_REQUESTS_BURST")

    # JWT settings (for future use)
    jwt_secret_key: str = Field(
        default="your-jwt-secret-key-change-in-production", env="JWT_SECRET_KEY"
    )
    jwt_algorithm: str = Field(default="HS256", env="JWT_ALGORITHM")
    # 1 week = 7 * 24 * 60 = 10,080 minutes
    jwt_expiry_minutes: int = Field(default=10080, env="JWT_EXPIRY_MINUTES")

    # Storage settings
    storage_backend: str = Field(
        default="s3", env="STORAGE_BACKEND")  # "local" or "s3"
    local_base_url: str = Field(
        # Base URL for local storage URLs
        default="http://10.0.2.2:8000", env="LOCAL_BASE_URL")
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
    use_postgis: bool = Field(default=False, env="USE_POSTGIS")
    # Check-in proximity enforcement
    checkin_enforce_proximity: bool = Field(
        default=True, env="CHECKIN_ENFORCE_PROXIMITY")
    # Max allowed distance in meters between user and place to allow check-in
    checkin_max_distance_meters: int = Field(
        default=500, env="CHECKIN_MAX_DISTANCE_METERS")

    # Place Data API Keys
    foursquare_api_key: Optional[str] = Field(
        default="FL4GZDJSAF340RYNVLFW4RLQOHZ0IY0X0YVX2LNWUNKAGYZX", env="FOURSQUARE_API_KEY"
    )
    foursquare_client_id: Optional[str] = Field(
        default="5T23EOYWM05NXX5VUNAZEY4WXJNSQ4Q5J115EVM5BNWUC3LV", env="FOURSQUARE_CLIENT_ID"
    )
    foursquare_client_secret: Optional[str] = Field(
        default="YBYIORTLA2DUPRYQDGF0T5URS23AWIMUU22SHAOHU4OAWFIT", env="FOURSQUARE_CLIENT_SECRET"
    )
    use_openstreetmap: bool = Field(
        default=True, env="USE_OPENSTREETMAP"
    )

    # Overpass API endpoints (comma-separated or JSON array in env)
    overpass_endpoints: List[str] = Field(
        default=[
            "https://overpass-api.de/api/interpreter",
            "https://overpass.kumi.systems/api/interpreter",
            "https://lz4.overpass-api.de/api/interpreter",
        ],
        env="OVERPASS_ENDPOINTS",
    )

    # DM limits
    dm_requests_per_min: int = Field(default=5, env="DM_REQUESTS_PER_MIN")
    dm_messages_per_min: int = Field(default=20, env="DM_MESSAGES_PER_MIN")

    # DM behavior
    # If true, bypass DM request gate and auto-accept new threads (still respects blocks)
    dm_allow_direct: bool = Field(default=True, env="DM_ALLOW_DIRECT")

    # Timeouts
    http_timeout_seconds: int = Field(default=30, env="HTTP_TIMEOUT_SECONDS")
    overpass_timeout_seconds: int = Field(
        default=25, env="OVERPASS_TIMEOUT_SECONDS")
    ws_send_timeout_seconds: int = Field(
        default=5, env="WS_SEND_TIMEOUT_SECONDS")

    # Enrichment
    enrich_ttl_hot_days: int = Field(default=14, env="ENRICH_TTL_HOT_DAYS")
    enrich_ttl_cold_days: int = Field(default=60, env="ENRICH_TTL_COLD_DAYS")
    enrich_max_distance_m: int = Field(
        default=150, env="ENRICH_MAX_DISTANCE_M")
    enrich_min_name_similarity: float = Field(
        default=0.65, env="ENRICH_MIN_NAME_SIM")

    # Foursquare trending fallback/override
    fsq_trending_enabled: bool = Field(
        default=True, env="FSQ_TRENDING_ENABLED"
    )
    # If true, always use FSQ trending instead of internal trending
    fsq_trending_override: bool = Field(
        default=True, env="FSQ_TRENDING_OVERRIDE"
    )
    fsq_trending_radius_m: int = Field(
        default=5000, env="FSQ_TRENDING_RADIUS_M"
    )
    # If true, use real v2 trending endpoint instead of v3 popularity sort
    fsq_use_real_trending: bool = Field(
        default=True, env="FSQ_USE_REAL_TRENDING"
    )

    # Place chat (ephemeral, check-in gated)
    place_chat_window_hours: int = Field(
        default=12, env="PLACE_CHAT_WINDOW_HOURS"
    )
    checkin_expiry_hours: int = Field(
        default=24, env="CHECKIN_EXPIRY_HOURS"
    )
    photo_aggregation_hours: int = Field(
        default=6, env="PHOTO_AGGREGATION_HOURS"
    )

    # Auto-seeding
    autoseed_enabled: bool = Field(default=True, env="AUTOSEED_ENABLED")
    autoseed_min_osm_count: int = Field(
        default=500, env="AUTOSEED_MIN_OSM_COUNT")

    # Upload limits (MB)
    avatar_max_mb: int = Field(default=5, env="AVATAR_MAX_MB")
    photo_max_mb: int = Field(default=10, env="PHOTO_MAX_MB")

    # External suggestions radius
    external_suggestions_radius_m: int = Field(
        default=10000, env="EXTERNAL_SUGGESTIONS_RADIUS_M")

    # Logging
    log_sample_rate: float = Field(default=0.1, env="LOG_SAMPLE_RATE")

    class Config:
        env_file = ".env"
        env_prefix = "APP_"
        case_sensitive = False
        extra = "ignore"


settings = Settings()
