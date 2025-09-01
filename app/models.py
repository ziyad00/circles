from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text, Float, UniqueConstraint, JSON
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=True)
    phone = Column(String, unique=True, index=True, nullable=True)
    username = Column(String, unique=True, index=True, nullable=True)
    is_verified = Column(Boolean, default=False)
    is_admin = Column(Boolean, default=False)
    # Profile
    name = Column(String, nullable=True)
    bio = Column(Text, nullable=True)
    avatar_url = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    # Privacy defaults
    # everyone|followers|no_one
    dm_privacy = Column(String, nullable=False, server_default="everyone")
    checkins_default_visibility = Column(
        String, nullable=False, server_default="public")
    collections_default_visibility = Column(
        String, nullable=False, server_default="public")

    # Relationships
    otp_codes = relationship("OTPCode", back_populates="user")
    check_ins = relationship("CheckIn", back_populates="user")
    saved_places = relationship("SavedPlace", back_populates="user")
    reviews = relationship("Review", back_populates="user")
    photos = relationship("Photo", back_populates="user")
    check_in_comments = relationship("CheckInComment", back_populates="user")
    check_in_likes = relationship("CheckInLike", back_populates="user")
    dm_messages = relationship("DMMessage", back_populates="sender")
    support_tickets = relationship("SupportTicket", back_populates="user")
    activities = relationship("Activity", back_populates="user")


class OTPCode(Base):
    __tablename__ = "otp_codes"

    id = Column(Integer, primary_key=True, index=True)
    # Nullable for phone-based OTP
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    phone = Column(String, nullable=True, index=True)  # For phone-based OTP
    code = Column(String(6), nullable=False)  # 6-digit OTP code
    is_used = Column(Boolean, default=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship with User
    user = relationship("User", back_populates="otp_codes")


class Place(Base):
    __tablename__ = "places"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    address = Column(String, nullable=True)
    city = Column(String, nullable=True, index=True)
    neighborhood = Column(String, nullable=True, index=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    categories = Column(String, nullable=True)  # comma-separated categories
    rating = Column(Float, nullable=True)
    description = Column(Text, nullable=True)
    # Price tier: "$", "$$", "$$$", "$$$$"
    price_tier = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # External data source fields
    # ID from external API
    external_id = Column(String, nullable=True, index=True)
    # "google", "foursquare", "osm", "osm_overpass"
    data_source = Column(String, nullable=True)
    # Foursquare-specific fields
    fsq_id = Column(String, nullable=True, unique=True, index=True)
    # "osm", "fsq" - where the place was originally discovered
    seed_source = Column(String, nullable=True, default="osm")
    website = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    # Store additional data as JSON
    place_metadata = Column(JSON, nullable=True)
    last_enriched_at = Column(DateTime(timezone=True),
                              nullable=True)  # When last enriched

    # Relationships
    check_ins = relationship("CheckIn", back_populates="place")
    saved_by = relationship("SavedPlace", back_populates="place")
    photos = relationship("Photo", back_populates="place")


class CheckIn(Base):
    __tablename__ = "check_ins"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"),
                     nullable=False, index=True)
    place_id = Column(Integer, ForeignKey("places.id"),
                      nullable=False, index=True)
    note = Column(Text, nullable=True)
    visibility = Column(String, default="public")  # public, friends, private
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    photo_url = Column(String, nullable=True)

    user = relationship("User", back_populates="check_ins")
    place = relationship("Place", back_populates="check_ins")
    # Multiple photos relationship
    photos = relationship(
        "CheckInPhoto",
        back_populates="check_in",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    # Comments and likes relationships
    comments = relationship(
        "CheckInComment", back_populates="check_in", cascade="all, delete-orphan")
    likes = relationship(
        "CheckInLike", back_populates="check_in", cascade="all, delete-orphan")


class SavedPlace(Base):
    __tablename__ = "saved_places"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"),
                     nullable=False, index=True)
    place_id = Column(Integer, ForeignKey("places.id"),
                      nullable=False, index=True)
    list_name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="saved_places")
    place = relationship("Place", back_populates="saved_by")


class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"),
                     nullable=False, index=True)
    place_id = Column(Integer, ForeignKey("places.id"),
                      nullable=False, index=True)
    rating = Column(Float, nullable=False)
    text = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="reviews")
    place = relationship("Place")


class Photo(Base):
    __tablename__ = "photos"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"),
                     nullable=False, index=True)
    place_id = Column(Integer, ForeignKey("places.id"),
                      nullable=False, index=True)
    # Optional linkage to a review (for review-attached photos)
    # Note: Some routers already reference review_id
    review_id = Column(Integer, ForeignKey(
        "reviews.id"), nullable=True, index=True)
    url = Column(String, nullable=False)
    caption = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="photos")
    place = relationship("Place", back_populates="photos")


