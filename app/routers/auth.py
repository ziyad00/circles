from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..schemas import OTPRequest, OTPVerify, OTPResponse, AuthResponse, UserResponse
from ..services.otp_service import OTPService
from ..services.jwt_service import JWTService, security
from ..models import User
from ..config import settings
from datetime import datetime, timedelta, timezone


# Simple in-memory throttle store (email+ip → list of timestamps)
_otp_request_log: dict[tuple[str, str], list[datetime]] = {}
_otp_verify_log: dict[tuple[str, str], list[datetime]] = {}

router = APIRouter(
    prefix="/auth",
    tags=["authentication"],
    responses={
        404: {"description": "User not found"},
        429: {"description": "Rate limit exceeded"},
        500: {"description": "Internal server error"}
    }
)


@router.post("/request-otp", response_model=OTPResponse)
async def request_otp(
    request: OTPRequest,
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
    - In production, this would be sent via email/SMS

    **Response:**
    - `message`: Success message with OTP code (dev mode)
    - `expires_in_minutes`: How long the OTP is valid
    """
    try:
        # Throttle by email + IP
        ip = http_request.client.host if http_request and http_request.client else "unknown"
        key = (request.email.lower(), ip)
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(minutes=1)
        entries = _otp_request_log.get(key, [])
        # keep only last minute
        entries = [ts for ts in entries if ts >= window_start]
        if len(entries) >= settings.otp_requests_per_minute:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                                detail="Too many OTP requests. Please try again later.")
        # enforce simple burst cap over 5 minutes
        burst_window_start = now - timedelta(minutes=5)
        burst_entries = [ts for ts in entries if ts >= burst_window_start]
        if len(burst_entries) >= settings.otp_requests_burst:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                                detail="Too many OTP requests. Please slow down.")
        # record request
        entries.append(now)
        _otp_request_log[key] = entries

        # Create user if not exists
        user = await OTPService.create_user_if_not_exists(db, request.email)

        # Generate OTP
        otp = await OTPService.create_otp(db, user.id)

        # In a real application, you would send this OTP via email/SMS
        # Only return OTP in response for development/debug mode
        if settings.debug:
            message = f"OTP code sent to {request.email}. For development: {otp.code}"
        else:
            message = f"OTP code sent to {request.email}"

        return OTPResponse(
            message=message,
            expires_in_minutes=settings.otp_expiry_minutes,
        )

    except HTTPException:
        # bubble up explicit HTTP errors like 429 throttle
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send OTP: {str(e)}"
        )


@router.post("/verify-otp", response_model=AuthResponse)
async def verify_otp(
    request: OTPVerify,
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
    try:
        # Throttle by email + IP (same limits as request-otp)
        ip = http_request.client.host if http_request and http_request.client else "unknown"
        key = (request.email.lower(), ip)
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(minutes=1)
        entries = _otp_verify_log.get(key, [])
        entries = [ts for ts in entries if ts >= window_start]
        if len(entries) >= settings.otp_requests_per_minute:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                                detail="Too many OTP verifications. Please try again later.")
        burst_window_start = now - timedelta(minutes=5)
        burst_entries = [ts for ts in entries if ts >= burst_window_start]
        if len(burst_entries) >= settings.otp_requests_burst:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                                detail="Too many OTP verifications. Please slow down.")
        entries.append(now)
        _otp_verify_log[key] = entries

        # Verify OTP
        is_valid, user = await OTPService.verify_otp(db, request.email, request.otp_code)

        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired OTP code"
            )

            # Generate JWT token
        access_token = JWTService.create_access_token(
            data={"sub": str(user.id), "email": user.email}
        )

        # Convert user to response model (pydantic v2)
        user_response = UserResponse.model_validate(user)

        return AuthResponse(
            message="OTP verified successfully",
            user=user_response,
            access_token=access_token
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to verify OTP: {str(e)}"
        )


@router.get("/me", response_model=UserResponse)
async def get_current_user(
    current_user: User = Depends(JWTService.get_current_user),
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
        return UserResponse(
            id=current_user.id,
            email=current_user.email,
            phone=current_user.phone,
            is_verified=current_user.is_verified,
            created_at=current_user.created_at
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating user response: {str(e)}"
        )
