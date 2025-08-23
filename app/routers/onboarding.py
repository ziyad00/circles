from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timezone, timedelta
import re

from ..database import get_db
from ..models import User, OTPCode, UserInterest
from ..schemas import (
    PhoneOTPRequest,
    PhoneOTPVerify,
    OnboardingUserSetup,
    OnboardingResponse,
    UsernameCheckRequest,
    UsernameCheckResponse,
)
from ..services.jwt_service import JWTService

router = APIRouter(
    prefix="/onboarding", 
    tags=["onboarding"],
    responses={
        400: {"description": "Invalid phone number or username format"},
        409: {"description": "Username already taken"},
        429: {"description": "Rate limit exceeded"},
        500: {"description": "Internal server error"}
    }
)


def validate_phone_number(phone: str) -> bool:
    """Validate phone number format (basic validation)"""
    # Remove all non-digit characters except +
    cleaned = re.sub(r'[^\d+]', '', phone)
    # Check if it starts with + and has 10-15 digits
    return bool(re.match(r'^\+\d{10,15}$', cleaned))


def validate_username(username: str) -> bool:
    """Validate username format"""
    # Username should be 3-30 characters, alphanumeric and underscores only
    return bool(re.match(r'^[a-zA-Z0-9_]{3,30}$', username))


