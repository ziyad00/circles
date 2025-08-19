from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Union, List
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


# Places & Check-ins

class PlaceBase(BaseModel):
    name: str = Field(..., examples=["Blue Bottle Coffee"])
    address: Optional[str] = Field(None, examples=["123 Market St"])
    city: Optional[str] = Field(None, examples=["San Francisco"])
    neighborhood: Optional[str] = Field(None, examples=["SoMa"])
    latitude: Optional[float] = Field(None, examples=[37.781])
    longitude: Optional[float] = Field(None, examples=[-122.404])
    # Accept either a comma-separated string or a list of strings
    categories: Optional[Union[str, List[str]]] = Field(
        None, examples=[["coffee", "cafe"], "coffee,cafe"]
    )
    rating: Optional[float] = Field(None, examples=[4.5])


class PlaceCreate(PlaceBase):
    name: str


class PlaceResponse(PlaceBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class CheckInCreate(BaseModel):
    place_id: int = Field(..., examples=[1])
    note: Optional[str] = Field(None, examples=["Latte time"])
    visibility: Optional[str] = Field(
        "public", examples=["public", "friends", "private"])


class CheckInResponse(BaseModel):
    id: int
    user_id: int
    place_id: int
    note: Optional[str] = None
    visibility: str
    created_at: datetime
    expires_at: datetime

    class Config:
        from_attributes = True


class SavedPlaceCreate(BaseModel):
    place_id: int = Field(..., examples=[1])
    list_name: Optional[str] = Field(None, examples=["Favorites"])


class SavedPlaceResponse(BaseModel):
    id: int
    user_id: int
    place_id: int
    list_name: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class PaginatedPlaces(BaseModel):
    items: list[PlaceResponse]
    total: int
    limit: int
    offset: int


class PaginatedSavedPlaces(BaseModel):
    items: list[SavedPlaceResponse]
    total: int
    limit: int
    offset: int


class PaginatedCheckIns(BaseModel):
    items: list[CheckInResponse]
    total: int
    limit: int
    offset: int


class ReviewCreate(BaseModel):
    rating: float = Field(..., ge=0, le=5, examples=[4.5])
    text: Optional[str] = Field(None, examples=["Great spot!"])


class ReviewResponse(BaseModel):
    id: int
    user_id: int
    place_id: int
    rating: float
    text: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class PaginatedReviews(BaseModel):
    items: list[ReviewResponse]
    total: int
    limit: int
    offset: int
