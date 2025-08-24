import random
import string
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from ..models import User, OTPCode
from ..config import settings


class OTPService:
    @staticmethod
    def generate_otp() -> str:
        """Generate a random 6-digit OTP code"""
        return ''.join(random.choices(string.digits, k=6))

    @staticmethod
    async def create_user_if_not_exists(db: AsyncSession, email: str, phone: str = None) -> User:
        """Create a new user if they don't exist"""
        # Check if user exists by email OR phone (if provided)
        conditions = [User.email == email]
        if phone:
            conditions.append(User.phone == phone)

        stmt = select(User).where(or_(*conditions))
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        if user is None:
            # Create new user
            user = User(email=email, phone=phone)
            db.add(user)
            await db.commit()
            await db.refresh(user)
        else:
            # Update phone if user exists but phone is different
            if phone and user.phone != phone:
                user.phone = phone
                await db.commit()
                await db.refresh(user)

        return user

    @staticmethod
    async def create_otp(db: AsyncSession, user_id: int) -> OTPCode:
        """Create a new OTP code for a user"""
        # Invalidate any existing unused OTP codes for this user
        stmt = select(OTPCode).where(
            and_(
                OTPCode.user_id == user_id,
                OTPCode.is_used == False,
                OTPCode.expires_at > datetime.now(timezone.utc)
            )
        )
        result = await db.execute(stmt)
        existing_otps = result.scalars().all()

        for otp in existing_otps:
            otp.is_used = True

        # Generate new OTP
        otp_code = OTPService.generate_otp()
        expires_at = datetime.now(timezone.utc) + \
            timedelta(minutes=settings.otp_expiry_minutes)

        # Create OTP record
        otp = OTPCode(
            user_id=user_id,
            code=otp_code,
            expires_at=expires_at
        )

        db.add(otp)
        await db.commit()
        await db.refresh(otp)

        return otp

    @staticmethod
    async def verify_otp(db: AsyncSession, email: str, otp_code: str) -> tuple[bool, User]:
        """Verify OTP code and return success status and user"""
        # Get user
        stmt = select(User).where(User.email == email)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            return False, None

        # Get the most recent unused OTP for this user
        stmt = select(OTPCode).where(
            and_(
                OTPCode.user_id == user.id,
                OTPCode.code == otp_code,
                OTPCode.is_used == False,
                OTPCode.expires_at > datetime.now(timezone.utc)
            )
        ).order_by(OTPCode.created_at.desc())

        result = await db.execute(stmt)
        otp = result.scalar_one_or_none()

        if not otp:
            return False, user

        # Mark OTP as used
        otp.is_used = True
        user.is_verified = True
        await db.commit()

        return True, user
