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
    name: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
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


class AdvancedSearchFilters(BaseModel):
    # Text search
    query: Optional[str] = None
    # Location filters
    city: Optional[str] = None
    neighborhood: Optional[str] = None
    # Category filters
    categories: Optional[list[str]] = None
    # Rating filters
    rating_min: Optional[float] = Field(None, ge=0, le=5)
    rating_max: Optional[float] = Field(None, ge=0, le=5)
    # Activity filters
    has_recent_checkins: Optional[bool] = None  # Has check-ins in last 24h
    has_reviews: Optional[bool] = None  # Has any reviews
    has_photos: Optional[bool] = None  # Has photos from reviews
    # Distance filters (if coordinates provided)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    radius_km: Optional[float] = Field(
        None, ge=0.1, le=100)  # Search radius in km
    # Sort options
    sort_by: Optional[str] = Field(
        None, pattern="^(name|rating|created_at|checkins|recent_checkins)$")
    sort_order: Optional[str] = Field(None, pattern="^(asc|desc)$")
    # Pagination
    limit: int = Field(20, ge=1, le=100)
    offset: int = Field(0, ge=0)


class SearchSuggestion(BaseModel):
    type: str  # "city", "neighborhood", "category"
    value: str
    count: int


class SearchSuggestions(BaseModel):
    cities: list[SearchSuggestion]
    neighborhoods: list[SearchSuggestion]
    categories: list[SearchSuggestion]


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


class EnhancedPlaceResponse(BaseModel):
    id: int
    name: str
    address: Optional[str] = None
    city: Optional[str] = None
    neighborhood: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    categories: Optional[str] = None
    rating: Optional[float] = None
    created_at: datetime
    # Enhanced stats
    stats: PlaceStats
    # Current active check-ins count (last 24h)
    current_checkins: int
    # Total check-ins ever
    total_checkins: int
    # Recent reviews count (last 30 days)
    recent_reviews: int
    # Photos count
    photos_count: int
    # Is user currently checked in (if authenticated)
    is_checked_in: Optional[bool] = None
    # User's saved status (if authenticated)
    is_saved: Optional[bool] = None
    model_config = ConfigDict(from_attributes=True)


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


class CheckInCommentCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=1000)


class CheckInCommentResponse(BaseModel):
    id: int
    check_in_id: int
    user_id: int
    user_name: str
    user_avatar_url: Optional[str] = None
    content: str
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class PaginatedCheckInComments(BaseModel):
    items: list[CheckInCommentResponse]
    total: int
    limit: int
    offset: int


class CheckInLikeResponse(BaseModel):
    id: int
    check_in_id: int
    user_id: int
    user_name: str
    user_avatar_url: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class PaginatedCheckInLikes(BaseModel):
    items: list[CheckInLikeResponse]
    total: int
    limit: int
    offset: int


class DetailedCheckInResponse(BaseModel):
    id: int
    user_id: int
    user_name: str
    user_avatar_url: Optional[str] = None
    place_id: int
    place_name: str
    place_address: Optional[str] = None
    place_city: Optional[str] = None
    place_neighborhood: Optional[str] = None
    place_categories: Optional[str] = None
    place_rating: Optional[float] = None
    note: Optional[str] = None
    visibility: str
    created_at: datetime
    updated_at: datetime
    # Enhanced details
    photo_urls: list[str] = []
    likes_count: int
    comments_count: int
    is_liked_by_current_user: Optional[bool] = None
    can_edit: bool
    can_delete: bool
    model_config = ConfigDict(from_attributes=True)


class CheckInStats(BaseModel):
    check_in_id: int
    likes_count: int
    comments_count: int
    views_count: int
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


# Users / Profiles


class UserUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    bio: Optional[str] = Field(None, max_length=500)
    # avatar uploaded via multipart; url is server-filled


class PublicUserResponse(BaseModel):
    id: int
    email: EmailStr
    name: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class InterestCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)


class InterestResponse(BaseModel):
    id: int
    user_id: int
    name: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class SupportTicketCreate(BaseModel):
    subject: str = Field(..., min_length=1, max_length=200)
    body: str = Field(..., min_length=1, max_length=5000)


class SupportTicketResponse(BaseModel):
    id: int
    user_id: int
    subject: str
    body: str
    status: str
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class PaginatedMedia(BaseModel):
    items: list[str]
    total: int
    limit: int
    offset: int


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
