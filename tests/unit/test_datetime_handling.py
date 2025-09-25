"""Unit tests for datetime handling to prevent timezone issues."""

import pytest
from datetime import datetime, timezone, timedelta
from app.utils import can_view_checkin, can_view_profile


class TestDateTimeHandling:
    """Test datetime handling utilities."""

    def test_timezone_aware_datetime_comparison(self):
        """Test that timezone-aware datetime comparison works correctly."""
        # Create timezone-aware datetimes
        now_utc = datetime.now(timezone.utc)
        past_utc = now_utc - timedelta(hours=2)
        future_utc = now_utc + timedelta(hours=2)

        # Test comparisons
        assert (now_utc - past_utc) == timedelta(hours=2)
        assert (future_utc - now_utc) == timedelta(hours=2)
        assert (now_utc - past_utc) < timedelta(hours=3)
        assert (now_utc - past_utc) > timedelta(hours=1)

    def test_timezone_naive_to_aware_conversion(self):
        """Test conversion from timezone-naive to timezone-aware datetime."""
        # Create timezone-naive datetime
        naive_dt = datetime(2025, 1, 25, 12, 0, 0)

        # Convert to timezone-aware
        aware_dt = naive_dt.replace(tzinfo=timezone.utc)

        # Test that it's now timezone-aware
        assert aware_dt.tzinfo is not None
        assert aware_dt.tzinfo == timezone.utc

        # Test that we can compare with other timezone-aware datetimes
        now_utc = datetime.now(timezone.utc)
        assert isinstance(now_utc - aware_dt, timedelta)

    def test_timezone_aware_datetime_creation(self):
        """Test creating timezone-aware datetimes."""
        # Test different ways to create timezone-aware datetimes
        dt1 = datetime.now(timezone.utc)
        dt2 = datetime(2025, 1, 25, 12, 0, 0, tzinfo=timezone.utc)
        dt3 = datetime(2025, 1, 25, 12, 0, 0).replace(tzinfo=timezone.utc)

        # All should be timezone-aware
        assert dt1.tzinfo is not None
        assert dt2.tzinfo is not None
        assert dt3.tzinfo is not None

        # All should be UTC
        assert dt1.tzinfo == timezone.utc
        assert dt2.tzinfo == timezone.utc
        assert dt3.tzinfo == timezone.utc

    def test_datetime_isoformat_parsing(self):
        """Test parsing datetime from ISO format strings."""
        # Test with timezone-aware datetime
        dt_aware = datetime.now(timezone.utc)
        iso_string = dt_aware.isoformat()

        # Parse back
        parsed_dt = datetime.fromisoformat(iso_string)
        assert parsed_dt == dt_aware

        # Test with Z suffix (common in APIs)
        iso_string_z = dt_aware.isoformat().replace('+00:00', 'Z')
        parsed_dt_z = datetime.fromisoformat(
            iso_string_z.replace('Z', '+00:00'))
        assert parsed_dt_z == dt_aware

    def test_datetime_arithmetic_with_timezones(self):
        """Test datetime arithmetic with timezone-aware datetimes."""
        base_time = datetime.now(timezone.utc)

        # Test adding/subtracting timedeltas
        future_time = base_time + timedelta(hours=6)
        past_time = base_time - timedelta(hours=6)

        # Test comparisons
        assert future_time > base_time
        assert past_time < base_time
        assert (future_time - base_time) == timedelta(hours=6)
        assert (base_time - past_time) == timedelta(hours=6)

        # Test time window calculations (like allowed_to_chat)
        time_limit = timedelta(hours=6)
        # Should be True (6 hours >= 6 hours)
        assert (future_time - base_time) >= time_limit
        # Should be True (6 hours >= 6 hours)
        assert (base_time - past_time) >= time_limit
        # Should be True (0 < 6 hours)
        assert (base_time - base_time) < time_limit

    def test_datetime_handling_edge_cases(self):
        """Test datetime handling edge cases."""
        # Test with None values
        dt1 = datetime.now(timezone.utc)
        dt2 = None

        # Should handle None gracefully
        if dt2 is not None:
            diff = dt1 - dt2
        else:
            diff = None

        assert diff is None

        # Test with very old datetime
        old_dt = datetime(1970, 1, 1, tzinfo=timezone.utc)
        now_dt = datetime.now(timezone.utc)

        # Should handle large time differences
        diff = now_dt - old_dt
        assert isinstance(diff, timedelta)
        assert diff.total_seconds() > 0

        # Test with future datetime
        future_dt = datetime(2030, 1, 1, tzinfo=timezone.utc)
        diff = future_dt - now_dt
        assert isinstance(diff, timedelta)
        assert diff.total_seconds() > 0


