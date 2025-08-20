from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text, Float
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    phone = Column(String, unique=True, index=True, nullable=True)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    otp_codes = relationship("OTPCode", back_populates="user")
    check_ins = relationship("CheckIn", back_populates="user")
    saved_places = relationship("SavedPlace", back_populates="user")
    reviews = relationship("Review", back_populates="user")
    photos = relationship("Photo", back_populates="user")
    dm_messages = relationship("DMMessage", back_populates="sender")

    # Friend relationships
    sent_friend_requests = relationship(
        "Friendship",
        foreign_keys="Friendship.requester_id",
        back_populates="requester"
    )
    received_friend_requests = relationship(
        "Friendship",
        foreign_keys="Friendship.addressee_id",
        back_populates="addressee"
    )


class OTPCode(Base):
    __tablename__ = "otp_codes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
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
    created_at = Column(DateTime(timezone=True), server_default=func.now())

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
    url = Column(String, nullable=False)
    caption = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="photos")
    place = relationship("Place", back_populates="photos")


class Friendship(Base):
    __tablename__ = "friendships"

    id = Column(Integer, primary_key=True, index=True)
    requester_id = Column(Integer, ForeignKey(
        "users.id"), nullable=False, index=True)
    addressee_id = Column(Integer, ForeignKey(
        "users.id"), nullable=False, index=True)
    # pending, accepted, rejected
    status = Column(String, nullable=False, default="pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True),
                        server_default=func.now(), onupdate=func.now())

    # Relationships
    requester = relationship("User", foreign_keys=[
                             requester_id], back_populates="sent_friend_requests")
    addressee = relationship("User", foreign_keys=[
                             addressee_id], back_populates="received_friend_requests")


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
    typing_until = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True),
                        server_default=func.now(), onupdate=func.now())
