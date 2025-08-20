import pytest
from datetime import datetime, timezone, timedelta
from app.routers.dms import _check_rate_limit


def test_rate_limit_function():
    """Test the rate limiting function directly"""
    # Test data structure
    log_dict = {}
    user_id = 1
    limit = 3

    # First 3 requests should succeed
    for i in range(3):
        result = _check_rate_limit(user_id, log_dict, limit)
        assert result is True, f"Request {i} should succeed"
        assert len(log_dict[user_id]) == i + 1

    # 4th request should fail
    result = _check_rate_limit(user_id, log_dict, limit)
    assert result is False, "4th request should be rate limited"
    assert len(log_dict[user_id]) == 3  # Should still be 3


def test_rate_limit_window():
    """Test that rate limiting respects the time window"""
    log_dict = {}
    user_id = 1
    limit = 2

    # Add old timestamps (outside 1-minute window)
    old_time = datetime.now(timezone.utc) - timedelta(minutes=2)
    log_dict[user_id] = [old_time, old_time, old_time]

    # Should be able to make 2 new requests
    for i in range(2):
        result = _check_rate_limit(user_id, log_dict, limit)
        assert result is True, f"Request {i} should succeed after window reset"

    # 3rd request should fail
    result = _check_rate_limit(user_id, log_dict, limit)
    assert result is False, "3rd request should be rate limited"


def test_rate_limit_per_user():
    """Test that rate limiting is per-user"""
    log_dict = {}
    user1_id = 1
    user2_id = 2
    limit = 2

    # User 1 makes 2 requests
    for i in range(2):
        result = _check_rate_limit(user1_id, log_dict, limit)
        assert result is True, f"User 1 request {i} should succeed"

    # User 1's 3rd request should fail
    result = _check_rate_limit(user1_id, log_dict, limit)
    assert result is False, "User 1's 3rd request should be rate limited"

    # User 2 should still be able to make requests
    for i in range(2):
        result = _check_rate_limit(user2_id, log_dict, limit)
        assert result is True, f"User 2 request {i} should succeed"


def test_rate_limit_cleanup():
    """Test that old entries are cleaned up"""
    log_dict = {}
    user_id = 1
    limit = 2

    # Add mixed old and new timestamps
    now = datetime.now(timezone.utc)
    old_time = now - timedelta(minutes=2)
    recent_time = now - timedelta(seconds=30)

    log_dict[user_id] = [old_time, recent_time, old_time]

    # Should clean up old entries and allow 1 more request
    result = _check_rate_limit(user_id, log_dict, limit)
    assert result is True, "Should allow request after cleanup"

    # Should have 2 entries (recent + new)
    assert len(log_dict[user_id]) == 2
