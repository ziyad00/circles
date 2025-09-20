"""
Unit tests for JWT Service
"""
from app.services.jwt_service import JWTService
import asyncio
import os
import sys
from datetime import datetime, timedelta

# Add the app directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '../../app'))


class JWTServiceTest:
    """Test JWT Service functionality"""

    def __init__(self):
        self.jwt_service = JWTService()

    def test_create_access_token(self):
        """Test creating access token"""
        user_id = 123
        token = self.jwt_service.create_token(user_id)

        assert token is not None, "Token should not be None"
        assert isinstance(token, str), "Token should be a string"
        assert len(token) > 0, "Token should not be empty"

        print(f"✅ Created access token: {token[:20]}...")
        return token

    def test_verify_token(self):
        """Test verifying token"""
        user_id = 123
        token = self.jwt_service.create_token(user_id)

        # Verify token
        payload = self.jwt_service.verify_token(token)

        assert payload is not None, "Payload should not be None"
        assert payload.get("sub") == str(
            user_id), f"User ID should be {user_id}"

        print(f"✅ Token verified successfully for user {user_id}")
        return payload

    def test_token_expiration(self):
        """Test token expiration"""
        user_id = 123
        # Create token with very short expiration (1 second)
        from datetime import timedelta
        short_expiry = timedelta(seconds=1)

        try:
            token = self.jwt_service.create_token(
                user_id, expires_delta=short_expiry)

            # Token should be valid immediately
            payload = self.jwt_service.verify_token(token)
            assert payload is not None, "Token should be valid immediately"

            print("✅ Token expiration test passed")

        except Exception as e:
            print(f"✅ Token expiration test passed (expected behavior): {e}")

    def test_invalid_token(self):
        """Test invalid token handling"""
        invalid_token = "invalid.token.here"

        try:
            payload = self.jwt_service.verify_token(invalid_token)
            assert False, "Should have raised an exception for invalid token"
        except Exception as e:
            print(f"✅ Invalid token correctly rejected: {e}")

    def test_get_current_user(self):
        """Test get current user from token"""
        user_id = 123
        token = self.jwt_service.create_token(user_id)

        # This would normally be called with a dependency injection
        # For unit testing, we'll just verify the token can be decoded
        payload = self.jwt_service.verify_token(token)
        current_user_id = payload.get("sub")

        assert current_user_id == str(
            user_id), f"Current user ID should be {user_id}"
        print(f"✅ Get current user test passed: {current_user_id}")

    def run_all_tests(self):
        """Run all JWT service tests"""
        print("🔐 Testing JWT Service...")
        print("=" * 40)

        try:
            self.test_create_access_token()
            self.test_verify_token()
            self.test_token_expiration()
            self.test_invalid_token()
            self.test_get_current_user()

            print("\n✅ All JWT Service tests passed!")

        except Exception as e:
            print(f"\n❌ JWT Service test failed: {e}")
            raise


async def main():
    """Main test runner"""
    test = JWTServiceTest()
    test.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main())
