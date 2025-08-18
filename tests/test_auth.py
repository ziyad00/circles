import pytest
from httpx import AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_request_otp():
    """Test requesting an OTP code"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post(
            "/auth/request-otp",
            json={"email": "test@example.com"}
        )

    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "expires_in_minutes" in data
    assert data["expires_in_minutes"] == 10
    assert "test@example.com" in data["message"]


@pytest.mark.asyncio
async def test_verify_otp_invalid():
    """Test verifying an invalid OTP code"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post(
            "/auth/verify-otp",
            json={"email": "test@example.com", "otp_code": "000000"}
        )

    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "Invalid or expired OTP code" in data["detail"]


@pytest.mark.asyncio
async def test_request_and_verify_otp():
    """Test the complete flow: request OTP and verify it"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Request OTP
        response = await ac.post(
            "/auth/request-otp",
            json={"email": "flow@example.com"}
        )

        assert response.status_code == 200
        data = response.json()

        # Extract OTP code from message (for development)
        otp_code = data["message"].split(": ")[-1]

        # Verify OTP
        response = await ac.post(
            "/auth/verify-otp",
            json={"email": "flow@example.com", "otp_code": otp_code}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "OTP verified successfully"
        assert data["user"]["email"] == "flow@example.com"
        assert data["user"]["is_verified"] == True