class TestCheckInTimeWindow:
    """Test check-in time window calculations."""

    def test_allowed_to_chat_calculation(self):
        """Test allowed_to_chat calculation logic."""
        now = datetime.now(timezone.utc)
        time_limit = timedelta(hours=6)

        # Test cases
        test_cases = [
            # (checkin_time, expected_allowed_to_chat)
            # 1 hour ago - should be allowed
            (now - timedelta(hours=1), True),
            # 3 hours ago - should be allowed
            (now - timedelta(hours=3), True),
            # Exactly 6 hours ago - should not be allowed
            (now - timedelta(hours=6), False),
            # 7 hours ago - should not be allowed
            (now - timedelta(hours=7), False),
            # 30 minutes ago - should be allowed
            (now - timedelta(minutes=30), True),
        ]

        for checkin_time, expected in test_cases:
            # Ensure checkin_time is timezone-aware
            if checkin_time.tzinfo is None:
                checkin_time = checkin_time.replace(tzinfo=timezone.utc)

            # Calculate allowed_to_chat
            allowed_to_chat = (now - checkin_time) < time_limit

            assert allowed_to_chat == expected, f"Failed for checkin_time: {checkin_time}"

    def test_timezone_naive_checkin_handling(self):
        """Test handling of timezone-naive checkin times."""
        now = datetime.now(timezone.utc)
        time_limit = timedelta(hours=6)

        # Create timezone-naive checkin time
        naive_checkin_time = datetime(2025, 1, 25, 12, 0, 0)

        # Convert to timezone-aware
        if naive_checkin_time.tzinfo is None:
            checkin_time = naive_checkin_time.replace(tzinfo=timezone.utc)
        else:
            checkin_time = naive_checkin_time

        # Should be able to calculate difference
        diff = now - checkin_time
        assert isinstance(diff, timedelta)

        # Should be able to compare with time limit
        allowed_to_chat = diff < time_limit
        assert isinstance(allowed_to_chat, bool)


class TestDateTimeValidation:
    """Test datetime validation in schemas."""

    def test_datetime_field_validation(self):
        """Test that datetime fields are properly validated."""
        from app.schemas import PublicUserResponse

        # Test with valid datetime
        valid_data = {
            "id": 1,
            "name": "Test User",
            "username": "testuser",
            "availability_status": "available",
            "availability_mode": "auto",
            "created_at": datetime.now(timezone.utc),
            "followers_count": 10,
            "following_count": 5,
            "check_ins_count": 25,
            "is_followed": False,
            "is_blocked": False
        }

        user_response = PublicUserResponse(**valid_data)
        assert isinstance(user_response.created_at, datetime)

        # Test with invalid datetime (string)
        invalid_data = valid_data.copy()
        invalid_data["created_at"] = "invalid_datetime"

        with pytest.raises(ValueError):
            PublicUserResponse(**invalid_data)

    def test_datetime_serialization(self):
        """Test datetime serialization for API responses."""
        from app.schemas import PublicUserResponse

        valid_data = {
            "id": 1,
            "name": "Test User",
            "username": "testuser",
            "availability_status": "available",
            "availability_mode": "auto",
            "created_at": datetime.now(timezone.utc),
            "followers_count": 10,
            "following_count": 5,
            "check_ins_count": 25,
            "is_followed": False,
            "is_blocked": False
        }

        user_response = PublicUserResponse(**valid_data)

        # Test serialization to dict
        response_dict = user_response.model_dump()
        assert "created_at" in response_dict
        assert isinstance(response_dict["created_at"], datetime)

        # Test serialization to JSON
        response_json = user_response.model_dump_json()
        assert "created_at" in response_json