class Follow(Base):
    __tablename__ = "follows"

    id = Column(Integer, primary_key=True, index=True)
    follower_id = Column(Integer, ForeignKey(
        "users.id"), nullable=False, index=True)
    followee_id = Column(Integer, ForeignKey(
        "users.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DMThread(Base):
    __tablename__ = "dm_threads"

    id = Column(Integer, primary_key=True, index=True)
    user_a_id = Column(Integer, ForeignKey(
        "users.id"), nullable=False, index=True)
    user_b_id = Column(Integer, ForeignKey(
        "users.id"), nullable=False, index=True)
    initiator_id = Column(Integer, ForeignKey(
        "users.id"), nullable=False, index=True)
    # pending, accepted, rejected, blocked
    status = Column(String, nullable=False, default="pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True),
                        server_default=func.now(), onupdate=func.now())


class CheckInPhoto(Base):
    __tablename__ = "check_in_photos"

    id = Column(Integer, primary_key=True, index=True)
    check_in_id = Column(Integer, ForeignKey(
        "check_ins.id"), nullable=False, index=True)
    url = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    check_in = relationship("CheckIn", back_populates="photos")


class CheckInComment(Base):
    __tablename__ = "check_in_comments"

    id = Column(Integer, primary_key=True, index=True)
    check_in_id = Column(Integer, ForeignKey(
        "check_ins.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey(
        "users.id", ondelete="CASCADE"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True),
                        server_default=func.now(), onupdate=func.now())

    check_in = relationship("CheckIn", back_populates="comments")
    user = relationship("User", back_populates="check_in_comments")


class CheckInLike(Base):
    __tablename__ = "check_in_likes"

    id = Column(Integer, primary_key=True, index=True)
    check_in_id = Column(Integer, ForeignKey(
        "check_ins.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey(
        "users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    check_in = relationship("CheckIn", back_populates="likes")
    user = relationship("User", back_populates="check_in_likes")

    # Ensure a user can only like a check-in once
    __table_args__ = (UniqueConstraint(
        'check_in_id', 'user_id', name='uq_checkin_like'),)


class DMMessage(Base):
    __tablename__ = "dm_messages"

    id = Column(Integer, primary_key=True, index=True)
    thread_id = Column(Integer, ForeignKey(
        "dm_threads.id"), nullable=False, index=True)
    sender_id = Column(Integer, ForeignKey(
        "users.id"), nullable=False, index=True)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    sender = relationship("User", back_populates="dm_messages")


class DMMessageLike(Base):
    __tablename__ = "dm_message_likes"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey(
        "dm_messages.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"),
                     nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Unique constraint to prevent duplicate likes
    __table_args__ = (
        UniqueConstraint('message_id', 'user_id',
                         name='uq_dm_message_like_user'),
    )


class DMParticipantState(Base):
    __tablename__ = "dm_participant_states"

    id = Column(Integer, primary_key=True, index=True)
    thread_id = Column(Integer, ForeignKey(
        "dm_threads.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"),
                     nullable=False, index=True)
    last_read_at = Column(DateTime(timezone=True), nullable=True)
    muted = Column(Boolean, default=False)
    blocked = Column(Boolean, default=False)
    pinned = Column(Boolean, default=False)
    archived = Column(Boolean, default=False)
    typing_until = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True),
                        server_default=func.now(), onupdate=func.now())


class CheckInCollection(Base):
    __tablename__ = "check_in_collections"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"),
                     nullable=False, index=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True),
                        server_default=func.now(), onupdate=func.now())
    visibility = Column(String, nullable=False, server_default="public")

    items = relationship("CheckInCollectionItem",
                         back_populates="collection", cascade="all, delete-orphan")


class CheckInCollectionItem(Base):
    __tablename__ = "check_in_collection_items"

    id = Column(Integer, primary_key=True, index=True)
    collection_id = Column(Integer, ForeignKey(
        "check_in_collections.id"), nullable=False, index=True)
    check_in_id = Column(Integer, ForeignKey(
        "check_ins.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    collection = relationship("CheckInCollection", back_populates="items")


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey(
        "users.id", ondelete="CASCADE"), nullable=False, index=True)
    subject = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    # open, in_progress, resolved, closed
    status = Column(String, default="open")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True),
                        server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="support_tickets")


class Activity(Base):
    __tablename__ = "activities"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey(
        "users.id", ondelete="CASCADE"), nullable=False, index=True)
    # checkin, like, comment, follow, review, collection
    activity_type = Column(String, nullable=False, index=True)
    # JSON string with activity details
    activity_data = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True),
                        server_default=func.now(), index=True)

    user = relationship("User", back_populates="activities")


class UserInterest(Base):
    __tablename__ = "user_interests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"),
                     nullable=False, index=True)
    name = Column(String, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey(
        "users.id", ondelete="CASCADE"), nullable=False, index=True)
    # Toggles
    dm_messages = Column(Boolean, nullable=False, server_default='true')
    dm_requests = Column(Boolean, nullable=False, server_default='true')
    follows = Column(Boolean, nullable=False, server_default='true')
    likes = Column(Boolean, nullable=False, server_default='true')
    comments = Column(Boolean, nullable=False, server_default='true')
    activity_summary = Column(Boolean, nullable=False, server_default='true')
    marketing = Column(Boolean, nullable=False, server_default='false')
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True),
                        server_default=func.now(), onupdate=func.now())
