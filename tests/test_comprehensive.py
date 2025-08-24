import pytest
import asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.main import app
from app.database import AsyncSessionLocal
from app.models import User, Place, CheckIn, DMMessage, DMParticipantState, CheckInCollection, Activity, SupportTicket
from app.services.jwt_service import JWTService
import json


@pytest.fixture
async def client():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def db_session():
    async with AsyncSessionLocal() as session:
        yield session


@pytest.fixture
async def test_user(db_session):
    """Create a test user and return their data"""
    user = User(
        email="test@example.com",
        display_name="Test User",
        username="testuser",
        bio="Test bio"
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    # Create JWT token
    token = JWTService.create_token(user.id)

    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "username": user.username,
        "token": token
    }


@pytest.fixture
async def test_user2(db_session):
    """Create a second test user"""
    user = User(
        email="test2@example.com",
        display_name="Test User 2",
        username="testuser2",
        bio="Test bio 2"
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    token = JWTService.create_token(user.id)

    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "username": user.username,
        "token": token
    }


@pytest.fixture
async def test_place(db_session):
    """Create a test place"""
    place = Place(
        name="Test Restaurant",
        address="123 Test St",
        latitude=40.7128,
        longitude=-74.0060,
        category="restaurant"
    )
    db_session.add(place)
    await db_session.commit()
    await db_session.refresh(place)
    return place


