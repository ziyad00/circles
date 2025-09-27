from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..schemas import PhoneOTPRequest, PhoneOTPVerify, OTPResponse, AuthResponse, UserResponse
from ..services.otp_service import OTPService
from ..services.jwt_service import JWTService, security
from ..services.storage import StorageService
from ..models import User, Follow, CheckIn
from sqlalchemy import select, func
from ..config import settings
from datetime import datetime, timedelta, timezone


# Simple in-memory throttle store (phone+ip → list of timestamps)
_otp_request_log: dict[tuple[str, str], list[datetime]] = {}
_otp_verify_log: dict[tuple[str, str], list[datetime]] = {}


def _convert_single_to_signed_url(photo_url: str | None) -> str | None:
    """Convert a single storage key or S3 URL to a signed URL."""
    if not photo_url:
        return None

    if not photo_url.startswith("http"):
        if settings.storage_backend == "local":
            return f"http://localhost:8000{photo_url}"
        try:
            signed_url = StorageService.generate_signed_url(photo_url)
            return signed_url
        except Exception as exc:
            return photo_url
    if "s3.amazonaws.com" in photo_url or "circles-media" in photo_url:
        try:
            if "s3.amazonaws.com" in photo_url and "/" in photo_url:
                if "/circles-media" in photo_url:
                    s3_key = photo_url.split("/circles-media", 1)[1].lstrip("/")
                else:
                    s3_key = photo_url.split(".s3.amazonaws.com/", 1)[1]
            else:
                s3_key = photo_url.split(".amazonaws.com/", 1)[1]
            signed_url = StorageService.generate_signed_url(s3_key)
            return signed_url
        except Exception as exc:
            return photo_url
    # Return the original URL if it's already a signed URL or external URL
    return photo_url

router = APIRouter(
    prefix="/auth",
    tags=["authentication"],
    responses={
        404: {"description": "User not found"},
        429: {"description": "Rate limit exceeded"},
        500: {"description": "Internal server error"}
    }
)


@router.post("/request-otp", response_model=OTPResponse, include_in_schema=False)
async def request_otp(
    request: PhoneOTPRequest,
    db: AsyncSession = Depends(get_db),
    http_request: Request = None,
):
    """
    Request an OTP code for authentication.

    This endpoint will:
    - Create a new user if they don't exist
    - Generate and send an OTP code
    - Apply rate limiting (3 requests per minute per IP)

    **Rate Limits:**
    - 3 requests per minute per IP address
    - 10 requests per 5 minutes per IP address (burst protection)

    **Development Mode:**
    - OTP code is returned in response for testing
    - In production, this would be sent via SMS

    **Response:**
    - `message`: Success message with OTP code (dev mode)
    - `expires_in_minutes`: How long the OTP is valid
    """
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Email/legacy OTP route is disabled. Use /onboarding/request-otp."
    )


@router.post("/verify-otp", response_model=AuthResponse, include_in_schema=False)
async def verify_otp(
    request: PhoneOTPVerify,
    db: AsyncSession = Depends(get_db),
    http_request: Request = None,
):
    """
    Verify OTP code and authenticate user.

    This endpoint will:
    - Validate the provided OTP code
    - Return user information and JWT access token
    - Apply rate limiting (5 attempts per minute per IP)

    **Rate Limits:**
    - 5 verification attempts per minute per IP address

    **Response:**
    - `message`: Success message
    - `user`: User profile information
    - `access_token`: JWT token for authenticated requests

    **Usage:**
    Include the access_token in subsequent requests:
    ```
    Authorization: Bearer <access_token>
    ```
    """
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Email/legacy OTP route is disabled. Use /onboarding/verify-otp."
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user(
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get current authenticated user's profile.

    **Authentication Required:** Yes

    **Response:**
    - Complete user profile information
    - Includes privacy settings and preferences

    **Use Cases:**
    - Display user profile in app
    - Check user settings and preferences
    - Verify authentication status
    """
    try:
        followers_count = await db.scalar(
            select(func.count(Follow.id)).where(
                Follow.followee_id == current_user.id)
        )
        following_count = await db.scalar(
            select(func.count(Follow.id)).where(
                Follow.follower_id == current_user.id)
        )

        check_in_count = await db.scalar(
            select(func.count(CheckIn.id)).where(
                CheckIn.user_id == current_user.id)
        )

        return UserResponse(
            id=current_user.id,
            phone=current_user.phone,
            is_verified=current_user.is_verified,
            username=current_user.username,
            name=current_user.name,
            bio=current_user.bio,
            avatar_url=_convert_single_to_signed_url(current_user.avatar_url),
            availability_status=current_user.availability_status,
            availability_mode=current_user.availability_mode,
            created_at=current_user.created_at,
            followers_count=followers_count or 0,
            following_count=following_count or 0,
            check_in_count=check_in_count or 0,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating user response: {str(e)}"
        )
