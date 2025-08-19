import pytest
import asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.main import app
from app.database import get_db
from app.models import User, OTPCode
from app.services.otp_service import OTPService
from app.services.jwt_service import JWTService
from datetime import datetime, timedelta


@pytest.fixture
async def client(test_session):
    """Create test client with overridden database dependency."""
    async def override_get_db():
        yield test_session

    app.dependency_overrides = {get_db: override_get_db}

    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides = {}


@pytest.fixture
async def db_session(test_session):
    """Create database session for tests."""
    yield test_session
    # Clean up after each test
    await test_session.execute(delete(OTPCode))
    await test_session.execute(delete(User))
    await test_session.commit()


class TestOTPAuthentication:
    """Test OTP authentication flow."""

    async def test_request_otp_new_user(self, client, db_session):
        """Test requesting OTP for a new user."""
        response = await client.post(
            "/auth/request-otp",
            json={"email": "newuser@example.com"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "expires_in_minutes" in data
        assert data["expires_in_minutes"] == 10
        assert "newuser@example.com" in data["message"]

        # Verify user was created
        stmt = select(User).where(User.email == "newuser@example.com")
        result = await db_session.execute(stmt)
        user = result.scalar_one_or_none()
        assert user is not None
        assert user.email == "newuser@example.com"
        assert user.is_verified == False

    async def test_request_otp_existing_user(self, client, db_session):
        """Test requesting OTP for an existing user."""
        # Create user first
        user = await OTPService.create_user_if_not_exists(db_session, "existing@example.com")

        response = await client.post(
            "/auth/request-otp",
            json={"email": "existing@example.com"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "expires_in_minutes" in data

    async def test_request_otp_invalid_email(self, client):
        """Test requesting OTP with invalid email."""
        response = await client.post(
            "/auth/request-otp",
            json={"email": "invalid-email"}
        )

        assert response.status_code == 422  # Validation error

    async def test_request_otp_missing_email(self, client):
        """Test requesting OTP without email."""
        response = await client.post(
            "/auth/request-otp",
            json={}
        )

        assert response.status_code == 422  # Validation error

    async def test_verify_otp_success(self, client, db_session):
        """Test successful OTP verification."""
        # Create user and OTP
        user = await OTPService.create_user_if_not_exists(db_session, "verify@example.com")
        otp = await OTPService.create_otp(db_session, user.id)

        response = await client.post(
            "/auth/verify-otp",
            json={"email": "verify@example.com", "otp_code": otp.code}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "OTP verified successfully"
        assert "user" in data
        assert "access_token" in data
        assert data["user"]["email"] == "verify@example.com"
        assert data["user"]["is_verified"] == True

        # Verify user is now verified
        stmt = select(User).where(User.email == "verify@example.com")
        result = await db_session.execute(stmt)
        user = result.scalar_one_or_none()
        assert user.is_verified == True

    async def test_verify_otp_invalid_code(self, client, db_session):
        """Test OTP verification with invalid code."""
        # Create user and OTP
        user = await OTPService.create_user_if_not_exists(db_session, "invalid@example.com")
        await OTPService.create_otp(db_session, user.id)

        response = await client.post(
            "/auth/verify-otp",
            json={"email": "invalid@example.com", "otp_code": "000000"}
        )

        assert response.status_code == 400
        data = response.json()
        assert "Invalid or expired OTP code" in data["detail"]

    async def test_verify_otp_expired_code(self, client, db_session):
        """Test OTP verification with expired code."""
        # Create user and OTP with past expiration
        user = await OTPService.create_user_if_not_exists(db_session, "expired@example.com")
        otp = OTPCode(
            user_id=user.id,
            code="123456",
            is_used=False,
            expires_at=datetime.utcnow() - timedelta(minutes=1)
        )
        db_session.add(otp)
        await db_session.commit()

        response = await client.post(
            "/auth/verify-otp",
            json={"email": "expired@example.com", "otp_code": "123456"}
        )

        assert response.status_code == 400
        data = response.json()
        assert "Invalid or expired OTP code" in data["detail"]

    async def test_verify_otp_used_code(self, client, db_session):
        """Test OTP verification with already used code."""
        # Create user and OTP
        user = await OTPService.create_user_if_not_exists(db_session, "used@example.com")
        otp = OTPCode(
            user_id=user.id,
            code="123456",
            is_used=True,
            expires_at=datetime.utcnow() + timedelta(minutes=10)
        )
        db_session.add(otp)
        await db_session.commit()

        response = await client.post(
            "/auth/verify-otp",
            json={"email": "used@example.com", "otp_code": "123456"}
        )

        assert response.status_code == 400
        data = response.json()
        assert "Invalid or expired OTP code" in data["detail"]

    async def test_verify_otp_nonexistent_user(self, client):
        """Test OTP verification for non-existent user."""
        response = await client.post(
            "/auth/verify-otp",
            json={"email": "nonexistent@example.com", "otp_code": "123456"}
        )

        assert response.status_code == 400
        data = response.json()
        assert "Invalid or expired OTP code" in data["detail"]

    async def test_verify_otp_missing_fields(self, client):
        """Test OTP verification with missing fields."""
        response = await client.post(
            "/auth/verify-otp",
            json={"email": "test@example.com"}
        )

        assert response.status_code == 422  # Validation error

    async def test_verify_otp_invalid_email_format(self, client):
        """Test OTP verification with invalid email format."""
        response = await client.post(
            "/auth/verify-otp",
            json={"email": "invalid-email", "otp_code": "123456"}
        )

        assert response.status_code == 422  # Validation error


class TestJWTAuthentication:
    """Test JWT token authentication."""

    async def test_jwt_token_creation(self, db_session):
        """Test JWT token creation."""
        user = await OTPService.create_user_if_not_exists(db_session, "jwt@example.com")
        token = JWTService.create_access_token(
            data={"sub": str(user.id), "email": user.email}
        )

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    async def test_jwt_token_verification(self, db_session):
        """Test JWT token verification."""
        user = await OTPService.create_user_if_not_exists(db_session, "verify@example.com")
        token = JWTService.create_access_token(
            data={"sub": str(user.id), "email": user.email}
        )

        payload = JWTService.verify_token(token)
        assert payload["sub"] == str(user.id)
        assert payload["email"] == user.email
        assert "exp" in payload

    async def test_jwt_token_invalid_signature(self):
        """Test JWT token with invalid signature."""
        invalid_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwiZW1haWwiOiJ0ZXN0QGV4YW1wbGUuY29tIiwiZXhwIjoxNzU1NTM3NDcwfQ.invalid_signature"

        with pytest.raises(Exception):
            JWTService.verify_token(invalid_token)

    async def test_jwt_token_expired(self):
        """Test JWT token that has expired."""
        # Create a token with past expiration
        expired_token = JWTService.create_access_token(
            data={"sub": "1", "email": "test@example.com"},
            expires_delta=timedelta(minutes=-10)
        )

        with pytest.raises(Exception):
            JWTService.verify_token(expired_token)

    async def test_get_current_user_success(self, client, db_session):
        """Test successful user retrieval with JWT token."""
        # Create user and get token
        user = await OTPService.create_user_if_not_exists(db_session, "current@example.com")
        user.is_verified = True
        await db_session.commit()

        token = JWTService.create_access_token(
            data={"sub": str(user.id), "email": user.email}
        )

        response = await client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "current@example.com"
        assert data["id"] == user.id
        assert data["is_verified"] == True

    async def test_get_current_user_invalid_token(self, client):
        """Test user retrieval with invalid JWT token."""
        response = await client.get(
            "/auth/me",
            headers={"Authorization": "Bearer invalid_token"}
        )

        assert response.status_code == 401

    async def test_get_current_user_missing_token(self, client):
        """Test user retrieval without JWT token."""
        response = await client.get("/auth/me")

        assert response.status_code == 403

    async def test_get_current_user_unverified_user(self, client, db_session):
        """Test user retrieval for unverified user."""
        # Create unverified user
        user = await OTPService.create_user_if_not_exists(db_session, "unverified@example.com")
        user.is_verified = False
        await db_session.commit()

        token = JWTService.create_access_token(
            data={"sub": str(user.id), "email": user.email}
        )

        response = await client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 401

    async def test_get_current_user_nonexistent_user(self, client):
        """Test user retrieval for non-existent user."""
        token = JWTService.create_access_token(
            data={"sub": "999", "email": "nonexistent@example.com"}
        )

        response = await client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 401


class TestOTPService:
    """Test OTP service methods."""

    async def test_create_user_if_not_exists_new(self, db_session):
        """Test creating a new user."""
        user = await OTPService.create_user_if_not_exists(db_session, "new@example.com")

        assert user.email == "new@example.com"
        assert user.is_verified == False
        assert user.id is not None

    async def test_create_user_if_not_exists_existing(self, db_session):
        """Test creating user when already exists."""
        # Create user first
        user1 = await OTPService.create_user_if_not_exists(db_session, "existing@example.com")

        # Try to create again
        user2 = await OTPService.create_user_if_not_exists(db_session, "existing@example.com")

        assert user1.id == user2.id
        assert user1.email == user2.email

    async def test_create_otp(self, db_session):
        """Test OTP creation."""
        user = await OTPService.create_user_if_not_exists(db_session, "otp@example.com")
        otp = await OTPService.create_otp(db_session, user.id)

        assert otp.user_id == user.id
        assert len(otp.code) == 6
        assert otp.is_used == False
        assert otp.expires_at > datetime.utcnow()

    async def test_create_otp_invalidates_old_otps(self, db_session):
        """Test that creating new OTP invalidates old ones."""
        user = await OTPService.create_user_if_not_exists(db_session, "invalidate@example.com")

        # Create first OTP
        otp1 = await OTPService.create_otp(db_session, user.id)

        # Create second OTP
        otp2 = await OTPService.create_otp(db_session, user.id)

        # First OTP should be invalidated
        stmt = select(OTPCode).where(OTPCode.id == otp1.id)
        result = await db_session.execute(stmt)
        old_otp = result.scalar_one_or_none()
        assert old_otp.is_used == True

    async def test_verify_otp_success(self, db_session):
        """Test successful OTP verification."""
        user = await OTPService.create_user_if_not_exists(db_session, "verify@example.com")
        otp = await OTPService.create_otp(db_session, user.id)

        is_valid, verified_user = await OTPService.verify_otp(db_session, user.email, otp.code)

        assert is_valid == True
        assert verified_user.id == user.id
        assert verified_user.is_verified == True

    async def test_verify_otp_invalid_code(self, db_session):
        """Test OTP verification with invalid code."""
        user = await OTPService.create_user_if_not_exists(db_session, "invalid@example.com")
        await OTPService.create_otp(db_session, user.id)

        is_valid, verified_user = await OTPService.verify_otp(db_session, user.email, "000000")

        assert is_valid == False
        assert verified_user is None

    async def test_verify_otp_nonexistent_user(self, db_session):
        """Test OTP verification for non-existent user."""
        is_valid, verified_user = await OTPService.verify_otp(db_session, "nonexistent@example.com", "123456")

        assert is_valid == False
        assert verified_user is None


class TestIntegration:
    """Integration tests for complete authentication flow."""

    async def test_complete_auth_flow(self, client, db_session):
        """Test complete authentication flow from OTP request to protected endpoint."""
        # Step 1: Request OTP
        response = await client.post(
            "/auth/request-otp",
            json={"email": "integration@example.com"}
        )
        assert response.status_code == 200

        # Get OTP code from response (for testing)
        data = response.json()
        otp_code = data["message"].split(": ")[-1]

        # Step 2: Verify OTP and get JWT token
        response = await client.post(
            "/auth/verify-otp",
            json={"email": "integration@example.com", "otp_code": otp_code}
        )
        assert response.status_code == 200

        data = response.json()
        token = data["access_token"]
        assert token is not None

        # Step 3: Access protected endpoint
        response = await client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200

        user_data = response.json()
        assert user_data["email"] == "integration@example.com"
        assert user_data["is_verified"] == True

    async def test_multiple_users_same_otp(self, client, db_session):
        """Test that OTP codes are unique per user."""
        # Request OTP for first user
        response1 = await client.post(
            "/auth/request-otp",
            json={"email": "user1@example.com"}
        )
        assert response1.status_code == 200

        # Request OTP for second user
        response2 = await client.post(
            "/auth/request-otp",
            json={"email": "user2@example.com"}
        )
        assert response2.status_code == 200

        # Get OTP codes
        data1 = response1.json()
        data2 = response2.json()
        otp1 = data1["message"].split(": ")[-1]
        otp2 = data2["message"].split(": ")[-1]

        # OTP codes should be different
        assert otp1 != otp2

        # Each OTP should only work for its respective user
        response = await client.post(
            "/auth/verify-otp",
            json={"email": "user1@example.com", "otp_code": otp2}
        )
        assert response.status_code == 400

    async def test_concurrent_otp_requests(self, client, db_session):
        """Test concurrent OTP requests for the same user."""
        # Make multiple concurrent requests
        tasks = []
        for i in range(3):
            task = client.post(
                "/auth/request-otp",
                json={"email": "concurrent@example.com"}
            )
            tasks.append(task)

        responses = await asyncio.gather(*tasks)

        # All requests should succeed
        for response in responses:
            assert response.status_code == 200

        # Only one user should be created
        stmt = select(User).where(User.email == "concurrent@example.com")
        result = await db_session.execute(stmt)
        users = result.scalars().all()
        assert len(users) == 1

    async def test_token_reuse_attempt(self, client, db_session):
        """Test that using the same OTP code twice fails."""
        # Request and verify OTP
        response = await client.post(
            "/auth/request-otp",
            json={"email": "reuse@example.com"}
        )
        assert response.status_code == 200

        data = response.json()
        otp_code = data["message"].split(": ")[-1]

        # First verification should succeed
        response = await client.post(
            "/auth/verify-otp",
            json={"email": "reuse@example.com", "otp_code": otp_code}
        )
        assert response.status_code == 200

        # Second verification with same code should fail
        response = await client.post(
            "/auth/verify-otp",
            json={"email": "reuse@example.com", "otp_code": otp_code}
        )
        assert response.status_code == 400


class TestErrorHandling:
    """Test error handling and edge cases."""

    async def test_database_connection_error(self, client, monkeypatch):
        """Test handling of database connection errors."""
        # Mock database dependency to raise an exception
        async def mock_get_db():
            raise Exception("Database connection failed")

        monkeypatch.setattr("app.database.get_db", mock_get_db)

        response = await client.post(
            "/auth/request-otp",
            json={"email": "error@example.com"}
        )

        assert response.status_code == 500

    async def test_invalid_jwt_payload(self, client):
        """Test JWT token with invalid payload."""
        # Create token with invalid user ID
        token = JWTService.create_access_token(
            data={"sub": "invalid_id", "email": "test@example.com"}
        )

        response = await client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 401

    async def test_malformed_json_request(self, client):
        """Test handling of malformed JSON requests."""
        response = await client.post(
            "/auth/request-otp",
            content="invalid json",
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 422

    async def test_large_email_input(self, client):
        """Test handling of very large email input."""
        large_email = "a" * 1000 + "@example.com"
        response = await client.post(
            "/auth/request-otp",
            json={"email": large_email}
        )

        assert response.status_code == 422  # Should be rejected by validation

    async def test_special_characters_in_email(self, client):
        """Test handling of special characters in email."""
        response = await client.post(
            "/auth/request-otp",
            json={"email": "test+tag@example.com"}
        )

        assert response.status_code == 200  # Should be accepted

    async def test_empty_otp_code(self, client, db_session):
        """Test handling of empty OTP code."""
        user = await OTPService.create_user_if_not_exists(db_session, "empty@example.com")
        await OTPService.create_otp(db_session, user.id)

        response = await client.post(
            "/auth/verify-otp",
            json={"email": "empty@example.com", "otp_code": ""}
        )

        assert response.status_code == 400