class TestAuthentication:
    """Test authentication endpoints"""

    async def test_request_otp(self, client):
        """Test OTP request"""
        response = await client.post("/auth/request-otp", json={
            "email": "newuser@example.com"
        })
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "newuser@example.com" in data["message"]

    async def test_verify_otp(self, client):
        """Test OTP verification"""
        # First request OTP
        await client.post("/auth/request-otp", json={
            "email": "verify@example.com"
        })

        # Then verify with test OTP (123456 in dev mode)
        response = await client.post("/auth/verify-otp", json={
            "email": "verify@example.com",
            "otp": "123456"
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"


class TestUsers:
    """Test user-related endpoints"""

    async def test_get_me(self, client, test_user):
        """Test getting current user profile"""
        headers = {"Authorization": f"Bearer {test_user['token']}"}
        response = await client.get("/users/me", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == test_user["email"]
        assert data["display_name"] == test_user["display_name"]

    async def test_update_me(self, client, test_user):
        """Test updating user profile"""
        headers = {"Authorization": f"Bearer {test_user['token']}"}
        update_data = {
            "display_name": "Updated Name",
            "bio": "Updated bio"
        }
        response = await client.put("/users/me", json=update_data, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["display_name"] == "Updated Name"
        assert data["bio"] == "Updated bio"

    async def test_get_user_profile(self, client, test_user, test_user2):
        """Test getting public user profile"""
        headers = {"Authorization": f"Bearer {test_user['token']}"}
        response = await client.get(f"/users/{test_user2['id']}", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == test_user2["username"]
        assert data["display_name"] == test_user2["display_name"]

    async def test_follow_user(self, client, test_user, test_user2):
        """Test following a user"""
        headers = {"Authorization": f"Bearer {test_user['token']}"}
        response = await client.post(f"/users/follow/{test_user2['id']}", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    async def test_get_following(self, client, test_user, test_user2):
        """Test getting following list"""
        # First follow the user
        headers = {"Authorization": f"Bearer {test_user['token']}"}
        await client.post(f"/users/follow/{test_user2['id']}", headers=headers)

        # Then get following list
        response = await client.get("/users/following", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert len(data["items"]) > 0

    async def test_unfollow_user(self, client, test_user, test_user2):
        """Test unfollowing a user"""
        # First follow the user
        headers = {"Authorization": f"Bearer {test_user['token']}"}
        await client.post(f"/users/follow/{test_user2['id']}", headers=headers)

        # Then unfollow
        response = await client.delete(f"/users/follow/{test_user2['id']}", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "message" in data


class TestPlaces:
    """Test place-related endpoints"""

    async def test_get_place(self, client, test_user, test_place):
        """Test getting place details"""
        headers = {"Authorization": f"Bearer {test_user['token']}"}
        response = await client.get(f"/places/{test_place.id}", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == test_place.name
        assert data["address"] == test_place.address

    async def test_get_place_stats(self, client, test_user, test_place):
        """Test getting enhanced place statistics"""
        headers = {"Authorization": f"Bearer {test_user['token']}"}
        response = await client.get(f"/places/{test_place.id}/stats/enhanced", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "total_checkins" in data
        assert "average_rating" in data

    async def test_place_search(self, client, test_user, test_place):
        """Test place search"""
        headers = {"Authorization": f"Bearer {test_user['token']}"}
        response = await client.get("/places/search/quick", params={
            "q": "Test",
            "lat": 40.7128,
            "lng": -74.0060,
            "radius_km": 10
        }, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_trending_places(self, client, test_user):
        """Test trending places"""
        headers = {"Authorization": f"Bearer {test_user['token']}"}
        response = await client.get("/places/trending", params={
            "lat": 40.7128,
            "lng": -74.0060,
            "radius_km": 10
        }, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "items" in data


class TestCheckIns:
    """Test check-in related endpoints"""

    async def test_create_checkin(self, client, test_user, test_place):
        """Test creating a check-in"""
        headers = {"Authorization": f"Bearer {test_user['token']}"}
        checkin_data = {
            "place_id": test_place.id,
            "message": "Great place!",
            "visibility": "public",
            "rating": 4.5
        }
        response = await client.post("/places/check-ins/full", json=checkin_data, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Great place!"
        assert data["rating"] == 4.5

    async def test_get_checkin_details(self, client, test_user, test_place):
        """Test getting check-in details"""
        # First create a check-in
        headers = {"Authorization": f"Bearer {test_user['token']}"}
        checkin_data = {
            "place_id": test_place.id,
            "message": "Test check-in",
            "visibility": "public"
        }
        create_response = await client.post("/places/check-ins/full", json=checkin_data, headers=headers)
        checkin_id = create_response.json()["id"]

        # Then get details
        response = await client.get(f"/check-ins/{checkin_id}", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Test check-in"

    async def test_like_checkin(self, client, test_user, test_user2, test_place):
        """Test liking a check-in"""
        # Create check-in with user2
        headers2 = {"Authorization": f"Bearer {test_user2['token']}"}
        checkin_data = {
            "place_id": test_place.id,
            "message": "Like this check-in",
            "visibility": "public"
        }
        create_response = await client.post("/places/check-ins/full", json=checkin_data, headers=headers2)
        checkin_id = create_response.json()["id"]

        # Like it with user1
        headers1 = {"Authorization": f"Bearer {test_user['token']}"}
        response = await client.post(f"/check-ins/{checkin_id}/like", headers=headers1)
        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    async def test_comment_checkin(self, client, test_user, test_user2, test_place):
        """Test commenting on a check-in"""
        # Create check-in with user2
        headers2 = {"Authorization": f"Bearer {test_user2['token']}"}
        checkin_data = {
            "place_id": test_place.id,
            "message": "Comment on this",
            "visibility": "public"
        }
        create_response = await client.post("/places/check-ins/full", json=checkin_data, headers=headers2)
        checkin_id = create_response.json()["id"]

        # Comment with user1
        headers1 = {"Authorization": f"Bearer {test_user['token']}"}
        comment_data = {"content": "Great check-in!"}
        response = await client.post(f"/check-ins/{checkin_id}/comments", json=comment_data, headers=headers1)
        assert response.status_code == 200
        data = response.json()
        assert data["content"] == "Great check-in!"


class TestDirectMessages:
    """Test direct message endpoints"""

    async def test_create_dm_thread(self, client, test_user, test_user2):
        """Test creating a DM thread"""
        headers = {"Authorization": f"Bearer {test_user['token']}"}
        thread_data = {
            "user_id": test_user2["id"],
            "message": "Hello there!"
        }
        response = await client.post("/dms/threads", json=thread_data, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "thread_id" in data
        assert data["message"]["content"] == "Hello there!"

    async def test_get_dm_inbox(self, client, test_user, test_user2):
        """Test getting DM inbox"""
        # First create a thread
        headers = {"Authorization": f"Bearer {test_user['token']}"}
        thread_data = {
            "user_id": test_user2["id"],
            "message": "Inbox test"
        }
        await client.post("/dms/threads", json=thread_data, headers=headers)

        # Then get inbox
        response = await client.get("/dms/inbox", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert len(data["items"]) > 0

    async def test_send_dm_message(self, client, test_user, test_user2):
        """Test sending a DM message"""
        # First create a thread
        headers = {"Authorization": f"Bearer {test_user['token']}"}
        thread_data = {
            "user_id": test_user2["id"],
            "message": "Initial message"
        }
        thread_response = await client.post("/dms/threads", json=thread_data, headers=headers)
        thread_id = thread_response.json()["thread_id"]

        # Then send another message
        message_data = {"content": "Follow-up message"}
        response = await client.post(f"/dms/threads/{thread_id}/messages", json=message_data, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["content"] == "Follow-up message"

    async def test_mark_dm_read(self, client, test_user, test_user2):
        """Test marking DM as read"""
        # First create a thread
        headers = {"Authorization": f"Bearer {test_user['token']}"}
        thread_data = {
            "user_id": test_user2["id"],
            "message": "Read test"
        }
        thread_response = await client.post("/dms/threads", json=thread_data, headers=headers)
        thread_id = thread_response.json()["thread_id"]

        # Then mark as read
        response = await client.post(f"/dms/threads/{thread_id}/read", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "message" in data


class TestCollections:
    """Test collection endpoints"""

    async def test_create_collection(self, client, test_user):
        """Test creating a collection"""
        headers = {"Authorization": f"Bearer {test_user['token']}"}
        collection_data = {
            "name": "My Favorite Places",
            "visibility": "public"
        }
        response = await client.post("/collections", json=collection_data, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "My Favorite Places"
        assert data["visibility"] == "public"

    async def test_get_collections(self, client, test_user):
        """Test getting user collections"""
        # First create a collection
        headers = {"Authorization": f"Bearer {test_user['token']}"}
        collection_data = {
            "name": "Test Collection",
            "visibility": "public"
        }
        await client.post("/collections", json=collection_data, headers=headers)

        # Then get collections
        response = await client.get("/collections", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert len(data["items"]) > 0

    async def test_add_checkin_to_collection(self, client, test_user, test_place):
        """Test adding check-in to collection"""
        # First create a collection
        headers = {"Authorization": f"Bearer {test_user['token']}"}
        collection_data = {
            "name": "Test Collection",
            "visibility": "public"
        }
        collection_response = await client.post("/collections", json=collection_data, headers=headers)
        collection_id = collection_response.json()["id"]

        # Create a check-in
        checkin_data = {
            "place_id": test_place.id,
            "message": "Collection test",
            "visibility": "public"
        }
        checkin_response = await client.post("/places/check-ins/full", json=checkin_data, headers=headers)
        checkin_id = checkin_response.json()["id"]

        # Add to collection
        add_data = {"check_in_id": checkin_id}
        response = await client.post(f"/collections/{collection_id}/items", json=add_data, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "message" in data


class TestActivityFeed:
    """Test activity feed endpoints"""

    async def test_get_activity_feed(self, client, test_user, test_user2):
        """Test getting activity feed"""
        # First follow user2
        headers = {"Authorization": f"Bearer {test_user['token']}"}
        await client.post(f"/users/follow/{test_user2['id']}", headers=headers)

        # Create activity by having user2 create a check-in
        headers2 = {"Authorization": f"Bearer {test_user2['token']}"}
        checkin_data = {
            "place_id": 1,  # Assuming place with ID 1 exists
            "message": "Activity test",
            "visibility": "public"
        }
        await client.post("/places/check-ins/full", json=checkin_data, headers=headers2)

        # Get activity feed
        response = await client.get("/activity/feed", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    async def test_get_my_activities(self, client, test_user, test_place):
        """Test getting user's own activities"""
        # Create a check-in to generate activity
        headers = {"Authorization": f"Bearer {test_user['token']}"}
        checkin_data = {
            "place_id": test_place.id,
            "message": "My activity",
            "visibility": "public"
        }
        await client.post("/places/check-ins/full", json=checkin_data, headers=headers)

        # Get my activities
        response = await client.get("/activity/my-activities", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "items" in data


class TestSettings:
    """Test settings endpoints"""

    async def test_get_privacy_settings(self, client, test_user):
        """Test getting privacy settings"""
        headers = {"Authorization": f"Bearer {test_user['token']}"}
        response = await client.get("/settings/privacy", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "dm_privacy" in data
        assert "checkins_default_visibility" in data

    async def test_update_privacy_settings(self, client, test_user):
        """Test updating privacy settings"""
        headers = {"Authorization": f"Bearer {test_user['token']}"}
        settings_data = {
            "dm_privacy": "followers_only",
            "checkins_default_visibility": "private",
            "collections_default_visibility": "private"
        }
        response = await client.put("/settings/privacy", json=settings_data, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["dm_privacy"] == "followers_only"
        assert data["checkins_default_visibility"] == "private"

    async def test_get_notification_preferences(self, client, test_user):
        """Test getting notification preferences"""
        headers = {"Authorization": f"Bearer {test_user['token']}"}
        response = await client.get("/settings/notifications", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "dm_messages" in data
        assert "follows" in data

    async def test_update_notification_preferences(self, client, test_user):
        """Test updating notification preferences"""
        headers = {"Authorization": f"Bearer {test_user['token']}"}
        preferences_data = {
            "dm_messages": True,
            "dm_requests": True,
            "follows": False,
            "likes": True,
            "comments": True,
            "activity_summary": False,
            "marketing": False
        }
        response = await client.put("/settings/notifications", json=preferences_data, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["dm_messages"] == True
        assert data["follows"] == False


class TestSupport:
    """Test support endpoints"""

    async def test_create_support_ticket(self, client, test_user):
        """Test creating a support ticket"""
        headers = {"Authorization": f"Bearer {test_user['token']}"}
        ticket_data = {
            "subject": "Test Issue",
            "message": "This is a test support ticket"
        }
        response = await client.post("/support/tickets", json=ticket_data, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["subject"] == "Test Issue"
        assert data["message"] == "This is a test support ticket"

    async def test_get_support_tickets(self, client, test_user):
        """Test getting user's support tickets"""
        # First create a ticket
        headers = {"Authorization": f"Bearer {test_user['token']}"}
        ticket_data = {
            "subject": "Test Ticket",
            "message": "Test message"
        }
        await client.post("/support/tickets", json=ticket_data, headers=headers)

        # Then get tickets
        response = await client.get("/support/tickets", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert len(data["items"]) > 0


class TestSystem:
    """Test system endpoints"""

    async def test_health_check(self, client):
        """Test health check endpoint"""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    async def test_metrics_endpoint(self, client):
        """Test metrics endpoint (should be accessible in dev mode)"""
        response = await client.get("/metrics")
        assert response.status_code == 200
        # Should return Prometheus metrics


class TestOnboarding:
    """Test onboarding endpoints"""

    async def test_request_phone_otp(self, client):
        """Test requesting phone OTP"""
        response = await client.post("/onboarding/request-phone-otp", json={
            "phone": "+1234567890"
        })
        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    async def test_verify_phone_otp(self, client):
        """Test verifying phone OTP"""
        # First request OTP
        await client.post("/onboarding/request-phone-otp", json={
            "phone": "+1234567890"
        })

        # Then verify (using test OTP 123456)
        response = await client.post("/onboarding/verify-phone-otp", json={
            "phone": "+1234567890",
            "otp": "123456"
        })
        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    async def test_check_username_availability(self, client):
        """Test checking username availability"""
        response = await client.get("/onboarding/check-username/testusername")
        assert response.status_code == 200
        data = response.json()
        assert "available" in data

    async def test_complete_user_setup(self, client):
        """Test completing user setup"""
        # First verify phone
        await client.post("/onboarding/request-phone-otp", json={"phone": "+1234567890"})
        await client.post("/onboarding/verify-phone-otp", json={
            "phone": "+1234567890",
            "otp": "123456"
        })

        # Then complete setup
        setup_data = {
            "username": "newuser",
            "display_name": "New User",
            "bio": "New user bio",
            "interests": ["food", "travel"]
        }
        response = await client.post("/onboarding/complete-setup", json=setup_data)
        assert response.status_code == 200
        data = response.json()
        assert "message" in data


# Run all tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
