#!/usr/bin/env python3
"""
Test Admin Access Script
Tests admin-only endpoints with both admin and regular users
"""

import asyncio
import sys
import os

# Add the app directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.database import get_db
from app.models import User
from app.services.jwt_service import JWTService


async def test_admin_access():
    """Test admin-only endpoints with different user types"""
    print("🧪 Testing Admin-Only Access")
    print("=" * 50)
    
    try:
        async for db in get_db():
            # Get admin user
            from sqlalchemy import select
            admin_result = await db.execute(select(User).where(User.is_admin == True))
            admin_user = admin_result.scalar_one_or_none()
            
            if not admin_user:
                print("❌ No admin user found. Run create_admin_user.py first.")
                return
            
            # Get or create regular user
            regular_result = await db.execute(select(User).where(User.is_admin == False))
            regular_users = regular_result.scalars().all()
            regular_user = regular_users[0] if regular_users else None
            
            if not regular_user:
                # Create a regular user
                regular_user = User(
                    username="testuser",
                    email="test@circles.com",
                    phone="+966500000001",
                    name="Test User",
                    is_verified=True,
                    is_admin=False
                )
                db.add(regular_user)
                await db.commit()
                await db.refresh(regular_user)
                print("✅ Created regular user for testing")
            
            # Generate tokens
            admin_token = JWTService.create_token(admin_user.id)
            regular_token = JWTService.create_token(regular_user.id)
            
            print(f"\n👤 Admin User:")
            print(f"   • ID: {admin_user.id}")
            print(f"   • Username: {admin_user.username}")
            print(f"   • Is Admin: {admin_user.is_admin}")
            print(f"   • Token: {admin_token[:50]}...")
            
            print(f"\n👤 Regular User:")
            print(f"   • ID: {regular_user.id}")
            print(f"   • Username: {regular_user.username}")
            print(f"   • Is Admin: {regular_user.is_admin}")
            print(f"   • Token: {regular_token[:50]}...")
            
            # Test endpoints
            import httpx
            
            async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
                # Test seeding endpoint
                print(f"\n🔒 Testing Seeding Endpoint:")
                
                # Test with admin token
                admin_response = await client.post(
                    "/places/seed/from-osm",
                    params={"min_lat": 24.7136, "min_lon": 46.6753, "max_lat": 24.7336, "max_lon": 46.6953},
                    headers={"Authorization": f"Bearer {admin_token}"}
                )
                print(f"   👑 Admin access: {admin_response.status_code} - {admin_response.text[:100]}...")
                
                # Test with regular user token
                regular_response = await client.post(
                    "/places/seed/from-osm",
                    params={"min_lat": 24.7136, "min_lon": 46.6753, "max_lat": 24.7336, "max_lon": 46.6953},
                    headers={"Authorization": f"Bearer {regular_token}"}
                )
                print(f"   👤 Regular user access: {regular_response.status_code} - {regular_response.text}")
                
                # Test stats endpoint
                print(f"\n📊 Testing Stats Endpoint:")
                
                # Test with admin token
                admin_stats_response = await client.get(
                    "/places/stats/enrichment",
                    headers={"Authorization": f"Bearer {admin_token}"}
                )
                print(f"   👑 Admin access: {admin_stats_response.status_code} - {admin_stats_response.text[:100]}...")
                
                # Test with regular user token
                regular_stats_response = await client.get(
                    "/places/stats/enrichment",
                    headers={"Authorization": f"Bearer {regular_token}"}
                )
                print(f"   👤 Regular user access: {regular_stats_response.status_code} - {regular_stats_response.text}")
                
                # Test without token
                print(f"\n🚫 Testing Without Token:")
                no_token_response = await client.post(
                    "/places/seed/from-osm",
                    params={"min_lat": 24.7136, "min_lon": 46.6753, "max_lat": 24.7336, "max_lon": 46.6953}
                )
                print(f"   🚫 No token: {no_token_response.status_code} - {no_token_response.text}")
                
    except Exception as e:
        print(f"❌ Error testing admin access: {str(e)}")


if __name__ == "__main__":
    asyncio.run(test_admin_access())
