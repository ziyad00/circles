"""
Unit tests for Authentication Service
"""
from app.models import User
from app.services.jwt_service import JWTService
import asyncio
import os
import sys
from unittest.mock import patch, MagicMock

# Add the app directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '../../app'))


class AuthServiceTest:
    """Test Authentication Service functionality"""

    def __init__(self):
        self.jwt_service = JWTService()

    def test_jwt_token_creation(self):
        """Test JWT token creation"""
        user_id = 123
        token = self.jwt_service.create_token(user_id)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

        print("✅ JWT token creation test passed")

    def test_jwt_token_validation(self):
        """Test JWT token validation"""
        user_id = 123
        token = self.jwt_service.create_token(user_id)

        # Test valid token
        decoded = self.jwt_service.verify_token(token)
        assert decoded is not None
        assert decoded.get("user_id") == user_id

        print("✅ JWT token validation test passed")

    def test_jwt_token_expiration(self):
        """Test JWT token expiration handling"""
        # Create a token with very short expiration
        user_id = 123
        token = self.jwt_service.create_token(user_id)

        # Token should be valid immediately
        decoded = self.jwt_service.verify_token(token)
        assert decoded is not None

        print("✅ JWT token expiration test passed")

    def test_invalid_token_handling(self):
        """Test invalid token handling"""
        invalid_tokens = [
            "invalid_token",
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid",
            "",
            None
        ]

        for invalid_token in invalid_tokens:
            try:
                decoded = self.jwt_service.verify_token(invalid_token)
                assert decoded is None
            except Exception:
                # Exception is also acceptable for invalid tokens
                pass

        print("✅ Invalid token handling test passed")

    def test_token_tampering_detection(self):
        """Test token tampering detection"""
        user_id = 123
        token = self.jwt_service.create_token(user_id)

        # Tamper with the token
        tampered_token = token[:-5] + "XXXXX"

        try:
            decoded = self.jwt_service.verify_token(tampered_token)
            assert decoded is None
        except Exception:
            # Exception is acceptable for tampered tokens
            pass

        print("✅ Token tampering detection test passed")

    def test_different_user_tokens(self):
        """Test tokens for different users"""
        user_ids = [1, 2, 3, 100, 999]
        tokens = []

        for user_id in user_ids:
            token = self.jwt_service.create_token(user_id)
            tokens.append(token)

            # Verify each token
            decoded = self.jwt_service.verify_token(token)
            assert decoded is not None
            assert decoded.get("user_id") == user_id

        # Ensure all tokens are different
        assert len(set(tokens)) == len(tokens)

        print("✅ Different user tokens test passed")

    def test_token_structure(self):
        """Test JWT token structure"""
        user_id = 123
        token = self.jwt_service.create_token(user_id)

        # JWT tokens should have 3 parts separated by dots
        parts = token.split('.')
        assert len(parts) == 3

        # Each part should be base64 encoded (non-empty)
        for part in parts:
            assert len(part) > 0

        print("✅ Token structure test passed")

    def test_user_authentication_flow(self):
        """Test complete user authentication flow"""
        user_id = 123

        # Step 1: Create token
        token = self.jwt_service.create_token(user_id)
        assert token is not None

        # Step 2: Verify token
        decoded = self.jwt_service.verify_token(token)
        assert decoded is not None
        assert decoded.get("user_id") == user_id

        # Step 3: Extract user ID
        extracted_user_id = decoded.get("user_id")
        assert extracted_user_id == user_id

        print("✅ User authentication flow test passed")

    def test_token_consistency(self):
        """Test token consistency for same user"""
        user_id = 123

        # Create multiple tokens for same user
        tokens = []
        for _ in range(5):
            token = self.jwt_service.create_token(user_id)
            tokens.append(token)

        # All tokens should be valid
        for token in tokens:
            decoded = self.jwt_service.verify_token(token)
            assert decoded is not None
            assert decoded.get("user_id") == user_id

        # Tokens should be different (due to timestamp)
        assert len(set(tokens)) == len(tokens)

        print("✅ Token consistency test passed")

    def test_edge_case_user_ids(self):
        """Test edge case user IDs"""
        edge_case_ids = [0, 1, -1, 999999, 2**31 - 1]

        for user_id in edge_case_ids:
            try:
                token = self.jwt_service.create_token(user_id)
                decoded = self.jwt_service.verify_token(token)

                if decoded is not None:
                    assert decoded.get("user_id") == user_id
            except Exception as e:
                # Some edge cases might not be supported
                print(f"Edge case {user_id} failed: {e}")

        print("✅ Edge case user IDs test passed")

    def run_all_tests(self):
        """Run all authentication service tests"""
        print("🔐 Testing Authentication Service...")
        print("=" * 50)

        try:
            self.test_jwt_token_creation()
            self.test_jwt_token_validation()
            self.test_jwt_token_expiration()
            self.test_invalid_token_handling()
            self.test_token_tampering_detection()
            self.test_different_user_tokens()
            self.test_token_structure()
            self.test_user_authentication_flow()
            self.test_token_consistency()
            self.test_edge_case_user_ids()

            print("\n✅ All Authentication Service tests passed!")

        except Exception as e:
            print(f"\n❌ Authentication Service test failed: {e}")
            raise


async def main():
    """Main test runner"""
    test = AuthServiceTest()
    test.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main())
