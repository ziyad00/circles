from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..schemas import OTPRequest, OTPVerify, OTPResponse, AuthResponse, UserResponse
from ..services.otp_service import OTPService
from ..services.jwt_service import JWTService, security
from ..models import User

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

            # Generate JWT token
        access_token = JWTService.create_access_token(
            data={"sub": str(user.id), "email": user.email}
        )

        # Convert user to response model
        user_response = UserResponse.from_orm(user)

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
async def get_current_user_info(
    current_user: User = Depends(JWTService.get_current_user)
):
    """
    Get current authenticated user information.
    This endpoint requires a valid JWT token.
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
