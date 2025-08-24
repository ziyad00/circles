#!/usr/bin/env python3
"""
Create Admin User Script
Creates an admin user for testing admin-only endpoints
"""

from app.services.jwt_service import JWTService
from app.models import User
from app.database import get_db
import asyncio
import sys
import os
from datetime import datetime

# Add the app directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))


async def create_admin_user():
    """Create an admin user"""
    print("🔧 Creating Admin User")
    print("=" * 40)

    try:
        async for db in get_db():
            # Check if admin user already exists
            from sqlalchemy import select
            result = await db.execute(select(User).where(User.is_admin == True))
            existing_admin = result.scalar_one_or_none()

            if existing_admin:
                print(f"✅ Admin user already exists:")
                print(f"   • ID: {existing_admin.id}")
                print(f"   • Username: {existing_admin.username}")
                print(f"   • Email: {existing_admin.email}")
                print(f"   • Phone: {existing_admin.phone}")
                print(f"   • Is Admin: {existing_admin.is_admin}")

                # Generate JWT token for existing admin
                token = JWTService.create_token(existing_admin.id)
                print(f"   • JWT Token: {token}")
                return existing_admin, token

            # Create new admin user
            admin_user = User(
                username="admin",
                email="admin@circles.com",
                phone="+966500000000",
                name="System Administrator",
                is_verified=True,
                is_admin=True,
                bio="System administrator for Circles app"
            )

            db.add(admin_user)
            await db.commit()
            await db.refresh(admin_user)

            print(f"✅ Admin user created successfully:")
            print(f"   • ID: {admin_user.id}")
            print(f"   • Username: {admin_user.username}")
            print(f"   • Email: {admin_user.email}")
            print(f"   • Phone: {admin_user.phone}")
            print(f"   • Is Admin: {admin_user.is_admin}")

            # Generate JWT token
            token = JWTService.create_token(admin_user.id)
            print(f"   • JWT Token: {token}")

            return admin_user, token

    except Exception as e:
        print(f"❌ Failed to create admin user: {str(e)}")
        return None, None


async def test_admin_access():
    """Test admin-only endpoints"""
    print("\n🧪 Testing Admin Access")
    print("=" * 40)

    admin_user, token = await create_admin_user()

    if not admin_user or not token:
        print("❌ Cannot test admin access - no admin user created")
        return

    # Test admin-only endpoints
    import httpx

    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        headers = {"Authorization": f"Bearer {token}"}

        # Test seeding endpoint
        print("\n1️⃣ Testing seeding endpoint...")
        try:
            response = await client.post(
                "/places/seed/from-osm",
                params={
                    "min_lat": 24.7136,
                    "min_lon": 46.6753,
                    "max_lat": 24.7336,
                    "max_lon": 46.6953
                },
                headers=headers
            )
            if response.status_code == 200:
                print("   ✅ Admin can access seeding endpoint")
                data = response.json()
                print(f"   📊 Seeded {data.get('seeded_count', 0)} places")
            else:
                print(f"   ❌ Admin access failed: {response.status_code}")
                print(f"   📄 Response: {response.text}")
        except Exception as e:
            print(f"   ❌ Error testing seeding: {str(e)}")

        # Test stats endpoint
        print("\n2️⃣ Testing stats endpoint...")
        try:
            response = await client.get("/places/stats/enrichment", headers=headers)
            if response.status_code == 200:
                print("   ✅ Admin can access stats endpoint")
                data = response.json()
                print(f"   📊 Total places: {data.get('total_places', 0)}")
                print(
                    f"   🔄 Enriched places: {data.get('enriched_places', 0)}")
            else:
                print(f"   ❌ Admin access failed: {response.status_code}")
                print(f"   📄 Response: {response.text}")
        except Exception as e:
            print(f"   ❌ Error testing stats: {str(e)}")


if __name__ == "__main__":
    asyncio.run(test_admin_access())
