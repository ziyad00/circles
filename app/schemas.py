from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional, Union, List
from enum import Enum
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
    model_config = ConfigDict(from_attributes=True)


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


"""Friends feature removed in favor of follows."""


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
    model_config = ConfigDict(from_attributes=True)


class VisibilityEnum(str, Enum):
    public = "public"
    friends = "friends"
    private = "private"


class CheckInCreate(BaseModel):
    place_id: int = Field(..., examples=[1])
    note: Optional[str] = Field(None, examples=["Latte time"])
    visibility: Optional[VisibilityEnum] = Field(
        default=None,
        examples=[VisibilityEnum.public,
                  VisibilityEnum.friends, VisibilityEnum.private],
    )


class CheckInResponse(BaseModel):
    id: int
    user_id: int
    place_id: int
    note: Optional[str] = None
    visibility: VisibilityEnum
    created_at: datetime
    expires_at: datetime
    # Deprecated single photo url; keep for backward compatibility
    photo_url: Optional[str] = None
    # New: multiple photos
    photo_urls: list[str] = []
    model_config = ConfigDict(from_attributes=True)


class SavedPlaceCreate(BaseModel):
    place_id: int = Field(..., examples=[1])
    list_name: Optional[str] = Field(None, examples=["Favorites"])


class SavedPlaceResponse(BaseModel):
    id: int
    user_id: int
    place_id: int
    list_name: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


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
    model_config = ConfigDict(from_attributes=True)


class PaginatedReviews(BaseModel):
    items: list[ReviewResponse]
    total: int
    limit: int
    offset: int


class PlaceStats(BaseModel):
    place_id: int
    average_rating: Optional[float] = None
    reviews_count: int
    active_checkins: int


# Photos

class PhotoCreate(BaseModel):
    review_id: int = Field(..., examples=[1])
    url: str = Field(..., examples=["https://example.com/photo.jpg"])
    caption: Optional[str] = Field(None, examples=["Latte art"])


class PhotoResponse(BaseModel):
    id: int
    user_id: int
    place_id: int
    review_id: Optional[int] = None
    url: str
    caption: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class CheckInPhotoResponse(BaseModel):
    id: int
    check_in_id: int
    url: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class PaginatedPhotos(BaseModel):
    items: list[PhotoResponse]
    total: int
    limit: int
    offset: int

# Direct Messages (DM)


class DMThreadStatus(str, Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"
    blocked = "blocked"


class DMThreadResponse(BaseModel):
    id: int
    user_a_id: int
    user_b_id: int
    initiator_id: int
    status: DMThreadStatus
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class PaginatedDMThreads(BaseModel):
    items: list[DMThreadResponse]
    total: int
    limit: int
    offset: int


class DMRequestCreate(BaseModel):
    recipient_email: EmailStr
    text: str = Field(..., min_length=1, max_length=2000)


class DMRequestDecision(BaseModel):
    status: DMThreadStatus = Field(..., examples=[DMThreadStatus.accepted])


class DMMessageCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)


class DMMessageResponse(BaseModel):
    id: int
    thread_id: int
    sender_id: int
    text: str
    created_at: datetime
    # computed for the requester: True if the other participant has read this message
    seen: Optional[bool] = None
    heart_count: int = 0
    liked_by_me: bool = False
    model_config = ConfigDict(from_attributes=True)


class PaginatedDMMessages(BaseModel):
    items: list[DMMessageResponse]
    total: int
    limit: int
    offset: int


class DMThreadMuteUpdate(BaseModel):
    muted: bool = Field(..., examples=[True])


class UnreadCountResponse(BaseModel):
    unread: int


class DMThreadBlockUpdate(BaseModel):
    blocked: bool = Field(..., examples=[True])


class TypingUpdate(BaseModel):
    typing: bool = Field(..., examples=[True])


class TypingStatusResponse(BaseModel):
    typing: bool
    until: Optional[datetime] = None


class PresenceResponse(BaseModel):
    user_id: int
    online: bool
    last_active_at: Optional[datetime] = None

# Follows


class FollowUserResponse(BaseModel):
    id: int
    email: str
    is_verified: bool
    created_at: datetime
    followed_at: datetime
    model_config = ConfigDict(from_attributes=True)


class PaginatedFollowers(BaseModel):
    items: list[FollowUserResponse]
    total: int
    limit: int
    offset: int


class PaginatedFollowing(BaseModel):
    items: list[FollowUserResponse]
    total: int
    limit: int
    offset: int


class HeartResponse(BaseModel):
    liked: bool
    heart_count: int


# Check-in Collections


class CollectionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    visibility: Optional[VisibilityEnum] = None


class CollectionResponse(BaseModel):
    id: int
    user_id: int
    name: str
    visibility: VisibilityEnum
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class PaginatedCollections(BaseModel):
    items: list[CollectionResponse]
    total: int
    limit: int
    offset: int


class CollectionItemResponse(BaseModel):
    id: int
    collection_id: int
    check_in_id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class PrivacySettingsUpdate(BaseModel):
    dm_privacy: Optional[str] = Field(
        None, pattern="^(everyone|followers|no_one)$")
    checkins_default_visibility: Optional[VisibilityEnum] = None
    collections_default_visibility: Optional[VisibilityEnum] = None


class PrivacySettingsResponse(BaseModel):
    dm_privacy: str
    checkins_default_visibility: VisibilityEnum
    collections_default_visibility: VisibilityEnum
