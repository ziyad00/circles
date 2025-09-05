from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Union, List
from enum import Enum
from datetime import datetime


class UserBase(BaseModel):
    phone: Optional[str] = None


class UserCreate(UserBase):
    pass


class UserResponse(UserBase):
    id: int
    is_verified: bool
    username: Optional[str] = None
    name: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    created_at: datetime
    followers_count: Optional[int] = None
    following_count: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)


class OTPRequest(BaseModel):
    phone: str


class OTPVerify(BaseModel):
    phone: str
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
    country: Optional[str] = Field(None, examples=["Saudi Arabia"])
    city: Optional[str] = Field(None, examples=["San Francisco"])
    neighborhood: Optional[str] = Field(None, examples=["SoMa"])
    latitude: Optional[float] = Field(None, examples=[37.781])
    longitude: Optional[float] = Field(None, examples=[-122.404])
    description: Optional[str] = Field(
        None, examples=["Specialty coffee and pastries in a modern space."])
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
    # Optional representative photo for list views (latest review/check-in photo)
    photo_url: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class VisibilityEnum(str, Enum):
    public = "public"
    friends = "friends"
    private = "private"


class CheckInCreate(BaseModel):
    place_id: int = Field(..., examples=[1])
    note: Optional[str] = Field(None, examples=["Latte time"])
    latitude: float = Field(..., ge=-90, le=90, examples=[24.7136])
    longitude: float = Field(..., ge=-180, le=180, examples=[46.6753])
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
    # Whether this check-in is still eligible for place chat (within window)
    allowed_to_chat: bool = False
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


class WhosHereItem(BaseModel):
    check_in_id: int
    user_id: int
    user_name: str
    username: Optional[str] = None
    user_avatar_url: Optional[str] = None
    created_at: datetime
    photo_urls: list[str] = []


class PaginatedWhosHere(BaseModel):
    items: list[WhosHereItem]
    total: int
    limit: int
    offset: int


class UserSearchFilters(BaseModel):
    q: Optional[str] = None
    has_avatar: Optional[bool] = None
    interests: Optional[list[str]] = None
    limit: int = Field(20, ge=1, le=100)
    offset: int = Field(0, ge=0)


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
    country: Optional[str] = None
    city: Optional[str] = None
    neighborhood: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    categories: Optional[str] = None
    rating: Optional[float] = None
    description: Optional[str] = None
    # Price tier as $, $$, $$$, $$$$
    price_tier: Optional[str] = None
    # Human-friendly opening hours string (if available)
    opening_hours: Optional[str] = None
    # Direct link to Google Maps directions/search for this place
    google_maps_url: Optional[str] = None
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
    # Whether current user can check in now (given optional lat/lng and cooldown)
    can_check_in: Optional[bool] = None
    # If cannot check in, a short reason string
    check_in_block_reason: Optional[str] = None
    # Optional amenities derived from external sources (e.g., FSQ attributes)
    amenities: Optional[dict[str, bool]] = None
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
    content: str = Field(..., min_length=1, max_length=1000,
                         description="Comment content")


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
    note: Optional[str] = None
    visibility: VisibilityEnum
    created_at: datetime
    expires_at: datetime
    photo_url: Optional[str] = None
    photo_urls: list[str] = []
    likes_count: int = 0
    comments_count: int = 0
    is_liked_by_user: bool = False
    allowed_to_chat: bool = False
    model_config = ConfigDict(from_attributes=True)


class CheckInStats(BaseModel):
    likes_count: int
    comments_count: int
    is_liked_by_user: bool


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
    # Additional fields for inbox display
    other_user_name: Optional[str] = None
    other_user_username: Optional[str] = None
    other_user_avatar: Optional[str] = None
    last_message: Optional[str] = None
    last_message_time: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class PaginatedDMThreads(BaseModel):
    items: list[DMThreadResponse]
    total: int
    limit: int
    offset: int


class DMRequestCreate(BaseModel):
    recipient_id: int
    text: str = Field(..., min_length=1, max_length=2000)


class DMRequestDecision(BaseModel):
    status: DMThreadStatus = Field(..., examples=[DMThreadStatus.accepted])


class DMMessageCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    reply_to_id: Optional[int] = None
    # Media attachments
    photo_urls: list[str] = Field(default_factory=list, max_length=10)
    video_urls: list[str] = Field(default_factory=list, max_length=5)


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
    # Reply functionality
    reply_to_id: Optional[int] = None
    reply_to_text: Optional[str] = None
    reply_to_sender_name: Optional[str] = None
    # Media attachments
    photo_urls: list[str] = Field(default_factory=list)
    video_urls: list[str] = Field(default_factory=list)
    model_config = ConfigDict(from_attributes=True)


class PaginatedDMMessages(BaseModel):
    items: list[DMMessageResponse]
    total: int
    limit: int
    offset: int


