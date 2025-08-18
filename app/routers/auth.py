from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..schemas import OTPRequest, OTPVerify, OTPResponse, AuthResponse, UserResponse
from ..services.otp_service import OTPService

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/request-otp", response_model=OTPResponse)
async def request_otp(
    request: OTPRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Request an OTP code for authentication.
    This will create a user if they don't exist and send an OTP code.
    """
    try:
        # Create user if not exists
        user = await OTPService.create_user_if_not_exists(db, request.email)

        # Generate OTP
        otp = await OTPService.create_otp(db, user.id)

        # In a real application, you would send this OTP via email/SMS
        # For now, we'll return it in the response (for development only)
        return OTPResponse(
            message=f"OTP code sent to {request.email}. For development: {otp.code}",
            expires_in_minutes=10
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send OTP: {str(e)}"
        )


@router.post("/verify-otp", response_model=AuthResponse)
async def verify_otp(
    request: OTPVerify,
    db: AsyncSession = Depends(get_db)
):
    """
    Verify OTP code and authenticate user.
    """
    try:
        # Verify OTP
        is_valid, user = await OTPService.verify_otp(db, request.email, request.otp_code)

        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired OTP code"
            )

        # Convert user to response model
        user_response = UserResponse.from_orm(user)

        return AuthResponse(
            message="OTP verified successfully",
            user=user_response,
            access_token=None  # Will be implemented with JWT later
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to verify OTP: {str(e)}"
        )
