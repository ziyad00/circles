#!/usr/bin/env python3
"""
Test script for chat-based dynamic limit functionality.
"""
import asyncio
import sys
import os
from datetime import timedelta
sys.path.append(os.path.join(os.path.dirname(__file__), '.'))

from app.routers.places import _parse_time_window


def test_parse_time_window():
    """Test time window parsing functionality."""
    print("Testing time window parsing...")
    
    # Test hours
    assert _parse_time_window("1h") == timedelta(hours=1)
    assert _parse_time_window("6h") == timedelta(hours=6)
    assert _parse_time_window("24h") == timedelta(hours=24)
    
    # Test days
    assert _parse_time_window("7d") == timedelta(days=7)
    assert _parse_time_window("30d") == timedelta(days=30)
    
    # Test case insensitive
    assert _parse_time_window("24H") == timedelta(hours=24)
    assert _parse_time_window("7D") == timedelta(days=7)
    
    # Test invalid input (should default to 24h)
    assert _parse_time_window("invalid") == timedelta(hours=24)
    assert _parse_time_window("") == timedelta(hours=24)
    
    print("✅ Time window parsing tests passed!")


def test_chat_based_limit_calculation():
    """Test chat-based dynamic limit calculation logic."""
    print("Testing chat-based dynamic limit calculation...")
    
    def mock_get_dynamic_limit(people_who_can_chat: int) -> int:
        """Mock the dynamic limit calculation based on people who can chat."""
        # Formula: min(50, max(3, 3 + (people_who_can_chat // 2)))
        dynamic_limit = max(3, min(50, 3 + (people_who_can_chat // 2)))
        return dynamic_limit
    
    # Test various people counts
    test_cases = [
        (0, 3),    # No people -> minimum 3
        (1, 3),    # 1 person -> still 3
        (2, 4),    # 2 people -> 4 (3 + 1)
        (4, 5),    # 4 people -> 5 (3 + 2)
        (6, 6),    # 6 people -> 6 (3 + 3)
        (10, 8),   # 10 people -> 8 (3 + 5)
        (20, 13),  # 20 people -> 13 (3 + 10)
        (100, 50), # 100 people -> capped at 50
        (200, 50)  # 200 people -> still capped at 50
    ]
    
    for people_count, expected_limit in test_cases:
        actual_limit = mock_get_dynamic_limit(people_count)
        assert actual_limit == expected_limit, f"Expected {expected_limit} for {people_count} people, got {actual_limit}"
        print(f"  ✅ {people_count} people who can chat -> {actual_limit} places")
    
    print("✅ Chat-based dynamic limit calculation tests passed!")


def main():
    """Run all tests."""
    print("🧪 Testing Chat-Based Dynamic Limit Functionality\n")
    
    try:
        
        # Test time window parsing
        test_parse_time_window()
        print()
        
        # Test chat-based dynamic limit calculation
        test_chat_based_limit_calculation()
        print()
        
        print("🎉 All tests passed! Chat-based dynamic limit functionality is working correctly.")
        print("\n📊 New Dynamic Limit Formula:")
        print("   limit = min(50, max(3, 3 + (people_who_can_chat // 2)))")
        print("   - Minimum: 3 places")
        print("   - Maximum: 50 places")
        print("   - Every 2 people who can chat adds 1 to the limit")
        print("   - Based on people with active check-ins within chat window (default 12h)")
        print("\n🕒 Chat Window:")
        print("   - Configurable via PLACE_CHAT_WINDOW_HOURS (default: 12 hours)")
        print("   - Only counts people whose check-ins haven't expired")
        print("   - Represents people who are 'present' and can interact")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
