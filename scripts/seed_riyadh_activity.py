import sys
import os
import asyncio
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

# Ensure project root on path for app.* imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import AsyncSessionLocal
from app.models import User, Place, CheckIn


RIYADH_BBOX = (24.3, 25.2, 46.2, 47.3)  # (min_lat, max_lat, min_lon, max_lon)


async def seed_recent_checkins(max_users: int = 10, max_places: int = 20) -> int:
    now = datetime.now(timezone.utc)
    created = 0
    async with AsyncSessionLocal() as session:
        # Pick users
        users = (await session.execute(select(User).order_by(User.id.asc()).limit(max_users))).scalars().all()
        if not users:
            return 0

        # Pick Riyadh places (by city or bbox)
        places_q = select(Place).limit(max_places)
        # Prefer city label
        riyadh_places = (await session.execute(select(Place).where(Place.city == "Riyadh").limit(max_places))).scalars().all()
        if not riyadh_places:
            min_lat, max_lat, min_lon, max_lon = RIYADH_BBOX
            riyadh_places = (
                await session.execute(
                    select(Place).where(
                        Place.latitude >= min_lat,
                        Place.latitude <= max_lat,
                        Place.longitude >= min_lon,
                        Place.longitude <= max_lon,
                    ).limit(max_places)
                )
            ).scalars().all()
        if not riyadh_places:
            return 0

        for user in users:
            # Each user checks into 1-2 random places recently
            for place in random.sample(riyadh_places, k=min(len(riyadh_places), random.randint(1, 2))):
                checkin = CheckIn(
                    user_id=user.id,
                    place_id=place.id,
                    note=random.choice(
                        ["Quick stop", "Coffee time", "Lunch", None]),
                    visibility=getattr(
                        user, "checkins_default_visibility", "public"),
                    created_at=now - timedelta(minutes=random.randint(0, 180)),
                    expires_at=now + timedelta(hours=24),
                )
                session.add(checkin)
                created += 1

        await session.commit()
    return created


async def main():
    n = await seed_recent_checkins()
    print(f"Seeded {n} recent Riyadh check-ins")


if __name__ == "__main__":
    asyncio.run(main())