class DMThreadMuteUpdate(BaseModel):
    muted: bool = Field(..., examples=[True])


class DMThreadPinUpdate(BaseModel):
    pinned: bool = Field(..., examples=[True])


class DMThreadArchiveUpdate(BaseModel):
    archived: bool = Field(..., examples=[True])


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
    username: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    is_verified: bool
    created_at: datetime
    followed_at: datetime
    # Whether the current user follows this user
    followed: bool = False
    model_config = ConfigDict(from_attributes=True)


class FollowStatusResponse(BaseModel):
    followed: bool


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


# Users search result with follow status relative to current user
class PublicUserSearchResponse(BaseModel):
    id: int
    name: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    created_at: datetime
    username: Optional[str] = None
    followed: bool = False
    model_config = ConfigDict(from_attributes=True)


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
    name: Optional[str] = None
    username: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    created_at: datetime
    followers_count: Optional[int] = None
    following_count: Optional[int] = None
    check_ins_count: Optional[int] = None
    is_followed: Optional[bool] = None
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
    # Map model attribute 'message' to response field 'body'
    body: str = Field(validation_alias='message', serialization_alias='body')
    status: str
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


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


class NotificationPreferencesUpdate(BaseModel):
    dm_messages: Optional[bool] = None
    dm_requests: Optional[bool] = None
    follows: Optional[bool] = None
    likes: Optional[bool] = None
    comments: Optional[bool] = None
    activity_summary: Optional[bool] = None
    marketing: Optional[bool] = None


class NotificationPreferencesResponse(BaseModel):
    dm_messages: bool
    dm_requests: bool
    follows: bool
    likes: bool
    comments: bool
    activity_summary: bool
    marketing: bool


class ActivityItem(BaseModel):
    id: int
    user_id: int
    user_name: str
    user_avatar_url: Optional[str] = None
    activity_type: str  # "checkin", "like", "comment", "follow", "review", "collection"
    activity_data: dict
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class PaginatedActivityFeed(BaseModel):
    items: list[ActivityItem]
    total: int
    limit: int
    offset: int


class ActivityFeedFilters(BaseModel):
    activity_types: Optional[list[str]] = Field(
        None, description="Filter by activity types")
    user_ids: Optional[list[int]] = Field(
        None, description="Filter by specific users")
    since: Optional[datetime] = Field(
        None, description="Show activities since this time")
    until: Optional[datetime] = Field(
        None, description="Show activities until this time")
    limit: int = Field(20, ge=1, le=100)
    offset: int = Field(0, ge=0)


# Onboarding Flow Schemas
class PhoneOTPRequest(BaseModel):
    phone: str = Field(..., description="Phone number with country code")


class PhoneOTPVerify(BaseModel):
    phone: str = Field(..., description="Phone number with country code")
    otp_code: str = Field(..., min_length=6, max_length=6,
                          description="6-digit OTP code")


class OnboardingUserSetup(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=50,
                            description="User's first name")
    last_name: str = Field(..., min_length=1, max_length=50,
                           description="User's last name")
    username: str = Field(..., min_length=3, max_length=30,
                          description="Unique username")
    interests: list[str] = Field(default_factory=list, min_items=0,
                                 max_items=10, description="User interests (optional)")


class OnboardingResponse(BaseModel):
    message: str
    user: dict
    access_token: str
    is_new_user: bool


class UsernameCheckRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=30)


class UsernameCheckResponse(BaseModel):
    available: bool
    message: str


class ProfileStats(BaseModel):
    checkins_count: int = 0
    checkins_public_count: int = 0
    checkins_followers_count: int = 0
    checkins_private_count: int = 0
    collections_count: int = 0
    collections_public_count: int = 0
    collections_followers_count: int = 0
    collections_private_count: int = 0
    followers_count: int = 0
    following_count: int = 0
    reviews_count: int = 0
    photos_count: int = 0
    total_likes_received: int = 0
    total_comments_received: int = 0
    model_config = ConfigDict(from_attributes=True)


class PlaceHourlyStats(BaseModel):
    hour: int
    checkins_count: int
    unique_users: int
    model_config = ConfigDict(from_attributes=True)


class PlaceCrowdLevel(BaseModel):
    current_checkins: int
    average_checkins: float
    crowd_level: str  # "low", "medium", "high", "very_high"
    model_config = ConfigDict(from_attributes=True)


class EnhancedPlaceStats(BaseModel):
    total_checkins: int
    total_reviews: int
    total_photos: int
    unique_visitors: int
    average_rating: float
    popular_hours: list[PlaceHourlyStats]
    crowd_level: PlaceCrowdLevel
    recent_activity: dict  # Last 24h, 7d, 30d activity
    model_config = ConfigDict(from_attributes=True)
