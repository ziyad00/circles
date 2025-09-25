"""Unit tests for utility functions."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from app.utils import can_view_checkin, can_view_profile


@pytest.mark.asyncio
async def test_can_view_checkin_public():
    """Test that public check-ins are viewable by anyone."""
    db = AsyncMock()

    result = await can_view_checkin(db, checkin_user_id=1, viewer_user_id=2, visibility="public")

    assert result is True


@pytest.mark.asyncio
async def test_can_view_checkin_private():
    """Test that private check-ins are only viewable by the owner."""
    db = AsyncMock()

    # Same user viewing their own check-in
    result = await can_view_checkin(db, checkin_user_id=1, viewer_user_id=1, visibility="private")
    assert result is True

    # Different user viewing private check-in
    result = await can_view_checkin(db, checkin_user_id=1, viewer_user_id=2, visibility="private")
    assert result is False


@pytest.mark.asyncio
async def test_can_view_checkin_followers():
    """Test that followers-only check-ins work correctly."""
    db = AsyncMock()

    # Mock the follow relationship query
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = True  # User 2 follows user 1
    db.execute.return_value = mock_result

    result = await can_view_checkin(db, checkin_user_id=1, viewer_user_id=2, visibility="followers")
    assert result is True

    # Test when user doesn't follow
    mock_result.scalar_one_or_none.return_value = None
    result = await can_view_checkin(db, checkin_user_id=1, viewer_user_id=3, visibility="followers")
    assert result is False


@pytest.mark.asyncio
async def test_can_view_profile_public():
    """Test that public profiles are viewable by anyone."""
    db = AsyncMock()
    user = MagicMock()
    user.profile_visibility = "public"

    result = await can_view_profile(db, user, viewer_user_id=2)
    assert result is True


@pytest.mark.asyncio
async def test_can_view_profile_private():
    """Test that private profiles are only viewable by the owner."""
    db = AsyncMock()
    user = MagicMock()
    user.id = 1
    user.profile_visibility = "private"

    # Same user viewing their own profile
    result = await can_view_profile(db, user, viewer_user_id=1)
    assert result is True

    # Different user viewing private profile
    result = await can_view_profile(db, user, viewer_user_id=2)
    assert result is False