@router.post("/request-otp")
async def request_phone_otp(
    payload: PhoneOTPRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Request OTP for phone number authentication.
    
    **Authentication Required:** No
    
    **Features:**
    - Phone number validation (international format)
    - Rate limiting (5-minute cooldown)
    - Creates user if not exists
    - Development mode returns OTP in response
    
    **Phone Validation:**
    - Must be international format (+1234567890)
    - 10-15 digits after country code
    - Basic format validation
    
    **Rate Limiting:**
    - 5-minute cooldown between requests
    - Prevents OTP spam
    
    **Development Mode:**
    - OTP returned in response for testing
    - In production, would send via SMS
    
    **Response:**
    - Success message
    - OTP code (dev mode only)
    - Whether user is new or existing
    
    **Use Cases:**
    - Phone-based authentication
    - User registration flow
    - Account recovery
    - Mobile app onboarding
    """

    # Validate phone number format
    if not validate_phone_number(payload.phone):
        raise HTTPException(
            status_code=400,
            detail="Invalid phone number format. Please use international format (e.g., +1234567890)"
        )

    # Check if user exists
    user_query = select(User).where(User.phone == payload.phone)
    user_result = await db.execute(user_query)
    user = user_result.scalar_one_or_none()

    # Rate limiting: prevent spam
    five_min_ago = datetime.now(timezone.utc) - timedelta(minutes=5)
    recent_otp_query = select(OTPCode).where(
        OTPCode.phone == payload.phone,
        OTPCode.created_at >= five_min_ago
    )
    recent_otp_result = await db.execute(recent_otp_query)
    if recent_otp_result.scalar_one_or_none():
        raise HTTPException(
            status_code=429,
            detail="Please wait 5 minutes before requesting another OTP"
        )

    # Generate OTP
    import random
    otp_code = str(random.randint(100000, 999999))

    # Create OTP record
    otp = OTPCode(
        phone=payload.phone,
        code=otp_code,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)
    )
    db.add(otp)
    await db.commit()

    # In production, send SMS here
    # For development, return the OTP
    return {
        "message": "OTP sent successfully",
        "otp": otp_code,  # Remove this in production
        "is_new_user": user is None
    }


@router.post("/verify-otp")
async def verify_phone_otp(
    payload: PhoneOTPVerify,
    db: AsyncSession = Depends(get_db)
):
    """Verify OTP and return user info or create new user"""

    # Validate phone number format
    if not validate_phone_number(payload.phone):
        raise HTTPException(
            status_code=400,
            detail="Invalid phone number format"
        )

    # Find valid OTP
    otp_query = select(OTPCode).where(
        OTPCode.phone == payload.phone,
        OTPCode.code == payload.otp_code,
        OTPCode.is_used == False,
        OTPCode.expires_at > datetime.now(timezone.utc)
    ).order_by(OTPCode.created_at.desc())

    otp_result = await db.execute(otp_query)
    otp = otp_result.scalar_one_or_none()

    if not otp:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired OTP"
        )

    # Mark OTP as used
    otp.is_used = True
    await db.commit()

    # Check if user exists
    user_query = select(User).where(User.phone == payload.phone)
    user_result = await db.execute(user_query)
    user = user_result.scalar_one_or_none()

    if user:
        # Existing user - return user info and token
        token = JWTService.create_token(user.id, user.phone)
        return OnboardingResponse(
            message="Login successful",
            user={
                "id": user.id,
                "phone": user.phone,
                "email": user.email,
                "username": user.username,
                "first_name": user.name.split()[0] if user.name else None,
                "last_name": " ".join(user.name.split()[1:]) if user.name and len(user.name.split()) > 1 else None,
                "is_verified": user.is_verified,
                "is_onboarded": user.username is not None
            },
            access_token=token,
            is_new_user=False
        )
    else:
        # New user - create temporary user record
        temp_user = User(
            phone=payload.phone,
            is_verified=True
        )
        db.add(temp_user)
        await db.commit()
        await db.refresh(temp_user)

        token = JWTService.create_token(temp_user.id, temp_user.phone)
        return OnboardingResponse(
            message="OTP verified. Please complete your profile.",
            user={
                "id": temp_user.id,
                "phone": temp_user.phone,
                "email": temp_user.email,
                "username": temp_user.username,
                "first_name": None,
                "last_name": None,
                "is_verified": temp_user.is_verified,
                "is_onboarded": False
            },
            access_token=token,
            is_new_user=True
        )


@router.post("/check-username")
async def check_username_availability(
    payload: UsernameCheckRequest,
    db: AsyncSession = Depends(get_db)
):
    """Check if username is available"""

    if not validate_username(payload.username):
        return UsernameCheckResponse(
            available=False,
            message="Username must be 3-30 characters long and contain only letters, numbers, and underscores"
        )

    # Check if username exists
    user_query = select(User).where(User.username == payload.username)
    user_result = await db.execute(user_query)
    existing_user = user_result.scalar_one_or_none()

    if existing_user:
        return UsernameCheckResponse(
            available=False,
            message="Username is already taken"
        )

    return UsernameCheckResponse(
        available=True,
        message="Username is available"
    )


@router.post("/complete-setup")
async def complete_user_setup(
    payload: OnboardingUserSetup,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Complete user onboarding with profile information"""

    # Validate username format
    if not validate_username(payload.username):
        raise HTTPException(
            status_code=400,
            detail="Invalid username format. Username must be 3-30 characters long and contain only letters, numbers, and underscores"
        )

    # Check if username is available
    username_query = select(User).where(User.username == payload.username)
    username_result = await db.execute(username_query)
    existing_user = username_result.scalar_one_or_none()

    if existing_user and existing_user.id != current_user.id:
        raise HTTPException(
            status_code=400,
            detail="Username is already taken"
        )

    # Update user profile
    current_user.name = f"{payload.first_name} {payload.last_name}".strip()
    current_user.username = payload.username

    # Add user interests
    for interest in payload.interests:
        user_interest = UserInterest(
            user_id=current_user.id,
            name=interest.strip()
        )
        db.add(user_interest)

    await db.commit()
    await db.refresh(current_user)

    # Generate new token with updated user info
    token = JWTService.create_token(current_user.id, current_user.phone)

    return OnboardingResponse(
        message="Profile setup completed successfully",
        user={
            "id": current_user.id,
            "phone": current_user.phone,
            "email": current_user.email,
            "username": current_user.username,
            "first_name": payload.first_name,
            "last_name": payload.last_name,
            "name": current_user.name,
            "is_verified": current_user.is_verified,
            "is_onboarded": True
        },
        access_token=token,
        is_new_user=False
    )


@router.get("/status")
async def get_onboarding_status(
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get current user's onboarding status"""

    # Get user interests
    interests_query = select(UserInterest.name).where(
        UserInterest.user_id == current_user.id)
    interests_result = await db.execute(interests_query)
    interests = [row[0] for row in interests_result.fetchall()]

    # Parse name into first and last name
    first_name = None
    last_name = None
    if current_user.name:
        name_parts = current_user.name.split()
        first_name = name_parts[0] if name_parts else None
        last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else None

    return {
        "user": {
            "id": current_user.id,
            "phone": current_user.phone,
            "email": current_user.email,
            "username": current_user.username,
            "first_name": first_name,
            "last_name": last_name,
            "name": current_user.name,
            "is_verified": current_user.is_verified,
            "is_onboarded": current_user.username is not None,
            "interests": interests
        },
        "onboarding_complete": current_user.username is not None
    }
