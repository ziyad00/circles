from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


class UserBase(BaseModel):
    email: EmailStr
    phone: Optional[str] = None


class UserCreate(UserBase):
    pass


class UserResponse(UserBase):
    id: int
    is_verified: bool
    created_at: datetime

    class Config:
        from_attributes = True


class OTPRequest(BaseModel):
    email: EmailStr


class OTPVerify(BaseModel):
    email: EmailStr
    otp_code: str


class OTPResponse(BaseModel):
    message: str
    expires_in_minutes: int


class AuthResponse(BaseModel):
    message: str
    user: UserResponse
    access_token: Optional[str] = None  # For future JWT implementation


class ErrorResponse(BaseModel):
    detail: str
